#!/usr/bin/env python3
"""
Enhanced Packet Receiver — sync-word correlation + FEC decode + CRC validate.

Architecture (built on the proven 121/121 sync-word technique):
  1. FFT-based FO estimation
  2. Mix down to baseband, RRC matched filter
  3. Try all SPS decimation phases
  4. Sync-word correlation (0xE38FC0FC at symbol rate)
  5. Extract FEC payload symbols → hard-decision bits → packet_decode()
  6. CRC validates → print decoded message

Variable-length payloads are handled by embedding a 1-byte length field
inside the FEC-protected data. The receiver always extracts enough FEC
symbols for the maximum payload size; packet_decode() reads the length
byte after FEC decoding and validates via CRC-32.

No more brute-force bit shifting or heuristic text matching.
"""
import numpy as np
import SoapySDR
import sys, time, argparse
from gnuradio.filter import firdes
from packet_codec import packet_decode, max_encoded_size_for_payload

SPS = 20; FS = 2000000

# Packet structure (from pkt_enhanced_tx.py)
PREAMBLE_BITS = 192  # 24 bytes of preamble
SYNC_BITS = 32

# Sync word: GNU Radio default access code (from packet_rx.py preamble_dummy).
# Chosen to NOT appear in the preamble, giving unambiguous correlation peaks.
SYNC_WORD = 0xACDDA4E2

# Precomputed sync word as BPSK symbols (0→+1, 1→-1)
_SYNC_BI = np.array([(SYNC_WORD >> (31 - i)) & 1 for i in range(SYNC_BITS)],
                    dtype=np.float64)
SYNC_BPSK = 2.0 * _SYNC_BI - 1.0

# Maximum FEC-encoded bytes the receiver will extract after the sync word.
# This is a fixed budget large enough for any payload up to 256 bytes.
MAX_FEC_BYTES = max_encoded_size_for_payload(512)      # 1038
MAX_FEC_SYMS = MAX_FEC_BYTES * 8                       # 8304 BPSK symbols (bits)


def rcc_taps(sps=SPS, alpha=0.35, ntaps=11):
    taps = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, alpha, ntaps * sps))
    return taps / np.max(np.abs(taps))


def scan_frequency(samples, search_width=10000, step=100):
    """
    Estimate carrier frequency offset by finding the spectral centroid
    within ±search_width Hz of DC.

    Uses power-weighted centroid (center of mass) rather than peak-picking,
    which is more robust against periodic preamble patterns.
    """
    nfft = min(262144, len(samples))
    window = np.hanning(nfft)
    seg = samples[:nfft] * window
    spec = np.abs(np.fft.fftshift(np.fft.fft(seg)))**2
    freqs = np.fft.fftshift(np.fft.fftfreq(nfft, 1.0 / FS))
    center = nfft // 2

    search_bins = int(search_width * nfft / FS)
    lo = max(0, center - search_bins)
    hi = min(nfft, center + search_bins + 1)

    band_spec = spec[lo:hi].copy()
    band_freqs = freqs[lo:hi]

    # Subtract noise floor (median of the band)
    noise_floor = np.median(band_spec)
    band_spec -= noise_floor
    band_spec = np.maximum(band_spec, 0)

    # Power-weighted centroid
    total_power = np.sum(band_spec)
    if total_power < 1e-10:
        return 0.0
    centroid = np.sum(band_freqs * band_spec) / total_power

    return centroid


def decode_payload_symbols(payload_syms):
    """
    Convert BPSK symbols to bytes via hard decisions, then packet_decode().
    Tries both normal and inverted polarity (180° phase ambiguity).

    The full set of extracted symbols is passed to packet_decode(),
    which handles the embedded length byte and CRC validation.

    Args:
        payload_syms: BPSK symbols (float, >0 = bit 0, <0 = bit 1)

    Returns:
        (decoded_message, polarity) or (None, None)
    """
    for invert, label in [(False, 'normal'), (True, 'inverted')]:
        bits = payload_syms if not invert else -payload_syms
        bits_hard = (bits < 0).astype(np.uint8)
        # Pack to bytes
        fec_data = bytearray()
        for i in range(0, len(bits_hard), 8):
            b = 0
            for j in range(8):
                if i + j < len(bits_hard):
                    b |= int(bits_hard[i + j]) << (7 - j)
            fec_data.append(b)
        # Pass all bytes — packet_decode handles length extraction
        result = packet_decode(bytes(fec_data))
        if result is not None:
            return result, label
    return None, None


def process_phase(filtered, phase, fo,
                   pre_bits=PREAMBLE_BITS,
                   top_n=5):
    """Process one SPS decimation phase, returning decoded packets.
    
    Instead of an adaptive threshold that can miss the real sync or
    be fooled by accidental correlations in the FEC payload, find the
    top `top_n` correlation peaks and try to decode each one.
    CRC validation on the decoded data filters out false alarms.
    
    Always extracts MAX_FEC_SYMS symbols after the sync word. The
    embedded length byte in the FEC-protected data tells packet_decode()
    how many bytes are real; extra symbols produce garbage that CRC
    catches.

    Args:
        filtered: RRC-filtered baseband signal
        phase: Decimation phase (0..SPS-1)
        fo: Carrier frequency offset estimate (Hz)
        pre_bits: Number of preamble symbols before sync word
        top_n: Number of correlation peaks to try
    """
    symbols = filtered[phase::SPS]
    # We need at least preamble+sync+stream_id_syms.  The actual FEC
    # payload may be shorter than MAX_FEC_SYMS for small messages;
    # packet_decode() handles undersized extraction via CRC.
    min_len = pre_bits + SYNC_BITS + 1
    if len(symbols) < min_len:
        return []

    corr = np.abs(np.correlate(symbols, SYNC_BPSK, 'valid'))
    th = np.mean(corr) + 2.5 * np.std(corr)  # relaxed threshold

    results = []
    radius = 10
    candidates = []
    for i in range(len(corr)):
        if corr[i] < th:
            continue
        lo, hi = max(0, i - radius), min(len(corr), i + radius + 1)
        if corr[i] < np.max(corr[lo:hi]):
            continue

        payload_start = i + SYNC_BITS
        if payload_start >= len(symbols):
            continue
        candidates.append((corr[i], i))

    # Sort by correlation strength, try top N
    candidates.sort(key=lambda x: -x[0])
    for corr_val, idx in candidates[:top_n]:
        payload_start = idx + SYNC_BITS
        # Extract available symbols up to MAX_FEC_SYMS
        n_syms = min(MAX_FEC_SYMS, len(symbols) - payload_start)
        payload = symbols[payload_start:payload_start + n_syms]
        msg, polarity = decode_payload_symbols(payload)
        if msg is not None:
            results.append({
                'message': msg,
                'fo': fo,
                'phase': phase,
                'sync_idx': idx,
                'polarity': polarity,
            })

    return results


class LiveReceiver:
    def __init__(self, freq=915e6, lna=8, vga=12,
                 amp=False, serial=None, duration=30):
        self.fs = int(FS)
        self.freq = freq
        self.lna, self.vga, self.amp = lna, vga, amp
        self.serial = serial
        self.duration = duration
        self.packets_found = 0

    def run(self):
        dev_str = (f'driver=hackrf,serial={self.serial}'
                   if self.serial else 'driver=hackrf')
        print(f"[EnhancedRX] Opening {dev_str} @ {self.freq/1e6:.3f} MHz...")
        sdr = SoapySDR.Device(dev_str)
        sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, self.fs)
        sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, self.freq)
        sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'LNA', float(self.lna))
        sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'VGA', float(self.vga))
        sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'AMP', float(self.amp))
        print(f"[EnhancedRX] LNA={self.lna} VGA={self.vga} "
              f"AMP={'on' if self.amp else 'off'}")

        rx_stream = sdr.setupStream(SoapySDR.SOAPY_SDR_RX,
                                    SoapySDR.SOAPY_SDR_CF32)
        sdr.activateStream(rx_stream)

        buf = np.zeros(524288, dtype=np.complex64)
        accum = []
        start = time.time()

        try:
            while time.time() - start < self.duration:
                sr = sdr.readStream(rx_stream, [buf], len(buf), timeoutUs=500000)
                if sr.ret > 0:
                    accum.append(buf[:sr.ret].copy())
                    total = sum(len(a) for a in accum)
                    if total >= 1_000_000:
                        chunk = np.concatenate(accum)
                        self._process_chunk(chunk)
                        accum = []
        except KeyboardInterrupt:
            pass

        sdr.deactivateStream(rx_stream)
        sdr.closeStream(rx_stream)
        elapsed = time.time() - start
        print(f"[EnhancedRX] DONE. {elapsed:.0f}s, "
              f"{self.packets_found} good packets.")

    def _process_chunk(self, samples):
        samples -= np.mean(samples)
        fo = scan_frequency(samples)
        t = np.arange(len(samples), dtype=np.float64)
        bb = samples * np.exp(-2j * np.pi * fo * t / FS)
        rrc = rcc_taps()
        filtered = np.convolve(bb.real, rrc, 'same')

        all_results = []
        for phase in range(SPS):
            all_results.extend(
                process_phase(filtered, phase, fo))

        # Deduplicate identical messages from multiple phases
        seen = set()
        for r in all_results:
            msg = r['message']
            if msg not in seen:
                seen.add(msg)
                self.packets_found += 1
                text = msg.decode('ascii', errors='replace')
                print(f"[EnhancedRX] #{self.packets_found} "
                      f"FO={r['fo']/1e3:.1f} kHz "
                      f"({r['polarity']}) "
                      f"| {text!r}", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Enhanced Packet RX')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--lna', type=float, default=8)
    parser.add_argument('--vga', type=float, default=12)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--duration', type=int, default=30)
    parser.add_argument('--file', type=str, default=None)
    args = parser.parse_args()

    if args.file:
        # Offline decode from IQ file
        raw = np.fromfile(args.file, dtype=np.int8)
        I = raw[0::2].astype(np.float64); Q = raw[1::2].astype(np.float64)
        I -= np.mean(I); Q -= np.mean(Q)
        samples = I + 1j * Q
        print(f"Loaded {len(samples)} samples ({len(samples)/FS:.2f}s)")

        fo = scan_frequency(samples)
        t = np.arange(len(samples), dtype=np.float64)
        bb = samples * np.exp(-2j * np.pi * fo * t / FS)
        rrc = rcc_taps()
        filtered = np.convolve(bb.real, rrc, 'same')

        seen = set()
        for phase in range(SPS):
            results = process_phase(filtered, phase, fo)
            for r in results:
                msg = r['message']
                if msg not in seen:
                    seen.add(msg)
                    text = msg.decode('ascii', errors='replace')
                    print(f"FO={r['fo']/1e3:.1f} kHz "
                          f"phase={r['phase']} ({r['polarity']}) "
                          f"| {text!r}")
    else:
        rx = LiveReceiver(freq=args.freq,
                          lna=args.lna, vga=args.vga,
                          amp=args.amp, serial=args.serial,
                          duration=args.duration)
        rx.run()
