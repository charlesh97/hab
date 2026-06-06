# Balloon Telemetry Simulator — Design Spec

## Goal

Create a standalone terminal application that mimics the HAB balloon's telemetry stream, sending realistic packet data to the dashboard/server's existing `POST /api/packet` endpoint so the web dashboard displays live, realistic data.

## Architecture

```
dashboard/sim/
  sim.py      # Terminal app generating realistic telemetry
  README.md   # Data format documentation + usage
  run.sh      # One-click launch script
```

No server or dashboard changes needed — the `POST /api/packet` endpoint and `ingest_packet()` broadcast path already exist.

## Data Format

Each POST body: `{"data": { ...packet... }}`

Packets are sent in round-robin order: position → motion → environment → power, one per second.

### Position Packet
Sent every 4th packet. Fields match dashboard's `PositionData` type.
```json
{
  "v": 1, "id": "HAB-001", "mid": "SIM", "seq": 1,
  "t": "T12:34:56", "type": "position",
  "lat": 39.3187, "lon": -120.3289, "alt_m": 18342.7, "agl_m": 17210.3,
  "fix": true, "fix_type": "3d", "sats": 14,
  "hdop": 0.82, "vdop": 1.34
}
```
Dashboard consumes: `lat`, `lon`, `alt_m` → TelemetrySample.lat/lng/altitude/gpsSats

### Motion Packet
Sent every 4th packet. Matches `MotionData` type.
```json
{
  "v": 1, "id": "HAB-001", "mid": "SIM", "seq": 2,
  "t": "T12:34:57", "type": "motion",
  "gs_mps": 13.8, "vs_mps": 5.4, "heading_deg": 72.6, "cog_deg": 74.1,
  "accel": {"x": 0.03, "y": -0.08, "z": 9.71},
  "gyro_dps": {"r": 0.4, "p": -0.2, "y": 1.1},
  "att_deg": {"roll": 2.8, "pitch": -4.1, "yaw": 71.9}
}
```
Dashboard consumes: `gs_mps` → TelemetrySample.groundSpeed, `vs_mps` → verticalSpeed, `heading_deg` → heading

### Environment Packet
Sent every 4th packet. Matches `EnvironmentData` type.
```json
{
  "v": 1, "id": "HAB-001", "mid": "SIM", "seq": 3,
  "t": "T12:34:58", "type": "environment",
  "temp_ext_c": -42.6, "temp_int_c": 12.4, "pressure_hpa": 72.8,
  "humidity_pct": 4.2, "baro_alt_m": 18190.5
}
```
Dashboard consumes: `temp_ext_c` → externalTemp, `temp_int_c` → internalTemp, `pressure_hpa` → pressure

### Power Packet
Sent every 4th packet. Matches `PowerData` type.
```json
{
  "v": 1, "id": "HAB-001", "mid": "SIM", "seq": 4,
  "t": "T12:34:59", "type": "power",
  "bat_v": 7.62, "bat_a": 0.84, "bat_w": 6.4, "bat_pct": 68,
  "bat_temp_c": 8.1,
  "rails_v": {"v5": 5.03, "v3v3": 3.31, "v1v8": 1.79}
}
```
Dashboard consumes: `bat_pct` → TelemetrySample.battery

## Flight Profile

The sim models a realistic balloon mission with 3 phases:

| Phase | Duration | Altitude | Vertical Speed |
|-------|----------|----------|----------------|
| Ascent | ~60 min | 0 → 18,000m | ~5 m/s |
| Float | ~30 min | ~18,000m | ±0.5 m/s |
| Descent | ~38 min | 18,000 → 0m | ~-8 m/s |

Additional realism:
- Position drifts eastward (prevailing winds at altitude)
- GPS sats oscillate 10-16
- External temp drops with altitude (-60°C at float)
- Battery gradually drains 100% → ~60%
- Internal temp stable around 15°C
- Pressure follows barometric formula

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | localhost | Receiver server host |
| `--port` | 8000 | Receiver server port |
| `--fast` | off | 10x speed for testing |
| `--start-at` | ascent | `ascent`, `float`, or `descent` |

## Data Alignment Review

All data fields sent by balloon-sim.py map 1:1 to fields consumed by the dashboard's `useHabApi.ts` WebSocket handler. No transformation needed — the existing `type`-based dispatch in `ws.onmessage` handles position/motion/environment/power branches correctly. The `TelemetrySample` aggregation in `setCurrent()` aggregates across all 4 packet types as they arrive.

## Files

| Path | Purpose |
|------|---------|
| `dashboard/sim/sim.py` | Terminal app |
| `dashboard/sim/README.md` | Data format docs + usage |
| `dashboard/sim/run.sh` | One-click launcher |

## Verification

1. `python sim.py` starts sending packets at ~1 Hz
2. `curl -s localhost:8000/api/packets` returns accumulated packets
3. Dashboard connects to WS and shows updating telemetry cards
4. Phase transitions visible in TopBar as altitude changes
