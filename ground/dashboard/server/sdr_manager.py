"""Lifecycle manager for the wideband SDR receive worker."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

if __package__:
    from .config import ReceiverConfig
    from .models import ReceiverState
else:
    from config import ReceiverConfig
    from models import ReceiverState


logger = logging.getLogger("sdr")

_WORKER_READY_TIMEOUT_SEC = 15.0
_WORKER_STOP_TIMEOUT_SEC = 3.0
_FFMPEG_STOP_TIMEOUT_SEC = 3.0


class InvalidStateError(Exception):
    def __init__(self, state: ReceiverState):
        super().__init__(f"Cannot perform operation in state: {state}")


class SdrManager:
    """Start, configure, and stop ``sdr_rx_worker.py``."""

    def __init__(
        self,
        ws_manager,
        config: ReceiverConfig,
        db_path: str | None = None,
    ) -> None:
        self._ws = ws_manager
        self._config = config
        self._db_path = db_path
        self._state = ReceiverState.IDLE
        self._worker: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._worker_stderr_task: asyncio.Task | None = None
        self._ffmpeg_process: asyncio.subprocess.Process | None = None
        self._ffmpeg_stderr_task: asyncio.Task | None = None
        self._logged_ffmpeg_exit: asyncio.subprocess.Process | None = None
        self._start_time: float | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._worker_config = self._build_worker_config()
        self._last_dvbs2_locked: bool | None = None
        self._last_snr_db: float | None = None
        self._last_worker_error: str | None = None

    @property
    def state(self) -> ReceiverState:
        return self._state

    @property
    def uptime_sec(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def _transition_to(self, state: ReceiverState) -> None:
        previous = self._state
        self._state = state
        if previous != state:
            logger.info(
                "Pipeline state transition: %s -> %s",
                previous.value,
                state.value,
            )


    async def start(self) -> None:
        """Spawn the worker and wait for its ``start`` acknowledgement."""
        async with self._lifecycle_lock:
            if self._state not in (ReceiverState.IDLE, ReceiverState.ERROR):
                raise InvalidStateError(self._state)

            self._last_dvbs2_locked = None
            self._last_snr_db = None
            self._last_worker_error = None
            self._transition_to(ReceiverState.STARTING)
            await self._ws.broadcast_status(self._build_status())

            try:
                await self._spawn_worker()

                # The worker announces that its command loop is ready before it
                # accepts the first command. Its second ready response confirms
                # that the SDR flowgraph has started successfully.
                await self._wait_for_ready("worker startup")
                await self._send_command(
                    "start", data=dict(self._worker_config)
                )
                await self._wait_for_ready("SDR start")
                await self._spawn_ffmpeg()

                self._transition_to(ReceiverState.RUNNING)
                self._start_time = time.time()
                self._reader_task = asyncio.create_task(
                    self._read_worker_lines(),
                    name="sdr-worker-output",
                )
                await self._ws.broadcast_status(self._build_status())
            except Exception:
                logger.exception("Failed to start SDR pipeline")
                await self._terminate_ffmpeg()
                await self._terminate_worker()
                self._transition_to(ReceiverState.IDLE)
                self._start_time = None
                await self._ws.broadcast_status(self._build_status())
                raise

    async def stop(self) -> None:
        """Ask the worker to stop its flowgraph, then end the process."""
        async with self._lifecycle_lock:
            if self._state != ReceiverState.RUNNING:
                return

            self._transition_to(ReceiverState.STOPPING)
            await self._ws.broadcast_status(self._build_status())

            try:
                await self._send_command("stop")
            except (BrokenPipeError, ConnectionError, RuntimeError):
                logger.warning("SDR worker exited before the stop command")
            finally:
                await self._terminate_ffmpeg()
                await self._terminate_worker()

            self._transition_to(ReceiverState.IDLE)
            self._start_time = None
            await self._ws.broadcast_status(self._build_status())

    async def configure(self, updates: dict[str, Any]) -> None:
        """Apply configuration now, and live-reconfigure if worker is running."""
        if not isinstance(updates, dict):
            raise TypeError("SDR configuration updates must be a JSON object")

        # Always update local config so start() picks it up
        self._worker_config.update(updates)
        self._update_receiver_config(updates)

        # If worker is already running, push change live
        if self._state == ReceiverState.RUNNING:
            logger.info("Applying live SDR configuration: %s", updates)
            await self._send_command("configure", data=updates)

    async def _spawn_worker(self) -> None:
        worker_script = Path(__file__).with_name("sdr_rx_worker.py")
        if not worker_script.is_file():
            raise FileNotFoundError(f"SDR worker not found: {worker_script}")
        worker_python = Path("/opt/homebrew/bin/python3.14")
        if not worker_python.is_file():
            worker_python = Path(sys.executable)

        self._worker = await asyncio.create_subprocess_exec(
            str(worker_python),
            str(worker_script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("SDR worker started (pid=%s)", self._worker.pid)
        self._worker_stderr_task = asyncio.create_task(
            self._read_worker_stderr(self._worker),
            name="sdr-worker-stderr",
        )

    async def _read_worker_stderr(
        self, worker: asyncio.subprocess.Process
    ) -> None:
        """Forward the worker's diagnostic stderr through central logging."""
        if worker.stderr is None:
            return

        try:
            while raw_line := await worker.stderr.readline():
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line:
                    logger.info("worker: %s", line)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error reading SDR worker stderr")

    async def _spawn_ffmpeg(self) -> None:
        logger.info("Starting ffmpeg video pipeline")
        self._ffmpeg_process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-err_detect", "ignore_err",
            "-ec", "0",
            "-fflags", "+genpts+discardcorrupt",
            "-i",
            "/tmp/dvbs2_ts_pipe",
            "-c:v",
            "mjpeg",
            "-q:v",
            "5",
            "-f",
            "mjpeg",
            "-listen",
            "1",
            "-r",
            "15",
            "http://0.0.0.0:8001/video",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._logged_ffmpeg_exit = None
        logger.info("ffmpeg started (pid=%s)", self._ffmpeg_process.pid)
        self._ffmpeg_stderr_task = asyncio.create_task(
            self._read_ffmpeg_stderr(self._ffmpeg_process),
            name="sdr-ffmpeg-stderr",
        )

    async def _read_ffmpeg_stderr(
        self, process: asyncio.subprocess.Process
    ) -> None:
        """Drain and log ffmpeg stderr so its pipe cannot block ffmpeg."""
        if process.stderr is None:
            return

        try:
            while raw_line := await process.stderr.readline():
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line:
                    logger.info("ffmpeg: %s", line)
            await process.wait()
            self._log_ffmpeg_exit(process)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error reading ffmpeg stderr")

    def _log_ffmpeg_exit(self, process: asyncio.subprocess.Process) -> None:
        if self._logged_ffmpeg_exit is process:
            return
        self._logged_ffmpeg_exit = process
        logger.info("ffmpeg exited with code %s", process.returncode)

    async def _send_command(
        self,
        command: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> None:
        worker = self._worker
        if worker is None or worker.stdin is None:
            raise RuntimeError("SDR worker is not running")

        message: dict[str, Any] = {"command": command}
        if data is not None:
            message["data"] = data
        worker.stdin.write(
            (json.dumps(message, separators=(",", ":")) + "\n").encode()
        )
        await worker.stdin.drain()

    async def _wait_for_ready(self, operation: str) -> None:
        """Read protocol messages until the worker acknowledges an operation."""
        while True:
            message = await self._read_worker_message(operation)
            message_type = message.get("type")
            if message_type == "ready":
                return
            if message_type == "error":
                detail = message.get("message", "Unknown worker error")
                logger.error("SDR worker error during %s: %s", operation, detail)
                raise RuntimeError(str(detail))
            if message_type == "status":
                await self._broadcast_worker_status(message)
            else:
                logger.warning("Unexpected SDR worker message: %s", message)

    async def _read_worker_message(self, operation: str) -> dict[str, Any]:
        worker = self._worker
        if worker is None or worker.stdout is None:
            raise RuntimeError("SDR worker stdout is unavailable")

        try:
            raw_line = await asyncio.wait_for(
                worker.stdout.readline(),
                timeout=_WORKER_READY_TIMEOUT_SEC,
            )
        except TimeoutError as exc:
            raise RuntimeError(
                f"Timed out waiting for {operation} acknowledgement"
            ) from exc

        if not raw_line:
            raise RuntimeError(
                f"SDR worker exited during {operation}"
            )
        try:
            message = json.loads(raw_line.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Invalid JSON from SDR worker during {operation}"
            ) from exc
        if not isinstance(message, dict):
            raise RuntimeError(
                f"Invalid response from SDR worker during {operation}"
            )
        return message

    async def _read_worker_lines(self) -> None:
        """Forward periodic worker status messages to WebSocket clients."""
        worker = self._worker
        if worker is None or worker.stdout is None:
            return

        try:
            async for raw_line in worker.stdout:
                try:
                    message = json.loads(
                        raw_line.decode("utf-8", errors="replace")
                    )
                except json.JSONDecodeError:
                    logger.warning("Ignoring invalid JSON from SDR worker")
                    continue
                if not isinstance(message, dict):
                    logger.warning("Ignoring non-object SDR worker message")
                    continue

                message_type = message.get("type")
                if message_type == "status":
                    await self._broadcast_worker_status(message)
                elif message_type == "error":
                    detail = str(
                        message.get("message", "Unknown SDR worker error")
                    )
                    logger.error("SDR worker error: %s", detail)
                    await self._ws.broadcast_error(
                        "HARDWARE_ERR",
                        detail,
                    )
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error reading SDR worker output")
        finally:
            # Only tear down if the worker process actually died (pipe closed)
            if self._state == ReceiverState.RUNNING and (
                self._worker is None or self._worker.returncode is not None
            ):
                await self._terminate_ffmpeg()
                logger.error("SDR worker exited unexpectedly")
                self._transition_to(ReceiverState.IDLE)
                self._start_time = None
                await self._ws.broadcast_error(
                    "HARDWARE_ERR", "SDR worker exited unexpectedly"
                )
                await self._ws.broadcast_status(self._build_status())

    async def _broadcast_worker_status(self, message: dict[str, Any]) -> None:
        dvbs2 = message.get("dvbs2")
        if isinstance(dvbs2, dict):
            locked = dvbs2.get("locked")
            if isinstance(locked, bool) and locked != self._last_dvbs2_locked:
                logger.info("DVB-S2 %s", "locked" if locked else "unlocked")
                self._last_dvbs2_locked = locked

            snr_value = dvbs2.get("snr_db")
            if isinstance(snr_value, (int, float)):
                snr_db = float(snr_value)
                if (
                    self._last_snr_db is None
                    or abs(snr_db - self._last_snr_db) >= 0.1
                ):
                    if self._last_snr_db is None:
                        logger.info("DVB-S2 SNR: %.1f dB", snr_db)
                    else:
                        logger.info(
                            "DVB-S2 SNR changed: %.1f -> %.1f dB",
                            self._last_snr_db,
                            snr_db,
                        )
                    self._last_snr_db = snr_db

        worker_error = message.get("error") or message.get("last_error")
        if worker_error:
            error_text = str(worker_error)
            if error_text != self._last_worker_error:
                logger.error("SDR worker status error: %s", error_text)
                self._last_worker_error = error_text

        status = self._build_status()
        for key in ("dvbs2", "hackrf"):
            if key in message:
                status[key] = message[key]
        await self._ws.broadcast_status(status)

    async def _terminate_worker(self) -> None:
        worker = self._worker
        reader_task = self._reader_task
        stderr_task = self._worker_stderr_task

        if worker is not None:
            if worker.returncode is None:
                try:
                    worker.terminate()
                except ProcessLookupError:
                    pass

            if worker.stdin is not None:
                worker.stdin.close()
                try:
                    await worker.stdin.wait_closed()
                except (AttributeError, BrokenPipeError, ConnectionError):
                    pass

            try:
                await asyncio.wait_for(
                    worker.wait(), timeout=_WORKER_STOP_TIMEOUT_SEC
                )
            except TimeoutError:
                if worker.returncode is None:
                    try:
                        worker.kill()
                    except ProcessLookupError:
                        pass
                    await worker.wait()

            logger.info("SDR worker exited with code %s", worker.returncode)

        if reader_task is not None and not reader_task.done():
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass

        if stderr_task is not None and not stderr_task.done():
            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass

        self._reader_task = None
        self._worker_stderr_task = None
        self._worker = None

    async def _terminate_ffmpeg(self) -> None:
        process = self._ffmpeg_process
        stderr_task = self._ffmpeg_stderr_task

        if process is not None:
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass

            try:
                await asyncio.wait_for(
                    process.wait(), timeout=_FFMPEG_STOP_TIMEOUT_SEC
                )
            except TimeoutError:
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    await process.wait()

            self._log_ffmpeg_exit(process)

        if stderr_task is not None and not stderr_task.done():
            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass

        self._ffmpeg_stderr_task = None
        self._ffmpeg_process = None

    def _build_worker_config(self) -> dict[str, Any]:
        return {
            "freq_hz": self._config.freq_hz,
            "sample_rate": self._config.sample_rate,
            "symbol_rate": self._config.symbol_rate,
            "dvbs2_offset_hz": getattr(
                self._config, "dvbs2_offset_hz", -2_000_000
            ),
            "modcod": getattr(self._config, "modcod", "QPSK1/2"),
            "lna": self._config.gain_lna,
            "vga": self._config.gain_vga,
            "amp": bool(self._config.gain_amp),
            "serial": self._config.serial,
        }

    def _update_receiver_config(self, updates: dict[str, Any]) -> None:
        field_map = {
            "freq_hz": "freq_hz",
            "sample_rate": "sample_rate",
            "symbol_rate": "symbol_rate",
            "dvbs2_offset_hz": "dvbs2_offset_hz",
            "modcod": "modcod",
            "lna": "gain_lna",
            "vga": "gain_vga",
            "amp": "gain_amp",
            "serial": "serial",
        }
        for worker_field, config_field in field_map.items():
            if worker_field in updates:
                setattr(self._config, config_field, updates[worker_field])

    def _build_status(self) -> dict[str, Any]:
        running = self._state == ReceiverState.RUNNING
        return {
            "running": running,
            "state": self._state.value,
            "tx_active": False,
            "rx_active": running,
            "device_connected": running,
            "device_serial": self._worker_config.get("serial") or "hackrf",
            "frequency": float(self._worker_config["freq_hz"]),
            "symbol_rate": float(self._worker_config["symbol_rate"]),
            "uptime_sec": self.uptime_sec,
            "pipeline": {"running": running},
            "error_count": 0,
            "last_error": "",
        }
