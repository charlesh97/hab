# receiver-server/routes/rest.py
"""REST endpoints — health check, packet query, device enumeration."""

import subprocess
from typing import Optional

from fastapi import APIRouter, Query


def create_rest_router(receiver_manager=None, ws_manager=None):
    router = APIRouter()

    @router.get("/health")
    async def health():
        return {"status": "ok"}

    @router.get("/api/packets")
    async def get_packets(since: Optional[int] = Query(None)):
        if receiver_manager is None:
            return []
        packets = receiver_manager.packet_buffer
        if since is not None:
            packets = [p for p in packets if p.get("seq", 0) > since]
        return packets

    @router.get("/api/devices")
    async def list_devices():
        try:
            result = subprocess.run(
                ["hackrf_info"], capture_output=True, text=True, timeout=5
            )
            serials = []
            for line in result.stdout.splitlines():
                if "Serial Number:" in line:
                    serials.append(line.split(":")[-1].strip())
            return serials
        except Exception:
            return []

    return router
