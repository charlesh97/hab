# receiver-server/tests/test_receiver_manager.py
import pytest
import pytest_asyncio
import asyncio
import json
from receiver_manager import ReceiverManager, InvalidStateError
from ws_manager import WebSocketManager
from config import ReceiverConfig
from models import ReceiverState


class MockWebSocket:
    def __init__(self):
        self.sent: list[str] = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, data: str):
        self.sent.append(data)


class TestReceiverStateMachine:

    @pytest_asyncio.fixture
    async def manager(self):
        ws_mgr = WebSocketManager()
        config = ReceiverConfig()
        mgr = ReceiverManager(ws_mgr, config)
        return mgr

    @pytest.mark.asyncio
    async def test_initial_state_is_idle(self, manager):
        assert manager.state == ReceiverState.IDLE

    @pytest.mark.asyncio
    async def test_cannot_stop_when_idle(self, manager):
        await manager.stop()

    @pytest.mark.asyncio
    async def test_cannot_configure_when_idle(self, manager):
        result = await manager.configure({"gain_lna": 40})
        assert result is None

    @pytest.mark.asyncio
    async def test_start_transitions_to_run_then_stop_returns_to_idle(self, manager):
        manager._start_receiver = lambda: None
        manager._stop_receiver = lambda: None
        manager._bridge_task = asyncio.current_task()
        manager._status_task = asyncio.current_task()

        await manager.start()
        assert manager.state == ReceiverState.RUNNING

        await manager.stop()
        assert manager.state == ReceiverState.IDLE

    @pytest.mark.asyncio
    async def test_start_from_error_state(self, manager):
        manager._state = ReceiverState.ERROR
        manager._start_receiver = lambda: None
        manager._stop_receiver = lambda: None
        manager._bridge_task = asyncio.current_task()
        manager._status_task = asyncio.current_task()

        await manager.start()
        assert manager.state == ReceiverState.RUNNING

    @pytest.mark.asyncio
    async def test_cannot_start_when_running(self, manager):
        manager._start_receiver = lambda: None
        manager._stop_receiver = lambda: None
        manager._bridge_task = asyncio.current_task()
        manager._status_task = asyncio.current_task()

        await manager.start()
        with pytest.raises(InvalidStateError):
            await manager.start()

    @pytest.mark.asyncio
    async def test_status_broadcast_on_state_change(self, manager):
        mgr = MockWebSocket()
        # replace ws_manager with a fresh one that has our mock
        ws_mgr = WebSocketManager()
        await ws_mgr.connect(mgr)
        manager._ws = ws_mgr

        manager._start_receiver = lambda: None
        manager._stop_receiver = lambda: None
        manager._bridge_task = asyncio.current_task()
        manager._status_task = asyncio.current_task()

        await manager.start()
        await asyncio.sleep(0)
        assert len(mgr.sent) >= 1
        start_msg = json.loads(mgr.sent[0])
        assert start_msg["data"]["state"] == "starting"

    @pytest.mark.asyncio
    async def test_error_cleanup_on_start_failure(self, manager):
        def failing_start():
            raise RuntimeError("SDR not found")
        manager._start_receiver = failing_start

        try:
            await manager.start()
        except RuntimeError:
            pass

        assert manager.state == ReceiverState.IDLE
        assert manager._receiver is None
        assert manager._bridge_task is None
        assert manager._status_task is None

    @pytest.mark.asyncio
    async def test_configure_updates_config(self, manager):
        manager._start_receiver = lambda: None
        manager._stop_receiver = lambda: None
        manager._bridge_task = asyncio.current_task()
        manager._status_task = asyncio.current_task()

        await manager.start()
        await manager.configure({"gain_lna": 40, "freq_hz": 440000000})
        assert manager._config.gain_lna == 40
        assert manager._config.freq_hz == 440000000

    @pytest.mark.asyncio
    async def test_packet_buffer(self, manager):
        assert manager.packet_buffer == []
