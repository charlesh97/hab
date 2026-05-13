#!/usr/bin/env python3
"""
Precise BPSK packet decoder - handles frequency offset, symbol timing, and phase.
"""
import numpy as np
from gnuradio.filter import firdes
import sys, os

fs = 2e6
sps = 20
sym_rate = fs // sps  # 100 kHz

SYNC_WORD = 0xE38FC0FC
EXPECTED = b"HELLO WORLD\n\x05"

def load_iq(filename):
    raw = np.fromfile(filename, dtype=np.int8)
    I = raw[0::2].astype(np.float64)
    Q = raw[1::2].astype(np.float64)
    I -= np.mean(I)
    Q -= np.mean(Q)
    return I + 1j*Q

def estimate_freq_offset(samples):
    """Estimate frequency offset using FFT with zoom."""
    nfft = min(524288, len(samples))
    window = np.hanning(nfft)
    fft = np.fft.fftshift(np.fft.fft(samples[:nfft] * window))
    fp = np.abs(fft)**2
    center = nfft // 2
    
    # Search in expected range (5-6 kHz)
    fo_range_hz = np.arange(4500, 6000, 10)
    best_fo = 0
    best_p = 0
    for fo in fo_range_hz:
        ci = int(center + fo * nfft / fs)
        if 0 <= ci < nfft:
            p = np.mean(fp[ci-1:ci+2])
            if p > best_p:
                best_p = p
                best_fo = fo
    
    # Also check negative
    for fo in -fo_range_hz:
        ci = int(center + fo * nfft / fs)
        if 0 <= ci < nfft:
            p = np.mean(fp[ci-1:ci+2])
            if p > best_p:
                best_p = p
                best_fo = fo
    
    print(f"Coarse FO: {best_fo:.1f} Hz")
    return best_fo

def fine_freq_from_preamble(symbols, start_idx, fo_guess=0, search_range=200):
    """Refine frequency using preamble's known structure (alternating ±1)."""
    # The preamble is 256 symbols of alternating +1, -1
    # So after slicing, it should be perfectly alternating
    # We can sweep a residual frequency correction to maximize the correlation
    
    preamble_len = 256
    preamble_template = np.tile([1.0, -1.0], 128)
    
    best_residual = 0
    best_corr = 0
    
    for residual_hz in np.linspace(-search_range, search_range, 101):
        if residual_hz == 0:
            corr = np.abs(np.dot(symbols[start_idx:start_idx+256], preamble_template))
        else:
            t = np.arange(preamble_len)
            correction = np.exp(-1j * 2 * np.pi * residual_hz / sym_rate * t)
            corrected = symbols[start_idx:start_idx+256] * correction
            corr = np.abs(np.dot(corrected, preamble_template))
        if corr > best_corr:
            best_corr = corr
            best_residual = residual_hz
    
    return best_residual, best_corr


def decode(filename):
    print(f"Loading {filename}...")
    samples = load_iq(filename)
    print(f"Samples: {len(samples)}, Duration: {len(samples)/fs:.2f}s")
    
    # 1. Coarse frequency offset estimation
    fo = estimate_freq_offset(samples)
    if fo < 0:
        fo += fs  # wrap around negative
    
    # 2. Mix down
    t = np.arange(len(samples))
    bb = samples * np.exp(-2j * np.pi * fo * t / fs)
    
    # 3. RRC matched filter
    rrc_taps = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, 0.35, 11*sps))
    rrc_taps = rrc_taps / np.sum(rrc_taps)
    
    # Apply filter to real part (BPSK at baseband)
    filt = np.convolve(bb.real, rrc_taps, 'same')
    
    # 4. Try ALL decimation phases, with fine frequency correction
    print("\n=== Scanning all phases and residual frequencies ===")
    
    best_results = []
    
    for phase in range(sps):
        syms = filt[phase::sps]
        if len(syms) < 500: continue
        
        # Preamble template for correlation
        pre_template = np.tile([1.0, -1.0], 128)
        
        # Correlate
        corr = np.correlate(syms, pre_template, 'same')
        corr_abs = np.abs(corr)
        
        threshold = np.mean(corr_abs) + 4 * np.std(corr_abs)
        
        peaks = []
        for i in range(len(corr_abs)):
            if corr_abs[i] > threshold and i > 10 and i + 400 < len(syms):
                left = corr_abs[max(0,i-5):i]
                right = corr_abs[i+1:min(len(corr_abs),i+6)]
                if (len(left) == 0 or corr_abs[i] >= np.max(left)) and \
                   (len(right) == 0 or corr_abs[i] >= np.max(right)):
                    peaks.append(i)
        
        for peak_idx in peaks:
            # Refine frequency using preamble symbols
            resid_fo, corr_val = fine_freq_from_preamble(syms, peak_idx, search_range=300)
            
            # Apply residual frequency correction to region around this packet
            pkt_len = 256 + 32 + 96 + 50  # preamble + sync + payload + margin
            pkt_start = max(0, peak_idx - 20)
            pkt_end = min(len(syms), peak_idx + pkt_len + 20)
            
            k = np.arange(pkt_end - pkt_start)
            corrected = syms[pkt_start:pkt_end] * np.exp(-1j * 2 * np.pi * resid_fo / sym_rate * k)
            
            # Now align properly
            # preamble correlation with corrected symbols
            c2 = np.correlate(corrected, pre_template, 'same')
            aligned_idx = np.argmax(np.abs(c2)) + pkt_start
            
            # Extract payload (preamble=256, sync=32)
            payload_start = aligned_idx + 256 + 32
            payload = corrected[aligned_idx - pkt_start + 256 + 32 : aligned_idx - pkt_start + 256 + 32 + 96]
            
            if len(payload) < 96:
                continue
            
            # Phase correction using sync word
            sync_syms = corrected[aligned_idx - pkt_start + 256 : aligned_idx - pkt_start + 256 + 32]
            sync_template = np.array([1.0 if (SYNC_WORD >> (31-i)) & 1 else -1.0 for i in range(32)])
            
            # Estimate phase from sync word
            phase_est = np.angle(np.dot(sync_syms, sync_template))
            payload_corrected = payload * np.exp(-1j * phase_est)
            
            # Try both inversions (BPSK 180° ambiguity)
            for invert in [False, True]:
                bits = ((payload_corrected.real > 0) ^ invert).astype(np.uint8)
                
                bytes_out = []
                for i in range(0, 96, 8):
                    b = 0
                    for j in range(8):
                        b |= (int(bits[i+j]) << (7-j))
                    bytes_out.append(b)
                
                decoded = bytes(bytes_out)
                score = sum(1 for a, b in zip(decoded, EXPECTED) if a == b) if len(decoded) >= len(EXPECTED) else 0
                
                if score >= 7:
                    best_results.append({
                        'phase': phase, 'peak_idx': peak_idx, 'aligned_idx': aligned_idx,
                        'resid_fo': resid_fo, 'invert': invert, 'score': score,
                        'payload': decoded, 'corr_val': corr_val,
                        'phase_est': phase_est
                    })
    
    # Sort by score
    best_results.sort(key=lambda x: -x['score'])
    
    print(f"\n{'='*70}")
    print(f"DECODE RESULTS for {os.path.basename(filename)}")
    print(f"{'='*70}")
    
    if best_results:
        for r in best_results[:10]:
            text = r['payload'].decode('ascii', errors='replace').strip()
            print(f"  Score={r['score']:2d}/{len(EXPECTED)} | "
                  f"rFO={r['resid_fo']:+.0f} Hz | phase={r['phase']:2d} | "
                  f"inv={int(r['invert'])} | "
                  f"align={r['aligned_idx']} | "
                  f"text={text!r}")
    else:
        print("  No decent packets found.")
    
    # Also extract raw symbols at the best-known location for debugging
    # Let's try a more exhaustive search with finer symbol timing
    print("\n=== Exhaustive symbol timing scan ===")
    
    # Try fractional-sample timing using interpolation
    # Mix down more carefully
    bb2 = samples * np.exp(-2j * np.pi * fo * t / fs)
    # Remove strong DC/bias
    bb2 -= np.mean(bb2)
    
    filt2 = np.convolve(bb2.real, rrc_taps, 'same')
    
    # Try sub-sample timing offsets (fractional sps shifts)
    for phase_frac in np.linspace(0, sps, 25):  # 25 steps across one symbol
        phase_int = int(phase_frac)
        frac = phase_frac - phase_int
        
        if phase_int + 1 >= len(filt2):
            continue
        
        # Linear interpolation between adjacent samples
        syms_frac = (1-frac) * filt2[phase_int::sps] + frac * filt2[phase_int+1::sps]
        if len(syms_frac) < 400:
            continue
        
        # Correlate with preamble
        corr = np.correlate(syms_frac, pre_template, 'same')
        corr_abs = np.abs(corr)
        
        # Find peak
        peak_idx = np.argmax(corr_abs)
        if peak_idx < 200 or peak_idx + 400 > len(syms_frac):
            continue
        
        peak_val = corr_abs[peak_idx]
        if peak_val < np.mean(corr_abs) + 4 * np.std(corr_abs):
            continue
        
        # Refine frequency on the preamble
        pre = syms_frac[peak_idx:peak_idx+256]
        # Differential phase
        diff = pre[1:] * np.conj(pre[:-1])
        w = np.abs(pre[:-1]) * np.abs(pre[1:])
        mean_diff_angle = np.angle(np.sum(diff * w) / (np.sum(w) + 1e-12))
        # For alternating ±1, the expected phase difference is π
        # residual FO causes additional rotation
        resid_fo_res = (mean_diff_angle - np.pi) * sym_rate / (2 * np.pi)
        
        # Apply correction
        k = np.arange(len(syms_frac))
        syms_corrected = syms_frac * np.exp(-1j * 2 * np.pi * resid_fo_res / sym_rate * k)
        
        # Re-correlate
        corr2 = np.correlate(syms_corrected, pre_template, 'same')
        peak_idx2 = np.argmax(np.abs(corr2))
        
        # Sync word and payload
        sync_start = peak_idx2 + 256
        payload_start = sync_start + 32
        payload_syms = syms_corrected[payload_start:payload_start+96]
        
        if len(payload_syms) < 96:
            continue
        
        sync_syms = syms_corrected[sync_start:sync_start+32]
        sync_template = np.array([1.0 if (SYNC_WORD >> (31-i)) & 1 else -1.0 for i in range(32)])
        
        # Phase correction
        phase_est = np.angle(np.dot(sync_syms, sync_template.conj()))
        payload_corrected = payload_syms * np.exp(-1j * phase_est)
        
        for invert in [False, True]:
            bits = ((payload_corrected.real > 0) ^ invert).astype(np.uint8)
            bytes_out = []
            for i in range(0, 96, 8):
                b = 0
                for j in range(8):
                    b |= (int(bits[i+j]) << (7-j))
                bytes_out.append(b)
            decoded = bytes(bytes_out)
            score = sum(1 for a, b in zip(decoded, EXPECTED) if a == b) if len(decoded) >= len(EXPECTED) else 0
            
            if score >= 7:
                text = decoded.decode('ascii', errors='replace').strip()
                print(f"  [exhaustive] Score={score:2d}/{len(EXPECTED)} | "
                      f"frac-phase={phase_frac:5.1f} | rFO={resid_fo_res:+.1f} Hz | "
                      f"inv={int(invert)} | text={text!r}")
                if score >= 11:
                    print("  *** NEAR-PERFECT ***")
    
    return best_results

if __name__ == '__main__':
    f = sys.argv[1] if len(sys.argv) > 1 else '/tmp/rx_cable_good.iq'
    decode(f)
