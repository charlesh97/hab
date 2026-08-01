# Balloon Telemetry Simulator 🎈

A standalone terminal app that mimics the HAB balloon's telemetry stream. Sends
realistic packet data to the dashboard/server's `POST /api/packet` endpoint so
the web dashboard displays live, believable data without RF hardware.

## Usage

```bash
# Normal speed (~2 hours real-time for full mission)
./sim.py

# Fast mode — 10x speed (full mission in ~13 minutes)
./sim.py --fast

# Point at a different server
./sim.py --host 192.168.1.50 --port 8000

# Skip to a specific flight phase
./sim.py --start-at float
./sim.py --start-at descent

# Quick launcher (runs fast mode)
./run.sh
```

## Flight Profile

| Phase   | Duration (1x) | Duration (10x) | Altitude      | Vertical Speed |
|---------|---------------|----------------|---------------|----------------|
| Ascent  | ~60 min       | ~6 min         | 0 → 18,000m  | ~5 m/s         |
| Float   | ~30 min       | ~3 min         | ~18,000m     | ±0.5 m/s       |
| Descent | ~38 min       | ~4 min         | 18,000 → 0m  | ~-8 m/s        |

Total mission time: ~2.1 hours real-time, ~13 minutes in fast mode.

## Data Format

Packets POST to `http://<host>:<port>/api/packet` with body:
```json
{"data": { ...packet... }}
```

Four packet types are sent in round-robin order, one per second:

### Position (every 4th packet)
Maps to dashboard's `PositionData` and `TelemetrySample.lat/lng/altitude/gpsSats`.
```json
{"v":1, "id":"HAB-001", "mid":"SIM", "seq":1, "t":"T12:34:56", "type":"position",
 "lat":39.3187, "lon":-120.3289, "alt_m":18342.7, "agl_m":17210.3,
 "fix":true, "fix_type":"3d", "sats":14, "hdop":0.82, "vdop":1.34}
```

### Motion (every 4th packet)
Maps to dashboard's `MotionData` and `TelemetrySample.verticalSpeed/groundSpeed/heading`.
```json
{"v":1, "id":"HAB-001", "mid":"SIM", "seq":2, "t":"T12:34:57", "type":"motion",
 "gs_mps":13.8, "vs_mps":5.4, "heading_deg":72.6, "cog_deg":74.1,
 "accel":{"x":0.03,"y":-0.08,"z":9.71},
 "gyro_dps":{"r":0.4,"p":-0.2,"y":1.1},
 "att_deg":{"roll":2.8,"pitch":-4.1,"yaw":71.9}}
```

### Environment (every 4th packet)
Maps to dashboard's `EnvironmentData` and `TelemetrySample.externalTemp/internalTemp/pressure`.
```json
{"v":1, "id":"HAB-001", "mid":"SIM", "seq":3, "t":"T12:34:58", "type":"environment",
 "temp_ext_c":-42.6, "temp_int_c":12.4, "pressure_hpa":72.8,
 "humidity_pct":4.2, "baro_alt_m":18190.5}
```

### Power (every 4th packet)
Maps to dashboard's `PowerData` and `TelemetrySample.battery`.
```json
{"v":1, "id":"HAB-001", "mid":"SIM", "seq":4, "t":"T12:34:59", "type":"power",
 "bat_v":7.62, "bat_a":0.84, "bat_w":6.4, "bat_pct":68,
 "bat_temp_c":8.1, "rails_v":{"v5":5.03,"v3v3":3.31,"v1v8":1.79}}
```

## Data Alignment

Every field in these packets maps 1:1 to what the dashboard's WebSocket handler
(`useHabApi.ts`) expects. The existing `type`-based dispatch handles position,
motion, environment, and power branches correctly. No dashboard changes needed.

## Prerequisites

- Python 3.8+ (standard library only — no pip dependencies)
- Receiver server must be running with `POST /api/packet` available
