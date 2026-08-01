# Phase 4 Review — Final Findings

## P2 (Should Fix)

### 1. Overlap too small for full packet
**File:** `ground/rx/combined_rx.py:40`
**Issue:** A 38-byte PositionFrame = 624 symbols = 12,480 samples at SPS=20. We only retain 2,000 samples. Packets more than 2,000 samples before a chunk boundary are still lost.
**Fix:** Increase overlap to ~15,000 samples (one full max packet + filter transient).

### 2. Receiver state not updated on subprocess exit
**File:** `ground/dashboard/server/receiver_manager.py:161-162`
**Issue:** When `combined_rx.py` exits (hardware fails, restart budget exhausted), the log shows the return code but `ReceiverManager` stays in RUNNING state. The status task continues reporting an active receiver.
**Fix:** Transition to ERROR or IDLE and broadcast updated status.

### 3. Missing `requests` dependency
**File:** `ground/rx/combined_rx.py:22`
**Issue:** `requests` is imported but not in `requirements.txt`. A clean dashboard install won't have it.
**Fix:** Add `requests` to `ground/dashboard/server/requirements.txt`.

### 4. TS rate doesn't adapt to MODCOD
**File:** `payload/tx/combined_tx.py:161-162`
**Issue:** TS rate formula assumes QPSK 1/2. If user picks a different modcod or `--no-pilots`, the calculation is wrong.
**Fix:** Reject non-default modes unless `--tsrate` is explicitly provided, or calculate tsrate from the actual parameters.
