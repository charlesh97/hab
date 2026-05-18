"""
HAB Ground Station — Web Dashboard Server
Serves the React SPA and provides WebSocket + REST API endpoints.
"""

import asyncio
import json
import logging
import math
import os
import random
import sys
import time
from collections import deque
from pathlib import Path
from typing import Optional

import aiohttp
from aiohttp import web

HAB_DIR = Path(__file__).parent.resolve()
HAB_GUI_DIR = HAB_DIR / "hab-gui" / "python"
sys.path.insert(0, str(HAB_GUI_DIR))
sys.path.insert(0, "/opt/homebrew/lib/python3.14/site-packages")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("hab-server")

WEB_DIST = HAB_DIR / "web-dashboard" / "dist"
from hab_engine import HabEngine

engine = HabEngine(enable_websocket=True)

# ── Module-level state for API consumption ──
_latest_spectrum: Optional[dict] = None
_telemetry_history: deque = deque(maxlen=120)
_sim_time: float = 0.0


def _spectrum_callback(frame):
    """Capture latest spectrum frame from the HabEngine flowgraph manager."""
    global _latest_spectrum
    _latest_spectrum = {
        "frequencies": frame.frequencies,
        "power_db": frame.power_db,
        "center_freq": frame.center_freq,
        "span_hz": frame.span_hz,
    }


# Hook into the engine's spectrum data stream
engine.set_spectrum_callback(_spectrum_callback)


# ── Simulated Data Generators ──

def _simulate_spectrum() -> dict:
    """Generate a simulated spectrum frame (noise floor + carrier peak)."""
    global _sim_time
    _sim_time += 0.1
    center_freq = 915e6
    span_hz = 2e6
    n = 256
    freqs = [center_freq - span_hz / 2 + i * span_hz / n for i in range(n)]
    noise_floor = -95
    power = []
    for f in freqs:
        offset = (f - center_freq) / span_hz
        sig = noise_floor
        # Carrier peak (Gaussian)
        sig += 35 * math.exp(-(offset * 60) ** 2)
        # Side lobes
        sig += 10 * math.exp(-((offset - 0.02) * 80) ** 2)
        sig += 8 * math.exp(-((offset + 0.02) * 80) ** 2)
        # Noise
        sig += random.gauss(0, 2)
        # Time-varying artifact
        sig += 3 * math.sin(2 * math.pi * _sim_time * 0.3 + math.pi * offset * 20)
        power.append(round(sig, 2))
    return {
        "frequencies": freqs,
        "power_db": power,
        "center_freq": center_freq,
        "span_hz": span_hz,
    }


async def _telemetry_simulator():
    """Background task: generate simulated telemetry data at 1 Hz."""
    t = 0.0
    while True:
        alt = 20000 + 15000 * math.sin(t * 0.1)
        sample = {
            "altitude": round(alt, 1),
            "verticalSpeed": round(1500 * math.cos(t * 0.1), 1),
            "groundSpeed": round(20 + 5 * math.sin(t * 0.05), 1),
            "heading": round(90 + 10 * math.sin(t * 0.03), 1),
            "internalTemp": round(20 + 3 * math.sin(t * 0.02), 1),
            "externalTemp": round(-50 + 10 * math.sin(t * 0.08 + 1), 1),
            "pressure": round(1013.25 * math.exp(-alt / 8430), 1),
            "battery": round(max(0, 90 - t * 0.001), 1),
            "gpsSats": random.randint(8, 12),
            "lat": round(39.05 + 0.5 * math.sin(t * 0.02), 4),
            "lng": round(-105.5 - 0.5 * math.cos(t * 0.02), 4),
            "timestamp": time.time(),
        }
        _telemetry_history.append(sample)
        t += 1
        await asyncio.sleep(1.0)


async def _spectrum_filler():
    """Background task: fill _latest_spectrum at 10 Hz when no real data."""
    global _latest_spectrum
    while True:
        if _latest_spectrum is None:
            frame = _simulate_spectrum()
            _latest_spectrum = frame
        await asyncio.sleep(0.1)


# ── CORS Middleware ──

@web.middleware
async def cors_middleware(request, handler):
    """Add CORS headers to every response and handle OPTIONS preflight."""
    if request.method == "OPTIONS":
        return web.Response(
            status=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Max-Age": "3600",
            },
        )
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


async def start_server():
    """Start the aiohttp server serving the React SPA + REST APIs."""

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
                    if current:
                        devices.append(current)
                    current = {"index": len(devices)}
                elif "Serial" in line:
                    current["serial"] = line.split(":")[1].strip()
                elif "Firmware" in line:
                    current["firmware"] = line.split(":")[1].strip()
            if current:
                devices.append(current)
            return web.json_response({"devices": devices})
        except Exception as e:
            return web.json_response({"error": str(e), "devices": []})

    # ── NEW: Spectrum endpoint ──
    async def api_spectrum(request):
        if _latest_spectrum is None:
            return web.json_response({"error": "No spectrum data available"}, status=503)
        return web.json_response(_latest_spectrum)

    # ── NEW: Telemetry endpoints ──
    async def api_telemetry_latest(request):
        if not _telemetry_history:
            return web.json_response({"error": "No telemetry data available"}, status=503)
        return web.json_response(_telemetry_history[-1])

    async def api_telemetry_history(request):
        return web.json_response(list(_telemetry_history))

    # ── NEW: Config endpoints ──
    async def api_config_get(request):
        cfg = engine.flowgraph.config
        return web.json_response({
            "frequency": cfg.get("center_freq", 915000000),
            "symbol_rate": cfg.get("symbol_rate", 1000000),
            "tx_gain_vga": cfg.get("tx_gain_vga", 16),
            "tx_gain_amp": bool(cfg.get("tx_gain_amp", False)),
            "modcod": cfg.get("modcod", "QPSK1/2"),
            "rolloff": cfg.get("rolloff", 0.2),
            "pilots": cfg.get("pilots", True),
            "device_connected": engine.status.device_connected,
            "device_serial": engine.status.device_serial,
        })

    async def api_config_update(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        updates = {}
        if "frequency" in body:
            updates["center_freq"] = float(body["frequency"])
        if "symbol_rate" in body:
            updates["symbol_rate"] = float(body["symbol_rate"])
        if "tx_gain_vga" in body:
            updates["tx_gain_vga"] = float(body["tx_gain_vga"])
        if "tx_gain_amp" in body:
            updates["tx_gain_amp"] = bool(body["tx_gain_amp"])
        engine.flowgraph.update_config(**updates)
        return web.json_response({"success": True})

    # ── NEW: SSE spectrum live endpoint ──
    async def api_spectrum_live(request):
        """Server-Sent Events endpoint streaming spectrum at 10 Hz."""
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            },
        )
        await response.prepare(request)
        try:
            while True:
                frame = _latest_spectrum
                if frame is None:
                    frame = _simulate_spectrum()
                await response.write(f"data: {json.dumps(frame)}\n\n".encode())
                await asyncio.sleep(0.1)
        except (asyncio.CancelledError, ConnectionResetError, ConnectionAbortedError):
            pass
        return response

    # ── NEW: WebSocket bridge at /ws ──
    async def ws_bridge(request):
        """Bridge between browser WebSocket and HabEngine WebSocket (ws://localhost:8765)."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect("ws://localhost:8765") as engine_ws:
                    async def forward_to_engine():
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await engine_ws.send_str(msg.data)
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                await engine_ws.send_bytes(msg.data)
                            elif msg.type == aiohttp.WSMsgType.CLOSE:
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                break

                    async def forward_to_browser():
                        async for msg in engine_ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await ws.send_str(msg.data)
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                await ws.send_bytes(msg.data)
                            elif msg.type == aiohttp.WSMsgType.CLOSE:
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                break

                    await asyncio.gather(
                        forward_to_engine(),
                        forward_to_browser(),
                    )
        except (ConnectionRefusedError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"WebSocket bridge: engine WS unavailable at ws://localhost:8765: {e}")
            try:
                await ws.send_json({
                    "type": "error",
                    "data": {"message": "Engine WebSocket unavailable at ws://localhost:8765"},
                })
            except Exception:
                pass
        except asyncio.CancelledError:
            pass
        finally:
            if not ws.closed:
                await ws.close()
        return ws

    # ── SPA catch-all: serve index.html for any unmatched path ──
    async def spa_handler(request):
        return web.FileResponse(WEB_DIST / "index.html")

    # ── Build app ──
    app = web.Application(middlewares=[cors_middleware])

    # API routes
    app.router.add_get("/api/status", api_status)
    app.router.add_post("/api/command", api_command)
    app.router.add_get("/api/hackrf", api_hackrf)
    app.router.add_get("/api/spectrum", api_spectrum)
    app.router.add_get("/api/telemetry/latest", api_telemetry_latest)
    app.router.add_get("/api/telemetry/history", api_telemetry_history)
    app.router.add_get("/api/config", api_config_get)
    app.router.add_post("/api/config", api_config_update)
    app.router.add_get("/api/spectrum/live", api_spectrum_live)

    # WebSocket bridge
    app.router.add_get("/ws", ws_bridge)

    # Static assets (built by Vite into dist/assets/)
    assets_dir = WEB_DIST / "assets"
    if assets_dir.exists():
        app.router.add_static("/assets", str(assets_dir), show_index=False)

    # SPA catch-all: every unmatched request gets index.html
    # This must be registered AFTER /api/* and /assets/*
    app.router.add_get("/{tail:.*}", spa_handler)

    # ── Start background tasks ──
    asyncio.create_task(_telemetry_simulator(), name="telemetry-simulator")
    asyncio.create_task(_spectrum_filler(), name="spectrum-filler")

    # ── Start ──
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("HAB_PORT", "3000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info("=" * 60)
    logger.info(f"  HAB Ground Station Web Dashboard")
    logger.info(f"  Dashboard:      http://localhost:{port}")
    logger.info(f"  WebSocket:      ws://localhost:{port}/ws")
    logger.info(f"  API Status:     http://localhost:{port}/api/status")
    logger.info(f"  API Command:    POST http://localhost:{port}/api/command")
    logger.info(f"  API Spectrum:   http://localhost:{port}/api/spectrum")
    logger.info(f"  API Telemetry:  http://localhost:{port}/api/telemetry/latest")
    logger.info(f"  API Config:     http://localhost:{port}/api/config")
    logger.info(f"  SSE Live:       http://localhost:{port}/api/spectrum/live")
    logger.info("=" * 60)
    logger.info(f"  Serving from:   {WEB_DIST}")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(start_server())
