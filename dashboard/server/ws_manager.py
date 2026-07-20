# receiver-server/ws_manager.py
"""WebSocket connection manager — multiplexed broadcast to all clients."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket
from models import ReceiverStatus, SpectrumFrame


_log = logging.getLogger("ws_manager")


def _client_label(ws) -> str:
    client = getattr(ws, "client", None)
    if client is None:
        return "unknown"
    host = getattr(client, "host", None)
    port = getattr(client, "port", None)
    if host is not None and port is not None:
        return f"{host}:{port}"
    if isinstance(client, tuple) and len(client) == 2:
        return f"{client[0]}:{client[1]}"
    return str(client)


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
            connection_count = len(self._connections)
        _log.info(
            "WebSocket connected: %s (%d clients)",
            _client_label(ws),
            connection_count,
        )

    async def disconnect(self, ws):
        removed = False
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)
                removed = True
            connection_count = len(self._connections)
        if removed:
            _log.info(
                "WebSocket disconnected: %s (%d clients)",
                _client_label(ws),
                connection_count,
            )

    async def broadcast(self, message: dict):
        dead = []
        text = json.dumps(message)
        async with self._lock:
            conns = list(self._connections)
        message_type = str(message.get("type", "message"))
        if message_type not in ("log", "status"):
            _log.debug(
                "Broadcasting %s to %d clients", message_type, len(conns)
            )
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception:
                _log.warning(
                    "WebSocket send failed for %s; disconnecting",
                    _client_label(ws),
                )
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
