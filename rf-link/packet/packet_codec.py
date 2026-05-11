#!/usr/bin/env python3
"""
Packet codec: CRC-32 + FEC encode/decode for the RF link.

Encapsulates payload bytes into a robust packet payload that can survive
the 2-bit truncation inherent to the k=7, rate=1/2 terminated CC encoding.

Packet payload format (software layer, to be embedded in the radio framing):

    [ payload bytes (N) ] [ CRC-32 (4 bytes) ] → pad→FEC → 
    → [ FEC-encoded bytes (2*(8*(N+4) + 8) // 8) ]

The 2-bit pre-padding makes the FEC output always byte-aligned, avoiding
the truncation issue documented in debug_packet_rxtx/packet_chain_analysis.md.

Usage:
    encoded = packet_encode(b"HELLO WORLD\\n")       # → 34 bytes
    payload = packet_decode(encoded)                  # → b"HELLO WORLD\\n"
"""
import zlib
from typing import Optional

from fec_cc import encode_bytes, decode_bytes_hard


def packet_encode(payload: bytes) -> bytes:
    """
    CRC-32 protect + FEC encode a payload.

    Args:
        payload: Raw data bytes (any length, including empty)

    Returns:
        FEC-encoded bytes, always byte-aligned
    """
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    data_with_crc = payload + crc.to_bytes(4, 'big')
    return encode_bytes(data_with_crc, pad_bits=2)


def packet_decode(encoded: bytes) -> Optional[bytes]:
    """
    FEC decode + CRC-32 validate.

    Args:
        encoded: FEC-encoded bytes from packet_encode()

    Returns:
        Original payload bytes if CRC validates, None otherwise
    """
    bit_decoded = decode_bytes_hard(encoded, pad_bits=2)
    if len(bit_decoded) < 32:
        return None  # can't have even 4 bytes
    
    # Pack bits back to bytes (MSB first)
    packed = bytearray()
    for i in range(0, len(bit_decoded), 8):
        b = 0
        for j in range(8):
            if i + j < len(bit_decoded):
                b |= (bit_decoded[i + j] & 1) << (7 - j)
        packed.append(b)
    
    if len(packed) < 4:
        return None
    
    data = bytes(packed[:-4])
    crc_recv = int.from_bytes(packed[-4:], 'big')
    crc_calc = zlib.crc32(data) & 0xFFFFFFFF
    
    if crc_recv != crc_calc:
        return None
    
    return data


def encode_size_for_payload(payload_len: int) -> int:
    """
    How many bytes the FEC encoder will produce for a given payload length.

    Args:
        payload_len: Number of payload bytes (before CRC)

    Returns:
        Number of FEC-encoded bytes
    """
    total = payload_len + 4  # +4 CRC
    return (total * 8 + 8) * 2 // 8  # (8*total + 2_pad + 6_term) * 2 / 8


# ── Self-test ──────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys

    test_cases = [
        (b"HELLO WORLD\n",   "12-byte message"),
        (b"test",            "4-byte message"),
        (b"A" * 100,         "100-byte message"),
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

    # Negative test: corrupt many bits (overwhelm FEC)
    payload = b"HELLO WORLD\n"
    enc = bytearray(packet_encode(payload))
    # Flip ~30% of bytes aggressively
    for i in range(0, len(enc), 3):
        enc[i] ^= 0xFF
    dec = packet_decode(bytes(enc))
    print(f"  {'OK' if dec is None else 'FAIL'}  heavy corruption → decode returns None")

    # Size prediction test
    for pl in [0, 4, 12, 20, 100]:
        predicted = encode_size_for_payload(pl)
        actual = len(packet_encode(b"x" * pl))
        match = "OK" if predicted == actual else "FAIL"
        print(f"  {match}  size pred: pl={pl:3d} → {predicted}B (actual {actual}B)")

    sys.exit(0 if all_ok else 1)
