# RF Packet Transmission & Reception — Detailed System Guide

**Author:** Codex  
**Date:** 2026-05-16  
**Project:** `/hab/rf-link/packet/`  
**Audience:** Charles Hood (you, debugging at 2am during a balloon launch)

---

## Table of Contents

1. [Why This System Exists](#1-why-this-system-exists)
2. [Data Pipeline — End to End](#2-data-pipeline--end-to-end)
3. [Packet Structure (ASCII Art)](#3-packet-structure)
4. [Frequency Offset (FO) — The Trickiest Part](#4-frequency-offset-fo--the-trickiest-part)
5. [AGC — Digital Gain Control](#5-agc--digital-gain-control)
6. [Variable SPS / Symbol Rate](#6-variable-sps--symbol-rate)
7. [Test Architecture — The Three Layers](#7-test-architecture--the-three-layers)
8. [Hardware Setup](#8-hardware-setup)
9. [How to Run Everything](#9-how-to-run-everything)
10. [Known Issues / Future Work](#10-known-issues--future-work)

---

## 1. Why This System Exists

### The Problem

Off-the-shelf radios (XBee, LoRa, etc.) can't push data reliably over 18 km from a high-altitude balloon (HAB). At that range, you need about 20 dB more link margin than consumer modules provide.

### The Solution

A custom BPSK (binary phase-shift keying) packet link built entirely in software:

- **Hardware**: Two HackRF Ones (software-defined radios, ~$300 each)
- **Software**: GNU Radio + Python + SoapySDR
- **Modulation**: BPSK at 915 MHz (ISM band)
- **FEC**: Convolutional code (k=7, rate=1/2) for forward error correction
- **CRC-32**: Detects any residual errors after FEC
- **Variable symbol rate**: Trade data rate for link margin on the fly

### Key Numbers

| Parameter | Default | At 18 km |
|-----------|---------|----------|
| TX Power | +10 dBm (10 mW) | Same |
| Frequency | 915 MHz | Same |
| Symbol rate | 100 ksym/s | 10–50 ksym/s |
| Bandwidth | ~135 kHz (BPSK @ 100k) | ~14 kHz (BPSK @ 10k) |
| Link margin | ~11 dB (SPS=20) | ~21 dB (SPS=200) |
| Data rate (net) | ~60 kbps | ~6 kbps |

---

## 2. Data Pipeline — End to End

### TX Side — Payload Bytes to Radio

```
┌──────────┐   "HELLO WORLD\n"
│  payload │   (12 bytes ASCII)
└────┬─────┘
     │
     ▼
┌──────────────────────────────────────────────────────┐
│ packet_encode()                   (packet_codec.py)  │
│                                                      │
│  1. Prepend 2-byte length (big-endian):             │
│     [0x00] [0x0C]                                    │
│                                                      │
│  2. Append CRC-32 (zlib.crc32 covering length+pld): │
│     [len(2)] [payload(N)] [crc32(4)]                 │
│     → "raw" bytes = 2 + 12 + 4 = 18 bytes           │
│                                                      │
│  3. Pre-pad 2 zero bits for byte alignment           │
│                                                      │
│  4. FEC encode: fec_cc.encode_bytes()                │
│     k=7, rate=1/2, terminated                        │
│     (18×8 + 2pad + 6term) × 2 = 304 bits = 38 bytes │
└────┬─────────────────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────────────────────┐
│ make_packet_bits()               (pkt_enhanced_tx.py) │
│                                                      │
│  Assemble the frame:                                 │
│  [ preamble: 24 bytes = 192 bits ]                   │
│  [ sync word: 4 bytes = 32 bits  ]                   │
│  [ FEC payload: 38 bytes = 304 bits ]                │
│                                                      │
│  Total: 528 bits per packet                          │
└────┬─────────────────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────────────────────┐
│ bpsk_modulate()                 (pkt_enhanced_tx.py) │
│                                                      │
│  1. Map bits: 0→+1.0, 1→-1.0  (BPSK symbols)        │
│  2. Upsample × SPS (insert zeros between symbols)   │
│  3. RRC pulse shape (α=0.35, length=11·SPS taps)    │
│  4. Normalize peak to 0.7 (headroom for HackRF DAC) │
│     → complex64 waveform at FS samples/sec           │
└────┬─────────────────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────────────────────┐
│ apply_burst_shaping()            (pkt_enhanced_tx.py) │
│                                                      │
│  Hann window ramp at start and end of waveform.      │
│  Prevents spectral splatter from hard amplitude      │
│  transitions when TX amplifier powers on/off.        │
│  Ramp length: 50 symbols = 50·SPS samples            │
└────┬─────────────────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────────────────────┐
│ GNU Radio flowgraph                                  │
│                                                      │
│  vector_source_c → throttle → soapy_sink             │
│                                                      │
│  SoapySDR driver → HackRF One → antenna              │
└──────────────────────────────────────────────────────┘
```

**Mathematical detail of BPSK modulation:**

1. Each bit (0 or 1) maps to one symbol: `symbol = -2·bit + 1` → `{0: +1, 1: -1}`
2. Symbols are upsampled by SPS: put each symbol at position `[0, SPS, 2·SPS, ...]` with zeros in between
3. Convolve with RRC filter taps (generated by `firdes.root_raised_cosine(gain=1, sps, 1.0, alpha, ntaps·sps)`)
4. Peak normalize to 0.7 (avoids clipping the HackRF DAC which has limited headroom at 8-bit)

### RX Side — Radio to Decoded Message

```
┌────────────────────┐
│  HackRF One        │
│  SoapySDR source   │
│  @ 915 MHz, FS     │
│  Gain: LNA / VGA   │
│  → raw CF32 samples│
└────────┬───────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ 1. DC Block                                           │
│    samples = samples - mean(samples)                  │
│    Removes DC offset from direct conversion SDR       │
└────────┬──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ 2. FO Estimation                                      │
│                                                      │
│    scan_frequency(samples):                          │
│    ┌─────────────────────────────────────┐           │
│    │ a. Find high-energy segment         │           │
│    │    (max energy over 65536-sample    │           │
│    │     sliding window)                 │           │
│    │                                      │           │
│    │ b. RRC filter the segment           │           │
│    │                                      │           │
│    │ c. Try 4 evenly-spaced decimation   │           │
│    │    phases (for speed)               │           │
│    │                                      │           │
│    │ d. For each FO candidate (±20 kHz   │           │
│    │    in 500 Hz steps):                │           │
│    │    • Rotate samples by -FO           │           │
│    │    • Correlate with sync word        │           │
│    │    • Track max correlation           │           │
│    │                                      │           │
│    │ e. If corr < threshold: fall back   │           │
│    │    to spectral centroid (FFT)       │           │
│    └─────────────────────────────────────┘           │
│                                                      │
│    Returns: FO estimate in Hz (e.g. -6500)           │
└────────┬──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ 3. Digital AGC                                        │
│                                                      │
│    apply_digital_agc(samples, target_rms=0.3):       │
│                                                      │
│    rms = sqrt(mean(|samples|²))                      │
│    gain = 0.3 / rms                                  │
│    samples = samples · gain                          │
│                                                      │
│    Normalizes signal to consistent amplitude for      │
│    correlation threshold and hard decisions.          │
│    Dead chunk (rms < 1e-3) → return zeros.           │
└────────┬──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ 4. Mix to Baseband                                    │
│                                                      │
│    t = [0, 1, 2, ..., len(samples)-1] / FS           │
│    bb = samples · exp(-j · 2π · FO · t)              │
│                                                      │
│    Rotates the received signal down to 0 Hz,          │
│    removing the bulk carrier offset.                  │
└────────┬──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ 5. RRC Matched Filter                                 │
│                                                      │
│    Same RRC taps as TX (α=0.35, 11·SPS). Convolve    │
│    with baseband signal. Matched filter maximizes     │
│    SNR at symbol-spaced sampling instants.            │
└────────┬──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ 6. Decimate × SPS (try multiple phases)              │
│                                                      │
│    For phase in range(0, min(SPS, 20)):              │
│      symbols = filtered[phase :: SPS]                │
│                                                      │
│    Each decimation phase captures a different         │
│    sample offset. At least one phase aligns with     │
│    the correct symbol boundary.                      │
│    Limited to 20 phases for performance.             │
│    Phase indices are evenly spaced:                  │
│      linspace(0, SPS-1, min(SPS, 20), dtype=int)    │
└────────┬──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ 7. Sync-Word Correlation                              │
│                                                      │
│    SYNC_WORD = 0xACDDA4E2 (32 bits)                  │
│    SYNC_BPSK = [bit→symbol mapping]                  │
│                                                      │
│    corr = |correlate(symbols, SYNC_BPSK, 'valid')|   │
│    threshold = mean(corr) + 2.5 · std(corr)          │
│    Find local peaks above threshold                  │
│    Sort by strength, try top 5                       │
│    (Higher N found sync; CRC filters false alarms)   │
└────────┬──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ 8. FO Refinement (per-packet)                        │
│                                                      │
│    a. Extract 32 sync symbols at peak position       │
│    b. Remove BPSK modulation:                        │
│       demod = sync_syms · expected_syms              │
│    c. Unwrap phase: φ = angle(demod)                 │
│    d. Fit line: slope = dθ/dsymbol                   │
│    e. dFO = slope · symbol_rate / (2π)               │
│                                                      │
│    This corrects the residual FO left after the       │
│    coarse scan_frequency (±250-500 Hz resolution).   │
│    Without this, phase would rotate 4.5 radians      │
│    across a 288-symbol packet at 100 ksym/s.         │
└────────┬──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ 9. Phase Correction on Payload                        │
│                                                      │
│    correction = exp(-j · 2π · dFO · k / symbol_rate) │
│    payload_corrected = payload_syms · correction      │
│                                                      │
│    Applies the refined FO correction to every        │
│    payload symbol before making hard decisions.      │
└────────┬──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ 10. Hard Decisions → Bits                             │
│                                                      │
│    Try both polarities (180° ambiguity):             │
│    • Normal: bit = 1 if real < 0, else 0             │
│    • Inverted: same but negate first                 │
│                                                      │
│    Pack bits MSB-first to bytes:                     │
│    for i in range(0, nbits, 8):                     │
│      byte = bits[i]<<7 | bits[i+1]<<6 | ...          │
└────────┬──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ 11. packet_decode()                (packet_codec.py)  │
│                                                      │
│    1. fec_cc.decode_bytes_hard()  (Viterbi decode)   │
│       → recovers original bit stream                 │
│    2. Strip 2 pre-padding bits, 6 termination bits   │
│    3. Pack bits to bytes                              │
│    4. Read first 2 bytes = payload length (big-end)  │
│    5. Validate length ≤ max_payload (512)            │
│    6. Read payload_length bytes                      │
│    7. Read next 4 bytes = received CRC-32            │
│    8. Compute CRC-32 over [length(2) + payload]      │
│    9. If match → return payload bytes                │
│       If mismatch → return None (CRC fail)           │
└────────┬──────────────────────────────────────────────┘
         │
         ▼
    "HELLO WORLD\n"
    (or None if CRC failed)
```

---

## 3. Packet Structure

### Air Interface Layout

```
 Byte 0                                  Byte 27                    Variable length (~14-1038 B)
├────────────────────────────────────┬──────────────┬────────────────────────────────────────┤
│          Preamble (24 B)           │  Sync Word   │         FEC-Protected Payload          │
│                                    │   (4 B)      │                                        │
└────────────────────────────────────┴──────────────┴────────────────────────────────────────┘

 ├── 192 bits ──┤├── 32 bits ──┤├─────────────────── N ≈ 112..8304 bits ─────────────────────┤
```

### Bit-Level Detail

**Preamble** (24 bytes = 192 bits):

```
Hex:  0xE3 8F C0 FC 7F C7 E3 81 C0 FF 80 38 FF F0 38 E0 0F C0 03 80 00 FF FF C0
Bin:  11100011 10001111 11000000 11111100 01111111 11000111 11100011 10000001
      11000000 11111111 10000000 00111000 11111111 11110000 00111000 11100000
      00001111 11000000 00000011 10000000 00000000 11111111 11111111 11000000
```

This preamble produces a strong correlation peak against itself but has very low
cross-correlation with random data. It was taken from the original working
GNU Radio flowgraph (`packet_rx.py`).

**Sync Word** (4 bytes = 32 bits):

```
Hex:  0xAC DDA4 E2
Bin:  10101100 11011101 10100100 11100010
```

The sync word is **deliberately different** from the first 4 bytes of the preamble
(preamble starts with `0xE3 8F C0 FC`). This means:
- The preamble creates a flat correlation floor (no strong peaks within itself)
- The sync word creates one sharp, unambiguous correlation peak
- Result: exact packet boundary, no false positives

### Payload Internals (before FEC encoding)

```
┌──────────────────┬────────────────────────────┬────────────────────┐
│  Length (2 B)    │   Payload Data (N B)       │   CRC-32 (4 B)    │
│  big-endian N    │   actual message content   │   zlib.crc32 of   │
│                   │                            │   [len][payload]  │
└──────────────────┴────────────────────────────┴────────────────────┘

Example for "HELLO WORLD\n" (12 bytes):
┌──────────┬──────────────┬──────────────────────────────┐
│ 0x00 0x0C│ H E L L O   W O R L D \n   │ 0x12 0x34 ... │
│  len=12  │        12 bytes               │   CRC-32     │
└──────────┴──────────────┴──────────────────────────────┘
```

### FEC Encoding Details

```
Raw before FEC:  18 bytes (2 len + 12 payload + 4 CRC) = 144 bits
Pre-padding:     +2 zero bits = 146 bits
Termination:     +6 zero bits = 152 bits
FEC encoded:     152 × 2 = 304 bits = 38 bytes
```

The 2-bit pre-padding is critical: it ensures the FEC output is byte-aligned.
The k=7 convolutional encoder produces 2 bits per input bit, but the
termination + padding makes `(144 + 8) × 2 = 304` bits = exactly 38 bytes.

### Packet Duration

| SPS | Sym/s | 12B Payload | Empty Payload |
|-----|-------|-------------|---------------|
| 20  | 100k  | 5.28 ms     | 2.38 ms       |
| 100 | 20k   | 26.4 ms     | 12.0 ms       |
| 200 | 10k   | 52.8 ms     | 24.0 ms       |

---

## 4. Frequency Offset (FO) — The Trickiest Part

### Why FO Happens

Every radio has a crystal oscillator that sets the center frequency. These crystals
are rated in parts per million (ppm):

```
Typical HackRF crystal: ±20 ppm
At 915 MHz: ±20 × 915 = ±18,300 Hz
```

Even a cheap TCXO (±2 ppm) gives ±1,830 Hz. For the two HackRFs connected by SMA cable,
the measured FO is approximately **-6,500 to -7,000 Hz** (one crystal runs fast, the other slow).

At the target 18 km link, the TX balloon payload uses a temperature-compensated
oscillator but the ground RX uses a standard HackRF crystal. Expect FO anywhere
in the ±10-20 kHz range, plus thermal drift over a multi-hour flight.

### Why FO Kills Demodulation

BPSK expects the constellation to be aligned with the real axis:

```
    Ideal:                     With 500 Hz FO @ 100k sym/s:
    
       Q                          Q
       |                          |
    ---+---→ I                ---+---→ I
       |                          | \
       |                          |  \  (spirals over time)
```

The received signal is `s(t) · exp(j·2π·FO·t)`. The FO causes the constellation
to rotate at `FO` Hz. Over 8304 symbols (max payload), 250 Hz residual FO produces
~4.5 radians of rotation — enough to flip bits from 0 to 1 and 1 to 0.

### Step 1: Coarse FO Estimation (`scan_frequency()`)

```
Input: raw CF32 samples (no AGC, no filtering)
Output: FO estimate in Hz (resolution ±250-500 Hz)

Algorithm:
  1. Find high-energy ~131k-sample segment
     (sliding window of 65536 samples, pick max energy)
  2. RRC filter the segment
  3. Try 4 evenly-spaced decimation phases
  4. For each FO candidate (step size = 500 Hz):
     a. Rotate by candidate FO: x[n]·exp(-j·2π·FO·n/FS)
     b. Correlate with sync word (BPSK symbols)
     c. Track max correlation
  5. Pick FO candidate with strongest correlation peak
  6. If max correlation < threshold:
     Fall back to spectral centroid (256k-pt FFT, find peak)
```

**Why this is on raw (pre-AGC) samples:** The scan depends on energy variance
to find the high-energy segment. AGC would normalize the noise floor to the same
level as the signal, making energy detection impossible.

**Search range:** ±20 kHz for initial acquisition, ±5 kHz for re-scan after lock.

### Step 2: FO Refinement (`refine_fo_from_sync()`)

After finding the sync word, we use the 32 known symbols to measure the exact
residual rotation:

```python
sync_syms = symbols[idx : idx + 32]          # extracted BPSK symbols
demod = sync_syms * expected_syms             # remove modulation: exp(j·φ)
phases = np.unwrap(np.angle(demod))           # unwrap phase
t = [0, 1, 2, ..., 31]                       # symbol indices
slope, _ = np.polyfit(t, phases, 1)          # fit line: dθ/ds
dFO = slope * symbol_rate / (2π)             # convert to Hz
```

The unwrap is safe for symbol rates ≥ 5 ksym/s because adjacent symbol phase
differences stay well below π radians.

### Step 3: Apply Correction

```python
k = range(len(payload_syms))
correction = exp(-j · 2π · dFO · k / symbol_rate)
payload_corrected = payload_syms · correction
```

### Continuous FO Tracking State Machine

The receiver doesn't just estimate FO once — it tracks it over time:

```
   [START] → scan_frequency(full ±20 kHz)
       │
       ▼
   [ACQUIRED] → use last FO estimate for next chunk
       │
       ├── decode success → update moving average (median of last 5)
       │                    reset empty counter
       │
       └── N empty chunks → [RE-SCAN] narrow ±5 kHz around last FO
                                    │
                                    └── lock new FO → [ACQUIRED]
                                        │
                                        └── still no decode → [START]
```

Key parameters:
- `_FO_HISTORY_WINDOW = 5` — median filter window size
- `_FO_EMPTY_THRESHOLD = 3` — consecutive empty chunks before re-scan
- `_FO_LOCK_MIN_CORR = 0.3` — minimum correlation to stay locked

---

## 5. AGC — Digital Gain Control

### Why It's Needed

HackRF raw signals vary enormously:

| Scenario | Typical Magnitude | Condition |
|----------|-------------------|-----------|
| No signal (noise floor) | 0.005-0.01 | Antenna disconnected |
| Cable test (direct SMA) | 0.5-2.0 | 2 HackRFs, LNA=8, VGA=12 |
| Outdoor 18 km link | 0.01-0.5 | After path loss |
| Saturated | > 2.0 | Gain too high + strong signal |

That's a range of 40+ dB. Without AGC, the sync-word correlation threshold
(`mean + 2.5·σ`) and hard-decision thresholds have no consistent meaning.

### The Chicken-and-Egg Problem

```
AGC before FO estimation? → AGC amplifies noise, KILLS energy detection
AGC after FO estimation?  → Correct, but means processing noise chunks
```

**Current solution:**

```
1. Energy detect on raw samples (simple max check)
2. FO estimate on raw samples (preserves energy variance)
3. DC block on raw samples
4. Apply AGC to normalize signal for demodulation
5. Mix down, filter, correlate, decode
```

### Implementation

```python
def apply_digital_agc(samples, target_rms=0.3, min_rms=1e-3):
    rms = np.sqrt(np.mean(np.abs(samples) ** 2))
    if rms < min_rms:
        return samples * 0.0  # silence below noise floor
    gain = target_rms / rms
    return samples * gain
```

**AGC target RMS = 0.3** (configurable via `--agc-target`). This is a good
level: large enough for reliable hard decisions, small enough to avoid
numerical overflow in the correlation computation.

---

## 6. Variable SPS / Symbol Rate

### What SPS Means

**SPS = Samples Per Symbol**. With a fixed sample rate `FS`:

```
Symbol Rate (sym/s) = FS / SPS

FS = 2,000,000 samples/second (2 MS/s)
SPS = 20 → Symbol rate = 100,000 sym/s (100 ksym/s)
SPS = 200 → Symbol rate = 10,000 sym/s (10 ksym/s)
SPS = 400 → Symbol rate = 5,000 sym/s (5 ksym/s)
```

### Why It Matters for Link Margin

Lower symbol rate = more energy per symbol = more processing gain:

| SPS | Symbol Rate | Processing Gain vs SPS=20 | Link Margin @ 18 km |
|-----|-------------|---------------------------|---------------------|
| 20  | 100 ksym/s  | 0 dB (baseline)           | ~11 dB              |
| 40  | 50 ksym/s   | +3 dB                     | ~14 dB              |
| 100 | 20 ksym/s   | +7 dB                     | ~18 dB              |
| 200 | 10 ksym/s   | +10 dB                    | ~21 dB              |
| 400 | 5 ksym/s    | +13 dB                    | ~24 dB              |

**Tradeoff:** More link margin = fewer bits per second.

```
Payload "HELLO WORLD\n" (12 bytes):
SPS=20  → packet duration = 5.28 ms  → ~200 pkts/sec  → ~2,000 bytes/sec
SPS=200 → packet duration = 52.8 ms  → ~20 pkts/sec   → ~200 bytes/sec
```

### Implementation

**TX:** `--sps` parameter controls upsampling factor before RRC pulse shaping.
The RRC filter taps recalculate with the new SPS value.

**RX:** `--sps` parameter controls:
1. Decimation spacing: `symbols = filtered[phase :: SPS]`
2. RRC matched filter tap count: `firdes.root_raised_cosine(..., sps, ...)`
3. Number of phases to try: `min(SPS, 20)` — performance cap
4. Symbol rate used for FO refinement: `FS / SPS`

### The Phase Problem

At SPS=20, trying all 20 decimation phases costs 20× the correlation processing.
At SPS=200, trying all 200 phases would cost 200× — infeasible for real-time.

**Fix:** Try `min(SPS, 20)` evenly-spaced phases using `np.linspace(0, SPS-1, min(SPS, 20))`.
With SPS=200, try phases [0, 10, 20, ..., 190]. The packet dedup system
(`position_tolerance = 10`) groups nearby phases detecting the same packet.

---

## 7. Test Architecture — The Three Layers

The test pyramid isolates failures by scope:

```
         ╱╲
        ╱  ╲
       ╱ L3 ╲   Hardware cable test (two HackRFs, real RF)
      ╱──────╲
     ╱  L2    ╲  Software loopback (TX→IQ→RX, all Python)
    ╱──────────╲
   ╱    L1      ╲ Direct codec round-trip (no modulation)
  ╱──────────────╲
```

### Layer 1 — Direct Codec (test_layer1.py)

**What it tests:** `packet_codec.py` + `fec_cc.py` encode/decode, no radio, no modulation.

**Test cases:**
- Round-trip for sizes 0, 1, 4, 12, 20, 50, 100, 200, 255, 511, 512 bytes
- Empty payload (boundary case)
- Binary data (all 256 byte values)
- Oversized capture (extra garbage after FEC data → still decodes correctly)
- Max payload rejection (200B payload rejected with max_payload=100)
- Heavy corruption (every 3rd byte inverted → decode returns None)
- Size predictions match actual encoded size

**Run:**
```bash
cd packet/test
python3 test_layer1.py
```

**Expected output:** All tests pass ✓, no radio needed.

### Layer 2 — Software Loopback (test_layer2.py)

**What it tests:** Full TX→RX pipeline in software. Generates bits → BPSK modulate → save as
int8 IQ → load → FO scan → RRC filter → decimate → sync correlate → extract → decode.

**Test cases:**
- Single packet decode
- Multiple payload sizes (0, 12, 200, 255, 511)
- Multi-packet burst (5 packets, verify at least 3 decode)
- Packet in zeros (simulates long recording)
- FO estimator returns ~0 for clean software signal
- **SPS variants:** 4, 20, 50, 100 with various payload sizes
- **Burst shaping:** shaped vs unshaped both decode identically
- **AGC:** recovers 0.05x scaled signal and 0.01x extreme
- **FO injection:** +5 kHz and -8 kHz injected offsets, verify tracking
- **Backward compatibility:** SPS=20 still works

**Run:**
```bash
cd packet/test
python3 test_layer2.py
```

**Expected output:** All 13 tests pass ✓, no radio needed.

### Layer 3 — Hardware Cable Test (test_layer3.py)

**What it tests:** Two HackRF Ones connected by SMA cable. TX sends packets, RX
receives and decodes. Uses subprocesses (not threads) to avoid SoapySDR resource
conflicts.

**Prerequisites:**
- Two HackRF Ones with SMA cable
- Known serial numbers (auto-detected by version string)
- v2.0.1 = TX, 2024.02.1 = RX

**Run (auto mode):**
```bash
cd packet/test
python3 test_layer3.py --duration 15 --n-packets 20
```

**Run (two terminals):**
```bash
# Terminal 1 (TX):
python3 test_layer3.py --tx --freq 915e6 --vga 40 --message "HELLO FROM TERMINAL" --n-packets 50

# Terminal 2 (RX):
python3 test_layer3.py --rx --freq 915e6 --lna 16 --vga 20 --duration 30 --amp
```

---

## 8. Hardware Setup

### Two-Terminal Workflow

The TX and RX **must run in separate terminals** (or on separate machines).
This is non-negotiable: SoapySDR/HackRF drivers are not thread-safe for
two concurrent device accesses from the same process.

### Cable Test Setup

```
┌─────────────────┐         SMA Cable         ┌─────────────────┐
│  HackRF #1 (TX) │ ─────── 10-20 cm ──────→  │  HackRF #0 (RX) │
│  serial: 74640f │                            │  serial: 6610f  │
│  fw: v2.0.1     │                            │  fw: 2024.02.1  │
└─────────────────┘                            └─────────────────┘
```

### Gain Settings

| Parameter | TX | RX |
|-----------|-----|-----|
| Frequency | 915 MHz | 915 MHz |
| LNA gain | N/A | 16 dB |
| VGA gain | 40 dB | 20 dB |
| AMP | OFF | ON |
| Sample rate | 2 MS/s | 2 MS/s |

**Why these settings?**

- **TX VGA=40, AMP=off:** Moderate output power (~-10 dBm) avoids overloading the
  RX front-end through the short cable. Higher VGA causes RX saturation.
- **RX LNA=16, VGA=20, AMP=on:** The LNA + VGA provide ~36 dB of gain. The AMP
  (built-in RF amplifier, ~14 dB) ensures the signal is strong enough for the
  HackRF's 8-bit ADC to digitize it properly.
- **Cable loss at 915 MHz:** ~0.5-1 dB for a 20 cm SMA cable — negligible.

### Crystal Offset

The two HackRFs have different crystal tolerances:

```
Measured FO: approximately -6,500 to -7,000 Hz
```

This means TX is running ~7 kHz above 915 MHz when the RX is right on frequency,
or vice versa. The `scan_frequency()` function easily catches this in the ±20 kHz
search window.

### Variable SPS / Symbol Rate Tests

```bash
# Terminal 1 — TX at SPS=40 (50 ksym/s):
python3 pkt_enhanced_tx.py --freq 915e6 --sps 40 --vga 40 --message "SLOWER"

# Terminal 2 — RX at SPS=40:
python3 pkt_enhanced_rx.py --freq 915e6 --sps 40 --lna 16 --vga 20 --amp --duration 30
```

Both sides MUST use the same SPS. The TX and RX RRC filters are matched
only when SPS is identical.

---

## 9. How to Run Everything

### Quick Reference

#### L1 Tests (codec only, no radio)

```bash
cd ~/Documents/git/hab/rf-link/packet/test
python3 test_layer1.py
```

#### L2 Tests (software loopback, no radio)

```bash
cd ~/Documents/git/hab/rf-link/packet/test
python3 test_layer2.py
```

#### L3 Hardware Cable Test (auto mode)

```bash
cd ~/Documents/git/hab/rf-link/packet/test
python3 test_layer3.py --duration 30 --n-packets 20
```

#### Manual TX/RX (two terminals)

**Terminal 1 — Transmitter:**
```bash
cd ~/Documents/git/hab/rf-link/packet/src
python3 pkt_enhanced_tx.py \
    --freq 915e6 \
    --samp-rate 2e6 \
    --sps 20 \
    --vga 40 \
    --amp \
    --message "HELLO WORLD" \
    --n-packets 100 \
    --repeat 2.0
```

**Terminal 2 — Receiver:**
```bash
cd ~/Documents/git/hab/rf-link/packet/src
python3 pkt_enhanced_rx.py \
    --freq 915e6 \
    --samp-rate 2e6 \
    --sps 20 \
    --lna 16 \
    --vga 20 \
    --amp \
    --duration 30 \
    --agc-target 0.3
```

#### Variable Symbol Rate (10× slower = 10 dB more margin)

```bash
# TX at SPS=200 (10 ksym/s, ~21 dB margin):
python3 pkt_enhanced_tx.py --freq 915e6 --sps 200 --vga 40 --message "DEEEEEEP"

# RX at SPS=200:
python3 pkt_enhanced_rx.py --freq 915e6 --sps 200 --lna 16 --vga 20 --amp --duration 60
```

#### Offline Decode (replay recorded IQ file)

```bash
python3 pkt_enhanced_rx.py --file captured.iq --sps 20 --samp-rate 2e6
```

The IQ file should be raw int16 interleaved (I0 Q0 I1 Q1 I2 Q2 ...), as produced
by GNU Radio's `File Sink`.

---

### All CLI Options

#### TX (`pkt_enhanced_tx.py`)

| Option | Default | Description |
|--------|---------|-------------|
| `--freq` | 915e6 | Center frequency (Hz) |
| `--samp-rate` | 2e6 | Sample rate (Hz) |
| `--sps` | 20 | Samples per symbol |
| `--vga` | 30 | TX VGA gain (0-47) |
| `--amp` | False | Enable TX amplifier |
| `--serial` | None | HackRF serial number |
| `--repeat` | 2.0 | Time between burst repeats (sec) |
| `--message` | "HELLO WORLD" | Payload text |
| `--n-packets` | 20 | Packets per burst |

#### RX (`pkt_enhanced_rx.py`)

| Option | Default | Description |
|--------|---------|-------------|
| `--freq` | 915e6 | Center frequency (Hz) |
| `--samp-rate` | 2e6 | Sample rate (Hz) |
| `--sps` | 20 | Samples per symbol |
| `--lna` | 8 | RX LNA gain (0-40) |
| `--vga` | 12 | RX VGA gain (0-62) |
| `--amp` | False | Enable RX amplifier |
| `--serial` | None | HackRF serial number |
| `--duration` | 30 | Capture duration (sec) |
| `--file` | None | Offline decode from IQ file |
| `--agc-target` | 0.3 | Digital AGC target RMS |

---

## 10. Known Issues / Future Work

### 🔴 High Priority

#### Correlation Threshold Blocks Weak Signals

**File:** `src/pkt_enhanced_rx.py`, `scan_frequency()` line ~140

The absolute correlation threshold `best_corr < 100` is amplitude-dependent.
For weak signals (< 0.4 CF32 amplitude), this threshold is never reached, and
the centroid FFT fallback always runs.

| CF32 Amplitude | Correlation Peak | Above 100? |
|---------------|-----------------|------------|
| 0.01 (very weak) | 5.3 | No |
| 0.10 (weak) | 53.3 | No |
| 0.50 (cable test) | 266.5 | Yes |

**Impact:** For the intended 18 km link, weak signals always hit the FFT fallback,
which is less reliable than the correlation-based estimate.

**Fix suggestion:** Normalize correlation by signal amplitude: use
`best_corr / sqrt(len(SYNC_BPSK)) > 3 · noise_std`.

#### No Per-Chunk Energy Check After Lock

**File:** `src/pkt_enhanced_rx.py`, `LiveReceiver._process_chunk()`

After the first chunk establishes FO lock, subsequent chunks skip energy
detection entirely. Pure noise gets AGC-amplified (up to 60 dB) and processed
through the full demod pipeline, wasting CPU.

**Fix suggestion:** Add a per-chunk energy check before AGC in the locked path:
```python
if np.max(np.abs(samples)) < _SIGNAL_DETECT_THRESHOLD * self.agc_target:
    self._empty_chunks += 1
    if self._fo_lock:
        return  # skip empty chunks
```

### 🟡 Medium Priority

#### Real-Only Filtering Diverges in File/Test Paths

**Files:** `test/test_layer2.py`, `pkt_enhanced_rx.py` file mode

The file mode and L2 tests use `bb.real` (I-only) instead of `bb` (complex) for
RRC filtering:

```python
# File/test path (wrong):
filtered = np.convolve(bb.real, rrc, 'same')

# Live receiver (correct):
filtered = np.convolve(bb, rrc, 'same')
```

For FO ≈ 0 (cable test) the phase is aligned, so `bb.real` captures all energy.
For signals with real FO, half the energy is lost. This hides a latent bug.

**Fix:** Change all `bb.real` to `bb` in test and file-mode paths.

#### Hardcoded Python Path

**File:** `test/test_layer3.py`

```python
PYTHON = '/opt/homebrew/opt/python@3.14/bin/python3.14'
```

This breaks on Python version updates. **Fix:** Use `sys.executable`.

### 🔵 Low Priority

#### Redundant SYNC_BPSK_LOCAL

`scan_frequency()` recomputes a local copy of the module-level `SYNC_BPSK`
constant on every call. Minor CPU waste — just use the global.

#### Burst Shaping Ramp Length

The code uses `ramp_len = min(ramp_symbols * sps, len(waveform) // 2)` (up to
50% tapered) vs. the plan's `// 4` (up to 25% tapered). Not a correctness issue
for normal operation (preamble is 192 bits, ample for sync detection), but
documented for awareness.

#### FO Re-Scan Bypasses Tracking State

When the re-scan triggers after N empty chunks, the new FO is set directly
without updating the history buffer. Benign — the next successful decode will
re-populate the history — but worth noting for diagnostics.

---

## Appendix A: File Map

```
packet/
├── src/
│   ├── pkt_enhanced_tx.py      # Transmitter (burst assembly, BPSK mod, RRC shaping)
│   ├── pkt_enhanced_rx.py      # Receiver (FO estimation, AGC, sync corr, decode)
│   ├── packet_codec.py         # CRC-32 + FEC framing (packet_encode / packet_decode)
│   └── fec_cc.py               # Convolutional codec (k=7, r=1/2, Viterbi)
├── test/
│   ├── test_layer1.py          # Direct codec tests (no radio)
│   ├── test_layer2.py          # Software loopback tests (TX→IQ→RX)
│   ├── test_layer3.py          # Hardware cable test (two HackRFs)
│   ├── layer3_tx.py            # Helper: TX subprocess for L3
│   └── layer3_rx.py            # Helper: RX subprocess for L3
├── docs/
│   ├── DETAILED.md             ← You are here
│   ├── rx_flow.svg             # RX signal processing flow diagram
│   └── tx_flow.svg             # TX signal processing flow diagram
├── ARCHITECTURE.md             # Architecture overview
├── CODEX_REVIEW.md             # Code review findings
├── HELLO_TX_RX.md              # Original working TX/RX documentation
├── STEP3_PLAN.md               # Step 3 implementation plan
└── ALIGNMENT_PLAN.md           # Project alignment progress
```

## Appendix B: Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `PREAMBLE_BITS` | 192 | 24-byte preamble |
| `SYNC_BITS` | 32 | 4-byte sync word |
| `SYNC_WORD` | `0xACDDA4E2` | Sync word (not in preamble) |
| `MAX_FEC_BYTES` | 1038 | Max FEC bytes for 512-byte payload |
| `MAX_FEC_SYMS` | 8304 | Max BPSK symbols after sync word |
| `RRC_ALPHA` | 0.35 | Root-raised cosine rolloff factor |
| `SPS` (default) | 20 | Samples per symbol |
| `FS` (default) | 2,000,000 | Sample rate (Hz) |
| `SYM_RATE` (default) | 100,000 | Symbol rate (FS/SPS) |
| `_SIGNAL_DETECT_THRESHOLD` | 0.1 | CF32 magnitude threshold for signal detect |
| `_FO_NARROW_WIDTH` | 5000 | ±5 kHz narrow re-scan |
| `_FO_WIDE_WIDTH` | 20000 | ±20 kHz full scan |
| `_FO_EMPTY_THRESHOLD` | 3 | Empty chunks before re-scan |
| `_FO_HISTORY_WINDOW` | 5 | Median filter for FO tracking |
| `position_tolerance` | 10 | Symbol tolerance for packet dedup |
| `top_n` | 5 | Max correlation peaks to try per phase |

---

*End of DETAILED.md — if you're reading this at 2am during a balloon launch,*
*start with `python3 test_layer2.py` to verify the pipeline, then move to the*
*cable loopback. If the cable test works, the OTA test is just further away.*
