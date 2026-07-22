from __future__ import annotations

import shutil
import subprocess
from typing import Optional

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


class Camera:
    WIDTH = 640
    HEIGHT = 480
    FPS = 15

    def __init__(self, device_path: str = "/dev/video0") -> None:
        self.device_path = device_path
        self._capture = None
        self._released = False
        self._v4l2_ctl: Optional[str] = None

        if cv2 is not None:
            self._capture = cv2.VideoCapture(device_path, cv2.CAP_V4L2)
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.WIDTH)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.HEIGHT)
            self._capture.set(cv2.CAP_PROP_FPS, self.FPS)
        else:
            self._v4l2_ctl = shutil.which("v4l2-ctl")
            if self._v4l2_ctl is not None:
                try:
                    subprocess.run(
                        [
                            self._v4l2_ctl,
                            "--device",
                            self.device_path,
                            (
                                "--set-fmt-video="
                                f"width={self.WIDTH},height={self.HEIGHT},"
                                "pixelformat=BGR3"
                            ),
                            f"--set-parm={self.FPS}",
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                        timeout=5,
                    )
                except (OSError, subprocess.SubprocessError):
                    self._v4l2_ctl = None

    def read_frame(self) -> Optional[np.ndarray]:
        if self._released:
            return None

        if self._capture is not None:
            if not self._capture.isOpened():
                return None
            success, frame = self._capture.read()
            return frame if success else None

        if self._v4l2_ctl is None:
            return None

        try:
            result = subprocess.run(
                [
                    self._v4l2_ctl,
                    "--device",
                    self.device_path,
                    "--stream-mmap=3",
                    "--stream-count=1",
                    "--stream-to=-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        expected_size = self.WIDTH * self.HEIGHT * 3
        if result.returncode != 0 or len(result.stdout) < expected_size:
            return None

        return np.frombuffer(
            result.stdout[:expected_size], dtype=np.uint8
        ).reshape(self.HEIGHT, self.WIDTH, 3).copy()

    def release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._released = True
