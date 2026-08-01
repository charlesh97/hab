#!/usr/bin/env python3
"""GPS Packet Bridge — launches pkt_simple_rx.py, translates to dashboard JSON.

Reads BPSK-decoded packets from pkt_simple_rx.py stdout, unpacks
PositionFrame binary payloads, and POSTs dashboard-compatible JSON
to the HAB Receiver Server at /api/packet.

Usage:
    /opt/homebrew/bin/python3.14 rf/packet/gps_bridge.py \
        --freq 915e6 --serial 60a464dc3606610f --lna 32 --vga 40 --amp

The bridge manages the RX subprocess lifecycle and exits on SIGINT/ SIGTERM.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed.  Run: pip install requests")
    sys.exit(1)

# ── Add payload modules to path ────────────────────────────────────
_HAB_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_HAB_ROOT / "payload"))

from telemetry.packet_format import PositionFrame, unpack_frame  # noqa: E402

# ── Constants ──────────────────────────────────────────────────────

BALLOON_ID = "HAB-001"
MISSION_ID = "FLIGHT-1"
DASHBOARD_URL = "http://localhost:8000/api/packet"
PYTHON_BIN = "/opt/homebrew/bin/python3.14"

# pkt_simple_rx.py output format:
#   [PktRx] #N FO=+1.2 kHz | 'raw bytes here'
# The payload bytes may contain non-printable characters, so we
# capture the raw bytes between the pipe and end-of-line by
# reading the RX stdout as binary.
#
# Strategy: parse "[PktRx] #" lines, extract everything after "| '"
# and before the closing "'".  Then decode escape sequences.


def extract_payload(line: str) -> bytes | None:
    """Extract payload bytes from a hex-encoded PktRx output line.

    With --hex-output, pkt_simple_rx.py outputs:
        [PktRx] #N FO=+X.X kHz phase=N | <hex>
    """
    m = re.search(r"\[PktRx\]\s+#\d+.*?\|\s*([0-9a-fA-F]+)", line)
    if not m:
        return None
    try:
        return bytes.fromhex(m.group(1))
    except ValueError:
        return None


def frame_to_dashboard(frame: PositionFrame) -> dict:
    """Convert a PositionFrame to dashboard-compatible JSON."""
    return {
        "v": 1,
        "id": BALLOON_ID,
        "mid": MISSION_ID,
        "seq": frame.seq,
        "t": f"T{time.strftime('%H:%M:%S', time.gmtime())}",
        "type": "position",
        "lat": frame.lat,
        "lon": frame.lon,
        "alt_m": frame.alt_m,
        "agl_m": frame.agl_m,
        "fix": frame.fix,
        "fix_type": frame.fix_type,
        "sats": frame.sats,
        "hdop": frame.hdop,
        "vdop": frame.vdop,
    }


async def read_rx_stdout(
    proc: asyncio.subprocess.Process, dashboard_url: str
) -> None:
    """Read lines from pkt_simple_rx.py stdout and POST packets."""
    assert proc.stdout is not None

    session = requests.Session()
    packets_sent = 0

    async for line in proc.stdout:
        line_str = line.decode("utf-8", errors="replace").strip()

        # Pass through RX status lines
        if not line_str.startswith("[PktRx]"):
            if any(kw in line_str for kw in ("Opening", "MHz", "Progress", "DONE", "FO")):
                print(f"  [RX] {line_str}", flush=True)
            continue

        # Extract payload
        payload = extract_payload(line_str)
        if payload is None:
            continue

        # Unpack binary frame
        try:
            frame = unpack_frame(payload)
        except (ValueError, TypeError) as exc:
            print(f"  [Bridge] unpack error ({len(payload)}B): {exc}", flush=True)
            continue

        if frame is None or not isinstance(frame, PositionFrame):
            print(f"  [Bridge] unknown frame type, {len(payload)}B", flush=True)
            continue

        # Convert to dashboard JSON
        packet = frame_to_dashboard(frame)

        # POST to dashboard
        try:
            resp = session.post(
                dashboard_url,
                json={"data": packet},
                timeout=5.0,
            )
            ok = resp.status_code == 200
        except requests.ConnectionError:
            ok = False
        except requests.Timeout:
            ok = False

        packets_sent += 1
        status = "✓" if ok else "✗"
        print(
            f"  [Bridge] #{packets_sent} {status}  "
            f"pos={frame.lat:.5f},{frame.lon:.5f}  "
            f"alt={frame.alt_m:.1f}m  sats={frame.sats}  "
            f"fix={frame.fix_type}",
            flush=True,
        )


async def main_async() -> None:
    parser = argparse.ArgumentParser(description="GPS Packet Bridge")
    parser.add_argument("--freq", type=float, default=915e6)
    parser.add_argument("--lna", type=float, default=32)
    parser.add_argument("--vga", type=float, default=40)
    parser.add_argument("--amp", action="store_true", default=True)
    parser.add_argument("--serial", type=str, default=None)
    parser.add_argument("--dashboard", type=str, default=DASHBOARD_URL,
                        help="Dashboard /api/packet URL")
    args = parser.parse_args()

    dashboard_url = args.dashboard

    # Locate pkt_simple_rx.py
    rx_script = _HAB_ROOT / "rf" / "packet" / "src" / "pkt_simple_rx.py"
    if not rx_script.exists():
        print(f"ERROR: RX script not found at {rx_script}")
        sys.exit(1)

    cmd = [
        PYTHON_BIN,
        str(rx_script),
        "--freq", str(int(args.freq)),
        "--duration", "0",  # run until killed
        "--lna", str(int(args.lna)),
        "--vga", str(int(args.vga)),
    ]
    if args.amp:
        cmd.append("--amp")
    if args.serial:
        cmd.extend(["--serial", args.serial])
    cmd.append("--hex-output")

    print(f"[Bridge] Launching: {' '.join(cmd)}")
    print(f"[Bridge] Dashboard: {DASHBOARD_URL}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={
            **os.environ,
            "PYTHONPATH": ":".join([
                "/opt/homebrew/lib/python3.14/site-packages",
                str(_HAB_ROOT / "rf" / "packet" / "src"),
                str(_HAB_ROOT / "rf" / "packet"),
            ]),
        },
    )

    print(f"[Bridge] RX PID {proc.pid} — Ctrl-C to stop")

    try:
        await read_rx_stdout(proc, dashboard_url)
    except asyncio.CancelledError:
        pass
    finally:
        print("[Bridge] Stopping RX...")
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except (ProcessLookupError, asyncio.TimeoutError):
            proc.kill()
        print("[Bridge] Stopped.")


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
