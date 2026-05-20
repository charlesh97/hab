"""Flowgraph Manager — manages the DVB-S2 TX GNU Radio flowgraph lifecycle via subprocess."""

import json
import logging
import os
import signal
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Optional, Callable

from .models import SpectrumFrame

logger = logging.getLogger(__name__)

WORKER_SCRIPT = str(Path(__file__).parent.parent / "dvbs2_tx_worker.py")


class FlowgraphManager:
    """
    Manages the DVB-S2 transmitter flowgraph lifecycle using a subprocess worker.
    The GNU Radio flowgraph runs in a separate process to avoid blocking the async event loop.
    """

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._running = False
        self._worker_ready = threading.Event()
        self._response_lock = threading.Lock()
        self._last_response: Optional[dict] = None
        self._response_event = threading.Event()
        self._read_thread: Optional[threading.Thread] = None
        self._spectrum_callback: Optional[Callable[[SpectrumFrame], None]] = None
        self._config = {
            "device_args": "driver=hackrf",
            "center_freq": 915e6,
            "symbol_rate": 1e6,
            "tx_gain_vga": 16.0,
            "tx_gain_amp": False,
            "file_path": "/tmp/tsfifo",
            "rolloff": 0.2,
            "modcod": "QPSK1/4",
            "pilots": True,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def config(self) -> dict:
        return dict(self._config)

    def set_spectrum_callback(self, callback: Callable[[SpectrumFrame], None]):
        self._spectrum_callback = callback

    def update_config(self, **kwargs):
        self._config.update(kwargs)

    def _read_worker_output(self):
        """Read stdout from the worker process and dispatch responses."""
        while self._process and self._process.poll() is None:
            try:
                line = self._process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue

                if line.startswith("{"):
                    try:
                        msg = json.loads(line)
                        self._handle_response(msg)
                    except json.JSONDecodeError:
                        logger.error(f"Worker JSON parse error: {line[:200]}")
                else:
                    logger.info(f"[worker] {line}")
            except Exception as e:
                logger.error(f"Worker read error: {e}")
                break
        logger.info("Worker output reader stopped")

    def _handle_response(self, msg: dict):
        """Handle a JSON response from the worker."""
        status = msg.get("status", "")
        error = msg.get("error", "")

        if status == "started":
            with self._lock:
                self._running = True
            logger.info("DVBS2 flowgraph started via worker")
        elif status in ("stopped", "already_stopped"):
            with self._lock:
                self._running = False
            logger.info(f"DVBS2 flowgraph {status} via worker")
        elif status == "ready":
            with self._response_lock:
                self._worker_ready.set()
            logger.info("Worker process ready")
        elif error:
            logger.error(f"Worker error: {error}")
        else:
            logger.debug(f"Worker response: {msg}")

    def _ensure_worker(self) -> bool:
        """Start the worker subprocess if not already running."""
        if self._process is not None and self._process.poll() is None:
            return True

        self._worker_ready = threading.Event()

        try:
            self._process = subprocess.Popen(
                [WORKER_SCRIPT],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
            )

            # Start reader thread
            self._read_thread = threading.Thread(
                target=self._read_worker_output, daemon=True
            )
            self._read_thread.start()

            # Wait for "ready" response
            ok = self._worker_ready.wait(timeout=5.0)
            if not ok:
                logger.warning("Worker process started but no 'ready' signal yet — continuing")
                # Process may still be alive; check after a moment
                time.sleep(0.5)
                if self._process.poll() is not None:
                    logger.error("Worker process died before becoming ready")
                    return False
            return True

        except Exception as e:
            logger.error(f"Failed to start worker: {e}")
            return False

    def _send_async(self, cmd: str, data: Optional[dict] = None):
        """Send a command to the worker without waiting for response (fire-and-forget)."""
        if self._process is None or self._process.poll() is not None:
            if not self._ensure_worker():
                return

        msg = {"command": cmd, "data": data or {}}
        try:
            self._process.stdin.write(json.dumps(msg) + "\n")
            self._process.stdin.flush()
        except BrokenPipeError:
            logger.error("Worker process died")
            self._cleanup()
        except Exception as e:
            logger.error(f"Worker send error on cmd={cmd}: {e}")

    def start(self) -> bool:
        """Start the DVB-S2 TX flowgraph via the worker subprocess (non-blocking)."""
        if self._running:
            logger.warning("Flowgraph already running")
            return False

        with self._lock:
            self._running = False  # Will be set True when worker responds
        
        self._send_async("start", self._config)
        return True

    def stop(self):
        """Stop the DVB-S2 TX flowgraph via the worker subprocess (non-blocking)."""
        with self._lock:
            was_running = self._running
            self._running = False
        
        if self._process and self._process.poll() is None:
            self._send_async("stop")
            
            # Give worker a moment to stop gracefully, then force kill if needed
            def _wait_and_cleanup():
                try:
                    self._process.wait(timeout=8.0)
                except subprocess.TimeoutExpired:
                    logger.warning("Worker not stopping — SIGTERM")
                    try:
                        self._process.terminate()
                        self._process.wait(timeout=5.0)
                    except subprocess.TimeoutExpired:
                        logger.warning("Worker not responding to SIGTERM — SIGKILL")
                        self._process.kill()
                        self._process.wait()
                self._process = None
                logger.info("DVBS2 worker process stopped")
            
            t = threading.Thread(target=_wait_and_cleanup, daemon=True)
            t.start()

    def reconfigure(self, **kwargs):
        """Reconfigure running flowgraph parameters (fire-and-forget)."""
        if self._process and self._process.poll() is None:
            self._send_async("reconfigure", kwargs)

    def _force_kill(self):
        """Force-kill the worker process."""
        if self._process:
            try:
                # Use SIGTERM first (gentle cleanup)
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Only SIGKILL as last resort
                logger.warning("Worker not responding to SIGTERM — using SIGKILL")
                self._process.kill()
                self._process.wait()
            except Exception:
                pass

    def _cleanup(self):
        """Full cleanup — kill the worker process."""
        self._running = False
        self._force_kill()
        self._process = None
        self._read_thread = None
        logger.info("DVBS2 worker cleanup done")

    def cleanup(self):
        self._cleanup()
