#!/usr/bin/env python3
"""
Packet HELLO Receiver - captures IQ samples and decodes BPSK packets.
Uses native SoapySDR for reliable streaming then pure Python demod.
"""
import numpy as np
import SoapySDR
import time, struct, sys
from gnuradio.filter import firdes

# Sync word (same as TX)
SYNC_WORD = 0xE38FC0FC
SYNC_BITS = np.array([(SYNC_WORD >> (31 - i)) & 1 for i in range(32)], dtype=np.float64)
SYNC_BPSK = 2.0 * SYNC_BITS - 1.0  # 0→+1, 1→-1

class PacketDecoder:
    """Demodulate and decode BPSK packets from raw IQ samples."""
    
    def __init__(self, samp_rate=2e6, sps=20, rrc_alpha=0.35):
        self.fs = int(samp_rate)
        self.sps = sps
        self.sym_rate = self.fs // sps
        
        # RRC matched filter (same as TX)
        self.rrc_taps = np.array(firdes.root_raised_cosine(sps, sps, 1.0, rrc_alpha, 11*sps))
        self.rrc_taps = self.rrc_taps / np.sum(self.rrc_taps)  # normalize
        
        # Pre-compute sync word template for correlation (after RRC)
        temp = np.zeros(self.sps * len(SYNC_BPSK), dtype=np.float64)
        temp[::sps] = SYNC_BPSK
        self.sync_template = np.convolve(temp, self.rrc_taps, 'same')
        
        self.packets_found = 0
        self.bytes_decoded = 0
    
    def process(self, samples_complex):
        """Process complex IQ samples, extract and decode packets."""
        # Remove DC offset
        samples = samples_complex - np.mean(samples_complex)
        
        # Mix down to remove frequency offset (find it via preamble)
        # First: coarse frequency estimation using FFT
        nfft = min(131072, len(samples))
        fft = np.fft.fftshift(np.fft.fft(samples[:nfft]))
        fp = np.abs(fft)**2
        # Avoid DC
        center = nfft // 2
        lo, hi = max(1, center - 500), min(nfft, center + 500)
        peak_idx = np.argmax(fp[lo:hi]) + lo
        if peak_idx == center:
            # Try wider search
            lo2, hi2 = max(1, center - 1000), min(nfft-1, center + 1000)
            peak_idx = np.argmax(fp[lo2:hi2]) + lo2
        freq_offset_hz = (peak_idx / nfft - 0.5) * self.fs
        if abs(freq_offset_hz) > 50000:  # Sanity check
            freq_offset_hz = 0
        
        # Mix down
        t = np.arange(len(samples), dtype=np.float64)
        bb = samples * np.exp(-2j * np.pi * freq_offset_hz * t / self.fs)
        
        # RRC matched filter (I only, since BPSK is real)
        filtered = np.convolve(bb.real, self.rrc_taps, 'same')
        
        # Decimate to symbol rate
        symbols = filtered[::self.sps]
        
        # Correlate with sync word template (using the RRC-shaped template)
        # At symbol rate
        corr = np.correlate(symbols, self.sync_template[::self.sps], 'same')
        corr_power = np.abs(corr)
        
        # Find peaks above threshold
        threshold = np.mean(corr_power) + 3 * np.std(corr_power)
        peaks = []
        for i in range(len(corr_power)):
            if corr_power[i] > threshold:
                # Check if it's a local max
                left = corr_power[max(0, i-5):i]
                right = corr_power[i+1:min(len(corr_power), i+6)]
                if (len(left) == 0 or corr_power[i] > np.max(left)) and \
                   (len(right) == 0 or corr_power[i] > np.max(right)):
                    peaks.append((i, corr_power[i]))
        
        # Process detected packets
        results = []
        for sym_idx, peak_val in sorted(peaks):
            # Alignment: sync word starts at sym_idx - len(SYNC_BITS)
            pkt_start = max(0, sym_idx - 3 * self.sps)  # rough alignment
            if pkt_start + 32 + 96 > len(symbols):  # need sync + 12 bytes
                continue
            
            # Extract symbols after sync word = payload
            # Payload starts after 256 preamble bits + 32 sync bits = 288 symbols
            payload_start = pkt_start + 256 + 32
            if payload_start + 96 > len(symbols):
                continue
                
            payload_syms = symbols[payload_start:payload_start + 96]
            
            # Hard decision BPSK: > 0 → 0, < 0 → 1 (matches TX mapping)
            bits = (payload_syms < 0).astype(np.uint8)
            
            # Pack to bytes
            bytes_out = []
            for i in range(0, 96, 8):
                byte_val = 0
                for j in range(8):
                    byte_val |= (int(bits[i+j]) << (7-j))
                bytes_out.append(byte_val)
            
            payload = bytes(bytes_out)
            self.packets_found += 1
            self.bytes_decoded += len(payload)
            
            # Verify it looks like text
            try:
                text = payload.decode('ascii', errors='replace')
                if text.startswith('HELLO') or text.startswith('ELLO') or 'HELLO' in text or 'WORLD' in text:
                    results.append((sym_idx, peak_val, 'GOOD', text))
                else:
                    results.append((sym_idx, peak_val, 'NOISE', text))
            except:
                results.append((sym_idx, peak_val, 'ERR', payload.hex()))
        
        return freq_offset_hz, results


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Packet HELLO RX')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--samp', type=float, default=2e6)
    parser.add_argument('--lna', type=float, default=16)
    parser.add_argument('--vga', type=float, default=20)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--duration', type=int, default=30,
                       help='Capture duration in seconds')
    args = parser.parse_args()
    
    fs = int(args.samp)
    
    # Open the RX HackRF via SoapySDR
    dev_str = f'driver=hackrf,serial={args.serial}' if args.serial else 'driver=hackrf'
    print(f"[PktHelloRX] Opening {dev_str}...")
    sdr = SoapySDR.Device(dev_str)
    sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, fs)
    sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, args.freq)
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'LNA', float(args.lna))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'VGA', float(args.vga))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'AMP', float(args.amp))
    print(f"[PktHelloRX] Listening: {args.freq/1e6:.3f} MHz, {fs/1e6:.1f} Msps")
    print(f"[PktHelloRX] LNA={args.lna}, VGA={args.vga}, AMP={'ON' if args.amp else 'OFF'}")
    
    # Setup RX stream
    rx_stream = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)
    
    decoder = PacketDecoder(fs)
    buf = np.zeros(65536, dtype=np.complex64)
    
    print(f"[PktHelloRX] Capturing for {args.duration}s. Press Ctrl-C to stop early.")
    start_time = time.time()
    all_samples = []
    
    try:
        while time.time() - start_time < args.duration:
            # Read samples
            sr = sdr.readStream(rx_stream, [buf], len(buf), timeoutUs=500000)
            if sr.ret > 0:
                chunk = buf[:sr.ret].copy()
                all_samples.append(chunk)
                
                # Process periodically
                if len(all_samples) >= 5:
                    big_chunk = np.concatenate(all_samples)
                    freq_off, packets = decoder.process(big_chunk)
                    
                    for sym_idx, peak, status, text in packets:
                        print(f"[PktHelloRX] PKT #{decoder.packets_found} | "
                              f"Status: {status} | "
                              f"Offset: {freq_off/1e3:.1f} kHz | "
                              f"Text: {text.strip()!r}")
                    
                    # Log summary
                    elapsed = time.time() - start_time
                    print(f"[PktHelloRX] Progress: {elapsed:.0f}s, "
                          f"{decoder.packets_found} packets, "
                          f"{decoder.bytes_decoded} bytes, "
                          f"freq_off={freq_off/1e3:.1f} kHz", flush=True)
                    
                    all_samples = []  # reset for next batch
                        
    except KeyboardInterrupt:
        pass
    
    sdr.deactivateStream(rx_stream)
    sdr.closeStream(rx_stream)
    
    duration = time.time() - start_time
    print(f"\n[PktHelloRX] Done. {duration:.0f}s, {decoder.packets_found} packets, "
          f"{decoder.bytes_decoded} bytes decoded.")


if __name__ == '__main__':
    main()
