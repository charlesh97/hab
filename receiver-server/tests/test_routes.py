# receiver-server/tests/test_routes.py
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from routes.rest import create_rest_router


def build_app(receiver_manager=None, ws_manager=None):
    app = FastAPI()
    app.include_router(create_rest_router(receiver_manager, ws_manager))
    return app


class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_health_returns_ok(self):
        app = build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestPacketsEndpoint:

    @pytest.mark.asyncio
    async def test_empty_buffer(self):
        class FakeMgr:
            packet_buffer = []

        app = build_app(receiver_manager=FakeMgr())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/packets")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_returns_all_packets(self):
        class FakeMgr:
            packet_buffer = [{"type": "environment", "temp_ext_c": -42.6}]

        app = build_app(receiver_manager=FakeMgr())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/packets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["type"] == "environment"

    @pytest.mark.asyncio
    async def test_since_filter(self):
        class FakeMgr:
            packet_buffer = [
                {"type": "environment", "seq": 1},
                {"type": "motion", "seq": 2},
                {"type": "power", "seq": 3},
            ]

        app = build_app(receiver_manager=FakeMgr())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/packets?since=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["seq"] == 2
        assert data[1]["seq"] == 3


class TestDevicesEndpoint:

    @pytest.mark.asyncio
    async def test_devices_returns_list(self):
        app = build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/devices")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---- Task 9: WebSocket router test ----


class TestWebSocketRouter:

    def test_router_created_without_errors(self):
        from ws_manager import WebSocketManager
        from config import ReceiverConfig
        from receiver_manager import ReceiverManager
        from routes.ws import create_ws_router

        wsm = WebSocketManager()
        rm = ReceiverManager(wsm, ReceiverConfig())
        router = create_ws_router(wsm, rm)
        assert router is not None
        routes = [r.path for r in router.routes]
        assert "/ws" in routes
