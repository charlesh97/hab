#!/usr/bin/env python3
"""Composite-link soak monitor: periodic DVB-S2 stills + TX/RX liveness + crash detection.

Owns the one-shot ffmpeg MJPEG bridge lifecycle (combined_rx.py spawns it
fire-and-forget with -listen 1 and never restarts it), grabs a still each
interval, samples Rock 2A TX progress over SSH, and watches RX-side PIDs.

Usage:
    python3 soak_monitor.py [--minutes 30] [--interval 60]
"""

import argparse
import datetime as dt
import os
import signal
import socket
import subprocess
import sys
import time

SOAK_ROOT = "/Users/charleslab/git/hab/soak"
RX_PID = None             # set via --rx-pid (combined_rx.py process)
TX_HOST = "rock2a.local"
VIDEO_PORT = 8001
UDP_PORT = 1234
BRIDGE_CMD = [
    "ffmpeg", "-hide_banner", "-loglevel", "warning",
    "-i", f"udp://127.0.0.1:{UDP_PORT}",
    "-c:v", "mjpeg", "-q:v", "5",
    "-f", "mpjpeg", "-listen", "1",
    f"http://0.0.0.0:{VIDEO_PORT}/video",
]


def now() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def log(msg: str, fh) -> None:
    line = f"[{now()}] {msg}"
    print(line, flush=True)
    fh.write(line + "\n")
    fh.flush()


def kill_stale_bridges() -> None:
    """Kill any ffmpeg consuming udp:1234 or holding :8001 (stale one-shot bridge)."""
    try:
        out = subprocess.run(
            ["pgrep", "-f", f"udp://127.0.0.1:{UDP_PORT}"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        for pid in out.splitlines():
            if pid and int(pid) != os.getpid():
                os.kill(int(pid), signal.SIGKILL)
                log(f"killed stale bridge pid {pid}", sys.stderr)
    except Exception as exc:
        log(f"kill_stale_bridges: {exc}", sys.stderr)


def wait_listener(port: int, timeout: float = 8.0) -> bool:
    """Probe whether a TCP listener is bound, WITHOUT connecting.

    The one-shot bridge treats the first accepted connection as its single
    client and exits after it. A connect()-based probe would therefore kill
    the bridge it is probing. lsof inspects the listen state instead.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(
            ["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return True
        time.sleep(0.5)
    return False


def start_bridge() -> subprocess.Popen | None:
    """Start fresh bridge, retrying on the known :8001 bind flake.

    The one-shot bridge binds :8001 only once it decodes a frame; with an
    intermittently corrupt TS the bind can take up to ~20s. Retry longer.
    """
    for attempt in range(2):
        p = subprocess.Popen(
            BRIDGE_CMD,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if wait_listener(VIDEO_PORT, timeout=14.0):
            return p
        try:
            p.kill()
        except ProcessLookupError:
            pass
    return None


def grab_still(path: str) -> tuple[bool, int]:
    """One MJPEG frame via a fresh bridge. Returns (ok, size_bytes).

    Strategy: reuse a serving bridge if present; otherwise kill stale ones
    and spin up fresh. The one-shot bridge dies after one client, so retry
    with a fresh bridge up to 4 generations; each attempt rides a decode
    window (H.264 over the lossy link delivers frames intermittently).
    """
    size = 0
    bridge = None
    for gen in range(4):
        if not wait_listener(VIDEO_PORT, timeout=1.0):
            if gen == 0:
                kill_stale_bridges()
            bridge = start_bridge()
            if bridge is None and not wait_listener(VIDEO_PORT, timeout=2.0):
                continue
        if not wait_listener(VIDEO_PORT, timeout=2.0):
            continue
        # Let the decode settle a few seconds before grabbing: the H.264
        # delivers frames erratically right after the muxer opens.
        time.sleep(3)
        grab = subprocess.Popen(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-timeout", "20000000",
             "-i", f"http://127.0.0.1:{VIDEO_PORT}/video",
             "-frames:v", "1", "-q:v", "2", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            grab.wait(timeout=20)
        except subprocess.TimeoutExpired:
            grab.kill()
            grab.wait(timeout=5)
            return False, 0
        size = os.path.getsize(path) if os.path.exists(path) else 0
        if grab.returncode == 0 and size > 1000:
            return True, size
        # The one-shot bridge exited after serving; next generation restarts it.
        if bridge is not None:
            try:
                bridge.kill()
            except ProcessLookupError:
                pass
            bridge = None
    return False, size


def tx_progress() -> tuple[int | None, str | None]:
    """SSH to Rock 2A, tail TX log. Returns (max_seq, last_line)."""
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=no",
             "-o", "BatchMode=yes", f"hab@{TX_HOST}",
             "tail -n 40 /tmp/tx_*.log"],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode != 0:
            return None, f"ssh rc={r.returncode}"
        seqs = [int(m) for m in __import__("re").findall(r"seq=(\d+)", r.stdout)]
        last = [ln for ln in r.stdout.strip().splitlines() if ln.strip()][-1:]
        return (max(seqs) if seqs else None), (last[0] if last else None)
    except Exception as exc:
        return None, str(exc)


def rx_alive() -> dict:
    """Process-level liveness for RX side."""
    result = {"combined": False, "hackrf": False, "dvbs2": False}
    if RX_PID is not None:
        try:
            os.kill(RX_PID, 0)
            result["combined"] = True
        except OSError:
            pass
    try:
        out = subprocess.run(["pgrep", "-f", "hackrf_transfer"],
                             capture_output=True, text=True, timeout=10).stdout
        result["hackrf"] = bool(out.strip())
    except Exception:
        pass
    try:
        out = subprocess.run(["pgrep", "-f", "dvbs2/rx.py --source fd"],
                             capture_output=True, text=True, timeout=10).stdout
        result["dvbs2"] = bool(out.strip())
    except Exception:
        pass
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=30)
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--rx-pid", type=int, default=None,
                    help="PID of the combined_rx.py process to watch")
    args = ap.parse_args()
    global RX_PID
    RX_PID = args.rx_pid

    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_dir = os.path.join(SOAK_ROOT, stamp)
    stills_dir = os.path.join(out_dir, "stills")
    os.makedirs(stills_dir, exist_ok=True)
    log_path = os.path.join(out_dir, "soak.log")

    fh = open(log_path, "w")
    log(f"SOAK START: {args.minutes} min @ {args.interval}s interval", fh)
    log(f"out_dir={out_dir}", fh)
    log(f"RX pid={RX_PID} alive={rx_alive()}", fh)

    tx_seq0, _ = tx_progress()
    log(f"TX baseline seq={tx_seq0}", fh)

    still_fails = 0
    tx_fails = 0
    start = time.time()
    end = start + args.minutes * 60
    idx = 0
    while time.time() < end:
        idx += 1
        elapsed = int(time.time() - start)
        # First still immediately, then on interval boundaries.
        if idx > 1:
            next_at = start + idx * args.interval
            wait = next_at - time.time()
            if wait > 0:
                time.sleep(wait)

        still_path = os.path.join(stills_dir, f"still_{idx:04d}.jpg")
        ok, size = grab_still(still_path)
        still_fails = still_fails + 1 if not ok else 0

        tx_seq, tx_last = tx_progress()
        tx_fails = tx_fails + 1 if tx_seq is None else 0

        rx = rx_alive()

        log(
            f"t=+{elapsed//60:02d}:{elapsed%60:02d} "
            f"still=#{idx} {'OK' if ok else 'FAIL'} {size}B "
            f"tx_seq={tx_seq} tx_fail_streak={tx_fails} "
            f"rx={rx} still_fail_streak={still_fails}",
            fh,
        )
        if tx_last and tx_seq is None:
            log(f"  tx_last: {tx_last[:160]}", fh)

        if not rx["combined"]:
            log("*** CRASH: combined_rx.py process gone ***", fh)
        if not rx["dvbs2"]:
            log("*** WARN: DVB-S2 child not running ***", fh)
        if not rx["hackrf"]:
            log("*** WARN: hackrf_transfer not running ***", fh)
        if still_fails >= 3:
            log("*** CRASH: 3 consecutive still failures (video path) ***", fh)
        if tx_fails >= 3:
            log("*** WARN: 3 consecutive TX ssh failures ***", fh)

    elapsed = int(time.time() - start)
    tx_seq_final, _ = tx_progress()
    rx_final = rx_alive()
    log(f"SOAK END: {elapsed}s. tx_seq {tx_seq0} -> {tx_seq_final}. rx={rx_final}", fh)
    log(f"stills: {idx} attempted, {idx - still_fails} consecutive-ok streak, dir={stills_dir}", fh)
    fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
