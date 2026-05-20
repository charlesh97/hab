# receiver-server/tests/test_ws_manager.py
import json
import pytest
import asyncio
from ws_manager import WebSocketManager
from models import ReceiverStatus, ReceiverState, SpectrumFrame


class MockWebSocket:
    def __init__(self):
        self.sent: list[str] = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, data: str):
        self.sent.append(data)


class TestWebSocketManager:

    @pytest.mark.asyncio
    async def test_connect(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        assert ws.accepted is True
        assert mgr.connection_count == 1

    @pytest.mark.asyncio
    async def test_disconnect(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        await mgr.disconnect(ws)
        assert mgr.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple(self):
        mgr = WebSocketManager()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await mgr.connect(ws1)
        await mgr.connect(ws2)
        await mgr.broadcast({"type": "status", "data": {"running": True}})
        assert len(ws1.sent) == 1
        assert len(ws2.sent) == 1
        payload1 = json.loads(ws1.sent[0])
        assert payload1["type"] == "status"

    @pytest.mark.asyncio
    async def test_broadcast_packet(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        await mgr.broadcast_packet({"type": "environment", "temp_ext_c": -42.6})
        payload = json.loads(ws.sent[0])
        assert payload["type"] == "packet"
        assert payload["data"]["type"] == "environment"

    @pytest.mark.asyncio
    async def test_broadcast_status(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        status = ReceiverStatus(running=True, state=ReceiverState.RUNNING, freq_hz=433500000)
        await mgr.broadcast_status(status)
        payload = json.loads(ws.sent[0])
        assert payload["data"]["state"] == "running"

    @pytest.mark.asyncio
    async def test_broadcast_spectrum(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        spectrum = SpectrumFrame(fc_hz=433500000, span_hz=2000000, points=[-85.2, -84.1], ts=1716072000.123)
        await mgr.broadcast_spectrum(spectrum)
        payload = json.loads(ws.sent[0])
        assert payload["data"]["fc_hz"] == 433500000

    @pytest.mark.asyncio
    async def test_broadcast_error(self):
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws)
        await mgr.broadcast_error("DEVICE_LOST", "HackRF disconnected")
        payload = json.loads(ws.sent[0])
        assert payload["type"] == "error"
        assert payload["data"]["code"] == "DEVICE_LOST"

    @pytest.mark.asyncio
    async def test_dead_connection_removed(self):
        mgr = WebSocketManager()

        class FailingWS:
            sent = []
            accepted = False

            async def accept(self):
                self.accepted = True

            async def send_text(self, data: str):
                raise Exception("connection lost")

        ws = FailingWS()
        await mgr.connect(ws)
        assert mgr.connection_count == 1
        await mgr.broadcast({"type": "status", "data": {}})
        assert mgr.connection_count == 0

    @pytest.mark.asyncio
    async def test_command_queue(self):
        mgr = WebSocketManager()
        cmd = {"type": "cmd:start", "data": {"freq_hz": 433500000}}
        mgr.push_command(cmd)
        received = await mgr.get_command()
        assert received == cmd
