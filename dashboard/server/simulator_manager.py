from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from threading import Lock


class SimulatorManager:
    def __init__(self, hab_root: Path, host: str, port: int):
        self._script = hab_root / 'dashboard' / 'sim' / 'sim.py'
        self._host = host
        self._port = port
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = Lock()
        self._launched_at: float | None = None
        self._mode = 'fast'
        self._phase = 'ascent'

    def _status_unlocked(self) -> dict:
        running = self._proc is not None and self._proc.poll() is None
        if not running:
            self._proc = None
        return {
            'running': running,
            'pid': self._proc.pid if running and self._proc else None,
            'host': self._host,
            'port': self._port,
            'mode': self._mode,
            'phase': self._phase,
            'launched_at': self._launched_at,
        }

    def status(self) -> dict:
        with self._lock:
            return self._status_unlocked()

    def start(self, fast: bool = True, start_at: str = 'ascent') -> dict:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return self._status_unlocked()

            if not self._script.exists():
                raise RuntimeError(f"Simulator script not found: {self._script}")

            cmd = [sys.executable, str(self._script), '--host', self._host, '--port', str(self._port), '--start-at', start_at]
            if fast:
                cmd.append('--fast')

            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._launched_at = time.time()
            self._mode = 'fast' if fast else 'realtime'
            self._phase = start_at
            return self._status_unlocked()

    def stop(self) -> dict:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = None
                return self._status_unlocked()

            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=3)
            self._proc = None
            return self._status_unlocked()

    def cleanup(self) -> None:
        self.stop()
