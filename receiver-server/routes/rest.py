# receiver-server/routes/rest.py
"""REST endpoints — health check, packet query, device enumeration."""

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
        """Enumerate SDR devices via SoapySDR (supports HackRF, RTL-SDR, etc.)."""
        try:
            import SoapySDR
            devices = SoapySDR.Device.enumerate()
            return [
                {
                    "driver": d["driver"],
                    "serial": d["serial"],
                    "label": d["label"],
                    "version": d["version"],
                }
                for d in devices
            ]
        except ImportError:
            return []
        except Exception:
            return []

    return router
