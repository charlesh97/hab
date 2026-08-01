# receiver-server/routes/ws.py
"""WebSocket endpoint — single persistent connection for the dashboard."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ws_manager import WebSocketManager
from sdr_manager import InvalidStateError, SdrManager


_log = logging.getLogger("ws")


def _client_label(ws: WebSocket) -> str:
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


def create_ws_router(
    ws_manager: WebSocketManager,
    sdr_manager: SdrManager,
) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws_manager.connect(ws)
        client = _client_label(ws)
        _log.info("WebSocket client connected: %s", client)
        try:
            recv_task = asyncio.create_task(_recv_loop(ws, ws_manager, sdr_manager))
            await recv_task
        except WebSocketDisconnect:
            pass
        finally:
            _log.info("WebSocket client disconnected: %s", client)
            await ws_manager.disconnect(ws)

    return router


async def _recv_loop(
    ws: WebSocket,
    ws_mgr: WebSocketManager,
    sdr_mgr: SdrManager,
):
    while True:
        raw = await ws.receive_text()
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            _log.error("WebSocket command error: invalid JSON")
            await ws_mgr.broadcast_error(
                "HARDWARE_ERR", "Invalid JSON in command"
            )
            continue

        if not isinstance(message, dict):
            _log.error("WebSocket command error: command must be an object")
            await ws_mgr.broadcast_error(
                "HARDWARE_ERR", "Command must be a JSON object"
            )
            continue

        msg_type = message.get("type", "")
        data = message.get("data", {})
        _log.debug("Received WebSocket command: %s", msg_type)

        try:
            if msg_type == "cmd:sdr:start":
                await sdr_mgr.start()
            elif msg_type == "cmd:sdr:stop":
                await sdr_mgr.stop()
            elif msg_type == "cmd:sdr:configure":
                await sdr_mgr.configure(data)
            else:
                _log.error("WebSocket command error: unknown type %s", msg_type)
                await ws_mgr.broadcast_error(
                    "HARDWARE_ERR", f"Unknown command type: {msg_type}"
                )
        except InvalidStateError as e:
            _log.error("WebSocket command %s failed: %s", msg_type, e)
            await ws_mgr.broadcast_error("HARDWARE_ERR", str(e))
        except Exception as e:
            _log.exception("WebSocket command %s failed", msg_type)
            await ws_mgr.broadcast_error("HARDWARE_ERR", str(e))
