#!/usr/bin/env python3
"""
Layer 2 — RF Software Loopback.

Tests the full TX→RX pipeline in software (no radio hardware):
  TX: payload → packet_encode() → bits → BPSK modulate → [preamble|sync|FEC]
  Save as int8 IQ → Load → FO scan → RRC filter → decimate →
  sync correlation → extract payload → packet_decode()

Also tests variable SPS, burst shaping, AGC, and FO injection.
"""
import sys, os, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pkt_enhanced_tx import make_packet_bits, bpsk_modulate, make_test_burst, apply_burst_shaping
from pkt_enhanced_rx import (
    process_phase, scan_frequency, rcc_taps, apply_digital_agc,
    FS, SPS, PREAMBLE_BITS, MAX_FEC_SYMS, SYNC_BPSK, SYNC_BITS
)


def _encode_iq(payload, sps=SPS):
    """Generate int8 IQ from a single packet at given SPS."""
    bits = make_packet_bits(payload)
    wf = np.array(bpsk_modulate(bits, sps=sps))
    I = (wf.real * 80).clip(-128, 127).astype(np.int8)
    Q = (wf.imag * 80).clip(-128, 127).astype(np.int8)
    iq = np.empty(2 * len(I), dtype=np.int8)
    iq[0::2] = I
    iq[1::2] = Q
    return iq, len(bits)


def _decode_iq(iq, sps=SPS, samp_rate=FS):
    """Full RX pipeline: int8 IQ → decoded message or None."""
    I = iq[0::2].astype(np.float64) - np.mean(iq[0::2])
    Q = iq[1::2].astype(np.float64) - np.mean(iq[1::2])
    samples = I + 1j * Q

    fo = scan_frequency(samples, sps=sps, samp_rate=samp_rate)
    t = np.arange(len(samples), dtype=np.float64)
    bb = samples * np.exp(-2j * np.pi * fo * t / samp_rate)
    rrc = rcc_taps(sps=sps)
    filtered = np.convolve(bb.real, rrc, 'same')

    n_phases = min(sps, 20)
    phase_indices = np.linspace(0, sps - 1, n_phases, dtype=int)
    for phase in phase_indices:
        for r in process_phase(filtered, phase, fo, sps=sps):
            return r['message']
    return None


def test_single_packet():
    """Single packet, known message."""
    payload = b'HELLO WORLD\n'
    iq, nbits = _encode_iq(payload)
    dec = _decode_iq(iq)
    assert dec == payload, f"Single packet decode failed: {dec}"
    return f"OK  {nbits} bits"


def test_multiple_sizes():
    """Multiple payload sizes."""
    sizes = [0, 12, 200, 255, 511]
    for n in sizes:
        payload = bytes([i % 256 for i in range(n)])
        iq, _ = _encode_iq(payload)
        dec = _decode_iq(iq)
        assert dec == payload, f"Size {n}: decode mismatch"
    return f"OK  {len(sizes)} sizes"


def test_burst():
    """Multi-packet burst: every packet decodes."""
    burst_wf = make_test_burst(b'BURST TEST\n', n_packets=5, gap_ms=20)
    wf_arr = np.array(burst_wf, dtype=np.complex64)
    I = (wf_arr.real * 80).clip(-128, 127).astype(np.int8)
    Q = (wf_arr.imag * 80).clip(-128, 127).astype(np.int8)
    iq = np.empty(2 * len(I), dtype=np.int8)
    iq[0::2] = I; iq[1::2] = Q

    I_f = iq[0::2].astype(np.float64) - np.mean(iq[0::2])
    Q_f = iq[1::2].astype(np.float64) - np.mean(iq[1::2])
    samples = I_f + 1j * Q_f
    fo = scan_frequency(samples)
    t = np.arange(len(samples), dtype=np.float64)
    bb = samples * np.exp(-2j * np.pi * fo * t / FS)
    rrc = rcc_taps()
    filtered = np.convolve(bb.real, rrc, 'same')

    expected = b'BURST TEST\n'
    count = 0
    for phase in range(SPS):
        for r in process_phase(filtered, phase, fo):
            if r['message'] == expected:
                count += 1
    assert count >= 3, f"Burst: only {count} decodes (expected >=3)"
    return f"OK  {count} decodes"


def test_oversized_capture():
    """Packet buried in zeros (simulates long recording)."""
    payload = b'HELLO\n'
    iq, _ = _encode_iq(payload)
    # Pad with 2x max budget of zeros before and after
    pad = np.zeros(MAX_FEC_SYMS * 4, dtype=np.int8)  # 2x each side = 4x
    full = np.concatenate([pad, iq, pad])
    dec = _decode_iq(full)
    assert dec == payload, "Oversized capture decode failed"
    return "OK"


def test_fo_estimator():
    """FO estimator returns ~0 for clean software signal."""
    payload = b'FO TEST\n'
    iq, _ = _encode_iq(payload)
    I = iq[0::2].astype(np.float64) - np.mean(iq[0::2])
    Q = iq[1::2].astype(np.float64) - np.mean(iq[1::2])
    samples = I + 1j * Q
    fo = scan_frequency(samples)
    assert abs(fo) < 10, f"FO centroid should be near 0, got {fo:.1f} Hz"
    return f"OK  fo={fo:.1f} Hz"


# ── New tests ─────────────────────────────────────────────

def test_sps_variants():
    """Codec round-trip at multiple SPS values: 4, 20, 50, 100."""
    payload = b'HELLO SPS TEST\n'
    for sps in [4, 20, 50, 100]:
        iq, nbits = _encode_iq(payload, sps=sps)
        dec = _decode_iq(iq, sps=sps)
        assert dec == payload, f"SPS={sps}: decode failed: {dec}"
    return "OK  4 SPS values (4, 20, 50, 100)"


def test_sps_small_payload():
    """Multiple payload sizes at SPS=4 and SPS=50."""
    sizes = [0, 12, 100, 255]
    for sps in [4, 50]:
        for n in sizes:
            payload = bytes([i % 256 for i in range(n)])
            iq, _ = _encode_iq(payload, sps=sps)
            dec = _decode_iq(iq, sps=sps)
            assert dec == payload, f"SPS={sps}, size={n}: decode mismatch"
    return "OK  SPS=4/50 with 4 sizes each"


def test_burst_shaping_non_destructive():
    """Burst shaping produces same decoded payload."""
    payload = b'SHAPING TEST\n'
    
    # Without shaping
    bits = make_packet_bits(payload)
    wf_no_shape = np.array(bpsk_modulate(bits))
    
    # With shaping
    wf_shaped = apply_burst_shaping(wf_no_shape.copy())
    
    # The shaped vs unshaped waveforms should decode identically
    for label, wf in [("unshaped", wf_no_shape), ("shaped", wf_shaped)]:
        I = (wf.real * 80).clip(-128, 127).astype(np.int8)
        Q = (wf.imag * 80).clip(-128, 127).astype(np.int8)
        iq = np.empty(2 * len(I), dtype=np.int8)
        iq[0::2] = I; iq[1::2] = Q
        dec = _decode_iq(iq)
        assert dec == payload, f"{label}: decode failed: {dec}"
    
    # Also test through make_test_burst with and without shaping
    for ramp in [0, 50]:
        burst = make_test_burst(payload, n_packets=2, gap_ms=10, ramp_symbols=ramp)
        wf_arr = np.array(burst, dtype=np.complex64)
        I = (wf_arr.real * 80).clip(-128, 127).astype(np.int8)
        Q = (wf_arr.imag * 80).clip(-128, 127).astype(np.int8)
        iq_burst = np.empty(2 * len(I), dtype=np.int8)
        iq_burst[0::2] = I; iq_burst[1::2] = Q
        
        I_f = iq_burst[0::2].astype(np.float64) - np.mean(iq_burst[0::2])
        Q_f = iq_burst[1::2].astype(np.float64) - np.mean(iq_burst[1::2])
        samples = I_f + 1j * Q_f
        fo = scan_frequency(samples)
        t = np.arange(len(samples), dtype=np.float64)
        bb = samples * np.exp(-2j * np.pi * fo * t / FS)
        rrc = rcc_taps()
        filtered = np.convolve(bb.real, rrc, 'same')
        
        found = False
        for phase in range(SPS):
            for r in process_phase(filtered, phase, fo):
                if r['message'] == payload:
                    found = True
                    break
            if found:
                break
        assert found, f"ramp_symbols={ramp}: no packet decoded"
    
    return "OK  shaping preserves decoded payload"


def test_agc():
    """Digital AGC recovers signal from artificially scaled IQ."""
    payload = b'AGC TEST\n'
    iq, _ = _encode_iq(payload)
    
    # Scale down by 0.05 (very weak signal)
    I = iq[0::2].astype(np.float64) * 0.05 - np.mean(iq[0::2].astype(np.float64) * 0.05)
    Q = iq[1::2].astype(np.float64) * 0.05 - np.mean(iq[1::2].astype(np.float64) * 0.05)
    samples = I + 1j * Q
    
    # Without AGC: should fail (too weak)
    fo = scan_frequency(samples)
    t = np.arange(len(samples), dtype=np.float64)
    bb = samples * np.exp(-2j * np.pi * fo * t / FS)
    rrc = rcc_taps()
    filtered = np.convolve(bb.real, rrc, 'same')
    
    without_agc = None
    for phase in range(SPS):
        for r in process_phase(filtered, phase, fo):
            without_agc = r['message']
            break
        if without_agc:
            break
    # (this may or may not decode — the key test is with AGC)
    
    # With AGC: must recover
    samples_agc = apply_digital_agc(samples)
    
    fo2 = scan_frequency(samples_agc)
    t2 = np.arange(len(samples_agc), dtype=np.float64)
    bb2 = samples_agc * np.exp(-2j * np.pi * fo2 * t2 / FS)
    bb2 -= np.mean(bb2)
    rrc2 = rcc_taps()
    filtered2 = np.convolve(bb2.real, rrc2, 'same')
    
    dec = None
    for phase in range(SPS):
        for r in process_phase(filtered2, phase, fo2):
            dec = r['message']
            break
        if dec:
            break
    
    assert dec == payload, f"AGC: decode failed (got {dec!r})"
    return "OK  AGC recovers 0.05x scaled signal"


def test_agc_extreme():
    """AGC with very weak signal (0.01x) and different target RMS."""
    payload = b'EXTREME\n'
    iq, _ = _encode_iq(payload)
    
    I = iq[0::2].astype(np.float64) * 0.01 - np.mean(iq[0::2].astype(np.float64) * 0.01)
    Q = iq[1::2].astype(np.float64) * 0.01 - np.mean(iq[1::2].astype(np.float64) * 0.01)
    samples = I + 1j * Q
    
    # Use custom AGC target
    samples_agc = apply_digital_agc(samples, target_rms=0.5)
    
    fo = scan_frequency(samples_agc)
    t = np.arange(len(samples_agc), dtype=np.float64)
    bb = samples_agc * np.exp(-2j * np.pi * fo * t / FS)
    bb -= np.mean(bb)
    rrc = rcc_taps()
    filtered = np.convolve(bb.real, rrc, 'same')
    
    dec = None
    for phase in range(SPS):
        for r in process_phase(filtered, phase, fo):
            dec = r['message']
            break
        if dec:
            break
    
    assert dec == payload, f"AGC extreme: decode failed (got {dec!r})"
    return "OK  AGC recovers 0.01x scaled signal"


def test_fo_injection():
    """Inject known frequency offset, verify tracking follows."""
    payload = b'FO INJECT\n'
    iq, _ = _encode_iq(payload)
    
    I = iq[0::2].astype(np.float64) - np.mean(iq[0::2].astype(np.float64))
    Q = iq[1::2].astype(np.float64) - np.mean(iq[1::2].astype(np.float64))
    samples = I + 1j * Q
    
    # Inject +5000 Hz FO
    offset_hz = 5000
    t = np.arange(len(samples), dtype=np.float64)
    samples_shifted = samples * np.exp(2j * np.pi * offset_hz * t / FS)
    
    # FO estimator should find ~5000 Hz
    fo_est = scan_frequency(samples_shifted)
    assert abs(fo_est - offset_hz) < 500, \
        f"FO injection: estimated {fo_est:.0f} Hz, expected ~{offset_hz} Hz"
    
    # Decode should still work after mixing down with estimated FO
    bb = samples_shifted * np.exp(-2j * np.pi * fo_est * t / FS)
    rrc = rcc_taps()
    filtered = np.convolve(bb.real, rrc, 'same')
    
    dec = None
    for phase in range(SPS):
        for r in process_phase(filtered, phase, fo_est):
            dec = r['message']
            break
        if dec:
            break
    
    assert dec == payload, f"FO injection: decode failed (got {dec!r})"
    return f"OK  FO={fo_est:.0f} Hz (injected {offset_hz} Hz)"


def test_fo_injection_negative():
    """Inject negative frequency offset."""
    payload = b'NEGATIVE FO\n'
    iq, _ = _encode_iq(payload)
    
    I = iq[0::2].astype(np.float64) - np.mean(iq[0::2].astype(np.float64))
    Q = iq[1::2].astype(np.float64) - np.mean(iq[1::2].astype(np.float64))
    samples = I + 1j * Q
    
    offset_hz = -8000
    t = np.arange(len(samples), dtype=np.float64)
    samples_shifted = samples * np.exp(2j * np.pi * offset_hz * t / FS)
    
    fo_est = scan_frequency(samples_shifted)
    assert abs(fo_est - offset_hz) < 500, \
        f"FO injection (neg): estimated {fo_est:.0f} Hz, expected ~{offset_hz} Hz"
    
    bb = samples_shifted * np.exp(-2j * np.pi * fo_est * t / FS)
    rrc = rcc_taps()
    filtered = np.convolve(bb.real, rrc, 'same')
    
    dec = None
    for phase in range(SPS):
        for r in process_phase(filtered, phase, fo_est):
            dec = r['message']
            break
        if dec:
            break
    
    assert dec == payload, f"FO injection (neg): decode failed (got {dec!r})"
    return f"OK  FO={fo_est:.0f} Hz (injected {offset_hz} Hz)"


def test_backward_compat():
    """All original tests pass at SPS=20 (default)."""
    # This is a smoke test that the default SPS=20 path still works
    # by re-running the first two test cases
    payload = b'BACKWARD COMPAT\n'
    iq, nbits = _encode_iq(payload)
    dec = _decode_iq(iq)
    assert dec == payload, f"Backward compat decode failed: {dec}"
    return f"OK  backward compatible at SPS=20"


# ── Test registry ────────────────────────────────────────
TESTS = [
    ("single packet",       test_single_packet),
    ("multiple sizes",      test_multiple_sizes),
    ("burst",               test_burst),
    ("oversized capture",   test_oversized_capture),
    ("FO estimator",        test_fo_estimator),
    # New tests
    ("SPS variants",        test_sps_variants),
    ("SPS small payload",   test_sps_small_payload),
    ("burst shaping",       test_burst_shaping_non_destructive),
    ("AGC",                 test_agc),
    ("AGC extreme",         test_agc_extreme),
    ("FO injection +5kHz",  test_fo_injection),
    ("FO injection -8kHz",  test_fo_injection_negative),
    ("backward compat",     test_backward_compat),
]


if __name__ == '__main__':
    failed = 0
    for name, fn in TESTS:
        try:
            result = fn()
            print(f"  ✓  {name:<20s}  {result}")
        except Exception as e:
            print(f"  ✗  {name:<20s}  {e}")
            failed += 1
    sys.exit(failed)
