from __future__ import annotations

import errno
import logging
import os
import signal
import stat
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from types import FrameType

from gps.nmea import NMEAParser
from sensors import LIS2DH, LPS25HB, MAX17049, TMP100

from . import packer


_LOGGER = logging.getLogger(__name__)
_active_writer: TelemetryWriterThread | None = None
_writer_lock = threading.Lock()
_previous_sigterm_handler = None


def _ensure_fifo(fifo_path: str | os.PathLike[str]) -> str:
    path = os.fspath(Path(fifo_path))

    try:
        os.mkfifo(path, 0o600)
    except FileExistsError:
        if not stat.S_ISFIFO(os.stat(path).st_mode):
            raise ValueError(f"path exists but is not a named pipe: {path}")

    return path


def _clamp_uint8(value: object) -> int:
    try:
        return max(0, min(255, int(round(float(value)))))
    except (TypeError, ValueError, OverflowError):
        return 0


class TelemetryWriterThread(threading.Thread):
    def __init__(self, fifo_path: str) -> None:
        super().__init__(name="telemetry-writer", daemon=True)
        self.fifo_path = fifo_path
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def _open_fifo(self) -> int | None:
        while not self.stop_event.is_set():
            try:
                return os.open(
                    self.fifo_path,
                    os.O_WRONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0),
                )
            except OSError as exc:
                if exc.errno in (errno.ENXIO, errno.ENOENT, errno.EINTR):
                    self.stop_event.wait(0.1)
                    continue
                raise
        return None

    def run(self) -> None:
        gps_data = {
            "lat": 0.0,
            "lon": 0.0,
            "altitude": 0.0,
            "fix_quality": 0,
        }

        try:
            with ExitStack() as stack:
                temperature = stack.enter_context(TMP100(0))
                accelerometer = stack.enter_context(LIS2DH(0))
                pressure = stack.enter_context(LPS25HB(0))
                battery = stack.enter_context(MAX17049(1))
                gps = stack.enter_context(NMEAParser("/dev/ttyS0"))

                while not self.stop_event.is_set():
                    fifo_fd = self._open_fifo()
                    if fifo_fd is None:
                        break

                    try:
                        while not self.stop_event.is_set():
                            cycle_started = time.monotonic()

                            try:
                                temp_c = temperature.read_temperature()
                                pressure_hpa = pressure.read_pressure()
                                accel_x, accel_y, accel_z = accelerometer.read_accel()
                                battery_v = battery.read_voltage()
                                battery_soc = _clamp_uint8(battery.read_soc())

                                sentence = gps.read_sentence()
                                if sentence is not None:
                                    fix = gps.parse_gga(sentence)
                                    if fix is not None:
                                        for key in (
                                            "lat",
                                            "lon",
                                            "altitude",
                                            "fix_quality",
                                        ):
                                            if fix.get(key) is not None:
                                                gps_data[key] = fix[key]
                                    else:
                                        position = gps.parse_rmc(sentence)
                                        if position is not None:
                                            for key in ("lat", "lon"):
                                                if position.get(key) is not None:
                                                    gps_data[key] = position[key]

                                frame = packer.pack_frame(
                                    float(temp_c),
                                    float(pressure_hpa),
                                    float(accel_x),
                                    float(accel_y),
                                    float(accel_z),
                                    float(gps_data["lat"]),
                                    float(gps_data["lon"]),
                                    float(gps_data["altitude"]),
                                    _clamp_uint8(gps_data["fix_quality"]),
                                    float(battery_v),
                                    battery_soc,
                                )

                                os.write(fifo_fd, frame)
                            except (BrokenPipeError, BlockingIOError):
                                break
                            except OSError as exc:
                                if exc.errno in (
                                    errno.EPIPE,
                                    errno.ENXIO,
                                    errno.EBADF,
                                ):
                                    break
                                _LOGGER.exception("telemetry polling failed")
                            except Exception:
                                _LOGGER.exception("telemetry polling failed")

                            remaining = 1.0 - (time.monotonic() - cycle_started)
                            if remaining > 0:
                                self.stop_event.wait(remaining)
                    finally:
                        os.close(fifo_fd)
        except Exception:
            _LOGGER.exception("telemetry writer stopped unexpectedly")


def _handle_sigterm(signum: int, frame: FrameType | None) -> None:
    with _writer_lock:
        writer = _active_writer
        previous_handler = _previous_sigterm_handler

    if writer is not None:
        writer.stop()

    if callable(previous_handler) and previous_handler is not _handle_sigterm:
        previous_handler(signum, frame)


def start_telemetry_writer(
    fifo_path: str | os.PathLike[str],
) -> TelemetryWriterThread:
    global _active_writer, _previous_sigterm_handler

    path = _ensure_fifo(fifo_path)

    with _writer_lock:
        if _active_writer is not None and _active_writer.is_alive():
            if _active_writer.fifo_path != path:
                raise RuntimeError("a telemetry writer is already running")
            return _active_writer

        writer = TelemetryWriterThread(path)
        _active_writer = writer

        if threading.current_thread() is threading.main_thread():
            current_handler = signal.getsignal(signal.SIGTERM)
            if current_handler is not _handle_sigterm:
                _previous_sigterm_handler = current_handler
                signal.signal(signal.SIGTERM, _handle_sigterm)

        writer.start()
        return writer
