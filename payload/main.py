import os
import signal
import stat
import subprocess
import threading
from collections.abc import Callable

from telemetry import writer as telemetry_writer
from tx import tx_pipeline


TELEMETRY_FIFO = "/tmp/tel_fifo"
TRANSPORT_FIFO = "/tmp/tsfifo"
MONITOR_INTERVAL = 1.0
SHUTDOWN_TIMEOUT = 5.0


def status(message: str) -> None:
    print(message, flush=True)


def ensure_fifo(path: str) -> None:
    try:
        os.mkfifo(path, 0o600)
        status(f"Created named pipe: {path}")
    except FileExistsError:
        if not stat.S_ISFIFO(os.lstat(path).st_mode):
            raise RuntimeError(f"Path exists but is not a named pipe: {path}")
        status(f"Using existing named pipe: {path}")


def launch_process(
    name: str,
    launcher: Callable[[], subprocess.Popen],
    shutdown_event: threading.Event,
) -> subprocess.Popen | None:
    if shutdown_event.is_set():
        return None

    try:
        process = launcher()
        status(f"Started {name} (PID {process.pid})")
        return process
    except Exception as exc:
        status(f"Failed to start {name}: {exc}")
        return None


def stop_process(name: str, process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return

    status(f"Stopping {name} (PID {process.pid})")
    try:
        process.terminate()
        process.wait(timeout=SHUTDOWN_TIMEOUT)
    except subprocess.TimeoutExpired:
        status(f"{name} did not stop; killing PID {process.pid}")
        process.kill()
        try:
            process.wait(timeout=SHUTDOWN_TIMEOUT)
        except subprocess.TimeoutExpired:
            status(f"{name} PID {process.pid} could not be reaped")
    except ProcessLookupError:
        pass
    except Exception as exc:
        status(f"Error while stopping {name}: {exc}")


def remove_fifo(path: str) -> None:
    try:
        if stat.S_ISFIFO(os.lstat(path).st_mode):
            os.unlink(path)
            status(f"Removed named pipe: {path}")
        else:
            status(f"Refusing to remove non-FIFO path: {path}")
    except FileNotFoundError:
        pass
    except OSError as exc:
        status(f"Failed to remove {path}: {exc}")


def main() -> int:
    shutdown_event = threading.Event()
    telemetry_thread = None
    processes: dict[str, subprocess.Popen | None] = {
        "ffmpeg": None,
        "dvbs2-tx": None,
    }
    managed_fifos: list[str] = []

    def request_shutdown(signum: int, _frame: object) -> None:
        if not shutdown_event.is_set():
            status(f"Received signal {signum}; shutting down")
            shutdown_event.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    launchers: dict[str, Callable[[], subprocess.Popen]] = {
        "ffmpeg": lambda: tx_pipeline.launch_ffmpeg(TRANSPORT_FIFO),
        "dvbs2-tx": lambda: tx_pipeline.launch_dvbs2_tx(
            TRANSPORT_FIFO,
            913,
            1e6,
            "QPSK1/2",
        ),
    }

    try:
        for fifo_path in (TELEMETRY_FIFO, TRANSPORT_FIFO):
            ensure_fifo(fifo_path)
            managed_fifos.append(fifo_path)

        if not shutdown_event.is_set():
            status("Starting telemetry writer")
            telemetry_thread = telemetry_writer.start_telemetry_writer(
                TELEMETRY_FIFO
            )
            status("Telemetry writer started")

        for name, launcher in launchers.items():
            processes[name] = launch_process(
                name,
                launcher,
                shutdown_event,
            )

        while not shutdown_event.wait(MONITOR_INTERVAL):
            if telemetry_thread is None or not telemetry_thread.is_alive():
                status("Telemetry writer stopped; restarting")
                try:
                    telemetry_thread = telemetry_writer.start_telemetry_writer(
                        TELEMETRY_FIFO
                    )
                    status("Telemetry writer restarted")
                except Exception as exc:
                    status(f"Failed to restart telemetry writer: {exc}")

            for name, launcher in launchers.items():
                process = processes[name]
                if process is None:
                    status(f"{name} is not running; starting")
                    processes[name] = launch_process(
                        name,
                        launcher,
                        shutdown_event,
                    )
                    continue

                return_code = process.poll()
                if return_code is not None:
                    status(
                        f"{name} exited with status {return_code}; restarting"
                    )
                    processes[name] = launch_process(
                        name,
                        launcher,
                        shutdown_event,
                    )

    finally:
        shutdown_event.set()

        for name, process in processes.items():
            stop_process(name, process)

        if telemetry_thread is not None:
            status("Stopping telemetry writer")
            try:
                telemetry_thread.stop()
                telemetry_thread.join(timeout=SHUTDOWN_TIMEOUT)
                if telemetry_thread.is_alive():
                    status("Telemetry writer did not stop before timeout")
                else:
                    status("Telemetry writer stopped")
            except Exception as exc:
                status(f"Error while stopping telemetry writer: {exc}")

        for fifo_path in reversed(managed_fifos):
            remove_fifo(fifo_path)

        status("Payload integration orchestrator stopped")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
