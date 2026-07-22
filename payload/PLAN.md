# Balloon Payload Software Plan

> **Status:** HARDWARE BRINGUP — GPS verified, I2C bus1 verified, bus0 sensors broken. Phase 1D (GPS) and 1C (fuel gauge) PASS. Phase 1B blocked.
> **Target SBC:** Radxa Rock 2A (RK3528A) running Armbian Debian 13 (Trixie) Minimal CLI
> **Date:** 2026-07-22 (updated)

---

## 1. System Overview

The payload SBC (Rock 2A) ingests sensor data, GPS, and camera video, muxes telemetry into an MPEG-TS stream, and transmits it via DVB-S2 through a HackRF Software Defined Radio.

```
┌──────────────────────────────────────────────────────────┐
│                      Rock 2A Payload                      │
│                                                           │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Sensors │  │   GPS   │  │  Camera  │  │  Battery  │  │
│  │ TMP100  │  │  L76K   │  │   USB    │  │ MAX17049  │  │
│  │ LIS2DH  │  │  UART   │  │  UVC     │  │  I2C Bus1 │  │
│  │ LPS25HB │  │  NMEA   │  │          │  │           │  │
│  │ I2C Bus0│  │         │  │          │  │           │  │
│  └────┬────┘  └────┬────┘  └────┬─────┘  └─────┬─────┘  │
│       │            │            │               │        │
│       └────────────┼────────────┼───────────────┘        │
│                    │            │                        │
│              ┌─────▼─────┐ ┌───▼──────┐                  │
│              │ Telemetry │ │  Video   │                  │
│              │  Writer   │ │ Encoder  │                  │
│              │  (Python) │ │ (ffmpeg) │                  │
│              └─────┬─────┘ └───┬──────┘                  │
│                    │            │                        │
│              ┌─────▼────────────▼──────┐                  │
│              │    TS Muxer (ffmpeg)    │                  │
│              │  MPEG-TS with 2 PIDs    │                  │
│              └────────────┬───────────┘                  │
│                           │                              │
│                    ┌──────▼───────┐                       │
│                    │  DVB-S2 TX   │                       │
│                    │ (dvbs2-tx)   │                       │
│                    │  → HackRF    │                       │
│                    └──────────────┘                       │
└──────────────────────────────────────────────────────────┘
```

### 1.1 Data Constraints

| Parameter | Value | Reason |
|-----------|-------|--------|
| DVB-S2 symbol rate | 1 Msps | HackRF bandwidth budget |
| DVB-S2 MODCOD | QPSK 1/2 (or 2/3) | Link budget — lowest SNR threshold |
| Transport stream rate | ~948 kbps | QPSK 1/2 at 1 Msps with pilots |
| Video bitrate target | ~700 kbps | Leaves ~250 kbps for telemetry + TS overhead |
| Video resolution | 640×480 | Low-res for link reliability |
| Video framerate | 15 fps | Balances motion smoothness vs bitrate |
| Sensor poll rate | 1 Hz | Each sensor read + GPS fix per second |

---

## 2. Hardware Pinout

### 2.1 I2C Bus 0 — Environmental Sensors
| Physical Pin | Rockchip GPIO | Function | Device | I2C Address |
|-------------|---------------|----------|--------|-------------|
| 3 | GPIO4_A0 (128) | SDA0 | — | — |
| 5 | GPIO4_A1 (129) | SCL0 | — | — |
| — | — | — | TMP100 | 0x48 |
| — | — | — | LIS2DH | 0x19 |
| — | — | — | LPS25HB | 0x5D |

### 2.2 I2C Bus 1 — Fuel Gauge
| Physical Pin | Rockchip GPIO | Function | Device | I2C Address |
|-------------|---------------|----------|--------|-------------|
| 27 | GPIO4_A2 (130) | SDA1 | — | — |
| 28 | GPIO4_A3 (131) | SCL1 | — | — |
| — | — | — | MAX17049 | 0x36 |

### 2.3 UART0 — GPS

| Physical Pin | Rockchip GPIO | Function | Direction |
|-------------|---------------|----------|-----------|
| 8 | GPIO0_B1 | UART0 TX | SBC → GPS |
| 10 | GPIO0_B0 | UART0 RX | GPS → SBC |

**Device:** `/dev/ttyS0` (NOT ttyS2 — see SETUP.md §6.1 for FIQ debugger issue)

GPS parameters: 9600 baud, 8N1, NMEA sentences (GGA, RMC, GSV, GSA, VTG, ZDA, GLL, GSV, TXT).
GPS + BeiDou constellations. 6–8 satellites typical. Active antenna powered by VDD_RF on module.
Control pins: GPS_WAKE = pin 33 (GPIO1_B1), GPS_RST_N = pin 35 (GPIO1_B6). Both active HIGH.

### 2.4 GPIO — GPS Control

| Physical Pin | gpiochip | Line | Function | Active State |
|-------------|----------|------|----------|-------------|
| 33 | gpiochip1 | 9 | GPS_WAKE | HIGH = enabled |
| 35 | gpiochip1 | 14 | GPS_RST_N | HIGH = not in reset |

### 2.4 USB
| Port | Device | Purpose |
|------|--------|---------|
| USB 3.0 OTG | HackRF One | DVB-S2 TX |
| USB 2.0 #1 | USB Camera (UVC) | Video capture |
| USB 2.0 #2 | (spare) | — |
| USB 2.0 #3 | (spare) | — |

### 2.5 Network
| Interface | Purpose |
|-----------|---------|
| Gigabit Ethernet | Ground testing, SSH, streaming |
| WiFi 6 | (not used in flight — disabled for power) |

---

## 3. Sensor Register Map

### 3.1 TMP100 — Temperature Sensor (I2C 0x48)

| Register | Address | Size | Description |
|----------|---------|------|-------------|
| Temperature | 0x00 | 2 bytes | 12-bit, MSB first. °C = raw × 0.0625 |
| Configuration | 0x01 | 1 byte | Resolution, shutdown, alert mode |

Resolution modes:
- 9-bit (default): 320 ms conversion, 0.5°C resolution
- 12-bit: 320 ms conversion, 0.0625°C resolution

### 3.2 LIS2DH — 3-Axis Accelerometer (I2C 0x19)

| Register | Address | Size | Description |
|----------|---------|------|-------------|
| WHO_AM_I | 0x0F | 1 byte | Should read 0x33 |
| CTRL_REG1 | 0x20 | 1 byte | ODR, low-power enable, axes |
| OUT_X_L | 0x28 | 1 byte | X-axis low byte |
| OUT_X_H | 0x29 | 1 byte | X-axis high byte |
| OUT_Y_L | 0x2A | 1 byte | Y-axis low byte |
| OUT_Y_H | 0x2B | 1 byte | Y-axis high byte |
| OUT_Z_L | 0x2C | 1 byte | Z-axis low byte |
| OUT_Z_H | 0x2D | 1 byte | Z-axis high byte |

Config: ±2g range, 10-bit resolution, 50 Hz ODR (CTRL_REG1 = 0x47).

### 3.3 LPS25HB — Pressure Sensor (I2C 0x5D)

| Register | Address | Size | Description |
|----------|---------|------|-------------|
| WHO_AM_I | 0x0F | 1 byte | Should read 0xBD |
| CTRL_REG1 | 0x20 | 1 byte | ODR, block data update |
| PRESS_OUT_XL | 0x28 | 1 byte | Pressure LSB |
| PRESS_OUT_L | 0x29 | 1 byte | Pressure mid-byte |
| PRESS_OUT_H | 0x2A | 1 byte | Pressure MSB |
| TEMP_OUT_L | 0x2B | 1 byte | Temperature LSB |
| TEMP_OUT_H | 0x2C | 1 byte | Temperature MSB |

Pressure: 24-bit value. hPa = raw / 4096.
Config: 25 Hz ODR, block data update (CTRL_REG1 = 0xC0).

### 3.4 MAX17049 — Fuel Gauge (I2C 0x36)

| Register | Address | Size | Description |
|----------|---------|------|-------------|
| VCELL | 0x02 | 2 bytes | Battery voltage (78.125 µV/bit) |
| SOC | 0x04 | 2 bytes | State of charge (1/256% per bit) |
| MODE | 0x06 | 2 bytes | Quick-start, hibernate |
| VERSION | 0x08 | 2 bytes | IC version |
| CONFIG | 0x0C | 2 bytes | Sleep, alert configuration |

Voltage: V = raw × 78.125 µV
SOC: % = raw × (1/256)

---

## 4. GPS Interface

### 4.1 L76K Module — ✅ VERIFIED 2026-07-22

- **Module:** Seeed Studio L76K GNSS (Quectel L76K inside)
- **Interface:** UART0, 9600 baud, 8N1
- **Device:** `/dev/ttyS0` on Rock 2A
- **Active antenna powered by VDD_RF on module — no external bias-T needed**
- **Test result:** 8 satellites, 3D fix, antenna OK, 179 valid NMEA sentences in 15s
- **Unused features:** EASY (fast reacquisition), LOCUS (internal logger), configurable update rate (up to 10 Hz), AIC (interference cancellation). See SETUP.md §6.3.

### 4.2 NMEA Sentences Parsed

| Sentence | Fields used |
|----------|-------------|
| GGA | Time, lat, lon, fix quality, altitude, satellites in use |
| RMC | Time, lat, lon, speed over ground, track angle, date |
| GSV | Satellites in view (per constellation — parsed for count) |
| GSA | DOP values, active satellite PRNs |
| TXT | Antenna status ("ANTENNA OK") |
| ZDA | UTC date/time |

---

## 5. Test Phase — Independent Verification

**Principle:** Every piece tested in isolation before any integration. Four scripts, four passes.

### Phase 1A: I2C Bus Scan
**File:** `tests/test_i2c_scan.py`

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open `/dev/i2c-0` | Success |
| 2 | Scan addresses 0x03–0x77 | See 0x19 (LIS2DH), 0x48 (TMP100), 0x5D (LPS25HB) |
| 3 | Open `/dev/i2c-1` | Success |
| 4 | Scan addresses 0x03–0x77 | See 0x36 (MAX17049) |
| 5 | Print summary table | Bus 0: 3 devices. Bus 1: 1 device. |

### Phase 1B: Sensor Readback
**File:** `tests/test_sensors.py`

| Step | Action | Expected |
|------|--------|----------|
| 1 | Read TMP100 WHO_AM_I | Valid temperature register (no WHO_AM_I on TMP100 — read temp directly) |
| 2 | Read LIS2DH WHO_AM_I (0x0F) | 0x33 |
| 3 | Read LPS25HB WHO_AM_I (0x0F) | 0xBD |
| 4 | Read TMP100 temp | Reasonable value (~20–30°C indoors) |
| 5 | Read LIS2DH accel X/Y/Z | Reasonable values (Z ≈ 1g, X/Y ≈ 0) |
| 6 | Read LPS25HB pressure + temp | ~1013 hPa at sea level |
| 7 | Print all decoded values | — |

### Phase 1C: Fuel Gauge
**File:** `tests/test_fuel_gauge.py`

| Step | Action | Expected |
|------|--------|----------|
| 1 | Read MAX17049 VCELL (0x02) | Valid voltage (3.0–4.2V for LiPo) |
| 2 | Read MAX17049 SOC (0x04) | Valid percentage (0–100%) |
| 3 | Read VERSION (0x08) | Non-zero |
| 4 | Print battery voltage + SOC | — |

### Phase 1D: GPS NMEA — ✅ PASS (2026-07-22)
**File:** `tests/test_gps.py`

| Step | Action | Expected | Actual |
|------|--------|----------|--------|
| 1 | Open GPS UART at 9600 8N1 | Success | ✅ `/dev/ttyS0` |
| 2 | Read NMEA for 15 seconds | See GGA, RMC, GSV sentences | ✅ 180 lines, 179 valid |
| 3 | Parse one GGA sentence | Extract lat, lon, fix quality | ✅ 37°45.194'N 122°23.581'W, fix=1 |
| 4 | Parse one RMC sentence | Extract speed, track | ✅ 0.93 kn, 252.9° |
| 5 | Print fix status | 0=no fix, 1=GPS, 2=DGPS | ✅ GPS Fix (SPS), 8 satellites |

### Phase 1E: Camera
**File:** `tests/test_camera.py` — ⏳ NOT YET RUN (no USB camera connected)

### Phase 1F: DVB-S2 TX (Existing)
**Already tested** from `rf/dvbs2/`. No new code. Feed a pre-encoded TS → HackRF → ground station RX verifies demodulation.

---

## 6. Integration Phase — Data Pipeline

After all independent tests pass, wire them together.

### 6.1 Pipeline Architecture

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  Sensors │   │   GPS    │   │  Camera  │   │  Battery │
│  Python  │   │  Python  │   │  ffmpeg  │   │  Python  │
│  poller  │   │  reader  │   │  encoder │   │  reader  │
└────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘
     │              │              │               │
     │  sensor dict │  NMEA dict   │  H.264 ES     │  voltage/SOC
     │  (1 Hz)      │  (per fix)   │  (real-time)   │  (1 Hz)
     │              │              │               │
     ▼              ▼              │               │
┌────────────┐  ┌─────────┐        │               │
│  Pack into │  │ Convert │        │               │
│  binary    │  │ to dict │        │               │
│  struct    │  │          │        │               │
└─────┬──────┘  └────┬─────┘        │               │
      │              │              │               │
      ▼              ▼              ▼               ▼
┌──────────────────────────────────────────────────────┐
│                Telemetry Writer Thread                │
│  Packs sensors + GPS + battery into binary frames     │
│  Writes to /tmp/tel_fifo (named pipe)                 │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │  /tmp/tel_fifo │ ← Named pipe
              └───────┬────────┘
                      │
┌─────────────────────┼─────────────────────────────────┐
│                     ▼                                  │
│  ffmpeg TS Muxer                                      │
│                                                       │
│  -video: /dev/video0 → libx264 → PID 0x100            │
│  -data:  /tmp/tel_fifo → copy    → PID 0x200           │
│  -map:   video PID 0x100, data PID 0x200               │
│  -mux:   MPEG-TS, CBR, 965326 bps                     │
│                                                       │
│  Output → /tmp/tsfifo (named pipe)                    │
└──────────────────────┬───────────────────────────────┘
                       │
              ┌────────▼────────┐
              │  /tmp/tsfifo    │ ← Named pipe
              └────────┬────────┘
                       │
┌──────────────────────▼────────────────────────────────┐
│  dvbs2-tx (Python or GNU Radio)                       │
│                                                       │
│  --source fifo --in-file /tmp/tsfifo                   │
│  --sink hackrf --freq 913e6                           │
│  --sym-rate 1e6 --modcod QPSK1/2 --pilots             │
│                                                       │
│  Output → HackRF @ 913 MHz, 1 Msps                    │
└──────────────────────────────────────────────────────┘
```

### 6.2 Integration Orchestrator

**File:** `payload/main.py`

Responsibilities:
1. Create named pipes (`/tmp/tel_fifo`, `/tmp/tsfifo`)
2. Start telemetry writer thread (sensors + GPS + battery → binary frames → tel_fifo)
3. Start ffmpeg subprocess (camera + tel_fifo → TS → tsfifo)
4. Start dvbs2-tx subprocess (tsfifo → HackRF)
5. Monitor all components, restart on failure, graceful shutdown on SIGTERM

### 6.3 Telemetry Binary Frame Format

```
┌─────────┬─────────┬──────────┬─────────┬─────────┬──────┐
│  Magic  │ Seq #   │ Timestamp│ Temp    │ Pressure│ ...  │
│  2 bytes│ 2 bytes │ 4 bytes  │ 2 bytes │ 4 bytes │      │
│  0xFEED │ uint16  │ uint32   │ int16   │ uint32  │      │
└─────────┴─────────┴──────────┴─────────┴─────────┴──────┘
```

Frame rate: 1 Hz (one frame per sensor poll cycle).
Sent as a private data PID (0x200) in the MPEG-TS stream.

### 6.4 ffmpeg Command (planned)

```bash
ffmpeg \
  -f v4l2 -video_size 640x480 -framerate 15 -i /dev/video0 \
  -c:v libx264 -preset ultrafast -tune zerolatency \
  -b:v 700k -maxrate 700k -bufsize 350k \
  -pix_fmt yuv420p -g 30 \
  -f data -i /tmp/tel_fifo -c:d copy \
  -map 0:v -map 1:d \
  -f mpegts \
  -muxrate 965326 \
  -streamid 0:0x100 -streamid 1:0x200 \
  -mpegts_flags +resend_headers \
  /tmp/tsfifo
```

---

## 7. Repository Structure

```
hab/payload/
├── PLAN.md                  ← This document (design + architecture)
├── SETUP.md                 ← Hardware bringup reference (overlays, udev, GPIO, GPS config)
├── requirements.txt         ← Python dependencies (smbus2, pyserial)
├── main.py                  ← Integration orchestrator (Phase 2)
├── .gitignore
├── sensors/
│   ├── __init__.py
│   ├── tmp100.py           ← TMP100 driver
│   ├── lis2dh.py           ← LIS2DH driver
│   ├── lps25hb.py          ← LPS25HB driver
│   └── max17049.py         ← MAX17049 driver
├── gps/
│   ├── __init__.py
│   └── nmea.py             ← NMEA parser + L76K reader
├── telemetry/
│   ├── __init__.py
│   ├── packer.py           ← Binary frame packer
│   └── writer.py           ← Writes frames to tel_fifo
├── camera/
│   ├── __init__.py
│   └── capture.py          ← Camera config + frame grab
├── tx/
│   ├── __init__.py
│   └── tx_pipeline.py      ← ffmpeg + dvbs2-tx launcher
└── tests/
    ├── test_i2c_scan.py    ← Phase 1A
    ├── test_sensors.py     ← Phase 1B
    ├── test_fuel_gauge.py  ← Phase 1C
    ├── test_gps.py         ← Phase 1D
    └── test_camera.py      ← Phase 1E
```

---

## 8. Dependencies (Rock 2A — Armbian Debian 13)

### System packages
```
python3 python3-pip python3-venv
i2c-tools               # i2cdetect for debugging
ffmpeg                  # Video encode + TS mux
hackrf                  # HackRF tools + libhackrf
gnuradio                # For dvbs2-tx (if using GNU Radio flowgraph)
```

### Python packages
```
smbus2      # I2C on Linux
pyserial    # UART for GPS
```

### Notes
- The Rock 2A runs Armbian Debian 13 (Trixie) — `apt` has all of these.
- `smbus2` is a pure-Python library; it uses the kernel I2C device (`/dev/i2c-N`), no kernel modules needed beyond the Rockchip I2C driver (included in vendor kernel).
- `gnuradio` may be heavyweight — if `dvbs2-tx` is the standalone Python implementation from `rf/dvbs2/`, GNU Radio may not be needed on the payload. The plan defers to whatever `tx.py` requires.

---

## 9. Power Budget (Estimated)

| Component | Current Draw | Notes |
|-----------|-------------|-------|
| Rock 2A idle | ~400 mA @ 5V (2W) | A53 quad, headless, Ethernet up |
| Rock 2A under load | ~800 mA @ 5V (4W) | ffmpeg + SDR TX |
| HackRF TX | ~350 mA @ 5V (1.75W) | TX mode at +0 dBm |
| USB Camera | ~200 mA @ 5V (1W) | Typical UVC webcam |
| GPS + Sensors | ~50 mA @ 3.3V | L76K active antenna |
| **Total** | **~7W** | **~1.4A @ 5V** |

Battery sizing: 4S LiPo (14.8V) → 5V buck converter. For a 3-hour flight: ~21 Wh. 4S 2000 mAh = ~30 Wh — good with margin.

---

## 10. Build Order

1. **Phase 1A–1E:** Write and test all independent test scripts on the Rock 2A
2. **Phase 2:** Write sensor drivers (`sensors/*.py`)
3. **Phase 3:** Write GPS reader (`gps/nmea.py`)
4. **Phase 4:** Write telemetry packer + writer (`telemetry/*.py`)
5. **Phase 5:** Write camera capture (`camera/capture.py`)
6. **Phase 6:** Write integration orchestrator (`main.py`)
7. **Phase 7:** Write DVB-S2 TX launcher (`tx/tx_pipeline.py`)
8. **Phase 8:** End-to-end bench test — HackRF TX → ground station RX → verify video + telemetry

---

## 11. Packet Radio Path — GPS-Only (2026-07-21)

> **Status:** BUILDING — parallel to the DVB-S2 path. This is the "get data flowing now" pipeline.

### 11.1 Architecture

The DVB-S2 path (sections 1–10) requires ffmpeg + video camera + MPEG-TS muxing + dvbs2-tx. This path runs in parallel:
GPS-only BPSK packet radio using the validated `rf/packet/` baseline, feeding the existing dashboard.

```
Rock 2A (TX)                              Mac (RX)
─────────────                             ────────
GPS L76K                                   HackRF clone (60a464dc3606610f)
  │                                          │
  ▼                                          ▼
nmea.py (parse GGA/RMC)                  pkt_simple_rx.py (UNTOCUHED)
  │  +HDOP field                            BPSK decode → "[PktRx] #N | '...'"
  ▼                                          │
packet_format.py (NEW)                      ▼
  type-tagged binary frame                gps_bridge.py (NEW)
  e.g. 0x01 + position fields              parse stdout → unpack → JSON
  │                                          │
  ▼                                          ▼
gps_packet_tx.py (NEW)                    POST /api/packet
  Build BPSK packet waveform                │
  GNU Radio vector_source → SoapySDR        ▼
  (same chain as pkt_simple_tx.py)        dashboard (EXISTING)
         │                                  FastAPI :8000
         └────────── 915 MHz ──────────────► React SPA + map
```

### 11.2 On-Air Payload Format

Each packet wraps in the BPSK outer frame (256b preamble + 32b sync 0xE38FC0FC + 16b length + CRC-16/XMODEM). The *payload* uses typed binary frames:

**Type 0x01 — Position (38 bytes):**
```
u8   type = 0x01
u16  seq
f64  lat (IEEE 754)
f64  lon
f32  alt_m
f32  agl_m
u8   fix (0/1)
u8   fix_type (0=none, 1=2d, 2=3d)
u8   sats
f32  hdop
f32  vdop
```

**Future:** 0x02=motion (52B), 0x03=environment (28B), 0x04=power (20B).

Common fields (v, id, mid, t) are added by the bridge — constant per mission.

### 11.3 Key Design Decisions

| Decision | Rationale |
|---|---|
| GNU Radio + SoapySDR on Rock 2A | Same validated BPSK chain as `pkt_simple_tx.py`; available in Debian repos |
| Same packet format as baseline | 256b preamble + 32b sync 0xE38FC0FC + CRC-16/XMODEM — validated 36/36 tests |
| Bridge bypasses receiver_manager | `receiver_manager.py` was stubbed for `[EnhancedRX]` format. Bridge POSTs to `/api/packet` directly |
| Separate from packer.py | `packer.py` (54B struct) stays for DVB-S2 PID injection. Packet radio uses typed binary frames |
| 1 Hz burst | ~64 ms air time per packet, ~936 ms idle. Power-efficient |
| Battery read every 5th frame | MAX17049 on I2C1 works; type 0x04 power packets interleaved |

### 11.4 Gaps Resolved From Original Plan

| Original gap | Resolution |
|---|---|
| I2C bus0 sensors broken | Not needed — GPS-only path uses position frames |
| GNU Radio on Rock 2A | `apt install gnuradio soapysdr-module-hackrf` — same stack as Mac |
| Dashboard format mismatch | Bridge translates binary → JSON per type |

### 11.5 Files

| File | Status | Purpose |
|---|---|---|
| `payload/telemetry/packet_format.py` | NEW | Type-tagged binary frame pack/unpack |
| `payload/gps/nmea.py` | PATCH | Add HDOP extraction from GGA field 8 |
| `payload/tx/gps_packet_tx.py` | NEW | GPS→frame→BPSK→hackrf_transfer |
| `rf/packet/gps_bridge.py` | NEW | RX stdout→unpack→POST /api/packet |
| `payload/telemetry/packer.py` | KEEP | DVB-S2 path only, not modified |

---

## 12. Open Questions

- [x] **GPS device path:** ~~Is it `/dev/ttyS2` on the Rock 2A?~~ → Resolved: `/dev/ttyS0` (UART0 M0). See SETUP.md §6.1 for FIQ debugger saga.
- [x] **GPS functionality:** ~~No NMEA output?~~ → Resolved: 8 satellites, 3D fix, antenna OK. FIQ debugger was consuming UART data.
- [ ] **Sensors on I2C bus 0:** TMP100, LIS2DH, LPS25HB not responding — confirmed broken hardware. Replace sensors.
- [ ] **Camera device:** Is it `/dev/video0`? Verify with `v4l2-ctl --list-devices`.
- [ ] **dvbs2-tx implementation:** Does the existing `rf/dvbs2/` use GNU Radio or standalone Python? Do we need to install gnuradio on the payload?
- [ ] **Battery type:** What's the actual battery pack (voltage, capacity)? Update power budget section.
- [ ] **Camera model:** Which USB camera? Update resolution + format constraints.
- [ ] **Link budget:** Has the DVB-S2 link budget been calculated for the expected altitude and antenna configuration?

---

## 13. References

- Rock 2A schematic / netlist — pin mapping source
- Quectel L76K datasheet — GPS module specs
- TMP100, LIS2DH, LPS25HB, MAX17049 datasheets — sensor register maps
- DVB-S2 TX (`hab/rf/dvbs2/`) — existing ground station code
