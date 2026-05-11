# RF Link — Test Pipeline

Every change to the packet chain must pass all three test layers before
being considered complete.  Run the full suite with:

```bash
cd rf-link/packet/test
./test_all.py          # all layers
./test_all.py --layer 1   # layer 1 only
./test_all.py --layer 2   # layer 2 only
./test_all.py --layer 3   # layer 3 only (needs HackRF hardware)
```

## Layer 1 — Direct Codec Unit Tests

Tests `packet_codec.py` directly (encode → decode round trip) with no radio
involved.  Runs in milliseconds.

**What it checks:**
- Round-trip encode/decode for payload sizes 0, 1, 4, 12, 20, 50, 100, 200,
  255, 511, 512 bytes
- Empty payload (boundary case)
- Binary data (all byte values 0x00-0xFF)
- Oversized decode: appending junk after FEC data → still extracts correct payload
- `max_payload` rejection: 200B packet with `max_payload=100` → returns None
- Heavy corruption: flipping 30% of FEC bytes → returns None
- Size predictions match actual encoded sizes

**Fails when:** Codec has a bug (CRC, padding, FEC mismatch).

## Layer 2 — RF Software Loopback

Tests the full TX→RX chain entirely in software (no radio hardware).
Runs in seconds.

**What it checks:**
- Generate a packet via `pkt_enhanced_tx.make_packet_bits()`
- BPSK modulate at current SPS
- Save as int8 interleaved IQ (same format HackRF produces)
- Load back through `pkt_enhanced_rx` pipeline:
  - DC removal → FO scan (spectral centroid) → mix down
  - RRC matched filter → decimate at all SPS phases
  - Sync-word correlation (top 5 peaks)
  - Extract payload symbols → hard-decision → packet_decode()
- Verify decoded payload matches original
- Repeats for payload sizes: 0, 12, 200, 255, 511 bytes
- Multi-packet burst test: 5 packets with 20ms gaps, verify all decode
- Oversized capture test: packet buried in zeros (simulates long recording)

**Fails when:** TX/RX pipeline mismatch, RRC filter issues, sync detection
broken, FO estimator broken, SPS inconsistency.

## Layer 3 — Hardware Cable Test

Tests over real hardware: HackRF TX → SMA cable → HackRF RX.
Requires two HackRF Ones (or one with loopback).  Runs in real time.

**What it checks:**
- Two terminals: one runs TX, one runs RX
- TX sends N packets with known payload
- RX captures for D seconds, counts successful decodes
- At low power settings, the FEC should correct occasional bit errors
- Reports packet count, decode rate, and signal quality indicators

**Skipped when:** No HackRF hardware detected.

## Adding New Tests

1. Write the test function in the relevant layer module
2. Add it to the `tests` list at the bottom of that module
3. The harness auto-discovers and runs all test functions

## CI / Pre-Commit

```bash
cd rf-link/packet && ./test/test_all.py --layer 1 --layer 2
```

Layer 1+2 pass in < 30 seconds with no hardware.  Layer 3 is manual
(hardware setup).
