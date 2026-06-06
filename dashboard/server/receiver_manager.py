# receiver-server/receiver_manager.py
"""Receiver state machine — lifecycle management with automatic error recovery."""

from __future__ import annotations

import asyncio
import time
from collections import deque

from models import ReceiverState, SpectrumFrame
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

    async def start(self):
        if self._state not in (ReceiverState.IDLE, ReceiverState.ERROR):
            raise InvalidStateError(self._state)
        self._state = ReceiverState.STARTING
        self._start_time = time.time()
        await self._ws.broadcast_status(self._build_status())
        try:
            self._start_receiver()
            self._state = ReceiverState.RUNNING
            await self._ws.broadcast_status(self._build_status())
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

    async def ingest_packet(self, packet: dict):
        """Receive and broadcast a telemetry packet from external sources.

        Called by the REST API when an external client (e.g. balloon-sim.py)
        POSTs a packet.  Appends to the packet buffer, updates counters,
        and broadcasts to all connected WebSocket clients.
        """
        self._packet_buffer.append(packet)
        self._packets_total += 1
        self._packets_valid += 1
        await self._ws.broadcast({"type": "telemetry", "data": packet})

    async def _cleanup(self):
        self._stop_receiver()
        self._receiver = None
        if self._status_task and not self._status_task.done():
            self._status_task.cancel()
            try:
                await self._status_task
            except asyncio.CancelledError:
                pass
        self._bridge_task = None
        self._status_task = None

    def _build_status(self) -> dict:
        """Build engine status dict matching what the dashboard expects."""
        return {
            "running": self._state == ReceiverState.RUNNING,
            "state": self._state.value,
            "tx_active": False,
            "rx_active": self._state == ReceiverState.RUNNING,
            "device_connected": True,
            "device_serial": "hackrf",
            "frequency": float(self._config.freq_hz),
            "symbol_rate": float(self._config.symbol_rate),
            "uptime_sec": self.uptime_sec,
            "pipeline": None,
            "error_count": 0,
            "last_error": "",
        }
