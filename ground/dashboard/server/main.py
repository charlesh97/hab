# receiver-server/main.py
"""HAB Receiver Server — FastAPI application entry point.

Manages a HackRF via SoapySDR, decodes BPSK packet telemetry using
dev/packet/packet/src/ as a library, and streams decoded packets,
spectrum, and status to the web dashboard over a single WebSocket.

Usage:
    bash launch.sh              # production (port 8000)
    python main.py              # dev with reload
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HAB_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(HAB_ROOT / "dev" / "packet" / "packet" / "src"))
sys.path.insert(0, str(HAB_ROOT / "dev" / "dvbs2" / "dvbs2"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from config import ReceiverConfig, ServerConfig
from ws_manager import WebSocketManager
from receiver_manager import ReceiverManager
from logging_handler import setup_logging
from routes.rest import create_rest_router
from routes.ws import create_ws_router


log_handler = setup_logging()


def create_app() -> FastAPI:
    server_config = ServerConfig()
    server_config.port = int(
        os.environ.get("HAB_PORT", server_config.port)
    )
    receiver_config = ReceiverConfig(server_port=server_config.port)
    ws_manager = WebSocketManager()
    log_handler.set_ws_manager(ws_manager)

    # ReceiverManager for packet buffering, persistence, and WebSocket broadcast.
    # External sources can also POST to /api/packet, which feeds ingest_packet().
    receiver_manager = ReceiverManager(
        ws_manager,
        receiver_config,
        db_path=server_config.database_path,
    )

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

    app.include_router(
        create_rest_router(
            receiver_manager=receiver_manager,
            ws_manager=ws_manager,
        )
    )
    app.include_router(create_ws_router(ws_manager, receiver_manager))

    # Serve dashboard static files (built React SPA)
    dist_dir = HAB_ROOT / "ground" / "dashboard" / "web" / "dist"
    if dist_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Catch-all: serve index.html for dashboard SPA."""
            if full_path.startswith("api/") or full_path.startswith("ws") or full_path.startswith("health"):
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=404, content={"detail": "Not found"})
            index = dist_dir / "index.html"
            if index.exists():
                return FileResponse(str(index))
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=404, content={"detail": "Not found"})
    else:
        print(f"Warning: dashboard dist not found at {dist_dir}")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("HAB_PORT", ServerConfig.port)),
        reload=True,
        log_level="info",
    )
