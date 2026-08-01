"""Central logging sink for the receiver server and dashboard clients."""

from __future__ import annotations

import asyncio
import logging
import threading
import weakref
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from typing import Any


_LOG_PATH = Path(__file__).with_name("a.log")
_LOGGER_NAMES = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "fastapi")
_setup_lock = threading.Lock()
_handler: DashboardLogHandler | None = None


class DashboardLogHandler(logging.Handler):
    """Write records to disk and mirror them to connected WebSocket clients."""

    def __init__(self, ws_manager: Any | None = None) -> None:
        super().__init__(level=logging.DEBUG)
        self._ws_manager = ws_manager
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._write_lock = threading.Lock()
        self._binding_lock = threading.Lock()
        self._seen_records: weakref.WeakSet[logging.LogRecord] = weakref.WeakSet()
        self._dashboard_log_handler = True

    def set_ws_manager(self, ws_manager: Any | None) -> None:
        """Bind the connection manager after the FastAPI app constructs it."""
        with self._binding_lock:
            self._ws_manager = ws_manager
        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            # create_app() normally runs before uvicorn starts its event loop.
            pass

    def emit(self, record: logging.LogRecord) -> None:
        try:
            with self._write_lock:
                # The handler is attached to root and uvicorn/FastAPI loggers.
                # A single record may therefore reach it more than once.
                if record in self._seen_records:
                    return
                self._seen_records.add(record)

                timestamp = datetime.fromtimestamp(record.created).astimezone()
                level = self._normalize_level(record.levelname)
                message = self._format_message(record)
                disk_line = (
                    f"{timestamp.isoformat(timespec='milliseconds')} "
                    f"[{level}] {record.name}: {message}\n"
                )
                with _LOG_PATH.open("a", encoding="utf-8") as log_file:
                    log_file.write(disk_line)

            self._broadcast(
                {
                    "type": "log",
                    "timestamp": timestamp.strftime("%H:%M:%S"),
                    "level": level,
                    "message": message,
                }
            )
        except Exception:
            self.handleError(record)

    @staticmethod
    def _normalize_level(level: str) -> str:
        normalized = level.upper()
        if normalized == "WARNING":
            return "WARN"
        if normalized == "CRITICAL":
            return "ERROR"
        return normalized

    @staticmethod
    def _format_message(record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            traceback_text = logging.Formatter().formatException(record.exc_info)
            message = f"{message}\n{traceback_text}"
        return message

    def _broadcast(self, entry: dict[str, str]) -> None:
        with self._binding_lock:
            ws_manager = self._ws_manager
        if ws_manager is None:
            return

        coroutine = ws_manager.broadcast(entry)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = self._event_loop
            if loop is None or not loop.is_running():
                coroutine.close()
                return
            try:
                future = asyncio.run_coroutine_threadsafe(coroutine, loop)
            except Exception:
                coroutine.close()
                return
            future.add_done_callback(self._consume_future_result)
            return

        self._event_loop = loop
        task = loop.create_task(coroutine)
        task.add_done_callback(self._consume_future_result)

    @staticmethod
    def _consume_future_result(future: asyncio.Future[Any] | Future[Any]) -> None:
        """Retrieve asynchronous errors without recursively logging them."""
        try:
            future.result()
        except BaseException:
            pass


def setup_logging(ws_manager: Any | None = None) -> DashboardLogHandler:
    """Install and return the process-wide dashboard logging handler."""
    global _handler

    with _setup_lock:
        if _handler is None:
            root_logger = logging.getLogger()
            existing = next(
                (
                    candidate
                    for candidate in root_logger.handlers
                    if getattr(candidate, "_dashboard_log_handler", False)
                ),
                None,
            )
            if isinstance(existing, DashboardLogHandler):
                _handler = existing
            else:
                _handler = DashboardLogHandler()

        _handler.set_ws_manager(ws_manager)
        for logger_name in _LOGGER_NAMES:
            target_logger = logging.getLogger(logger_name)
            if _handler not in target_logger.handlers:
                target_logger.addHandler(_handler)

        logging.getLogger().setLevel(logging.DEBUG)
        return _handler


if __name__ == "__main__":
    setup_logging()
