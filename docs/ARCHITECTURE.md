# HAB Packet Radio — System Architecture

> Snapshot: commit `74a98a1` — validated pipeline: 187 good packets, 5 min continuous, 0 dropouts

## Physical Topology

```
┌──────────────────── Rock 2A (192.168.86.30) ────────────────────┐
│                                                                    │
│  ┌──────────┐   UART0   ┌──────────┐   USB 3.0   ┌───────────┐  │
│  │ L76K GPS │───9600───▶│ NMEA     │────────────▶│   Soapy   │  │
│  │ (XIAO)   │  pins 8/10│ Parser   │             │HackRF Sink│  │
│  └──────────┘           └────┬─────┘             └─────┬─────┘  │
│                              │                         │         │
│                              ▼                         │         │
│                     ┌────────────────┐                 │         │
│                     │ PositionFrame  │                 │         │
│                     │  .pack() → 38B │───BPSK────────▶│         │
│                     └────────────────┘  100 ksym/s     │         │
│                                                                    │
│  gps_packet_tx.py                                                 │
│  • 1 Hz burst cycle                                               │
│  • 256b preamble + 32b sync (0xE38FC0FC)                          │
│  • CRC-16/XMODEM                                                  │
│  • RRC-shaped BPSK (α=0.35, SPS=20, FS=2 MHz)                    │
└──────────────────────────────────┬─────────────────────────────────┘
                                   │
                           915 MHz BPSK
                                   │
┌──────────────────── Mac (RX) ────┼─────────────────────────────────┐
│                                  ▼                                  │
│  ┌───────────┐   USB    ┌────────────────┐   stdout   ┌─────────┐ │
│  │  HackRF   │─────────▶│pkt_simple_rx.py│───hex─────▶│ bridge  │ │
│  │ One (RX)  │          │ BPSK demod     │  payloads  │         │ │
│  └───────────┘          └────────────────┘            └────┬────┘ │
│                                                            │       │
│                                   POST /api/packet         │       │
│                                   {"data": {...}}          ▼       │
│                                           ┌───────────────────┐   │
│                                           │  FastAPI Dashboard │   │
│                                           │  localhost:8000    │   │
│                                           └───────────────────┘   │
│                                                                    │
│  gps_bridge.py                                                     │
│  • Async subprocess manager                                        │
│  • Hex payload → unpack_frame() → PositionFrame                    │
│  • frame_to_dashboard() → JSON → POST                              │
└────────────────────────────────────────────────────────────────────┘
```

## Data Flow (Layers)

```
Layer 4: Dashboard JSON     {"v":1, "id":"HAB-001", "type":"position", ...}
         ▲
         │ frame_to_dashboard()
         │
Layer 3: PositionFrame      38-byte typed binary (type=0x01, seq, lat, lon, alt, ...)
         ▲
         │ unpack_frame() / pack_frame()
         │
Layer 2: Packet Framing     256b preamble | 32b sync | 16b len | payload | CRC-16
         ▲
         │ make_packet_waveform() / pkt_simple_rx.py decode
         │
Layer 1: BPSK Waveform      RRC-shaped complex64 samples @ 2 MS/s → 100 ksym/s
         ▲
         │ SoapySDR / HackRF
         │
Layer 0: RF                 915 MHz, ~10 mW (VGA=47, AMP=on)
```

## Key Files

### TX Pipeline (Rock 2A)
| File | Role |
|---|---|
| `payload/tx/gps_packet_tx.py` | Main TX loop: reads GPS, packs frames, builds BPSK bursts, transmits via SoapySDR |
| `payload/gps/nmea.py` | NMEA sentence parser, reads `/dev/ttyS0` at 9600 baud |
| `payload/telemetry/packet_format.py` | `PositionFrame` dataclass: pack/unpack, 38-byte struct, type dispatch |

### RX Pipeline (Mac)
| File | Role |
|---|---|
| `rf/packet/gps_bridge.py` | Async bridge: manages RX subprocess lifecycle, parses stdout, POSTs to dashboard |
| `rf/packet/src/pkt_simple_rx.py` | BPSK demodulator: HackRF RX → packet decode → hex output |
| `rf/packet/src/pkt_simple_tx.py` | Standalone BPSK TX (test/debug — not used in live pipeline) |

### Dashboard (Mac)
| File | Role |
|---|---|
| `dashboard/server/main.py` | FastAPI app entry point |
| `dashboard/server/routes/rest.py` | `POST /api/packet` endpoint |
| `dashboard/server/models.py` | Pydantic packet models |

## Frame Format

### Outer Packet (BPSK)
```
| Preamble (256b) | Sync 0xE38FC0FC (32b) | Length uint16 | Payload | CRC-16/XMODEM |
```
- Preamble: alternating 1/0 (carrier recovery)
- Sync: fixed 32-bit word for frame alignment
- Length: big-endian uint16, payload bytes
- CRC-16: XMODEM polynomial 0x1021 over payload only

### Inner Payload (PositionFrame, type=0x01)
```
| type (1B) | seq (2B) | lat (8B) | lon (8B) | alt_m (4B) | agl_m (4B) |
| fix (1B) | fix_type (1B) | sats (1B) | hdop (4B) | vdop (4B) |
= 38 bytes
```

- Type byte: 0x01 = position (future: 0x02=motion, 0x03=environment, 0x04=power)
- All multi-byte fields: little-endian (`<` struct)
- fix_type: 0=none, 1=2d, 2=3d

### Dashboard JSON (POST /api/packet)
```json
{
  "data": {
    "v": 1,
    "id": "HAB-001",
    "mid": "FLIGHT-1",
    "seq": 42,
    "t": "T14:32:15",
    "type": "position",
    "lat": 37.75326,
    "lon": -122.39294,
    "alt_m": 41.7,
    "agl_m": 31.7,
    "fix": true,
    "fix_type": "2d",
    "sats": 10,
    "hdop": 1.2,
    "vdop": 0.0
  }
}
```

## Launch Commands

### TX (Rock 2A)
```bash
ssh hab@192.168.86.30
cd ~/payload
python3 tx/gps_packet_tx.py --freq 915e6 --device /dev/ttyS0 --baud 9600
```

### RX Bridge (Mac)
```bash
cd ~/git/hab
/opt/homebrew/bin/python3.14 rf/packet/gps_bridge.py \
    --freq 915e6 --serial 60a464dc3606610f --lna 32 --vga 40 --amp
```

## Dependencies

| Component | Rock 2A (Armbian Debian 13) | Mac (macOS 26) |
|---|---|---|
| GNU Radio | 3.10.12 (apt) | — |
| SoapySDR + HackRF module | soapysdr-module-hackrf (apt) | soapyhackrf (brew) |
| libhackrf | hackrf (apt) | hackrf (brew) |
| Python | 3.12 (system) | 3.14 (brew) |
| requests | — | brew pip3.14 |

## Known Issues & Gotchas

1. **Zombie process locks HackRF**: macOS enforces exclusive USB ownership. If a previous `pkt_simple_rx.py` exits without cleanup, the next launch gets "Could not Open HackRF Device". Fix: `kill -9 <pid>` or unplug/re-plug.

2. **SoapySDR sink API**: On arm64 GNU Radio 3.10, `soapy.sink()` requires 7 positional args: `("driver=hackrf", "fc32", 1, "", "", [""], [""])`. The serial goes in arg[3]: `"serial=XXXX"`.

3. **Working directory for bridge**: Must run from `~/git/hab` so `sys.path` resolves `telemetry.packet_format`. The bridge adds `../payload` to path relative to its own file location.

4. **Python 3.14 on macOS**: `requests` must be installed via `pip3.14 install --break-system-packages requests` or `brew`. PEP 668 blocks unqualified `pip install`.

5. **HackRF clone detection**: Both HackRFs are clones (not genuine GSG). `hackrf_info` warns "Hardware does not appear to have been manufactured by Great Scott Gadgets" — functionally identical, cosmetic warning only.

## Future Architectural Notes

Areas identified for restructuring:

- **DVB-S2 integration**: The packet radio pipeline runs independently. DVB-S2 transport (`rf/dvbs2/`) expects MPEG-TS streams — a muxer is needed to inject telemetry packets into the TS alongside video.
- **Dashboard persistence**: `POST /api/packet` returns 200 but currently drops packets when `receiver_manager` is None (standalone server mode). Needs a direct ingestion path.
- **Burst vs. continuous TX**: TX builds and tears down flowgraphs per packet (1 Hz cycle). Continuous mode would avoid startup overhead.
- **Error handling in bridge cleanup**: `proc.terminate()`/`proc.kill()` throws `ProcessLookupError` if the subprocess has already exited — needs a process-exists guard.
- **AGL calculation**: Currently hardcoded `alt_m - 10.0` as rough AGL. Needs barometric sensor or terrain database.
