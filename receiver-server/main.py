# receiver-server/main.py
"""HAB Receiver Server — FastAPI application entry point.

Manages a HackRF via SoapySDR, decodes BPSK packet telemetry using
rf-link/packet/src/ as a library, and streams decoded packets,
spectrum, and status to the web dashboard over a single WebSocket.

Usage:
    python -m uvicorn main:app --host 0.0.0.0 --port 8000
    # or: bash launch.sh
"""

from __future__ import annotations

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
