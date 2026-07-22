#!/usr/bin/env python3
"""
Phase 1E: USB UVC Camera Test
Tests /dev/video0 capture via OpenCV (cv2), falling back to v4l2-ctl or fswebcam.

Usage:
    python test_camera.py                    # run all tests
    python test_camera.py --device /dev/video1  # alternate device
"""

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEVICE = "/dev/video0"
OUTPUT_FRAME = "test_frame.jpg"


def _size_fmt(num_bytes: int) -> str:
    for unit in ("B", "KB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} MB"


def _err(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Phase 1 – device presence
# ---------------------------------------------------------------------------

def device_present(device: str) -> bool:
    """Return True if the V4L2 device node exists."""
    return os.path.exists(device)


# ---------------------------------------------------------------------------
# Phase 2 – query capabilities (v4l2-ctl – required fallback tool)
# ---------------------------------------------------------------------------

def _v4l2_json(device: str) -> Optional[dict]:
    """Run ``v4l2-ctl --all`` and return parsed JSON (if supported)."""
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "-d", device, "--all"],
            capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None

    # v4l2-ctl >= 1.22 supports ``--list-formats-json``, but ``--all``
    # includes that plus driver/card info. Try raw parsing first.
    return _parse_v4l2_all(proc.stdout, device)


def _parse_v4l2_all(output: str, device: str) -> dict:
    """Parse the human-readable ``v4l2-ctl --all`` output into a dict."""
    result: dict = {"device": device, "driver": "", "card": "", "bus": "",
                    "resolutions": [], "formats": []}
    res_seen = set()
    fmt_seen = set()

    for line in output.splitlines():
        line = line.strip()
        # Driver / Card / Bus info
        if line.startswith("Driver name"):
            result["driver"] = line.split(":", 1)[-1].strip().strip('"')
        elif line.startswith("Card type"):
            result["card"] = line.split(":", 1)[-1].strip().strip('"')
        elif line.startswith("Bus info"):
            result["bus"] = line.split(":", 1)[-1].strip().strip('"')

        # Format line: "Index       : 0\n        Type        : Video Capture\n        Pixel Format: 'MJPG' (compressed)"
        m = re.match(r"Pixel Format\s*:\s*'(\w+)'", line)
        if m:
            fmt_seen.add(m.group(1))

        # Resolution: "Size: Discrete 1920x1080"
        m = re.match(r"Size:\s*(?:Discrete|Stepwise)\s+(\d+)x(\d+)", line, re.IGNORECASE)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            res_seen.add((w, h))

    result["formats"] = sorted(fmt_seen)
    result["resolutions"] = [f"{w}x{h}" for w, h in sorted(res_seen, key=lambda x: x[0] * x[1])]
    return result


def query_capabilities(device: str) -> Optional[dict]:
    """Return a dict with driver, card, resolutions, and formats."""
    info = _v4l2_json(device)
    if info:
        return info

    # Older v4l2-ctl without JSON – text parse
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "-d", device, "--list-formats-ext"],
            capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        _err("v4l2-ctl not found – install v4l-utils")
        return None
    if proc.returncode != 0:
        _err(f"v4l2-ctl returned {proc.returncode}: {proc.stderr.strip()}")
        return None
    return _parse_v4l2_all(proc.stdout, device)


# ---------------------------------------------------------------------------
# Phase 3 – capture one frame
# ---------------------------------------------------------------------------

def capture_opencv(device: str, output_path: str) -> Optional[dict]:
    """Capture a frame via OpenCV.  Returns dict with dimensions/size/format or None."""
    try:
        import cv2
    except ImportError:
        return None  # caller will try fallback

    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        cap.release()
        return None

    try:
        # Let the camera auto-expose (a few read() warm-ups)
        for _ in range(10):
            cap.read()

        ret, frame = cap.read()
        if not ret or frame is None:
            _err("OpenCV: read() returned no frame")
            return None

        cv2.imwrite(output_path, frame)
        h, w = frame.shape[:2]
        channels = 1 if len(frame.shape) == 2 else frame.shape[2]
        fmt_str = "GRAY" if channels == 1 else f"BGR-{channels}ch"
        return {
            "backend": "OpenCV",
            "width": w,
            "height": h,
            "channels": channels,
            "format": fmt_str,
            "file": output_path,
        }
    finally:
        cap.release()


def capture_fswebcam(device: str, output_path: str) -> Optional[dict]:
    """Capture a frame via fswebcam."""
    if shutil.which("fswebcam") is None:
        return None

    proc = subprocess.run(
        ["fswebcam", "-d", device, "--no-banner", "-r", "1920x1080",
         "--jpeg", "95", output_path],
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        _err(f"fswebcam failed: {proc.stderr.strip()}")
        return None
    return _frame_metadata(output_path, backend="fswebcam")


def capture_v4l2ctl(device: str, output_path: str) -> Optional[dict]:
    """Capture via ``v4l2-ctl --stream-mmap --stream-count=1 --stream-to=``."""
    if shutil.which("v4l2-ctl") is None:
        return None

    # v4l2-ctl can stream raw frames, but a JPEG is trickier.
    # On UVC cameras a common pattern is:
    #   v4l2-ctl -d /dev/video0 --set-fmt-video=width=1920,height=1080,pixelformat=MJPG
    #   v4l2-ctl -d /dev/video0 --stream-mmap=3 --stream-count=1 --stream-to=frame.raw
    # That produces an MJPEG stream which we rename to .jpg.
    raw = output_path + ".raw"
    # Try to set MJPG first
    subprocess.run(
        ["v4l2-ctl", "-d", device,
         "--set-fmt-video", "width=1920,height=1080,pixelformat=MJPG"],
        capture_output=True, timeout=10,
    )
    proc = subprocess.run(
        ["v4l2-ctl", "-d", device,
         "--stream-mmap", "--stream-count=1", f"--stream-to={raw}"],
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0 or not os.path.exists(raw):
        _err(f"v4l2-ctl stream failed: {proc.stderr.strip()}")
        return None

    os.replace(raw, output_path)
    return _frame_metadata(output_path, backend="v4l2-ctl")


def _frame_metadata(path: str, backend: str) -> Optional[dict]:
    """Return metadata for a saved image file."""
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        _err(f"Cannot stat {path}: {exc}")
        return None

    # Try reading dimensions with PIL (likely available if OpenCV isn't)
    try:
        from PIL import Image
        img = Image.open(path)
        w, h = img.size
        fmt = img.format or pathlib.Path(path).suffix.upper().lstrip(".")
        return {
            "backend": backend,
            "width": w,
            "height": h,
            "channels": len(img.getbands()),
            "format": fmt,
            "file": path,
        }
    except ImportError:
        pass
    except Exception as exc:
        _err(f"PIL read error: {exc}")

    # Best-effort without PIL
    return {
        "backend": backend,
        "width": None,
        "height": None,
        "channels": None,
        "format": pathlib.Path(path).suffix.upper().lstrip("."),
        "file": path,
    }


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

def run_tests(device: str, output_path: str = OUTPUT_FRAME) -> bool:
    """Return True if all tests pass."""
    all_pass = True
    print(f"=== Camera Test: {device} ===\n")

    # --- 1. Device presence ---
    print("[1/3] Checking device presence …")
    if not device_present(device):
        _err(f"Camera device not found: {device}")
        print("\n  ⚠ No /dev/video0 node.  Is the USB UVC camera plugged in?\n"
              "  On Rock 2A / Linux, check:\n"
              "    lsusb | grep -i camera\n"
              "    dmesg | tail -20\n"
              "    v4l2-ctl --list-devices\n")
        return False
    print(f"  ✓ {device} exists")

    # --- 2. Query capabilities ---
    print("\n[2/3] Querying capabilities …")
    caps = query_capabilities(device)
    if caps:
        print(f"  Card   : {caps.get('card', 'N/A')}")
        print(f"  Driver : {caps.get('driver', 'N/A')}")
        print(f"  Bus    : {caps.get('bus', 'N/A')}")
        print(f"  Formats: {', '.join(caps['formats']) if caps['formats'] else '(none)'}")
        print(f"  Resolutions: {', '.join(caps['resolutions']) if caps['resolutions'] else '(none)'}")
    else:
        print("  ⚠ Could not query capabilities (v4l2-ctl missing?)")
        all_pass = False

    # --- 3. Capture frame ---
    print("\n[3/3] Capturing test frame …")
    meta = None
    for backend_name, backend_fn in [
        ("OpenCV", capture_opencv),
        ("fswebcam", capture_fswebcam),
        ("v4l2-ctl", capture_v4l2ctl),
    ]:
        try:
            meta = backend_fn(device, output_path)
        except Exception as exc:
            print(f"  ⚠ {backend_name} raised exception: {exc}")
            continue
        if meta:
            print(f"  Backend: {backend_name}")
            break

    if meta is None:
        _err("All capture backends failed.")
        _err("Install one of: python3-opencv, fswebcam, or v4l-utils (v4l2-ctl)")
        return False

    frame_size = os.path.getsize(meta["file"]) if os.path.exists(meta["file"]) else 0
    print(f"  Width   : {meta.get('width', '?')}")
    print(f"  Height  : {meta.get('height', '?')}")
    print(f"  Channels: {meta.get('channels', '?')}")
    print(f"  Format  : {meta.get('format', '?')}")
    print(f"  File    : {meta['file']} ({_size_fmt(frame_size)})")

    if frame_size == 0:
        _err("Captured frame is empty / 0 bytes")
        all_pass = False
    else:
        print(f"  ✓ Frame captured successfully")

    print(f"\n=== {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'} ===")
    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1E: USB UVC Camera Test")
    parser.add_argument("--device", default=DEVICE, help=f"Video device (default: {DEVICE})")
    parser.add_argument("--output", default=OUTPUT_FRAME, help=f"Output JPEG (default: {OUTPUT_FRAME})")
    args = parser.parse_args()

    success = run_tests(args.device, args.output)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
