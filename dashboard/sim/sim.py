#!/usr/bin/env python3
"""
HAB Balloon Telemetry Simulator

Sends realistic balloon flight telemetry to the HAB receiver server's
POST /api/packet endpoint. Models a complete balloon mission profile:
ascent (~60 min), float (~30 min), descent (~38 min).

Usage:
    ./sim.py                          # localhost:8000
    ./sim.py --host 192.168.1.5       # remote receiver
    ./sim.py --fast                   # 10x speed (mission in ~13 min)
    ./sim.py --start-at float         # skip to float phase
    ./sim.py --start-at descent       # skip to descent phase
"""

import argparse
import json
import math
import random
import time
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError


# ── Constants ──────────────────────────────────────────────────────────────

FLIGHT_PROFILE = {
    "ascent":  {"alt_start": 0, "alt_end": 18000, "vs": 5.0,  "duration_s": 3600},
    "float":   {"alt_start": 18000, "alt_end": 18000, "vs": 0.0, "duration_s": 1800},
    "descent": {"alt_start": 18000, "alt_end": 0,     "vs": -8.0,"duration_s": 2250},
}

BAROMETRIC_LAPSE = 0.0065           # K/m — temperature drop with altitude
SEA_LEVEL_PRESSURE = 1013.25        # hPa
SEA_LEVEL_TEMP = 15.0               # °C
PRESSURE_SCALE_HEIGHT = 8430        # m

INITIAL_BATTERY = 100.0
FINAL_BATTERY = 60.0
TOTAL_MISSION_S = sum(p["duration_s"] for p in FLIGHT_PROFILE.values())  # 7650 s (~2.1h)


# ── Telemetry Generators ───────────────────────────────────────────────────

def barometric_pressure(alt_m: float) -> float:
    """Approximate barometric pressure at altitude."""
    return SEA_LEVEL_PRESSURE * math.exp(-alt_m / PRESSURE_SCALE_HEIGHT)


def exterior_temp(alt_m: float) -> float:
    """Tropospheric temperature lapse rate approximation."""
    return SEA_LEVEL_TEMP - BAROMETRIC_LAPSE * alt_m


def make_position(seq: int, mission_s: float, alt_m: float) -> dict:
    """Generate a position packet with realistic drift."""
    base_lat, base_lon = 39.3187, -120.3289
    # Slow eastward drift (prevailing winds at altitude)
    lon_drift = mission_s / 3600 * 1.5   # ~1.5 degrees per hour east
    lat_wobble = random.uniform(-0.005, 0.005)
    lon_wobble = random.uniform(-0.005, 0.005)

    # AG is ~95% of MSL altitude during ascent/descent, slightly less at float
    agl_factor = 0.85 + random.uniform(0.05, 0.1)

    sats = random.randint(10, 16)

    return {
        "v": 1, "id": "HAB-001", "mid": "SIM", "seq": seq,
        "t": ts_now(), "type": "position",
        "lat": round(base_lat + lat_wobble, 5),
        "lon": round(base_lon + lon_drift + lon_wobble, 5),
        "alt_m": round(alt_m, 1),
        "agl_m": round(alt_m * agl_factor, 1),
        "fix": True, "fix_type": "3d", "sats": sats,
        "hdop": round(random.uniform(0.5, 1.5), 2),
        "vdop": round(random.uniform(0.8, 2.0), 2),
    }


def make_motion(seq: int, vs: float, mission_s: float) -> dict:
    """Generate a motion/inertial packet."""
    # Ground speed increases with altitude (jet stream effects)
    gs_base = min(5.0 + mission_s / 300, 25.0)
    heading = (90 + 15 * math.sin(mission_s / 600)) % 360  # oscillate around east

    return {
        "v": 1, "id": "HAB-001", "mid": "SIM", "seq": seq,
        "t": ts_now(), "type": "motion",
        "gs_mps": round(random.uniform(gs_base - 2, gs_base + 2), 2),
        "vs_mps": round(vs + random.uniform(-0.3, 0.3), 2),
        "heading_deg": round(heading + random.uniform(-5, 5), 1),
        "cog_deg": round(heading + random.uniform(-3, 3), 1),
        "accel": {
            "x": round(random.uniform(-0.05, 0.05), 3),
            "y": round(random.uniform(-0.05, 0.05), 3),
            "z": round(random.uniform(9.6, 9.8), 3),
        },
        "gyro_dps": {
            "r": round(random.uniform(-0.5, 0.5), 2),
            "p": round(random.uniform(-0.5, 0.5), 2),
            "y": round(random.uniform(-0.5, 0.5), 2),
        },
        "att_deg": {
            "roll": round(random.uniform(-3, 3), 2),
            "pitch": round(random.uniform(-3, 3), 2),
            "yaw": round(heading + random.uniform(-2, 2), 1),
        },
    }


def make_environment(seq: int, alt_m: float) -> dict:
    """Generate an environment/sensor packet."""
    ext_temp = exterior_temp(alt_m) + random.uniform(-2, 2)
    int_temp = 15.0 + random.uniform(-1, 1)  # insulated interior stays stable
    pressure = barometric_pressure(alt_m) * random.uniform(0.97, 1.03)
    humidity = random.uniform(2, 15)

    return {
        "v": 1, "id": "HAB-001", "mid": "SIM", "seq": seq,
        "t": ts_now(), "type": "environment",
        "temp_ext_c": round(ext_temp, 1),
        "temp_int_c": round(int_temp, 1),
        "pressure_hpa": round(pressure, 1),
        "humidity_pct": round(humidity, 1),
        "baro_alt_m": round(barometric_pressure(alt_m) / SEA_LEVEL_PRESSURE
                            * PRESSURE_SCALE_HEIGHT, 1),
    }


def make_power(seq: int, mission_s: float) -> dict:
    """Generate a power system packet with gradual battery drain."""
    battery_pct = INITIAL_BATTERY - (INITIAL_BATTERY - FINAL_BATTERY) * (
        mission_s / TOTAL_MISSION_S
    )
    battery_pct = max(FINAL_BATTERY, min(INITIAL_BATTERY, battery_pct))
    bat_v = 8.2 - (INITIAL_BATTERY - battery_pct) * 0.01  # slight voltage sag
    bat_a = 0.7 + random.uniform(0.1, 0.3)
    bat_w = bat_v * bat_a
    bat_temp = 8.0 + random.uniform(-1, 2)

    return {
        "v": 1, "id": "HAB-001", "mid": "SIM", "seq": seq,
        "t": ts_now(), "type": "power",
        "bat_v": round(bat_v, 3),
        "bat_a": round(bat_a, 2),
        "bat_w": round(bat_w, 2),
        "bat_pct": int(round(battery_pct)),
        "bat_temp_c": round(bat_temp, 1),
    }


# ── Flight Profile Engine ──────────────────────────────────────────────────

class BalloonFlight:
    """Models the balloon's position over time through 3 flight phases."""

    def __init__(self, start_phase: str = "ascent"):
        self.mission_s = 0.0
        self.altitude = 0.0
        self.vertical_speed = 0.0
        self.current_phase = start_phase
        self.phase_offset_s = 0.0

    def advance(self, dt: float):
        """Advance the flight model by dt seconds."""
        self.mission_s += dt

        phase = self._get_phase()

        if phase == "ascent":
            self.vertical_speed = FLIGHT_PROFILE["ascent"]["vs"]
            self.altitude += self.vertical_speed * dt
            if self.altitude >= FLIGHT_PROFILE["ascent"]["alt_end"]:
                self.altitude = FLIGHT_PROFILE["ascent"]["alt_end"]
                self.current_phase = "float"

        elif phase == "float":
            self.vertical_speed = random.uniform(-0.5, 0.5)
            self.altitude += self.vertical_speed * dt
            # Clamp around float altitude
            self.altitude = max(17500, min(18500, self.altitude))

        elif phase == "descent":
            self.vertical_speed = FLIGHT_PROFILE["descent"]["vs"]
            self.altitude += self.vertical_speed * dt
            if self.altitude <= FLIGHT_PROFILE["descent"]["alt_end"]:
                self.altitude = FLIGHT_PROFILE["descent"]["alt_end"]
                self.vertical_speed = 0.0

        self.altitude = max(0, self.altitude)
        self.vertical_speed = round(self.vertical_speed, 2)

    def _get_phase(self) -> str:
        return self.current_phase


def ts_now() -> str:
    """Return current time as T12:34:56 format."""
    return datetime.now(timezone.utc).strftime("T%H:%M:%S")


# ── HTTP Client ────────────────────────────────────────────────────────────

def send_packet(host: str, port: int, packet: dict) -> bool:
    """POST a single packet to the receiver server. Returns True on success."""
    url = f"http://{host}:{port}/api/packet"
    body = json.dumps({"data": packet}).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except URLError as e:
        print(f"  ⚠  Send failed: {e.reason}", flush=True)
        return False


# ── Main Loop ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HAB Balloon Telemetry Simulator")
    parser.add_argument("--host", default="localhost", help="Receiver server host")
    parser.add_argument("--port", type=int, default=8000, help="Receiver server port")
    parser.add_argument("--fast", action="store_true",
                        help="Run at 10x speed (mission in ~13 min)")
    parser.add_argument("--start-at", default="ascent",
                        choices=["ascent", "float", "descent"],
                        help="Mission phase to start at")
    args = parser.parse_args()

    print(f"🎈 HAB Balloon Telemetry Simulator")
    print(f"   Target:  http://{args.host}:{args.port}/api/packet")
    print(f"   Speed:   {'10x (fast mode)' if args.fast else '1x (real-time)'}")
    print(f"   Phase:   {args.start_at}")
    print(f"   Ctrl-C to stop\n", flush=True)

    flight = BalloonFlight(start_phase=args.start_at)

    # If starting mid-flight, skip to the right altitude
    if args.start_at == "float":
        flight.altitude = 18000
    elif args.start_at == "descent":
        flight.altitude = 18000

    seq = 1
    tick = 0          # cycles through 4 packet types
    dt = 1.0           # seconds per tick (real-time)
    phase_reported = None

    generators = [make_position, make_motion, make_environment, make_power]

    try:
        while True:
            # Advance flight model
            flight.advance(dt)

            # Report phase transitions
            if flight.current_phase != phase_reported:
                phase_label = flight.current_phase.upper()
                print(f"   [{phase_label}] alt={flight.altitude:.0f}m  "
                      f"vs={flight.vertical_speed:.1f}m/s  "
                      f"t={flight.mission_s:.0f}s", flush=True)
                phase_reported = flight.current_phase

            # Generate the current packet type
            gen = generators[tick % len(generators)]
            if gen == make_position:
                packet = make_position(seq, flight.mission_s, flight.altitude)
            elif gen == make_motion:
                packet = make_motion(seq, flight.vertical_speed, flight.mission_s)
            elif gen == make_environment:
                packet = make_environment(seq, flight.altitude)
            else:
                packet = make_power(seq, flight.mission_s)

            # Send
            ok = send_packet(args.host, args.port, packet)
            status = "✓" if ok else "✗"
            pkt_type = packet["type"].ljust(12)
            print(f"   [{status}] #{seq:05d} {pkt_type}"
                  f"  alt={flight.altitude:.0f}m  "
                  f"bat={packet.get('bat_pct', '—')}%  "
                  f"temp={packet.get('temp_ext_c', '—')}°C",
                  flush=True)

            seq += 1
            tick += 1

            # Sleep until next tick (fast mode = 0.1s)
            sleep_s = dt / (10 if args.fast else 1)
            time.sleep(sleep_s)

    except KeyboardInterrupt:
        print(f"\n   ✋ Stopped after {seq - 1} packets, "
              f"{flight.mission_s:.0f}s simulated mission time", flush=True)


if __name__ == "__main__":
    main()
