# receiver-server/routes/ws.py
"""WebSocket endpoint — single persistent connection for the dashboard."""

import json
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ws_manager import WebSocketManager
from receiver_manager import ReceiverManager, InvalidStateError
from config import ReceiverConfig


def create_ws_router(
    ws_manager: WebSocketManager,
    receiver_manager: ReceiverManager,
) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws_manager.connect(ws)
        try:
            recv_task = asyncio.create_task(_recv_loop(ws, ws_manager, receiver_manager))
            await recv_task
        except WebSocketDisconnect:
            pass
        finally:
            await ws_manager.disconnect(ws)

    return router


async def _recv_loop(
    ws: WebSocket,
    ws_mgr: WebSocketManager,
    receiver_mgr: ReceiverManager,
):
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
                await receiver_mgr.start()
            elif msg_type == "cmd:stop":
                await receiver_mgr.stop()
            elif msg_type == "cmd:configure":
                await receiver_mgr.configure(data)
            else:
                await ws_mgr.broadcast_error(
                    "HARDWARE_ERR", f"Unknown command type: {msg_type}"
                )
        except InvalidStateError as e:
            await ws_mgr.broadcast_error("HARDWARE_ERR", str(e))
        except Exception as e:
            await ws_mgr.broadcast_error("HARDWARE_ERR", str(e))
