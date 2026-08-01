# Phase 2 Review — Codex Findings

## P1 (Critical)

### 1. Nyquist collision at default sample rate
**File:** `payload/tx/combined_tx.py`
**Issue:** At 4 MS/s with ±2 MHz offset, the two streams alias onto each other (`+2 MHz` = `-2 MHz` at π rad/sample in discrete time).
**Status:** Warnings added by Codex. Use `--sample-rate 6000000` (or higher) for actual operation.

### 2. Composite still unreachable from dashboard
**File:** `ground/dashboard/server/main.py`
**Issue:** `create_ws_router` still receives `SdrManager`. The new `ReceiverManager`/`combined_rx.py` is only reachable via REST.
**Status:** Unchanged from Phase 1.

## P2 (Should Fix)

### 3. Decoder overlap gap (carried over from P1)
**File:** `ground/rx/combined_rx.py`
**Issue:** BPSK packets straddling HackRF read boundaries split and lost.
**Status:** Unchanged.

### 4. Blocking POST in SDR loop (carried over from P1)
**File:** `ground/rx/combined_rx.py:385-389`
**Issue:** Synchronous `requests.post()` stalls the HackRF read loop.
**Status:** Unchanged.

### 5. Hardcoded dashboard port (carried over from P1)
**File:** `ground/dashboard/server/receiver_manager.py:134`
**Issue:** Always posts to port 8000, ignoring `HAB_PORT`.
**Status:** Unchanged.

### 6. Packet tests broken after reorg (carried over from P1)
**Files:** `dev/packet/packet/test/test_layer{1,2,3}_simple.py`
**Issue:** Import removed `pkt_simple_rx.py`.
**Status:** Unchanged.

### 7. OTA test paths broken (carried over from P1)
**File:** `dev/gui/python/test_ota.sh:10`
**Issue:** References `rf/` which no longer exists at that relative level.
**Status:** Unchanged.

## Phase 2-Specific

### 8. GPS serial blocking read
**File:** `payload/tx/combined_tx.py`
**Issue:** Serial read in the main loop can block, stalling SDR writes. Should use non-blocking or timeout reads.
**Status:** New finding.

### 9. DVB-S2 pipe read could stall
**File:** `payload/tx/combined_tx.py`
**Issue:** Reading from the DVB-S2 subprocess pipe is blocking with no timeout fallback.
**Status:** New finding.

### 10. Rate limiting not yet implemented
**File:** `payload/tx/combined_tx.py`
**Issue:** Spec requested error rate-limiting; not present in initial implementation.
**Status:** New finding.
