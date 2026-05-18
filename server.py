"""
HAB Ground Station — Web Dashboard Server
Serves the React SPA and provides WebSocket + REST API endpoints.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

HAB_DIR = Path(__file__).parent.resolve()
HAB_GUI_DIR = HAB_DIR / "hab-gui" / "python"
sys.path.insert(0, str(HAB_GUI_DIR))
sys.path.insert(0, "/opt/homebrew/lib/python3.14/site-packages")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("hab-server")

WEB_DIST = HAB_DIR / "web-dashboard" / "dist"
from hab_engine import HabEngine

engine = HabEngine(enable_websocket=True)


async def start_server():
    """Start the aiohttp server serving the React SPA + REST APIs."""
    from aiohttp import web

    # ── API Handlers ──
    async def api_status(request):
        s = engine.status
        return web.json_response({
            "running": s.running,
            "tx_active": s.tx_active,
            "device_connected": s.device_connected,
            "frequency": s.frequency,
            "symbol_rate": s.symbol_rate,
            "uptime_sec": s.uptime_sec,
            "pipeline": {
                "running": s.pipeline.running if s.pipeline else False,
                "file_path": s.pipeline.file_path if s.pipeline else "",
                "bitrate": s.pipeline.bitrate if s.pipeline else 0,
            } if s.pipeline else None,
            "error_count": s.error_count,
            "last_error": s.last_error,
        })

    async def api_command(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        cmd = body.get("command", "")
        data = body.get("data", {})
        if cmd == "start_pipeline":
            return web.json_response({"success": engine.start_pipeline(data.get("file_path", ""))})
        elif cmd == "stop_pipeline":
            engine.stop_pipeline()
            return web.json_response({"success": True})
        elif cmd == "start_tx":
            return web.json_response({"success": engine.start_tx(data.get("device_args", "driver=hackrf"))})
        elif cmd == "stop_tx":
            engine.stop_tx()
            return web.json_response({"success": True})
        elif cmd == "set_frequency":
            engine.flowgraph.update_config(center_freq=float(data.get("frequency", 915e6)))
            return web.json_response({"success": True})
        elif cmd == "set_gain":
            engine.flowgraph.update_config(tx_gain_vga=float(data.get("vga", 16)), tx_gain_amp=bool(data.get("amp", False)))
            return web.json_response({"success": True})
        else:
            return web.json_response({"error": f"Unknown: {cmd}"}, status=400)

    async def api_hackrf(request):
        try:
            import subprocess
            result = subprocess.run(["hackrf_info"], capture_output=True, text=True, timeout=5)
            devices, current = [], {}
            for line in result.stdout.strip().split("\n"):
                if "Found HackRF" in line:
                    if current: devices.append(current)
                    current = {"index": len(devices)}
                elif "Serial" in line:
                    current["serial"] = line.split(":")[1].strip()
                elif "Firmware" in line:
                    current["firmware"] = line.split(":")[1].strip()
            if current: devices.append(current)
            return web.json_response({"devices": devices})
        except Exception as e:
            return web.json_response({"error": str(e), "devices": []})

    # ── SPA catch-all: serve index.html for any unmatched path ──
    async def spa_handler(request):
        return web.FileResponse(WEB_DIST / "index.html")

    # ── Build app ──
    app = web.Application(middlewares=[])

    # API routes
    app.router.add_get("/api/status", api_status)
    app.router.add_post("/api/command", api_command)
    app.router.add_get("/api/hackrf", api_hackrf)

    # Static assets (built by Vite into dist/assets/)
    assets_dir = WEB_DIST / "assets"
    if assets_dir.exists():
        app.router.add_static("/assets", str(assets_dir), show_index=False)

    # SPA catch-all: every unmatched request gets index.html
    # This must be registered AFTER /api/* and /assets/*
    app.router.add_get("/{tail:.*}", spa_handler)

    # ── Start ──
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("HAB_PORT", "3000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info("=" * 60)
    logger.info(f"  HAB Ground Station Web Dashboard")
    logger.info(f"  Dashboard:      http://localhost:{port}")
    logger.info(f"  WebSocket:      ws://localhost:8765")
    logger.info(f"  API Status:     http://localhost:{port}/api/status")
    logger.info(f"  API Command:    POST http://localhost:{port}/api/command")
    logger.info("=" * 60)
    logger.info(f"  Serving from:   {WEB_DIST}")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(start_server())
