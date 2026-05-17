# RF Packet Link — Architecture & Flow

## Packet Structure (Air Interface)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Air Burst                                    │
├────────────────┬──────────┬─────────────────────────────────────────┤
│   Preamble     │ Sync Word │         FEC-Protected Payload          │
│   (24 bytes)   │ (4 bytes) │   (variable length, ~14..1038 bytes)   │
├────────────────┴──────────┴─────────────────────────────────────────┤
│           ├── BPSK symbols (all at same symbol rate) ───┤            │
└─────────────────────────────────────────────────────────────────────┘

Payload internals (before FEC encoding):
┌──────────────────┬────────────────────────────┬────────────────────┐
│ Length (2 bytes) │   Payload Data (N bytes)   │    CRC-32 (4 B)   │
│  big-endian N    │   actual message content   │ zlib.crc32 of     │
│                   │                            │ [len][payload]    │
└──────────────────┴────────────────────────────┴────────────────────┘
```

### Transmission Parameters

| Parameter | Default | Typical Range |
|-----------|---------|---------------|
| Sample rate | 2 MS/s | 1–20 MS/s |
| Samples per symbol (SPS) | 20 | 4–2000 |
| Symbol rate | 100 ksym/s | 1–500 ksym/s |
| Modulation | BPSK | BPSK |
| RRC rolloff (α) | 0.35 | 0.2–0.5 |
| TX center frequency | 915 MHz | 300–6000 MHz |
| TX power | +10 dBm | (HackRF max) |

## Signal Processing Chain

### Transmitter Flow

```
┌──────────┐   payload bytes   ┌──────────┐   FEC bytes   ┌───────────┐
│  packet_ │ ────────────────→ │  packet_ │ ────────────→ │  fec_cc   │
│  encode  │                   │  codec   │               │  encoder  │
│   call   │   length(2) +     │  (CRC)   │               │  k=7,r=1/2│
│          │   payload + crc32 │          │               │  +2 pad   │
└──────────┘                   └──────────┘               └───────────┘
                                     │                          │
                                     │                          ▼
                                     │                ┌──────────────────┐
                                     │                │  Bit stream:     │
                                     │                │  [...fec bits...]│
                                     │                └──────────────────┘
                                     │                          │
                                     │                          ▼
                                     │                ┌──────────────────┐
                                     │       ┌────────┤  pkt_enhanced_tx │
                                     │       │        │  build burst:    │
                                     │       │        │  preamble(192 B) │
                                     │       │        │  + sync(32 bits) │
                                     │       │        │  + fec bits      │
                                     │       │        └────────┬─────────┘
                                     │       │                 │
                                     │       │                 ▼
                                     │       │        ┌──────────────────┐
                                     │       │        │  BPSK modulate   │
                                     │       │        │  RRC pulse shape │
                                     │       │        │  burst shaping   │
                                     │       │        │  (Hann envelope) │
                                     │       │        └────────┬─────────┘
                                     │       │                 │
                                     │       │                 ▼
                                     │       │        ┌──────────────────┐
                                     │       │        │  SoapySDR/       │
                                     │       │        │  HackRF One      │
                                     │       │        └──────────────────┘
```

### Receiver Flow

```
┌────────────────┐
│  HackRF One    │
│  (SoapySDR)    │  ─── complex32 samples @ FS, tuner @ fc
└───────┬────────┘
        │
        ▼
┌──────────────────────────────────┐
│  Digital AGC                     │
│  Scale RMS → target (e.g. 0.3)  │
│  Skip chunk if signal < noise   │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  FO Estimation (scan_frequency)  │
│  FFT centroid or sync-word       │
│  correlation sweep ±20 kHz       │
│  Continuous tracking (re-scan on │
│  threshold)                      │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Mix to baseband                 │
│  samples × exp(-j2π·FO·t/FS)    │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  RRC matched filter              │
│  (root_raised_cosine, α=0.35)   │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Decimate × SPS (try all phases) │
│  phase 0..SPS-1                  │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Sync-word correlation           │
│  (0xACDDA4E2 as BPSK symbols)   │
│  Find top correlation peaks      │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Extract FEC payload symbols     │
│  MAX_FEC_SYMS after sync word    │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Hard-decision bits              │
│  Pack to bytes                   │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  packet_decode (CRC-32 + FEC)    │
│  Viterbi decode → length check → │
│  CRC validate → return payload   │
└──────────────┬───────────────────┘
               │
               ▼
          Decoded message
          (ASCII/text)
```

## Module Dependency Map

```
                    ┌──────────┐
                    │  fec_cc  │  (convol. encoder + Viterbi decoder)
                    └────┬─────┘
                         │ import
                         ▼
                    ┌──────────────┐
                    │ packet_codec │  (CRC-32 + FEC framing)
                    └──────┬───────┘
                     ┌─────┴──────┐
                     │            │
                     ▼            ▼
              ┌──────────┐  ┌──────────┐
              │  tx      │  │  rx      │
              │ enhanced │  │ enhanced │
              └──────────┘  └──────────┘
```

### File-by-file role

| File | Role | Lines | Key Classes/Functions |
|------|------|-------|-----------------------|
| `src/fec_cc.py` | Convolutional codec | 282 | `encode_bytes()`, `decode_bytes_hard()` |
| `src/packet_codec.py` | CRC+FEC framing | 210 | `packet_encode()`, `packet_decode()` |
| `src/pkt_enhanced_tx.py` | BPSK TX with SDR | ~150 | `main()`, `bpsk_modulate()`, `make_packet_bits()`, `make_test_burst()`, `apply_burst_shaping()` |
| `src/pkt_enhanced_rx.py` | Synch-word RX with AGC | ~360 | `LiveReceiver`, `scan_frequency()`, `process_phase()`, `decode_payload_symbols()` |

## Key Design Decisions

### 2-bit Pre-padding
The convolutional encoder (k=7, terminated) requires the bit stream to terminate in the zero state. GNU Radio's byte-aligned approach drops 2 bits, creating a truncation error. We add 2 pre-padding bits before encoding so the output is byte-aligned without truncation.

### Variable-Length Payloads
The length is embedded *inside* the FEC-protected data (2 bytes, big-endian). The receiver extracts a fixed maximum number of FEC symbols and lets packet_decode() use the length byte + CRC to find the actual payload boundaries.

### Sync Word ≠ Preamble
The preamble is 24 bytes of a specific pattern (from the original GRC flowgraph). The sync word is `0xACDDA4E2` — deliberately **not** the first 4 bytes of the preamble. This gives unambiguous correlation: the preamble creates a flat correlation floor, then the sync word produces a sharp peak.

### FO Search Strategy
The initial FO estimate uses a ±20 kHz sweep in 500 Hz steps, comparing sync-word correlation strength. After acquisition, FO is continuously tracked via periodic narrow re-scans (±5 kHz around last estimate).
