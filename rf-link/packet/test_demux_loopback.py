#!/usr/bin/env python3
"""
Definitive loopback test for the header/payload demux.

Tests the new length-byte protocol end-to-end:
  1. Direct codec (encode → decode) with length byte
  2. Oversized decode (extra garbage tolerated)
  3. Corruption → None
  4. max_payload bounds
  5. Size predictions match actual
  6. RF loopback (single packet)
  7. Multi-packet burst
"""
import numpy as np
import sys
sys.path.insert(0, '.')

from packet_codec import (
    packet_encode, packet_decode,
    encode_size_for_payload, max_encoded_size_for_payload,
)
from pkt_enhanced_tx import make_packet_bits, bpsk_modulate
from pkt_enhanced_rx import (
    rcc_taps, scan_frequency, process_phase,
    MAX_FEC_SYMS, SYNC_BITS, PREAMBLE_BITS,
)

FS = 2_000_000
SPS = 20
_MIN_SYM = PREAMBLE_BITS + SYNC_BITS + MAX_FEC_SYMS  # 4416
_MIN_SAMP = int(_MIN_SYM * SPS)                       # 88320
ok = True


def rf_test(payload, fo_hz=100, noise=0.008):
    """TX → channel → RX. FO estimated on unpadded signal; noise-padded afterward."""
    sig = np.array(bpsk_modulate(make_packet_bits(payload)), dtype=np.complex64)
    t_sig = np.arange(len(sig)) / FS
    ch = sig * np.exp(2j * np.pi * fo_hz * t_sig)
    if noise > 0:
        ch += np.random.normal(0, noise, len(sig))
    fo_est = scan_frequency(ch)
    # Noise-pad for RX extraction window (better than zero-padding for FFT)
    if len(sig) < _MIN_SAMP:
        nz = np.random.normal(0, noise, int(_MIN_SAMP - len(sig)))
        ch = np.concatenate([ch, nz + 1j * nz])
    t = np.arange(len(ch)) / FS
    bb = ch * np.exp(-2j * np.pi * fo_est * t)
    filt = np.convolve(bb.real, rcc_taps(), 'same')
    found = set()
    for phase in range(SPS):
        for r in process_phase(filt, phase, fo_est):
            found.add(bytes(r['message']))
    return payload in found


# ══════════════════════════════════════════════════
# 1. Direct codec
# ══════════════════════════════════════════════════
print("=== 1. Direct codec ===")
for p in [b'HELLO WORLD\n', b'test', b'', bytes(range(20)), b'A'*200]:
    enc = packet_encode(p)
    dec = packet_decode(enc)
    ok &= (dec == p)
    print(f"  {'OK' if dec == p else 'FAIL'}  {len(p):3d}B → {len(enc)}B → {len(dec)}B")

# ══════════════════════════════════════════════════
# 2. Oversized decode
# ══════════════════════════════════════════════════
print("\n=== 2. Oversized decode ===")
for p in [b'test', b'HELLO WORLD\n', b'A'*200]:
    enc = packet_encode(p)
    for junk in [10, 50, 200]:
        dec = packet_decode(enc + bytes([junk % 256] * junk))
        ok &= (dec == p)
        print(f"  {'OK' if dec == p else 'FAIL'}  {len(p):3d}B + {junk:3d}B junk")

# ══════════════════════════════════════════════════
# 3. Corruption → None
# ══════════════════════════════════════════════════
print("\n=== 3. Corruption rejection ===")
enc = bytearray(packet_encode(b'test'))
for i in range(0, len(enc), 3): enc[i] ^= 0xFF
result = packet_decode(bytes(enc))
ok &= (result is None)
print(f"  {'OK' if result is None else 'FAIL'}  heavy corruption → {result}")

# ══════════════════════════════════════════════════
# 4. max_payload bounds
# ══════════════════════════════════════════════════
print("\n=== 4. Max payload bounds ===")
result = packet_decode(packet_encode(b'A'*200), max_payload=100)
ok &= (result is None)
print(f"  {'OK' if result is None else 'FAIL'}  max_payload=100 rejects 200B → {result}")

# ══════════════════════════════════════════════════
# 5. Size predictions
# ══════════════════════════════════════════════════
print("\n=== 5. Size predictions ===")
for pl in [0, 4, 12, 100, 255]:
    pred, act = encode_size_for_payload(pl), len(packet_encode(b'x' * pl))
    ok &= (pred == act)
    print(f"  {'OK' if pred == act else 'FAIL'}  pl={pl:3d}: pred={pred}B  act={act}B")

# max_encoded_size = encode_size_for_payload(max)
for mp in [255, 256]:
    print(f"  max_encoded_size_for_payload({mp}) = {max_encoded_size_for_payload(mp)}B")

# ══════════════════════════════════════════════════
# 6. RF loopback (single packet)
# ══════════════════════════════════════════════════
print("\n=== 6. RF loopback ===")
for p, label, fo, nz in [
    (b'HELLO WORLD\n',         "12-char",   100, 0.005),
    (b'HELLO FROM SUBAGENT\n', "20-char",   100, 0.005),
    (b'test',                  "4-byte",    100, 0.005),
    (b'',                      "empty",     100, 0.008),
    (b'A'*200,                 "200-byte",  100, 0.008),
    (b'A'*255,                 "255-byte",  100, 0.008),
]:
    result = rf_test(p, fo, nz)
    ok &= result
    print(f"  {'OK' if result else 'FAIL'}  {label:<15s}  {len(p):3d}B")

# ══════════════════════════════════════════════════
# 7. Multi-packet burst
# ══════════════════════════════════════════════════
print("\n=== 7. Multi-packet burst ===")
packets = [b'FIRST\n', b'SECOND\n', b'THIRD\n']
all_bits = sum((make_packet_bits(p) for p in packets), [])
sig = np.array(bpsk_modulate(all_bits), dtype=np.complex64)

t_sig = np.arange(len(sig)) / FS
ch = sig * np.exp(2j * np.pi * 50 * t_sig)
ch += np.random.normal(0, 0.005, len(sig))
fo_est = scan_frequency(ch)
# Pad with noise
needed = int(len(sig) + _MIN_SAMP)
nz = np.random.normal(0, 0.005, int(needed - len(ch)))
ch = np.concatenate([ch, nz + 1j * nz])

t = np.arange(len(ch)) / FS
bb = ch * np.exp(-2j * np.pi * fo_est * t)
filt = np.convolve(bb.real, rcc_taps(), 'same')

found = set()
# Use top_n=20 to ensure all 3 sync words are tried
for phase in range(SPS):
    for r in process_phase(filt, phase, fo_est, top_n=20):
        found.add(bytes(r['message']))
match = found == set(packets)
ok &= match
print(f"  {'OK' if match else 'FAIL'}  found={sorted(found)}  expected={sorted(packets)}")

# ══════════════════════════════════════════════════
print()
print("═" * 42)
if ok:
    print("ALL TESTS PASSED ✓")
    sys.exit(0)
else:
    print("SOME TESTS FAILED ✗")
    sys.exit(1)
