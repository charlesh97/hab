# Packet Communication System

BPSK packet telemetry link for the HAB ground station — CRC-32 + FEC protected
packets received via sync-word correlation.

## Directory Structure

```
packet/
├── src/                  # Active production code
│   ├── packet_codec.py       # CRC-32 + FEC encode/decode (no radio)
│   ├── fec_cc.py             # Convolutional codec (k=7, rate 1/2)
│   ├── pkt_enhanced_tx.py    # TX chain: packet bits → BPSK modulated IQ
│   └── pkt_enhanced_rx.py    # RX chain: IQ → sync-word correlation → decode
├── test/                 # 3-layer test suite (see test/README.md)
│   ├── test_all.py           # Test runner
│   ├── test_layer1.py        # Codec-only round-trip (no radio)
│   ├── test_layer2.py        # TX→RX software loopback (no radio)
│   ├── test_layer3.py        # Hardware cable test (HackRF required)
│   ├── layer3_tx.py          # TX helper for hardware tests
│   ├── layer3_rx.py          # RX helper for hardware tests
│   └── tx_continuous.py      # Continuous burst transmitter
├── debug/                # Development & troubleshooting tools
│   ├── packet_rx.py          # GNU Radio hierarchical RX block
│   ├── packet_tx.py          # GNU Radio hierarchical TX block
│   ├── packet_loopback_hier.py    # Software loopback hierarchical block
│   ├── padding_packing_crc_block.py   # Custom CRC padding block
│   ├── padding_and_packing_crc_block.block.yml  # GRC block definition
│   ├── burst_to_stream.py        # Burst-to-stream converter
│   ├── packet_gap_filler.py      # TX gap filler
│   ├── packet_chain_analysis.md  # Chain data-flow analysis
│   └── padding_packing_crc.md    # CRC padding docs
├── docs/                 # System documentation
│   ├── DETAILED.md           # Deep-dive system guide
│   ├── diagrams.mmd          # Mermaid architecture diagrams
│   ├── packet_structure.md/svg  # Packet format diagrams
│   ├── rx_flow.md/svg           # RX pipeline flow
│   └── tx_flow.md/svg           # TX pipeline flow
├── test/README.md        # Test suite documentation
└── README.md             # This file
```

## Active Code

### `src/packet_codec.py`
Core codec — CRC-32 generation and FEC encoding/decoding. No radio dependencies.
Used by both `pkt_enhanced_tx` and `pkt_enhanced_rx`.

- `packet_encode(data, max_payload=512)` → FEC-protected bytes
- `packet_decode(fec_data, max_payload=512)` → original data or None

### `src/pkt_enhanced_tx.py`
Transmitter chain: takes a payload, appends CRC-32, FEC encodes, prepends
preamble + sync word, then BPSK-modulates at the configured SPS.

### `src/pkt_enhanced_rx.py`
Receiver chain: DC remove → FO scan → mix down → RRC match filter →
try all SPS decimation phases → sync-word correlate (0xE38FC0FC) →
extract FEC payload → hard-decision → CRC validate → print.

## Three-Layer Test Suite

See `test/README.md` for full details.

```bash
# Layer 1 — Codec round-trip (milliseconds, no radio)
./test/test_all.py --layer 1

# Layer 2 — Software loopback (seconds, no radio)
./test/test_all.py --layer 2

# Layer 3 — Hardware cable test (HackRF required)
./test/test_all.py --layer 3

# All layers
./test/test_all.py
```

## Key Parameters

- **Modulation**: BPSK
- **Sync Word**: `0xE38FC0FC` (32-bit)
- **Preamble**: 24 bytes (192 bits)
- **FEC**: Convolutional code (k=7, rate=1/2, terminated)
- **CRC**: CRC-32
- **Max Payload**: 512 bytes (2-byte length field)
- **SPS**: 20 (configurable)
- **Sample Rate**: 2 MHz (default)

## Debug Tools

The `debug/` directory contains intermediate troubleshooting scripts used
during development of the packet chain. These are GNU Radio hierarchical
blocks and custom blocks for bit-padding/PCRC debugging. They are not
part of the production chain but are preserved for reference.
