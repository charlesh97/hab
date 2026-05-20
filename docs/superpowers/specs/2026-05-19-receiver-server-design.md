# Receiver Server Design

**Date:** 2026-05-19  
**Status:** Approved  
**Scope:** New FastAPI-based receiver server that manages HackRF, decodes BPSK packet telemetry, streams results to a web dashboard via WebSocket.

---

## 1. System Architecture

Three components:

```
+-----------------------------------------------------+
|  web-dashboard/  (React + Vite SPA)                 |
|  - Telemetry display, RF config, packet log         |
|  - WebSocket client (single persistent connection)  |
+---------------------+-------------------------------+
                      | ws://localhost:8000/ws
                      |
+---------------------+-------------------------------+
|  receiver-server/  (FastAPI + uvicorn)              |
|                                                     |
|  +--------------+  +------------------+             |
|  | WS Manager   |  | REST Endpoints   |             |
|  | broadcast    |  | /api/devices     |             |
|  | packets +    |  | /api/packets     |             |
|  | status +     |  | /api/receiver/*  |             |
|  | spectrum     |  | /health          |             |
|  +------+------+  +------------------+             |
|         |                                           |
|  +------+------+                                    |
|  | ReceiverMgr |  async, runs in event loop        |
|  | start/stop/ |                                    |
|  | configure   |                                    |
|  +------+------+                                    |
|         |                                           |
|  +------+------+                                    |
|  | PacketRX    |  wraps packet/src/ code            |
|  | BPSK -> FEC |  IQ samples -> bytes -> JSON       |
|  | -> CRC->JSON|                                    |
|  +------+------+                                    |
|         |                                           |
|  +------+------+                                    |
|  | SoapySDR    |  HackRF driver                     |
|  +-------------+                                    |
+-----------------------------------------------------+
```

### Key Design Decisions

- **Receiver runs in the same process as FastAPI** — an async task on the same event loop, yields decoded packets via an `asyncio.Queue`. No separate process needed.
- **Dashboard connects via a single WebSocket** — bidirectional, no REST polling or SSE needed.
- **PacketRX wraps existing code** from `rf-link/packet/src/` (`pkt_enhanced_rx`, `packet_codec`, `fec_cc`) — imported as a library, not modified.
- **HabEngine is not used** for the receiver path. This server replaces the RX-side responsibilities.

---

## 2. WebSocket Protocol & Data Models

### 2.1 Server → Dashboard Messages

**`packet`** — decoded telemetry JSON, streamed in real-time:

```json
{
  "type": "packet",
  "data": {
    "v": 1,
    "id": "HAB001",
    "mid": "donner-01",
    "seq": 18429,
    "t": "2026-05-19T04:22:41Z",
    "type": "environment",
    "temp_ext_c": -42.6,
    "temp_int_c": 12.4,
    "pressure_hpa": 72.8,
    "humidity_pct": 4.2,
    "baro_alt_m": 18190.5
  }
}
```

**`status`** — receiver health, pushed periodically (~1 Hz):

```json
{
  "type": "status",
  "data": {
    "running": true,
    "state": "running",
    "freq_hz": 433500000,
    "sample_rate": 2000000,
    "gain_lna": 32,
    "gain_vga": 30,
    "gain_amp": 0,
    "packets_total": 847,
    "packets_valid": 823,
    "symbol_rate": 100000,
    "sps": 20,
    "signal_strength_db": -42.3,
    "lock": true,
    "fo_hz": 1234.5
  }
}
```

**`spectrum`** — power spectrum computed from IQ stream (~5 Hz):

```json
{
  "type": "spectrum",
  "data": {
    "fc_hz": 433500000,
    "span_hz": 2000000,
    "points": [-85.2, -84.1, -90.3, "...256 total..."],
    "ts": 1716072000.123
  }
}
```

**`error`** — async notifications:

```json
{
  "type": "error",
  "data": {
    "code": "DEVICE_LOST",
    "message": "HackRF disconnected"
  }
}
```

### 2.2 Dashboard → Server Commands

**`cmd:start`** — start the receiver:

```json
{"type": "cmd:start", "data": {"freq_hz": 433500000, "gain_lna": 32, "gain_vga": 30, "gain_amp": 0}}
```

**`cmd:stop`** — stop the receiver:

```json
{"type": "cmd:stop", "data": {}}
```

**`cmd:configure`** — update params on-the-fly (not all params are hot-reloadable; freq/gain changes take effect on next chunk read cycle):

```json
{"type": "cmd:configure", "data": {"freq_hz": 440000000, "gain_lna": 40}}
```

### 2.3 REST Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/devices` | List attached HackRF serials |
| GET | `/api/packets?since=<seq>` | Historical packets from ring buffer (catch-up after reconnect) |
| GET | `/health` | Liveness check |

---

## 3. Pydantic Models

Telemetry packets use discriminated unions by `type`:

```python
class AccelData(BaseModel):
    x: float; y: float; z: float

class GyroData(BaseModel):
    r: float; p: float; y: float

class AttData(BaseModel):
    roll: float; pitch: float; yaw: float

class RailsVData(BaseModel):
    v5: float; v3v3: float; v1v8: float

class EnvironmentPayload(BaseModel):
    type: Literal["environment"]
    temp_ext_c: float; temp_int_c: float
    pressure_hpa: float; humidity_pct: float
    baro_alt_m: float

class MotionPayload(BaseModel):
    type: Literal["motion"]
    gs_mps: float; vs_mps: float
    heading_deg: float; cog_deg: float
    accel: AccelData; gyro_dps: GyroData; att_deg: AttData

class PositionPayload(BaseModel):
    type: Literal["position"]
    lat: float; lon: float
    alt_m: float; agl_m: float
    fix: bool; fix_type: str
    sats: int; hdop: float; vdop: float

class PowerPayload(BaseModel):
    type: Literal["power"]
    bat_v: float; bat_a: float; bat_w: float
    bat_pct: int; bat_temp_c: float
    rails_v: RailsVData

TelemetryPacket = Annotated[
    Union[EnvironmentPayload, MotionPayload, PositionPayload, PowerPayload],
    Field(discriminator="type")
]

class WsPacket(BaseModel):
    type: Literal["packet"]
    data: object  # raw dict, validated lazily

class WsStatus(BaseModel):
    type: Literal["status"]
    data: ReceiverStatus

class WsSpectrum(BaseModel):
    type: Literal["spectrum"]
    data: SpectrumFrame

class WsError(BaseModel):
    type: Literal["error"]
    data: ErrorInfo
```

Header fields (`v`, `id`, `mid`, `seq`, `t`, `type`) are validated at the `TelemetryPacket` level. The raw payload dict is passed through as `data: object` in the WS message envelope.

---

## 4. PacketRX Module (Async Bridge)

The existing `pkt_enhanced_rx.py` is synchronous (blocking SoapySDR C extension calls). It is wrapped in an async bridge:

```python
class AsyncPacketReceiver:
    def __init__(self, packet_queue: asyncio.Queue, spectrum_queue: asyncio.Queue):
        self._packet_queue = packet_queue
        self._spectrum_queue = spectrum_queue
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def start(self, config: ReceiverConfig):
        self._running = True
        # LiveReceiver is instantiated from pkt_enhanced_rx.py
        self._receiver = LiveReceiver(...)
        self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self):
        loop = asyncio.get_event_loop()
        chunk_count = 0
        while self._running:
            # Blocking SDR I/O offloaded to thread pool
            raw_bytes = await loop.run_in_executor(
                self._executor,
                self._receiver.read_chunk
            )
            if raw_bytes:
                payload = packet_decode(raw_bytes)
                if payload:
                    await self._packet_queue.put(json.loads(payload))
            # Spectrum: every ~20th chunk (approximately 5 Hz)
            chunk_count += 1
            if chunk_count % 20 == 0:
                spectrum = self._compute_spectrum()
                await self._spectrum_queue.put(spectrum)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        self._executor.shutdown(wait=True)

    def _compute_spectrum(self) -> SpectrumFrame:
        # FFT -> magnitude -> dB -> 256-point array
        ...
```

### Key Design Points

- **Thread pool executor** (`max_workers=1`) for blocking SoapySDR reads — keeps the event loop free.
- **Two asyncio.Queues** bridge receiver thread → WebSocket broadcast — non-blocking, backpressure-aware.
- `LiveReceiver` from `pkt_enhanced_rx.py` is used as-is (import, don't modify).
- Config hot-reload: atomic variable checked at start of each read cycle.
- Spectrum computation uses the same IQ stream — no second HackRF session or `hackrf_sweep` subprocess.

---

## 5. Project Structure

```
hab/
├── rf-link/                    # Unchanged
│   ├── packet/src/             # Imported as library by receiver-server
│   └── dvbs2/                  # Future: imported for DVB-S2 mode
├── receiver-server/            # NEW
│   ├── main.py                 # FastAPI app creation, uvicorn launcher
│   ├── config.py               # Settings, env vars, defaults
│   ├── packet_rx.py            # AsyncPacketReceiver wrapper
│   ├── receiver_manager.py     # ReceiverMgr: lifecycle, state machine
│   ├── ws_manager.py           # WebSocket connection multiplexer + broadcast
│   ├── models.py               # Pydantic models (packets, status, config, ws messages)
│   ├── schemas.py              # API request/response schemas
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── ws.py               # /ws endpoint + command dispatch
│   │   └── rest.py             # /api/devices, /api/packets, /health
│   ├── dvbs2_rx.py             # FUTURE: AsyncDvbs2Receiver wrapper
│   ├── requirements.txt        # fastapi, uvicorn, pydantic, numpy, SoapySDR
│   └── launch.sh               # uvicorn main:app --host 0.0.0.0 --port 8000
├── web-dashboard/              # To be replaced separately
└── hab-gui/                    # Legacy (TX path may still be used)
```

`rf-link/packet/src/` is never modified. Imported via `sys.path` manipulation or pip editable install.

---

## 6. Receiver State Machine

```
                    cmd:start
    IDLE +---+--------------------------->> STARTING
      ^    |                                   |
      |    |                                   v
      |    |          +--------------+    RUNNING
      |    |          | errors:       |       |
      |    |          | DEVICE_LOST   |       | cmd:stop
      |    |          | SIGNAL_LOST   |       |
      |    |          | HARDWARE_ERR  |       v
      |    |          +-------|-------+    STOPPING
      |    |                  |              |
      +----+------------------+--------------+
                    (auto cleanup)          IDLE
```

### States

| State | Description |
|-------|-------------|
| `IDLE` | No receiver active. Can list devices, query history. |
| `STARTING` | SoapySDR opening, FO scanning. Dashboard shows loading. |
| `RUNNING` | Actively decoding. Packets streaming, status ticking. |
| `STOPPING` | Graceful shutdown (stop SDR, drain queue). |
| `ERROR` | Unrecoverable fault. `status.running=false` with error detail. |

### Transition Rules

- `cmd:start` — valid only in `IDLE` or `ERROR`
- `cmd:stop` — valid only in `RUNNING` (no-op in other states)
- `cmd:configure` — valid only in `RUNNING`
- `STARTING → ERROR` if SDR open fails (no device, busy, hardware fault)
- `RUNNING → ERROR` if SDR stream dies (USB disconnect, buffer overflow)
- `STOPPING → IDLE` after SDR closed and async task joined

---

## 7. Error Recovery

**No error leaves the server in a zombie state.** Recovery is automatic:

```
RUNNING -- error detected --> CLEANUP (automatic)
                                |
                                +-- Close SoapySDR stream
                                +-- Cancel receiver async task
                                +-- Drain remaining packets from queue
                                +-- Reset signal pipeline state
                                |
                                v
                              IDLE
                                |
                        broadcast: {"type":"status", "data":{"running":false, "last_error":"..."}}
```

### Error Categories

| Error | Severity | Recovery |
|-------|----------|----------|
| `DEVICE_LOST` | Fatal | Close handle, transition to IDLE. Dashboard can `cmd:start` to retry. |
| `HARDWARE_ERR` | Fatal | Same — may need physical intervention, but server stays up. |
| `DECODE_ERR` | Non-fatal | Skip bad packet, stay in RUNNING. Per-packet CRC failures do not crash. |
| `API_ERROR` | Non-fatal | Log it, server stays up, connection unaffected. |

**Cleanup guarantee:** After any `_cleanup()` call, the SoapySDR handle is closed and the receiver task is cancelled. A subsequent `cmd:start` will always work (assuming hardware is available).

---

## 8. Spectrum from IQ Stream

Spectrum data is computed from the same IQ stream used for packet decoding — no second HackRF process.

- **Every ~20th IQ chunk** (approximately 5 Hz): compute FFT, magnitude squared, dBFS, downsample to 256 points.
- Pushed to `spectrum_queue`, then broadcast via the same WebSocket connection.
- The dashboard's `SpectrumWaterfall.tsx` component consumes this identically to how it consumed SSE data previously.

```json
{
  "type": "spectrum",
  "data": {
    "fc_hz": 433500000,
    "span_hz": 2000000,
    "points": [-85.2, -84.1, -90.3, ...],
    "ts": 1716072000.123
  }
}
```

---

## 9. Packet Buffer (Reconnect Catch-Up)

A ring buffer of the last N decoded packets (N=1000) is maintained in memory.

- `GET /api/packets?since=<seq>` returns all buffered packets with `seq > since`.
- Allows the dashboard to catch up after a WebSocket reconnect without gaps.
- Buffer is a `collections.deque` with `maxlen=1000`.

---

## 10. Future DVB-S2 Video Path

When DVB-S2 mode is added later:

- `AsyncDvbs2Receiver` wraps the GNU Radio flowgraph from `dvbs2/rx.py` using the same pattern: `run_in_executor` for `gr.top_block`.
- MPEG-TS output goes to a sink (file, UDP, or pipe) — can be streamed to the dashboard or saved to disk.
- The `ReceiverMgr` state machine handles mode switching (`packet` vs `dvbs2`) — only one mode active at a time per HackRF (shared device constraint).
- The API surfaces DVB-S2-specific parameters: `modcod`, `rolloff`, `pilots`, `fec_frame` size.

---

## 11. Non-Goals

- TX (transmit) functionality — out of scope for this server. TX may remain in hab-gui or be added later.
- GNU Radio hierarchical blocks (`packet/debug/`) — not used. Production path uses `pkt_enhanced_rx.py` only.
- HabEngine integration — not used. This server replaces the RX side of HabEngine.
- Dashboard replacement — this spec covers the receiver server only. Dashboard replacement is a separate effort.
