#!/usr/bin/env python3
"""Balloon Telemetry Simulator — realistic HAB flight data for ground-station testing.

Connects to the receiver-server at /api/packet and generates a complete
balloon flight profile (ascent → float → descent) at ~1 Hz, cycling through
all 4 telemetry types: position, motion, environment, power.

Usage:
    ./balloon-sim.py                        # localhost:8000, 1× speed
    ./balloon-sim.py --host 10.0.0.5        # remote server
    ./balloon-sim.py --fast                 # 10× speed
    ./balloon-sim.py --profile descent      # start from descent
    ./balloon-sim.py --rate 2               # 2 packets/sec
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time

try:
    import requests
except ImportError:
    print("❌ 'requests' not found.  Install:  pip install requests")
    sys.exit(1)


# ── Flight constants ──────────────────────────────────────────────────────────

LAT_START = 38.5747     # Sacramento area (California)
LON_START = -121.4930
ALT_MAX = 18_000.0       # float altitude (m)
ALT_ASCENT_RATE = 5.0    # m/s
ALT_DESCENT_RATE = 8.0   # m/s
TEMP_INT_C = 15.0        # internal temperature stays stable

BATTERY_START = 100.0      # %
BATTERY_END = 60.0         # % at end of flight

# Balloon ID / mission ID
BALLOON_ID = "HAB-001"
MISSION_ID = "SIM"


# ── Standard-atmosphere helpers ───────────────────────────────────────────────

def _pressure_at(alt_m: float) -> float:
    """Approximate pressure (hPa) at altitude using the 1976 US Std Atmosphere."""
    h = alt_m / 1000.0            # km
    if h <= 11.0:
        p = 1013.25 * (1.0 - 0.0225577 * h) ** 5.2559
    else:
        p = 226.32 * math.exp(-(h - 11.0) / 6.342)
    return round(p, 2)


def _temp_ext_at(alt_m: float) -> float:
    """Approximate external temperature (°C) at altitude."""
    h = alt_m / 1000.0
    if h <= 11.0:
        t = 15.0 - 6.5 * h
    else:
        t = -56.5
    return round(t, 2)


# ── Balloon state machine ─────────────────────────────────────────────────────

class BalloonSimulator:
    """Stateful balloon flight simulator.

    Manages a realistic flight profile with three phases:

        Ascent   –  ~5 m/s  from 0 → 18 000 m  (~60 min)
        Float    –  drift at 18 000 m          (~15 min)
        Descent  –  ~8 m/s  back toward ground (~38 min)

    Each call to :meth:`tick` advances the flight state by *dt* seconds and
    returns a single telemetry packet (cycling through the 4 types).
    """

    def __init__(self, profile: str = "ascent"):
        # Flight state
        self.seq = 0                       # total packets sent
        self.phase = "ascent"              # ascent | float | descent
        self.flight_time = 0.0             # elapsed seconds
        self._type_idx = 0                 # cycles 0,1,2,3 → pos,motion,env,pwr

        # Dynamic values
        self.alt_m = 0.0
        self.lat = LAT_START
        self.lon = LON_START
        self.vs_mps = ALT_ASCENT_RATE      # vertical speed
        self.gs_mps = 2.0                  # ground speed — ramps up with altitude
        self.heading_deg = 90.0            # east
        self.cog_deg = 90.0
        self.bat_pct = 100.0
        self._phase_entered = 0.0          # time current phase started

        if profile == "descent":
            self.alt_m = ALT_MAX
            self.vs_mps = -ALT_DESCENT_RATE
            self.gs_mps = 22.0
            self.bat_pct = 75.0
            self.flight_time = 4200.0
            self.phase = "descent"
            self._phase_entered = 4200.0
        elif profile == "float":
            self.alt_m = ALT_MAX
            self.vs_mps = 0.0
            self.gs_mps = 22.0
            self.bat_pct = 82.0
            self.flight_time = 3600.0
            self.phase = "float"
            self._phase_entered = 3600.0
        # else "ascent" – start from zero as above

    # ── helpers ──────────────────────────────────────────────────────────

    def _timestamp(self) -> str:
        return time.strftime("T%H:%M:%S", time.gmtime())

    def _jitter(self, base: float, pct: float = 5.0) -> float:
        return base + base * random.uniform(-pct / 100, pct / 100)

    def _lat_lon_from_speed(self, gs: float, hdg: float, dt: float) -> tuple[float, float]:
        """Advance lat/lon given ground speed (m/s) and heading (degrees)."""
        lat_r = math.radians(self.lat)
        d_north = gs * dt * math.cos(math.radians(hdg))   # m north
        d_east  = gs * dt * math.sin(math.radians(hdg))    # m east
        dlat = d_north / 111_111.0
        dlon = d_east / (111_111.0 * math.cos(lat_r))
        return self.lat + dlat, self.lon + dlon

    # ── packet generators ───────────────────────────────────────────────

    def _common(self) -> dict:
        self.seq += 1
        return {
            "v": 1,
            "id": BALLOON_ID,
            "mid": MISSION_ID,
            "seq": self.seq,
            "t": self._timestamp(),
        }

    def _make_position(self) -> dict:
        fix = self.alt_m > 20
        if fix:
            sats = random.randint(12, 16)
            fix_type = "3d" if sats >= 4 else "2d"
        else:
            sats = random.randint(4, 10)
            fix_type = "2d"
        return {
            **self._common(),
            "type": "position",
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "alt_m": round(self.alt_m, 2),
            "agl_m": round(max(self.alt_m - 10, 0), 2),
            "fix": fix,
            "fix_type": fix_type,
            "sats": sats,
            "hdop": round(random.uniform(0.6, 1.6), 2),
            "vdop": round(random.uniform(0.9, 2.1), 2),
        }

    def _make_motion(self) -> dict:
        return {
            **self._common(),
            "type": "motion",
            "gs_mps": round(self.gs_mps + random.uniform(-0.5, 0.5), 3),
            "vs_mps": round(self.vs_mps + random.uniform(-0.3, 0.3), 3),
            "heading_deg": round(self.heading_deg + random.uniform(-2, 2), 2),
            "cog_deg": round(self.cog_deg + random.uniform(-2, 2), 2),
            "accel": {
                "x": round(random.uniform(-0.05, 0.05), 3),
                "y": round(random.uniform(-0.05, 0.05), 3),
                "z": round(9.81 + random.uniform(-0.02, 0.02), 3),
            },
            "gyro_dps": {
                "r": round(random.uniform(-0.5, 0.5), 2),
                "p": round(random.uniform(-0.5, 0.5), 2),
                "y": round(random.uniform(-1, 1), 2),
            },
            "att_deg": {
                "roll": round(random.uniform(-3, 3), 2),
                "pitch": round(random.uniform(-3, 3), 2),
                "yaw": round(self.heading_deg + random.uniform(-5, 5), 2),
            },
        }

    def _make_environment(self) -> dict:
        pressure = _pressure_at(self.alt_m)
        temp_ext = _temp_ext_at(self.alt_m)
        # humidity drops at altitude; small residual at float
        h = max(2.0, 45.0 * math.exp(-self.alt_m / 5000.0))
        return {
            **self._common(),
            "type": "environment",
            "temp_ext_c": temp_ext,
            "temp_int_c": round(TEMP_INT_C + random.uniform(-1, 1), 2),
            "pressure_hpa": pressure,
            "humidity_pct": round(random.uniform(h - 1, h + 1), 2),
            "baro_alt_m": round(self.alt_m + random.uniform(-50, 50), 2),
        }

    def _make_power(self) -> dict:
        # Battery voltage droops with remaining charge
        soc = self.bat_pct / 100.0
        v_nom = 7.4 + (soc - 0.5) * 1.2        # 6.8 V @ 0% → 8.0 V @ 100%
        i_load = 0.6 + (1.0 - soc) * 0.4        # 0.6 A (full) → 1.0 A (drained)
        return {
            **self._common(),
            "type": "power",
            "bat_v": round(v_nom + random.uniform(-0.05, 0.05), 3),
            "bat_a": round(i_load + random.uniform(-0.02, 0.02), 3),
            "bat_w": round(v_nom * i_load + random.uniform(-0.1, 0.1), 2),
            "bat_pct": max(0, int(self.bat_pct + random.uniform(-0.5, 0.5))),
            "bat_temp_c": round(TEMP_INT_C + random.uniform(-1, 2), 2),
        }

    # ── flight physics tick ─────────────────────────────────────────────

    def tick(self, dt: float) -> dict:
        """Advance the simulation by *dt* seconds and return one packet.

        Cycles through the 4 telemetry types in order: position, motion,
        environment, power.
        """
        self.flight_time += dt
        dt = min(dt, 5.0)  # cap to avoid huge jumps

        # ── Phase transitions ────────────────────────────────────────
        if self.phase == "ascent" and self.alt_m >= ALT_MAX - 50:
            self.phase = "float"
            self._phase_entered = self.flight_time
            self.vs_mps = 0.0
            self.gs_mps = 22.0 + random.uniform(-2, 2)
        elif self.phase == "float" and self.flight_time - self._phase_entered >= 900:
            self.phase = "descent"
            self._phase_entered = self.flight_time
            self.vs_mps = -ALT_DESCENT_RATE
            self.gs_mps = 15.0 + random.uniform(-2, 2)
        elif self.phase == "descent" and self.alt_m <= 50:
            self.phase = "landed"
            self.vs_mps = 0.0
            self.gs_mps = 0.0

        # ── Update state variables ───────────────────────────────────
        if self.phase == "ascent":
            # Slow ground speed near ground, faster aloft
            frac = min(self.alt_m / ALT_MAX, 1.0)
            target_gs = 2.0 + frac * 23.0       # 2 → 25 m/s
            self.gs_mps += (target_gs - self.gs_mps) * 0.01 * dt
            self.vs_mps = ALT_ASCENT_RATE + random.uniform(-0.4, 0.4)
            self.alt_m += self.vs_mps * dt
            self.heading_deg += random.uniform(-1, 1) * dt
            self.heading_deg %= 360
            self.cog_deg = self.heading_deg + random.uniform(-2, 2)

        elif self.phase == "float":
            self.vs_mps = random.uniform(-0.5, 0.5)
            self.alt_m += self.vs_mps * dt
            # Keep near float altitude
            self.alt_m = max(ALT_MAX - 300, min(ALT_MAX + 200, self.alt_m))
            self.gs_mps += random.uniform(-0.3, 0.3) * dt
            self.gs_mps = max(10, min(30, self.gs_mps))
            self.heading_deg += random.uniform(-0.5, 0.5) * dt
            self.heading_deg %= 360
            self.cog_deg = self.heading_deg + random.uniform(-2, 2)

        elif self.phase == "descent":
            self.vs_mps = -ALT_DESCENT_RATE + random.uniform(-0.5, 0.5)
            self.alt_m += self.vs_mps * dt
            self.alt_m = max(0.0, self.alt_m)
            self.gs_mps += random.uniform(-0.2, 0.2) * dt
            self.gs_mps = max(3, min(25, self.gs_mps))
            self.heading_deg += random.uniform(-0.3, 0.3) * dt
            self.heading_deg %= 360
            self.cog_deg = self.heading_deg + random.uniform(-2, 2)

        elif self.phase == "landed":
            self.alt_m = max(0.0, self.alt_m - 0.5 * dt)

        # ── Position ──────────────────────────────────────────────────
        self.lat, self.lon = self._lat_lon_from_speed(
            self.gs_mps, self.heading_deg, dt
        )

        # ── Battery drain ─────────────────────────────────────────────
        flight_hours = self.flight_time / 3600.0
        # Linear: 100 % → 60 % over ~2 hours
        self.bat_pct = max(0.0, BATTERY_START - flight_hours * 20.0)

        # ── Assemble packet ───────────────────────────────────────────
        builders = [self._make_position, self._make_motion,
                    self._make_environment, self._make_power]
        packet = builders[self._type_idx]()
        self._type_idx = (self._type_idx + 1) % 4
        return packet


# ── CLI entry point ───────────────────────────────────────────────────────────

def _status_line(sim: BalloonSimulator, rate: float, elapsed: float) -> str:
    """Return a single-line status string with emoji indicators."""
    phase_emoji = {"ascent": "🚀", "float": "🎈", "descent": "🪂", "landed": "📍"}
    emoji = phase_emoji.get(sim.phase, "❓")
    phase_pad = sim.phase.ljust(8)
    return (
        f"{emoji} {phase_pad}"
        f"alt={sim.alt_m:8.0f}m  "
        f"vs={sim.vs_mps:+.1f}m/s  "
        f"gs={sim.gs_mps:5.1f}m/s  "
        f"bat={sim.bat_pct:5.1f}%  "
        f"seq={sim.seq:6d}  "
        f"rate={rate:5.2f}pkt/s  "
        f"⏱ {elapsed:7.1f}s"
    )


def main():
    ap = argparse.ArgumentParser(
        description="Balloon telemetry simulator for HAB ground station",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--host", default="localhost", help="Receiver server hostname")
    ap.add_argument("--port", type=int, default=8000, help="Receiver server port")
    ap.add_argument("--fast", action="store_true", help="Run at 10× speed")
    ap.add_argument("--rate", type=float, default=1.0, help="Target packet rate (Hz)")
    ap.add_argument(
        "--profile", choices=("ascent", "float", "descent"), default="ascent",
        help="Starting flight phase",
    )
    args = ap.parse_args()

    speedup = 10.0 if args.fast else 1.0
    dt = speedup / args.rate
    url = f"http://{args.host}:{args.port}/api/packet"

    print(f"🎈 HAB Balloon Simulator")
    print(f"   Server:    POST {url}")
    print(f"   Speed:     {'10× FAST' if args.fast else '1× realtime'}")
    print(f"   Rate:      {args.rate} packet(s)/sec")
    print(f"   Profile:   {args.profile}")
    print(f"   Start:     {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print(f"   Ctrl-C to stop")
    print()

    sim = BalloonSimulator(profile=args.profile)
    t0 = time.monotonic()
    last_status = 0.0
    sent = 0
    session = requests.Session()  # connection reuse

    try:
        while True:
            cycle_start = time.monotonic()

            packet = sim.tick(dt)
            payload = {"type": "telemetry", "data": packet}

            ok = False
            try:
                resp = session.post(url, json=payload, timeout=5.0)
                ok = resp.status_code == 200
            except requests.ConnectionError:
                pass  # will show in status line
            except requests.Timeout:
                pass

            sent += 1
            elapsed = time.monotonic() - t0

            # Status line every 0.5 seconds of wall-clock time
            if elapsed - last_status >= 0.5 or sent == 1:
                rate = sent / elapsed if elapsed > 0 else 0.0
                status = _status_line(sim, rate, sim.flight_time)
                status += "  ✅" if ok else "  ❌ send failed"
                print(f"\r{' ' * 120}\r{status}", end="", flush=True)
                last_status = elapsed

            # Throttle to maintain ~target rate in wall-clock time
            wall_dt = time.monotonic() - cycle_start
            sleep = 1.0 / args.rate - wall_dt
            if sleep > 0:
                time.sleep(sleep)

    except KeyboardInterrupt:
        elapsed = time.monotonic() - t0
        rate = sent / elapsed if elapsed > 0 else 0.0
        print()
        print()
        print(f"🛑 Stopped after {elapsed:.1f}s wall time, "
              f"{sim.flight_time:.0f}s flight time")
        print(f"   Packets sent: {sent}  |  Average rate: {rate:.2f}/s")
        print(f"   Final state:  "
              f"alt={sim.alt_m:.0f}m, "
              f"phase={sim.phase}, "
              f"pos={sim.lat:.4f},{sim.lon:.4f}, "
              f"bat={sim.bat_pct:.0f}%")


if __name__ == "__main__":
    main()
