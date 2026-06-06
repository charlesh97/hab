#!/usr/bin/env python3
"""
Layer 1 — Direct Codec Unit Tests.

Tests packet_codec.py encode/decode round trip with no radio involvement.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from packet_codec import packet_encode, packet_decode, encode_size_for_payload


def test_roundtrip_sizes():
    """Encode → decode for all standard payload sizes."""
    sizes = [0, 1, 4, 12, 20, 50, 100, 200, 255, 511, 512]
    for n in sizes:
        payload = bytes([i % 256 for i in range(n)])
        enc = packet_encode(payload)
        dec = packet_decode(enc)
        assert dec == payload, f"Size {n}: decode mismatch"
    return f"OK  {len(sizes)} sizes (0..512)"


def test_empty():
    """Empty payload boundary case."""
    payload = b''
    enc = packet_encode(payload)
    # 2 len + 0 payload + 4 crc = 6 bytes before FEC
    # (6*8+8)*2//8 = 14 bytes FEC
    assert len(enc) == 14, f"Expected 14B FEC, got {len(enc)}"
    dec = packet_decode(enc)
    assert dec == b'', "Empty decode should match"
    return "OK"


def test_binary_data():
    """All byte values 0x00-0xFF as payload."""
    payload = bytes(range(256))
    enc = packet_encode(payload)
    dec = packet_decode(enc)
    assert dec == payload, "Binary 256B round-trip failed"
    return "OK"


def test_oversized_decode():
    """Extra garbage after FEC data → still extracts correct payload."""
    payload = b'HELLO WORLD\n'
    enc = packet_encode(payload)
    oversized = enc + bytes([0xAB, 0xCD, 0xEF] * 17)
    dec = packet_decode(oversized)
    assert dec == payload, "Oversized decode failed"
    return "OK"


def test_max_payload_rejection():
    """max_payload parameter correctly rejects oversized claims."""
    payload = b'A' * 200
    enc = packet_encode(payload)
    dec = packet_decode(enc, max_payload=100)
    assert dec is None, "Should reject 200B with max_payload=100"
    return "OK"


def test_corruption():
    """Heavy bit corruption → decode returns None."""
    payload = b'HELLO WORLD\n'
    enc = bytearray(packet_encode(payload))
    for i in range(0, len(enc), 3):
        enc[i] ^= 0xFF
    dec = packet_decode(bytes(enc))
    assert dec is None, "Should reject corrupted data"
    return "OK"


def test_size_predictions():
    """encode_size_for_payload matches actual encoded size."""
    for pl in [0, 4, 12, 20, 100, 512]:
        predicted = encode_size_for_payload(pl)
        actual = len(packet_encode(b'x' * pl))
        assert predicted == actual, f"Size pred pl={pl}: {predicted} != {actual}"
    return f"OK  6 sizes matched"


# ── Test registry ────────────────────────────────────────
TESTS = [
    ("round-trip sizes",    test_roundtrip_sizes),
    ("empty payload",       test_empty),
    ("binary 256B",         test_binary_data),
    ("oversized decode",    test_oversized_decode),
    ("max_payload reject",  test_max_payload_rejection),
    ("corruption",          test_corruption),
    ("size predictions",    test_size_predictions),
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
