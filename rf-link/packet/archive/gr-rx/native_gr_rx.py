#!/usr/bin/env python3
"""
Native SoapySDR + GNU Radio digital blocks BPSK packet receiver.

Two modes:
  1. Offline decode of a captured IQ file (--file)
  2. Live capture via SoapySDR HackRF (--freq, --lna, --vga, --serial)

The TX sends: preamble(256 alternating bits) + sync_word(0xE38FC0FC, 32 bits) +
              payload("HELLO WORLD\\n", 12 bytes = 96 bits). Packets repeat ~every 2 sec.

Processing chain (all numpy, verified on /tmp/rx_cable_good.iq):
  1. Coarse FO estimate via FFT peak
  2. Mix down to baseband
  3. RRC matched filter
  4. Symbol timing via decimation phase sweep
  5. Preamble correlation for packet detection
  6. Fine FO correction using preamble
  7. Sync word correlation to refine timing
  8. Phase correction via sync word
  9. Hard decision → bits → bytes → ASCII
"""
import numpy as np
import argparse, sys, os, time
from gnuradio.filter import firdes

# ── System Constants ──────────────────────────────────────────────────────────
SYNC_WORD = 0xE38FC0FC        # 32-bit sync word
EXPECTED_PAYLOAD = b"HELLO WORLD\n"  # 12 bytes = 96 bits

# BPSK bit→symbol mapping used by TX: bit=0→+1.0, bit=1→-1.0
PRE_BITS = np.array(([1, 0] * 128)[:256], dtype=np.uint8)
PRE_SYMS = -2.0 * PRE_BITS + 1.0   # [1,0] → [-1,+1], alternating

SYNC_BITS = np.array([(SYNC_WORD >> (31 - i)) & 1 for i in range(32)], dtype=np.uint8)
SYNC_SYMS = -2.0 * SYNC_BITS + 1.0  # same BPSK map


# ── I/Q Helpers ───────────────────────────────────────────────────────────────

def load_iq(filename):
    """Load raw int8 interleaved IQ file → complex float64, zero-mean."""
    raw = np.fromfile(filename, dtype=np.int8)
    I = raw[0::2].astype(np.float64)
    Q = raw[1::2].astype(np.float64)
    I -= np.mean(I)
    Q -= np.mean(Q)
    return I + 1j * Q


def estimate_fo_fft(samples, fs=2e6, search_khz=(4.0, 7.0)):
    """
    FFT-based coarse FO estimation.
    Searches the specified kHz range (away from DC) for the spectral peak.
    Returns offset in Hz (positive or negative).
    """
    nfft = min(524288, len(samples))
    windowed = samples[:nfft] * np.hanning(nfft)
    fft = np.fft.fftshift(np.fft.fft(windowed))
    fp = np.abs(fft) ** 2
    freqs = np.fft.fftshift(np.fft.fftfreq(nfft, 1.0 / fs))

    lo_hz, hi_hz = search_khz[0] * 1000, search_khz[1] * 1000
    mask = (np.abs(freqs) >= lo_hz) & (np.abs(freqs) <= hi_hz)
    if not np.any(mask):
        guard = int(1000 * nfft / fs)
        mask = np.ones(nfft, dtype=bool)
        mask[nfft // 2 - guard:nfft // 2 + guard] = False
    return freqs[np.argmax(fp * mask)]


def make_rrc_taps(sps=20, alpha=0.35, ntaps=None):
    """Build normalised RRC matched filter taps (same shape as TX pulse shaping)."""
    if ntaps is None:
        ntaps = 11 * sps
    taps = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, alpha, ntaps), dtype=np.float64)
    return taps / np.sqrt(np.sum(taps ** 2))


def mix_down(samples, fo_hz, fs=2e6):
    """Mix samples down by fo_hz. Returns baseband complex array."""
    t = np.arange(len(samples), dtype=np.float64)
    return samples * np.exp(-2j * np.pi * fo_hz * t / fs)


# ── Packet Detection & Decode ────────────────────────────────────────────────

def find_and_decode_packets(symbols, sym_rate, sps=20, resid_fo_range=600,
                            resid_fo_steps=401, align_shifts=(-2, -1, 0, 1, 2)):
    """
    Find packets via preamble correlation, fine-tune FO/timing, decode.
    Returns list of decoded-packet dicts sorted by score descending.
    """
    if len(symbols) < 500:
        return []

    # ── Preamble correlation ──
    pre_corr = np.correlate(symbols, PRE_SYMS, 'same')
    pre_corr_abs = np.abs(pre_corr)
    threshold = np.mean(pre_corr_abs) + 5.0 * np.std(pre_corr_abs)

    # Local maxima
    candidates = []
    for i in range(256, len(pre_corr_abs) - 384):
        if pre_corr_abs[i] > threshold:
            left = pre_corr_abs[max(0, i - 8):i]
            right = pre_corr_abs[i + 1:min(len(pre_corr_abs), i + 9)]
            if (len(left) == 0 or pre_corr_abs[i] >= np.max(left)) and \
               (len(right) == 0 or pre_corr_abs[i] >= np.max(right)):
                candidates.append(i)

    # Deduplicate nearby peaks
    candidates.sort()
    deduped = []
    for c in candidates:
        if not deduped or c - deduped[-1] >= 64:
            deduped.append(c)

    # ── Fine FO search grid (pre-compute rotation vectors) ──
    fos = np.linspace(-resid_fo_range, resid_fo_range, resid_fo_steps)
    k_256 = np.arange(256, dtype=np.float64)

    all_results = []
    for pk in deduped:
        # Naive preamble start (correlation output pk ≈ pre_start + 128)
        # Verified: real start = pk - 129 for consistent 1-symbol offset
        base_start = pk - 129

        for shift in align_shifts:
            pre_start = base_start + shift
            pkt_end = pre_start + 256 + 32 + 96 + 16
            if pre_start < 0 or pkt_end > len(symbols):
                continue

            seg = symbols[pre_start:pre_start + 256 + 32 + 96 + 16]
            if len(seg) < 256 + 32 + 96:
                continue

            # ── Fine FO via preamble ──
            # Sweep residual FO to maximise correlation with preamble template
            best_fo = 0.0
            best_corr = 0.0
            for fo in fos:
                seg_corr = seg[:256] * np.exp(-1j * 2 * np.pi * fo / sym_rate * k_256)
                corr_val = np.abs(np.dot(seg_corr, PRE_SYMS))
                if corr_val > best_corr:
                    best_corr = corr_val
                    best_fo = fo

            if best_corr < 10:
                continue

            # Apply fine FO correction
            k_full = np.arange(len(seg), dtype=np.float64)
            corrected = seg * np.exp(-1j * 2 * np.pi * best_fo / sym_rate * k_full)

            # ── Extract sync word ──
            sync_syms = corrected[256:256 + 32]
            if len(sync_syms) < 32:
                continue

            # Phase correction (BPSK carrier recovery)
            phase_est = np.angle(np.dot(sync_syms, SYNC_SYMS.conj()))
            sync_corr = sync_syms * np.exp(-1j * phase_est)
            sync_bits = (sync_corr.real < 0).astype(np.uint8)
            sync_word_got = 0
            for b in sync_bits:
                sync_word_got = (sync_word_got << 1) | int(b)

            # ── Payload extraction ──
            payload_syms = corrected[256 + 32:256 + 32 + 96]
            if len(payload_syms) < 96:
                continue
            payload_corr = payload_syms * np.exp(-1j * phase_est)

            for invert in (False, True):
                bits = (payload_corr.real < 0) ^ invert
                if len(bits) < 96:
                    continue
                # Pack bits to bytes (MSB first, matching TX)
                byte_list = []
                for bi in range(0, 96, 8):
                    bv = 0
                    for bj in range(8):
                        bv |= (int(bits[bi + bj]) << (7 - bj))
                    byte_list.append(bv)
                decoded = bytes(byte_list)

                # Score against expected payload (byte-level match)
                score = sum(1 for a, b in zip(decoded, EXPECTED_PAYLOAD) if a == b) \
                    if len(decoded) >= len(EXPECTED_PAYLOAD) else 0

                sync_match = (sync_word_got == SYNC_WORD)
                sync_match_inv = (sync_word_got == (~SYNC_WORD & 0xFFFFFFFF))

                all_results.append({
                    'pk': pk,
                    'pre_start': pre_start,
                    'shift': shift,
                    'resid_fo': best_fo,
                    'sync_word_got': sync_word_got,
                    'sync_match': sync_match or sync_match_inv,
                    'phase_est': phase_est,
                    'invert': invert,
                    'score': score,
                    'decoded': decoded,
                    'sync_corr': best_corr,
                    'pkt_length': len(seg),
                })

    # Sort: best score first
    all_results.sort(key=lambda r: (-r['score'], -(r.get('sync_corr') or 0)))
    return all_results


# ── Offline File Decode ───────────────────────────────────────────────────────

def decode_file(filename, fs=2e6, sps=20):
    """
    Full offline decode of a captured IQ file.
    """
    print(f"[Decode] Loading {filename}...", flush=True)
    samples = load_iq(filename)
    n_sec = len(samples) / fs
    print(f"[Decode] {len(samples)} samples ({n_sec:.1f}s)", flush=True)

    # 1. Coarse FO
    fo = estimate_fo_fft(samples, fs)
    print(f"[Decode] Coarse FO: {fo / 1e3:.3f} kHz", flush=True)

    # 2. Mix down to baseband
    bb = mix_down(samples, fo, fs)

    # 3. RRC matched filter (on real part for BPSK)
    rrc_taps = make_rrc_taps(sps)
    bb_filtered = np.convolve(bb.real, rrc_taps, 'same')

    sym_rate = fs / float(sps)
    print(f"[Decode] Symbol rate: {sym_rate / 1e3:.1f} kHz", flush=True)

    # 4. Try all decimation phases
    print(f"[Decode] Scanning {sps} decimation phases...", flush=True)
    all_results = []
    for phase in range(sps):
        symbols = bb_filtered[phase::sps]
        if len(symbols) < 500:
            continue
        results = find_and_decode_packets(symbols, sym_rate, sps)
        for r in results:
            r['phase'] = phase
        all_results.extend(results)

    all_results.sort(key=lambda r: (-r['score'], -(r.get('sync_corr') or 0)))
    return all_results


# ── Live Capture via SoapySDR ────────────────────────────────────────────────

def capture_live(args):
    """Live capture using SoapySDR native HackRF API, then decode the buffer."""
    import SoapySDR
    from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_RX

    fs = int(args.samp)
    n_samples = int(fs * args.duration)

    print(f"[Live] Opening HackRF (serial={args.serial})...", flush=True)
    try:
        sdr = SoapySDR.Device(f"driver=hackrf,serial={args.serial}")
    except Exception as e:
        print(f"[Live] SoapySDR error: {e}", flush=True)
        return

    sdr.setSampleRate(SOAPY_SDR_RX, 0, fs)
    sdr.setBandwidth(SOAPY_SDR_RX, 0, 0.0)
    sdr.setFrequency(SOAPY_SDR_RX, 0, args.freq)
    sdr.setGain(SOAPY_SDR_RX, 0, "LNA", float(args.lna))
    sdr.setGain(SOAPY_SDR_RX, 0, "VGA", float(args.vga))
    sdr.setGain(SOAPY_SDR_RX, 0, "AMP", 1.0 if args.amp else 0.0)

    rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [0])
    sdr.activateStream(rx_stream)

    print(f"[Live] Capturing {args.duration}s at {fs / 1e6:.1f} Msps "
          f"(N={n_samples})...", flush=True)

    chunk = np.zeros(65536, dtype=np.complex64)
    buf_c = np.array([], dtype=np.complex64)
    collected = 0
    last_report = time.time()
    timeout_us = int(2e6)

    try:
        while collected < n_samples:
            sr = sdr.readStream(rx_stream, [chunk], len(chunk), timeoutUs=timeout_us)
            if sr.ret > 0:
                buf_c = np.concatenate([buf_c, chunk[:sr.ret]])
                collected += sr.ret
            elif sr.ret == 0:
                continue
            else:
                print(f"[Live] Stream error: {sr.ret}", flush=True)
                break

            now = time.time()
            if now - last_report >= 1.0:
                pct = 100.0 * collected / n_samples
                print(f"[Live] {collected}/{n_samples} ({pct:.0f}%)", flush=True)
                last_report = now
    except KeyboardInterrupt:
        print("[Live] Interrupted.", flush=True)

    sdr.deactivateStream(rx_stream)
    sdr.closeStream(rx_stream)
    print(f"[Live] Captured {len(buf_c)} complex samples", flush=True)

    if len(buf_c) == 0:
        print("[Live] No samples!", flush=True)
        return

    samples_64 = buf_c.astype(np.float64)

    # ── Decode ──
    sps = 20
    fo = estimate_fo_fft(samples_64, fs)
    print(f"[Decode] Coarse FO: {fo / 1e3:.3f} kHz", flush=True)

    bb = mix_down(samples_64, fo, fs)
    rrc_taps = make_rrc_taps(sps)
    bb_filtered = np.convolve(bb.real, rrc_taps, 'same')
    sym_rate = fs / float(sps)

    all_results = []
    for phase in range(sps):
        symbols = bb_filtered[phase::sps]
        if len(symbols) < 500:
            continue
        results = find_and_decode_packets(symbols, sym_rate, sps)
        for r in results:
            r['phase'] = phase
        all_results.extend(results)

    all_results.sort(key=lambda r: (-r['score'], -(r.get('sync_corr') or 0)))
    return all_results


# ── Output Formatting ─────────────────────────────────────────────────────────

def print_results(results, top_n=20):
    """Print decode results table."""
    print()
    print("=" * 72)
    print("DECODE RESULTS")
    print("=" * 72)

    if not results:
        print("  No packets found.")
        print()
        return

    printed = set()
    perfect = 0
    for r in results:
        key = (r['phase'], r['pre_start'], r['invert'])
        if key in printed:
            continue
        printed.add(key)

        text = r['decoded'].decode('ascii', errors='replace')
        # Sanitize for display
        display = text.replace('\x00', '.').replace('\x05', '.')

        sync_hex = f"0x{r['sync_word_got']:08X}"
        sync_tag = "SYNC_OK" if r.get('sync_match') else sync_hex

        print(f"  score={r['score']:2d}/{len(EXPECTED_PAYLOAD)} | "
              f"ph={r['phase']:2d} | shift={r['shift']:+2d} | "
              f"rFO={r['resid_fo']:+.1f}Hz | inv={int(r['invert'])} | "
              f"{sync_tag:10s} | {display!r}")

        if r['score'] == len(EXPECTED_PAYLOAD):
            perfect += 1
            print(f"     ╰─ *** PERFECT DECODE #{perfect} ***")
            print()

        if len(printed) >= top_n:
            break

    if perfect:
        print(f"  ✅  {perfect} perfect decode(s)!")
    elif results:
        best = results[0]['score']
        print(f"  ⚠️  Best score: {best}/{len(EXPECTED_PAYLOAD)}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Native SoapySDR + GNU Radio digital blocks BPSK RX')
    parser.add_argument('--file', type=str, default=None,
                        help='IQ file to decode offline (int8 interleaved I/Q)')
    parser.add_argument('--freq', type=float, default=915e6,
                        help='Receive frequency (Hz)')
    parser.add_argument('--samp', type=float, default=2e6,
                        help='Sample rate (Hz)')
    parser.add_argument('--lna', type=float, default=8,
                        help='HackRF LNA gain (dB)')
    parser.add_argument('--vga', type=float, default=12,
                        help='HackRF VGA gain (dB)')
    parser.add_argument('--amp', action='store_true', default=False,
                        help='HackRF AMP enable')
    parser.add_argument('--serial', type=str, default='',
                        help='HackRF serial number')
    parser.add_argument('--duration', type=float, default=6.0,
                        help='Live capture duration (seconds)')
    args = parser.parse_args()

    if args.file:
        results = decode_file(args.file, args.samp)
        print_results(results)
    else:
        if not args.serial:
            print("Provide --serial for live RX or --file for offline decode.",
                  file=sys.stderr)
            sys.exit(1)
        results = capture_live(args)
        print_results(results)


if __name__ == '__main__':
    main()
