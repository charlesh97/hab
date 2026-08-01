# Phase 1+2 — Consolidated Review Findings & Fix Guidance

## P1 (Critical)

### 1. Anti-alias filtering before decimation
**Files:** `ground/rx/combined_rx.py`, `payload/tx/combined_tx.py`
**Original issue:** At 4 MS/s with ±2 MHz offset, the oscillator is `exp(jπn)` which equals its conjugate; after decimation the two channels are identical.
**Status:** ✅ **Fixed.** Codex applied anti-alias filters in `combined_rx.py` during Phase 2. Both scripts now warn if sample rate ≤ 2× offset.
**Fix applied:** Low-pass filters per branch before decimation, plus runtime warning when Nyquist collision is imminent.

### 2. Composite receiver unreachable from dashboard
**File:** `ground/dashboard/server/main.py:73`
**Issue:** `create_ws_router()` still receives the old `SdrManager`. When the user clicks Start, the dashboard sends `cmd:sdr:start` which launches `sdr_rx_worker.py` instead of `combined_rx.py`. The new `ReceiverManager` is only wired to REST routes.
**Fix:** Either:
  a) Replace `SdrManager` with `ReceiverManager` in the `create_ws_router()` call in `main.py`, or
  b) Have `SdrManager._start_receiver()` delegate to `ReceiverManager._start_receiver()` instead of launching `sdr_rx_worker.py` directly.
  
  The cleanest approach: pass both `ws_manager` and `receiver_manager` to `create_ws_router`, and route `cmd:sdr:start` / `cmd:sdr:stop` through the `ReceiverManager` for the composite RX path.

---

## P2 (Should Fix)

### 3. Decoder overlap gap
**File:** `ground/rx/combined_rx.py`
**Issue:** Each call to `PacketDecoder.decode()` processes a fixed-size chunk (524288 samples). If a BPSK packet's preamble starts near the end of one chunk and its payload/CRC falls in the next chunk, neither chunk can decode it — the packet is silently lost.
**Fix:** Retain at least one maximum-packet span of samples between consecutive chunk boundaries. On each iteration, prepend the previous chunk's tail (e.g. last 2000 samples, enough for one full 38-byte PositionFrame at SPS=20) to the current chunk before calling `decode()`. Suppress duplicate packets by tracking decoded sequence numbers and skipping already-seen ones.

### 4. Blocking POST in SDR read loop
**File:** `ground/rx/combined_rx.py:385-389`
**Issue:** `self.http.post()` is synchronous and can block for up to 2 seconds per call. The SDR read loop runs every ~131 ms at 4 MS/s, so a single slow POST stalls both DVB-S2 FIFO writes and BPSK decode, causing HackRF buffer overruns.
**Fix:** Replace the synchronous POST with a background worker:
  - Create a `threading.Thread` (or `concurrent.futures.ThreadPoolExecutor`) that reads from a `queue.Queue`.
  - In the main loop, push decoded frames onto the queue (non-blocking, with a max size to bound memory).
  - The background thread pops frames and POSTs them, retrying on failure.
  - Use `queue.put_nowait()` so the main loop never waits.

### 5. Hardcoded dashboard port
**File:** `ground/dashboard/server/receiver_manager.py:134`
**Issue:** `combined_rx.py` is launched with `--dashboard http://localhost:8000/api/packet`. If the server runs on a non-default port (e.g. `HAB_PORT=9000`), every decoded packet POST goes to port 8000 and vanishes.
**Fix:** In `receiver_manager.py:_start_receiver()`, construct the dashboard URL from the actual server configuration:
  ```python
  server_port = self._config.server_port if hasattr(self._config, 'server_port') else 8000
  dashboard_url = f"http://localhost:{server_port}/api/packet"
  cmd.extend(["--dashboard", dashboard_url])
  ```
  Ensure `ReceiverConfig` has a `server_port: int = 8000` field.

### 6. Packet tests broken after reorg
**Files:** `dev/packet/packet/test/test_layer{1,2,3}_simple.py`
**Issue:** These tests import `pkt_simple_rx` from the old path. After the reorg, `pkt_simple_rx.py` moved to `ground/rx/demod.py`.
**Fix:** Update the import in each test file:
  ```python
  # Old: from pkt_simple_rx import ...
  # New: import sys; sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent / "ground" / "rx"))
  from demod import PacketDecoder
  ```
  Or add a compatibility shim `ground/rx/pkt_simple_rx.py` that re-exports from `demod`.

### 7. OTA test paths broken
**File:** `dev/gui/python/test_ota.sh:10`
**Issue:** `SCRIPT_DIR` resolves to `dev/gui/python/`, so `../../rf` → `dev/rf/` which doesn't exist. The script uses `set -e` so it exits immediately on the first failure.
**Fix:** Update the script's path calculation to find the actual `dev/` root:
  ```bash
  HAB_DEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  source "$HAB_DEV_DIR/setup_env.sh"
  ```
  Also update all references from `"$HAB_DEV_DIR/rf/..."` to `"$HAB_DEV_DIR/dev/..."` for DVB-S2 binary paths.

---

## Phase 2-Specific (P2)

### 8. GPS serial blocking read
**File:** `payload/tx/combined_tx.py`
**Issue:** `serial.readline()` is a blocking call with no timeout. If the GPS module goes silent (no fix, no data), the main loop hangs indefinitely, stopping all SDR writes.
**Fix:** Use `serial.Serial(timeout=1.0)` when opening the port. Wrap the read in a non-blocking loop:
  ```python
  line = None
  if gps_serial.in_waiting:
      line = gps_serial.readline()
  ```
  Or rely on the timeout to return empty strings. A lost GPS sentence is not a critical error — the BPSK modulator should fall back to the last known position and continue transmitting.

### 9. DVB-S2 pipe read could stall
**File:** `payload/tx/combined_tx.py`
**Issue:** Reading IQ samples from the DVB-S2 subprocess pipe (`os.read()`) blocks if no data is available. There's no timeout or non-blocking fallback.
**Fix:** Use either:
  a) `os.set_blocking(pipe_fd, False)` and handle `BlockingIOError` by padding with zeros and retrying next loop iteration, or
  b) `select.select([pipe_fd], [], [], timeout=0.01)` before each read to check availability.
  
  If no DVB-S2 data is available, pad the DVB-S2 channel with zeros (maintains phase coherence in the mix) and continue with whatever BPSK data is ready.

### 10. Error rate-limiting not implemented
**File:** `payload/tx/combined_tx.py`
**Issue:** The Phase 2 spec called for rate-limited error logging (max 1 per 10 seconds per error type), but the initial implementation logs every error unconditionally, which can flood stderr on the Rock 2A's constrained storage.
**Fix:** Port the `RateLimitedLogger` class from `ground/rx/combined_rx.py` to the TX side. Same pattern:
  ```python
  class RateLimitedLogger:
      def __init__(self, interval: float = 10.0):
          self.interval = interval
          self._last_log: dict[str, float] = {}
      
      def warning(self, key: str, message: str, *args) -> None:
          now = time.monotonic()
          if now - self._last_log.get(key, -self.interval) >= self.interval:
              self._last_log[key] = now
              LOG.warning(message, *args)
  ```
  Instantiate once in `CompositeTransmitter.__init__()` and use for GPS errors, pipe stalls, SDR underflows, and POST failures.

---

## Summary of Changes to Make

| # | Priority | File | Change |
|---|---|---|---|
| 1 | P1 | `combined_rx.py`, `combined_tx.py` | ✅ **Already fixed** (anti-alias + warning) |
| 2 | **P1** | `main.py:73` | Wire `ReceiverManager` to dashboard WS commands |
| 3 | P2 | `combined_rx.py` | Add sample overlap between decode() calls |
| 4 | P2 | `combined_rx.py` | Move HTTP POST to background thread |
| 5 | P2 | `receiver_manager.py:134` | Use configured port for dashboard URL |
| 6 | P2 | `test_layer{1,2,3}_simple.py` | Point imports at `ground/rx/demod.py` |
| 7 | P2 | `test_ota.sh` | Fix `rf/` → `dev/` path resolution |
| 8 | P2 | `combined_tx.py` | Non-blocking GPS serial read with timeout |
| 9 | P2 | `combined_tx.py` | Non-blocking DVB-S2 pipe read with zero-pad fallback |
| 10 | P2 | `combined_tx.py` | Port `RateLimitedLogger` to TX side |
