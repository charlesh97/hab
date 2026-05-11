#!/usr/bin/env python3.14
"""
Sync-word-based packet decoder for captured IQ file.

Reads /tmp/rx_cable_good.iq (8M complex int8 samples, 4 seconds at 2 Msps).
Uses the actual 32-bit sync word (0xE38FC0FC) for precise packet boundary
detection instead of preamble correlation.

Packet structure:
  - 256 bits alternating preamble (clock recovery)
  - 32-bit sync word: 0xE38FC0FC
  - 96-bit payload: b"HELLO WORLD\n" = 12 bytes
"""
import numpy as np
import sys, os
from gnuradio.filter import firdes

# Packet parameters
SPS = 20
FS = 2_000_000
SYNC_WORD = 0xE38FC0FC
PRE_SYNC_BITS = 256  # preamble bits before sync word
SYNC_BITS = 32
PAYLOAD_BITS = 96
BITS_PER_PACKET = PRE_SYNC_BITS + SYNC_BITS + PAYLOAD_BITS  # 384

# Sync word as BPSK symbols (0→+1, 1→-1) at symbol rate
_SYNC_BI = np.array([(SYNC_WORD >> (31 - i)) & 1 for i in range(SYNC_BITS)], dtype=np.float64)
SYNC_BPSK = 2.0 * _SYNC_BI - 1.0  # +1 for bit 0, -1 for bit 1


def rcc_taps(sps=SPS, alpha=0.35, ntaps=11):
    """Root raised cosine matched filter taps."""
    taps = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, alpha, ntaps * sps))
    return taps / np.max(np.abs(taps))


def load_iq(filename):
    """Load complex int8 IQ file, remove DC."""
    raw = np.fromfile(filename, dtype=np.int8)
    I = raw[0::2].astype(np.float64)
    Q = raw[1::2].astype(np.float64)
    I -= np.mean(I)
    Q -= np.mean(Q)
    samples = I + 1j * Q
    print(f"Loaded {len(samples)} complex samples ({len(samples)/FS:.2f}s)")
    return samples


def scan_frequency(samples, fo_min=-10000, fo_max=10000, step=100, skip_dc=2000):
    """Scan FO range at coarse resolution, pick best candidate."""
    nfft = min(262144, len(samples))
    window = np.hanning(nfft)
    seg = samples[:nfft] * window
    spec = np.abs(np.fft.fftshift(np.fft.fft(seg)))**2
    center = nfft // 2
    
    best_fo = 0
    best_power = 0
    bw_bins = 20  # sum ±20 bins around the carrier
    
    for fo_hz in range(fo_min, fo_max + 1, step):
        ci = center + int(fo_hz * nfft / FS)
        lo = max(0, ci - bw_bins)
        hi = min(nfft, ci + bw_bins + 1)
        if lo < hi:
            power = np.mean(spec[lo:hi])
            if power > best_power:
                best_power = power
                best_fo = fo_hz
    
    # Refine: try ±1/2 step around best
    for fo_hz in np.arange(best_fo - step/2, best_fo + step/2 + 0.1, step/4):
        ci = center + int(round(fo_hz * nfft / FS))
        lo = max(0, ci - bw_bins)
        hi = min(nfft, ci + bw_bins + 1)
        if lo < hi:
            power = np.mean(spec[lo:hi])
            if power > best_power:
                best_power = power
                best_fo = fo_hz
    
    print(f"Best FO: {best_fo:.1f} Hz (power: {best_power:.1e})")
    # Sanity: also check that DC is lower
    dc_power = np.mean(spec[center-5:center+6])
    print(f"  DC power: {dc_power:.1e}, ratio: {best_power/dc_power:.1f}x")
    return best_fo


def correlate_sync_word(symbols):
    """Correlate with the exact sync word at symbol rate.
    
    Returns: correlation array (length len(symbols) - SYNC_BITS + 1)
    Peak at index k means sync word starts at symbol index k.
    """
    return np.correlate(symbols, SYNC_BPSK, 'valid')


def bits_to_bytes(bits_msb):
    """Convert 96 bits (MSB-first) to 12 bytes."""
    assert len(bits_msb) == PAYLOAD_BITS
    out = []
    for i in range(0, PAYLOAD_BITS, 8):
        b = 0
        for j in range(8):
            b |= int(bits_msb[i + j]) << (7 - j)
        out.append(b)
    return bytes(out)


def bits_to_bytes_lsb(bits):
    """Convert 96 bits (LSB-first packing) to 12 bytes."""
    out = []
    for i in range(0, PAYLOAD_BITS, 8):
        b = 0
        for j in range(8):
            b |= int(bits[i + j]) << j
        out.append(b)
    return bytes(out)


def try_bit_shifts(bits_in, text_only=True):
    """Try all 8 bit shifts and both MSB/LSB packing on 96 bits.
    Returns list of (text, score, packing, shift, invert)."""
    results = []
    for invert in [False, True]:
        bits = bits_in.copy()
        if invert:
            bits = 1 - bits
        for shift in range(8):
            # Rotate left by shift
            shifted = np.roll(bits, -shift)
            for packing, fn in [('MSB', bits_to_bytes), ('LSB', bits_to_bytes_lsb)]:
                try:
                    b = fn(shifted)
                    text = b.decode('ascii', errors='replace')
                    # Score: count printable ASCII chars
                    printable = sum(32 <= c < 127 for c in b)
                    # Bonus for HELLO, WORLD, ELLO, ORLD matches
                    upper = text.upper()
                    bonus = 0
                    if 'HELLO' in upper: bonus += 50
                    if 'WORLD' in upper: bonus += 50
                    if '\n' in text: bonus += 10
                    if '\x05' in text: bonus += 10
                    score = printable + bonus
                    results.append((text, score, packing, shift, invert))
                except:
                    pass
    return sorted(results, key=lambda x: -x[1])


def process_phase(filtered, phase, fo_value):
    """Process one decimation phase. Returns best decodes found."""
    symbols = filtered[phase::SPS]
    if len(symbols) < BITS_PER_PACKET + 10:
        return []
    
    # Correlate with sync word
    corr = correlate_sync_word(symbols)
    corr_power = np.abs(corr)
    
    # Adaptive threshold
    mean_c = np.mean(corr_power)
    std_c = np.std(corr_power)
    # Use a lower threshold since sync word is more specific
    threshold = mean_c + 3.5 * std_c
    
    # Find local peaks
    peaks = []
    radius = 10
    for i in range(len(corr_power)):
        if corr_power[i] < threshold:
            continue
        lo = max(0, i - radius)
        hi = min(len(corr_power), i + radius + 1)
        if corr_power[i] >= np.max(corr_power[lo:hi]):
            peaks.append((i, corr_power[i]))
    
    # Sort by peak strength
    peaks.sort(key=lambda x: -x[1])
    
    phase_results = []
    for sync_idx, peak_val in peaks:
        # The sync word starts at sync_idx (symbol index).
        # Preamble is BEFORE the sync word (256 symbols).
        # Payload starts right AFTER the sync word (sync_idx + 32).
        pkt_start = sync_idx - PRE_SYNC_BITS
        payload_start = sync_idx + SYNC_BITS
        
        if pkt_start < 0 or payload_start + PAYLOAD_BITS > len(symbols):
            continue
        
        payload = symbols[payload_start:payload_start + PAYLOAD_BITS]
        
        # Hard decision: BPSK mapping:
        # TX: bit 0 → +1, bit 1 → -1
        # RX: symbol > 0 → bit 0, symbol < 0 → bit 1
        bits_hard = (payload < 0).astype(np.uint8)
        
        decodes = try_bit_shifts(bits_hard)
        for text, score, packing, shift, invert in decodes[:3]:  # keep top 3 per sync hit
            phase_results.append({
                'phase': phase,
                'sync_idx': sync_idx,
                'pkt_start': pkt_start,
                'corr': peak_val,
                'fo': fo_value,
                'text': text,
                'score': score,
                'packing': packing,
                'shift': shift,
                'invert': invert,
                'text_stripped': text.strip(),
                'fo_hz': fo_value,
            })
    
    return phase_results


def decode_file(filename):
    """Main decode routine."""
    print(f"=" * 65)
    print(f"SYNC-WORD-BASED PACKET DECODER")
    print(f"File: {filename}")
    print(f"=" * 65)
    
    samples = load_iq(filename)
    
    # Step 1: Find carrier frequency offset
    fo = scan_frequency(samples)
    print(f"Using FO: {fo:.1f} Hz")
    
    # Step 2: Mix down to baseband
    t = np.arange(len(samples), dtype=np.float64)
    bb = samples * np.exp(-2j * np.pi * fo * t / FS)
    
    # Step 3: RRC matched filter
    print("Applying RRC matched filter (alpha=0.35, 11*sps taps)...")
    rrc_taps = rcc_taps()
    filtered = np.convolve(bb.real, rrc_taps, 'same')
    
    # Step 4: Try all decimation phases
    print(f"\nTrying all {SPS} decimation phases...")
    all_results = []
    
    for phase in range(SPS):
        pr = process_phase(filtered, phase, fo)
        if pr:
            all_results.extend(pr)
    
    if not all_results:
        print("\nNo sync word correlations found above threshold.")
        print("Attempting wider search with lower threshold and FO refinement...")
        
        # Try nearby FO values
        for delta_fo in [-100, -50, 50, 100]:
            fo2 = fo + delta_fo
            bb2 = samples * np.exp(-2j * np.pi * fo2 * t / FS)
            filtered2 = np.convolve(bb2.real, rrc_taps, 'same')
            for phase in range(SPS):
                pr = process_phase(filtered2, phase, fo2)
                if pr:
                    all_results.extend(pr)
        
        if not all_results:
            # Try without SPS constraint - dump raw decode at one phase
            print("\nStill nothing. Printing raw decode at each phase for debugging...")
            for phase in range(SPS):
                symbols = filtered[phase::SPS]
                if len(symbols) < 100: continue
                # Print first 100 symbols to see preamble
                pre = symbols[:100]
                print(f"  Phase {phase:2d}: first 100 symbols = {pre[:40]}")
    
    
    # Step 5: Rank and display results
    print(f"\n{'='*65}")
    print(f"RESULTS")
    print(f"{'='*65}")
    
    if all_results:
        # Deduplicate: group by decoded text (text_stripped)
        seen_texts = set()
        unique_results = []
        for r in sorted(all_results, key=lambda x: -x['corr']):
            stripped = r['text_stripped']
            if stripped not in seen_texts:
                seen_texts.add(stripped)
                unique_results.append(r)
        
        # Score-based ranking (penalize noise, reward HELLO WORLD)
        def score_result(r):
            base = r['score']
            text = r['text_stripped'].upper()
            if text == 'HELLO WORLD' + '\n\x05': return 999999
            if 'HELLO' in text and 'WORLD' in text: return 50000
            if 'HELLO' in text: return 10000
            if 'WORLD' in text: return 5000
            return base
        
        unique_results.sort(key=score_result, reverse=True)
        
        print(f"\nTop decodes (sorted by quality):")
        print(f"{'Rank':<5} {'Phase':<6} {'FO(Hz)':<9} {'Corr':<8} {'Pack':<6} {'Shft':<5} {'Inv':<5} {'Score':<6} {'Decoded Text'}")
        print(f"{'─'*65}")
        for rank, r in enumerate(unique_results[:20], 1):
            text_show = r['text_stripped']
            if len(text_show) > 40:
                text_show = text_show[:37] + '...'
            print(f"{rank:<5} {r['phase']:<6} {r['fo_hz']:<9.0f} {r['corr']:<8.0f} "
                  f"{r['packing']:<6} {r['shift']:<5} {'Y' if r['invert'] else 'N':<5} "
                  f"{r['score']:<6} {text_show!r}")
        
        # Show the very best match
        best = unique_results[0]
        print(f"\n{'='*65}")
        print(f"BEST DECODE")
        print(f"{'='*65}")
        if best['invert']:
            print(f"  Phase: {best['phase']} (inverted)")
        else:
            print(f"  Phase: {best['phase']} (normal)")
        print(f"  FO: {best['fo_hz']:.1f} Hz")
        print(f"  Sync correlation: {best['corr']:.0f} (max possible: {SYNC_BITS})")
        print(f"  Sync symbol index: {best['sync_idx']}")
        print(f"  Packet start symbol: {best['pkt_start']}")
        print(f"  Bit packing: {best['packing']}, shift: {best['shift']}")
        print(f"  Score: {best['score']}")
        print(f"  Raw text: {best['text']!r}")
        print(f"  Stripped: {best['text_stripped']!r}")
        
        # Show hex of best decode
        if 'HELLO' in best['text'].upper():
            syms, bits_hard, shifted, decoded_bytes = _unpack_decode(unique_results[0], filtered)
            print(f"  Payload hex: {decoded_bytes.hex()}")
            print(f"  Payload repr: {decoded_bytes!r}")
            # Also check the raw symbols around the sync word for Phase 13 specifically
            print(f"  Sample indices: sync={best['sync_idx']}, pkt_start={best['pkt_start']}")
            # Show preamble-sync boundary to confirm alignment
            boundary_start = best['sync_idx'] - 20
            boundary = syms[boundary_start:best['sync_idx'] + 10]
            print(f"  Symbols before/at sync: {np.round(boundary, 1).tolist()}")
    else:
        print("  No decodes found.")
    
    print()
    return all_results


def _unpack_decode(r, filtered):
    """Helper to reconstruct bit sequence from decode result."""
    symbols = filtered[r['phase']::SPS]
    payload_start = r['sync_idx'] + SYNC_BITS
    payload = symbols[payload_start:payload_start + PAYLOAD_BITS]
    bits_hard = (payload < 0).astype(np.uint8)
    if r['invert']:
        bits_hard = 1 - bits_hard
    shifted = np.roll(bits_hard, -r['shift'])
    if r['packing'] == 'MSB':
        b = bits_to_bytes(shifted)
    else:
        b = bits_to_bytes_lsb(shifted)
    return symbols, bits_hard, shifted, b


if __name__ == '__main__':
    f = sys.argv[1] if len(sys.argv) > 1 else '/tmp/rx_cable_good.iq'
    decode_file(f)
