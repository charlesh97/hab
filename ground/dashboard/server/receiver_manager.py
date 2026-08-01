# receiver-server/receiver_manager.py
"""Receiver state machine — lifecycle management with automatic error recovery."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from models import ReceiverState, SpectrumFrame
from config import ReceiverConfig


logger = logging.getLogger("receiver")


class InvalidStateError(Exception):
    def __init__(self, state: ReceiverState):
        super().__init__(f"Cannot perform operation in state: {state}")


class ReceiverManager:
    def __init__(self, ws_manager, config: ReceiverConfig, db_path: str | None = None):
        self._ws = ws_manager
        self._config = config
        self._state = ReceiverState.IDLE
        self._packet_buffer: deque[dict] = deque(maxlen=1000)
        self._receiver = None
        self._bridge_task: asyncio.Task | None = None
        self._status_task: asyncio.Task | None = None
        self._packets_total = 0
        self._packets_valid = 0
        self._spectrum_frame = None
        self._start_time: float | None = None
        self._db_path = db_path
        self._db_conn: sqlite3.Connection | None = None
        if db_path:
            try:
                self._db_conn = sqlite3.connect(str(db_path))
                self._db_conn.execute(
                    "CREATE TABLE IF NOT EXISTS packets ("
                    "  seq INTEGER PRIMARY KEY,"
                    "  received_at TEXT NOT NULL,"
                    "  type TEXT NOT NULL,"
                    "  payload TEXT NOT NULL"
                    ")"
                )
                self._db_conn.commit()
            except sqlite3.Error:
                logger.exception("Failed to initialize packet database: %s", db_path)
                raise

    @property
    def state(self) -> ReceiverState:
        return self._state

    @property
    def packet_buffer(self) -> list[dict]:
        return list(self._packet_buffer)

    @property
    def uptime_sec(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    async def start(self):
        if self._state not in (ReceiverState.IDLE, ReceiverState.ERROR):
            raise InvalidStateError(self._state)
        self._state = ReceiverState.STARTING
        self._start_time = time.time()
        await self._ws.broadcast_status(self._build_status())
        try:
            result = self._start_receiver()
            if asyncio.iscoroutine(result):
                await result
            self._state = ReceiverState.RUNNING
            await self._ws.broadcast_status(self._build_status())
            self._status_task = asyncio.create_task(self._status_broadcast_loop())
        except Exception:
            await self._cleanup()
            self._state = ReceiverState.IDLE
            raise

    async def _status_broadcast_loop(self):
        """Broadcast status every 2 seconds while running."""
        try:
            while self._state == ReceiverState.RUNNING:
                await asyncio.sleep(2)
                if self._state == ReceiverState.RUNNING:
                    await self._ws.broadcast_status(self._build_status())
        except asyncio.CancelledError:
            pass

    async def stop(self):
        if self._state != ReceiverState.RUNNING:
            return
        self._state = ReceiverState.STOPPING
        await self._cleanup()
        self._state = ReceiverState.IDLE
        self._start_time = None
        await self._ws.broadcast_status(self._build_status())

    async def configure(self, updates: dict):
        if self._state != ReceiverState.RUNNING:
            return
        for key in ("freq_hz", "gain_lna", "gain_vga", "gain_amp",
                     "symbol_rate", "sps"):
            if key in updates:
                setattr(self._config, key, updates[key])

    async def _start_receiver(self):
        """Launch the composite video and telemetry receiver."""
        hab_root = Path(__file__).resolve().parent.parent.parent.parent
        rx_script = hab_root / "ground" / "rx" / "combined_rx.py"
        if not rx_script.is_file():
            raise FileNotFoundError(f"RX script not found: {rx_script}")

        server_port = getattr(self._config, "server_port", 8000)
        dashboard_url = f"http://localhost:{server_port}/api/packet"
        cmd = [
            sys.executable,
            str(rx_script),
            "--center-freq", str(int(self._config.freq_hz)),
            "--sample-rate", "4000000",
            "--lna", str(self._config.gain_lna or 32),
            "--vga", str(self._config.gain_vga or 40),
            "--udp-host", "127.0.0.1",
            "--udp-port", "1234",
            "--dashboard", dashboard_url,
        ]
        if getattr(self._config, "gain_amp", False):
            cmd.append("--amp")
        if self._config.serial:
            cmd.extend(["--serial", self._config.serial])

        self._receiver = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._bridge_task = asyncio.create_task(
            self._read_receiver_lines()
        )

    async def _read_receiver_lines(self):
        """Log output from the composite receiver until it exits."""
        try:
            if self._receiver is None or self._receiver.stdout is None:
                return
            async for line in self._receiver.stdout:
                line = line.decode("utf-8", errors="replace").strip()
                if line:
                    logger.info("RX: %s", line)
            return_code = await self._receiver.wait()
            logger.info("RX process exited with status %d", return_code)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error reading receiver output")

    def _stop_receiver(self):
        """Terminate the RX subprocess."""
        if self._receiver is not None:
            try:
                self._receiver.terminate()
            except ProcessLookupError:
                pass
        if self._bridge_task and not self._bridge_task.done():
            self._bridge_task.cancel()

    async def ingest_packet(self, packet: dict):
        """Receive and broadcast a telemetry packet from external sources.

        Called by the REST API when an external client (e.g. balloon-sim.py)
        POSTs a packet.  Appends to the packet buffer, updates counters,
        and broadcasts to all connected WebSocket clients.
        """
        logger.info(
            "Ingesting packet type=%s seq=%s",
            packet.get("type", "unknown"),
            packet.get("seq", "unknown"),
        )
        self._packet_buffer.append(packet)
        self._packets_total += 1
        self._packets_valid += 1
        await self._ws.broadcast({"type": "telemetry", "data": packet})
        self._save_packet(packet)

    async def _cleanup(self):
        self._stop_receiver()
        self._receiver = None
        if self._db_conn:
            self._db_conn.close()
            self._db_conn = None
        if self._status_task and not self._status_task.done():
            self._status_task.cancel()
            try:
                await self._status_task
            except asyncio.CancelledError:
                pass
        self._bridge_task = None
        self._status_task = None

    def _build_status(self) -> dict:
        """Build engine status dict matching what the dashboard expects."""
        return {
            "running": self._state == ReceiverState.RUNNING,
            "state": self._state.value,
            "tx_active": False,
            "rx_active": self._state == ReceiverState.RUNNING,
            "device_connected": True,
            "device_serial": "hackrf",
            "frequency": float(self._config.freq_hz),
            "symbol_rate": float(self._config.symbol_rate),
            "uptime_sec": self.uptime_sec,
            "pipeline": None,
            "error_count": 0,
            "last_error": "",
        }

    def _save_packet(self, packet: dict):
        if self._db_conn is None:
            return
        try:
            self._db_conn.execute(
                "INSERT OR REPLACE INTO packets (seq, received_at, type, payload) VALUES (?, ?, ?, ?)",
                (
                    packet.get("seq", 0),
                    datetime.now(timezone.utc).isoformat(),
                    packet.get("type", "unknown"),
                    json.dumps(packet),
                ),
            )
            self._db_conn.commit()
        except sqlite3.Error:
            logger.error(
                "SQLite error writing packet seq=%s", packet.get("seq"),
                exc_info=True,
            )
        except Exception:
            logger.exception(
                "Failed to serialize packet seq=%s for database",
                packet.get("seq"),
            )
