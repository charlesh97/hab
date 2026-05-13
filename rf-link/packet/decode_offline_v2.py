#!/usr/bin/env python3
"""
Offline packet decoder v2 - improved symbol timing recovery.
"""
import numpy as np
import sys, os
from gnuradio.filter import firdes

SYNC_WORD = 0xE38FC0FC
SYNC_BITS = np.array([(SYNC_WORD >> (31 - i)) & 1 for i in range(32)], dtype=np.float64)

def decode_file(filename, sps=20):
    fs = 2000000
    raw = np.fromfile(filename, dtype=np.int8)
    I = raw[0::2].astype(np.float64)
    Q = raw[1::2].astype(np.float64)
    I -= np.mean(I)
    Q -= np.mean(Q)
    samples = I + 1j*Q
    print(f"Loaded {len(samples)} samples ({len(samples)/fs:.1f}s)")

    # Precise frequency scan
    nfft = min(262144, len(samples))
    center = nfft // 2
    best_fo = 0
    best_power = 0
    for fo_hz in range(-10000, 10001, 100):
        ci = center + int(fo_hz * nfft / fs)
        if 0 <= ci < nfft:
            power = np.mean(np.abs(np.fft.fft(samples[:nfft] * np.hanning(nfft))**2)[ci-20:ci+20])
            if power > best_power:
                best_power = power
                best_fo = fo_hz
    print(f"Best frequency: {best_fo/1e3:.2f} kHz (scan resolution: 100 Hz)")

    # Mix down
    t = np.arange(len(samples))
    bb = samples * np.exp(-2j * np.pi * best_fo * t / fs)
    
    # RRC matched filter
    rrc = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, 0.35, 11*sps))
    rrc = rrc / np.max(rrc)
    filtered = np.convolve(bb.real, rrc, 'same')
    
    # Try multiple decimation phases (for symbol timing recovery)
    print("\nTrying multiple decimation phases...")
    best_packets = []
    
    for phase in range(sps):
        symbols = filtered[phase::sps]
        if len(symbols) < 400: continue
        
        # Correlate with preamble (first 64 bits = alternating)
        preamble_template = np.tile([1, -1], 32)
        corr = np.correlate(symbols, preamble_template, 'same')
        corr_power = np.abs(corr)
        
        threshold = np.mean(corr_power) + 4 * np.std(corr_power)
        peaks = []
        
        for i in range(len(corr_power)):
            if corr_power[i] > threshold and corr_power[i] == np.max(corr_power[max(0,i-10):min(len(corr_power),i+11)]):
                peaks.append(i)
        
        for pkt_idx in peaks:
            if pkt_idx + 32 + 96 >= len(symbols):
                continue
            if pkt_idx - 200 < 0:
                continue
            
            # Extract payload (96 symbols after sync)
            # Sync word starts at pkt_idx + 256 (after preamble)
            # No - the preamble correlation gives us the START of the preamble
            # So payload starts at pkt_idx + 256 + 32 = pkt_idx + 288
            payload_start = pkt_idx + 256 + 32
            if payload_start + 96 > len(symbols):
                continue
                
            payload = symbols[payload_start:payload_start + 96]
            
            # Try both phase rotations (BPSK 0° and 180°)
            for invert, label in [(False, ''), (True, '_INV')]:
                bits = ((payload < 0) ^ invert).astype(np.uint8)
                
                # Pack
                bytes_out = []
                for i in range(0, 96, 8):
                    b = 0
                    for j in range(8):
                        b |= (int(bits[i+j]) << (7-j))
                    bytes_out.append(b)
                text = bytes(bytes_out).decode('ascii', errors='replace')
                
                if 'HELLO' in text or 'ELLO' in text or 'WORLD' in text or 'ORLD' in text:
                    best_packets.append((phase, label, text, pkt_idx, corr_power[pkt_idx]))
    
    if best_packets:
        print(f"\n{'='*60}")
        print(f"*** FOUND MATCHING PACKETS! ***")
        print(f"{'='*60}")
        for phase, label, text, idx, power in sorted(best_packets, key=lambda x: -x[4])[:10]:
            print(f"  Phase={phase}{label} | idx={idx} | power={power:.0f} | {text.strip()!r}")
    else:
        print("\nNo matching packets found.")
        # Show sample decoded text
        print("\nSample decoded from best phase:")
        # Find best phase based on correlation peak strength
        best_phase = 0
        best_peak = 0
        for phase in range(sps):
            symbols = filtered[phase::sps]
            if len(symbols) < 400: continue
            corr = np.correlate(symbols, np.tile([1,-1],32), 'same')
            cp = np.max(np.abs(corr))
            if cp > best_peak:
                best_peak = cp
                best_phase = phase
        
        symbols = filtered[best_phase::sps]
        # Show text at each potential packet
        corr = np.correlate(symbols, np.tile([1,-1],32), 'same')
        peaks = np.argsort(-np.abs(corr))[:5]
        for p in sorted(peaks):
            payload = symbols[p+288:p+288+96]
            bits = (payload < 0).astype(np.uint8)
            bytes_out = []
            for i in range(0, 96, 8):
                b = 0
                for j in range(8):
                    b |= (int(bits[i+j]) << (7-j))
                bytes_out.append(b)
            text = bytes(bytes_out).decode('ascii', errors='replace')
            print(f"  phase={best_phase} idx={p}: {text.strip()!r}")


if __name__ == '__main__':
    f = sys.argv[1] if len(sys.argv) > 1 else '/tmp/rx_offline.iq'
    decode_file(f)
