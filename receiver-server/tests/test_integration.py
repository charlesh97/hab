# receiver-server/tests/test_integration.py
"""Integration tests for the full receiver-server application."""

import pytest
from fastapi.testclient import TestClient
from main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestHealth:

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestPackets:

    def test_packets_empty(self, client):
        resp = client.get("/api/packets")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestDevices:

    def test_devices_endpoint(self, client):
        resp = client.get("/api/devices")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestWebSocket:

    def test_ws_connects(self, client):
        with client.websocket_connect("/ws") as ws:
            pass

    def test_ws_cmd_start_in_idle_state(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "cmd:start", "data": {"freq_hz": 433500000}})
            data = ws.receive_json()
            assert data["type"] == "status"
            state = data["data"]["state"]
            # Without hardware, the receiver will fail to open SDR and transition
            # to IDLE. Either "starting" or idle-ish states are valid.
            assert state in ("starting", "running", "idle")

    def test_ws_cmd_stop_from_idle(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "cmd:stop", "data": {}})
            # stop when IDLE is a no-op, no response message required

    def test_ws_handles_invalid_json(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_text("not json")
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "Invalid JSON" in data["data"]["message"]

    def test_ws_handles_unknown_command(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "cmd:mystery", "data": {}})
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "Unknown command" in data["data"]["message"]
