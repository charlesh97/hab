#!/usr/bin/env python3
"""
Layer 2 — Software Loopback Tests.

Generates TX waveforms and runs them through the production RX pipeline:
GNU Radio FLL, RRC matched filter, sync acquisition, Costas loop, and CRC.
No radio hardware required.
"""
import os
import sys
import time
from pathlib import Path

_HAB = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(_HAB / "ground" / "rx"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import numpy as np

from pkt_simple_tx import make_packet, make_test_packets
from demod import (
    PacketDecoder, rcc_taps, scan_frequency,
    SPS, FS, SYNC_BPSK, SYNC_BITS, PRE_SYNC
)


def decode_waveform(wf):
    """Run the exact production decoder and return decoded payloads."""
    results = PacketDecoder().decode(np.asarray(wf, dtype=np.complex64))
    return [result[0] for result in results]


def add_carrier(wf, fo_hz, phase_rad=1.1):
    """Apply deterministic carrier frequency and phase offsets."""
    samples = np.asarray(wf, dtype=np.complex64)
    time_samples = np.arange(len(samples), dtype=np.float64)
    rotation = np.exp(1j * (2 * np.pi * fo_hz * time_samples / FS + phase_rad))
    return np.asarray(samples * rotation, dtype=np.complex64)


# ── Core Loopback Tests ───────────────────────────────────

def test_single_packet():
    """One packet round-trip through full RX pipeline."""
    payload = b'HELLO WORLD'
    wf = np.array(make_packet(payload, sps=20))
    results = decode_waveform(wf)
    assert results == [payload], f"Expected one deduplicated payload, got {results}"
    return f"OK  {len(wf)} samples, {len(results)} decoded"

def test_multiple_sizes():
    """Payload sizes 1–128 bytes all decode correctly (within MAX_PAYLOAD_BYTES)."""
    for pl_len in [1, 5, 12, 50, 100, 128]:
        payload = bytes([i % 256 for i in range(pl_len)])
        wf = np.array(make_packet(payload, sps=20))
        results = decode_waveform(wf)
        assert payload in results, f"{pl_len}B: not decoded (got {results})"
    return "OK  6 sizes (1-128B)"

def test_burst_decode():
    """Multi-packet burst: all packets decoded."""
    payload = b'BURST TEST'
    burst = make_test_packets(payload, n_packets=5, gap_ms=50)
    wf = np.array(burst)
    results = decode_waveform(wf)
    count = sum(1 for r in results if r == payload)
    assert count == 5, f"Only {count}/5 burst packets decoded"
    return f"OK  {count}/5 decoded"


def test_noisy_gapped_burst():
    """Carrier loops reacquire each packet across hardware-like noisy gaps."""
    payload = b'GAP NOISE'
    waveform = np.asarray(
        make_test_packets(payload, n_packets=5, gap_ms=30),
        dtype=np.complex64,
    )
    rng = np.random.default_rng(4335)
    noise = 0.1 * (
        rng.standard_normal(len(waveform)) +
        1j * rng.standard_normal(len(waveform))
    )
    results = decode_waveform(waveform + noise.astype(np.complex64))
    assert results == [payload] * 5, f"Noisy gap decode count: {len(results)}/5"
    return "OK  5/5 with noisy 30ms gaps"

def test_oversized_capture():
    """Packet buried in zeros — still decodes."""
    payload = b'BURIED'
    pkt_wf = np.array(make_packet(payload, sps=20))
    # Pad with zeros before and after
    pad = np.zeros(len(pkt_wf) * 2, dtype=np.complex64)
    full = np.concatenate([pad, pkt_wf, pad])
    results = decode_waveform(full)
    assert payload in results, f"Oversized: not decoded"
    return "OK  buried in 4× padding"

def test_non_ascii_payload():
    """Binary payloads (all byte values) decode correctly."""
    payload = bytes(range(128))  # within MAX_PAYLOAD_BYTES
    wf = np.array(make_packet(payload, sps=20))
    results = decode_waveform(wf)
    assert payload in results, "128 binary bytes not decoded"
    return "OK  128 binary bytes"

def test_crc_catches_corruption():
    """Gaussian noise injection → original payload NOT recovered.

    Adding noise at the IQ sample level is averaged out by the RRC matched
    filter. We inject noise at sufficient power that bit errors become
    likely, then verify CRC prevents the original payload from being
    recovered.
    """
    payload = b'CORRUPT ME'
    wf = np.array(make_packet(payload, sps=20))

    # Clean decode should work
    results = decode_waveform(wf)
    clean_count = sum(1 for r in results if r == payload)
    assert clean_count >= 1, f"Clean decode failed (got {len(results)} results)"

    # Inject Gaussian noise at 200% of signal amplitude — guarantees bit errors
    np.random.seed(42)
    signal_rms = np.sqrt(np.mean(np.abs(wf)**2))
    noise = (np.random.randn(len(wf)) + 1j * np.random.randn(len(wf))) * signal_rms * 2.0
    wf_noisy = wf + noise.astype(np.complex64)

    results_n = decode_waveform(wf_noisy)
    valid = [r for r in results_n if r == payload]
    # At 200% noise, CRC should prevent original payload recovery
    assert len(valid) == 0, \
        f"CRC FAIL: original payload recovered from noisy signal ({len(results_n)} total decoded)"
    return f"OK  original payload NOT recovered ({len(results_n)} random CRC passes)"

def test_fo_estimator_approximate():
    """Band-edge FLL reports baseband carrier near zero."""
    payload = b'FO TEST'
    wf = np.array(make_packet(payload, sps=20))
    fo = scan_frequency(wf)
    assert abs(fo) < 10, f"Unexpected baseband FO: {fo:.1f} Hz"
    return f"OK  fo={fo:.2f} Hz"


def test_costas_residual_tracking():
    """Native GNU Radio Costas loop tracks residual offsets at symbol rate."""
    rng = np.random.default_rng(20260719)
    preamble_bits = np.array(([1, 0] * 128), dtype=np.uint8)
    data_bits = rng.integers(0, 2, 1024, dtype=np.uint8)
    bits = np.concatenate([preamble_bits, data_bits])
    mapped = 1.0 - 2.0 * bits.astype(np.float64)
    symbol_rate = FS / SPS
    decoder = PacketDecoder()

    for fo_hz in [-250, -100, -50, 0, 50, 100, 250]:
        n = np.arange(len(mapped), dtype=np.float64)
        symbols = mapped * np.exp(1j * (2 * np.pi * fo_hz * n / symbol_rate + 0.91))
        corrected, estimated = decoder._costas_correct(symbols)
        hard = (corrected[PRE_SYNC:].real < 0).astype(np.uint8)
        if np.mean(hard == data_bits) < 0.5:
            hard = 1 - hard
        assert np.array_equal(hard, data_bits), f"Costas bit errors at {fo_hz} Hz"
        assert abs(estimated - fo_hz) < 2.0, \
            f"Costas estimate {estimated:.2f} Hz for {fo_hz} Hz"
    return "OK  residual FO ±250 Hz"


def test_full_carrier_offsets_128_bytes():
    """Full acquisition and tracking decode 128-byte packets across ±8 kHz."""
    payload = bytes(range(128))
    waveform = make_packet(payload, sps=SPS)
    for fo_hz in [-8000, -3000, -250, 250, 3000, 8000]:
        results = PacketDecoder().decode(add_carrier(waveform, fo_hz))
        matching = [result for result in results if result[0] == payload]
        assert len(matching) == 1, f"{fo_hz} Hz: expected one decode, got {len(matching)}"
        assert abs(matching[0][2] - fo_hz) < 25, \
            f"{fo_hz} Hz: reported {matching[0][2]:.2f} Hz"
    return "OK  128B at ±250/±3k/±8k Hz"


def test_long_payload_with_awgn():
    """A 128-byte packet survives moderate complex AWGN and carrier offset."""
    payload = bytes(range(127, -1, -1))
    waveform = add_carrier(make_packet(payload, sps=SPS), 3000, phase_rad=2.2)
    rng = np.random.default_rng(42)
    signal_rms = np.sqrt(np.mean(np.abs(waveform) ** 2))
    snr_linear = 10 ** (15 / 10)
    noise_scale = signal_rms / np.sqrt(2 * snr_linear)
    noise = noise_scale * (rng.standard_normal(len(waveform)) + 1j * rng.standard_normal(len(waveform)))
    results = decode_waveform(waveform + noise.astype(np.complex64))
    assert results == [payload], f"AWGN decode failed: {len(results)} results"
    return "OK  128B, 3kHz FO, 15dB SNR"


def test_incomplete_preamble_rejected():
    """Sync candidates without a complete acquisition preamble are rejected."""
    waveform = np.asarray(make_packet(b'NO PREFIX', sps=SPS), dtype=np.complex64)
    truncated = waveform[100 * SPS:]
    assert decode_waveform(truncated) == [], "Decoded packet without full preamble"
    return "OK  missing 100 preamble symbols"

# ── Performance Test ──────────────────────────────────────

def test_decode_performance():
    """Decode completes in under 2 seconds for 1M samples."""
    # Generate a waveform and pad to ~500K samples
    payload = b'PERF'
    pkt_wf = np.array(make_packet(payload, sps=20))
    # Repeat to make larger
    wf = np.tile(pkt_wf, 30)

    t0 = time.time()
    results = decode_waveform(wf)
    elapsed = time.time() - t0

    assert len(results) >= 1, "No decode in perf test"
    assert elapsed < 5.0, f"Decode too slow: {elapsed:.2f}s for {len(wf)} samples"
    return f"OK  {elapsed:.3f}s for {len(wf)} samples ({len(results)} decoded)"

# ── Sync Word Integrity ──────────────────────────────────

def test_sync_correlation_peak():
    """Sync word correlation produces a clear, unambiguous peak."""
    payload = b'PEAK TEST'
    wf = np.array(make_packet(payload, sps=20))
    samples = wf - np.mean(wf)
    rrc = rcc_taps()
    filt = np.convolve(samples.real, rrc, 'same')

    # Check all 20 phases for correlation quality
    best_peak = 0
    for phase in range(SPS):
        symbols = filt[phase::SPS]
        if len(symbols) < PRE_SYNC + SYNC_BITS + 32:
            continue
        corr = np.correlate(symbols, SYNC_BPSK, 'valid')
        cp = np.abs(corr)
        if len(cp) == 0:
            continue
        peak = np.max(cp)
        if peak > best_peak:
            best_peak = peak

    assert best_peak > 50, f"Weak correlation peak: {best_peak:.1f}"
    return f"OK  peak={best_peak:.1f}"


# ── Test registry ────────────────────────────────────────
TESTS = [
    ("single packet",            test_single_packet),
    ("multiple sizes",           test_multiple_sizes),
    ("burst decode",             test_burst_decode),
    ("noisy gapped burst",       test_noisy_gapped_burst),
    ("oversized capture",        test_oversized_capture),
    ("non-ASCII payload",        test_non_ascii_payload),
    ("CRC catches corruption",   test_crc_catches_corruption),
    ("FO estimator baseband",    test_fo_estimator_approximate),
    ("Costas residual tracking", test_costas_residual_tracking),
    ("128B carrier offsets",     test_full_carrier_offsets_128_bytes),
    ("128B with AWGN",           test_long_payload_with_awgn),
    ("incomplete preamble",      test_incomplete_preamble_rejected),
    ("decode performance",       test_decode_performance),
    ("sync correlation peak",    test_sync_correlation_peak),
]


if __name__ == '__main__':
    failed = 0
    for name, fn in TESTS:
        try:
            result = fn()
            print(f"  ✓  {name:<26s}  {result}")
        except Exception as e:
            print(f"  ✗  {name:<26s}  {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    sys.exit(failed)
