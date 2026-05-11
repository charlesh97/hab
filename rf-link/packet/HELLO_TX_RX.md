# BPSK Packet Link — HELLO WORLD TX/RX

This directory contains the working BPSK packet communication link that successfully
transmitted and decoded `"HELLO WORLD\n"` over an SMA cable between two HackRF Ones
(5,809 clean packets in 20 seconds, score 121/121).

## Files

| File | Purpose |
|------|---------|
| `pkt_hello_tx.py` | Transmitter — sends a burst of BPSK packets with a known message |
| `pkt_rx_final.py` | Live receiver — native SoapySDR capture + sync-word-based decoding |
| `hello_decoder.py` | Offline decoder — analyze captured IQ files against the known packet structure |
| `packet_tx.py` | Original GNU Radio hierarchical TX block (full packet chain) |
| `packet_rx.py` | Original GNU Radio hierarchical RX block (full packet chain) |
| `telemetry_tx.py` | Original HackRF TX test script (full packet chain) |
| `telemetry_rx.py` | Original HackRF RX test script (full packet chain) |

## Packet Structure (Enhanced — CRC+FEC Protected)

```
[ preamble: 24 bytes ] [ sync word: 32 bits ] [ FEC payload: variable ]
```

- **Preamble**: `0xE38FC0FC7FC7E381C0FF8038FFF038E00FC0038000FFFFC0` (24 bytes, from `packet_rx.py`)
- **Sync word**: `0xACDDA4E2` (GNU Radio default access code, different from preamble — unambiguous correlation)
- **Payload**: CRC-32 + FEC (convolutional code k=7, rate=1/2) protected variable-length data
- **Modulation**: BPSK, RRC-shaped (α=0.35), 20 samples/symbol
- **Sample rate**: 2 Msps
- **Symbol rate**: 100 kbaud
- **Packet duration (12B payload)**: 496 symbols × 20 = 9,920 samples ≈ 4.96 ms

### Original (Legacy) Implementation

The original working TX/RX (`pkt_hello_tx.py` / `pkt_rx_final.py`) uses a simpler structure:
```
[ 256-bit alternating preamble ] [ 32-bit sync word: 0xE38FC0FC ] [ raw 96-bit payload ]
```

## How to Run

### Terminal 1 — Transmitter

```bash
python3 pkt_hello_tx.py --freq 915e6 --samp 2e6 --vga 47 --amp --serial <TX_SERIAL>
```

### Terminal 2 — Receiver

```bash
python3 pkt_rx_final.py --freq 915e6 --lna 8 --vga 12 --duration 30 --serial <RX_SERIAL>
```

## Receiver Architecture

The live receiver (`pkt_rx_final.py`) uses a two-stage approach:

1. **Frequency offset estimation** — FFT-based scan of ±10 kHz around the carrier to
   find the strongest spectral peak, then mix down to baseband
2. **Sync-word correlation** — RRC matched filter, decimate to symbol rate, then
   correlate against the known 32-bit BPSK sync word. The correlation peak gives
   exact packet boundary. Adaptive threshold = mean + 3.5× stddev.

This approach was proven on the offline capture first (`hello_decoder.py` at 121/121),
then ported to live SoapySDR streaming.

## Bugs Beaten

1. `map_bb([1, -1])` outputs unsigned bytes — `-1` wraps to 255
2. SoapySDR sink needs `throttle` block — GNU Radio scheduler doesn't stream
   without it
3. RRC filter gain must equal `sps` — default `gain=1.0` gives 0.055 V output
4. Preamble correlation is ambiguous — all 256 preamble bits alternate, giving
   flat correlation peaks. Sync-word correlation resolves exact boundaries
5. Frequency offset estimation must run on *raw* IQ, not RRC-filtered data
