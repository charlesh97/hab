#!/usr/bin/env python3
"""
Offline packet decoder - processes a captured IQ file and looks for HELLO packets.
This lets us debug the demod chain without real-time constraints.
"""
import numpy as np
import sys, os
from gnuradio.filter import firdes

SYNC_WORD = 0xE38FC0FC
SYNC_BITS = np.array([(SYNC_WORD >> (31 - i)) & 1 for i in range(32)], dtype=np.float64)
SYNC_BPSK = 2.0 * SYNC_BITS - 1.0

def process_file(filename, sps=20, rrc_alpha=0.35, debug=False):
    """Process an IQ file and look for HELLO WORLD packets."""
    fs = 2e6  # Hardcoded for our test setup
    
    # Read raw int8 IQ data
    raw = np.fromfile(filename, dtype=np.int8)
    if len(raw) == 0:
        print("Empty file!")
        return
    
    # Convert to complex
    I = raw[0::2].astype(np.float64)
    Q = raw[1::2].astype(np.float64)
    
    # Remove DC
    I -= np.mean(I)
    Q -= np.mean(Q)
    
    samples = I + 1j*Q
    print(f"Loaded {len(samples)} complex samples ({len(samples)/fs:.1f}s)")
    
    # === STEP 1: Frequency offset estimation ===
    # Use FFT to find the carrier
    nfft = min(262144, len(samples))
    windowed = samples[:nfft] * np.hanning(nfft)
    fft = np.fft.fftshift(np.fft.fft(windowed))
    fp = np.abs(fft)**2
    
    # Find peak away from DC
    center = nfft // 2
    guard = int(5 * nfft / fs)  # skip 5 Hz around DC
    search_region = np.concatenate([range(center-guard-1000, center-guard), 
                                    range(center+guard, center+guard+1000)])
    search_region = [i for i in search_region if 0 <= i < nfft]
    
    peak_idx = search_region[np.argmax(fp[search_region])]
    freq_offset = (peak_idx / nfft - 0.5) * fs
    print(f"Frequency offset: {freq_offset/1e3:.2f} kHz (at bin {peak_idx})")
    
    # === STEP 2: Mix down ===
    t = np.arange(len(samples), dtype=np.float64)
    bb = samples * np.exp(-2j * np.pi * freq_offset * t / fs)
    
    # Also show the spectrum of the baseband signal
    w2 = bb[:nfft] * np.hanning(nfft)
    fft2 = np.fft.fftshift(np.fft.fft(w2))
    fp2 = 10*np.log10(np.abs(fft2)**2 + 1e-12)
    noise_floor = np.percentile(fp2, 10)
    print(f"Baseband noise floor: {noise_floor:.1f} dB")
    
    # Check power in the BPSK band (±135 kHz around 0)
    half_bw = int(135e3 / fs * nfft)
    center = nfft // 2
    sig_power = np.mean(fp2[center-half_bw:center+half_bw])
    print(f"BPSK band power ({135e3/1e3:.0f} kHz): {sig_power:.1f} dB (SNR: {sig_power-noise_floor:.1f})")
    
    # === STEP 3: RRC matched filter ===
    rrc_taps = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, rrc_alpha, 11*sps))
    rrc_taps = rrc_taps / np.max(np.abs(rrc_taps))
    filtered = np.convolve(bb.real, rrc_taps, 'same')
    
    # === STEP 4: Decimate to symbol rate ===
    symbols = filtered[::sps]
    print(f"Symbols: {len(symbols)}")
    
    # === STEP 5: Sync word correlation (at symbol rate) ===
    # Correlate with the sync word BPSK pattern
    sync_corr = np.correlate(symbols, SYNC_BPSK, 'same')
    sync_power = np.abs(sync_corr)
    
    # Find threshold
    corr_mean = np.mean(sync_power)
    corr_std = np.std(sync_power)
    threshold = corr_mean + 5 * corr_std
    
    print(f"Correlation stats: mean={corr_mean:.3f}, std={corr_std:.3f}, threshold={threshold:.3f}")
    
    # Find peaks
    peaks = []
    for i in range(32, len(sync_power) - 96 - 256):
        if sync_power[i] > threshold:
            # Check local max
            left = sync_power[max(0,i-5):i]
            right = sync_power[i+1:min(len(sync_power),i+6)]
            if (len(left) == 0 or sync_power[i] > np.max(left)) and \
               (len(right) == 0 or sync_power[i] > np.max(right)):
                # Estimate packet start (preamble is 256 bits before sync)
                pkt_start = i - 256
                if pkt_start >= 0 and pkt_start + 256 + 32 + 96 <= len(symbols):
                    peaks.append((i, sync_power[i], pkt_start))
    
    print(f"Found {len(peaks)} correlation peaks")
    
    # === STEP 6: Decode packets ===
    decoded = []
    for sync_idx, peak_val, pkt_start in sorted(peaks, key=lambda x: -x[1])[:50]:
        # Extract payload symbols (96 bits = 12 bytes)
        payload_start = pkt_start + 256 + 32
        payload_syms = symbols[payload_start:payload_start + 96]
        
        # Hard decision
        bits = (payload_syms < 0).astype(np.uint8)
        
        # Pack to bytes
        bytes_out = []
        for i in range(0, 96, 8):
            byte_val = 0
            for j in range(8):
                byte_val |= (int(bits[i+j]) << (7-j))
            bytes_out.append(byte_val)
        
        payload = bytes(bytes_out)
        
        # Check if it looks like our message
        try:
            text = payload.decode('ascii', errors='replace')
            if 'HELLO' in text.upper() or 'WORLD' in text.upper() or 'ELLO' in text:
                decoded.append((peak_val, 'GOOD', text, pkt_start))
            else:
                # Also try inverting (if the BPSK phase is flipped)
                bits_inv = (~bits) & 1
                bytes_inv = []
                for i in range(0, 96, 8):
                    byte_val = 0
                    for j in range(8):
                        byte_val |= (int(bits_inv[i+j]) << (7-j))
                    bytes_inv.append(byte_val)
                payload_inv = bytes(bytes_inv)
                text_inv = payload_inv.decode('ascii', errors='replace')
                if 'HELLO' in text_inv.upper() or 'WORLD' in text_inv.upper():
                    decoded.append((peak_val, 'GOOD_INV', text_inv, pkt_start))
                else:
                    decoded.append((peak_val, 'NOISE', text, pkt_start))
        except:
            decoded.append((peak_val, 'ERR', payload.hex(), pkt_start))
            
    return decoded, freq_offset, symbols


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 decode_offline.py <iq_file>")
        print("Will also look for /tmp/rx_* files")
        sys.exit(1)
    
    filename = sys.argv[1]
    results, freq_off, symbols = process_file(filename)
    
    print(f"\n{'='*60}")
    print(f"DECODE RESULTS for {os.path.basename(filename)}")
    print(f"{'='*60}")
    
    if results:
        for peak_val, status, text, pkt_start in results[:20]:
            print(f"  | {status:8s} | peak={peak_val:.2f} | offset={pkt_start} sym | {text.strip()!r}")
    else:
        print("  No packets found.")
    
    # Also print first 256 preamble symbols to check 
    if len(symbols) > 500:
        # Plot preamble autocorrelation
        pre = symbols[:256]
        auto = np.correlate(pre, pre, 'full')
        mid = len(auto)//2
        print(f"\nPreamble autocorrelation at lag 0: {auto[mid]:.1f}")
        print(f"Preamble autocorrelation at lag 1: {auto[mid-1]:.1f}")
        print(f"Preamble autocorrelation at lag sps({20}): {auto[mid-20] if mid-20 >= 0 else 'n/a':.1f}")

        # Check symbol statistics to verify BPSK
        if len(symbols) > 200:
            sym_sample = symbols[:2000]
            snr_estimate = np.abs(np.mean(sym_sample))**2 / np.var(sym_sample)
            print(f"SNR estimate (samples): {10*np.log10(snr_estimate+1e-12):.1f} dB")
            h, _ = np.histogram(sym_sample, bins=15)
            print(f"Symbol histogram: {h}")
