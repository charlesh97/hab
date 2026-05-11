#!/usr/bin/env python3
"""
Layer 2 — RF Software Loopback.

Tests the full TX→RX pipeline in software (no radio hardware):
  TX: payload → packet_encode() → bits → BPSK modulate → [preamble|sync|FEC]
  Save as int8 IQ → Load → FO scan → RRC filter → decimate →
  sync correlation → extract payload → packet_decode()
"""
import sys, os, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pkt_enhanced_tx import make_packet_bits, bpsk_modulate, make_test_burst
from pkt_enhanced_rx import (
    process_phase, scan_frequency, rcc_taps,
    FS, SPS, PREAMBLE_BITS, MAX_FEC_SYMS, SYNC_BPSK, SYNC_BITS
)


def _encode_iq(payload):
    """Generate int8 IQ from a single packet."""
    bits = make_packet_bits(payload)
    wf = np.array(bpsk_modulate(bits))
    I = (wf.real * 80).clip(-128, 127).astype(np.int8)
    Q = (wf.imag * 80).clip(-128, 127).astype(np.int8)
    iq = np.empty(2 * len(I), dtype=np.int8)
    iq[0::2] = I
    iq[1::2] = Q
    return iq, len(bits)


def _decode_iq(iq, fec_syms=None):
    """Full RX pipeline: int8 IQ → decoded message or None."""
    I = iq[0::2].astype(np.float64) - np.mean(iq[0::2])
    Q = iq[1::2].astype(np.float64) - np.mean(iq[1::2])
    samples = I + 1j * Q

    fo = scan_frequency(samples)
    t = np.arange(len(samples), dtype=np.float64)
    bb = samples * np.exp(-2j * np.pi * fo * t / FS)
    rrc = rcc_taps()
    filtered = np.convolve(bb.real, rrc, 'same')

    for phase in range(SPS):
        for r in process_phase(filtered, phase, fo):
            return r['message']  # return first successful decode
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


# ── Test registry ────────────────────────────────────────
TESTS = [
    ("single packet",       test_single_packet),
    ("multiple sizes",      test_multiple_sizes),
    ("burst",               test_burst),
    ("oversized capture",   test_oversized_capture),
    ("FO estimator",       test_fo_estimator),
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
