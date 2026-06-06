# receiver-server/routes/rest.py
"""REST endpoints — health check, packet query, device enumeration."""

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query


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

    @router.post("/api/packet")
    async def post_packet(body: dict = Body(...)):
        """Receive a telemetry packet from external sources (e.g. balloon-sim.py)."""
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Body must be a JSON object")

        data = body.get("data")
        if data is None:
            raise HTTPException(status_code=400, detail="Missing 'data' field")

        # Validate required fields
        pkt_type = data.get("type")
        pkt_seq = data.get("seq")
        if pkt_type not in ("position", "motion", "environment", "power"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid or missing packet type: {pkt_type!r}",
            )
        if pkt_seq is None:
            raise HTTPException(status_code=400, detail="Missing 'seq' in packet data")

        if receiver_manager is not None:
            await receiver_manager.ingest_packet(data)

        return {"status": "ok", "seq": pkt_seq}

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
