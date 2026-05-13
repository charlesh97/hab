#!/usr/bin/env python3
"""
Proper BPSK decoder - handles residual FO by working with complex baseband.
"""
import numpy as np
from gnuradio.filter import firdes
import sys, os

fs = 2e6; sps = 20; sym_rate = fs / sps  # 100 kHz
EXPECTED = b"HELLO WORLD\n\x05"
SYNC_WORD = 0xE38FC0FC

# Pre-compute sync word BPSK symbols
SYNC_SYMS = np.array([
    1.0 if (SYNC_WORD >> (31-i)) & 1 else -1.0 for i in range(32)
])

def load_iq(filename):
    raw = np.fromfile(filename, dtype=np.int8)
    I = raw[0::2].astype(np.float64) - np.mean(raw[0::2])
    Q = raw[1::2].astype(np.float64) - np.mean(raw[1::2])
    return I + 1j*Q

def decode(filename):
    print(f"Loading {filename}...")
    s = load_iq(filename)
    N = len(s)
    print(f"Samples: {N}, Duration: {N/fs:.2f}s")
    
    # 1. Coarse frequency estimation using FFT
    nfft = min(524288, N)
    window = np.hanning(nfft)
    fft = np.fft.fftshift(np.fft.fft(s[:nfft] * window))
    fp = np.abs(fft)**2
    center = nfft // 2
    
    # Scan FO range 4.5-6 kHz in 10 Hz steps
    fo_range = np.arange(4500, 6000, 10)
    best_fo = 0
    best_p = 0
    for fo in fo_range:
        ci = int(center + fo * nfft / fs)
        if 0 <= ci < nfft:
            p = np.mean(fp[ci-1:ci+2])
            if p > best_p:
                best_p = p
                best_fo = fo
    print(f"Coarse FO: {best_fo:.0f} Hz")
    
    # 2. Mix down using coarse FO
    t = np.arange(N)
    bb = s * np.exp(-2j * np.pi * best_fo * t / fs)
    
    # 3. Apply RRC matched filter to COMPLEX baseband
    rrc = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, 0.35, 11*sps))
    rrc = rrc / np.sum(rrc)
    bb_filt = np.convolve(bb, rrc, 'same')  # Complex filtering
    
    # 4. Try each decimation phase
    pre_template = np.tile([1.0, -1.0], 128)  # 256-symbol alternating preamble
    
    all_results = []
    
    for phase in range(sps):
        syms = bb_filt[phase::sps]
        if len(syms) < 500: continue
        
        # Correlate with preamble template
        corr = np.correlate(syms.real, pre_template, 'same')
        corr_abs = np.abs(corr)
        
        threshold = np.mean(corr_abs) + 4 * np.std(corr_abs)
        
        for i in range(len(corr_abs)):
            if corr_abs[i] > threshold:
                # Check local max
                left = corr_abs[max(0,i-3):i]
                right = corr_abs[i+1:min(len(corr_abs),i+4)]
                if (len(left) == 0 or corr_abs[i] >= np.max(left)) and \
                   (len(right) == 0 or corr_abs[i] >= np.max(right)):
                    
                    # Estimate residual FO from preamble phase rotation
                    preamble = syms[i:i+256]
                    if len(preamble) < 256: continue
                    
                    # For alternating preamble, each symbol should be opposite sign
                    # The differential phase between consecutive symbols is approximately pi
                    # residual FO causes additional rotation
                    diff = preamble[1:] * np.conj(preamble[:-1])
                    
                    # Weight by signal energy
                    w = np.abs(preamble[:-1]) * np.abs(preamble[1:])
                    w = w / (np.sum(w) + 1e-12)
                    
                    mean_angle = np.angle(np.sum(diff * w))
                    # Expected: π (alternating), residual FO adds to this
                    resid_fo = (mean_angle - np.pi) * sym_rate / (2 * np.pi)
                    
                    # Apply residual FO correction to entire packet region
                    packet_len = 256 + 32 + 96 + 20
                    k = np.arange(packet_len)
                    pkt_end = min(i + packet_len, len(syms))
                    actual_len = pkt_end - i
                    k = np.arange(actual_len)
                    
                    corrected = syms[i:i+actual_len] * np.exp(-1j * 2 * np.pi * resid_fo * k / sym_rate)
                    
                    # Now do phase correction using sync word
                    sync_syms = corrected[256:256+32]
                    if len(sync_syms) < 32: continue
                    
                    phase_est = np.angle(np.dot(sync_syms, SYNC_SYMS.conj()))
                    
                    # Apply phase correction and extract payload
                    payload_raw = corrected[256+32:256+32+96] * np.exp(-1j * phase_est)
                    if len(payload_raw) < 96: continue
                    
                    # Try both inversions
                    for invert in [False, True]:
                        bits = ((payload_raw.real > 0) ^ invert).astype(np.uint8)
                        
                        bytes_out = []
                        for bi in range(0, 96, 8):
                            b = 0
                            for bj in range(8):
                                b |= (int(bits[bi+bj]) << (7-bj))
                            bytes_out.append(b)
                        
                        decoded = bytes(bytes_out)
                        score = sum(1 for a, b in zip(decoded, EXPECTED) if a == b) if len(decoded) >= len(EXPECTED) else 0
                        
                        if score >= 7:
                            # Also verify sync word match
                            sync_corr = np.abs(np.dot(sync_syms * np.exp(-1j*phase_est), SYNC_SYMS.conj()))
                            all_results.append({
                                'phase': phase,
                                'sym_idx': i,
                                'resid_fo': resid_fo,
                                'invert': invert,
                                'score': score,
                                'payload': decoded,
                                'sync_corr': sync_corr,
                                'corr_val': corr_abs[i],
                                'phase_est': phase_est
                            })
    
    # Sort by score descending
    all_results.sort(key=lambda x: -x['score'])
    
    print(f"\n{'='*70}")
    print(f"DECODE RESULTS for {os.path.basename(filename)}")
    print(f"{'='*70}")
    
    if all_results:
        printed = set()
        for r in all_results:
            text = r['payload'].decode('ascii', errors='replace')
            # Deduplicate by payload text
            key = (r['phase'], r['sym_idx'], text.strip())
            if key in printed: continue
            printed.add(key)
            
            print(f"  Score={r['score']:2d}/{len(EXPECTED)} | "
                  f"phase={r['phase']:2d} | idx={r['sym_idx']:6d} | "
                  f"rFO={r['resid_fo']:+.1f} Hz | "
                  f"inv={int(r['invert'])} | "
                  f"sync_corr={r['sync_corr']:.0f} | "
                  f"text={text.strip()!r}")
            
            if r['score'] == len(EXPECTED):
                print(f"  *** PERFECT DECODE! ***")
            
            if len(printed) >= 20:
                break
    else:
        print("  No valid packets found.")
        print("\nTrying alternative approach: direct preamble-based decode...")
        
        # Fallback: For each phase, find the best preamble start and decode
        # without relying on residual FO correction from differential phase
        for phase in range(sps):
            syms = bb_filt[phase::sps]
            if len(syms) < 500: continue
            
            corr = np.correlate(syms.real, pre_template, 'same')
            top_idx = np.argmax(np.abs(corr))
            if top_idx < 256 or top_idx + 400 > len(syms):
                continue
            
            print(f"\n  Phase {phase}: best preamble at sym idx {top_idx}")
            
            preamble = syms[top_idx:top_idx+256]
            
            for resid_fo_try in np.linspace(-30, 30, 13):
                k = np.arange(256+32+96+20)
                corrected = syms[top_idx:top_idx+256+32+96+20] * \
                    np.exp(-1j * 2 * np.pi * resid_fo_try * k / sym_rate)
                
                sync_syms = corrected[256:256+32]
                payload_syms = corrected[256+32:256+32+96]
                
                if len(sync_syms) < 32 or len(payload_syms) < 96:
                    continue
                
                for phase_shift in np.linspace(-np.pi, np.pi, 9):
                    payload_corr = payload_syms * np.exp(-1j * phase_shift)
                    
                    for invert in [False, True]:
                        bits = ((payload_corr.real > 0) ^ invert).astype(np.uint8)
                        bytes_out = []
                        for bi in range(0, 96, 8):
                            b = 0
                            for bj in range(8):
                                b |= (int(bits[bi+bj]) << (7-bj))
                            bytes_out.append(b)
                        decoded = bytes(bytes_out)
                        score = sum(1 for a, b in zip(decoded, EXPECTED) if a == b)
                        
                        if score >= 7:
                            text = decoded.decode('ascii', errors='replace').strip()
                            print(f"    rFO={resid_fo_try:+.0f} pShift={phase_shift:+.2f} inv={int(invert)} score={score:2d}: {text!r}")

    return all_results

if __name__ == '__main__':
    f = sys.argv[1] if len(sys.argv) > 1 else '/tmp/rx_cable_good.iq'
    decode(f)
