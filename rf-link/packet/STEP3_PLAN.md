# Step 3: Long-Range Receiver Hardening — Implementation Plan

## Overview

Transform the current bench-tested link into an 18km-capable system with three
enhancements:

| # | Feature | Why for 18km | Effort |
|---|---------|-------------|--------|
| 2 | **Variable SPS / Symbol Rate** | 10× lower symbol rate = 10 dB more link margin | ~40 lines each in TX/RX |
| 3 | **Burst Shaping (Hann Ramps)** | Prevents spectral splatter, recovers ~3-6 dB effective TX power | ~15 lines in TX |
| 4 | **AGC + Continuous FO Tracking** | AGC handles 40+ dB signal variation; FO tracking prevents drift failure over minutes | ~40 lines in RX |

---

## Feature 2: Variable SPS / Symbol Rate

### Design

Both TX and RX currently hardcode `SPS = 20` and `FS = 2_000_000`. Make both
configurable via `--sps` and `--samp-rate` CLI arguments.

The sample rate determines absolute timing and bandwidth, SPS determines
symbol rate = FS / SPS.

```
FS=2e6, SPS=20  → 100 ksym/s  (current, ~11 dB margin @ 18 km)
FS=2e6, SPS=200 →  10 ksym/s  (~21 dB margin)
FS=2e6, SPS=400 →   5 ksym/s  (~24 dB margin)
FS=2e6, SPS=40  →  50 ksym/s  (~14 dB margin)
```

### TX Changes (`pkt_enhanced_tx.py`)

- Add `--sps` (int, default 20) and `--samp-rate` (float, default 2e6) args
- Replace module-level `SPS = 20` / `FS = 2_000_000` with function parameters
- `bpsk_modulate()`: accept `sps` parameter for pulse shaping taps
- `make_test_burst()`: accept `sps`, `fs` from caller
- `main()`: pass CLI values through the chain
- RRC tap generation uses variable sps

### RX Changes (`pkt_enhanced_rx.py`)

- Add `--sps` and `--samp-rate` args
- Replace module-level `SPS = 20` / `FS = 2000000`
- `rcc_taps()`: accept sps parameter
- `scan_frequency()`: accept fs parameter; sweep width scales with symbol rate
- `process_phase()`: accept sps parameter (controls which phases to try)
- `LiveReceiver.__init__()` and `.run()`: pass through SPS/FS
- `_process_chunk()`: rebuild RRC taps at current SPS

### Performance Note

At SPS=20, the receiver tries 20 decimation phases. At SPS=200, that would be
200 phases — 10× the processing per chunk. For real-time use at high SPS,
consider limiting to `min(SPS, 20)` phases (e.g., try phase 0, 10, 20, ...).
The deduplication step will still catch the right phase.

### Test Plan

- Verify codec round-trip at multiple SPS values (4, 20, 50, 100)
- Run Layer 2 loopback test at SPS=40, 100, 200 — confirm decode works
- (Hardware) Send with SPS=40 RX with SPS=40 — confirm decodes
- (Hardware) Send with SPS=20, RX with SPS=20 — confirm backward compat

---

## Feature 3: Burst Shaping (Hann Ramps)

### Design

Apply a Hann-window amplitude ramp to the beginning and end of each packet
burst (or each individual packet within a multi-packet burst). This smooths
the power-on/power-off transient, preventing spectral splatter.

The ramp length should be proportional to the filter length: ~50 symbols is
a good starting point.

### TX Changes (`pkt_enhanced_tx.py`)

Add after `bpsk_modulate` in the burst assembly pipeline:

```python
def apply_burst_shaping(waveform, sps, ramp_symbols=50):
    """Apply Hann ramp to burst start/end. waveform is complex64 list."""
    ramp_len = min(ramp_symbols * sps, len(waveform) // 4)
    if ramp_len < 2:
        return waveform  # too short to ramp
    ramp = np.hanning(2 * ramp_len)
    up = ramp[:ramp_len]
    down = ramp[ramp_len:]
    w = np.asarray(waveform)
    w[:ramp_len] = (w[:ramp_len].T * up).T if w.ndim > 1 else w[:ramp_len] * up
    w[-ramp_len:] = (w[-ramp_len:].T * down).T if w.ndim > 1 else w[-ramp_len:] * down
    return w.tolist()
```

Apply in `make_test_burst()` after building each packet waveform:

```python
shaped = apply_burst_shaping(waveform, sps)
```

### Why Hann over other windows

- Hann has zero endpoint discontinuity (starts/ends at exactly 0)
- Good sidelobe suppression (~32 dB down from peak)
- Simple: `np.hanning(2*N)` gives the perfect up/down ramp pair
- No signal energy lost at burst center; only the transitions are tapered

### RX Impact

The RX sync-word correlation process_phase() works on the filtered symbol
stream. Since the preamble is 192 bits long and the ramp is only ~50 symbols
(~400 samples at SPS=8), the preamble provides plenty of full-amplitude bits
for the sync word to lock onto. The correlation threshold (`mean + 2.5*std`)
is amplitude-independent.

**No RX code changes needed.**

### Test Plan

- Visual: capture shaped vs unshaped burst on spectrum analyzer or `np.fft.fft`
  to verify sidelobe reduction
- Layer 2 loopback: both shaped and unshaped bursts should decode identically
- Verify `apply_burst_shaping` is a no-op for impulse waveform (SPS=4, 1 symbol)

---

## Feature 4: AGC + Continuous FO Tracking

### 4a: Digital AGC

### Design

Add a software AGC stage right after sample acquisition. The AGC normalizes
the RMS amplitude of each chunk to a configurable target (default 0.3).

This has three benefits:
1. Sync-word correlation threshold becomes meaningful across wide signal ranges
2. Decoder hard decisions work at consistent levels
3. Fast energy detection can skip empty chunks (no-signal noise floor)

### RX Changes (`pkt_enhanced_rx.py`)

```python
def apply_digital_agc(samples, target_rms=0.3, min_rms=1e-3):
    """Normalize signal RMS to target. Returns (scaled, gain_db)."""
    rms = np.sqrt(np.mean(np.abs(samples)**2))
    if rms < min_rms:
        return samples * 0 + 1e-6j, -120.0  # noise floor
    gain = target_rms / rms
    return samples * gain, 20 * np.log10(gain)
```

Integrate at the top of `_process_chunk()`:

```python
def _process_chunk(self, samples):
    samples, gain_db = apply_digital_agc(samples, target_rms=self.agc_target)
    # ... rest of processing ...
```

Add `--agc-target` CLI arg (default 0.3).

### 4b: Continuous FO Tracking

### Design

Currently FO is estimated once (from the first chunk with energy) and never
updated. For a link that runs for minutes (HAB flight), oscillator drift will
cause the center frequency to walk off. The fix:

1. **Track the last-good FO** — after each successful decode, record the FO
2. **Re-scan on silence** — if N consecutive chunks have no decodes, re-run
   scan_frequency with a narrow window (±5 kHz around last good FO)
3. **Moving average** — smooth FO changes to prevent thrashing

### RX Changes (`pkt_enhanced_rx.py`)

In `LiveReceiver`:

```python
# New attributes
self._fo_lock = False        # whether we have a valid FO
self._fo_history = []        # list of FO estimates from decodes
self._empty_chunks = 0       # consecutive chunks with no decode
self._fo_recheck_interval = 10  # re-check after this many empty chunks
```

In `_process_chunk()`:

```python
# Before FO estimation
if self._fo_lock and self._empty_chunks < self._fo_recheck_interval:
    fo = self._fo  # reuse last estimate (fast path)
else:
    if self._fo_lock:
        # Narrow re-scan around last known FO
        fo = scan_frequency(samples, search_center=self._fo, search_width=5000)
    else:
        fo = scan_frequency(samples)
    
    if abs(fo) > 1 or True:  # always consider a non-zero FO valid
        self._fo = fo
        self._fo_lock = True
        self._empty_chunks = 0

# After processing:
if any_good_packets:
    self._fo_history.append(fo)
    if len(self._fo_history) > 5:
        self._fo_history.pop(0)
    self._fo = np.median(self._fo_history)  # median filter
    self._empty_chunks = 0
else:
    self._empty_chunks += 1
```

The `scan_frequency` function needs a narrower-fast-path mode:

```python
def scan_frequency(samples, search_width=20000, search_center=0.0):
    """..."""
    # Existing logic but center on search_center, search ±search_width/2
```

### Behavioral states

```
State diagram for FO tracker:

   [START] → scan_frequency(full ±20 kHz)
       │
       ▼
   [ACQUIRED] → FO locked, use last estimate
       │
       ├── decode success → update moving avg, reset counter
       │
       └── N empty chunks → [RE-SCAN] narrow ±5 kHz around last FO
                                   │
                                   └── lock new FO → [ACQUIRED]
                                       │
                                       └── still no decode → [START]
```

### Test Plan

- Layer 2 loopback: FO tracker should lock to 0 Hz immediately
- Inject artificial FO by rotating samples: `samples *= exp(-j·2π·f_off·t)`
  at a few kHz offset; verify tracking follows
- Verify re-scan triggers after N empty chunks of silence
- Verify moving average prevents FO hopping on single bad decode

---

## Implementation Order

```
Day 1:  Feature 2 — Variable SPS (TX + RX)
        ├── Add --sps and --samp-rate args
        ├── Thread SPS through TX chain
        ├── Thread SPS through RX chain
        └── Verify Layer 2 tests at SPS=20, 40, 100

Day 1:  Feature 3 — Burst Shaping
        ├── Write apply_burst_shaping()
        ├── Integrate into make_test_burst()
        └── Verify Layer 2 tests pass (nominal behavior unchanged)

Day 2:  Feature 4a — Digital AGC
        ├── Write apply_digital_agc()
        ├── Integrate into _process_chunk()
        └── Verify Layer 2 tests with various input levels

Day 2:  Feature 4b — Continuous FO Tracking
        ├── Add narrow re-scan mode to scan_frequency()
        ├── Add state tracking to LiveReceiver
        ├── Add FO injection test
        └── Verify loopback with artificial FO drift
```

### Files Changed

| File | Lines Added | What |
|------|------------|------|
| `src/pkt_enhanced_tx.py` | ~55 | `--sps`, `--samp-rate`, burst shaping function |
| `src/pkt_enhanced_rx.py` | ~80 | `--sps`, `--samp-rate`, AGC, FO tracking, `--agc-target` |
| `packet_codec.py` | 0 | No changes needed |
| `test/test_layer2.py` | ~20 | Parameterize SPS test cases |
| `ALIGNMENT_PLAN.md` | ~10 | Update progress |
| `ARCHITECTURE.md` | Already done | Has diagrams and flow |

### Backward Compatibility

All new CLI args have defaults matching the current behavior:
- `--sps 20` → same as current
- `--samp-rate 2000000` → same as current
- `--agc-target 0.3` → no effective change for strong signals

Existing tests should pass without modification.
