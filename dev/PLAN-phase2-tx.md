# Phase 2 — Composite Transmitter (TX)

## Goal

Replace the two separate TX paths (fifo → dvbs2 tx.py, and standalone GPS BPSK tx)
with a single `payload/tx/composite.py` that:
1. Launches ffmpeg → MPEG-TS → UDP
2. Receives MPEG-TS from UDP and DVB-S2 modulates it
3. Reads GPS NMEA and produces BPSK-modulated PositionFrames
4. Frequency-offsets both streams ±X MHz, sums them
5. Transmits the composite baseband via one HackRF

## Architecture

```
Camera ──▶ ffmpeg ──▶ MPEG-TS ──▶ UDP : 127.0.0.1:1235
                                        │
                                        ▼
                               UDP Source block
                                        │
                               ┌────────────────┐
                               │  DVB-S2 Mod    │  (QPSK 1/2, 1 Msym/s)
                               │  (blocks from  │
                               │   dvbs2/tx.py) │
                               └───────┬────────┘
                                       │
                                  × exp(j2π·offset·t)
                                       │
                                       ▼
GPS NMEA ──▶ PositionFrame ──▶ ┌──────────────┐     SUM ──▶ HackRF @ fc
  .pack()                      │  BPSK Mod    │        │
                               │  (100 ksym/s) │        │
                               │  38B packets  │        │
                               └───────┬───────┘        │
                                       │                │
                                  × exp(-j2π·offset·t)  │
                                       │                │
                                       └────────────────┘
```

**Transmission:**
- fc = center frequency (e.g. 914 MHz)
- DVB-S2 appears at fc + offset (e.g. 916 MHz)
- BPSK appears at fc - offset (e.g. 912 MHz)
- Both summed into one baseband → one Soapy sink

---

## Files to Create

### `payload/tx/composite.py` (~350 lines)

Standalone script meant to run as the sole TX process on the Rock 2A,
launched either directly or via `payload/main.py`.

**CLI args:**

```
--center-freq   Center frequency (default 914e6)
--offset        +/- offset in Hz (default 100 kHz)
--sample-rate   SDR sample rate (default 6e6 to accommodate both streams)
--vga           HackRF VGA gain (default 47)
--amp           Enable HackRF amp (store_true)
--serial        HackRF serial (optional)
--gps-device    GPS serial device (default /dev/ttyS0)
--gps-baud      GPS serial baud (default 9600)
--video-device  Video device (default /dev/video0)
--video-fps     Video framerate (default 15)
--video-bitrate Video encode bitrate (default 700k)
--video-size    Video resolution (default 640x480)
--ts-muxrate    MPEG-TS muxrate (default 965326)
--sym-rate      DVB-S2 symbol rate (default 1e6)
--modcod        DVB-S2 MODCOD (default QPSK1/2)
--rolloff       DVB-S2 rolloff (default 0.35)
--pilots        Enable DVB-S2 pilots (store_true)
--ffmpeg-udp    UDP port for ffmpeg video (default 1235)
```

**Workflow:**

```
1. Parse CLI args
2. Start ffmpeg subprocess writing MPEG-TS to UDP (127.0.0.1:<ffmpeg-udp>)
3. Open GPS serial device
4. Open HackRF via SoapySDR
5. Create GNU Radio top_block with:

       ┌─────────────────────────────────────────────────────────────────┐
       │  GNU Radio Flowgraph                                            │
       │                                                                 │
       │  UDP Source (MPEG-TS) ──▶ DVB-S2 Mod Block ──▶ × exp(j·...) ──┐│
       │                          (constellation, mod, framing, pilots)  ││
       │                                                                ││
       │  Vector Source (BPSK bursts ──▶ RRC ──▶ × exp(-j·...) ────────┼┤→ SUM → Soapy Sink
       │   1 Hz loop via throttle)                                      ││
       │                                                                ││
       └────────────────────────────────────────────────────────────────┘┘

   Since the DVB-S2 blocks are complex GNU Radio blocks and don't easily
   compose with the BPSK vector-source approach, use this strategy:

   The main loop handles:
   a. Reading GPS NMEA, building PositionFrame, packing to bytes
   b. BPSK modulating each packet (reuse make_packet_waveform from tx/main.py)
   c. Frequency-shifting the BPSK burst by -offset
   d. Appending trailing silence to fill 1-second cycle

   Meanwhile, the DVB-S2 runs in a GNU Radio top_block on a background thread:
   - UDP source reads the MPEG-TS stream that ffmpeg sends
   - DVB-S2 modulator blocks process the stream
   - The modulated output is frequency-shifted by +offset
   - Both streams are summed and transmitted

   OR, more practically: since we can't easily sum two running GNU Radio
   streams at different sample rates (DVB-S2 at 1 Msym/s → higher sample rate
   vs BPSK at 100 ksym/s), use this approach:

   Run the DVB-S2 GNU Radio flowgraph in its own thread, writing the
   modulated + frequency-shifted I/Q to a queue. In the main thread,
   read from the queue, sum with the BPSK waveform, and send to the
   Soapy sink. This avoids the sample rate mismatch issue.
```

**Simplified approach (practical):**

```python
# Two separate threads sharing a synchronized sample buffer:
#
# Thread 1: DVB-S2 GNU Radio flowgraph
#   - UDP source → DVB-S2 modulator → frequency shift +offset
#   → custom sink that pushes to a thread-safe deque
#
# Thread 2: Main loop (1 Hz)
#   - Read GPS → PositionFrame → BPSK modulate → frequency shift -offset
#   - Read the latest DVB-S2 block from the deque
#   - Resample BPSK to match DVB-S2 sample rate (if needed)
#   - Sum the two streams element-wise
#   - Write summed samples to Soapy sink
#   - Sleep to maintain 1 Hz cycle timing
```

Alternatively, if both streams can use the same sample rate:
- Set Soapy sink to 6 MS/s (Nyquist covers ±2 MHz fine)
- DVB-S2 runs at 6 MS/s: upsample from 1 Msym/s × SPS
- BPSK runs at 6 MS/s: 100 ksym/s × SPS = 2 MS/s, upsampled to 6 MS/s
- Sum at 6 MS/s
- This is cleaner but more complex up-front

**Recommended first implementation:** Use the thread-safe deque approach.
It gets the system working and can be optimized to a single flowgraph later.

**Error handling:**
- If GPS device cannot be opened, log warning, transmit packets with last known position (or zeros)
- If HackRF fails to open, exit with code 1
- If ffmpeg dies, restart it (up to 3 times, then give up)
- Log transmitted packet status (frequency, GPS position, DVB-S2 bitrate)

---

## Files to Modify

> **Note:** The composite transmitter was implemented as `payload/tx/combined_tx.py`
> (entry point `payload/tx/main.py`). References to `composite.py` below are the
> original design name; `combined_tx.py` is the realization.

### `payload/tx/combined_tx.py` (replaces earlier `tx_pipeline.py`)

The composite transmitter owns ffmpeg and the DVB-S2 encoder internally.
`tx_pipeline.py` (the earlier FIFO-based ffmpeg launcher) was removed when the
composite pipeline landed.

```python
def launch_ffmpeg(udp_port=1235, video_device="/dev/video0",
                  tel_fifo="/tmp/tel_fifo",
                  video_fps=15, video_bitrate="700k",
                  video_size="640x480", ts_muxrate=965326):
    """Launch ffmpeg writing MPEG-TS to UDP."""
    return subprocess.Popen([
        "ffmpeg", "-y",
        "-f", "v4l2",
        "-framerate", str(video_fps),
        "-video_size", video_size,
        "-i", video_device,
        "-f", "data",
        "-i", tel_fifo,
        "-map", "0:v:0",
        "-map", "1:0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-b:v", video_bitrate,
        "-c:d", "copy",
        "-f", "mpegts",
        "-muxrate", str(ts_muxrate),
        f"udp://127.0.0.1:{udp_port}",
    ])
```

Also add `launch_composite_tx()` helper that calls `python3 payload/tx/composite.py`
with appropriate args.

### `payload/main.py`

Update the orchestrator to launch `composite.py` instead of separate
ffmpeg + dvbs2-tx processes:

```python
processes: dict[str, subprocess.Popen | None] = {
    "composite-tx": None,
}
```

Remove the `ffmpeg` and `dvbs2-tx` entries. The composite script manages its own
ffmpeg subprocess internally.

Remove or update the `launchers` dict and the FIFO setup/teardown for
`TRANSPORT_FIFO` (the telemetry FIFO `/tmp/tel_fifo` is still needed for the
overhead data stream).

---

## Verification

### On the Mac (file-to-HackRF loopback test):
```bash
# Requires HackRF connected
cd ~/git/hab
python3 payload/tx/composite.py \
  --center-freq 914e6 --offset 2e6 \
  --sample-rate 6000000 --vga 47 --amp \
  --gps-device /dev/null  \
  --video-device /dev/null \
  --ffmpeg-udp 1235
```

This won't transmit useful video (no camera), but it confirms:
- The HackRF opens
- The flowgraph runs without error
- The 1 Hz BPSK cycle works
- GPS-less fallback works

### On the Rock 2A:
```bash
cd ~/git/hab
python3 payload/tx/composite.py \
  --center-freq 914e6 --offset 2e6 \
  --sample-rate 6000000 --vga 47 --amp \
  --gps-device /dev/ttyS0 --gps-baud 9600 \
  --video-device /dev/video0 \
  --serial 60a464dc3674640f
```
