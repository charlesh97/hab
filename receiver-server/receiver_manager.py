# receiver-server/receiver_manager.py
"""Receiver state machine — lifecycle management with automatic error recovery."""

from __future__ import annotations

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
            await self._ws.broadcast_status(self._build_status())
        except Exception:
            await self._cleanup()
            self._state = ReceiverState.IDLE
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
