# Phase 1 Review — Codex Findings

## P1 (Critical)

### 1. Identical channels at default offset/sample-rate
**File:** `ground/rx/combined_rx.py:305-311`
**Issue:** With `--offset 2e6` and `--sample-rate 4e6`, the oscillator is `exp(jπn)`, which equals its own conjugate. After `[::2]` decimation, `dvbs2` and `bpsk` are byte-for-byte identical.
**Fix:** Add anti-alias filtering per branch before decimation, or ensure the offset provides adequate channel separation.

### 2. Composite receiver unreachable from dashboard controls
**File:** `ground/dashboard/server/main.py:73`
**Issue:** `create_ws_router` still receives `SdrManager`, so clicking "Start" launches the old `sdr_rx_worker.py`. The new `ReceiverManager`/`combined_rx.py` is wired only to REST routes.
**Fix:** Route WebSocket lifecycle commands (`cmd:sdr:start`) to the composite pipeline.

## P2 (Should Fix)

### 3. Decoder overlap gap
**File:** `ground/rx/combined_rx.py:369-371`
**Issue:** Packets straddling HackRF read boundaries are split and discarded.
**Fix:** Preserve one max-packet span between chunks with duplicate suppression.

### 4. Blocking POST in SDR read loop
**File:** `ground/rx/combined_rx.py:337-340`
**Issue:** Synchronous `requests.post()` (up to 2s timeout) stalls the HackRF read loop, blocking both DVB-S2 FIFO writes and BPSK decode.
**Fix:** Offload HTTP POSTs to a background worker thread.

### 5. Hardcoded dashboard port
**File:** `ground/dashboard/server/receiver_manager.py:134`
**Issue:** Always POSTs telemetry to port `8000`, regardless of configured `HAB_PORT`.
**Fix:** Construct POST URL from actual server configuration.

### 6. Packet tests broken after reorg
**Files:** `dev/packet/packet/test/test_layer{1,2,3}_simple.py`
**Issue:** Tests still import from removed `pkt_simple_rx.py` and fail with `ModuleNotFoundError`.
**Fix:** Point imports at `ground/rx/demod.py`.

### 7. OTA test path broken
**File:** `dev/gui/python/test_ota.sh:10`
**Issue:** Script lives under `dev/` but references `rf/` (no longer at that relative level). `set -e` means immediate exit.
**Fix:** Update path references to `dev/setup_env.sh` and relocated DVB-S2 directory.
