# receiver-server/receiver_manager.py
"""Receiver state machine — lifecycle management with automatic error recovery."""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections import deque

from models import ReceiverState, ReceiverStatus, ErrorCode, SpectrumFrame
from config import ReceiverConfig


class InvalidStateError(Exception):
    def __init__(self, state: ReceiverState):
        super().__init__(f"Cannot perform operation in state: {state}")


def _simulate_telemetry_packet(seq: int) -> dict:
    """Generate a realistic simulated telemetry packet."""
    t = time.time()
    ts = time.strftime("T%H:%M:%S", time.gmtime(t))

    packet_type = random.choice(["position", "motion", "environment", "power"])

    if packet_type == "position":
        return {
            "v": 1, "id": "HAB-001", "mid": "SIM", "seq": seq, "t": ts,
            "type": "position",
            "lat": 39.3187 + random.uniform(-0.01, 0.01),
            "lon": -120.3289 + random.uniform(-0.01, 0.01),
            "alt_m": 18000 + random.uniform(-100, 100),
            "agl_m": 17000 + random.uniform(-100, 100),
            "fix": True, "fix_type": "3d", "sats": random.randint(10, 16),
            "hdop": round(random.uniform(0.5, 1.5), 2),
            "vdop": round(random.uniform(0.8, 2.0), 2),
        }
    elif packet_type == "motion":
        return {
            "v": 1, "id": "HAB-001", "mid": "SIM", "seq": seq, "t": ts,
            "type": "motion",
            "gs_mps": random.uniform(10, 25),
            "vs_mps": random.uniform(-2, 8),
            "heading_deg": random.uniform(0, 360),
            "cog_deg": random.uniform(0, 360),
            "accel": {"x": round(random.uniform(-0.1, 0.1), 3),
                      "y": round(random.uniform(-0.1, 0.1), 3),
                      "z": round(random.uniform(9.6, 9.8), 3)},
            "gyro_dps": {"r": round(random.uniform(-1, 1), 2),
                         "p": round(random.uniform(-1, 1), 2),
                         "y": round(random.uniform(-1, 1), 2)},
            "att_deg": {"roll": round(random.uniform(-5, 5), 2),
                        "pitch": round(random.uniform(-5, 5), 2),
                        "yaw": round(random.uniform(0, 360), 2)},
        }
    elif packet_type == "environment":
        return {
            "v": 1, "id": "HAB-001", "mid": "SIM", "seq": seq, "t": ts,
            "type": "environment",
            "temp_ext_c": round(random.uniform(-60, -30), 2),
            "temp_int_c": round(random.uniform(10, 25), 2),
            "pressure_hpa": round(random.uniform(50, 100), 2),
            "humidity_pct": round(random.uniform(2, 15), 2),
            "baro_alt_m": round(random.uniform(17000, 19000), 2),
        }
    else:  # power
        return {
            "v": 1, "id": "HAB-001", "mid": "SIM", "seq": seq, "t": ts,
            "type": "power",
            "bat_v": round(random.uniform(7.2, 8.4), 3),
            "bat_a": round(random.uniform(0.5, 1.5), 3),
            "bat_w": round(random.uniform(4.0, 10.0), 2),
            "bat_pct": random.randint(50, 100),
            "bat_temp_c": round(random.uniform(5, 15), 2),
            "rails_v": {"v5": round(random.uniform(4.9, 5.1), 3),
                        "v3v3": round(random.uniform(3.2, 3.4), 3),
                        "v1v8": round(random.uniform(1.75, 1.85), 3)},
        }


def _simulate_spectrum(fc_hz: int = 433500000, span_hz: int = 2000000) -> SpectrumFrame:
    """Generate a simulated spectrum frame."""
    num_points = 256
    ts = time.time()
    freqs = [fc_hz - span_hz / 2 + i * span_hz / num_points for i in range(num_points)]
    # Create a bell-shaped noise floor with a peak in the middle
    points = []
    for i in range(num_points):
        noise = random.uniform(-85, -75)
        signal = -20 * math.exp(-((freqs[i] - fc_hz) ** 2) / (2 * (span_hz / 8) ** 2))
        points.append(noise + signal)
    return SpectrumFrame(
        fc_hz=fc_hz,
        span_hz=span_hz,
        points=points,
        ts=ts,
    )


class ReceiverManager:
    def __init__(self, ws_manager, config: ReceiverConfig, simulate: bool = False):
        self._ws = ws_manager
        self._config = config
        self._state = ReceiverState.IDLE
        self._packet_buffer: deque[dict] = deque(maxlen=1000)
        self._receiver = None
        self._bridge_task: asyncio.Task | None = None
        self._status_task: asyncio.Task | None = None
        self._simulate_task: asyncio.Task | None = None
        self._spectrum_task: asyncio.Task | None = None
        self._packets_total = 0
        self._packets_valid = 0
        self._spectrum_frame = None
        self._simulate = simulate
        self._start_time: float | None = None

    @property
    def state(self) -> ReceiverState:
        return self._state

    @property
    def packet_buffer(self) -> list[dict]:
        return list(self._packet_buffer)

    @property
    def uptime_sec(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    @property
    def simulate(self) -> bool:
        return self._simulate

    async def start(self):
        if self._state not in (ReceiverState.IDLE, ReceiverState.ERROR):
            raise InvalidStateError(self._state)
        self._state = ReceiverState.STARTING
        self._start_time = time.time()
        await self._ws.broadcast_status(self._build_status())
        try:
            if self._simulate:
                self._start_simulation()
            else:
                self._start_receiver()
            self._state = ReceiverState.RUNNING
            await self._ws.broadcast_status(self._build_status())
            # Start periodic status broadcaster
            self._status_task = asyncio.create_task(self._status_broadcast_loop())
        except Exception:
            await self._cleanup()
            self._state = ReceiverState.IDLE
            raise

    async def _status_broadcast_loop(self):
        """Broadcast status every 2 seconds while running."""
        try:
            while self._state == ReceiverState.RUNNING:
                await asyncio.sleep(2)
                if self._state == ReceiverState.RUNNING:
                    await self._ws.broadcast_status(self._build_status())
        except asyncio.CancelledError:
            pass

    async def stop(self):
        if self._state != ReceiverState.RUNNING:
            return
        self._state = ReceiverState.STOPPING
        await self._cleanup()
        self._state = ReceiverState.IDLE
        self._start_time = None
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

    def _start_simulation(self):
        """Start simulated telemetry + spectrum generators."""
        self._receiver = object()  # placeholder
        self._simulate_task = asyncio.create_task(self._simulate_loop())
        self._spectrum_task = asyncio.create_task(self._simulate_spectrum_loop())
        self._bridge_task = self._simulate_task

    async def _simulate_loop(self):
        """Generate simulated telemetry packets at ~1 Hz."""
        seq = 1
        try:
            while self._state == ReceiverState.RUNNING:
                packet = _simulate_telemetry_packet(seq)
                self._packet_buffer.append(packet)
                self._packets_total += 1
                self._packets_valid += 1
                await self._ws.broadcast({"type": "telemetry", "data": packet})
                seq += 1
                await asyncio.sleep(1.0 + random.uniform(-0.2, 0.2))
        except asyncio.CancelledError:
            pass

    async def _simulate_spectrum_loop(self):
        """Generate simulated spectrum frames at ~5 Hz."""
        try:
            while self._state == ReceiverState.RUNNING:
                frame = _simulate_spectrum(
                    fc_hz=self._config.freq_hz,
                    span_hz=self._config.sample_rate,
                )
                self._spectrum_frame = frame
                await self._ws.broadcast_spectrum(frame)
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            pass

    async def _cleanup(self):
        self._stop_receiver()
        self._receiver = None
        for task in (self._simulate_task, self._status_task, self._spectrum_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._bridge_task = None
        self._status_task = None
        self._simulate_task = None
        self._spectrum_task = None

    def _build_status(self) -> dict:
        """Build engine status dict matching what the dashboard expects."""
        return {
            "running": self._state == ReceiverState.RUNNING,
            "state": self._state.value,
            "tx_active": False,
            "rx_active": self._state == ReceiverState.RUNNING,
            "device_connected": True,
            "device_serial": "SIMULATED" if self._simulate else "hackrf",
            "frequency": float(self._config.freq_hz),
            "symbol_rate": float(self._config.symbol_rate),
            "uptime_sec": self.uptime_sec,
            "pipeline": None,
            "error_count": 0,
            "last_error": "",
        }
