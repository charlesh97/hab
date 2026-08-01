# `gps_bridge.py` — Exhaustive Line-by-Line Analysis

**File:** `rf/packet/gps_bridge.py`  
**Role:** Process supervisor and protocol translator. Launches the BPSK packet receiver (`pkt_simple_rx.py`) as a subprocess, reads decoded binary payloads from its stdout, unpacks them into structured `PositionFrame` objects, and POSTs dashboard-compatible JSON to the HAB Receiver Server.

---

## Table of Contents

1. [Shebang & Module Docstring (lines 1–13)](#1-shebang--module-docstring-lines-113)
2. [Imports (lines 15–25)](#2-imports-lines-1525)
3. [Requests Import Guard (lines 27–31)](#3-requests-import-guard-lines-2731)
4. [sys.path Manipulation (lines 33–37)](#4-syspath-manipulation-lines-3337)
5. [Constants (lines 39–53)](#5-constants-lines-3953)
6. [`extract_payload()` (lines 56–68)](#6-extract_payload-lines-5668)
7. [`frame_to_dashboard()` (lines 71–89)](#7-frame_to_dashboard-lines-7189)
8. [`read_rx_stdout()` (lines 92–150)](#8-read_rx_stdout-lines-92150)
9. [`main_async()` (lines 153–216)](#9-main_async-lines-153216)
10. [`main()` / `__main__` guard (lines 219–227)](#10-main--__main__-guard-lines-219227)
11. [Implicit Assumptions & Fragilities](#11-implicit-assumptions--fragilities)
12. [Data-Flow Diagram](#12-data-flow-diagram)

---

## 1. Shebang & Module Docstring (lines 1–13)

```python
#!/usr/bin/env python3
```
**Line 1:** POSIX shebang line. Uses `/usr/bin/env` to locate `python3` from `$PATH` rather than a hardcoded path. However, the actual subprocess launch (line 172) uses the hardcoded `PYTHON_BIN = "/opt/homebrew/bin/python3.14"` — so this shebang is decorative for the bridge itself and does not affect the RX subprocess.

```python
"""GPS Packet Bridge — launches pkt_simple_rx.py, translates to dashboard JSON.
...
"""
```
**Lines 2–13:** Module docstring describing the pipeline:

- **Input:** BPSK-decoded packets from `pkt_simple_rx.py` stdout.
- **Processing:** Unpacks `PositionFrame` binary payloads.
- **Output:** POSTs dashboard-compatible JSON to the HAB Receiver Server at `/api/packet`.
- **Lifecycle:** The bridge manages the RX subprocess and exits on SIGINT/SIGTERM.
- **Usage example:** Demonstrates the CLI invocation with typical arguments (`--freq 915e6 --serial ... --lna 32 --vga 40 --amp`). The `915e6` (915 MHz) is the ISM-band target; the 32/40 dB gain values are specific to a HackRF SDR setup.

---

## 2. Imports (lines 15–25)

```python
from __future__ import annotations
```
**Line 15:** PEP 563 — enables postponed evaluation of type annotations. All annotations are treated as strings and not evaluated at runtime. This allows forward references (`PositionFrame` can appear before the import that defines it) and reduces import-time overhead. Required by `@dataclass(frozen=True, slots=True)` patterns in `packet_format.py`.

```python
import argparse         # CLI argument parsing
import asyncio          # async subprocess management, async for over stdout
import json             # (unused directly — the bridge POSTs dicts via requests.Session, not json.dumps)
import os               # os.environ for subprocess env propagation
import re               # regex matching of PktRx output lines
import signal           # (unused — the bridge catches KeyboardInterrupt via asyncio.CancelledError)
import sys              # sys.exit(1), sys.path manipulation
import time             # time.strftime for dashboard timestamps
from pathlib import Path  # clean path arithmetic for HAB_ROOT resolution
```
**Lines 17–25:** Standard library imports. Notable: `signal` is imported but never referenced — the bridge relies on `asyncio.CancelledError` (raised by `asyncio.run` when a `KeyboardInterrupt` arrives) rather than explicit signal handlers. `json` is imported but never directly called — `requests.Session.post(json=...)` handles JSON serialization internally.

---

## 3. Requests Import Guard (lines 27–31)

```python
try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed.  Run: pip install requests")
    sys.exit(1)
```
**Lines 27–31:** Defensive import guard. `requests` is a third-party library not in the standard library. On macOS Homebrew Python 3.14, it may or may not be installed globally. This guard fails early with a clear message rather than crashing deep inside `read_rx_stdout()` with a cryptic `NameError`. The suggested fix (`pip install requests`) assumes the user's pip maps to the correct Python installation — this assumption can break in multi-version environments.

---

## 4. sys.path Manipulation (lines 33–37)

```python
# ── Add payload modules to path ────────────────────────────────────
_HAB_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_HAB_ROOT / "payload"))
```
**Lines 33–35:** Two critical operations in two lines:

### Line 34: `_HAB_ROOT` calculation

```
Path(__file__)                           # rf/packet/gps_bridge.py  (could be relative)
    .resolve()                           # /absolute/path/to/hab/rf/packet/gps_bridge.py
    .parent                              # /absolute/path/to/hab/rf/packet/
    .parent                              # /absolute/path/to/hab/rf/
    .parent                              # /absolute/path/to/hab/
```

This three-level `parent` chain is a **layout-sensitive relative path**. It assumes:

- `gps_bridge.py` lives at `<repo_root>/rf/packet/`
- The repo root (`_HAB_ROOT`) is three directories up
- The file structure is exactly `rf/packet/gps_bridge.py`

If the file is moved (e.g., to `rf/packet/src/gps_bridge.py` or to a top-level `bridge/` directory), this calculation silently produces the wrong root and the subsequent import will fail with `ModuleNotFoundError`.

The leading underscore (`_HAB_ROOT`) signals "module-private" by convention — the constant is not part of the public API.

### Line 35: `sys.path.insert(0, ...)`

Inserts `_HAB_ROOT/payload/` at the **front** of `sys.path` (index 0). This takes priority over other entries. The purpose is to resolve the import on line 37:

```python
from telemetry.packet_format import PositionFrame, unpack_frame  # noqa: E402
```
**Line 37:** This is the payoff — imports `PositionFrame` (frozen dataclass with 38-byte struct layout) and `unpack_frame` (type-dispatched unpacker). The actual file lives at `<HAB_ROOT>/payload/telemetry/packet_format.py`. The `# noqa: E402` comment suppresses flake8's "module level import not at top of file" warning since the import must follow the `sys.path` manipulation.

### Why not `sys.path.append`?

`insert(0, ...)` prepends rather than appends. This ensures the local `payload/` directory wins over any system-installed packages that might also have a `telemetry` subpackage. Without this, a `pip install telemetry` (a real PyPI package) could shadow the local module.

---

## 5. Constants (lines 39–53)

### Hardcoded Values

```python
BALLOON_ID = "HAB-001"
MISSION_ID = "FLIGHT-1"
DASHBOARD_URL = "http://localhost:8000/api/packet"
PYTHON_BIN = "/opt/homebrew/bin/python3.14"
```
**Lines 41–44:** Four module-level constants:

| Constant | Value | Meaning | Fragility |
|---|---|---|---|
| `BALLOON_ID` | `"HAB-001"` | Payload identifier, embedded in every dashboard POST | Hardcoded — real flights would need `--balloon-id` CLI arg |
| `MISSION_ID` | `"FLIGHT-1"` | Mission identifier, also in every POST | Same as above — should be a CLI arg or env var |
| `DASHBOARD_URL` | `"http://localhost:8000/api/packet"` | Default dashboard endpoint | Overridable via `--dashboard` CLI arg (line 160), which is good. But the constant includes `localhost`, assuming dashboard runs on the same machine |
| `PYTHON_BIN` | `"/opt/homebrew/bin/python3.14"` | Hardcoded path to the Python interpreter for the RX subprocess | Extremely brittle — only works on Apple Silicon Macs with Homebrew Python 3.14 at that exact path. x86 Macs use `/usr/local`, Linux uses different paths entirely, and version changes require editing the source |

### Docstring Comment Block (lines 46–53)

```python
# pkt_simple_rx.py output format:
#   [PktRx] #N FO=+1.2 kHz | 'raw bytes here'
# The payload bytes may contain non-printable characters, so we
# capture the raw bytes between the pipe and end-of-line by
# reading the RX stdout as binary.
#
# Strategy: parse "[PktRx] #" lines, extract everything after "| '"
# and before the closing "'".  Then decode escape sequences.
```
**Lines 46–53:** This comment block describes an **older output format** that is no longer active. In the current `pkt_simple_rx.py`, when `--hex-output` is passed (which `gps_bridge.py` always does — line 184), the output is:

```
[PktRx] #N FO=+X.X kHz phase=N | <hex>
```

…with raw hex bytes after the pipe, **not** quoted raw bytes like `| 'raw bytes here'`. The comment references a previously used format where payloads were emitted as Python string literals (with escape sequences). The current format is hex-encoded, which is what `extract_payload()` actually handles (see §6). **The docstring comment is stale but the implementation is correct.**

The comment also says "reading the RX stdout as binary" — but on line 101, stdout is actually decoded as UTF-8 (`line.decode("utf-8", errors="replace")`). This is fine because `--hex-output` produces only ASCII-safe hex characters, but the comment is misleading.

---

## 6. `extract_payload()` (lines 56–68)

```python
def extract_payload(line: str) -> bytes | None:
```

**Line 56:** Type signature: accepts a string (decoded stdout line), returns either raw `bytes` or `None` if the line doesn't match or contains invalid hex.

```python
    """Extract payload bytes from a hex-encoded PktRx output line.

    With --hex-output, pkt_simple_rx.py outputs:
        [PktRx] #N FO=+X.X kHz phase=N | <hex>
    """
```

**Lines 57–61:** Updated docstring that correctly describes the current output format, unlike the stale comment block at lines 46–53.

### Regex Breakdown (line 62)

```python
    m = re.search(r"\[PktRx\]\s+#\d+.*?\|\s*([0-9a-fA-F]+)", line)
```

This is the core extraction. Let's disassemble the regex token by token:

| Token | Meaning |
|---|---|
| `\[PktRx\]` | Literal string `[PktRx]` — brackets escaped since they are regex metacharacters |
| `\s+` | One or more whitespace characters (space between `[PktRx]` and `#`) |
| `#` | Literal `#` character |
| `\d+` | One or more digits — the packet counter (`N`) |
| `.*?` | Non-greedy match of any characters — swallows ` FO=+X.X kHz phase=N` or any variant (with/without phase field, with/without FO sign) |
| `\|` | Literal pipe `\|` — escaped since `\|` is a regex alternation operator |
| `\s*` | Zero or more whitespace characters after the pipe |
| `([0-9a-fA-F]+)` | **Capturing group 1:** One or more hex digits (0-9, a-f, A-F) — this is the payload |

**Why `.*?` (non-greedy)?** Without the `?`, `.*` would greedily consume past the pipe and potentially eat hex digits. `.*?\|\s*` ensures matching stops at the *first* pipe character encountered, because `.*?` gives back as few characters as possible.

**Why `\s*` after the pipe?** The output format uses `| ` (pipe + space), but a trailing space is optional. `\s*` is defensive.

**Why `[0-9a-fA-F]+` and not `[0-9a-fA-F]{2,}`?** No minimum length constraint. A zero-byte payload would match empty string (though `bytes.fromhex("")` returns `b""`, which is valid). In practice a PositionFrame is 38 bytes = 76 hex chars.

**What this regex does NOT match:** Lines that have additional content after the hex (unlikely in current output), or hex that contains spaces or other delimiters.

```python
    if not m:
        return None
```
**Line 63–64:** No match → `None`. This handles non-PktRx lines or PktRx lines with corrupted format.

```python
    try:
        return bytes.fromhex(m.group(1))
    except ValueError:
        return None
```
**Lines 65–68:** `bytes.fromhex()` converts the captured hex string to raw bytes. It raises `ValueError` if the string has an odd number of characters (valid hex must have even length). Caught and converted to `None` — the bridge silently skips malformed payloads.

**Important:** `bytes.fromhex("")` returns `b""` (empty bytes), which would then fail `unpack_frame()` with "expected 38 bytes, got 0". The regex requires at least one hex digit (`+`), and one digit is odd length → `ValueError` → `None`. So the minimum viable match is 2 hex digits (1 byte), which would still fail unpack validation.

---

## 7. `frame_to_dashboard()` (lines 71–89)

```python
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
```

### Field Mapping

| JSON Key | Source | Type | Description |
|---|---|---|---|
| `v` | Literal `1` | `int` | Dashboard JSON schema version |
| `id` | `BALLOON_ID` constant | `str` | Payload identifier (`"HAB-001"`) |
| `mid` | `MISSION_ID` constant | `str` | Mission identifier (`"FLIGHT-1"`) |
| `seq` | `frame.seq` | `int` | Packet sequence number from binary frame |
| `t` | `time.gmtime()` | `str` | Bridge-side timestamp in format `T14:30:00` (UTC, HH:MM:SS only — **no date component**) |
| `type` | Literal `"position"` | `str` | Packet type discriminator for the dashboard |
| `lat` | `frame.lat` | `float` | Latitude (decimal degrees) |
| `lon` | `frame.lon` | `float` | Longitude (decimal degrees) |
| `alt_m` | `frame.alt_m` | `float` | Altitude above MSL (meters) |
| `agl_m` | `frame.agl_m` | `float` | Altitude above ground level (meters) |
| `fix` | `frame.fix` | `bool` | GPS fix status (True/False) |
| `fix_type` | `frame.fix_type` | `str` | GPS fix quality: `"none"`, `"2d"`, or `"3d"` |
| `sats` | `frame.sats` | `int` | Number of tracked satellites |
| `hdop` | `frame.hdop` | `float` | Horizontal dilution of precision |
| `vdop` | `frame.vdop` | `float` | Vertical dilution of precision |

### Critical Design Issue: Timestamp (line 78)

```python
"t": f"T{time.strftime('%H:%M:%S', time.gmtime())}",
```

The timestamp `t` is **not** from the GPS frame — it is the bridge's wall-clock time at the moment of POST. This means:

1. **No date:** The `T` prefix suggests an ISO 8601 time, but only `HH:MM:SS` is included. The dashboard cannot reconstruct the absolute timestamp (which day?).
2. **Not GPS time:** The GPS receiver in the payload provides its own time. If the SDR records a packet and the bridge processes it minutes later (offline replay), the timestamp is wrong by that delay.
3. **Latency indicator:** In live mode, the bridge's `time.strftime` roughly approximates reception time + decoding latency, which is more of a "received at" timestamp than a "measured at" timestamp.

A more robust design would include `frame.gps_time` if available in the PositionFrame, or at minimum format the full ISO 8601 datetime.

### Dataclass Field Guarantees

The `PositionFrame` is a `frozen=True, slots=True` dataclass. This means:
- All fields are guaranteed to exist (no missing attributes).
- Fields are immutable after construction.
- No extraneous attributes can be added.

`frame_to_dashboard` can safely access `frame.lat`, `frame.lon`, etc. without AttributeError risk.

---

## 8. `read_rx_stdout()` (lines 92–150)

```python
async def read_rx_stdout(
    proc: asyncio.subprocess.Process, dashboard_url: str
) -> None:
```

**Lines 92–94:** Async function signature. Takes the subprocess handle and the dashboard URL (can differ from `DASHBOARD_URL` if `--dashboard` was passed). Returns `None` — all output goes to stdout and HTTP.

```python
    assert proc.stdout is not None
```
**Line 96:** Runtime assertion. `asyncio.create_subprocess_exec` with `stdout=asyncio.subprocess.PIPE` guarantees `proc.stdout` is non-None, but the type checker doesn't know this — the annotation is `asyncio.StreamReader | None`. The `assert` both satisfies the type checker and guards against programming errors where stdin or stderr was piped but stdout was not.

```python
    session = requests.Session()
```
**Line 98:** Creates a persistent HTTP session. Benefits:
- Connection reuse via HTTP keep-alive (avoids TCP handshake overhead per packet).
- Connection pooling with automatic retry.
- Shared cookie jar and headers across all POSTs (unused here, but available).

```python
    packets_sent = 0
```
**Line 99:** Running counter for display purposes. Not the same as `frame.seq` — this counts bridge-processed packets, while `frame.seq` counts packets as numbered by the payload's GPS module.

### Async Stdout Iteration (line 101)

```python
    async for line in proc.stdout:
```
**Line 101:** Async iterator over subprocess stdout. Each `line` is a `bytes` object (subprocess stdout is opened in binary mode by `asyncio.subprocess.PIPE`). The loop blocks asynchronously — other asyncio tasks (if any) can proceed while waiting for the next line. The loop terminates when stdout is closed (subprocess exits) or the task is cancelled.

```python
        line_str = line.decode("utf-8", errors="replace").strip()
```
**Line 102:** Decodes the bytes to string. `errors="replace"` means any non-UTF-8 byte sequences become `�` (U+FFFD) — this prevents crashes on binary garbage while still allowing the rest of the line to be inspected. `.strip()` removes trailing newline and any leading/trailing whitespace.

### Pass-Through Logic (lines 104–108)

```python
        # Pass through RX status lines
        if not line_str.startswith("[PktRx]"):
            if any(kw in line_str for kw in ("Opening", "MHz", "Progress", "DONE", "FO")):
                print(f"  [RX] {line_str}", flush=True)
            continue
```

**Lines 105–108:** Two-tier filter:

**Tier 1: `startswith("[PktRx]")`** — All real packet output from `pkt_simple_rx.py` starts with this prefix. If a line does NOT start with `[PktRx]`, it's a status/metadata line.

**Tier 2: Keyword filter** — From the non-PktRx lines, only pass through those containing any of these keywords:

| Keyword | Source | When it appears |
|---|---|---|
| `Opening` | `[PktRx] Opening...` (line 385 of pkt_simple_rx.py) | SDR initialization |
| `MHz` | `[PktRx] 915.000 MHz, LNA=32, VGA=40` (line 392) | Post-init confirmation |
| `Progress` | `[PktRx] Progress: Ns, M good packets` (line 426) | Periodic status |
| `DONE` | `[PktRx] DONE. Ns, M good packets.` (line 434) | Clean exit summary |
| `FO` | Not actually produced as a status line — but matches any line containing "FO" | Defensive catch-all for frequency offset info |

Lines matching these keywords are printed with an `[RX]` prefix (instead of `[Bridge]`), indicating the message originated from the RX subprocess, not the bridge itself.

Non-PktRx lines that don't match any keyword are silently discarded — this includes progress output from the SDR read loop, potential error messages without these keywords, etc.

### Payload Extraction (lines 110–113)

```python
        # Extract payload
        payload = extract_payload(line_str)
        if payload is None:
            continue
```

Calls `extract_payload()` (see §6). If the regex didn't match or hex decoding failed, silently skip. This handles:
- Corrupted lines
- Lines where the RX printed something inside `[PktRx]` tags that isn't a packet
- Race conditions where a partial line was flushed

### Frame Unpacking (lines 115–124)

```python
        # Unpack binary frame
        try:
            frame = unpack_frame(payload)
        except (ValueError, TypeError) as exc:
            print(f"  [Bridge] unpack error ({len(payload)}B): {exc}", flush=True)
            continue
```

**Lines 116–120:** Calls `unpack_frame()` from `telemetry/packet_format.py`. This function:

1. Checks `len(data) < 1` → returns `None` if empty.
2. Reads `data[0]` as the frame type byte.
3. Looks up the parser class in `_PARSERS` dict.
4. Calls `parser.unpack(data)` — for `PositionFrame`, this:
   - Validates length exactly equals `_POS_SIZE` (38 bytes).
   - Unpacks via `struct.unpack("<B H d d f f B B B f f")`.
   - Validates the type byte is `0x01`.
   - Returns a `PositionFrame` instance.

Errors caught:
- `ValueError`: Wrong size, wrong type byte, or struct unpack failure.
- `TypeError`: If `parser` is `None` (unknown frame type) and `.unpack()` is called on `None` — but `unpack_frame()` returns `None` first, so this should not happen in practice. It's a defensive catch.

Error message includes the payload size in bytes, which is useful for debugging (e.g., "packet is 36B instead of 38B").

```python
        if frame is None or not isinstance(frame, PositionFrame):
            print(f"  [Bridge] unknown frame type, {len(payload)}B", flush=True)
            continue
```

**Lines 122–124:** `unpack_frame()` returns `None` for unknown frame types (anything other than `0x01`). This handles:
- Future frame types (motion 0x02, environment 0x03, power 0x04)
- Corrupt type bytes
- Empty payloads

Only `PositionFrame` instances proceed to dashboard POST.

### Conversion & POST (lines 126–140)

```python
        # Convert to dashboard JSON
        packet = frame_to_dashboard(frame)
```

**Line 127:** Converts the `PositionFrame` to a dict (see §7). The variable is named `packet` to match the dashboard's terminology.

```python
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
```

**Lines 130–140:** HTTP POST with error handling:

| Aspect | Detail |
|---|---|
| **Method** | `POST` |
| **URL** | `dashboard_url` (default `http://localhost:8000/api/packet`) |
| **Payload** | `{"data": <packet dict>}` — the dashboard expects a `data` wrapper key |
| **JSON serialization** | Handled automatically by `session.post(json=...)` — calls `json.dumps()` internally |
| **Timeout** | 5.0 seconds — per-request timeout, not cumulative. Prevents the async loop from blocking indefinitely on a hung dashboard |
| **ConnectionError** | Dashboard unreachable (no server listening, wrong host/port, network down) → `ok = False` |
| **Timeout** | Dashboard accepted the connection but didn't respond within 5 seconds → `ok = False` |
| **Success** | HTTP 200 → `ok = True` |
| **Non-200** | HTTP 4xx/5xx → `ok = False` — the bridge does NOT retry, does NOT log the status code, and does NOT buffer for later replay |

**Design limitation:** Non-200 responses lose the status code information. If the dashboard returns 400 (bad request) or 500 (internal error), the bridge only knows "not OK" — it can't tell whether the payload was malformed or the server crashed. The packet is dropped.

### Status Reporting (lines 142–150)

```python
        packets_sent += 1
        status = "✓" if ok else "✗"
        print(
            f"  [Bridge] #{packets_sent} {status}  "
            f"pos={frame.lat:.5f},{frame.lon:.5f}  "
            f"alt={frame.alt_m:.1f}m  sats={frame.sats}  "
            f"fix={frame.fix_type}",
            flush=True,
        )
```

**Lines 142–150:** One-line per-packet summary printed to stdout:

- `[Bridge]` — prefix identifying the bridge as the source
- `#N` — bridge's own sent-packet counter
- `✓` or `✗` — visual indicator of POST success/failure
- `pos=lat,lon` — coordinates to 5 decimal places (~1.1m precision at the equator)
- `alt=X.Xm` — altitude to 1 decimal
- `sats=N` — satellite count
- `fix=type` — GPS fix quality

`flush=True` ensures the output appears immediately even when stdout is line-buffered or piped. Important for real-time monitoring.

---

## 9. `main_async()` (lines 153–216)

### Argument Parsing (lines 153–162)

```python
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
```

| Argument | Type | Default | Passed to subprocess? | Notes |
|---|---|---|---|---|
| `--freq` | `float` | `915000000.0` | Yes, as `--freq 915000000` | Center frequency in Hz. `915e6` = 915 MHz ISM band |
| `--lna` | `float` | `32` | Yes, as `--lna 32` | HackRF LNA gain in dB |
| `--vga` | `float` | `40` | Yes, as `--vga 40` | HackRF VGA gain in dB |
| `--amp` | `store_true` | `True` | Yes, as `--amp` (boolean flag) | HackRF amplifier enable. Default `True` is unusual — normally `store_true` defaults to `False` |
| `--serial` | `str` | `None` | Yes, if provided | HackRF serial number for multi-SDR setups |
| `--dashboard` | `str` | `DASHBOARD_URL` | No — used locally | Override the dashboard endpoint URL |

**`--amp` default oddity (line 158):** `action="store_true", default=True` means the flag is **always True**. The user cannot disable the amp — passing `--amp` keeps it True, and not passing it also keeps it True. There is no `--no-amp` counterpart. This looks like a convenience default for a setup where the amp is always on, but it makes the CLI argument essentially non-functional.

```python
    dashboard_url = args.dashboard
```
**Line 164:** Local alias — avoids `args.dashboard` everywhere.

### RX Script Location (lines 166–170)

```python
    # Locate pkt_simple_rx.py
    rx_script = _HAB_ROOT / "rf" / "packet" / "src" / "pkt_simple_rx.py"
    if not rx_script.exists():
        print(f"ERROR: RX script not found at {rx_script}")
        sys.exit(1)
```

**Lines 167–170:** Constructs the path `<HAB_ROOT>/rf/packet/src/pkt_simple_rx.py` using the same `_HAB_ROOT` from line 34. This imposes a specific directory layout:

```
hab/                          ← _HAB_ROOT
├── rf/
│   └── packet/
│       ├── gps_bridge.py     ← this file
│       └── src/
│           └── pkt_simple_rx.py  ← the subprocess target
└── payload/
    └── telemetry/
        └── packet_format.py  ← imported module
```

The `.exists()` check provides a clear error message before launching the subprocess, rather than letting `asyncio.create_subprocess_exec` fail with a confusing `FileNotFoundError`.

### Command Construction (lines 172–184)

```python
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
```

**Lines 172–184:** Constructs the argument list for `create_subprocess_exec`:

| Position | Argument | Value | Why |
|---|---|---|---|
| 0 | Python binary | `/opt/homebrew/bin/python3.14` | Hardcoded interpreter path |
| 1 | Script | Full path to `pkt_simple_rx.py` | Resolved via `_HAB_ROOT` |
| 2–3 | `--freq` | `int(float)` conversion (e.g., `915000000`) | `float` → `int` because the RX script expects integer Hz |
| 4–5 | `--duration` | `"0"` | **Critical:** `0` means "run until killed" (line 402 of pkt_simple_rx.py: `while self.duration == 0 or ...`). This makes the subprocess a persistent daemon |
| 6–7 | `--lna` | `int(float)` conversion | Gain in dB |
| 8–9 | `--vga` | `int(float)` conversion | Gain in dB |
| 10 | `--amp` | (flag only) | Enables HackRF amp if `args.amp` is True |
| 11–12 | `--serial` | HackRF serial string | Only added if `args.serial` is not None |
| 13 | `--hex-output` | (flag only) | **Always appended.** This is what produces the `| <hex>` output format that `extract_payload()` depends on |

**`--duration "0"` semantics:** The RX script's main loop is `while self.duration == 0 or time.time() - start < self.duration`. When `duration` is 0, the first condition is always true → infinite loop. The bridge controls the subprocess lifecycle via signals.

**`--hex-output` is non-negotiable:** Line 184 unconditionally appends it. Without hex output, `pkt_simple_rx.py` would print decoded ASCII with `clean!r` and/or HELLO WORLD detection — formats that `extract_payload()` cannot parse. This is correct for the bridge's binary frame protocol.

### Subprocess Launch (lines 186–201)

```python
    print(f"[Bridge] Launching: {' '.join(cmd)}")
    print(f"[Bridge] Dashboard: {DASHBOARD_URL}")
```

**Lines 186–187:** Pre-launch informational output. Shows the full command (including the hardcoded Python path) and the dashboard URL being targeted.

```python
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
```

**Lines 189–201:** This is the most complex block in the file. Let's break it down:

#### Subprocess I/O Setup

- `stdout=asyncio.subprocess.PIPE` — captures stdout as an async stream readable via `async for`
- `stderr=asyncio.subprocess.STDOUT` — **redirects stderr to stdout**. This means all error messages from the RX script (tracebacks, SoapySDR errors, etc.) appear intermixed with packet output and flow through the same `proc.stdout` stream. The bridge's `read_rx_stdout()` will see them and (if they don't start with `[PktRx]` and don't match the keyword filter) silently discard them.
- No `stdin` pipe — the subprocess gets the parent's stdin (usually the terminal), but it doesn't read from it.

#### Environment Construction

The `env` parameter replaces the subprocess's entire environment. The pattern:

```python
env={
    **os.environ,           # copy all parent process env vars
    "PYTHONPATH": "..."     # override/add PYTHONPATH
}
```

**Line 195:** `**os.environ` — spreads all parent environment variables into the new dict. This preserves `PATH`, `HOME`, `DYLD_LIBRARY_PATH` (critical for SoapySDR .dylib loading on macOS), etc.

**Lines 196–198:** Constructs `PYTHONPATH` with three entries joined by `:`:

1. `/opt/homebrew/lib/python3.14/site-packages` — **Hardcoded.** Where Homebrew installs Python packages (numpy, SoapySDR, gnuradio, requests). This is the Apple Silicon Mac path; on x86 it would be `/usr/local/lib/python3.14/site-packages`.

2. `<HAB_ROOT>/rf/packet/src` — Where `pkt_simple_rx.py` lives. Allows the script to import sibling modules if needed.

3. `<HAB_ROOT>/rf/packet` — The parent directory. Allows imports like `from src.pkt_simple_rx import ...` or access to package-level modules.

**Why override PYTHONPATH instead of using the parent's?** The parent process might have its own `PYTHONPATH` that could interfere. By constructing it from scratch, the bridge guarantees the subprocess can find its dependencies. However, this is **fragile** — if the Homebrew site-packages path changes (Python upgrade, different package manager), the subprocess won't find numpy/SoapySDR/gnuradio.

**Why is `stderr=asyncio.subprocess.STDOUT` potentially problematic?** Error messages (SDR initialization failures, import errors, tracebacks) are mixed into the same stream as packet data. The pass-through filter in `read_rx_stdout()` only prints lines containing specific keywords. A critical SoapySDR error like `"ERROR: Failed to open HackRF"` would likely NOT match any keyword and be silently swallowed, making debugging difficult.

### Lifecycle Management (lines 203–216)

```python
    print(f"[Bridge] RX PID {proc.pid} — Ctrl-C to stop")
```

**Line 203:** Prints the subprocess PID — useful for manual `kill` if the bridge itself hangs or is backgrounded.

```python
    try:
        await read_rx_stdout(proc, dashboard_url)
    except asyncio.CancelledError:
        pass
    finally:
```

**Lines 205–209:** The core execution block:

- **`await read_rx_stdout(...)`** — blocks until the subprocess stdout closes (subprocess exits) or an exception occurs.
- **`asyncio.CancelledError`** — raised when the asyncio task is cancelled. This happens when:
  - `KeyboardInterrupt` (Ctrl-C) is caught by `asyncio.run()` in `main()` (line 221) and propagates as a `CancelledError` into the event loop.
  - The task is explicitly cancelled by another coroutine.
  - The `catch` + `pass` pattern means the cancellation is acknowledged but execution continues to the `finally` block for cleanup.
- **`finally`** — guaranteed to run regardless of normal exit, cancellation, or unhandled exception in `read_rx_stdout`.

#### The Terminate/Kill Sequence (lines 210–216)

```python
        print("[Bridge] Stopping RX...")
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except (ProcessLookupError, asyncio.TimeoutError):
            proc.kill()
        print("[Bridge] Stopped.")
```

This implements a **graceful-then-forceful** shutdown sequence:

```
                    ┌──────────────────┐
                    │  Stop requested   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ proc.terminate()  │  ← SIGTERM
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ await proc.wait() │  ← 5.0 second deadline
                    │   (timeout=5.0)  │
                    └───┬─────────┬────┘
                        │         │
                   exits in    doesn't exit
                   time        within 5s
                        │         │
              ┌─────────▼──┐  ┌───▼──────────────┐
              │ DONE ✓     │  │ proc.kill()       │ ← SIGKILL
              └────────────┘  │ (ProcessLookupError│
                              │  or TimeoutError) │
                              └───────────────────┘
```

**`proc.terminate()`** sends `SIGTERM` (signal 15). This is the "please shut down" signal. `pkt_simple_rx.py` handles `KeyboardInterrupt` (which is SIGINT, not SIGTERM), but SIGTERM will still terminate the Python process — it just won't trigger the `except KeyboardInterrupt` block, so the SDR stream cleanup (`deactivateStream`/`closeStream`) in the RX script may not execute.

**`await asyncio.wait_for(proc.wait(), timeout=5.0)`** waits for the process to exit, with a 5-second deadline. If the process exits cleanly within 5 seconds, `proc.wait()` returns the exit code. If 5 seconds pass, `asyncio.TimeoutError` is raised.

**`except (ProcessLookupError, asyncio.TimeoutError):`** catches two failure modes:

1. **`ProcessLookupError`:** The process has already exited between the `terminate()` call and the `wait()` call. This is a race condition — possible when the RX process was already shutting down or crashed. `proc.kill()` on an already-dead process also raises `ProcessLookupError`, but since it's inside the same `except` block, it's silently caught. Net effect: process is already dead, nothing more to do.

2. **`asyncio.TimeoutError`:** The process didn't exit within 5 seconds of SIGTERM. This means the process is hung (blocked on SDR I/O, stuck in a loop, etc.). `proc.kill()` sends `SIGKILL` (signal 9) — the OS forcibly terminates the process with no chance for cleanup.

**Edge case not handled:** `proc.kill()` can also raise `ProcessLookupError` if the process dies between the `wait_for` timeout and the `kill()` call. This would be an unhandled exception escaping the `finally` block, aborting the bridge with a traceback. In practice this window is extremely narrow (microseconds) but theoretically possible.

**`print("[Bridge] Stopped.")`** — confirmation that cleanup completed, printed regardless of which path was taken.

---

## 10. `main()` / `__main__` Guard (lines 219–227)

```python
def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass
```

**Lines 219–223:** The synchronous entry point. `asyncio.run()` creates a new event loop, runs `main_async()` to completion, and closes the loop.

**KeyboardInterrupt handling:** When the user presses Ctrl-C, the following cascade occurs:

1. Python receives `SIGINT`.
2. `asyncio.run()` translates this to a `CancelledError` thrown into the running task.
3. `main_async()` catches `CancelledError` → `pass` → enters `finally` → graceful shutdown.
4. After `main_async()` returns, `asyncio.run()` does its own cleanup.

However, there is an edge case: if a `KeyboardInterrupt` arrives **during** `asyncio.run()`'s event-loop teardown (after `main_async()` has returned but before the loop is fully closed), it would be raised here and caught by the outer `except KeyboardInterrupt: pass` — preventing an ugly traceback on exit.

```python
if __name__ == "__main__":
    main()
```

**Lines 226–227:** Standard Python idiom. The module can be imported (for testing, documentation generation, etc.) without executing `main()`. When run directly (`python gps_bridge.py`), `main()` is called.

---

## 11. Implicit Assumptions & Fragilities

### File System Layout

| Assumption | Location in Code | What Breaks |
|---|---|---|
| `gps_bridge.py` is at `<root>/rf/packet/` | Line 34 (`parent.parent.parent`) | Moving the file changes `_HAB_ROOT`, breaking the import and RX script path |
| `pkt_simple_rx.py` is at `<root>/rf/packet/src/` | Line 167 | The subprocess launch fails with "RX script not found" |
| `packet_format.py` is at `<root>/payload/telemetry/` | Line 35 (`sys.path`) | `ImportError: cannot import name 'PositionFrame'` |
| The working directory doesn't matter | Line 34 uses `__file__.resolve()` | The resolve() call makes this assumption true — relative execution doesn't break path resolution |

### Platform & Environment

| Assumption | Location in Code | What Breaks |
|---|---|---|
| macOS on Apple Silicon (arm64) | Line 44 (`/opt/homebrew/bin/python3.14`) | Fails on Intel Mac (`/usr/local/...`), Linux, Windows |
| Homebrew Python 3.14 specifically | Line 44 | Fails on Python 3.13, 3.12, or any other version |
| Homebrew site-packages path | Lines 196–197 (`/opt/homebrew/lib/python3.14/site-packages`) | Subprocess can't import numpy, SoapySDR, gnuradio |
| HackRF with specific serial | `--serial` CLI arg | If omitted and multiple HackRFs are connected, SoapySDR may pick the wrong device |
| Dashboard running on localhost:8000 | Line 43 (`DASHBOARD_URL`) | POSTs fail silently — packets are lost with only a `✗` in stdout |
| `requests` library installed | Line 27 (`import requests`) | Early exit with helpful message, so this is handled gracefully |

### Runtime Behavior

| Assumption | Location in Code | What Breaks |
|---|---|---|
| `pkt_simple_rx.py` uses `--hex-output` format | Line 184 (always appended) | If the RX script's hex format changes, `extract_payload` regex breaks |
| `[PktRx]` prefix is stable | Line 62 (regex) | If the prefix changes, no packets are extracted |
| Subprocess responds to SIGTERM within 5 seconds | Line 214 (`timeout=5.0`) | `proc.kill()` is sent — loses SDR cleanup in the RX script |
| No other async tasks compete for the event loop | Line 206 (`await read_rx_stdout`) | The bridge has only one coroutine — fine, but adding concurrent tasks could create cancellation ordering issues |
| PositionFrame is always exactly 38 bytes | `packet_format.py` `_POS_SIZE` | `unpack_frame()` raises `ValueError` → printed as "unpack error" and skipped |

### Data Integrity

| Assumption | Location in Code | What Breaks |
|---|---|---|
| Dashboard timestamp is bridge time, not GPS time | Line 78 (`time.gmtime()`) | Timestamps are lagged by decode+network latency; no date information |
| Non-200 responses are discarded silently | Line 140 (`ok = False`) | Lost packets, no retry, no status code logged |
| Packet sequence from RX is monotonic and gap-free | N/A | The bridge doesn't track `frame.seq` gaps — lost/corrupt packets are invisible |
| Only `PositionFrame` (0x01) matters | Line 122 (`isinstance(frame, PositionFrame)`) | Future frame types (motion, environment, power) are logged and skipped |

---

## 12. Data-Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        gps_bridge.py                              │
│                                                                   │
│  main()                                                           │
│    └─ asyncio.run(main_async())                                   │
│         │                                                         │
│         ├─ argparse (--freq, --lna, --vga, --amp, --serial)      │
│         │                                                         │
│         ├─ asyncio.create_subprocess_exec(                        │
│         │      "/opt/homebrew/bin/python3.14",                    │
│         │      "pkt_simple_rx.py --hex-output ...",               │
│         │      stdout=PIPE, stderr=STDOUT,                        │
│         │      env={PYTHONPATH=...}                               │
│         │  )                                                      │
│         │       │                                                 │
│         │       ▼                                                 │
│         │  ┌─────────────────────────────────┐                    │
│         │  │     pkt_simple_rx.py             │                    │
│         │  │  HackRF → SoapySDR → BPSK decode │                    │
│         │  │  stdout: [PktRx] #N ... | <hex>  │                    │
│         │  └────────────┬────────────────────┘                    │
│         │               │ stdout (async pipe)                     │
│         │               ▼                                         │
│         └─► read_rx_stdout(proc, dashboard_url)                   │
│               │                                                   │
│               ├─ line.decode("utf-8") → str                       │
│               │                                                   │
│               ├─ Pass-through non-PktRx status lines              │
│               │  (Opening, MHz, Progress, DONE, FO)               │
│               │                                                   │
│               ├─ extract_payload(line_str)                        │
│               │  regex: \[PktRx\]\s+#\d+.*?\|\s*([0-9a-fA-F]+)   │
│               │  bytes.fromhex() → raw bytes                      │
│               │                                                   │
│               ├─ unpack_frame(payload)                            │
│               │  ├─ Read type byte (data[0])                      │
│               │  ├─ 0x01 → PositionFrame.unpack()                 │
│               │  │    struct: <B H d d f f B B B f f              │
│               │  │    (38 bytes → lat, lon, alt, agl, etc.)       │
│               │  └─ Other → None (skipped)                        │
│               │                                                   │
│               ├─ frame_to_dashboard(frame) → dict                 │
│               │  {v, id, mid, seq, t, type, lat, lon,             │
│               │   alt_m, agl_m, fix, fix_type, sats,              │
│               │   hdop, vdop}                                     │
│               │                                                   │
│               └─ session.post(dashboard_url,                      │
│                    json={"data": packet}, timeout=5.0)             │
│                         │                                         │
│                         ▼                                         │
│              ┌────────────────────────────┐                       │
│              │   Dashboard Server          │                       │
│              │   http://localhost:8000     │                       │
│              │   POST /api/packet          │                       │
│              └────────────────────────────┘                       │
│                                                                   │
│  Shutdown:                                                        │
│    1. KeyboardInterrupt → CancelledError                          │
│    2. finally: proc.terminate() → wait 5s → proc.kill()          │
└──────────────────────────────────────────────────────────────────┘
```

---

## Summary of Findings

**Architecture:** The bridge is a single-responsibility process supervisor. It correctly decouples the SDR receive pipeline (`pkt_simple_rx.py`) from the dashboard ingestion, allowing each to be developed, tested, and debugged independently. The async design handles subprocess I/O without blocking.

**Strengths:**
- Clean separation of concerns (subprocess management, payload extraction, frame unpacking, HTTP delivery).
- Defensive error handling at every stage — hex decode failures, struct unpack errors, connection errors, timeouts.
- Graceful shutdown with terminate→wait→kill escalation.
- Distinct log prefixes (`[RX]` vs `[Bridge]`) for traceability.
- Documented CLI usage in the module docstring.

**Critical Fragilities:**
1. **Hardcoded paths:** `/opt/homebrew/bin/python3.14` and `/opt/homebrew/lib/python3.14/site-packages` tie the entire pipeline to a specific Python installation on Apple Silicon Macs. Moving to any other machine requires source edits.
2. **Stale comment block (lines 46–53):** Describes an old output format (`| 'raw bytes here'`) that is no longer used, while the actual `extract_payload()` implementation correctly handles hex output. This could confuse maintainers.
3. **Silent error swallowing:** Non-PktRx lines that don't match the pass-through keywords (including SDR errors) are silently dropped. A failing SDR initialization would produce no visible output.
4. **Timestamp:** Uses bridge wall-clock time instead of GPS frame time, with no date component.
5. **No retry/queue for failed POSTs:** If the dashboard is down, packets are lost permanently.
6. **`signal` import is unused,** `json` import is unused (though harmless).
