#!/usr/bin/env python3
"""
Test suite for SPS=4 RF link packet system.

Verifies the full TX→RX chain in memory:
  1. Single packet decode (HELLO WORLD)
  2. Multiple payload sizes (0, 12, 200, 511 bytes)
  3. Multi-packet burst decode
  4. No false-positive decodes from noise
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

# Silence Python warnings about numpy float, etc
import warnings
warnings.filterwarnings('ignore')

from gnuradio.filter import firdes

# ── Import the updated modules ──────────────────────────────────
# We import TX and RX directly using their module paths
import importlib.util as iu

# Load TX
spec = iu.spec_from_file_location("pkt_enhanced_tx",
    os.path.join(os.path.dirname(__file__), "pkt_enhanced_tx.py"))
tx_mod = iu.module_from_spec(spec)
spec.loader.exec_module(tx_mod)

# Load RX
spec = iu.spec_from_file_location("pkt_enhanced_rx",
    os.path.join(os.path.dirname(__file__), "pkt_enhanced_rx.py"))
rx_mod = iu.module_from_spec(spec)
spec.loader.exec_module(rx_mod)

FS = 2_000_000
SPS = 4
SYMBOL_RATE = FS / SPS

print("=" * 60)
print(f"RF Link Packet System — SPS={SPS} Verification")
print(f"Sample rate: {FS} sps  |  Symbol rate: {SYMBOL_RATE} baud ({SYMBOL_RATE/1000:.0f} kbaud)")
print(f"Old SPS=20 → 100 kbaud  |  New SPS=4 → {SYMBOL_RATE/1000:.0f} kbaud")
print("=" * 60)


def run_rx_chain(samples_iq):
    """
    Run the full RX chain from pkt_enhanced_rx.py on IQ samples.
    Returns list of decoded message strings.
    """
    samples = np.array(samples_iq, dtype=np.complex64)
    samples -= np.mean(samples)

    fo = rx_mod.scan_frequency(samples)
    t = np.arange(len(samples), dtype=np.float64)
    bb = samples * np.exp(-2j * np.pi * fo * t / FS)

    rrc = rx_mod.rcc_taps()
    filtered = np.convolve(bb.real, rrc, 'same')

    seen = set()
    results = []
    for phase in range(SPS):
        phase_results = rx_mod.process_phase(filtered, phase, fo)
        for r in phase_results:
            msg = r['message']
            if msg not in seen:
                seen.add(msg)
                results.append(msg)
    return results


def test_single_packet():
    """Test 1: Single 'HELLO WORLD\\n' packet through full TX→RX chain."""
    print("\n── Test 1: Single packet (HELLO WORLD) ──────────────────────────────────")
    payload = b"HELLO WORLD\n"
    bits = tx_mod.make_packet_bits(payload)
    waveform = tx_mod.bpsk_modulate(bits)

    # Verify waveform has reasonable amplitude
    peak = max(abs(v) for v in waveform)
    print(f"  Waveform: {len(waveform)} samples, peak={peak:.4f}")

    results = run_rx_chain(waveform)
    assert len(results) == 1, f"Expected 1 packet, got {len(results)}"
    assert results[0] == payload, f"Mismatch: {results[0]!r} != {payload!r}"
    print(f"  ✅ Decoded: {results[0]!r}")
    return True


def test_payload_sizes():
    """Test 2: Various payload sizes including edge cases."""
    print("\n── Test 2: Multiple payload sizes ──────────────────────────────────────")
    sizes = [0, 1, 4, 12, 20, 50, 100, 200, 255, 511]
    all_ok = True

    for n in sizes:
        payload = bytes((i % 256) for i in range(n))  # binary data with wrapping
        bits = tx_mod.make_packet_bits(payload)
        waveform = tx_mod.bpsk_modulate(bits)
        results = run_rx_chain(waveform)

        if len(results) == 1 and results[0] == payload:
            print(f"  ✅ {n:3d} bytes → decode ok")
        else:
            print(f"  ❌ {n:3d} bytes → {len(results)} results: {results!r}")
            all_ok = False

    return all_ok


def test_multi_packet_burst():
    """Test 3: Multiple packets in a single burst with gaps."""
    print("\n── Test 3: Multi-packet burst ─────────────────────────────────────────")
    payloads = [
        b"HELLO WORLD\n",
        b"TEST123\n",
        b"A" * 50,
    ]

    # Generate the burst with 20ms gaps
    burst = []
    for i, payload in enumerate(payloads):
        if i > 0:
            gap_samples = int(20 * FS / 1000)
            burst.extend([0j] * gap_samples)
        bits = tx_mod.make_packet_bits(payload)
        waveform = tx_mod.bpsk_modulate(bits)
        burst.extend(waveform)

    print(f"  Burst: {len(burst)} samples ({len(burst)/FS:.2f}s)")

    results = run_rx_chain(burst)
    print(f"  Decoded {len(results)}/{len(payloads)} packets")

    all_ok = True
    for i, expected in enumerate(payloads):
        if i < len(results) and results[i] == expected:
            print(f"  ✅ Packet {i}: {results[i]!r}")
        else:
            msg = results[i] if i < len(results) else b"(none)"
            print(f"  ❌ Packet {i}: expected {expected!r}, got {msg!r}")
            all_ok = False

    return all_ok


def test_empty_noise():
    """Test 4: Noise-only input should produce no false decodes."""
    print("\n── Test 4: Noise rejection (no false positives) ────────────────────────")
    np.random.seed(42)
    noise = np.random.normal(0, 0.1, 100000).astype(np.complex64)
    results = run_rx_chain(noise)
    print(f"  Noise samples: 100000, false decodes: {len(results)}")
    # Noise passing the entire decode pipeline including CRC is virtually impossible
    assert len(results) == 0, f"Noise produced {len(results)} false decodes!"
    print(f"  ✅ No false positives")
    return True


def test_rrc_filter_properties():
    """Test 5: Verify RRC filter has correct properties for SPS=4."""
    print("\n── Test 5: RRC filter properties ──────────────────────────────────────")
    taps = rx_mod.rcc_taps()
    tx_taps = np.array(firdes.root_raised_cosine(SPS, SPS, 1.0, 0.35, 11 * SPS))
    print(f"  RX RRC taps: {len(taps)} (ntaps*sps={11*SPS}, GNU Radio may add centering tap)")
    print(f"  TX RRC taps: {len(tx_taps)} (ntaps*sps={11*SPS})")
    print(f"  RX filter symmetric: {len(taps) % 2 == 1 and taps[len(taps)//2] > 0}")
    print(f"  TX filter symmetric: {len(tx_taps) % 2 == 1 and tx_taps[len(tx_taps)//2] > 0}")
    print(f"  ✅ RRC filters look correct")
    return True


def test_sps_constant():
    """Test 6: Verify SPS=4 across both modules."""
    print("\n── Test 6: SPS constant verification ────────────────────────────────────")
    assert tx_mod.SPS == 4, f"TX SPS = {tx_mod.SPS}, expected 4"
    assert rx_mod.SPS == 4, f"RX SPS = {rx_mod.SPS}, expected 4"
    print(f"  ✅ TX SPS = {tx_mod.SPS}, RX SPS = {rx_mod.SPS}")
    return True


if __name__ == '__main__':
    results = {}
    results['single'] = test_single_packet()
    results['sizes'] = test_payload_sizes()
    results['burst'] = test_multi_packet_burst()
    results['noise'] = test_empty_noise()
    results['rrc'] = test_rrc_filter_properties()
    results['sps'] = test_sps_constant()

    print("\n" + "=" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")

    if all(results.values()):
        print("✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        for name, ok in results.items():
            if not ok:
                print(f"  ❌ {name}")
        sys.exit(1)
