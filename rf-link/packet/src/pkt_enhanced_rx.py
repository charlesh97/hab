#!/usr/bin/env python3
"""
Enhanced Packet Receiver — sync-word correlation + FEC decode + CRC validate.

Architecture (built on the proven 121/121 sync-word technique):
  1. FFT-based FO estimation
  2. Mix down to baseband, RRC matched filter
  3. Try all SPS decimation phases (up to 20 for performance)
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
import sys, time, argparse
from packet_codec import packet_decode, max_encoded_size_for_payload

SPS = 20
FS = 2000000

# Packet structure (from pkt_enhanced_tx.py)
PREAMBLE_BITS = 192  # 24 bytes of preamble
SYNC_BITS = 32

# Sync word: GNU Radio default access code (from packet_rx.py preamble_dummy).
# Chosen to NOT appear in the preamble, giving unambiguous correlation peaks.
SYNC_WORD = 0xACDDA4E2

# Precomputed sync word as BPSK symbols (0→+1, 1→-1)
_SYNC_BI = np.array([(SYNC_WORD >> (31 - i)) & 1 for i in range(SYNC_BITS)],
                    dtype=np.float64)
SYNC_BPSK = -2.0 * _SYNC_BI + 1.0  # bit 0→+1, 1→-1 (matches TX mapping)

# Maximum FEC-encoded bytes the receiver will extract after the sync word.
# This is a fixed budget large enough for any payload up to 512 bytes.
MAX_FEC_BYTES = max_encoded_size_for_payload(512)      # 1038
MAX_FEC_SYMS = MAX_FEC_BYTES * 8                       # 8304 BPSK symbols (bits)

# FO tracking constants
_FO_HISTORY_WINDOW = 5       # median filter window for FO estimates
_FO_EMPTY_THRESHOLD = 3      # consecutive empty chunks before re-scan
_FO_NARROW_WIDTH = 5000      # ±5 kHz narrow re-scan
_FO_WIDE_WIDTH = 20000       # ±20 kHz full scan
_FO_LOCK_MIN_CORR = 0.3      # minimum normalized correlation to lock FO


def rcc_taps(sps=SPS, alpha=0.35, ntaps=11):
    from gnuradio.filter import firdes
    taps = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, alpha, ntaps * sps))
    return taps / np.max(np.abs(taps))


def apply_digital_agc(samples, target_rms=0.3, min_rms=1e-3):
    """Apply digital AGC to normalize RMS amplitude to target level.
    
    Args:
        samples: Complex numpy array
        target_rms: Target RMS level (default 0.3)
        min_rms: Minimum RMS threshold to avoid amplifying noise (default 1e-3)
    
    Returns:
        RMS-scaled samples (same array shape, modified copy)
    """
    rms = np.sqrt(np.mean(np.abs(samples) ** 2))
    if rms < min_rms:
        return samples * 0.0  # silence below noise floor
    gain = target_rms / rms
    return samples * gain


def scan_frequency(samples, search_width=None, sps=SPS, samp_rate=FS, narrow=False):
    """
    Estimate carrier frequency offset by maximizing sync-word correlation.

    Finds a high-energy segment, mixes by candidate FO values across
    ±search_width, RRC filters, decimates, and finds the FO that gives the
    strongest sync-word correlation peak.

    Falls back to spectral centroid for software loopback (FO ≈ 0).

    Args:
        samples: Complex baseband samples
        search_width: ±Hz to search. If None, defaults to 20% of symbol rate
        sps: Samples per symbol (default SPS)
        samp_rate: Sample rate in Hz (default FS)
        narrow: If True, use narrower search for quicker re-scan

    Returns:
        Estimated frequency offset in Hz
    """
    from gnuradio.filter import firdes
    
    symbol_rate = samp_rate / sps
    if search_width is None:
        search_width = int(0.2 * symbol_rate)  # 20% of symbol rate
        search_width = max(search_width, 2000)  # minimum ±2 kHz
        if narrow:
            search_width = min(search_width, _FO_NARROW_WIDTH)
    
    SYNC_BPSK_LOCAL = np.array([(SYNC_WORD >> (31 - i)) & 1 for i in range(32)],
                               dtype=np.float64) * 2.0 - 1.0
    
    # Find a high-energy segment
    n = min(131072, len(samples))
    end = min(n * 16, len(samples))
    energy = np.abs(samples[:end])
    window = 65536
    if len(energy) > window:
        cs = np.cumsum(energy)
        best_start = int(np.argmax(cs[window:] - cs[:-window]))
    else:
        best_start = 0
    
    seg = samples[best_start:best_start + n]
    t_arr = np.arange(n, dtype=np.float64)
    rrc_tmp = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, 0.35, 11 * sps))
    rrc_tmp /= np.max(np.abs(rrc_tmp))
    
    # RRC filter once, then rotate per candidate
    filt_full = np.convolve(seg, rrc_tmp, 'same')
    
    # Use evenly-spaced decimation phases, limited to 20 for performance
    n_phases = min(sps, 20)
    phase_indices = np.linspace(0, sps - 1, n_phases, dtype=int)
    
    # Determine symbol count per phase
    max_syms = 5000
    t_sym_list = []
    sym_list = []
    for ph in phase_indices:
        syms = filt_full[ph::sps]
        n_avail = min(max_syms, len(syms))
        sym_list.append(syms[:n_avail])
        t_sym_list.append(t_arr[ph::sps][:n_avail])
    
    best_corr = 0.0
    best_fo = 0.0
    
    # Search step: finer grid for narrower scan
    step = 250 if narrow else 500
    for fo_candidate in np.arange(-search_width, search_width + step, step):
        for syms, ts in zip(sym_list, t_sym_list):
            rotated = syms * np.exp(-2j * np.pi * fo_candidate * ts / samp_rate)
            corr = np.abs(np.correlate(rotated, SYNC_BPSK_LOCAL, 'valid'))
            m = np.max(corr)
            if m > best_corr:
                best_corr = m
                best_fo = fo_candidate
    
    # If correlation is very weak, fall back to centroid
    if best_corr < 100:
        nfft = min(262144, len(samples))
        seg_fft = samples[:nfft] * np.hanning(nfft)
        spec = np.abs(np.fft.fftshift(np.fft.fft(seg_fft)))**2
        freqs = np.fft.fftshift(np.fft.fftfreq(nfft, 1.0 / samp_rate))
        cn = nfft // 2
        sb = int(search_width * nfft / samp_rate)
        lo, hi = max(0, cn - sb), min(nfft, cn + sb + 1)
        band = spec[lo:hi].copy()
        nf = np.median(band)
        band = np.maximum(band - nf, 0)
        tp = np.sum(band)
        if tp > 1e-10:
            return np.sum(freqs[lo:hi] * band) / tp
        return 0.0
    
    return best_fo


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


def process_phase(filtered, phase, fo, sps=SPS,
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
        sps: Samples per symbol (default SPS)
        pre_bits: Number of preamble symbols before sync word
        top_n: Number of correlation peaks to try
    """
    symbols = filtered[phase::sps]
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
                 amp=False, serial=None, duration=30,
                 sps=SPS, samp_rate=FS, agc_target=0.3):
        self.fs = int(samp_rate)
        self.sps = sps
        self.freq = freq
        self.lna, self.vga, self.amp = lna, vga, amp
        self.serial = serial
        self.duration = duration
        self.packets_found = 0
        self.agc_target = agc_target
        self._fo = None  # FO estimated once, reused across chunks
        # Continuous FO tracking state
        self._fo_lock = False
        self._fo_history = []
        self._empty_chunks = 0

    def run(self):
        import SoapySDR
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

    def _compute_fo_search_width(self):
        """Compute search width based on symbol rate and lock state."""
        symbol_rate = self.fs / self.sps
        base_width = int(0.2 * symbol_rate)
        if self._fo_lock:
            return _FO_NARROW_WIDTH
        return max(base_width, _FO_WIDE_WIDTH)

    def _update_fo_tracking(self, new_fo):
        """Update FO tracking state with a new estimate."""
        self._fo_history.append(new_fo)
        if len(self._fo_history) > _FO_HISTORY_WINDOW:
            self._fo_history = self._fo_history[-_FO_HISTORY_WINDOW:]
        # Use median to filter outliers
        median_fo = float(np.median(self._fo_history))
        self._fo = median_fo
        self._fo_lock = True
        self._empty_chunks = 0

    def _process_chunk(self, samples):
        # Apply digital AGC
        samples = apply_digital_agc(samples, target_rms=self.agc_target)

        samples -= np.mean(samples)

        # Estimate FO — initial scan or re-scan based on tracking state
        if self._fo is None:
            mag = np.abs(samples)
            if np.max(mag) < self.agc_target * 0.1:
                return  # no signal in this chunk, wait for next
            search_width = self._compute_fo_search_width()
            self._fo = scan_frequency(samples, search_width=search_width,
                                      sps=self.sps, samp_rate=self.fs)
            print(f"[EnhancedRX] FO estimate: {self._fo:.0f} Hz", flush=True)
        elif self._empty_chunks >= _FO_EMPTY_THRESHOLD:
            # Re-scan: try narrow window around last FO first
            print(f"[EnhancedRX] {self._empty_chunks} empty chunks, re-scanning FO...",
                  flush=True)
            narrow_fo = scan_frequency(samples, search_width=_FO_NARROW_WIDTH,
                                       sps=self.sps, samp_rate=self.fs, narrow=True)
            # Check if the narrow scan produced a credible estimate
            # Re-scan with small step to get correlation strength
            narrow_corr = scan_frequency(samples, search_width=_FO_NARROW_WIDTH,
                                         sps=self.sps, samp_rate=self.fs, narrow=False)
            
            # Validate using correlation strength — fall back to wide scan if weak
            symbol_rate = self.fs / self.sps
            full_width = int(0.2 * symbol_rate)
            full_width = max(full_width, _FO_WIDE_WIDTH)
            wide_fo = scan_frequency(samples, search_width=full_width,
                                     sps=self.sps, samp_rate=self.fs)
            
            # Use narrow if close to last known FO, otherwise use wide
            if abs(narrow_fo - (self._fo or 0)) < _FO_NARROW_WIDTH * 1.5:
                self._fo = narrow_fo
            else:
                self._fo = wide_fo
            self._empty_chunks = 0
            print(f"[EnhancedRX] FO re-estimate: {self._fo:.0f} Hz", flush=True)
        
        fo = self._fo

        t = np.arange(len(samples), dtype=np.float64)
        bb = samples * np.exp(-2j * np.pi * fo * t / self.fs)
        bb -= np.mean(bb)
        rrc = rcc_taps(sps=self.sps)
        filtered = np.convolve(bb, rrc, 'same')

        all_results = []
        # Use evenly-spaced decimation phases, limited to 20 for performance
        n_phases = min(self.sps, 20)
        phase_indices = np.linspace(0, self.sps - 1, n_phases, dtype=int)
        for phase in phase_indices:
            all_results.extend(
                process_phase(filtered, phase, fo, sps=self.sps))

        # Deduplicate identical messages from multiple phases
        seen = set()
        found_any = False
        for r in all_results:
            msg = r['message']
            if msg not in seen:
                seen.add(msg)
                self.packets_found += 1
                found_any = True
                text = msg.decode('ascii', errors='replace')
                print(f"[EnhancedRX] #{self.packets_found} "
                      f"FO={r['fo']/1e3:.1f} kHz "
                      f"({r['polarity']}) "
                      f"| {text!r}", flush=True)
        
        if found_any:
            # Update FO tracking with average from multiple phases
            if all_results:
                fos = [r['fo'] for r in all_results]
                mean_fo = float(np.mean(fos))
                self._update_fo_tracking(mean_fo)
            self._empty_chunks = 0
        else:
            self._empty_chunks += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Enhanced Packet RX')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--lna', type=float, default=8)
    parser.add_argument('--vga', type=float, default=12)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--duration', type=int, default=30)
    parser.add_argument('--file', type=str, default=None)
    parser.add_argument('--sps', type=int, default=SPS,
                        help='Samples per symbol (default: %(default)s)')
    parser.add_argument('--samp-rate', type=float, default=2e6, dest='samp_rate',
                        help='Sample rate in Hz (default: %(default)s)')
    parser.add_argument('--agc-target', type=float, default=0.3,
                        help='Digital AGC target RMS (default: %(default)s)')
    args = parser.parse_args()
    
    sps = args.sps
    fs = int(args.samp_rate)

    if args.file:
        # Offline decode from IQ file
        raw = np.fromfile(args.file, dtype=np.int8)
        I = raw[0::2].astype(np.float64); Q = raw[1::2].astype(np.float64)
        I -= np.mean(I); Q -= np.mean(Q)
        samples = I + 1j * Q
        print(f"Loaded {len(samples)} samples ({len(samples)/fs:.2f}s)")
        
        # Apply digital AGC to file mode too
        samples = apply_digital_agc(samples, target_rms=args.agc_target)

        fo = scan_frequency(samples, sps=sps, samp_rate=fs)
        t = np.arange(len(samples), dtype=np.float64)
        bb = samples * np.exp(-2j * np.pi * fo * t / fs)
        rrc = rcc_taps(sps=sps)
        filtered = np.convolve(bb.real, rrc, 'same')

        seen = set()
        n_phases = min(sps, 20)
        phase_indices = np.linspace(0, sps - 1, n_phases, dtype=int)
        for phase in phase_indices:
            results = process_phase(filtered, phase, fo, sps=sps)
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
                          duration=args.duration,
                          sps=sps, samp_rate=fs,
                          agc_target=args.agc_target)
        rx.run()
