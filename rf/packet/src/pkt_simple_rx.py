#!/usr/bin/env python3
"""
Packet Receiver - live BPSK decode from HackRF via native SoapySDR.
Uses sync-word-based correlation (proven approach from hello_decoder.py).
"""
import numpy as np
import SoapySDR
import sys, time, argparse
from gnuradio import gr, blocks, digital
from gnuradio.filter import firdes

def crc16(data: bytes) -> int:
    """CRC-16/XMODEM (0x1021). Returns 16-bit unsigned int."""
    crc = 0
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc

SPS = 20; FS = 2000000
PRE_SYNC = 256; SYNC_BITS = 32; LEN_BITS = 16; CRC_BITS = 16; MAX_PAYLOAD_BYTES = 128
MAX_POST_SYNC = LEN_BITS + (MAX_PAYLOAD_BYTES + 2) * 8  # len + payload + crc
COSTAS_LOOP_BW = 2 * np.pi / 200
COSTAS_MAX_OFFSET_HZ = 8_000
FLL_LOOP_BW = 2 * np.pi / 400
FLL_FILTER_SIZE = 45
FLL_MAX_OFFSET_HZ = 10_000
SYNC_WORD = 0xE38FC0FC
_SYNC_BI = np.array([(SYNC_WORD >> (31-i)) & 1 for i in range(SYNC_BITS)], dtype=np.float64)
SYNC_BPSK = 2.0 * _SYNC_BI - 1.0

def rcc_taps(sps=SPS, alpha=0.35, ntaps=11):
    taps = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, alpha, ntaps * sps))
    return taps / np.max(np.abs(taps))

def _run_fll(samples):
    """Run GNU Radio's band-edge FLL and return (corrected, input CFO Hz)."""
    samples = np.asarray(samples, dtype=np.complex64)
    if len(samples) == 0:
        return samples.copy(), 0.0

    rms = float(np.sqrt(np.mean(np.abs(samples) ** 2)))
    if not np.isfinite(rms) or rms < 1e-8:
        return samples.copy(), 0.0

    # Preserve the tail of finite packet vectors across the FLL's FIR delay.
    normalized = np.pad(
        np.asarray(samples / rms, dtype=np.complex64),
        (0, FLL_FILTER_SIZE),
    )
    tb = gr.top_block()
    source = blocks.vector_source_c(normalized.tolist(), False)
    fll = digital.fll_band_edge_cc(SPS, 0.35, FLL_FILTER_SIZE, FLL_LOOP_BW)
    fll_limit = 2 * np.pi * FLL_MAX_OFFSET_HZ / FS
    fll.set_min_freq(-fll_limit)
    fll.set_max_freq(fll_limit)
    sink = blocks.vector_sink_c()
    tb.connect(source, fll, sink)
    tb.run()

    corrected = np.asarray(sink.data(), dtype=np.complex64)
    # The FLL exposes its NCO correction, which has the opposite sign to
    # the carrier offset present at its input.
    input_fo_hz = -float(fll.get_frequency()) * FS / (2 * np.pi)
    return corrected, input_fo_hz


def _fine_fo_estimate(samples, fs=FS):
    """Estimate BPSK carrier offset with sub-Hz accuracy via squared-signal FFT.

    Squares the complex baseband to remove BPSK modulation (producing a
    clean tone at 2×Δf), then uses zero-padded FFT with parabolic
    interpolation for sub-bin resolution.  Falls back to 0.0 when no
    clear tone is found.

    This provides a *global*, one-shot estimate that avoids the tracking
    dynamics and convergence time of closed-loop estimators like the FLL.
    """
    samples = np.asarray(samples, dtype=np.complex64)
    if len(samples) < 1024:
        return 0.0

    # --- square to remove BPSK modulation: s² = A²·exp(j(4πΔf·n/fs + 2φ)) ---
    squared = samples ** 2

    # Decimate to keep FFT computationally reasonable
    max_fft = 256 * 1024
    if len(squared) > max_fft:
        step = max(1, len(squared) // max_fft)
        squared = squared[::step]
        fs_eff = fs / step
    else:
        fs_eff = fs

    n = len(squared)
    n_fft = n * 4                     # 4× zero-padding for fine bin spacing
    spectrum = np.fft.fft(squared, n=n_fft)
    spectrum = np.fft.fftshift(spectrum)
    freqs = np.fft.fftshift(np.fft.fftfreq(n_fft, d=1 / fs_eff))
    power = np.abs(spectrum)

    # Search ±20 kHz around DC (covers Δf ±10 kHz after the ÷2 below)
    dc_idx = n_fft // 2
    bin_width = fs_eff / n_fft
    search_bins = int(20_000 / bin_width)
    lo = max(1, dc_idx - search_bins)
    hi = min(n_fft - 1, dc_idx + search_bins + 1)

    # Find strongest bin and interpolate
    peak_offset = int(np.argmax(power[lo:hi]))
    peak_idx = lo + peak_offset
    y_peak = float(power[peak_idx])

    if 1 <= peak_idx < n_fft - 1:
        y_prev = float(power[peak_idx - 1])
        y_next = float(power[peak_idx + 1])
        denom = y_prev - 2 * y_peak + y_next
        delta = 0.5 * (y_prev - y_next) / denom if abs(denom) > 1e-15 else 0.0
    else:
        delta = 0.0

    # Validate: peak must stand clearly above the noise floor
    median_power = float(np.median(power[lo:hi]))
    if y_peak < 5.0 * median_power:
        return 0.0

    peak_freq = freqs[peak_idx] + delta * bin_width
    return peak_freq / 2.0            # tone at 2×Δf → divide by 2


def scan_frequency(samples, fo_min=-10000, fo_max=10000, step=100):
    """Estimate BPSK carrier offset with sub-Hz accuracy.

    Tries the squared-signal FFT estimator first; falls back to the
    GNU Radio band-edge FLL when the FFT method cannot identify a
    clear tone.
    """
    del step
    fo_hz = _fine_fo_estimate(samples)
    if not np.isfinite(fo_hz) or abs(fo_hz) < 0.5:
        _, fo_hz = _run_fll(samples)
    if not np.isfinite(fo_hz) or fo_hz < fo_min or fo_hz > fo_max:
        return 0.0
    return fo_hz

class PacketDecoder:
    def __init__(self):
        self.packets_found = 0

    def _costas_correct(self, complex_syms, initial_fo_hz=0.0, initial_phase=0.0):
        """Track residual carrier on an aligned packet-symbol window."""
        complex_syms = np.asarray(complex_syms, dtype=np.complex64)
        if len(complex_syms) == 0:
            return complex_syms.copy(), 0.0

        rms = float(np.sqrt(np.mean(np.abs(complex_syms) ** 2)))
        if not np.isfinite(rms) or rms < 1e-8:
            return complex_syms.copy(), 0.0

        normalized = np.asarray(complex_syms / rms, dtype=np.complex64)
        tb = gr.top_block()
        source = blocks.vector_source_c(normalized.tolist(), False)
        costas = digital.costas_loop_cc(COSTAS_LOOP_BW, 2, False)
        costas_limit = COSTAS_MAX_OFFSET_HZ * 2 * np.pi * SPS / FS
        costas.set_min_freq(-costas_limit)
        costas.set_max_freq(costas_limit)
        costas.set_frequency(initial_fo_hz * 2 * np.pi * SPS / FS)
        costas.set_phase(initial_phase)
        sink = blocks.vector_sink_c()
        tb.connect(source, costas, sink)
        tb.run()

        corrected = np.asarray(sink.data(), dtype=np.complex64)
        residual_fo_hz = float(costas.get_frequency()) * FS / (2 * np.pi * SPS)
        return corrected, residual_fo_hz

    @staticmethod
    def _decode_post_sync(post_syms):
        """Return (payload, length) when length and CRC validate."""
        bits_hard = (np.asarray(post_syms).real < 0).astype(np.uint8)

        for try_invert in (False, True):
            bits = bits_hard if not try_invert else 1 - bits_hard
            for shift in range(8):
                shifted = bits[shift:]
                if len(shifted) < LEN_BITS:
                    continue

                length = 0
                for bit in shifted[:LEN_BITS]:
                    length = (length << 1) | int(bit)
                if length < 1 or length > MAX_PAYLOAD_BYTES:
                    continue

                pkt_bits = LEN_BITS + (length * 8) + CRC_BITS
                if pkt_bits > len(shifted):
                    continue

                packet_bytes = []
                for offset in range(0, pkt_bits, 8):
                    value = 0
                    for bit in shifted[offset:offset + 8]:
                        value = (value << 1) | int(bit)
                    packet_bytes.append(value)

                payload = bytes(packet_bytes[2:2 + length])
                rx_crc = (packet_bytes[2 + length] << 8) | packet_bytes[3 + length]
                if crc16(payload) == rx_crc:
                    return payload, length

        return None

    @staticmethod
    def _burst_regions(samples, block_samples=2048):
        """Find gapped RF bursts, returning guarded sample ranges.

        When the capture is continuous or has no clear energy contrast, the
        whole vector is returned so carrier loops retain their streaming
        behavior. A one-block hole is merged to tolerate shaped packet edges.
        """
        samples = np.asarray(samples)
        if len(samples) < block_samples * 4:
            return [(0, len(samples))]

        block_count = int(np.ceil(len(samples) / block_samples))
        padded = np.pad(samples, (0, block_count * block_samples - len(samples)))
        block_rms = np.sqrt(np.mean(
            np.abs(padded.reshape(block_count, block_samples)) ** 2,
            axis=1,
        ))
        noise_rms = float(np.percentile(block_rms, 30))
        signal_rms = float(np.percentile(block_rms, 99))
        if not np.isfinite(noise_rms + signal_rms):
            return [(0, len(samples))]
        if signal_rms < max(noise_rms * 1.8, noise_rms + 1e-4):
            return [(0, len(samples))]

        threshold = noise_rms + 0.25 * (signal_rms - noise_rms)
        active_blocks = np.flatnonzero(block_rms > threshold)
        if len(active_blocks) == 0:
            return [(0, len(samples))]

        # Split only when at least two inactive blocks separate bursts.
        splits = np.flatnonzero(np.diff(active_blocks) > 2) + 1
        groups = np.split(active_blocks, splits)
        guard_blocks = 2
        regions = []
        for group in groups:
            if len(group) < 2:
                continue
            start_block = max(0, int(group[0]) - guard_blocks)
            end_block = min(block_count, int(group[-1]) + guard_blocks + 1)
            start = start_block * block_samples
            end = min(len(samples), end_block * block_samples)
            if regions and start <= regions[-1][1]:
                regions[-1] = (regions[-1][0], max(regions[-1][1], end))
            else:
                regions.append((start, end))

        return regions or [(0, len(samples))]

    def decode(self, samples_complex, raw_signal=None):
        samples = np.asarray(samples_complex, dtype=np.complex64)
        if len(samples) == 0:
            return []

        if raw_signal is not None:
            return self._decode_segment(samples, raw_signal=raw_signal)

        results = []
        sync_positions = []
        for start, end in self._burst_regions(samples):
            for result in self._decode_segment(samples[start:end]):
                absolute_sync = start + result[3] + result[4] * SPS
                if any(abs(absolute_sync - prior) <= SPS for prior in sync_positions):
                    continue
                sync_positions.append(absolute_sync)
                phase = absolute_sync % SPS
                sync_idx = absolute_sync // SPS
                results.append((
                    result[0],
                    result[1],
                    result[2],
                    phase,
                    sync_idx,
                    result[5],
                ))
        return sorted(results, key=lambda result: result[3] + result[4] * SPS)

    def _decode_segment(self, samples_complex, raw_signal=None):
        samples = np.asarray(samples_complex, dtype=np.complex64)
        if len(samples) == 0:
            return []
        samples = samples - np.mean(samples)

        if raw_signal is None:
            coarse_fo = _fine_fo_estimate(samples)
            if abs(coarse_fo) < 0.5:
                _, coarse_fo = _run_fll(samples)
        else:
            coarse_fo = _fine_fo_estimate(np.asarray(raw_signal, dtype=np.complex64))
            if abs(coarse_fo) < 0.5:
                _, coarse_fo = _run_fll(np.asarray(raw_signal, dtype=np.complex64))
        t = np.arange(len(samples))
        bb = samples * np.exp(-2j * np.pi * coarse_fo * t / FS)

        rrc = rcc_taps()
        filt = np.convolve(bb, rrc, 'same')

        phase_streams = []
        for phase in range(SPS):
            symbols = filt[phase::SPS]
            if len(symbols) < PRE_SYNC + SYNC_BITS + LEN_BITS + 8:
                continue

            phase_streams.append((phase, symbols))

        candidates = []
        # Track every established SPS phase. Eye-amplitude ranking is not
        # reliable for arbitrary payload statistics and pulse transitions.
        for phase, symbols in phase_streams:
            corrected, residual_fo = self._costas_correct(symbols)

            corr = np.correlate(corrected, SYNC_BPSK, 'valid')
            cp = np.abs(corr)
            th = np.mean(cp) + 3.5 * np.std(cp)

            for i in range(len(cp)):
                if cp[i] < th:
                    continue
                lo = max(0, i - 10); hi = min(len(cp), i + 11)
                if cp[i] < np.max(cp[lo:hi]):
                    continue
                if i < PRE_SYNC or i + SYNC_BITS + LEN_BITS + 8 > len(symbols):
                    continue
                candidates.append((
                    float(cp[i]),
                    phase,
                    i,
                    corrected,
                    phase + i * SPS,
                    residual_fo,
                ))

        results = []
        decoded_positions = []
        for _, phase, sync_idx, corrected, absolute_sync, residual_fo in sorted(
            candidates,
            key=lambda item: (item[4], -item[0]),
        ):
            if any(abs(absolute_sync - prior) <= SPS for prior in decoded_positions):
                continue
            post_start = sync_idx + SYNC_BITS
            if len(corrected) < post_start + LEN_BITS + 8:
                continue

            decoded = self._decode_post_sync(corrected[post_start:post_start + MAX_POST_SYNC + 7])
            if decoded is None:
                continue

            payload, length = decoded
            decoded_positions.append(absolute_sync)
            results.append((
                payload,
                length + 10,
                coarse_fo + residual_fo,
                phase,
                sync_idx,
                length,
            ))

        return results


class LiveReceiver:
    def __init__(self, freq=915e6, lna=8, vga=12, amp=False, serial=None, duration=30):
        self.fs = int(FS); self.decoder = PacketDecoder()
        self.freq = freq; self.lna = lna; self.vga = vga; self.amp = amp
        self.serial = serial; self.duration = duration

    def run(self):
        dev_str = f'driver=hackrf,serial={self.serial}' if self.serial else 'driver=hackrf'
        print(f"[PktRx] Opening...")
        sdr = SoapySDR.Device(dev_str)
        sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, self.fs)
        sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, self.freq)
        sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'LNA', float(self.lna))
        sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'VGA', float(self.vga))
        sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'AMP', float(self.amp))
        print(f"[PktRx] {self.freq/1e6:.3f} MHz, LNA={self.lna}, VGA={self.vga}")

        rx_stream = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
        sdr.activateStream(rx_stream)

        buf = np.zeros(524288, dtype=np.complex64)
        accum = []  # accumulate for better signal
        start = time.time()

        try:
            while self.duration == 0 or time.time() - start < self.duration:
                sr = sdr.readStream(rx_stream, [buf], len(buf), timeoutUs=500000)
                if sr.ret > 0:
                    accum.append(buf[:sr.ret].copy())

                    # Process every ~1M samples for good FO estimation
                    total = sum(len(a) for a in accum)
                    if total >= 1000000:
                        chunk = np.concatenate(accum)
                        texts = self.decoder.decode(chunk)
                        for text, score, fo, phase, sync_idx, length in texts:
                            self.decoder.packets_found += 1
                            if args.hex_output:
                                print(f"[PktRx] #{self.decoder.packets_found} FO={fo/1e3:.1f} kHz phase={phase} | {text.hex()}", flush=True)
                            else:
                                clean = text.decode('ascii', errors='replace').strip()
                                if 'HELLO' in clean.upper() or 'WORLD' in clean.upper():
                                    print(f"[PktRx] *** HELLO WORLD! *** FO={fo/1e3:.1f} kHz phase={phase} score={score} | {clean!r}", flush=True)
                                else:
                                    print(f"[PktRx] #{self.decoder.packets_found} FO={fo/1e3:.1f} kHz | {clean!r}", flush=True)
                        accum = []

                        elapsed = time.time() - start
                        if self.decoder.packets_found > 0:
                            print(f"[PktRx] Progress: {elapsed:.0f}s, {self.decoder.packets_found} good packets", flush=True)
        except KeyboardInterrupt:
            pass

        sdr.deactivateStream(rx_stream)
        sdr.closeStream(rx_stream)
        elapsed = time.time() - start
        if self.decoder.packets_found > 0:
            print(f"[PktRx] DONE. {elapsed:.0f}s, {self.decoder.packets_found} good packets.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Packet RX')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--lna', type=float, default=32)
    parser.add_argument('--vga', type=float, default=40)
    parser.add_argument('--amp', action='store_true', default=True)
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--duration', type=int, default=30)
    parser.add_argument('--file', type=str, default=None)
    parser.add_argument('--hex-output', action='store_true', default=False,
                        help='Output decoded payloads as hex (for binary data)')
    args = parser.parse_args()

    if args.file:
        raw = np.fromfile(args.file, dtype=np.int8)
        I = raw[0::2].astype(np.float64); Q = raw[1::2].astype(np.float64)
        I -= np.mean(I); Q -= np.mean(Q)
        decoder = PacketDecoder()
        texts = decoder.decode(I + 1j*Q)
        for text, score, fo, phase, sync_idx, length in texts:
            if args.hex_output:
                print(f"FO={fo/1e3:.1f} kHz len={length} | {text.hex()}")
            else:
                clean = text.decode('ascii', errors='replace').strip()
                print(f"FO={fo/1e3:.1f} kHz score={score} len={length} | {clean!r}")
    else:
        rx = LiveReceiver(freq=args.freq, lna=args.lna, vga=args.vga,
                          amp=args.amp, serial=args.serial, duration=args.duration)
        rx.run()
