# Receiver Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI receiver server at `hab/receiver-server/` that manages a HackRF via SoapySDR, decodes BPSK packet telemetry using `rf-link/packet/src/` as a library, and streams decoded packets, spectrum, and status to the web dashboard over a single WebSocket connection.

**Architecture:** Single async process (FastAPI + uvicorn). Synchronous SDR I/O runs in a thread pool executor via `asyncio.get_event_loop().run_in_executor`. Results flow through `asyncio.Queue` to a bridge coroutine that broadcasts via `WebSocketManager`. A `ReceiverManager` state machine (`IDLE → STARTING → RUNNING → STOPPING → IDLE`) governs lifecycle with automatic error recovery.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, Pydantic v2, numpy, SoapySDR, pytest + httpx (testing).

---

## File Structure

```
receiver-server/
├── main.py               # FastAPI app creation, uvicorn launcher
├── config.py             # ServerConfig, ReceiverConfig, ReceiverDefaults
├── models.py             # Pydantic models (telemetry packets, status, ws messages)
├── ws_manager.py         # WebSocketManager: connection tracking, broadcast
├── receiver_manager.py   # ReceiverManager: state machine, lifecycle
├── packet_rx.py          # ReceiverWorker (sync SDR) + AsyncPacketReceiver (async bridge)
├── routes/
│   ├── __init__.py
│   ├── ws.py             # /ws WebSocket endpoint + command dispatch
│   └── rest.py           # /api/devices, /api/packets, /health
├── requirements.txt
├── launch.sh
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_receiver_manager.py
    ├── test_ws_manager.py
    ├── test_routes.py
    └── conftest.py
```

---

### Task 1: Project Skeleton

**Files:**
- Create: `receiver-server/requirements.txt`
- Create: `receiver-server/launch.sh`
- Create: `receiver-server/routes/__init__.py`
- Create: `receiver-server/tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p receiver-server/routes receiver-server/tests
```

- [ ] **Step 2: Write requirements.txt**

```bash
cat > receiver-server/requirements.txt << 'EOF'
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0.0
numpy>=1.24.0
SoapySDR>=0.8.0
EOF
```

- [ ] **Step 3: Write launch.sh**

```bash
cat > receiver-server/launch.sh << 'EOF'
#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HAB_ROOT="$(dirname "$SCRIPT_DIR")"

export PYTHONPATH="${HAB_ROOT}/rf-link/packet/src:${HAB_ROOT}/rf-link/dvbs2:${PYTHONPATH:-}"

HOST="${HAB_HOST:-0.0.0.0}"
PORT="${HAB_PORT:-8000}"

echo "Starting receiver server on ${HOST}:${PORT}..."
exec python -m uvicorn main:app --host "${HOST}" --port "${PORT}" --log-level info
EOF
chmod +x receiver-server/launch.sh
```

- [ ] **Step 4: Write empty __init__ files**

```python
# receiver-server/routes/__init__.py (empty)
# receiver-server/tests/__init__.py (empty)
```

- [ ] **Step 5: Install dependencies**

```bash
cd receiver-server && pip install -r requirements.txt
```

- [ ] **Step 6: Verify uvicorn can import**

```bash
python -c "import fastapi; import uvicorn; import pydantic; print('OK')"
```
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
cd /Users/charlesclaw/Documents/git/hab && git add receiver-server/ && git commit -m "feat: add receiver-server project skeleton"
```

---

### Task 2: Pydantic Models

**Files:**
- Create: `receiver-server/models.py`
- Create: `receiver-server/tests/test_models.py`
- Create: `receiver-server/tests/conftest.py`

- [ ] **Step 1: Write conftest.py**

```python
# receiver-server/tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 2: Write failing model tests**

```python
# receiver-server/tests/test_models.py
import pytest
from pydantic import ValidationError
from models import (
    EnvironmentPayload, MotionPayload, PositionPayload, PowerPayload,
    AccelData, GyroData, AttData, RailsVData,
    ReceiverStatus, ReceiverState, SpectrumFrame, ErrorInfo, ErrorCode,
    WsPacketMessage, WsStatusMessage, WsSpectrumMessage, WsErrorMessage,
    CmdStart, CmdStop, CmdConfigure,
)


class TestTelemetryPayloads:
    def test_environment_payload_valid(self):
        pkt = EnvironmentPayload(
            type="environment", temp_ext_c=-42.6, temp_int_c=12.4,
            pressure_hpa=72.8, humidity_pct=4.2, baro_alt_m=18190.5,
        )
        assert pkt.type == "environment"
        assert pkt.temp_ext_c == -42.6

    def test_environment_payload_wrong_type_rejected(self):
        with pytest.raises(ValidationError):
            EnvironmentPayload(
                type="motion", temp_ext_c=-42.6, temp_int_c=12.4,
                pressure_hpa=72.8, humidity_pct=4.2, baro_alt_m=18190.5,
            )

    def test_environment_payload_missing_field(self):
        with pytest.raises(ValidationError):
            EnvironmentPayload(type="environment", temp_ext_c=-42.6)

    def test_motion_payload_valid(self):
        pkt = MotionPayload(
            type="motion", gs_mps=13.8, vs_mps=5.4,
            heading_deg=72.6, cog_deg=74.1,
            accel={"x": 0.03, "y": -0.08, "z": 9.71},
            gyro_dps={"r": 0.4, "p": -0.2, "y": 1.1},
            att_deg={"roll": 2.8, "pitch": -4.1, "yaw": 71.9},
        )
        assert pkt.accel.x == 0.03

    def test_motion_payload_nested_validation(self):
        with pytest.raises(ValidationError):
            MotionPayload(
                type="motion", gs_mps=13.8, vs_mps=5.4,
                heading_deg=72.6, cog_deg=74.1,
                accel={"x": "bad"}, gyro_dps={"r": 0}, att_deg={"roll": 0, "pitch": 0, "yaw": 0},
            )

    def test_position_payload_valid(self):
        pkt = PositionPayload(
            type="position", lat=39.318742, lon=-120.328915,
            alt_m=18342.7, agl_m=17210.3,
            fix=True, fix_type="3d", sats=14, hdop=0.82, vdop=1.34,
        )
        assert pkt.fix is True

    def test_power_payload_valid(self):
        pkt = PowerPayload(
            type="power", bat_v=7.62, bat_a=0.84, bat_w=6.4,
            bat_pct=68, bat_temp_c=8.1,
            rails_v={"v5": 5.03, "v3v3": 3.31, "v1v8": 1.79},
        )
        assert pkt.bat_pct == 68


class TestSubModels:
    def test_accel_data_from_dict(self):
        a = AccelData(x=0.03, y=-0.08, z=9.71)
        assert a.z == 9.71

    def test_rails_v_from_dict(self):
        r = RailsVData(v5=5.03, v3v3=3.31, v1v8=1.79)
        assert r.v3v3 == 3.31


class TestReceiverStatus:
    def test_defaults(self):
        s = ReceiverStatus(running=False, state=ReceiverState.IDLE)
        assert s.freq_hz == 0
        assert s.packets_total == 0

    def test_serialization(self):
        s = ReceiverStatus(
            running=True, state=ReceiverState.RUNNING,
            freq_hz=433500000, gain_lna=32, packets_total=42, packets_valid=40,
        )
        d = s.model_dump()
        assert d["state"] == "running"
        assert d["packets_valid"] == 40


class TestWsMessages:
    def test_packet_message(self):
        msg = WsPacketMessage(type="packet", data={"v": 1, "type": "environment", "temp_ext_c": -42.6})
        assert msg.type == "packet"
        d = msg.model_dump()
        assert d["data"]["temp_ext_c"] == -42.6

    def test_status_message(self):
        status = ReceiverStatus(running=False, state=ReceiverState.IDLE)
        msg = WsStatusMessage(type="status", data=status)
        assert msg.data.state == ReceiverState.IDLE

    def test_spectrum_message(self):
        spectrum = SpectrumFrame(fc_hz=433500000, span_hz=2000000, points=[-85.2, -84.1], ts=1716072000.123)
        msg = WsSpectrumMessage(type="spectrum", data=spectrum)
        assert len(msg.data.points) == 2

    def test_error_message(self):
        err = ErrorInfo(code=ErrorCode.DEVICE_LOST, message="HackRF disconnected")
        msg = WsErrorMessage(type="error", data=err)
        assert msg.data.code == ErrorCode.DEVICE_LOST

    def test_cmd_start_valid(self):
        cmd = CmdStart(type="cmd:start", data={"freq_hz": 433500000, "gain_lna": 32, "gain_vga": 30, "gain_amp": 0})
        assert cmd.data.freq_hz == 433500000

    def test_cmd_stop(self):
        cmd = CmdStop(type="cmd:stop")
        assert cmd.type == "cmd:stop"

    def test_cmd_configure_partial(self):
        cmd = CmdConfigure(type="cmd:configure", data={"gain_lna": 40})
        assert cmd.data.gain_lna == 40
```

- [ ] **Step 3: Run tests (expect all to fail with import error)**

```bash
cd receiver-server && python -m pytest tests/test_models.py -v
```
Expected: ImportError (models module not found)

- [ ] **Step 4: Write models.py**

```python
# receiver-server/models.py
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel


class AccelData(BaseModel):
    x: float
    y: float
    z: float


class GyroData(BaseModel):
    r: float
    p: float
    y: float


class AttData(BaseModel):
    roll: float
    pitch: float
    yaw: float


class RailsVData(BaseModel):
    v5: float
    v3v3: float
    v1v8: float


class EnvironmentPayload(BaseModel):
    type: Literal["environment"]
    temp_ext_c: float
    temp_int_c: float
    pressure_hpa: float
    humidity_pct: float
    baro_alt_m: float


class MotionPayload(BaseModel):
    type: Literal["motion"]
    gs_mps: float
    vs_mps: float
    heading_deg: float
    cog_deg: float
    accel: AccelData
    gyro_dps: GyroData
    att_deg: AttData


class PositionPayload(BaseModel):
    type: Literal["position"]
    lat: float
    lon: float
    alt_m: float
    agl_m: float
    fix: bool
    fix_type: str
    sats: int
    hdop: float
    vdop: float


class PowerPayload(BaseModel):
    type: Literal["power"]
    bat_v: float
    bat_a: float
    bat_w: float
    bat_pct: int
    bat_temp_c: float
    rails_v: RailsVData


class ReceiverState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class ReceiverStatus(BaseModel):
    running: bool = False
    state: ReceiverState = ReceiverState.IDLE
    freq_hz: int = 0
    sample_rate: int = 0
    gain_lna: int = 0
    gain_vga: int = 0
    gain_amp: int = 0
    packets_total: int = 0
    packets_valid: int = 0
    symbol_rate: int = 100_000
    sps: int = 20
    signal_strength_db: float = 0.0
    lock: bool = False
    fo_hz: float = 0.0
    last_error: str = ""


class SpectrumFrame(BaseModel):
    fc_hz: int
    span_hz: int
    points: list[float]
    ts: float


class ErrorCode(str, Enum):
    DEVICE_LOST = "DEVICE_LOST"
    SIGNAL_LOST = "SIGNAL_LOST"
    HARDWARE_ERR = "HARDWARE_ERR"


class ErrorInfo(BaseModel):
    code: ErrorCode
    message: str


class WsPacketMessage(BaseModel):
    type: Literal["packet"]
    data: dict


class WsStatusMessage(BaseModel):
    type: Literal["status"]
    data: ReceiverStatus


class WsSpectrumMessage(BaseModel):
    type: Literal["spectrum"]
    data: SpectrumFrame


class WsErrorMessage(BaseModel):
    type: Literal["error"]
    data: ErrorInfo


class CmdStart(BaseModel):
    type: Literal["cmd:start"]
    data: "ReceiverConfig"


class CmdStop(BaseModel):
    type: Literal["cmd:stop"]
    data: dict = {}


class CmdConfigure(BaseModel):
    type: Literal["cmd:configure"]
    data: "ReceiverConfig"

```

- [ ] **Step 5: Run tests (expect all to pass)**

```bash
cd receiver-server && python -m pytest tests/test_models.py -v
```
Expected: 14 passed

- [ ] **Step 6: Commit**

```bash
cd /Users/charlesclaw/Documents/git/hab && git add receiver-server/models.py receiver-server/tests/ && git commit -m "feat: add Pydantic models for telemetry packets, status, and WS messages"
```

---

### Task 3: Config Dataclasses

**Files:**
- Create: `receiver-server/config.py`

- [ ] **Step 1: Write config.py**

```python
# receiver-server/config.py
from dataclasses import dataclass, field


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    packet_buffer_size: int = 1000
    status_interval_sec: float = 1.0
    spectrum_points: int = 256
    spectrum_chunk_interval: int = 20


@dataclass
class ReceiverConfig:
    freq_hz: int = 433_500_000
    sample_rate: int = 2_000_000
    symbol_rate: int = 100_000
    sps: int = 20
    gain_lna: int = 32
    gain_vga: int = 30
    gain_amp: int = 0
    serial: str | None = None
```

- [ ] **Step 2: Verify import**

```bash
cd receiver-server && python -c "from config import ServerConfig, ReceiverConfig; rc = ReceiverConfig(); assert rc.freq_hz == 433500000; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/charlesclaw/Documents/git/hab && git add receiver-server/config.py && git commit -m "feat: add config dataclasses"
```

---

### Task 4: Fix Forward Reference in models.py

`CmdStart` and `CmdConfigure` reference `ReceiverConfig` which is defined in `config.py`. We need to resolve this circular reference.

- [ ] **Step 1: Add typing_extensions check, fix models.py**

```python
# At the top of models.py, add:
from __future__ import annotations
```

Replace the bottom of models.py:

```python
# Remove CmdStart, CmdStop, CmdConfigure from models.py entirely.
# They will be moved to schemas.py in Task 7.
```

Actually, we can fix this by removing the forward refs and just using `dict`:

The `data` field uses `"ReceiverConfig"` but that class is in `config.py`. We move command models to `schemas.py` in Task 7. For now in models.py, use `dict`:

```python
class CmdStart(BaseModel):
    type: Literal["cmd:start"]
    data: dict

class CmdStop(BaseModel):
    type: Literal["cmd:stop"]
    data: dict = {}

class CmdConfigure(BaseModel):
    type: Literal["cmd:configure"]
    data: dict
```

- [ ] **Step 2: Update test_models.py to match**

```python
def test_cmd_start_valid(self):
    cmd = CmdStart(type="cmd:start", data={"freq_hz": 433500000, "gain_lna": 32, "gain_vga": 30, "gain_amp": 0})
    assert cmd.data["freq_hz"] == 433500000

def test_cmd_configure_partial(self):
    cmd = CmdConfigure(type="cmd:configure", data={"gain_lna": 40})
    assert cmd.data["gain_lna"] == 40
```

- [ ] **Step 3: Run tests**

```bash
cd receiver-server && python -m pytest tests/test_models.py -v
```
Expected: 14 passed

- [ ] **Step 4: Commit**

```bash
cd /Users/charlesclaw/Documents/git/hab && git add receiver-server/models.py receiver-server/tests/test_models.py && git commit -m "fix: remove forward refs from command models, use dict for data"
```

---

### Task 5: WebSocket Manager

**Files:**
- Create: `receiver-server/ws_manager.py`
- Create: `receiver-server/tests/test_ws_manager.py`

- [ ] **Step 1: Write failing test**

```python
# receiver-server/tests/test_ws_manager.py
import json
import pytest
import asyncio
from ws_manager import WebSocketManager
from models import ReceiverStatus, ReceiverState, SpectrumFrame


class MockWebSocket:
    def __init__(self):
        self.sent: list[str] = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, data: str):
        self.sent.append(data)


class TestWebSocketManager:

    async def test_connect(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        assert ws.accepted is True
        assert mgr.connection_count == 1

    async def test_disconnect(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        await mgr.disconnect(ws)
        assert mgr.connection_count == 0

    async def test_broadcast_to_multiple(self):
        mgr = WebSocketManager()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await mgr.connect(ws1)
        await mgr.connect(ws2)
        await mgr.broadcast({"type": "status", "data": {"running": True}})
        assert len(ws1.sent) == 1
        assert len(ws2.sent) == 1
        payload1 = json.loads(ws1.sent[0])
        assert payload1["type"] == "status"

    async def test_broadcast_packet(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        await mgr.broadcast_packet({"type": "environment", "temp_ext_c": -42.6})
        payload = json.loads(ws.sent[0])
        assert payload["type"] == "packet"
        assert payload["data"]["type"] == "environment"

    async def test_broadcast_status(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        status = ReceiverStatus(running=True, state=ReceiverState.RUNNING, freq_hz=433500000)
        await mgr.broadcast_status(status)
        payload = json.loads(ws.sent[0])
        assert payload["data"]["state"] == "running"

    async def test_broadcast_spectrum(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        spectrum = SpectrumFrame(fc_hz=433500000, span_hz=2000000, points=[-85.2, -84.1], ts=1716072000.123)
        await mgr.broadcast_spectrum(spectrum)
        payload = json.loads(ws.sent[0])
        assert payload["data"]["fc_hz"] == 433500000

    async def test_broadcast_error(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        await mgr.broadcast_error("DEVICE_LOST", "HackRF disconnected")
        payload = json.loads(ws.sent[0])
        assert payload["type"] == "error"
        assert payload["data"]["code"] == "DEVICE_LOST"

    async def test_dead_connection_removed(self):
        mgr = WebSocketManager()

        class FailingWS:
            sent = []; accepted = False

            async def accept(self):
                self.accepted = True

            async def send_text(self, data: str):
                raise Exception("connection lost")

        ws = FailingWS()
        await mgr.connect(ws)
        assert mgr.connection_count == 1
        await mgr.broadcast({"type": "status", "data": {}})
        assert mgr.connection_count == 0

    async def test_command_queue(self):
        mgr = WebSocketManager()
        cmd = {"type": "cmd:start", "data": {"freq_hz": 433500000}}
        mgr.push_command(cmd)
        received = await mgr.get_command()
        assert received == cmd
```

- [ ] **Step 2: Run tests (expect failure)**

```bash
cd receiver-server && python -m pytest tests/test_ws_manager.py -v
```
Expected: ImportError

- [ ] **Step 3: Write ws_manager.py**

```python
# receiver-server/ws_manager.py
import asyncio
import json
from fastapi import WebSocket
from models import ReceiverStatus, SpectrumFrame


class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket | object] = []
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def connect(self, ws):
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)

    async def disconnect(self, ws):
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        text = json.dumps(message)
        async with self._lock:
            conns = list(self._connections)
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    async def broadcast_packet(self, packet: dict):
        await self.broadcast({"type": "packet", "data": packet})

    async def broadcast_status(self, status: ReceiverStatus):
        await self.broadcast({"type": "status", "data": status.model_dump()})

    async def broadcast_spectrum(self, spectrum: SpectrumFrame):
        await self.broadcast({"type": "spectrum", "data": spectrum.model_dump()})

    async def broadcast_error(self, code: str, message: str):
        await self.broadcast({"type": "error", "data": {"code": code, "message": message}})

    def push_command(self, message: dict):
        self._command_queue.put_nowait(message)

    async def get_command(self) -> dict:
        return await self._command_queue.get()
```

- [ ] **Step 4: Run tests**

```bash
cd receiver-server && python -m pytest tests/test_ws_manager.py -v
```
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/charlesclaw/Documents/git/hab && git add receiver-server/ws_manager.py receiver-server/tests/test_ws_manager.py && git commit -m "feat: add WebSocketManager with broadcast and connection tracking"
```

---

### Task 6: Receiver Manager (State Machine)

**Files:**
- Create: `receiver-server/receiver_manager.py`
- Create: `receiver-server/tests/test_receiver_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# receiver-server/tests/test_receiver_manager.py
import pytest
import asyncio
import json
from receiver_manager import ReceiverManager, InvalidStateError
from ws_manager import WebSocketManager
from config import ReceiverConfig
from models import ReceiverState


class MockWebSocket:
    def __init__(self):
        self.sent: list[str] = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, data: str):
        self.sent.append(data)


class TestReceiverStateMachine:

    @pytest.fixture
    async def manager(self):
        ws_mgr = WebSocketManager()
        config = ReceiverConfig()
        mgr = ReceiverManager(ws_mgr, config)
        return mgr

    async def test_initial_state_is_idle(self, manager):
        assert manager.state == ReceiverState.IDLE

    async def test_cannot_stop_when_idle(self, manager):
        await manager.stop()

    async def test_cannot_configure_when_idle(self, manager):
        result = await manager.configure({"gain_lna": 40})
        assert result is None

    async def test_start_transitions_to_run_then_stop_returns_to_idle(self, manager):
        manager._start_receiver = lambda: None
        manager._stop_receiver = lambda: None
        manager._bridge_task = asyncio.current_task()
        manager._status_task = asyncio.current_task()

        await manager.start()
        assert manager.state == ReceiverState.RUNNING

        await manager.stop()
        assert manager.state == ReceiverState.IDLE

    async def test_start_from_error_state(self, manager):
        manager._state = ReceiverState.ERROR
        manager._start_receiver = lambda: None
        manager._stop_receiver = lambda: None
        manager._bridge_task = asyncio.current_task()
        manager._status_task = asyncio.current_task()

        await manager.start()
        assert manager.state == ReceiverState.RUNNING

    async def test_cannot_start_when_running(self, manager):
        manager._start_receiver = lambda: None
        manager._stop_receiver = lambda: None
        manager._bridge_task = asyncio.current_task()
        manager._status_task = asyncio.current_task()

        await manager.start()
        with pytest.raises(InvalidStateError):
            await manager.start()

    async def test_status_broadcast_on_state_change(self, manager):
        mgr = MockWebSocket()
        # replace ws_manager with a fresh one that has our mock
        ws_mgr = WebSocketManager()
        await ws_mgr.connect(mgr)
        manager._ws = ws_mgr

        manager._start_receiver = lambda: None
        manager._stop_receiver = lambda: None
        manager._bridge_task = asyncio.current_task()
        manager._status_task = asyncio.current_task()

        await manager.start()
        await asyncio.sleep(0)
        assert len(mgr.sent) >= 1
        start_msg = json.loads(mgr.sent[0])
        assert start_msg["data"]["state"] == "starting"

    async def test_error_cleanup_on_start_failure(self, manager):
        def failing_start():
            raise RuntimeError("SDR not found")
        manager._start_receiver = failing_start

        try:
            await manager.start()
        except RuntimeError:
            pass

        assert manager.state == ReceiverState.IDLE
        assert manager._receiver is None
        assert manager._bridge_task is None
        assert manager._status_task is None

    async def test_configure_updates_config(self, manager):
        manager._start_receiver = lambda: None
        manager._stop_receiver = lambda: None
        manager._bridge_task = asyncio.current_task()
        manager._status_task = asyncio.current_task()

        await manager.start()
        await manager.configure({"gain_lna": 40, "freq_hz": 440000000})
        assert manager._config.gain_lna == 40
        assert manager._config.freq_hz == 440000000

    async def test_packet_buffer(self, manager):
        assert manager.packet_buffer == []
```

- [ ] **Step 2: Run tests (expect failure)**

```bash
cd receiver-server && python -m pytest tests/test_receiver_manager.py -v
```
Expected: ImportError

- [ ] **Step 3: Write receiver_manager.py**

```python
# receiver-server/receiver_manager.py
import asyncio
from collections import deque
from models import ReceiverState, ReceiverStatus, ErrorCode
from config import ReceiverConfig


class InvalidStateError(Exception):
    def __init__(self, state: ReceiverState):
        super().__init__(f"Cannot perform operation in state: {state}")


class ReceiverManager:
    def __init__(self, ws_manager, config: ReceiverConfig):
        self._ws = ws_manager
        self._config = config
        self._state = ReceiverState.IDLE
        self._packet_buffer: deque[dict] = deque(maxlen=1000)
        self._receiver = None
        self._bridge_task: asyncio.Task | None = None
        self._status_task: asyncio.Task | None = None
        self._packets_total = 0
        self._packets_valid = 0
        self._spectrum_frame = None

    @property
    def state(self) -> ReceiverState:
        return self._state

    @property
    def packet_buffer(self) -> list[dict]:
        return list(self._packet_buffer)

    async def start(self):
        if self._state not in (ReceiverState.IDLE, ReceiverState.ERROR):
            raise InvalidStateError(self._state)
        self._state = ReceiverState.STARTING
        await self._ws.broadcast_status(self._build_status())
        try:
            self._start_receiver()
            self._state = ReceiverState.RUNNING
        except Exception:
            await self._cleanup()
            raise

    async def stop(self):
        if self._state != ReceiverState.RUNNING:
            return
        self._state = ReceiverState.STOPPING
        await self._cleanup()
        self._state = ReceiverState.IDLE
        await self._ws.broadcast_status(self._build_status())

    async def configure(self, updates: dict):
        if self._state != ReceiverState.RUNNING:
            return
        for key in ("freq_hz", "gain_lna", "gain_vga", "gain_amp",
                     "symbol_rate", "sps"):
            if key in updates:
                setattr(self._config, key, updates[key])

    def _start_receiver(self):
        pass

    def _stop_receiver(self):
        pass

    async def _cleanup(self):
        self._stop_receiver()
        self._receiver = None
        for task in (self._bridge_task, self._status_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._bridge_task = None
        self._status_task = None

    def _build_status(self) -> ReceiverStatus:
        return ReceiverStatus(
            running=self._state == ReceiverState.RUNNING,
            state=self._state,
            freq_hz=self._config.freq_hz,
            sample_rate=self._config.sample_rate,
            gain_lna=self._config.gain_lna,
            gain_vga=self._config.gain_vga,
            gain_amp=self._config.gain_amp,
            packets_total=self._packets_total,
            packets_valid=self._packets_valid,
            symbol_rate=self._config.symbol_rate,
            sps=self._config.sps,
        )
```

- [ ] **Step 4: Run tests**

```bash
cd receiver-server && python -m pytest tests/test_receiver_manager.py -v
```
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/charlesclaw/Documents/git/hab && git add receiver-server/receiver_manager.py receiver-server/tests/test_receiver_manager.py && git commit -m "feat: add ReceiverManager state machine with lifecycle and error recovery"
```

---

### Task 7: PacketRX — ReceiverWorker (Sync SDR Manager)

**Files:**
- Create: `receiver-server/packet_rx.py`

This file contains two classes:
1. `ReceiverWorker` — synchronous wrapper around SoapySDR + packet decode pipeline
2. `AsyncPacketReceiver` — async bridge using `run_in_executor`

- [ ] **Step 1: Write packet_rx.py with ReceiverWorker**

```python
# receiver-server/packet_rx.py
import time
import asyncio
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from config import ReceiverConfig


class ReceiverWorker:
    """Synchronous SDR manager + signal processing pipeline.

    Uses packet_codec and fec_cc from rf-link/packet/src/ for FEC/CRC.
    Wraps SoapySDR for HackRF control.
    """

    def __init__(self, config: ReceiverConfig):
        self.config = config
        self._sdr = None
        self._rx_stream = None
        self._fo_est = 0.0
        self._chunk_size = 524_288
        self._rrc_taps = None
        self._raw_iq = None

    def open(self) -> None:
        import SoapySDR
        from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32

        args = dict(driver="hackrf")
        if self.config.serial:
            args["serial"] = self.config.serial

        self._sdr = SoapySDR.Device(args)
        self._sdr.setSampleRate(SOAPY_SDR_RX, 0, self.config.sample_rate)
        self._sdr.setFrequency(SOAPY_SDR_RX, 0, self.config.freq_hz)

        try:
            self._sdr.setGain(SOAPY_SDR_RX, 0, "LNA", self.config.gain_lna)
            self._sdr.setGain(SOAPY_SDR_RX, 0, "VGA", self.config.gain_vga)
            self._sdr.setGain(SOAPY_SDR_RX, 0, "AMP", self.config.gain_amp)
        except Exception:
            pass

        self._rx_stream = self._sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        self._sdr.activateStream(self._rx_stream)

        self._init_rrc_filter()

    def _init_rrc_filter(self):
        sps = self.config.sps
        span = 10
        t = np.arange(-span, span + 1e-9, 1 / sps)
        beta = 0.35
        denom = 1.0 - (2.0 * beta * t) ** 2
        with np.errstate(divide="ignore", invalid="ignore"):
            taps = (
                np.sin(np.pi * t * (1 - beta))
                + 4 * beta * t * np.cos(np.pi * t * (1 + beta))
            ) / (np.pi * t * denom + 1e-30)
        taps[np.abs(t) < 1e-9] = 1.0 + beta * (4 / np.pi - 1)
        taps = taps / np.sqrt(np.sum(taps**2))
        self._rrc_taps = taps.astype(np.float32)

    def read_one(self) -> dict | None:
        import SoapySDR
        from SoapySDR import SOAPY_SDR_RX

        buf = np.zeros(self._chunk_size, dtype=np.complex64)
        try:
            sr = self._sdr.readStream(
                self._rx_stream, [buf], self._chunk_size, timeoutUs=5_000_000
            )
        except Exception:
            return None

        if sr.ret <= 0:
            return None

        samples = buf[: sr.ret]
        self._raw_iq = samples
        return self._decode(samples)

    def _decode(self, samples: np.ndarray) -> dict | None:
        from packet.src.packet_codec import packet_decode

        samples = samples - np.mean(samples)
        max_val = np.max(np.abs(samples))
        if max_val < 0.1:
            return None

        t = np.arange(len(samples)) / self.config.sample_rate
        lo = np.exp(-2j * np.pi * self._fo_est * t)
        samples = (samples * lo).astype(np.complex64)
        filtered = np.convolve(samples, self._rrc_taps, mode="same")
        denom = np.sqrt(np.mean(np.abs(filtered) ** 2) + 1e-30)
        filtered = filtered / denom

        sps = self.config.sps
        sync_word_bits = [1, 0, 1, 0, 1, 1, 0, 0,
                         1, 1, 0, 1, 1, 1, 0, 1,
                         1, 0, 1, 0, 0, 1, 0, 0,
                         1, 1, 1, 0, 0, 0, 1, 0]
        sync_symbols = np.array([1 if b else -1 for b in sync_word_bits], dtype=np.float32)
        corr = np.abs(np.correlate(np.real(filtered), sync_symbols, mode="valid"))
        threshold = np.mean(corr) + 2.5 * np.std(corr)
        peaks = np.where(corr > threshold)[0]

        if len(peaks) == 0:
            return None

        peak = peaks[0]
        symbols = np.real(filtered[peak::sps])
        bits = np.where(symbols > 0, 1, 0).astype(np.uint8).tolist()
        bits.extend([0] * 8)
        byte_list = []
        for i in range(0, len(bits) - 7, 8):
            b = 0
            for j in range(8):
                b = (b << 1) | bits[i + j]
            byte_list.append(b)
        payload = packet_decode(bytes(byte_list))
        if payload is None:
            return None
        import json
        return json.loads(payload.decode("utf-8"))

    def compute_spectrum(self, points: int = 256) -> list[float] | None:
        if self._raw_iq is None or len(self._raw_iq) == 0:
            return None
        fft = np.fft.fft(self._raw_iq * np.hanning(len(self._raw_iq)))
        mag = np.abs(np.fft.fftshift(fft))
        mag_db = 20 * np.log10(mag + 1e-30)
        indices = np.linspace(0, len(mag_db) - 1, points, dtype=int)
        return mag_db[indices].tolist()

    def close(self):
        import SoapySDR
        from SoapySDR import SOAPY_SDR_RX

        if self._rx_stream is not None:
            try:
                self._sdr.deactivateStream(self._rx_stream)
                self._sdr.closeStream(self._rx_stream)
            except Exception:
                pass
            self._rx_stream = None
        self._sdr = None


class AsyncPacketReceiver:
    def __init__(
        self,
        on_packet,
        on_spectrum,
        on_error,
        spectrum_points: int = 256,
        spectrum_interval: int = 20,
    ):
        self._on_packet = on_packet
        self._on_spectrum = on_spectrum
        self._on_error = on_error
        self._spectrum_points = spectrum_points
        self._spectrum_interval = spectrum_interval
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, worker: ReceiverWorker):
        self._running = True
        self._worker = worker
        loop = asyncio.get_event_loop()

        try:
            await loop.run_in_executor(self._executor, worker.open)
        except Exception as e:
            await self._on_error("HARDWARE_ERR", str(e))
            raise

        self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self):
        loop = asyncio.get_event_loop()
        chunk_count = 0
        while self._running:
            try:
                result = await loop.run_in_executor(
                    self._executor, self._worker.read_one
                )
                if result is not None:
                    await self._on_packet(result)

                chunk_count += 1
                if chunk_count % self._spectrum_interval == 0:
                    spectrum = await loop.run_in_executor(
                        self._executor,
                        self._worker.compute_spectrum,
                        self._spectrum_points,
                    )
                    if spectrum is not None:
                        spectrum_frame = await loop.run_in_executor(
                            self._executor,
                            lambda: self._build_spectrum_frame(self._worker, spectrum),
                        )
                        await self._on_spectrum(spectrum_frame)
            except Exception as e:
                await self._on_error("HARDWARE_ERR", str(e))
                break

    def _build_spectrum_frame(self, worker, points):
        from models import SpectrumFrame
        return SpectrumFrame(
            fc_hz=worker.config.freq_hz,
            span_hz=worker.config.sample_rate,
            points=points,
            ts=time.time(),
        )

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if hasattr(self, "_worker"):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self._executor, self._worker.close)
        self._executor.shutdown(wait=True)
```

- [ ] **Step 2: Verify import (no hardware needed)**

```bash
cd receiver-server && python -c "
import sys; sys.path.insert(0, '../rf-link/packet/src')
from packet_rx import ReceiverWorker, AsyncPacketReceiver
from config import ReceiverConfig
w = ReceiverWorker(ReceiverConfig())
print('ReceiverWorker imported OK')
print('AsyncPacketReceiver imported OK')
"
```
Expected: `ReceiverWorker imported OK`, `AsyncPacketReceiver imported OK`

- [ ] **Step 3: Test spectrum computation in isolation**

```bash
cd receiver-server && python -c "
import sys; sys.path.insert(0, '../rf-link/packet/src')
import numpy as np
from packet_rx import ReceiverWorker
from config import ReceiverConfig

w = ReceiverWorker(ReceiverConfig())
w._raw_iq = np.random.randn(524288) + 1j * np.random.randn(524288)
spectrum = w.compute_spectrum(256)
assert spectrum is not None
assert len(spectrum) == 256
print(f'Spectrum: {len(spectrum)} points, min={min(spectrum):.1f}, max={max(spectrum):.1f}')
"
```
Expected: `Spectrum: 256 points, min=..., max=...`

- [ ] **Step 4: Commit**

```bash
cd /Users/charlesclaw/Documents/git/hab && git add receiver-server/packet_rx.py && git commit -m "feat: add ReceiverWorker (sync SDR) and AsyncPacketReceiver (async bridge)"
```

---

### Task 8: REST Routes

**Files:**
- Create: `receiver-server/routes/rest.py`
- Create: `receiver-server/tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

```python
# receiver-server/tests/test_routes.py
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from routes.rest import create_rest_router


def build_app(receiver_manager=None, ws_manager=None):
    app = FastAPI()
    app.include_router(create_rest_router(receiver_manager, ws_manager))
    return app


class TestHealthEndpoint:

    async def test_health_returns_ok(self):
        app = build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestPacketsEndpoint:

    async def test_empty_buffer(self):
        class FakeMgr:
            packet_buffer = []

        app = build_app(receiver_manager=FakeMgr())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/packets")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_all_packets(self):
        class FakeMgr:
            packet_buffer = [{"type": "environment", "temp_ext_c": -42.6}]

        app = build_app(receiver_manager=FakeMgr())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/packets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["type"] == "environment"

    async def test_since_filter(self):
        class FakeMgr:
            packet_buffer = [
                {"type": "environment", "seq": 1},
                {"type": "motion", "seq": 2},
                {"type": "power", "seq": 3},
            ]

        app = build_app(receiver_manager=FakeMgr())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/packets?since=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["seq"] == 2
        assert data[1]["seq"] == 3


class TestDevicesEndpoint:

    async def test_devices_returns_list(self):
        app = build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/devices")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Run tests (expect failure)**

```bash
cd receiver-server && pip install httpx && python -m pytest tests/test_routes.py -v
```
Expected: ImportError (no routes.rest module)

- [ ] **Step 3: Write routes/rest.py**

```python
# receiver-server/routes/rest.py
import json
import subprocess
from typing import Optional
from fastapi import APIRouter, Query


def create_rest_router(receiver_manager=None, ws_manager=None):
    router = APIRouter()

    @router.get("/health")
    async def health():
        return {"status": "ok"}

    @router.get("/api/packets")
    async def get_packets(since: Optional[int] = Query(None)):
        if receiver_manager is None:
            return []
        packets = receiver_manager.packet_buffer
        if since is not None:
            packets = [p for p in packets if p.get("seq", 0) > since]
        return packets

    @router.get("/api/devices")
    async def list_devices():
        try:
            result = subprocess.run(
                ["hackrf_info"], capture_output=True, text=True, timeout=5
            )
            serials = []
            for line in result.stdout.splitlines():
                if "Serial Number:" in line:
                    serials.append(line.split(":")[-1].strip())
            return serials
        except Exception:
            return []

    return router
```

- [ ] **Step 4: Run tests**

```bash
cd receiver-server && python -m pytest tests/test_routes.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/charlesclaw/Documents/git/hab && git add receiver-server/routes/rest.py receiver-server/tests/test_routes.py receiver-server/routes/__init__.py && git commit -m "feat: add REST routes (/health, /api/packets, /api/devices)"
```

---

### Task 9: WebSocket Route

**Files:**
- Create: `receiver-server/routes/ws.py`
- Add WS route test to `receiver-server/tests/test_routes.py`

- [ ] **Step 1: Write ws.py**

```python
# receiver-server/routes/ws.py
import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ws_manager import WebSocketManager
from receiver_manager import ReceiverManager, InvalidStateError
from config import ReceiverConfig


def create_ws_router(
    ws_manager: WebSocketManager,
    receiver_manager: ReceiverManager,
):
    router = APIRouter()

    @router.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws_manager.connect(ws)
        try:
            recv_task = asyncio.create_task(_recv_loop(ws, ws_manager))
            await recv_task
        except WebSocketDisconnect:
            pass
        finally:
            await ws_manager.disconnect(ws)

    async def _recv_loop(ws: WebSocket, ws_mgr: WebSocketManager):
        while True:
            raw = await ws.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await ws_mgr.broadcast_error(
                    "HARDWARE_ERR", "Invalid JSON in command"
                )
                continue

            msg_type = message.get("type", "")
            data = message.get("data", {})

            try:
                if msg_type == "cmd:start":
                    config = ReceiverConfig(**data)
                    await receiver_manager.start()
                elif msg_type == "cmd:stop":
                    await receiver_manager.stop()
                elif msg_type == "cmd:configure":
                    await receiver_manager.configure(data)
                else:
                    await ws_mgr.broadcast_error(
                        "HARDWARE_ERR", f"Unknown command type: {msg_type}"
                    )
            except InvalidStateError as e:
                await ws_mgr.broadcast_error("HARDWARE_ERR", str(e))
            except Exception as e:
                await ws_mgr.broadcast_error("HARDWARE_ERR", str(e))

    return router
```

- [ ] **Step 2: Add WS test to test_routes.py**

Append to `receiver-server/tests/test_routes.py`:

```python
from routes.ws import create_ws_router


class TestWebSocketEndpoint:

    async def test_ws_connect_disconnect(self):
        from ws_manager import WebSocketManager
        from config import ReceiverConfig
        from receiver_manager import ReceiverManager

        wsm = WebSocketManager()
        rm = ReceiverManager(wsm, ReceiverConfig())

        app = FastAPI()
        app.include_router(create_ws_router(wsm, rm))

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            async with client.stream("GET", "/ws") as ws_response:
                pass
        assert ws_response.status_code == 200

    async def test_ws_receives_status_on_connect(self):
        from ws_manager import WebSocketManager
        from config import ReceiverConfig
        from receiver_manager import ReceiverManager

        wsm = WebSocketManager()
        rm = ReceiverManager(wsm, ReceiverConfig())

        app = FastAPI()
        app.include_router(create_ws_router(wsm, rm))

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            with pytest.raises(Exception):
                async with client.stream("GET", "/ws") as ws_response:
                    pass

    async def test_ws_unknown_command_sends_error(self):
        from ws_manager import WebSocketManager
        from config import ReceiverConfig
        from receiver_manager import ReceiverManager

        wsm = WebSocketManager()
        rm = ReceiverManager(wsm, ReceiverConfig())

        app = FastAPI()
        app.include_router(create_ws_router(wsm, rm))

        msg = {"type": "cmd:nonexistent", "data": {}}
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            with pytest.raises(Exception):
                async with client.stream("GET", "/ws") as ws_response:
                    pass
```

Hmm, the httpx WebSocket testing is limited. Let's simplify the WS test to just verify the router mounts correctly. We'll test WS via the integration test in Task 10.

Replace the WS test class with:

```python
class TestWebSocketRouter:
    def test_router_created_without_errors(self):
        from ws_manager import WebSocketManager
        from config import ReceiverConfig
        from receiver_manager import ReceiverManager

        wsm = WebSocketManager()
        rm = ReceiverManager(wsm, ReceiverConfig())
        router = create_ws_router(wsm, rm)
        assert router is not None
        routes = [r.path for r in router.routes]
        assert "/ws" in routes
```

- [ ] **Step 3: Run tests**

```bash
cd receiver-server && python -m pytest tests/test_routes.py -v
```
Expected: 6 passed

- [ ] **Step 4: Commit**

```bash
cd /Users/charlesclaw/Documents/git/hab && git add receiver-server/routes/ws.py receiver-server/tests/test_routes.py && git commit -m "feat: add WebSocket route with command dispatch"
```

---

### Task 10: main.py — FastAPI App Wiring

**Files:**
- Create: `receiver-server/main.py`

- [ ] **Step 1: Write main.py**

```python
# receiver-server/main.py
import sys
from pathlib import Path

HAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HAB_ROOT / "rf-link" / "packet" / "src"))
sys.path.insert(0, str(HAB_ROOT / "rf-link" / "dvbs2"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ServerConfig, ReceiverConfig
from ws_manager import WebSocketManager
from receiver_manager import ReceiverManager
from routes.rest import create_rest_router
from routes.ws import create_ws_router


def create_app() -> FastAPI:
    server_config = ServerConfig()
    receiver_config = ReceiverConfig()
    ws_manager = WebSocketManager()
    receiver_manager = ReceiverManager(ws_manager, receiver_config)

    app = FastAPI(title="HAB Receiver Server")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.ws_manager = ws_manager
    app.state.receiver_manager = receiver_manager

    app.include_router(create_rest_router(receiver_manager, ws_manager))
    app.include_router(create_ws_router(ws_manager, receiver_manager))

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
```

- [ ] **Step 2: Verify app starts**

```bash
cd receiver-server && python -c "
from main import app
print(f'App created: {app.title}')
print(f'Routes: {[r.path for r in app.routes]}')
"
```
Expected: App created with routes listed

- [ ] **Step 3: Verify uvicorn can serve the app**

```bash
cd receiver-server && timeout 3 python -m uvicorn main:app --host 0.0.0.0 --port 8000 2>&1 || true
```
Expected: Uvicorn starts without import errors

- [ ] **Step 4: Commit**

```bash
cd /Users/charlesclaw/Documents/git/hab && git add receiver-server/main.py && git commit -m "feat: add main.py FastAPI app wiring"
```

---

### Task 11: Integration Test

**Files:**
- Create: `receiver-server/tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# receiver-server/tests/test_integration.py
import pytest
from fastapi.testclient import TestClient
from main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestPackets:
    def test_packets_empty(self, client):
        resp = client.get("/api/packets")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestDevices:
    def test_devices_endpoint(self, client):
        resp = client.get("/api/devices")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestWebSocket:
    def test_ws_connects(self, client):
        with client.websocket_connect("/ws") as ws:
            pass

    def test_ws_cmd_start_in_idle_state(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "cmd:start", "data": {"freq_hz": 433500000}})
            data = ws.receive_json()
            assert data["type"] == "status"
            assert data["data"]["state"] in ("starting", "running") or "error" in data.get("data", {}).get("last_error", "")
            ws.send_json({"type": "cmd:stop", "data": {}})
            data = ws.receive_json()
            assert data["type"] == "status"

    def test_ws_cmd_configure_in_idle_is_noop(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "cmd:configure", "data": {"gain_lna": 40}})

    def test_ws_handles_invalid_json(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_text("not json")
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "Invalid JSON" in data["data"]["message"]

    def test_ws_handles_unknown_command(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "cmd:mystery", "data": {}})
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "Unknown command" in data["data"]["message"]
```

- [ ] **Step 2: Run integration tests**

```bash
cd receiver-server && python -m pytest tests/test_integration.py -v
```
Expected: 6 passed

- [ ] **Step 3: Run all tests together**

```bash
cd receiver-server && python -m pytest tests/ -v
```
Expected: 29 passed (14 models + 9 ws_manager + 9 receiver_manager + 5 routes + 6 integration = 43... wait let me recalculate)

14 (test_models) + 9 (test_ws_manager) + 9 (test_receiver_manager) + 6 (test_routes) + 6 (test_integration) = 44

But test_routes has 5 old + 1 new WS router test = 6. OK so 14 + 9 + 9 + 6 + 6 = 44.

Let me adjust. The routes test has 5 from Task 8 + 1 WS router test from Task 9 = 6 total.

So: 14 + 9 + 9 + 6 + 6 = 44 tests total.

Expected: 44 passed

- [ ] **Step 4: Commit**

```bash
cd /Users/charlesclaw/Documents/git/hab && git add receiver-server/tests/test_integration.py && git commit -m "test: add integration tests for REST and WebSocket endpoints"
```

---

### Task 12: Final Verification

- [ ] **Step 1: Full test suite**

```bash
cd receiver-server && python -m pytest tests/ -v
```

- [ ] **Step 2: Verify launch.sh works**

```bash
cd receiver-server && bash launch.sh &
sleep 2
curl -s http://localhost:8000/health
kill %1 2>/dev/null
```

- [ ] **Step 3: Commit any remaining changes**

```bash
cd /Users/charlesclaw/Documents/git/hab && git status && git add -A receiver-server/ && git commit -m "chore: final verification and cleanup"
```
