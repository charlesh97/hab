# Encoder Throughput Evidence — Rock 2A (RK3528) DVB-S2 Encoder Ceiling

**Claim:** the Rock 2A's Python/numpy DVB-S2 encoder (`dev/dvbs2/dvbs2/tx.py`)
cannot sustain the composite sample rate it is asked to produce. The ceiling
is roughly **4–4.2 MS/s** in the original config (8 MS/s sample rate, 2 Msym/s,
`--rrc-delay 2`), and **6.7 MS/s** in the lighter Option A config
(4 MS/s sample rate, 1 Msym/s, `--rrc-delay 1`). The encoder output rate is
bounded by filter cost (RRC taps), not by the symbol rate.

Measured 2026-07-31 on the Rock 2A (`/home/hab/git/hab`, Armbian,
4× RK3528 cores, ~63 °C, load 3–4.5 during live TX).

## Measurement 1 — Paced consumer at 8 MS/s (the old config)

Script: `/tmp/rk2_paced_encoder.py` (replicates the live pipeline: ffmpeg
testsrc → `tx.py` encoder → consumer pacing reads at exactly 8 MS/s in
40 ms chunks, same as the composite+HackRF backpressure; no RF, no mixer).

```bash
# on Rock 2A:
python3 /tmp/rk2_paced_encoder.py
```

**Result: `chunks=32 samples=10240000 wall=5.01s rate=2.05 MS/s`**

The encoder produced 1.28 s of samples in 5 s of wall time — it fell **4×
behind** the 8 MS/s the link demanded. Output file `/tmp/paced_enc.fc32`
(81,920,000 B = 10.24 M complex64 samples) verified on the Mac: **100%
continuous, clean DVB-S2 at DC, 50.8 dB SNR** → the encoder output is
perfect when it can keep up; the on-air gaps were *starvation*, not
distortion.

## Measurement 2 — Unpaced drain (the ceiling, no pacing involved)

Script: `/tmp/rk2_symrate_test.py` — reads encoder output as fast as
possible for 10 s (zero backpressure) at symbol rates 0.9 / 0.75 / 1.0 Msym/s.

**Result: ceiling ≈ 4.2 MS/s regardless of symbol rate** (sym=1.0 run:
3.92 MS/s; the script's `need=sym*4` check is sloppy — the output stream is
at the fixed 8 MS/s sample rate, so the real requirement was 8 MS/s and
3.92 was 49% of it).

## Measurement 3 — Option A: lighter filter fixes it

Script: `/tmp/rk2_optA_test.py` — same drain test at 4 MS/s sample rate,
1 Msym/s, `--rrc-delay 1`.

**Result: `Option A (4e6/1e6 rrc1): 6.71 MS/s (need 4.0) -> OK`** — 168%
margin. This is the config that produced the first live TS since the 0-TS
era and passed the 30/30 still soak.

**Kicker:** the same Option A rates with `--rrc-delay 2` instead of 1 gave
**3.23 MS/s — still short**. The RRC filter is the binding constraint:
`--rrc-delay 1` at 4 sps = 9 taps; `--rrc-delay 2` at 4 sps = 17 taps.
Halving the taps is what unlocked the config.

## Why

`tx.py` is a single-core-bound Python/numpy filter chain (the RRC pulse
shaping filter dominates). The Rock 2A has 4 cores; during live TX the
encoder sat at 93–99% of one core with load average 4.5/4 — the board was
saturated. `combined_tx.py` passes `--samp-rate` = the composite sample
rate to the encoder (see `_tx_command`, `combined_tx.py:464`), so the
encoder's output rate **equals** the composite rate. Raising the composite
rate to 8 MS/s (or higher) directly demands more encoder throughput than
the CPU can supply.

## Implications

1. **Link design rule:** the composite sample rate must stay within the
   encoder's measured ceiling for the chosen filter: ~4 MS/s with
   `--rrc-delay 2`, ~6.7 MS/s with `--rrc-delay 1`.
2. The validated Option A config (4 MS/s / 1 Msym/s / rrc1) is a *design
   around* the hardware limit, not the theoretical optimum.
3. **To go wider** (e.g. 6–10 MS/s composite for a wider channel plan), the
   encoder rate must be **decoupled** from the composite rate: run `tx.py`
   at its own rate and digitally upsample/interpolate the DVB-S2 branch to
   the composite rate before the frequency interleave. That is a code change
   to `combined_tx.py` (rational resampler between encoder output and mixer),
   not a CLI flag.
4. A 6 MS/s composite at 2 Msym/s (3 sps, rrc1, 7 taps) *may* fit the
   6.7 MS/s ceiling without decoupling — unverified; needs a 30-second
   `rk2_optA_test.py`-style measurement before trusting it.

## Re-running the evidence

```bash
# copy to Rock 2A, run with TX stopped (CPU contention corrupts numbers)
scp /tmp/rk2_paced_encoder.py hab@rock2a.local:/tmp/
scp /tmp/rk2_symrate_test.py hab@rock2a.local:/tmp/
scp /tmp/rk2_optA_test.py hab@rock2a.local:/tmp/
ssh hab@rock2a.local "python3 /tmp/rk2_paced_encoder.py"
ssh hab@rock2a.local "python3 /tmp/rk2_optA_test.py"
```

Sanity: paced ≈ 2 MS/s at 8 MS/s demand; Option A ≈ 6.7 MS/s at 4 MS/s
demand; both outputs decode cleanly offline.
