#!/usr/bin/env python3
"""
Packet codec: CRC-32 + FEC encode/decode for the RF link.

Encapsulates payload bytes into a robust packet payload that can survive
the 2-bit truncation inherent to the k=7, rate=1/2 terminated CC encoding.

Packet payload format (before FEC):

    [ length (2 bytes, big-endian) ] [ payload bytes (N) ] [ CRC-32 (4 bytes) ]

  • length = N (number of payload bytes, 0..65535)
  • CRC-32 covers [length][payload_data]
  • Pre-padded with 2 zero bits before FEC encoding for byte alignment

Frame-level structure (in the radio burst):

    [ preamble (24 B) ] [ sync word (4 B) ] [ FEC-encoded payload ]

On the RX side:
  1. Extract MAX_ENCODED_SIZE FEC symbols after sync word
  2. FEC decode
  3. Read first byte as length
  4. Validate length, CRC-32 over [length][payload]
  5. Return payload bytes (addressable by length, not raw decode)

Usage:
    encoded = packet_encode(b"HELLO WORLD\\n")       # → 36 bytes
    payload = packet_decode(encoded)                  # → b"HELLO WORLD\\n"
"""
import zlib
from typing import Optional

from fec_cc import encode_bytes, decode_bytes_hard


def packet_encode(payload: bytes) -> bytes:
    """
    CRC-32 protect + FEC encode a payload, with embedded length byte.

    Format: [len(2, big-endian)] [payload(N)] [CRC-32(4)]

    Args:
        payload: Raw data bytes (any length 0..65535)

    Returns:
        FEC-encoded bytes, always byte-aligned
    """
    data = len(payload).to_bytes(2, 'big') + payload
    crc = zlib.crc32(data) & 0xFFFFFFFF
    data_with_crc = data + crc.to_bytes(4, 'big')
    return encode_bytes(data_with_crc, pad_bits=2)


def packet_decode(encoded: bytes, max_payload: int = 512) -> Optional[bytes]:
    """
    FEC decode + length-byte validation + CRC-32 check.

    The encoded data should be the full FEC output from packet_encode().
    Extra garbage bytes at the end are safe: the Viterbi decoder will
    still produce a plausible output; the length+CRC check catches it.

    Args:
        encoded: FEC-encoded bytes from packet_encode() (or oversized)
        max_payload: Maximum allowed payload length (default 512)

    Returns:
        Original payload bytes if validation passes, None otherwise
    """
    bit_decoded = decode_bytes_hard(encoded, pad_bits=2)
    if len(bit_decoded) < 32:
        return None  # can't have even 4 bytes (len + CRC)

    # Pack bits back to bytes (MSB first)
    packed = bytearray()
    for i in range(0, len(bit_decoded), 8):
        b = 0
        for j in range(8):
            if i + j < len(bit_decoded):
                b |= (bit_decoded[i + j] & 1) << (7 - j)
        packed.append(b)

    total_bytes = len(packed)
    if total_bytes < 6:
        return None  # need at least len(2) + CRC(4)

    payload_len = int.from_bytes(packed[:2], 'big')
    if payload_len > max_payload:
        return None

    # Need: len(2) + payload(N) + crc(4) = payload_len + 6
    if total_bytes < payload_len + 6:
        return None

    # Data covered by CRC = length bytes + payload data
    data = bytes(packed[:2 + payload_len])
    crc_recv = int.from_bytes(packed[2 + payload_len:2 + payload_len + 4], 'big')
    crc_calc = zlib.crc32(data) & 0xFFFFFFFF

    if crc_recv != crc_calc:
        return None

    return bytes(packed[2:2 + payload_len])


def encode_size_for_payload(payload_len: int) -> int:
    """
    How many bytes the FEC encoder will produce for a given payload length.

    Accounts for the +2 length bytes (big-endian) + 4 CRC bytes.

    Args:
        payload_len: Number of payload bytes

    Returns:
        Number of FEC-encoded bytes
    """
    total = 2 + payload_len + 4  # +2 length bytes, +4 CRC
    return (total * 8 + 8) * 2 // 8  # (8*total + 2_pad + 6_term) * 2 / 8


def max_encoded_size_for_payload(max_payload: int = 512) -> int:
    """
    Max FEC-encoded bytes for a receiver to extract.

    This is the outer extraction budget: always extract this many
    FEC symbols after the sync word, and let packet_decode() handle
    the length byte to determine where the real data ends.

    Args:
        max_payload: Maximum expected payload length (default 512)

    Returns:
        Max FEC-encoded bytes to extract
    """
    return encode_size_for_payload(max_payload)


# ── Self-test ──────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys

    test_cases = [
        (b"HELLO WORLD\n",   "12-byte message"),
        (b"test",            "4-byte message"),
        (b"A" * 200,         "200-byte message"),
        (b"",                "empty message"),
        (bytes(range(20)),   "binary 20 bytes"),
    ]

    all_ok = True
    for payload, desc in test_cases:
        enc = packet_encode(payload)
        dec = packet_decode(enc)
        ok = dec == payload
        status = "OK" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  {status}  {desc:<20s}  {len(payload):3d}B → enc={len(enc)}B → dec={len(dec) if dec else 0}B")

    # Test max_payload parameter limits short decode buffer
    payload = b"A" * 200
    enc = packet_encode(payload)
    dec = packet_decode(enc, max_payload=100)
    ok = dec is None
    status = "OK" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  {status}  max_payload=100 rejects 200B  → None")

    # Test oversized encoded data (extra garbage after real FEC)
    payload = b"HELLO WORLD\n"
    enc = packet_encode(payload)
    # Append 50 bytes of noise (simulates extracting max size)
    oversized = enc + bytes([0xAB, 0xCD, 0xEF] * 17)  # 51 bytes of junk
    dec = packet_decode(oversized)
    ok = dec == payload
    status = "OK" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  {status}  oversized decode (extra garbage)  → correct payload")

    # Negative test: corrupt many bits (overwhelm FEC)
    payload = b"HELLO WORLD\n"
    enc = bytearray(packet_encode(payload))
    for i in range(0, len(enc), 3):
        enc[i] ^= 0xFF
    dec = packet_decode(bytes(enc))
    ok = dec is None
    status = "OK" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  {status}  heavy corruption → decode returns None")

    # Size prediction test
    for pl in [0, 4, 12, 20, 100]:
        predicted = encode_size_for_payload(pl)
        actual = len(packet_encode(b"x" * pl))
        match = "OK" if predicted == actual else "FAIL"
        print(f"  {match}  size pred: pl={pl:3d} → {predicted}B (actual {actual}B)")

    # max_encoded_size_for_payload matches encode_size_for_payload(256)
    pl = 256
    predicted = encode_size_for_payload(pl)
    mf = max_encoded_size_for_payload(pl)
    match = "OK" if predicted == mf else "FAIL"
    print(f"  {match}  max_encoded_size_for_payload({pl}) = {mf}B  "
          f"(encode_size = {predicted}B)")

    sys.exit(0 if all_ok else 1)
