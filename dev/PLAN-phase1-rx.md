# Phase 1 — Composite Receiver (RX)

## Goal

Replace the two separate RX paths (DVB-S2 demod + BPSK packet demod) with a single
`combined_rx.py` that opens one HackRF at a center frequency and splits the
baseband into two frequency-offset streams. The dashboard launches this process
and receives decoded video (MPEG-TS over UDP) and telemetry packets (HTTP POST).

## Architecture

```
HackRF @ 4+ MS/s, center fc
              │
        read_stream() chunk
         ┌────┴────┐
         │         │
    × e^(+j2π·2e6·t/fs)    × e^(-j2π·2e6·t/fs)
    (shift 912→DC)         (shift 916→DC)
         │                   │
         ▼                   ▼
    ┌─────────┐       ┌──────────────┐
    │  FIFO   │       │  BPSK Demod  │
    │  /tmp/  │       │  (demod.py   │
    │ dvbs2   │       │   decode())  │
    │  .iq    │       └──────┬───────┘
    └────┬────┘              │
         │              unpack_frame()
         ▼              → PositionFrame
    dvbs2/rx.py          → to_transport()
    --source fd          → POST /api/packet
    --sink udp
    --out-udp IP:PORT
         │
         ▼
    Dashboard video
    player (UDP)
```

## Files to Create

### `ground/rx/combined_rx.py` — Main script (~250 lines)

Runnable standalone, launched by dashboard.

**CLI args:**

```
--center-freq   Center frequency (default 914e6)
--offset        +/- offset per stream in Hz (default 100 kHz)
--sample-rate   SDR sample rate (default 4e6)
--lna           HackRF LNA gain (default 32)
--vga           HackRF VGA gain (default 40)
--amp           Enable HackRF amp flag (store_true)
--serial        HackRF serial number (optional)
--dvbs2-fifo   FIFO path for DVB-S2 I/Q samples (default /tmp/dvbs2_rx.iq)
--dvbs2-bin    Path to dvbs2/rx.py
--dvbs2-args   Extra CLI args for dvbs2 rx.py (e.g. "--modcod QPSK1/2 --rolloff 0.35 --pilots")
--udp-host     UDP target for MPEG-TS (default 127.0.0.1)
--udp-port     UDP target port (default 1234)
--dashboard    Dashboard URL (default http://localhost:8000/api/packet)
```

**Algorithm:**

```
1. Parse CLI args
2. Ensure FIFO exists at --dvbs2-fifo (else create)
3. Build dvbs2 rx.py subprocess command:

   python3 <dvbs2-bin>                      \
     --source fd                              \
     --in-fd <fd_to_fifo>                     \
     --sink udp                               \
     --out-udp <udp_host>:<udp_port>          \
     --sym-rate 1e6                           \
     --freq <center_freq - offset>            \  (tells rx.py the "tuned" frequency)
     <dvbs2-args>

   NOTE: The FIFO contains baseband samples already shifted so the DVB-S2
   signal (originally at center_freq - offset) appears at DC. The rx.py still
   needs the correct --freq for internal filter/LNA timing. Pass
   center_freq - offset as --freq.

4. Start the dvbs2 rx.py subprocess
5. Open HackRF via SoapySDR at center_freq, sample_rate
6. In a loop (until SIGINT/SIGTERM):
   a. Read stream chunk (e.g. 524288 samples = ~130 ms @ 4 MS/s)
   b. Generate a frequency-shifted copy for DVB-S2:
      t = np.arange(len(chunk))
      dvbs2_shifted = chunk * np.exp(2j * np.pi * (+offset) * t / sample_rate)
      # Shifts signal at (center - offset) to DC
      Write dvbs2_shifted.tobytes() to the FIFO
   c. Generate a frequency-shifted copy for BPSK:
      bpsk_shifted = chunk * np.exp(-2j * np.pi * (+offset) * t / sample_rate)
      # Shifts signal at (center + offset) to DC
      Run bpsk_decoder.decode(bpsk_shifted)
      For each decoded payload:
        frame = unpack_frame(payload)
        if frame:
            packet = frame.to_transport()
            requests.post(dashboard_url, json={"data": packet}, timeout=2)
   d. Flush FIFO after write to ensure subprocess receives data promptly
7. On shutdown: terminate dvbs2 subprocess, close SDR, remove FIFO
```

**BPSK decoder import:**

```python
import sys
from pathlib import Path
_HAB = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_HAB / "protocol"))
sys.path.insert(0, str(_HAB / "ground" / "rx"))

from telemetry import unpack_frame
# Import and instantiate the PacketDecoder from demod.py
# PacketDecoder is a class that takes samples and returns [(payload, score, fo, phase, sync_idx, length), ...]
```

The BPSK decoder shares the same frequency plan as `payload/tx/main.py`:
- 100 ksym/s, SPS=20, FS=2 MS/s for the BPSK portion
- RRC α=0.35, sync word 0xE38FC0FC, preamble 256 bits, CRC-16/XMODEM
- Packets are 38-byte PositionFrames inside the standard framing

**Error handling:**
- If the HackRF fails to open, log and exit with code 1
- If FIFO write fails (subprocess died), recreate FIFO and restart subprocess
- If POST to dashboard fails, log warning, continue
- Rate-limit error log messages to 1 per 10 seconds

---

## Files to Modify

### `ground/dashboard/server/receiver_manager.py`

The `ReceiverManager._start_receiver()` method currently launches `pkt_simple_rx.py`
as a subprocess. Replace this with launching `combined_rx.py`:

```python
async def _start_receiver(self):
    hab_root = Path(__file__).resolve().parent.parent.parent.parent
    rx_script = hab_root / "ground" / "rx" / "combined_rx.py"

    cmd = [
        sys.executable,
        str(rx_script),
        "--center-freq", str(int(self._config.freq_hz)),
        "--sample-rate", "4000000",
        "--lna", str(self._config.gain_lna or 32),
        "--vga", str(self._config.gain_vga or 40),
        "--udp-host", "127.0.0.1",
        "--udp-port", "1234",
        "--dashboard", f"http://localhost:{self._config.server_port}/api/packet",
    ]
    if self._config.serial:
        cmd.extend(["--serial", self._config.serial])
    if getattr(self._config, "gain_amp", False):
        cmd.append("--amp")

    self._receiver = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    self._bridge_task = asyncio.create_task(
        self._read_receiver_lines()
    )
```

The `_read_receiver_lines()` method should be simplified since combined_rx.py
handles its own packet ingestion. It should just log stdout lines and watch for
process exit.

Also clean up the stale `_start_receiver` method's imports — it currently
references `rf/packet/src/pkt_simple_rx.py` which no longer exists at that path.

**Update `ReceiverConfig` to include `server_port`** if it doesn't have it.

### `ground/dashboard/server/config.py` (check current state)

Add `server_port: int = 8000` to `ReceiverConfig` if missing.

### `ground/dashboard/server/routes/rest.py`

No changes needed — the `/api/packet` endpoint already works with the bridge's
JSON format. combined_rx.py will POST the same shapes.

### `ground/dashboard/server/main.py`

Fix the sys.path insert for dev libraries (Codex review P2). Use a proper
`HAB_ROOT` computation:

```python
HAB_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(HAB_ROOT / "dev" / "packet" / "packet" / "src"))
sys.path.insert(0, str(HAB_ROOT / "dev" / "dvbs2" / "dvbs2"))
```

---

## Verification

### Standalone test (before dashboard integration):
```bash
cd ~/git/hab
python3 ground/rx/combined_rx.py \
  --center-freq 914e6 --sample-rate 4000000 \
  --lna 32 --vga 40 \
  --dvbs2-bin dev/dvbs2/dvbs2/rx.py \
  --udp-port 1234 \
  --dashboard http://localhost:8000/api/packet
```

Then in another terminal:
```bash
# Listen for MPEG-TS video
ffplay udp://127.0.0.1:1234

# Check packets arriving at dashboard
curl http://localhost:8000/api/packets | jq '. | length'
```

### Integration test:
```bash
cd ~/git/hab/ground/dashboard/server
python3 main.py
# combined_rx.py should auto-launch when receiver starts
```
