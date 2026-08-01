# HAB Ground Station — User Guide

A professional ground station application for high-altitude balloon (HAB) DVB-S2 video transmission and telemetry reception.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                 Python Backend (HabEngine)               │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ DVBS2 TX │  │ Pipeline │  │ WebSocket Server     │  │
│  │ Flowgraph│  │ (ffmpeg  │  │ ws://localhost:8765   │  │
│  │ via SDR  │  │  → tsp)  │  │                      │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│         │            │                │                 │
│         └─────┬──────┘                │                 │
│               │                       │                 │
│         ┌─────▼─────┐                 │                 │
│         │ HabEngine  │  (singleton)   │                 │
│         └─────┬─────┘                 │                 │
│               │                       │                 │
│         ┌─────▼──────┐                │                 │
│         │ PySide6 GUI │               │                 │
│         │ (Operator)  │               │                 │
│         └────────────┘                │                 │
└───────────────────────────────────────┼─────────────────┘
                                        │
                              ┌─────────▼────────┐
                              │  macOS Dashboard  │
                              │  (SwiftUI)        │
                              └──────────────────┘
```

## Quick Start

### 1. Setup Environment

```bash
cd ~/Documents/git/hab/rf
source setup_env.sh
```

This activates the venv and configures GNU Radio paths.

### 2. Launch GUI

```bash
cd ~/Documents/git/hab/hab-gui/python
./launch.sh
```

Three tabs:

| Tab | Purpose |
|-----|---------|
| **Connection** | Discover and connect to HackRF devices, set frequency/gain |
| **DVBS-2 TX** | Select MP4 file, start encoding pipeline, transmit via SDR |
| **Telemetry** | Spectrum analyzer and packet telemetry display |

### 3. Over-the-Air Test

```bash
cd ~/Documents/git/hab/hab-gui/python
bash test_ota.sh
```

This runs: file-to-file loopback → OTA TX/RX → TS verification → WebSocket test.

### 4. macOS Dashboard

Open the Xcode project and run:

```bash
open ~/Documents/git/hab/hab-gui/macos/Balloon\ Dashboard.xcodeproj
```

Build and run. Connect to `ws://localhost:8765`.

## OTA Workflow

### Transmitter (HackRF #0 — serial ...60661)
```
Source File (MP4) 
    → ffmpeg (encode to MPEG-TS at 965 kbps)
    → tsp (rate regulate to 965326 bps)
    → /tmp/tsfifo (named pipe)
    → GNU Radio DVBS2 flowgraph (QPSK 1/2, pilots on)
    → SoapySDR → HackRF TX at 915 MHz (ISM band)
```

### Receiver (HackRF #1 — serial ...67464)
```
HackRF RX at 915 MHz
    → SoapySDR source
    → GNU Radio dvbs2rx demodulator
    → MPEG-TS output (file or UDP)
    → ffplay or VLC to view
```

### Bitrate Calculation

For QPSK 1/2 at 1 Msym/s with pilots ON:
- Transport stream bitrate: **965,326 bps**
- Video budget: ~700 kbps (H.264)
- Audio budget: ~128 kbps (MP2)
- Remaining: ~137 kbps for overhead/headers

## Available Commands

### CLI Tools (rf/dvbs2/)

```bash
# File-to-file test
python3 dvbs2/tx.py --source file --in-file input.ts \
  --sink file --out-file output.iq --sym-rate 1e6 --modcod QPSK1/2

# Over-the-air TX
python3 dvbs2/tx.py --source file --in-file video.ts \
  --sink hackrf --hackrf-vga 16 --hackrf-amp \
  --hackrf-serial 'SERIAL' --freq 915e6 --sym-rate 1e6

# Over-the-air RX
python3 dvbs2/rx.py --source hackrf --hackrf-serial 'SERIAL' \
  --hackrf-lna 8 --hackrf-vga 24 --hackrf-amp \
  --sink file --out-file rx.ts --freq 915e6 --sym-rate 1e6
```

### GUI

```bash
# Launch full app
./launch.sh

# Run tests
python3 test_engine.py

# Full OTA test
bash test_ota.sh
```

## Development

### Project Structure

```
hab/
├── rf/
│   ├── dvbs2/              # CLI DVB-S2 tools
│   │   ├── tx.py           # Transmitter (HackRF/USRP/BladeRF)
│   │   ├── rx.py           # Receiver (HackRF/RTL-SDR/USRP)
│   │   └── flowgraph.py    # GRC-generated flowgraph
│   ├── packet/             # Packet telemetry (FSK/GMSK)
│   ├── dtv-utils-master/   # dvbs2rate utility (COMPILED)
│   ├── setup_env.sh        # Environment setup
│   └── venv/               # Python venv
├── hab-gui/
│   ├── python/
│   │   ├── main.py         # GUI entry point
│   │   ├── connection_tab.py
│   │   ├── dvbs2_tx_tab.py
│   │   ├── dvbs2_flowgraph.py  # Embedded flowgraph (FIXED)
│   │   ├── telemetry_tab.py
│   │   ├── telemetry_rx.py
│   │   ├── hab_engine/     # Core engine package ★
│   │   │   ├── engine.py           # HabEngine singleton
│   │   │   ├── flowgraph_manager.py
│   │   │   ├── pipeline_manager.py
│   │   │   ├── websocket_server.py # WS server :8765
│   │   │   └── models.py           # Data models
│   │   ├── launch.sh       # One-command launcher
│   │   ├── test_engine.py  # 25 integration tests
│   │   └── test_ota.sh     # OTA test suite
│   └── macos/
│       └── Balloon Dashboard/  # Xcode SwiftUI app
└── docs/
    └── ARCHITECTURE.md
```

### Adding Features

1. **Engine**: Modify `hab_engine/engine.py`
2. **Flowgraph**: Modify `dvbs2_flowgraph.py` (GNU Radio)
3. **GUI Tab**: Create new tab file, add to `main.py`
4. **macOS**: Add SwiftUI views, connect via WebSocket

## Troubleshooting

| Issue | Likely Fix |
|-------|-----------|
| "No module named 'gnuradio'" | Run `source rf/setup_env.sh` |
| HackRF not found | Check USB, run `hackrf_info` |
| No carrier lock | Increase TX gain, check antennas, verify frequency matches |
| High FER | Decrease symbol rate, increase TX power |
| GUI won't render | Needs macOS with display — `ssh -X` or run locally |
| WebSocket connection refused | Ensure Python GUI is running (launch.sh) |
