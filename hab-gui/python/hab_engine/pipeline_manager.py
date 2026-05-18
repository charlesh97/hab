"""Pipeline Manager — controls ffmpeg → tsp → FIFO encoding pipeline."""

import os
import subprocess
import threading
import logging
from pathlib import Path
from typing import Optional, Callable

from .models import PipelineStatus

logger = logging.getLogger(__name__)


class PipelineManager:
    """
    Manages the video encoding pipeline:
    ffmpeg (encode MP4 → MPEG-TS over UDP) → tsp (rate regulate) → FIFO file
    """

    def __init__(self, tsfifo_path: str = "/tmp/tsfifo"):
        self.tsfifo_path = tsfifo_path
        self._ffmpeg: Optional[subprocess.Popen] = None
        self._tsp: Optional[subprocess.Popen] = None
        self._debug_callback: Optional[Callable[[str, str], None]] = None
        self._lock = threading.Lock()
        self._status = PipelineStatus()
        self._threads: list[threading.Thread] = []

    def set_debug_callback(self, callback: Callable[[str, str], None]):
        """Set callback for debug output (process_name, message)."""
        self._debug_callback = callback

    @property
    def status(self) -> PipelineStatus:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._status.running

    def start(self, input_file: str,
              video_bitrate: str = "700k",
              audio_bitrate: str = "128k",
              resolution: str = "1920:1080",
              framerate: int = 30,
              muxrate: int = 965326,
              ts_bitrate: int = 965326) -> bool:
        """Start ffmpeg + tsp pipeline for the given input file."""
        if self._status.running:
            logger.warning("Pipeline already running")
            return False

        if not os.path.exists(input_file):
            logger.error(f"Input file not found: {input_file}")
            return False

        with self._lock:
            try:
                # Create named pipe
                if os.path.exists(self.tsfifo_path):
                    os.remove(self.tsfifo_path)
                os.mkfifo(self.tsfifo_path)
                logger.info(f"Created FIFO: {self.tsfifo_path}")

                # ── ffmpeg command ──
                ffmpeg_cmd = [
                    "ffmpeg", "-re", "-fflags", "+genpts",
                    "-i", input_file,
                    "-vf", f"scale={resolution},format=yuv420p",
                    "-r", str(framerate),
                    "-c:v", "libx264", "-preset", "veryfast",
                    "-tune", "zerolatency",
                    "-g", str(framerate),
                    "-keyint_min", str(framerate),
                    "-b:v", video_bitrate,
                    "-maxrate", video_bitrate,
                    "-bufsize", str(int(video_bitrate.replace("k", "")) * 3 // 4) + "k",
                    "-c:a", "mp2",
                    "-b:a", audio_bitrate,
                    "-f", "mpegts",
                    "-muxrate", str(muxrate),
                    "-mpegts_flags", "+resend_headers",
                    f"udp://239.1.1.1:5001?pkt_size=1316"
                ]

                self._ffmpeg = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                # ── tsp command ──
                tsp_cmd = [
                    "tsp", "-I", "ip", "239.1.1.1:5001",
                    "-P", "regulate", "--bitrate", str(ts_bitrate),
                    "-O", "file", self.tsfifo_path,
                ]

                self._tsp = subprocess.Popen(
                    tsp_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                # Start output reader threads
                if self._ffmpeg.stdout:
                    t = threading.Thread(
                        target=self._read_output,
                        args=(self._ffmpeg, "ffmpeg"),
                        daemon=True
                    )
                    t.start()
                    self._threads.append(t)

                if self._tsp.stdout:
                    t = threading.Thread(
                        target=self._read_output,
                        args=(self._tsp, "tsp"),
                        daemon=True
                    )
                    t.start()
                    self._threads.append(t)

                self._status = PipelineStatus(
                    running=True,
                    file_path=input_file,
                    bitrate=ts_bitrate,
                )
                logger.info(f"Pipeline started: {input_file}")
                return True

            except Exception as e:
                logger.error(f"Failed to start pipeline: {e}")
                self._cleanup()
                return False

    def _read_output(self, process: subprocess.Popen, name: str):
        """Read stdout from a process line by line."""
        try:
            for line in process.stdout:
                line = line.strip()
                if line:
                    if self._debug_callback:
                        self._debug_callback(name, line)
                    logger.debug(f"[{name}] {line}")
        except Exception:
            pass

    def stop(self):
        """Stop the pipeline and clean up."""
        with self._lock:
            self._cleanup()
            self._status = PipelineStatus()

    def _cleanup(self):
        """Kill processes and remove FIFO."""
        for proc, name in [(self._ffmpeg, "ffmpeg"), (self._tsp, "tsp")]:
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                except Exception:
                    pass

        self._ffmpeg = None
        self._tsp = None

        if os.path.exists(self.tsfifo_path):
            try:
                os.remove(self.tsfifo_path)
            except Exception:
                pass
