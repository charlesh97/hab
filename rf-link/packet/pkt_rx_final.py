#!/usr/bin/env python3
"""
Packet Receiver - live BPSK decode from HackRF via native SoapySDR.
Uses sync-word-based correlation (proven approach from hello_decoder.py).
"""
import numpy as np
import SoapySDR
import sys, time, argparse
from gnuradio.filter import firdes

SPS = 20; FS = 2000000
PRE_SYNC = 256; SYNC_BITS = 32; PAYLOAD_BITS = 96
SYNC_WORD = 0xE38FC0FC
_SYNC_BI = np.array([(SYNC_WORD >> (31-i)) & 1 for i in range(SYNC_BITS)], dtype=np.float64)
SYNC_BPSK = 2.0 * _SYNC_BI - 1.0

def rcc_taps(sps=SPS, alpha=0.35, ntaps=11):
    taps = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, alpha, ntaps * sps))
    return taps / np.max(np.abs(taps))

def scan_frequency(samples, fo_min=-10000, fo_max=10000, step=100):
    nfft = min(262144, len(samples))
    window = np.hanning(nfft)
    seg = samples[:nfft] * window
    spec = np.abs(np.fft.fftshift(np.fft.fft(seg)))**2
    center = nfft // 2
    best_fo = 0; best_power = 0
    for fo_hz in range(fo_min, fo_max + 1, step):
        ci = center + int(fo_hz * nfft / FS)
        lo = max(0, ci - 20); hi = min(nfft, ci + 21)
        power = np.mean(spec[lo:hi])
        if power > best_power: best_power = power; best_fo = fo_hz
    # Refine
    for fo_hz in np.arange(best_fo - step/2, best_fo + step/2 + 0.1, step/4):
        ci = center + int(round(fo_hz * nfft / FS))
        lo = max(0, ci - 20); hi = min(nfft, ci + 21)
        power = np.mean(spec[lo:hi])
        if power > best_power: best_power = power; best_fo = fo_hz
    return best_fo

class PacketDecoder:
    def __init__(self):
        self.packets_found = 0
    
    def decode(self, samples_complex, raw_signal=None):
        samples = samples_complex - np.mean(samples_complex)
        fo = scan_frequency(samples if raw_signal is None else raw_signal)
        
        t = np.arange(len(samples))
        bb = samples * np.exp(-2j * np.pi * fo * t / FS)
        rrc = rcc_taps()
        filt = np.convolve(bb.real, rrc, 'same')
        
        results = []
        for phase in range(SPS):
            symbols = filt[phase::SPS]
            if len(symbols) < PRE_SYNC + SYNC_BITS + PAYLOAD_BITS: continue
            
            corr = np.correlate(symbols, SYNC_BPSK, 'valid')
            cp = np.abs(corr)
            th = np.mean(cp) + 3.5 * np.std(cp)
            
            peaks = []
            for i in range(len(cp)):
                if cp[i] < th: continue
                lo = max(0, i-10); hi = min(len(cp), i+11)
                if cp[i] >= np.max(cp[lo:hi]):
                    sync_idx = i
                    payload_start = sync_idx + SYNC_BITS
                    if payload_start + PAYLOAD_BITS > len(symbols): continue
                    
                    payload = symbols[payload_start:payload_start+PAYLOAD_BITS]
                    bits_hard = (payload < 0).astype(np.uint8)
                    
                    # Try all combos
                    for invert in [False, True]:
                        bits = bits_hard if not invert else 1 - bits_hard
                        for shift in range(8):
                            shifted = np.roll(bits, -shift)
                            for msb in [True, False]:
                                by = []
                                for i2 in range(0, PAYLOAD_BITS, 8):
                                    b = 0
                                    for j2 in range(8):
                                        if msb: b |= int(shifted[i2+j2]) << (7-j2)
                                        else: b |= int(shifted[i2+j2]) << j2
                                    by.append(b)
                                text = bytes(by)
                                printable = sum(32 <= c < 127 for c in by)
                                upper = text.decode('ascii', errors='replace').upper()
                                bonus = 0
                                if 'HELLO' in upper: bonus += 50
                                if 'WORLD' in upper: bonus += 50
                                if '\n' in text.decode('ascii', errors='replace'): bonus += 10
                                score = printable + bonus
                                
                                if 'HELLO' in upper or 'WORLD' in upper:
                                    results.append((text, score, fo, phase, sync_idx))
        
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
            while time.time() - start < self.duration:
                sr = sdr.readStream(rx_stream, [buf], len(buf), timeoutUs=500000)
                if sr.ret > 0:
                    accum.append(buf[:sr.ret].copy())
                    
                    # Process every ~1M samples for good FO estimation
                    total = sum(len(a) for a in accum)
                    if total >= 1000000:
                        chunk = np.concatenate(accum)
                        texts = self.decoder.decode(chunk)
                        for text, score, fo, phase, sync_idx in texts:
                            self.decoder.packets_found += 1
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
    parser.add_argument('--lna', type=float, default=8)
    parser.add_argument('--vga', type=float, default=12)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--duration', type=int, default=30)
    parser.add_argument('--file', type=str, default=None)
    args = parser.parse_args()
    
    if args.file:
        raw = np.fromfile(args.file, dtype=np.int8)
        I = raw[0::2].astype(np.float64); Q = raw[1::2].astype(np.float64)
        I -= np.mean(I); Q -= np.mean(Q)
        decoder = PacketDecoder()
        texts = decoder.decode(I + 1j*Q)
        for text, score, fo, phase, sync_idx in texts:
            clean = text.decode('ascii', errors='replace').strip()
            print(f"FO={fo/1e3:.1f} kHz score={score} | {clean!r}")
    else:
        rx = LiveReceiver(freq=args.freq, lna=args.lna, vga=args.vga,
                          amp=args.amp, serial=args.serial, duration=args.duration)
        rx.run()
