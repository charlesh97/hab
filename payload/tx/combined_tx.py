#!/usr/bin/env python3
"""Transmit DVB-S2 video and BPSK position telemetry with one HackRF."""

from __future__ import annotations

import argparse
import errno
import functools
import logging
import math
import os
import select
import shlex
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import serial


_HAB_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_HAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_HAB_ROOT))

from payload.telemetry.nmea import GPSState, NMEAParser  # noqa: E402
from protocol.telemetry import FrameType, PositionFrame  # noqa: E402


LOG = logging.getLogger("combined_tx")

BPSK_SYMBOL_RATE = 100_000
BPSK_REFERENCE_SPS = 20
BPSK_REFERENCE_SAMPLE_RATE = BPSK_SYMBOL_RATE * BPSK_REFERENCE_SPS
RRC_ALPHA = 0.35
RRC_SPAN_SYMBOLS = 11
SYNC_WORD = 0xE38FC0FC
PREAMBLE_BITS = 256
PACKET_PERIOD_SECONDS = 1.0
PACKET_LEAD_SILENCE_SECONDS = 0.05
CHUNK_SECONDS = 0.04
GPS_RECONNECT_SECONDS = 5.0
PROCESS_RESTART_SECONDS = 1.0
MAX_DVBS2_RESTARTS = 3
MAX_FFMPEG_RESTARTS = 3
ERROR_LOG_INTERVAL = 10.0
DEFAULT_SYMBOL_RATE = 2_000_000.0
TIMESTAMP_OVERLAY_FILTER = (
    r"drawtext=text='%{localtime\:%Y-%m-%d %H\\\:%M\\\:%S}':"
    "fontcolor=white:fontsize=32:x=20:y=20:"
    "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
)

_FEC_FRAME = 64800.0
_MOD = 2.0
_NUM, _DEN = 1.0, 2.0
_BCH = 12.0
_PILOTS = 36.0

# Fixed headroom avoids changing either waveform's amplitude from chunk to
# chunk. The BPSK waveform itself peaks at 0.7, matching the former packet TX.
DVBS2_LEVEL = np.float32(0.65)
BPSK_LEVEL = np.float32(0.45)


@functools.lru_cache(maxsize=8)
def _frequency_oscillators(
    count: int, offset: float, sample_rate: float
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return immutable up/down oscillators for a fixed chunk shape."""
    phase_step = 2.0 * np.pi * offset / sample_rate
    angles = phase_step * np.arange(count, dtype=np.float64)
    up = np.exp(1j * angles).astype(np.complex64)
    down = up.conjugate()
    up.setflags(write=False)
    down.setflags(write=False)
    return up, down, phase_step


def compute_tsrate(sym_rate: float) -> int:
    """Return the QPSK 1/2 normal-frame TS rate with pilots enabled."""
    denominator = (
        _FEC_FRAME / _MOD
        + 90
        + math.ceil(_FEC_FRAME / _MOD / 90 / 16 - 1) * _PILOTS
    )
    numerator = _FEC_FRAME * (_NUM / _DEN) - 16 * _BCH - 80
    return int(round(sym_rate / denominator * numerator))


class RateLimitedLogger:
    """Rate-limit repeated runtime errors by a stable key."""

    def __init__(self, interval: float = ERROR_LOG_INTERVAL) -> None:
        self.interval = interval
        self._last_log: dict[str, float] = {}

    def warning(self, key: str, message: str, *args: object) -> None:
        now = time.monotonic()
        if now - self._last_log.get(key, -self.interval) >= self.interval:
            self._last_log[key] = now
            LOG.warning(message, *args)

    def error(self, key: str, message: str, *args: object) -> None:
        now = time.monotonic()
        if now - self._last_log.get(key, -self.interval) >= self.interval:
            self._last_log[key] = now
            LOG.error(message, *args)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Composite DVB-S2 video and BPSK telemetry transmitter"
    )
    parser.add_argument("--center-freq", type=float, default=914e6)
    parser.add_argument(
        "--no-bpsk", action="store_true",
        help="Disable BPSK telemetry. Transmit DVB-S2 only at center frequency.",
    )
    parser.add_argument(
        "--offset", type=float, default=700e3,
        help="Frequency offset between DVB-S2 and BPSK subcarriers (Hz). "
        "MUST match the RX --offset value. Ignored when --no-bpsk is set.",
    )
    parser.add_argument("--sample-rate", type=float, default=8e6)
    parser.add_argument("--vga", type=float, default=30)
    parser.add_argument("--amp", action="store_true")
    parser.add_argument("--serial")
    parser.add_argument("--gps-port", default="/dev/ttyS0")
    parser.add_argument("--gps-baud", type=int, default=9600)
    parser.add_argument("--video-udp", type=int, default=5000)
    parser.add_argument(
        "--video-size",
        default="1280x720",
        help="Camera resolution WxH (default: 1280x720)",
    )
    parser.add_argument(
        "--video-source",
        choices=["camera", "testsrc"],
        default="camera",
        help="Video input: 'camera' uses /dev/video0 (default), 'testsrc' uses ffmpeg's synthetic test pattern",
    )
    parser.add_argument("--no-video", action="store_true", help="Disable video/DVB-S2, BPSK telemetry only")
    parser.add_argument("--sym-rate", type=float, default=DEFAULT_SYMBOL_RATE)
    parser.add_argument(
        "--tsrate",
        type=int,
        help="Transport stream rate (default: calculated from --sym-rate)",
    )
    parser.add_argument("--modcod", default="QPSK1/2")
    parser.add_argument(
        "--rolloff",
        type=float,
        choices=(0.35, 0.25, 0.20),
        default=0.35,
    )
    pilots = parser.add_mutually_exclusive_group()
    pilots.add_argument("--pilots", dest="pilots", action="store_true")
    pilots.add_argument("--no-pilots", dest="pilots", action="store_false")
    parser.set_defaults(pilots=True)
    timestamp_overlay = parser.add_mutually_exclusive_group()
    timestamp_overlay.add_argument(
        "--timestamp-overlay", dest="timestamp_overlay", action="store_true"
    )
    timestamp_overlay.add_argument(
        "--no-timestamp-overlay", dest="timestamp_overlay", action="store_false"
    )
    parser.set_defaults(timestamp_overlay=True)
    parser.add_argument(
        "--rrc-delay",
        type=int,
        default=2,
        help="RRC filter half-span in symbol periods (default: 2). "
        "Lower values reduce CPU load at the cost of spectral regrowth.",
    )
    parser.add_argument(
        "--use-gr",
        action="store_true",
        help="Use GNU Radio C++ DVB-S2 blocks instead of Python/numpy encoder. "
        "Requires gnuradio 3.10+ with gr-dtv installed on the target.",
    )
    parser.add_argument(
        "--dvbs2-bin",
        default=str(_HAB_ROOT / "dev" / "dvbs2" / "dvbs2" / "tx.py"),
        help="Path to the existing DVB-S2 tx.py",
    )
    args = parser.parse_args(argv)

    if args.center_freq <= 0:
        parser.error("--center-freq must be positive")
    if args.offset < 0:
        parser.error("--offset must not be negative")
    if args.sample_rate <= 0:
        parser.error("--sample-rate must be positive")
    if args.offset > args.sample_rate / 2:
        parser.error("--offset must not exceed the Nyquist frequency")
    if not 0 <= args.vga <= 47:
        parser.error("--vga must be between 0 and 47")
    if args.sym_rate <= 0:
        parser.error("--sym-rate must be positive")
    if args.tsrate is not None and args.tsrate <= 0:
        parser.error("--tsrate must be positive")
    if not 1 <= args.video_udp <= 65535:
        parser.error("--video-udp must be between 1 and 65535")
    if args.gps_baud <= 0:
        parser.error("--gps-baud must be positive")

    bpsk_sps = args.sample_rate / BPSK_SYMBOL_RATE
    if bpsk_sps < 2 or not np.isclose(
        bpsk_sps, round(bpsk_sps), rtol=0.0, atol=1e-9
    ):
        parser.error(
            "--sample-rate must be an integer multiple of 100000 for BPSK"
        )
    if args.sample_rate / args.sym_rate < 2:
        parser.error("--sample-rate must provide at least 2 DVB-S2 samples/symbol")
    if args.no_bpsk:
        args.offset = 0.0
    if args.tsrate is None:
        args.tsrate = compute_tsrate(args.sym_rate)
    if args.use_gr and not args.no_bpsk:
        parser.error("--use-gr currently requires --no-bpsk (BPSK mixing not yet ported to GNU Radio)")
    return args


def crc16(data: bytes) -> int:
    """CRC-16/XMODEM (polynomial 0x1021, initial value zero)."""
    checksum = 0
    for byte in data:
        checksum ^= byte << 8
        for _ in range(8):
            checksum = (
                (checksum << 1) ^ 0x1021
                if checksum & 0x8000
                else checksum << 1
            ) & 0xFFFF
    return checksum


def _bytes_to_bits(data: bytes) -> list[int]:
    return [
        (byte >> shift) & 1
        for byte in data
        for shift in range(7, -1, -1)
    ]


def packet_bits(payload: bytes) -> list[int]:
    """Build the packet bit stream consumed by the ground BPSK decoder."""
    preamble = [1, 0] * (PREAMBLE_BITS // 2)
    sync = [(SYNC_WORD >> shift) & 1 for shift in range(31, -1, -1)]
    return (
        preamble
        + sync
        + _bytes_to_bits(struct.pack(">H", len(payload)))
        + _bytes_to_bits(payload)
        + _bytes_to_bits(struct.pack(">H", crc16(payload)))
    )


def root_raised_cosine_taps(
    samples_per_symbol: int,
    alpha: float = RRC_ALPHA,
    span_symbols: int = RRC_SPAN_SYMBOLS,
) -> np.ndarray:
    """Return pure-numpy RRC taps for unit symbol duration."""
    tap_count = samples_per_symbol * span_symbols
    times = (
        np.arange(tap_count, dtype=np.float64) - (tap_count - 1) / 2.0
    ) / samples_per_symbol
    taps = np.empty(tap_count, dtype=np.float64)

    zero = np.isclose(times, 0.0, rtol=0.0, atol=1e-12)
    singular = np.isclose(
        np.abs(times),
        1.0 / (4.0 * alpha),
        rtol=0.0,
        atol=1e-12,
    )
    regular = ~(zero | singular)

    taps[zero] = 1.0 + alpha * (4.0 / np.pi - 1.0)
    angle = np.pi / (4.0 * alpha)
    taps[singular] = alpha / np.sqrt(2.0) * (
        (1.0 + 2.0 / np.pi) * np.sin(angle)
        + (1.0 - 2.0 / np.pi) * np.cos(angle)
    )
    t = times[regular]
    taps[regular] = (
        np.sin(np.pi * t * (1.0 - alpha))
        + 4.0 * alpha * t * np.cos(np.pi * t * (1.0 + alpha))
    ) / (np.pi * t * (1.0 - (4.0 * alpha * t) ** 2))
    return taps


def _fft_convolve_same(signal: np.ndarray, taps: np.ndarray) -> np.ndarray:
    """Match ``np.convolve(..., mode="same")`` without quadratic FIR work."""
    full_count = len(signal) + len(taps) - 1
    fft_count = 1 << (full_count - 1).bit_length()
    full = np.fft.irfft(
        np.fft.rfft(signal, fft_count) * np.fft.rfft(taps, fft_count),
        fft_count,
    )[:full_count]
    same_count = max(len(signal), len(taps))
    same_start = (min(len(signal), len(taps)) - 1) // 2
    return full[same_start : same_start + same_count]


def bpsk_modulate(
    bits: list[int],
    sample_rate: float = BPSK_REFERENCE_SAMPLE_RATE,
) -> np.ndarray:
    """Map bits to an RRC-shaped BPSK complex64 waveform."""
    samples_per_symbol = int(round(sample_rate / BPSK_SYMBOL_RATE))
    mapped = 1.0 - 2.0 * np.asarray(bits, dtype=np.float64)
    upsampled = np.zeros(len(mapped) * samples_per_symbol, dtype=np.float64)
    upsampled[::samples_per_symbol] = mapped
    waveform = _fft_convolve_same(
        upsampled,
        root_raised_cosine_taps(samples_per_symbol),
    )
    peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
    if peak > 0.0:
        waveform *= 0.7 / peak
    return waveform.astype(np.complex64)


def make_packet_waveform(
    payload: bytes,
    sample_rate: float = BPSK_REFERENCE_SAMPLE_RATE,
) -> np.ndarray:
    return bpsk_modulate(packet_bits(payload), sample_rate)


def build_bpsk_cycle(payload: bytes, sample_rate: float) -> np.ndarray:
    """Return one second containing one packet and otherwise zero samples."""
    sample_count = int(round(sample_rate * PACKET_PERIOD_SECONDS))
    packet = make_packet_waveform(payload, sample_rate)
    packet_start = int(round(sample_rate * PACKET_LEAD_SILENCE_SECONDS))
    if packet_start + len(packet) > sample_count:
        raise ValueError("BPSK packet does not fit in its one-second cycle")
    cycle = np.zeros(sample_count, dtype=np.complex64)
    cycle[packet_start : packet_start + len(packet)] = packet
    return cycle


def frequency_interleave(
    dvbs2_iq: np.ndarray,
    bpsk_iq: np.ndarray,
    offset: float,
    sample_rate: float,
    phase: float = 0.0,
) -> tuple[np.ndarray, float]:
    """Shift DVB-S2 up, BPSK down, and sum with continuous mixer phase."""
    if len(dvbs2_iq) != len(bpsk_iq):
        raise ValueError("DVB-S2 and BPSK chunks must have equal lengths")
    count = len(dvbs2_iq)
    up, down, phase_step = _frequency_oscillators(count, offset, sample_rate)
    rotation = np.complex64(complex(math.cos(phase), math.sin(phase)))
    composite = (
        np.complex64(DVBS2_LEVEL * rotation)
        * np.asarray(dvbs2_iq, dtype=np.complex64)
        * up
        + np.complex64(BPSK_LEVEL * rotation.conjugate())
        * np.asarray(bpsk_iq, dtype=np.complex64)
        * down
    )
    next_phase = (phase + phase_step * count) % (2.0 * np.pi)
    return np.asarray(composite, dtype=np.complex64), next_phase


class GPSConnection:
    """Non-blocking GPS reader with five-second serial reconnection."""

    def __init__(
        self,
        port: str,
        baud: int,
        errors: RateLimitedLogger,
    ) -> None:
        self.port = port
        self.baud = baud
        self.errors = errors
        self.state = GPSState()
        self.parser: NMEAParser | None = None
        self.next_connect = 0.0

    def _connect(self, now: float) -> None:
        try:
            self.parser = NMEAParser(self.port, self.baud, timeout=0)
            LOG.info("GPS opened on %s at %d baud", self.port, self.baud)
        except (OSError, serial.SerialException) as exc:
            self.parser = None
            self.next_connect = now + GPS_RECONNECT_SECONDS
            self.errors.warning(
                "gps-open",
                "GPS unavailable on %s; retrying in %.0fs: %s",
                self.port,
                GPS_RECONNECT_SECONDS,
                exc,
            )

    def poll(self) -> GPSState:
        now = time.monotonic()
        if self.parser is None:
            if now >= self.next_connect:
                self._connect(now)
            return self.state
        try:
            for _ in range(32):
                sentence = self.parser.read_sentence()
                if sentence is None:
                    break
                self.state.update(sentence)
        except (OSError, serial.SerialException) as exc:
            self.errors.warning(
                "gps-read",
                "GPS read failed; reconnecting in %.0fs: %s",
                GPS_RECONNECT_SECONDS,
                exc,
            )
            self.close()
            self.next_connect = now + GPS_RECONNECT_SECONDS
        return self.state

    def close(self) -> None:
        if self.parser is not None:
            try:
                self.parser.close()
            except (OSError, serial.SerialException):
                pass
            self.parser = None


class Dvbs2Pipeline:
    """Run ffmpeg piped directly into tx.py, read IQ from tx.py stdout."""

    def __init__(
        self,
        args: argparse.Namespace,
        errors: RateLimitedLogger,
    ) -> None:
        self.args = args
        self.errors = errors
        self.ffmpeg_proc: subprocess.Popen | None = None
        self.tx_proc: subprocess.Popen | None = None
        self.restart_count = 0
        self.next_restart = 0.0
        self.failed = False

    def _tx_command(self) -> list[str]:
        tsrate = getattr(self.args, "tsrate", None)
        if tsrate is None:
            tsrate = compute_tsrate(self.args.sym_rate)
        cmd = [
            sys.executable,
            str(Path(self.args.dvbs2_bin)),
            "--source", "fd", "--in-fd", "0",
            "--sink", "fd", "--out-fd", "1",
            "--out-iq-format", "fc32",
            "--samp-rate", str(int(round(self.args.sample_rate))),
            "--sym-rate", str(self.args.sym_rate),
            "--tsrate", str(tsrate),
            "--freq", str(int(round(self.args.center_freq + self.args.offset))),
            "--modcod", self.args.modcod,
            "--rolloff", str(self.args.rolloff),
            "--rrc-delay", str(self.args.rrc_delay),
        ]
        if self.args.pilots:
            cmd.append("--pilots")
        return cmd

    def _ffmpeg_command(self) -> list[str]:
        video_bitrate = int(int(self.args.tsrate * 0.78) // 1000 * 1000)
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        ]
        if self.args.video_source == "testsrc":
            command.extend([
                "-f", "lavfi", "-i",
                f"testsrc=size={self.args.video_size}:rate=15",
            ])
        else:
            command.extend([
                "-f", "v4l2", "-framerate", "15",
                "-video_size", self.args.video_size,
                "-i", "/dev/video0",
            ])
        command.append("-an")
        if self.args.timestamp_overlay:
            command.extend(["-vf", TIMESTAMP_OVERLAY_FILTER])
        command.extend([
            "-c:v", "libx264", "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-b:v", str(video_bitrate), "-maxrate", str(video_bitrate),
            "-bufsize", str(video_bitrate),
            "-g", "15", "-keyint_min", "15",
            "-f", "mpegts", "-muxrate", str(self.args.tsrate),
            "-",
        ])
        return command

    def start(self) -> None:
        # Start tx.py first (it opens and waits for input on stdin)
        tx_cmd = self._tx_command()
        LOG.info("Starting DVB-S2 encoder: %s", shlex.join(tx_cmd))
        # We'll feed data via ffmpeg → tx.py stdin pipe
        self.tx_proc = subprocess.Popen(
            tx_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True, bufsize=0,
        )

        # Start ffmpeg, pipe its stdout into tx.py's stdin
        ff_cmd = self._ffmpeg_command()
        LOG.info("Starting ffmpeg: %s", shlex.join(ff_cmd))
        self.ffmpeg_proc = subprocess.Popen(
            ff_cmd, stdout=self.tx_proc.stdin, stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        self.tx_proc.stdin.close()  # tx.py reads from pipe, not us

    def ensure_running(self) -> None:
        if self.failed:
            return
        # Check if either process has died
        tx_alive = self.tx_proc is not None and self.tx_proc.poll() is None
        ff_alive = self.ffmpeg_proc is not None and self.ffmpeg_proc.poll() is None
        if tx_alive and ff_alive:
            return
        now = time.monotonic()
        if now < self.next_restart:
            return
        if self.restart_count >= MAX_DVBS2_RESTARTS:
            self.failed = True
            self.errors.error(
                "dvbs2-give-up",
                "DVB-S2 encoder failed after %d restarts; video disabled",
                MAX_DVBS2_RESTARTS,
            )
            self.close()
            return

        self.restart_count += 1
        LOG.warning(
            "Restarting DVB-S2 encoder (%d/%d)",
            self.restart_count,
            MAX_DVBS2_RESTARTS,
        )
        # Kill everything and restart from scratch
        self.close()
        try:
            self.start()
        except (OSError, subprocess.SubprocessError) as exc:
            self.errors.warning(
                "dvbs2-restart", "DVB-S2 restart failed: %s", exc
            )
        self.next_restart = now + PROCESS_RESTART_SECONDS

    def read_samples(self, count: int) -> np.ndarray:
        byte_count = count * 8
        samples = np.empty(count, dtype=np.complex64)
        sample_bytes = memoryview(samples).cast("B")
        received = 0
        stdout = self.tx_proc.stdout if self.tx_proc is not None else None

        # Read a complete chunk directly into the numpy array. The unthrottled
        # GNU Radio process blocks on its stdout pipe while the HackRF is busy,
        # making writeStream the only real-time pacing governor.
        while received < byte_count and stdout is not None:
            try:
                amount = stdout.readinto(sample_bytes[received:])
            except (OSError, ValueError):
                break
            if not amount:
                break
            received += amount

        received_samples = received // 8
        if received_samples == count:
            return samples
        samples[received_samples:] = 0
        self.errors.warning(
            "dvbs2-underflow",
            "DVB-S2 IQ underflow; padded %d samples",
            count - received_samples,
        )
        return samples

    def close(self) -> None:
        # Kill ffmpeg first
        if self.ffmpeg_proc is not None and self.ffmpeg_proc.poll() is None:
            self.ffmpeg_proc.terminate()
            try:
                self.ffmpeg_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ffmpeg_proc.kill()
                self.ffmpeg_proc.wait(timeout=2)
            self.ffmpeg_proc = None
        # Then kill tx.py (it will notice stdin EOF from ffmpeg dying)
        if self.tx_proc is not None and self.tx_proc.poll() is None:
            self.tx_proc.terminate()
            try:
                self.tx_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.tx_proc.kill()
                self.tx_proc.wait(timeout=2)
            self.tx_proc = None


class FfmpegProcess:
    """Own the payload camera encoder and its bounded restart policy."""

    def __init__(
        self,
        udp_port: int,
        errors: RateLimitedLogger,
        video_size: str = "1280x720",
        tsrate: int = compute_tsrate(DEFAULT_SYMBOL_RATE),
        video_bitrate: int = 1_500_000,
        udp_host: str = "127.0.0.1",
        timestamp_overlay: bool = True,
    ) -> None:
        self.udp_port = udp_port
        self.udp_host = udp_host
        self.errors = errors
        self.video_size = video_size
        self.tsrate = tsrate
        self.video_bitrate = video_bitrate
        self.timestamp_overlay = timestamp_overlay
        self.process: subprocess.Popen | None = None
        self.restart_count = 0
        self.next_restart = 0.0
        self.failed = False

    def command(self) -> list[str]:
        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-f",
            "v4l2",
            "-framerate",
            "15",
            "-video_size",
            self.video_size,
            "-i",
            "/dev/video0",
            "-an",
        ]
        if self.timestamp_overlay:
            command.extend(["-vf", TIMESTAMP_OVERLAY_FILTER])
        command.extend([
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-b:v",
            str(self.video_bitrate),
            "-maxrate",
            str(self.video_bitrate),
            "-bufsize",
            str(self.video_bitrate),
            "-g",
            "15",
            "-keyint_min",
            "15",
            "-f",
            "mpegts",
            "-muxrate",
            str(self.tsrate),
            f"udp://{self.udp_host}:{self.udp_port}?pkt_size=1316",
        ])
        return command

    def _start(self) -> None:
        command = self.command()
        LOG.info("Starting ffmpeg: %s", shlex.join(command))
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def start(self) -> None:
        try:
            self._start()
        except OSError as exc:
            self.errors.warning("ffmpeg-start", "ffmpeg failed to start: %s", exc)
            self.next_restart = time.monotonic() + PROCESS_RESTART_SECONDS

    def ensure_running(self) -> None:
        if self.failed or (
            self.process is not None and self.process.poll() is None
        ):
            return
        now = time.monotonic()
        if now < self.next_restart:
            return
        if self.restart_count >= MAX_FFMPEG_RESTARTS:
            self.failed = True
            self.errors.error(
                "ffmpeg-give-up",
                "ffmpeg failed after %d restarts; camera video disabled",
                MAX_FFMPEG_RESTARTS,
            )
            return

        return_code = self.process.poll() if self.process is not None else None
        self.restart_count += 1
        LOG.warning(
            "Restarting ffmpeg (%d/%d, previous status %s)",
            self.restart_count,
            MAX_FFMPEG_RESTARTS,
            return_code,
        )
        try:
            self._start()
        except OSError as exc:
            self.errors.warning(
                "ffmpeg-restart", "ffmpeg restart failed: %s", exc
            )
        self.next_restart = now + PROCESS_RESTART_SECONDS

    def close(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)


class CompositeTransmitter:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.errors = RateLimitedLogger()
        self.gps = GPSConnection(args.gps_port, args.gps_baud, self.errors)
        self.dvbs2 = Dvbs2Pipeline(args, self.errors)
        remote_host = "127.0.0.1"
        video_bitrate = int(args.tsrate * 0.78)
        video_bitrate = (video_bitrate // 1000) * 1000
        self.ffmpeg = FfmpegProcess(
            args.video_udp,
            self.errors,
            video_size=args.video_size,
            tsrate=args.tsrate,
            video_bitrate=video_bitrate,
            udp_host=remote_host,
            timestamp_overlay=args.timestamp_overlay,
        )
        self.sdr = None
        self.stream = None
        self.soapy = None
        self.stop_requested = False
        self.mixer_phase = 0.0
        self.sequence = 0
        self.bpsk_cycle = np.empty(0, dtype=np.complex64)
        self.bpsk_position = 0

    def request_stop(self, _signum: int | None = None, _frame: object = None) -> None:
        self.stop_requested = True

    def _open_sdr(self) -> None:
        try:
            import SoapySDR
        except ImportError as exc:
            raise RuntimeError("Python SoapySDR bindings are not installed") from exc

        device_str = "driver=hackrf"
        if self.args.serial:
            device_str += f",serial={self.args.serial}"
        self.soapy = SoapySDR
        self.sdr = SoapySDR.Device(device_str)
        direction = SoapySDR.SOAPY_SDR_TX
        self.sdr.setSampleRate(direction, 0, self.args.sample_rate)
        self.sdr.setBandwidth(direction, 0, 0)
        self.sdr.setFrequency(direction, 0, self.args.center_freq)
        self.sdr.setGain(direction, 0, "VGA", self.args.vga)
        self.sdr.setGain(direction, 0, "AMP", float(self.args.amp))
        self.stream = self.sdr.setupStream(
            direction, SoapySDR.SOAPY_SDR_CF32
        )
        self.sdr.activateStream(self.stream)
        LOG.info(
            "HackRF TX %.3f MHz, %.3f MS/s, VGA=%.0f, AMP=%s, mode=%s",
            self.args.center_freq / 1e6,
            self.args.sample_rate / 1e6,
            self.args.vga,
            self.args.amp,
            "DVB-S2 only" if self.args.no_bpsk else "DVB-S2+BPSK",
        )

    def _new_bpsk_cycle(self) -> np.ndarray:
        state = self.gps.state
        frame = PositionFrame(
            type=FrameType.POSITION,
            seq=self.sequence,
            **state.position_fields(),
        )
        payload = frame.pack()
        self.sequence = (self.sequence + 1) & 0xFFFF
        LOG.info(
            "Position seq=%d, %d bytes, %.6f,%.6f alt=%.1fm fix=%s sats=%d",
            frame.seq,
            len(payload),
            frame.lat,
            frame.lon,
            frame.alt_m,
            frame.fix_type,
            frame.sats,
        )
        return build_bpsk_cycle(payload, self.args.sample_rate)

    def _next_bpsk_samples(self, count: int) -> np.ndarray:
        output = np.zeros(count, dtype=np.complex64)
        output_position = 0
        while output_position < count:
            if self.bpsk_position >= len(self.bpsk_cycle):
                self.bpsk_cycle = self._new_bpsk_cycle()
                self.bpsk_position = 0
            copy_count = min(
                count - output_position,
                len(self.bpsk_cycle) - self.bpsk_position,
            )
            output[output_position : output_position + copy_count] = (
                self.bpsk_cycle[
                    self.bpsk_position : self.bpsk_position + copy_count
                ]
            )
            output_position += copy_count
            self.bpsk_position += copy_count
        return output

    def _write_samples(self, samples: np.ndarray) -> None:
        position = 0
        while position < len(samples) and not self.stop_requested:
            result = self.sdr.writeStream(
                self.stream,
                [samples[position:]],
                len(samples) - position,
                timeoutUs=500_000,
            )
            if result.ret > 0:
                position += result.ret
                continue
            if result.ret == getattr(self.soapy, "SOAPY_SDR_TIMEOUT", -1):
                self.errors.warning(
                    "hackrf-timeout", "HackRF TX timed out; continuing"
                )
            elif result.ret == getattr(self.soapy, "SOAPY_SDR_UNDERFLOW", -7):
                self.errors.warning(
                    "hackrf-underflow", "HackRF TX underflow; continuing"
                )
            else:
                self.errors.warning(
                    "hackrf-write",
                    "HackRF writeStream failed with status %d",
                    result.ret,
                )
            return

    def _run_gr_mode(self) -> None:
        """Run the GNU Radio DVB-S2 pipeline via the reference tx.py.

        Uses ``dev/dvbs2/dvbs2/tx.py --sink hackrf`` — the proven reference
        flow graph that correctly handles the PL framer's ×2 upsampling,
        RRC pulse shaping, and direct SoapySDR/HackRF output.  Replaces the
        entire composite loop when ``--use-gr`` is active.
        """
        tx_bin = str(
            _HAB_ROOT / "dev" / "dvbs2" / "dvbs2" / "tx.py"
        )
        LOG.info("Using reference DVB-S2 encoder: %s", tx_bin)

        tsrate = getattr(self.args, "tsrate", None)
        if tsrate is None:
            tsrate = compute_tsrate(self.args.sym_rate)

        tx_cmd = [
            sys.executable,
            tx_bin,
            "--source", "fd", "--in-fd", "0",
            "--sink", "hackrf",
            "--freq", str(int(round(self.args.center_freq))),
            "--samp-rate", str(int(round(self.args.sample_rate))),
            "--sym-rate", str(self.args.sym_rate),
            "--tsrate", str(tsrate),
            "--modcod", str(self.args.modcod),
            "--rolloff", str(self.args.rolloff),
            "--rrc-delay", str(self.args.rrc_delay),
            "--hackrf-vga", str(self.args.vga),
        ]
        if self.args.pilots:
            tx_cmd.append("--pilots")
        if self.args.amp:
            tx_cmd.append("--hackrf-amp")

        video_bitrate = int(tsrate * 0.78 // 1000 * 1000)
        ff_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            "-f", "v4l2", "-framerate", "15",
            "-video_size", self.args.video_size,
            "-i", "/dev/video0",
            "-an",
        ]
        if self.args.timestamp_overlay:
            ff_cmd.extend(["-vf", TIMESTAMP_OVERLAY_FILTER])
        ff_cmd.extend([
            "-c:v", "libx264", "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-b:v", str(video_bitrate), "-maxrate", str(video_bitrate),
            "-bufsize", str(video_bitrate),
            "-g", "15", "-keyint_min", "15",
            "-f", "mpegts", "-muxrate", str(tsrate),
            "-",
        ])

        LOG.info("Starting ffmpeg -> tx.py (hackrf sink)")

        tx_proc = subprocess.Popen(
            tx_cmd, stdin=subprocess.PIPE, close_fds=True,
        )
        ff_proc = subprocess.Popen(
            ff_cmd, stdout=tx_proc.stdin, stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        tx_proc.stdin.close()  # ffmpeg owns the pipe

        # Wait for ffmpeg to finish (or be killed)
        try:
            ff_proc.wait()
        except KeyboardInterrupt:
            pass

        # Shut down the encoder
        if tx_proc.poll() is None:
            tx_proc.terminate()
            try:
                tx_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tx_proc.kill()
                tx_proc.wait(timeout=2)

        LOG.info("Reference DVB-S2 pipeline stopped")

    def run(self) -> None:
        # GNU Radio mode: replaces the entire composite loop
        if self.args.use_gr and self.args.no_bpsk:
            self._run_gr_mode()
            return

        chunk_samples = max(
            4096, int(round(self.args.sample_rate * CHUNK_SECONDS))
        )
        if not self.args.no_bpsk and not self.args.no_video:
            _frequency_oscillators(
                chunk_samples, self.args.offset, self.args.sample_rate
            )
        try:
            self._open_sdr()
            if not self.args.no_video:
                self.dvbs2.start()
            while not self.stop_requested:
                if not self.args.no_bpsk:
                    self.gps.poll()
                if not self.args.no_video:
                    self.dvbs2.ensure_running()
                    dvbs2_iq = self.dvbs2.read_samples(chunk_samples)
                else:
                    dvbs2_iq = np.zeros(chunk_samples, dtype=np.complex64)

                if self.args.no_bpsk:
                    dvbs2_iq *= DVBS2_LEVEL
                    composite = dvbs2_iq
                else:
                    bpsk_iq = self._next_bpsk_samples(chunk_samples)
                    if not self.args.no_video:
                        composite, self.mixer_phase = frequency_interleave(
                            dvbs2_iq,
                            bpsk_iq,
                            self.args.offset,
                            self.args.sample_rate,
                            self.mixer_phase,
                        )
                    else:
                        composite = np.zeros(
                            chunk_samples, dtype=np.complex64
                        )
                        composite[: len(bpsk_iq)] = bpsk_iq
                self._write_samples(composite)
        finally:
            if self.sdr is not None and self.stream is not None:
                try:
                    self.sdr.deactivateStream(self.stream)
                finally:
                    self.sdr.closeStream(self.stream)
            if not self.args.no_video:
                self.dvbs2.close()
            self.gps.close()
            LOG.info("Composite transmitter stopped")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[CombinedTX] %(levelname)s: %(message)s",
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
            "with the current receiver to avoid aliasing",
            args.sample_rate / 1e6,
        )

    transmitter = CompositeTransmitter(args)
    signal.signal(signal.SIGINT, transmitter.request_stop)
    signal.signal(signal.SIGTERM, transmitter.request_stop)
    try:
        transmitter.run()
    except KeyboardInterrupt:
        transmitter.request_stop()
    except Exception:
        LOG.exception("Composite transmitter failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
