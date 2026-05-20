# receiver-server/ws_manager.py
"""WebSocket connection manager — multiplexed broadcast to all clients."""

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

    async def broadcast_status(self, status: ReceiverStatus | dict):
        if isinstance(status, ReceiverStatus):
            data = status.model_dump()
        else:
            data = status
        await self.broadcast({"type": "status", "data": data})

    async def broadcast_spectrum(self, spectrum: SpectrumFrame):
        await self.broadcast({"type": "spectrum", "data": spectrum.model_dump()})

    async def broadcast_error(self, code: str, message: str):
        await self.broadcast({"type": "error", "data": {"code": code, "message": message}})

    def push_command(self, message: dict):
        self._command_queue.put_nowait(message)

    async def get_command(self) -> dict:
        return await self._command_queue.get()
