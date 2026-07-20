import pytest

from simulator_manager import SimulatorManager


class DummyProc:
    def __init__(self, pid: int = 4321):
        self.pid = pid
        self.terminated = False
        self.killed = False
        self.wait_calls = 0
        self._poll_result = None

    def poll(self):
        return self._poll_result

    def terminate(self):
        self.terminated = True
        self._poll_result = 0

    def wait(self, timeout=None):
        self.wait_calls += 1
        return 0

    def kill(self):
        self.killed = True
        self._poll_result = 0


def test_start_returns_status_without_deadlock(monkeypatch, tmp_path):
    sim_script = tmp_path / "dashboard" / "sim"
    sim_script.mkdir(parents=True)
    (sim_script / "sim.py").write_text("print('sim')\n")

    proc = DummyProc()
    launched = {}

    def fake_popen(cmd, stdout=None, stderr=None):
        launched["cmd"] = cmd
        return proc

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    manager = SimulatorManager(tmp_path, host="127.0.0.1", port=8000)
    status = manager.start(fast=False, start_at="float")

    assert status["running"] is True
    assert status["pid"] == 4321
    assert status["mode"] == "realtime"
    assert status["phase"] == "float"
    assert launched["cmd"][-2:] == ["--start-at", "float"]


def test_stop_returns_status_without_deadlock(tmp_path):
    sim_script = tmp_path / "dashboard" / "sim"
    sim_script.mkdir(parents=True)
    (sim_script / "sim.py").write_text("print('sim')\n")

    manager = SimulatorManager(tmp_path, host="127.0.0.1", port=8000)
    manager._proc = DummyProc()

    status = manager.stop()

    assert status["running"] is False
    assert manager._proc is None


def test_start_raises_when_script_missing(tmp_path):
    manager = SimulatorManager(tmp_path, host="127.0.0.1", port=8000)

    with pytest.raises(RuntimeError, match="Simulator script not found"):
        manager.start()
