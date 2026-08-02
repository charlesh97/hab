#!/usr/bin/env python3
"""Receive the HAB DVB-S2 video and BPSK telemetry with one HackRF."""

from __future__ import annotations

import argparse
import errno
import logging
import os
import select
import shlex
import fcntl
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Thread

import numpy as np
import requests


_HAB = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_HAB / "protocol"))
sys.path.insert(0, str(_HAB / "ground" / "rx"))

from demod import FS as BPSK_SAMPLE_RATE  # noqa: E402
from demod import PacketDecoder  # noqa: E402
from telemetry import unpack_frame  # noqa: E402


LOG = logging.getLogger("combined_rx")
CHUNK_SAMPLES = 32_768
MAX_DVBS2_RESTARTS = 3
ERROR_LOG_INTERVAL = 10.0
BPSK_CHANNEL_CUTOFF_HZ = 180_000.0
CHANNEL_FILTER_TAPS = 129
BPSK_DECODE_SAMPLES = 1_048_576
DECODER_OVERLAP_SAMPLES = 30_000
VIDEO_PORT = 8001


def _wait_listener(port: int, timeout: float = 8.0) -> bool:
    """Wait for a TCP listener without consuming its first connection."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
        time.sleep(0.5)
    return False


def _next_fast_fft_size(minimum: int) -> int:
    """Return the next 2/3/5/7-smooth length for PocketFFT."""
    candidate = minimum
    while True:
        remainder = candidate
        for factor in (2, 3, 5, 7):
            while remainder % factor == 0:
                remainder //= factor
        if remainder == 1:
            return candidate
        candidate += 1


class RateLimitedLogger:
    """Suppress repeated warnings while a downstream service is unavailable."""

    def __init__(self, interval: float = ERROR_LOG_INTERVAL):
        self.interval = interval
        self._last_log: dict[str, float] = {}

    def warning(self, key: str, message: str, *args) -> None:
        now = time.monotonic()
        if now - self._last_log.get(key, -self.interval) >= self.interval:
            self._last_log[key] = now
            LOG.warning(message, *args)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Composite DVB-S2 and BPSK receiver for one HackRF"
    )
    parser.add_argument("--center-freq", type=float, default=914e6)
    parser.add_argument(
        "--offset", type=float, default=700e3,
        help="Frequency offset between DVB-S2 and BPSK subcarriers (Hz). "
        "MUST match the TX --offset value. Ignored when --no-bpsk is set.",
    )
    parser.add_argument(
        "--no-bpsk", action="store_true",
        help="Disable BPSK telemetry. Receive DVB-S2 only at center frequency.",
    )
    parser.add_argument("--sample-rate", type=float, default=8e6)
    parser.add_argument("--sym-rate", type=float, default=2e6)
    parser.add_argument("--lna", type=float, default=32)
    parser.add_argument("--vga", type=float, default=40)
    parser.add_argument("--amp", action="store_true")
    parser.add_argument("--serial")
    parser.add_argument("--dvbs2-fifo", default="/tmp/dvbs2_rx.iq")
    parser.add_argument(
        "--dvbs2-bin",
        default=str(_HAB / "dev" / "dvbs2" / "dvbs2" / "rx.py"),
    )
    parser.add_argument(
        "--dvbs2-args",
        default="",
        help="Additional arguments appended to the DVB-S2 receiver command",
    )
    parser.add_argument("--no-dvbs2", action="store_true", help="Disable DVB-S2, BPSK telemetry only")
    parser.add_argument("--udp-host", default="127.0.0.1")
    parser.add_argument("--udp-port", type=int, default=1234)
    parser.add_argument(
        "--dashboard",
        default="http://localhost:8000/api/packet",
    )
    args = parser.parse_args(argv)

    if args.sample_rate < 2e6:
        parser.error("--sample-rate must be at least 2000000")
    if args.sym_rate <= 0:
        parser.error("--sym-rate must be positive")
    if args.sample_rate / args.sym_rate < 2:
        parser.error("--sample-rate must provide at least 2 DVB-S2 samples/symbol")
    ratio = args.sample_rate / BPSK_SAMPLE_RATE
    if not np.isclose(ratio, round(ratio), rtol=0.0, atol=1e-9):
        parser.error("--sample-rate must be an integer multiple of 2000000")
    if args.no_bpsk:
        args.offset = 0.0
    return args


def _dvbs2_python() -> str:
    homebrew_python = Path("/opt/homebrew/bin/python3.14")
    if (
        sys.platform == "darwin"
        and homebrew_python.is_file()
        and os.access(homebrew_python, os.X_OK)
    ):
        return str(homebrew_python)
    return sys.executable


class Dvbs2Pipeline:
    """Own the FIFO and the DVB-S2 decoder subprocess."""

    def __init__(self, args: argparse.Namespace, errors: RateLimitedLogger):
        self.args = args
        self.errors = errors
        self.fifo_path = Path(args.dvbs2_fifo)
        self.process: subprocess.Popen | None = None
        self.write_fd: int | None = None
        self.restart_count = 0

    def _ensure_fifo(self) -> None:
        try:
            mode = self.fifo_path.stat().st_mode
        except FileNotFoundError:
            os.mkfifo(self.fifo_path)
            return
        if not stat.S_ISFIFO(mode):
            raise RuntimeError(f"FIFO path is not a FIFO: {self.fifo_path}")

    def _command(self, read_fd: int) -> list[str]:
        command = [
            _dvbs2_python(),
            str(Path(self.args.dvbs2_bin)),
            "--source", "fd",
            "--in-fd", str(read_fd),
            "--sink", "udp",
            "--out-udp", f"{self.args.udp_host}:{self.args.udp_port}",
            "--sym-rate", str(int(self.args.sym_rate)),
            "--samp-rate", str(int(self.args.sample_rate)),
            "--freq", str(int(self.args.center_freq - self.args.offset)),
            "--modcod", "QPSK1/2",
            "--rolloff", "0.35",
            "--pilots", "on",
        ]
        if self.args.dvbs2_args:
            command.extend(shlex.split(self.args.dvbs2_args))
        return command

    def start(self) -> None:
        self._ensure_fifo()
        read_fd = os.open(self.fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            self.write_fd = os.open(
                self.fifo_path, os.O_WRONLY | os.O_NONBLOCK
            )
            os.set_blocking(read_fd, True)
            # Increase pipe buffer to 1 MB so a chunk fits without blocking
            # while rx.py finishes initializing its GNU Radio flow graph.
            try:
                fcntl.fcntl(self.write_fd, fcntl.F_SETPIPE_SZ, 1024 * 1024)
            except (AttributeError, OSError):
                pass  # macOS 10.6 and older, or kernel limit
            command = self._command(read_fd)
            LOG.info("Starting DVB-S2 receiver: %s", shlex.join(command))
            self.process = subprocess.Popen(command, pass_fds=(read_fd,))
        except Exception:
            if self.write_fd is not None:
                os.close(self.write_fd)
                self.write_fd = None
            raise
        finally:
            os.close(read_fd)

    def _stop_process(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process = None

    def _restart(self, reason: str) -> None:
        if self.restart_count >= MAX_DVBS2_RESTARTS:
            raise RuntimeError(
                f"DVB-S2 receiver failed after {MAX_DVBS2_RESTARTS} restarts"
            )
        self.restart_count += 1
        LOG.warning(
            "Restarting DVB-S2 receiver (%d/%d): %s",
            self.restart_count,
            MAX_DVBS2_RESTARTS,
            reason,
        )
        if self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None
        self._stop_process()
        try:
            self.fifo_path.unlink()
        except FileNotFoundError:
            pass
        self.start()

    def write(self, samples: np.ndarray) -> None:
        if (
            self.process is None
            or self.process.poll() is not None
            or self.write_fd is None
        ):
            self._restart("subprocess exited")
            return

        pending = memoryview(
            np.ascontiguousarray(samples, dtype=np.complex64)
        ).cast("B")
        deadline = time.monotonic() + max(
            2.0, 2.0 * len(samples) / self.args.sample_rate
        )
        while pending:
            try:
                written = os.write(self.write_fd, pending)
                pending = pending[written:]
            except BlockingIOError:
                if self.process.poll() is not None:
                    self._restart("subprocess exited while FIFO was full")
                    return
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    select.select([], [self.write_fd], [], min(0.01, remaining))
                    continue
                self.errors.warning(
                    "fifo-full",
                    "DVB-S2 FIFO full; dropped %d sample bytes",
                    len(pending),
                )
                return
            except BrokenPipeError:
                self._restart("FIFO reader closed")
                return
            except OSError as exc:
                if exc.errno in (errno.EPIPE, errno.EBADF):
                    self._restart(os.strerror(exc.errno))
                    return
                raise

    def close(self) -> None:
        if self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None
        self._stop_process()
        try:
            self.fifo_path.unlink()
        except FileNotFoundError:
            pass


class CompositeReceiver:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.errors = RateLimitedLogger()
        self.dvbs2 = Dvbs2Pipeline(args, self.errors)
        # Composite telemetry is explicitly burst-mode. Requiring an energy
        # burst prevents a continuous DVB-S2 plateau from entering the much
        # more expensive carrier/timing/frame search.
        self.decoder = PacketDecoder(bursts_only=True)
        self._overlap_samples = np.empty(0, dtype=np.complex64)
        self._seen_seqs: set[int] = set()
        self._decode_queue: Queue[tuple[int, np.ndarray] | None] = Queue(
            maxsize=8
        )
        self._decode_worker: Thread | None = None
        self._decode_chunks: list[np.ndarray] = []
        self._decode_sample_count = 0
        self._decode_sequence = 0
        self._post_queue: Queue[dict | None] = Queue(maxsize=256)
        self._post_worker: Thread | None = None
        self.hackrf_proc: subprocess.Popen | None = None
        self.video_bridge: subprocess.Popen | None = None
        self._video_bridge_worker: Thread | None = None
        self.stop_requested = False
        self.mixer_phase = 0.0
        self._mixer_oscillators: dict[int, np.ndarray] = {}
        self.decimation = int(round(args.sample_rate / BPSK_SAMPLE_RATE))
        self.decimation_phase = 0
        if not args.no_bpsk:
            self.channel_taps = self._channel_filter_taps()
            filter_memory = len(self.channel_taps) - 1
            self.bpsk_filter_state = np.zeros(
                filter_memory, dtype=np.complex64
            )
            self._channel_filter_fft: dict[int, np.ndarray] = {}

    def request_stop(self, _signum=None, _frame=None) -> None:
        self.stop_requested = True

    def _post_worker_loop(self) -> None:
        session = requests.Session()
        try:
            while not self.stop_requested:
                try:
                    packet = self._post_queue.get(timeout=0.5)
                except Empty:
                    continue
                if packet is None:
                    break
                try:
                    response = session.post(
                        self.args.dashboard,
                        json={"data": packet},
                        timeout=2,
                    )
                    response.raise_for_status()
                except requests.RequestException as exc:
                    self.errors.warning(
                        "dashboard-post",
                        "Dashboard POST failed: %s",
                        exc,
                    )
        finally:
            session.close()

    def _decode_worker_loop(self) -> None:
        last_sequence: int | None = None
        while not self.stop_requested:
            try:
                item = self._decode_queue.get(timeout=0.5)
            except Empty:
                continue
            if item is None:
                break

            sequence, samples = item
            if last_sequence is not None and sequence != last_sequence + 1:
                self._overlap_samples = np.empty(0, dtype=np.complex64)
            if len(self._overlap_samples) > 0:
                samples = np.concatenate([self._overlap_samples, samples])
            self._post_frames(samples)
            last_sequence = sequence

    def _queue_bpsk_samples(self, samples: np.ndarray) -> None:
        self._decode_chunks.append(samples)
        self._decode_sample_count += len(samples)
        if self._decode_sample_count < BPSK_DECODE_SAMPLES:
            return

        combined = np.concatenate(self._decode_chunks)
        batch = np.asarray(
            combined[:BPSK_DECODE_SAMPLES], dtype=np.complex64
        )
        remainder = combined[BPSK_DECODE_SAMPLES:]
        self._decode_chunks = [remainder] if len(remainder) else []
        self._decode_sample_count = len(remainder)

        sequence = self._decode_sequence
        self._decode_sequence += 1
        try:
            self._decode_queue.put_nowait((sequence, batch))
        except Full:
            self.errors.warning(
                "decoder-queue-full",
                "BPSK decoder falling behind; dropped %.3f seconds of samples",
                len(batch) / BPSK_SAMPLE_RATE,
            )

    def _open_hackrf_transfer(self) -> None:
        lna_db = min(int(self.args.lna), 40)
        vga_db = min(int(self.args.vga), 62)
        amp_flag = "1" if self.args.amp else "0"
        srate = int(round(self.args.sample_rate))
        freq = int(round(self.args.center_freq))
        env = None
        if self.args.serial:
            env = {**{k: v for k, v in (getattr(os, "environ", {}) or {}).items()},
                   "HACKRF_SERIAL": self.args.serial}
        self.hackrf_proc = subprocess.Popen(
            [
                "hackrf_transfer",
                "-r", "/dev/stdout",
                "-f", str(freq),
                "-s", str(srate),
                "-l", str(lna_db),
                "-g", str(vga_db),
                "-a", amp_flag,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        LOG.info(
            "HackRF %.3f MHz, %.3f MS/s (hackrf_transfer), LNA=%d, VGA=%d, AMP=%s, mode=%s",
            self.args.center_freq / 1e6,
            self.args.sample_rate / 1e6,
            lna_db, vga_db, self.args.amp,
            "DVB-S2 only" if self.args.no_bpsk else "DVB-S2+BPSK",
        )

    def _kill_stale_video_bridges(self) -> None:
        try:
            result = subprocess.run(
                [
                    "pgrep",
                    "-f",
                    f"udp://127.0.0.1:{self.args.udp_port}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for pid_text in result.stdout.strip().splitlines():
                if pid_text and int(pid_text) != os.getpid():
                    os.kill(int(pid_text), signal.SIGKILL)
                    LOG.info("Killed stale video bridge pid %s", pid_text)
        except Exception as exc:
            self.errors.warning(
                "video-bridge-stale",
                "Failed to kill stale video bridge: %s",
                exc,
            )

    def _spawn_video_bridge(self) -> subprocess.Popen | None:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            f"udp://127.0.0.1:{self.args.udp_port}",
            "-c:v",
            "mjpeg",
            "-q:v",
            "5",
            "-f",
            "mpjpeg",
            "-listen",
            "1",
            f"http://0.0.0.0:{VIDEO_PORT}/video",
        ]
        for _attempt in range(2):
            if self.stop_requested:
                return None
            bridge = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if _wait_listener(VIDEO_PORT, timeout=14.0):
                return bridge
            try:
                bridge.kill()
            except ProcessLookupError:
                pass
        return None

    def _video_bridge_supervisor(self) -> None:
        self._kill_stale_video_bridges()
        while not self.stop_requested:
            if (
                self.video_bridge is None
                or self.video_bridge.poll() is not None
            ):
                if self.stop_requested:
                    break
                bridge = self._spawn_video_bridge()
                if self.stop_requested:
                    if bridge is not None and bridge.poll() is None:
                        bridge.terminate()
                        try:
                            bridge.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            bridge.kill()
                            bridge.wait(timeout=2)
                    break
                self.video_bridge = bridge
            time.sleep(5)

    def _channel_filter_taps(self) -> np.ndarray:
        indexes = np.arange(CHANNEL_FILTER_TAPS) - (
            CHANNEL_FILTER_TAPS - 1
        ) / 2
        normalized_cutoff = (
            2.0 * BPSK_CHANNEL_CUTOFF_HZ / self.args.sample_rate
        )
        taps = (
            normalized_cutoff
            * np.sinc(normalized_cutoff * indexes)
            * np.hamming(CHANNEL_FILTER_TAPS)
        )
        return np.asarray(taps / np.sum(taps), dtype=np.float32)

    def _filter_and_decimate(
        self,
        samples: np.ndarray,
        start: int,
        state_name: str,
    ) -> np.ndarray:
        state = getattr(self, state_name)
        extended = np.concatenate((state, samples))
        tap_count = len(self.channel_taps)
        convolution_count = len(extended) + tap_count - 1
        fft_size = _next_fast_fft_size(convolution_count)
        tap_fft = self._channel_filter_fft.get(fft_size)
        if tap_fft is None:
            tap_fft = np.fft.fft(self.channel_taps, fft_size)
            self._channel_filter_fft[fft_size] = tap_fft
        convolution = np.fft.ifft(
            np.fft.fft(extended, fft_size) * tap_fft
        )
        # The valid convolution has one output for each new input sample and
        # is identical to a causal streaming FIR over ``state + samples``.
        valid = convolution[
            tap_count - 1 : tap_count - 1 + len(samples)
        ]
        filtered = valid[start::self.decimation]
        setattr(
            self,
            state_name,
            np.asarray(
                extended[-(tap_count - 1) :],
                dtype=np.complex64,
            ).copy(),
        )
        return np.asarray(filtered, dtype=np.complex64)

    def _split(self, samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        count = len(samples)
        step = 2.0 * np.pi * self.args.offset / self.args.sample_rate
        base_oscillator = self._mixer_oscillators.get(count)
        if base_oscillator is None:
            base_oscillator = np.exp(
                1j * step * np.arange(count)
            ).astype(np.complex64)
            base_oscillator.setflags(write=False)
            self._mixer_oscillators[count] = base_oscillator
        phase_rotation = np.complex64(np.exp(1j * self.mixer_phase))
        oscillator = base_oscillator * phase_rotation
        self.mixer_phase = (self.mixer_phase + step * count) % (2.0 * np.pi)
        start = (-self.decimation_phase) % self.decimation
        self.decimation_phase = (
            self.decimation_phase + count
        ) % self.decimation
        # Keep DVB-S2 at the full composite rate declared to rx.py. Only the
        # BPSK branch needs anti-alias filtering before its 2 MS/s decimation.
        dvbs2 = np.asarray(
            samples * oscillator.conjugate(), dtype=np.complex64
        )
        bpsk = self._filter_and_decimate(
            samples * oscillator,
            start,
            "bpsk_filter_state",
        )
        return dvbs2, bpsk

    def _post_frames(self, samples: np.ndarray) -> None:
        for payload, score, fo, phase, sync_idx, length in self.decoder.decode(
            samples
        ):
            del score, sync_idx, length
            try:
                frame = unpack_frame(payload)
            except (TypeError, ValueError) as exc:
                self.errors.warning(
                    "frame-unpack", "Invalid BPSK frame: %s", exc
                )
                continue
            if frame is None:
                self.errors.warning(
                    "frame-type",
                    "Unknown BPSK frame type (%d bytes)",
                    len(payload),
                )
                continue

            packet = frame.to_transport()
            sequence = packet.get("seq")
            if isinstance(sequence, int):
                if sequence in self._seen_seqs:
                    continue
                self._seen_seqs.add(sequence)
                if len(self._seen_seqs) > 1000:
                    self._seen_seqs = set(list(self._seen_seqs)[-500:])
            try:
                self._post_queue.put_nowait(packet)
                self.decoder.packets_found += 1
                LOG.info(
                    "Telemetry #%d seq=%s FO=%.1f Hz phase=%d",
                    self.decoder.packets_found,
                    packet.get("seq"),
                    fo,
                    phase,
                )
            except Full:
                self.errors.warning(
                    "queue-full",
                    "Post queue full; dropping packet",
                )
        self._overlap_samples = samples[-DECODER_OVERLAP_SAMPLES:].copy()

    def run(self) -> None:
        try:
            self._post_worker = Thread(
                target=self._post_worker_loop,
                daemon=True,
            )
            self._post_worker.start()
            if not self.args.no_bpsk:
                self._decode_worker = Thread(
                    target=self._decode_worker_loop,
                    daemon=True,
                )
                self._decode_worker.start()
            if not self.args.no_dvbs2:
                self.dvbs2.start()
                self._video_bridge_worker = Thread(
                    target=self._video_bridge_supervisor,
                    daemon=True,
                )
                self._video_bridge_worker.start()
            self._open_hackrf_transfer()
            chunk_bytes = CHUNK_SAMPLES * 2  # 2 bytes per SC8 sample (I+Q)
            while not self.stop_requested:
                raw = self.hackrf_proc.stdout.read(chunk_bytes)
                if not raw or len(raw) < chunk_bytes:
                    if not self.stop_requested:
                        self.errors.warning(
                            "pipe-read", "hackrf_transfer pipe ended (%d/%d bytes)",
                            len(raw), chunk_bytes,
                        )
                    break
                # Convert SC8 (int8 I/Q interleaved) → complex64
                iq8 = np.frombuffer(raw, dtype=np.int8).astype(np.float32).reshape(-1, 2)
                samples = np.asarray(
                    (iq8[:, 0] + 1j * iq8[:, 1]) / 128.0,
                    dtype=np.complex64,
                )
                if self.args.no_bpsk:
                    dvbs2 = samples
                else:
                    dvbs2, bpsk = self._split(samples)
                if not self.args.no_dvbs2:
                    self.dvbs2.write(dvbs2)
                if not self.args.no_bpsk:
                    self._queue_bpsk_samples(bpsk)
        finally:
            self.stop_requested = True
            try:
                self._decode_queue.put_nowait(None)
            except Full:
                pass
            try:
                self._post_queue.put_nowait(None)
            except Full:
                pass
            if self._decode_worker is not None:
                self._decode_worker.join(timeout=3)
            if self._post_worker is not None:
                self._post_worker.join(timeout=3)
            if self.hackrf_proc is not None and self.hackrf_proc.poll() is None:
                self.hackrf_proc.terminate()
                try:
                    self.hackrf_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.hackrf_proc.kill()
                    self.hackrf_proc.wait(timeout=2)
            if (
                self.video_bridge is not None
                and self.video_bridge.poll() is None
                and not self.args.no_dvbs2
            ):
                self.video_bridge.terminate()
                try:
                    self.video_bridge.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.video_bridge.kill()
                    self.video_bridge.wait(timeout=2)
            self.dvbs2.close()
            LOG.info("Composite receiver stopped")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[CombinedRX] %(levelname)s: %(message)s",
    )
    args = parse_args(argv)
    if np.isclose(
        args.offset,
        args.sample_rate / 2.0,
        rtol=0.0,
        atol=1e-9,
    ):
        LOG.warning(
            "Both offsets lie on the Nyquist edge at %.3f MS/s; use 6 MS/s "
            "with the current 2 MS/s channel decimation to avoid aliasing",
            args.sample_rate / 1e6,
        )
    receiver = CompositeReceiver(args)
    signal.signal(signal.SIGINT, receiver.request_stop)
    signal.signal(signal.SIGTERM, receiver.request_stop)
    try:
        receiver.run()
    except KeyboardInterrupt:
        receiver.request_stop()
    except Exception:
        LOG.exception("Composite receiver failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
