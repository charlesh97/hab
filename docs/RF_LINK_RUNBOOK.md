# RF Link Runbook — Composite DVB-S2 Video + BPSK Telemetry

How to bring up the full link yourself: one HackRF per side, composite
transmit (DVB-S2 video + BPSK telemetry) sharing a single radio each way.
Validated end-to-end 2026-07-31 (30-min soak, 30/30 stills over RF).

## Hardware

| Side | Device | Role |
|---|---|---|
| TX | Radxa Rock 2A (Armbian) + HackRF `60a464dc3674640f` | Payload: encodes & transmits |
| RX | Mac (Homebrew Python 3.14 + GNU Radio) + HackRF `60a464dc3606610f` | Ground station: decodes video + telemetry |

Link: **914.0 MHz center**, composite = DVB-S2 at **+700 kHz** offset, BPSK at **−700 kHz**.

## The validated config (Option A)

The Rock 2A's encoder tops out at ~4 MS/s sustained, so the link runs at
**4 MS/s sample rate / 1 Msym/s symbol rate** with a light RRC filter
(`--rrc-delay 1`). Anything needing 8 MS/s (the old 2 Msym/s config) starves
on air and the video never locks. This config runs the encoder at ~70% of
its ceiling — comfortable margin.

---

## 1. Transmit (on the Rock 2A)

**Use the restart script** — it kills stale TX processes (composite TX, DVB-S2 encoder,
ffmpeg, GPS gpioset holders) and starts a fresh video-only TX:

```bash
ssh rock2a "bash /home/hab/restart_tx.sh"
# repo source: scripts/restart_tx.sh  (deployed to /home/hab/restart_tx.sh)
# log: /tmp/tx_video.log
```

It re-asserts the GPS GPIOs itself (`gpiochip1:9` WAKE, `gpiochip1:14` RST_N) — no
manual `gpioset` needed. The equivalent one-liner:

```bash
cd /home/hab/git/hab
nohup python3 -u payload/tx/main.py \
  --center-freq 914e6 \
  --sample-rate 4e6 \
  --sym-rate 1e6 \
  --rrc-delay 1 \
  --video-size 640x360 \
  --no-timestamp-overlay \
  --video-source testsrc \
  --no-bpsk \
  --serial 60a464dc3674640f \
  > /tmp/tx_video.log 2>&1 &
```


`payload/tx/main.py` is a thin wrapper over `payload/tx/combined_tx.py`.

### TX parameters

| Flag | Default | Notes |
|---|---|---|
| `--center-freq` | `914e6` | RF center frequency (Hz) |
| `--offset` | `700e3` | Subcarrier spacing DVB-S2↔BPSK. **Must match RX.** Ignored with `--no-bpsk` |
| `--sample-rate` | `8e6` | **Use `4e6`** — Rock 2A encoder ceiling ~4 MS/s |
| `--sym-rate` | `2e6` | **Use `1e6`** — pairs with 4e6 sample rate |
| `--rrc-delay` | `2` | RRC filter half-span (symbols). **Use `1`** — lighter CPU; `2` = 3.23 MS/s (too slow) |
| `--video-source` | `camera` | `camera` (`/dev/video0`) or `testsrc` (ffmpeg synthetic — use for validation; the Rock 2A camera is currently dead for sustained streaming) |
| `--video-size` | `1280x720` | `640x360` keeps ffmpeg CPU low |
| `--timestamp-overlay` / `--no-timestamp-overlay` | overlay **ON** | drawtext clock in corner; `--no-timestamp-overlay` to disable |
| `--modcod` | `QPSK1/2` | |
| `--rolloff` | `0.35` | choices `0.35` `0.25` `0.20` |
| `--pilots` / `--no-pilots` | pilots **ON** | |
| `--tsrate` | auto | Override TS rate (bps); auto-computed from `--sym-rate` |
| `--vga` | `30` | HackRF TX VGA (0–47) |
| `--amp` | off | HackRF TX amp |
| `--serial` | — | HackRF serial (explicit radio selection) |
| `--gps-port` | `/dev/ttyS0` | GPS UART |
| `--gps-baud` | `9600` | |
| `--video-udp` | `5000` | ffmpeg → encoder TS UDP port |
| `--no-video` | — | BPSK telemetry only (no DVB-S2) |
| `--no-bpsk` | — | DVB-S2 only, at center freq |
| `--use-gr` | off | GNU Radio C++ DVB-S2 blocks instead of numpy encoder |
| `--dvbs2-bin` | `dev/dvbs2/dvbs2/tx.py` | Path to DVB-S2 tx |

---

## 2. Receive (on the Mac)

**Use the restart script** — it kills the stale RX (combined_rx, DVB-S2 child,
hackrf_transfer) plus any ffmpeg bridge squatting on UDP:1234/:8001, then starts fresh:

```bash
cd ~/git/hab && bash scripts/restart_rx.sh
# log: /tmp/rx.log
```

The equivalent manual launch. Use `exec … > log 2>&1` (plain `nohup … &` fails with exit −1):

```bash
cd ~/git/hab
PYTHONPATH=/opt/homebrew/lib/python3.14/site-packages \
exec /opt/homebrew/bin/python3.14 -u ground/rx/combined_rx.py \
  --center-freq 914e6 \
  --sample-rate 4e6 \
  --sym-rate 1e6 \
  --no-bpsk \
  --serial 60a464dc3606610f \
  --lna 32 --vga 40 --amp \
  > /tmp/rx.log 2>&1
```

**Use `/opt/homebrew/bin/python3.14`** — system `python3` exits 1. `dev/setup_env.sh` sets `PYTHONPATH` for GNU Radio; if you skip it, set `PYTHONPATH=/opt/homebrew/lib/python3.14/site-packages`.

### RX parameters

| Flag | Default | Notes |
|---|---|---|
| `--center-freq` | `914e6` | Must match TX |
| `--offset` | `700e3` | **Must match TX.** `_split` shifts the DVB-S2 branch by `−offset` |
| `--sample-rate` | `8e6` | **Use `4e6`** — must be an integer multiple of `2e6` (BPSK FS) |
| `--sym-rate` | `2e6` | **Use `1e6`**; must satisfy sample/sym ≥ 2 |
| `--lna` / `--vga` | `32` / `40` | RX gains |
| `--amp` | off | RX amp — **ON** in validated config |
| `--serial` | — | HackRF serial (explicit) |
| `--udp-host` / `--udp-port` | `127.0.0.1:1234` | TS output sink (feeds the video bridge) |
| `--dvbs2-bin` | `dev/dvbs2/dvbs2/rx.py` | DVB-S2 RX path |
| `--dvbs2-fifo` | `/tmp/dvbs2_rx.iq` | IQ FIFO to DVB-S2 child |
| `--dvbs2-args` | `""` | Extra args appended to DVB-S2 child cmd |
| `--no-dvbs2` | — | BPSK telemetry only |
| `--no-bpsk` | — | DVB-S2 only |
| `--dashboard` | `http://localhost:8000/api/packet` | BPSK → dashboard POST |

### Health signals (in `/tmp/rx.log`)

- **DVB-S2 live stats** — one line every 5 s:
  `[DVBS2] DVB-S2 rx: fifo=4.00/4.00 MS/s, fifo_full=0 drops, child=alive, restarts=0, bridge=SERVING`
  - `fifo` = IQ rate fed to the decoder vs requested — below target means the HackRF/USB is starving
  - `fifo_full` drops = decoder can't keep up (drops IQ, corrupting TS)
  - `child`/`restarts` = DVB-S2 decoder process health
  - `bridge` = `WAITING` (listening, no client) / `SERVING` (client streaming) / `DOWN`
- **TX side** (`ssh rock2a "tail -f /tmp/tx_video.log"`) — same cadence:
  `[DVBS2] DVB-S2 enc: rate=4.00/4.00 MS/s (100.0%), underflow=0 pads, tx=alive, ffmpeg=alive, restarts=0`
  - `rate` below 100% + `underflow` pads = encoder starving (pads = silence/garbage in TS)
  - Encoder/ffmpeg child stderr is captured to `/tmp/tx_dvbs2_stderr.log` and `/tmp/tx_ffmpeg_stderr.log`
- **BPSK** (when enabled): `Telemetry` line ~1/sec with `seq=` increasing; FO locked around `−7 kHz` (HackRF clock offset) — expect it, don't chase it.
- Watch for `BPSK decoder falling behind`, `Unknown BPSK frame type` spam, pacing overflow/underflow.
- bbdeheader `upl != 188 bytes` / `dfl not a multiple of 8` = TS corruption clusters over RF.

---

## 3. Video bridge + still grab

The composite RX spawns an ffmpeg MJPEG bridge: `udp://127.0.0.1:1234` → MJPEG served on `:8001/video`. The bridge is one-shot (accepts **one** client then exits), but the RX runs a supervisor thread that kills stale bridges on startup and **auto-respawns the bridge within ~5 s** whenever it exits (client served, crash, or never bound). CameraFeed can be refreshed as often as you like.

Manual bridge (for a single still):

```bash
ffmpeg -hide_banner -loglevel warning \
  -i udp://127.0.0.1:1234 -c:v mjpeg -q:v 5 -f mpjpeg \
  -listen 1 http://0.0.0.0:8001/video &
# wait for :8001 to LISTEN (lsof -nP -iTCP:8001 -sTCP:LISTEN)
ffmpeg -y -hide_banner -loglevel error -timeout 20000000 \
  -i http://127.0.0.1:8001/video -frames:v 1 -q:v 2 still.jpg
```

⚠️ **Probe :8001 with `lsof`, never `connect()`/`curl`** — a connect is the
bridge's one client, so it exits immediately. The bridge binds only once a
clean H.264 frame decodes; with the link's ~5–7% packet-loss clusters this
can take 10–20 s. Retry with a fresh bridge (the link delivers frames
intermittently).

---

## 4. 30-minute soak

```bash
cd ~/git/hab
# RX PID = the combined_rx.py python PID (pgrep -f combined_rx.py)
/opt/homebrew/bin/python3.14 -u soak/soak_monitor.py \
  --minutes 30 --interval 60 --rx-pid <RX_PID>
```

Output: `soak/YYYY-MM-DD_HHMMSS/` with `soak.log` + `stills/still_NNNN.jpg`
(~17 KB each). Monitor SSHs to `rock2a.local` (`hab@`) to sample TX seq
progress, watches RX-side PIDs, and flags `CRASH` after 3 consecutive still
failures (informational — the soak keeps running).

| Flag | Default | Notes |
|---|---|---|
| `--minutes` | `30` | Soak duration |
| `--interval` | `60` | Seconds between stills |
| `--rx-pid` | — | PID of the running `combined_rx.py` (watched for liveness) |

---

## 5. Offline verification (capture → decode)

Capture raw IQ with the RX HackRF, then decode locally. This is how the
0-TS bugs were isolated — it proves whether a problem is in the **signal**
(air path) or the **RX glue** (code):

```bash
# 1. Capture (TX must be on). SC8: 8 bytes/sample; 40 M samples ≈ 5 s @ 8 MS/s
hackrf_transfer -r /tmp/cap.sc8 -f 914000000 -s 8000000 -n 40000000 \
  -a 1 -l 32 -g 40

# 2. Shift the DVB-S2 branch to baseband (−offset) and decode via rx.py
#    (pattern: offline file-in decode, same path the live child uses)
```

A clean local reference is worth generating before touching RF: feed
`payload/tx/combined_tx.py` a `testsrc` source straight to a file (no
HackRF) — the composite should show DVB-S2 at +700 kHz, 100% continuous
duty. The live capture will show ~100% duty too; the Rock 2A encoder gaps
(starvation) were the original no-lock cause.

---

## 6. Dashboard (on the Mac)

The ground dashboard lives in `ground/dashboard/` (server on `:8000`, Preact/TS SPA).
Only this path is valid — the pre-reorg `~/git/hab/dashboard/` is dead code.

```bash
cd ~/git/hab/ground/dashboard/server
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
# browse http://<mac-ip>:8000   (localhost works; charleslab.local does not resolve)
```

Video status is **decoupled from the dashboard's own receiver manager**: the SPA
polls `GET /api/video-status` every 5 s and the server answers by `lsof`-inspecting
:8001 (never `connect()` — that would consume the one-shot bridge). It reports up
when the bridge holds **any** socket on :8001 (LISTEN *or* ESTABLISHED), so the feed
stays mounted while a client streams. `up:true` means "a bridge is there", not
"frames are decodable" — if the pane is blank while `up:true`, check the `[DVBS2]`
stats in `/tmp/rx.log` and the TX log.

Map behavior: packets are always logged, but no-fix / zero coordinates are not
plotted (map shows `NO FIX`) — `useHabApi.ts` + `MapCard.tsx`.

Note: `ground/dashboard/server/hab_data.db` grows unbounded (~1.9 GB / ~7 M packets
as of Aug 2026). It is gitignored runtime data; prune or VACUUM if disk matters.

---

## Known issues & gotchas

1. **Rock 2A camera is dead for sustained streaming** — `/dev/video0`
   delivered ~184 KB total (one 1080p frame ≈ 3.1 MB); ffmpeg stalls at
   1.3% CPU. Single-frame grabs work; 15 fps doesn't. Use
   `--video-source testsrc` to validate; fix the camera driver separately.
2. **Encoder ceiling ~4 MS/s** — the RK3528 is single-core-bound. Design the
   link around it (Option A above). Don't raise `--sym-rate` back to 2e6
   without also dropping video resolution/CPU load.
3. **Stale ffmpeg bridge on UDP:1234** steals the TS stream — the RX
   supervisor now kills stale bridges on startup, but if you run a manual
   bridge or another grabber, `pkill -f "udp://127.0.0.1:1234"` first.
4. **Bridge is one-shot per client, auto-respawned by the RX supervisor**
   (~5 s cadence). Lsof-probe only — a `connect()`/`curl` is the bridge's
   one client and consumes it (harmless now: it respawns).
5. **`nohup … &` RX launch fails** on macOS (exit −1) — use the
   `exec … > log 2>&1` form; kill both wrapper + python PIDs to stop.
6. **Rock 2A SSH is flaky (rc 255)**: single commands or script files only,
   no `&&` chains. Remote `sed`/inline-python edits don't stick — write
   files locally and `scp`. `pkill -f` patterns self-match the ssh command
   line when they match its args — use bracket tricks (`tx[.]py`).
7. **~26° constant phase smear over RF** (EVM 0.454 vs 0.112 local) causes
   occasional H.264 corruption windows (~5–7% TS packet-loss clusters);
   stills still succeed ~70–80%. Suspected HackRF clock/phase noise — next
   isolation step is an RF loopback test (HackRF TX→RX direct).
8. **System `python3` exits 1** on the Mac — always
   `/opt/homebrew/bin/python3.14` with `PYTHONPATH` from `dev/setup_env.sh`.
9. **pyserial not in the base env** for test runs — `PYTHONPATH=/tmp/compvenv/lib/python3.14/site-packages` (tests import `serial`).
10. **`~/hab` is dead** — an abandoned July-20 scaffold, separate git repo pointing at
    `charleshood/hab` (different org), single "init" commit. The project is `~/git/hab`
    (`charlesh97/hab`). Nothing references `~/hab`; archived to `~/Archive/`.
11. **Rock 2A `/home/hab/git/hab` is a loose scp'd copy, not a git clone** — deploy by
    scp'ing `payload/tx/combined_tx.py` and comparing md5. `restart_tx.sh` lives at
    `/home/hab/restart_tx.sh` (source: `scripts/restart_tx.sh`).

## Tests

```bash
cd ~/git/hab
PYTHONPATH=/tmp/compvenv/lib/python3.14/site-packages \
  /opt/homebrew/bin/python3.14 -m pytest \
  ground/rx/tests/test_combined_rx.py payload/tests/test_combined_tx.py -q
# 33 passed
```
