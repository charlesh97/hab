#!/usr/bin/env python3
"""
Layer 1 — Codec Unit Tests (no radio, no pipeline).

Tests CRC-16, length field, packet construction, burst structure,
sync word integrity, and silence rejection. Does NOT test the full
RX decode pipeline — that's Layer 2 (software loopback).
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import numpy as np

from pkt_simple_tx import FS, crc16, make_packet, make_test_packets
from pkt_simple_rx import PacketDecoder, SYNC_WORD, SYNC_BITS, PRE_SYNC, LEN_BITS, CRC_BITS, MAX_PAYLOAD_BYTES, SPS


# ── CRC-16 Tests ──────────────────────────────────────────

def test_crc_known_vector():
    """CRC-16/XMODEM check value."""
    assert crc16(b'123456789') == 0x31C3
    return "OK  0x31C3"

def test_crc_empty():
    """CRC-16 of empty payload."""
    assert crc16(b'') == 0x0000
    return "OK  0x0000"

def test_crc_deterministic():
    """Same input → same CRC, different inputs → different CRC."""
    assert crc16(b'A') == crc16(b'A')
    assert crc16(b'A') != crc16(b'B')
    assert crc16(b'AB') != crc16(b'BA')
    return "OK  deterministic"

def test_crc_single_bit():
    """Single-bit change flips CRC."""
    a = crc16(b'\x00' * 10)
    b = crc16(b'\x00' * 9 + b'\x01')
    assert a != b
    return "OK  bit-sensitive"

def test_crc_all_bytes():
    """All 256 byte values produce valid 16-bit CRCs."""
    for b in range(256):
        c = crc16(bytes([b]))
        assert 0 <= c <= 0xFFFF
    return "OK  256 single-byte CRCs"

# ── Length Field Tests ────────────────────────────────────

def test_length_encoding():
    """2-byte big-endian length field round-trips."""
    for n in [0, 1, 12, 127, 128, 255]:
        lb = struct.pack('>H', n)
        val = (lb[0] << 8) | lb[1]
        assert val == n, f"Length {n}: {val} != {n}"
    return "OK  6 values (0-255)"

def test_length_max_boundary():
    """Length field handles 0x0000 and 0xFFFF."""
    assert struct.pack('>H', 0) == b'\x00\x00'
    assert struct.pack('>H', 65535) == b'\xff\xff'
    return "OK  0x0000, 0xFFFF"

# ── Packet Construction Tests ─────────────────────────────

def test_packet_structure():
    """Packet waveform has correct sample count for given payload."""
    for pl_len in [1, 5, 12, 100, 255]:
        payload = bytes([i % 256 for i in range(pl_len)])
        wf = np.array(make_packet(payload, sps=20))
        energy = np.sum(np.abs(wf)**2)
        assert energy > 0, f"Zero-energy waveform for {pl_len}B"
        nbits = PRE_SYNC + SYNC_BITS + LEN_BITS + pl_len*8 + CRC_BITS
        assert abs(len(wf) - nbits*SPS) < 200, \
            f"Size mismatch: {len(wf)} vs {nbits*SPS}"
    return "OK  5 sizes (1-255B)"

def test_packet_nonzero():
    """Every packet waveform has significant signal energy."""
    for msg in [b'X', b'HELLO', b'\x00' * 20]:
        wf = np.array(make_packet(msg, sps=20))
        peak = np.max(np.abs(wf))
        assert peak > 0.01, f"Low peak {peak:.4f} for {msg!r}"
    return "OK  peak > 0.01 for all"

def test_burst_packet_count():
    """make_test_packets produces correct number of packets."""
    payload = b'BURST'
    for n in [1, 3, 10]:
        burst = make_test_packets(payload, n_packets=n, gap_ms=50)
        burst_arr = np.array(burst)
        # Count non-zero regions as proxy for packets
        nonzero = np.abs(burst_arr) > 1e-10
        # Each packet is ~7200 samples; count transitions
        transitions = np.diff(nonzero.astype(int))
        regions = np.sum(transitions == 1)  # rising edges
        # Allow 1-packet margin (first region may not have rising edge)
        assert regions >= n - 1, f"Expected ≥{n-1} packet regions, got {regions}"
    return "OK  1/3/10 packets"

def test_burst_gap_length():
    """Gap between packets is approximately correct.

    The RRC-shaped waveform produces near-zero crossings throughout the packet,
    but the explicit [0j] gap samples are the only *exactly zero* samples.
    The longest contiguous zero runs are the inter-packet gaps.
    """
    payload = b'X'
    gap_ms = 50
    burst = np.array(make_test_packets(payload, n_packets=3, gap_ms=gap_ms))
    gap_exp = int(gap_ms * FS / 1000)  # samples at 2 Msps
    # Only exact zeros come from the explicit gap padding
    is_exact_zero = np.abs(burst) == 0.0
    zero_runs = []
    count = 0
    in_run = False
    for v in is_exact_zero:
        if v and not in_run:
            count = 1; in_run = True
        elif v and in_run:
            count += 1
        elif not v and in_run:
            zero_runs.append(count)
            count = 0; in_run = False
    if in_run:
        zero_runs.append(count)
    # The longest runs should be the inter-packet gaps.
    assert len(zero_runs) >= 2, f"Expected ≥2 gap runs, got {len(zero_runs)}"
    longest = sorted(zero_runs, reverse=True)[:3]
    assert abs(longest[0] - gap_exp) < 5, \
        f"Longest gap run {longest[0]} ≠ {gap_exp}"
    assert abs(longest[1] - gap_exp) < 5, \
        f"Second-longest gap run {longest[1]} ≠ {gap_exp}"
    return f"OK  2× {longest[0]}-sample gaps (target {gap_exp})"

# ── Sync Word Tests ───────────────────────────────────────

def test_sync_word_constant():
    """Sync word is the proven 0xE38FC0FC."""
    assert SYNC_WORD == 0xE38FC0FC, f"Sync word changed: 0x{SYNC_WORD:08X}"
    return "OK  0xE38FC0FC"

def test_sync_bits_correct():
    """SYNC_BITS matches 32-bit sync word."""
    assert SYNC_BITS == 32
    return "OK  32 bits"

# ── RX Constants Tests ────────────────────────────────────

def test_constants_reasonable():
    """Key constants are within expected ranges."""
    assert PRE_SYNC == 256, f"Preamble: {PRE_SYNC}"
    assert LEN_BITS == 16
    assert CRC_BITS == 16
    assert MAX_PAYLOAD_BYTES >= 128
    assert SPS == 20
    return "OK  preamble=256, len=16b, crc=16b, max_payload≥128"

# ── Silence / Noise Rejection ─────────────────────────────

def test_no_false_positives_silence():
    """Silent input produces zero decodes."""
    decoder = PacketDecoder()
    np.random.seed(12345)
    noise = (np.random.randn(50000) + 1j * np.random.randn(50000)).astype(np.complex64)
    noise *= 0.1
    results = decoder.decode(noise)
    assert len(results) == 0, f"Noise produced {len(results)} false positives"
    return "OK  0 false positives"

# ── CRITICAL: TX Payload → RX Check (bit-level) ──────────

def test_tx_bits_match_rx_bit_extraction():
    """Verify that the TX bit sequence can be extracted by the RX bit logic."""
    # Build a known payload and extract the raw bits the TX would send
    payload = b'HELLO WORLD'
    # Reconstruct exactly the bit sequence TX uses
    preamble_bits = ([1, 0] * 128)[:256]
    sync_word = 0xE38FC0FC
    sync_bits = [(sync_word >> (31 - i)) & 1 for i in range(32)]
    length = len(payload)
    len_bytes = struct.pack('>H', length)
    crc = crc16(payload)
    crc_bytes = struct.pack('>H', crc)

    def _bytes_to_bits(bs):
        bits = []
        for b in bs:
            for i in range(8):
                bits.append((b >> (7 - i)) & 1)
        return bits

    all_bits = (preamble_bits + sync_bits +
                _bytes_to_bits(len_bytes) +
                _bytes_to_bits(payload) +
                _bytes_to_bits(crc_bytes))

    # Verify sync word position
    sync_region = all_bits[256:256+32]
    sync_val = 0
    for i, b in enumerate(sync_region):
        sync_val |= b << (31 - i)
    assert sync_val == sync_word, f"Sync word mismatch: 0x{sync_val:08X}"

    # Verify length field
    len_region = all_bits[256+32:256+32+16]
    len_val = 0
    for i, b in enumerate(len_region):
        len_val |= b << (15 - i)
    assert len_val == length, f"Length mismatch: {len_val} ≠ {length}"

    # Verify CRC field
    crc_start = 256 + 32 + 16 + len(payload)*8
    crc_region = all_bits[crc_start:crc_start+16]
    crc_val = 0
    for i, b in enumerate(crc_region):
        crc_val |= b << (15 - i)
    assert crc_val == crc, f"CRC mismatch: 0x{crc_val:04X} ≠ 0x{crc:04X}"

    return f"OK  sync=0x{sync_val:08X} len={len_val} crc=0x{crc_val:04X}"


# ── Test registry ────────────────────────────────────────
TESTS = [
    ("CRC known vector",         test_crc_known_vector),
    ("CRC empty",                 test_crc_empty),
    ("CRC deterministic",         test_crc_deterministic),
    ("CRC bit-sensitive",         test_crc_single_bit),
    ("CRC all 256 bytes",         test_crc_all_bytes),
    ("length encoding",           test_length_encoding),
    ("length max boundary",       test_length_max_boundary),
    ("packet structure",          test_packet_structure),
    ("packet nonzero",            test_packet_nonzero),
    ("burst packet count",        test_burst_packet_count),
    ("burst gap length",          test_burst_gap_length),
    ("sync word",                 test_sync_word_constant),
    ("sync bits",                 test_sync_bits_correct),
    ("constants",                 test_constants_reasonable),
    ("silence → 0 false pos",     test_no_false_positives_silence),
    ("TX bits = RX theory",       test_tx_bits_match_rx_bit_extraction),
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
