# HAB Ground Station — Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                 Python Backend (hab-engine)                  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ DVBS2 TX     │  │ Telemetry RX │  │ Spectrum Mgr     │  │
│  │ Pipeline Mgr │  │ Flowgraph    │  │ FFT extraction   │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│         └────────┬────────┘────────────────────┘            │
│                  │                                          │
│           ┌──────▼──────┐                                   │
│           │  HabEngine  │  Core orchestrator                 │
│           │  (singleton)│                                   │
│           └──────┬──────┘                                   │
│                  │                                          │
│     ┌────────────┼────────────┐                             │
│     │            │            │                             │
│  ┌──▼──┐  ┌──────▼──────┐  ┌─▼─────────┐                  │
│  │ GUI │  │ WebSocket   │  │ REST API  │                  │
│  │ Tabs│  │ Server :8765 │  │ :8766     │                  │
│  └─────┘  └──────┬──────┘  └───────────┘                  │
│                  │                                          │
└──────────────────┼──────────────────────────────────────────┘
                   │ ws://localhost:8765
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              macOS App (SwiftUI Dashboard)                   │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │ Waterfall│  │ GPS Map  │  │ Telemetry│  │ Pipeline   │ │
│  │ Spectrum │  │ Overlay  │  │ Readout  │  │ Controls   │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### Video TX Path
```
File (MP4) → ffmpeg (encode to TS) → UDP multicast → tsp (regulate) 
→ /tmp/tsfifo (FIFO) → GNU Radio DVBS2 flowgraph → SoapySDR → HackRF TX
```

### Telemetry RX Path  
```
HackRF RX → SoapySDR Source → GNU Radio Demod → Packet Decoder 
→ Message Callback → HabEngine → GUI Terminal + WebSocket broadcast
```

### Spectrum Data Path
```
GNU Radio Source → Stream to Vector → FFT → Complex to Mag² 
→ Vector Sink → _update_spectrum() → Queue → GUI Plot + WS broadcast
```

### macOS App Data
```
HabEngine WebSocket Server → JSON messages every 100ms:
{
  "type": "spectrum" | "telemetry" | "status" | "pipeline",
  "data": { ... }
}

Commands (macOS → Engine):
{
  "command": "start_pipeline" | "stop_pipeline" | "start_tx" | "stop_tx" | 
             "set_frequency" | "set_gain" | "set_symbol_rate"
}
```

## Module Structure

```
hab-gui/python/
├── main.py                 # Entry point, creates engine + window
├── connection_tab.py       # HackRF discovery + connection UI
├── dvbs2_tx_tab.py         # DVBS2 video transmission tab
├── telemetry_tab.py        # Telemetry RX + spectrum analyzer tab
├── dvbs2_flowgraph.py      # Embedded GNU Radio flowgraph (FIXED)
├── dvbs2_tx.py             # Reference standalone flowgraph (from rf-link/dvbs2)
├── telemetry_rx.py         # Telemetry receiver flowgraph
│
├── hab_engine/             # Core engine package
│   ├── __init__.py
│   ├── engine.py           # HabEngine - singleton orchestrator
│   ├── flowgraph_manager.py # DVBS2 TX flowgraph lifecycle
│   ├── telemetry_manager.py # Telemetry RX flowgraph lifecycle
│   ├── pipeline_manager.py # ffmpeg → tsp pipeline control
│   ├── spectrum_manager.py # FFT extraction + queue management
│   ├── websocket_server.py # WebSocket server for macOS app
│   └── models.py           # Typed data models / messages
```

## Dual-Channel Architecture

Two separate GNU Radio flowgraphs run simultaneously:

| Channel | HackRF | Direction | Purpose |
|---------|--------|-----------|---------|
| Video TX | #0 (serial ...60661) | Transmit | DVB-S2 QPSK video downlink |
| Packet RX | #1 (serial ...67464) | Receive | FSK/GMSK telemetry data |

The HabEngine manages both flowgraphs independently with separate:
- Sample rates, frequencies, gains
- Start/stop lifecycles
- Error handling

## Phased Implementation

### Phase 1 — Core Engine + GUI Fixes (CURRENT)
- [x] Fix dvbs2_flowgraph.py sink name bug
- [x] Fix set_freq → set_frequency 
- [x] Add real spectrum extraction blocks
- [x] Wire connection params into flowgraph
- [x] Create HabEngine orchestrator
- [x] Create FlowgraphManager
- [x] Create PipelineManager
- [ ] Wire GUI tabs → HabEngine

### Phase 2 — Telemetry Integration
- [ ] Add SoapySDR source to telemetry_rx.py
- [ ] Connect demod blocks
- [ ] Implement packet decoder
- [ ] Wire telemetry tab → HabEngine

### Phase 3 — WebSocket + macOS App
- [ ] Build WebSocket server
- [ ] Define message protocol
- [ ] Update macOS SwiftUI app
- [ ] Connect dashboard to engine

### Phase 4 — Integration Testing
- [ ] OTA test with full pipeline
- [ ] Dual HackRF test (video TX + telemetry RX)
- [ ] macOS app connectivity test
- [ ] Performance profiling

## Data Models (hab_engine/models.py)

```python
@dataclass
class PipelineStatus:
    running: bool
    file_path: str
    bitrate: float
    packets_sent: int
    errors: int

@dataclass  
class SpectrumFrame:
    frequencies: List[float]  # Hz
    power_db: List[float]     # dB
    timestamp: float

@dataclass
class TelemetryPacket:
    data: bytes
    parsed: str
    rssi: float
    snr: float
    timestamp: float

@dataclass
class DeviceInfo:
    serial: str
    label: str
    connected: bool
    frequency: float
    sample_rate: float
    gains: Dict[str, float]

# WebSocket Message Types
WS_CMD_START_PIPELINE = "start_pipeline"
WS_CMD_STOP_PIPELINE = "stop_pipeline"  
WS_CMD_START_TX = "start_tx"
WS_CMD_STOP_TX = "stop_tx"
WS_CMD_SET_FREQ = "set_frequency"
WS_CMD_SET_GAIN = "set_gain"
WS_EVT_STATUS = "status"
WS_EVT_SPECTRUM = "spectrum"
WS_EVT_TELEMETRY = "telemetry"
WS_EVT_PIPELINE = "pipeline"
```
