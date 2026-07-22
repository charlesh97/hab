#!/usr/bin/env python3
"""
Phase 1D: GPS NMEA Test Script
===============================
Opens the L76K GPS module via UART, reads NMEA sentences for 15 seconds,
identifies sentence types, extracts key fields from GGA and RMC sentences,
and reports fix status.

Hardware:  Radxa Rock 2A, L76K GNSS module
UART:      GPIO4_D0 (TX, pin 8), GPIO4_C7 (RX, pin 10)
Baud:      9600, 8N1
Reference: PLAN.md Section 4 — GPS Interface
"""

from __future__ import annotations

import sys
import time
import signal
import re
from datetime import datetime

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Run: pip install pyserial")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GPS_BAUD = 9600
GPS_TIMEOUT = 1.0           # serial read timeout (seconds)
CAPTURE_DURATION = 15       # total read window (seconds)
UART_CANDIDATES = [         # search order per PLAN.md §4.1
    "/dev/ttyS0",
    "/dev/ttyS1",
    "/dev/ttyAMA0",
]


# ---------------------------------------------------------------------------
# NMEA helpers
# ---------------------------------------------------------------------------

def nmea_checksum_ok(sentence: str) -> bool:
    """Validate NMEA checksum (XOR of bytes between '$' and '*')."""
    try:
        payload, checksum_str = sentence.split("*")
    except ValueError:
        return False  # no checksum field — skip
    if not payload.startswith("$"):
        return False
    data = payload[1:]  # strip leading '$'
    computed = 0
    for ch in data:
        computed ^= ord(ch)
    try:
        expected = int(checksum_str.strip(), 16)
    except ValueError:
        return False
    return computed == expected


def identify_sentence_type(sentence: str) -> str | None:
    """
    Return the talker+sentence ID (e.g. 'GPGGA', 'GPRMC', 'GPGSV')
    or None if unparseable.
    """
    fields = sentence.split(",")
    if not fields:
        return None
    addr = fields[0].lstrip("$")
    if "_" in addr:
        # proprietary sentences like $PSTI,030,...
        return addr.split("_")[0] if addr.startswith("P") else None
    # standard NMEA: $GPGGA, $GLGSV, $GNRMC, $BDGGA, etc.
    if re.match(r"^[A-Z]{2}[A-Z]{3}$", addr):
        return addr
    return None


def safe_float(val: str) -> float | None:
    """Parse float from NMEA field, returning None on empty/invalid."""
    if not val or val.strip() == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# NMEA sentence parsers
# ---------------------------------------------------------------------------

def parse_gga(fields: list[str]) -> dict | None:
    """
    Parse a GGA sentence.

    $GPGGA,hhmmss.ss,ddmm.mmmm,N,dddmm.mmmm,W,q,ss,hdop,alt,M,...
      0    1          2        3 4         5 6 7  8    9  10
    """
    if len(fields) < 11:
        return None

    utc_time    = fields[1]
    lat_raw     = fields[2]
    lat_ns      = fields[3]          # 'N' or 'S'
    lon_raw     = fields[4]
    lon_ew      = fields[5]          # 'E' or 'W'
    fix_qual    = safe_float(fields[6])  # 0=no fix, 1=GPS, 2=DGPS, 6=dead reckoning
    sats_used   = safe_float(fields[7])
    altitude_m  = safe_float(fields[9])
    alt_units   = fields[10]         # 'M'

    if not utc_time or not lat_raw or not lon_raw:
        return None

    # Convert ddmm.mmmm → decimal degrees
    lat_deg = _nmea_dm_to_dd(lat_raw, lat_ns)
    lon_deg = _nmea_dm_to_dd(lon_raw, lon_ew)

    return {
        "type": "GGA",
        "time_utc": utc_time,
        "latitude": lat_deg,
        "longitude": lon_deg,
        "fix_quality": int(fix_qual) if fix_qual is not None else None,
        "satellites_used": int(sats_used) if sats_used is not None else None,
        "altitude_m": altitude_m,
    }


def parse_rmc(fields: list[str]) -> dict | None:
    """
    Parse an RMC sentence.

    $GPRMC,hhmmss.ss,A,ddmm.mmmm,N,dddmm.mmmm,W,spd,track,date,,,mode
      0    1          2 3         4 5         6 7   8     9
    """
    if len(fields) < 10:
        return None

    utc_time  = fields[1]
    status    = fields[2]           # 'A'=active/valid, 'V'=void
    lat_raw   = fields[3]
    lat_ns    = fields[4]
    lon_raw   = fields[5]
    lon_ew    = fields[6]
    speed_kn  = safe_float(fields[7])
    track_deg = safe_float(fields[8])
    date_str  = fields[9]           # ddmmyy

    if not utc_time or not date_str:
        return None

    lat_deg = _nmea_dm_to_dd(lat_raw, lat_ns) if lat_raw and lat_ns else None
    lon_deg = _nmea_dm_to_dd(lon_raw, lon_ew) if lon_raw and lon_ew else None

    return {
        "type": "RMC",
        "time_utc": utc_time,
        "status": status,                 # 'A' or 'V'
        "latitude": lat_deg,
        "longitude": lon_deg,
        "speed_knots": speed_kn,
        "track_angle_deg": track_deg,
        "date": date_str,
    }


def _nmea_dm_to_dd(raw: str, hemisphere: str) -> float | None:
    """
    Convert NMEA ddmm.mmmm to decimal degrees.
    Example: 4807.038,N → 48.1173
    """
    if not raw or not hemisphere:
        return None
    try:
        # find decimal point or split by convention
        if "." in raw:
            int_part, frac_part = raw.split(".")
        else:
            int_part, frac_part = raw, "0"
        # ddmm.mmmm → degrees = first 2–3 digits, minutes = rest
        if len(int_part) <= 4:
            # longitude (dddmm.mmmm) — degrees is first 3 digits
            deg_len = 3 if len(int_part) > 4 else 2
        else:
            deg_len = 3 if hemisphere in ("E", "W") else 2

        degrees = float(int_part[:deg_len])
        minutes = float(int_part[deg_len:] + "." + frac_part)
        dd = degrees + minutes / 60.0
        if hemisphere in ("S", "W"):
            dd = -dd
        return round(dd, 6)
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def open_gps_uart() -> serial.Serial | None:
    """Try each candidate UART device in order. Return the open Serial or None."""
    for device in UART_CANDIDATES:
        try:
            ser = serial.Serial(
                port=device,
                baudrate=GPS_BAUD,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=GPS_TIMEOUT,
            )
            print(f"  Opened {device} at {GPS_BAUD} baud 8N1")
            return ser
        except (serial.SerialException, OSError) as e:
            print(f"  {device}: {e}")
    return None


def fmt_lat(lat: float | None) -> str:
    """Format decimal latitude as dd°mm.mmm' N/S."""
    if lat is None:
        return "N/A"
    hemi = "N" if lat >= 0 else "S"
    abs_lat = abs(lat)
    deg = int(abs_lat)
    minutes = (abs_lat - deg) * 60.0
    return f"{deg}°{minutes:07.4f}' {hemi}"


def fmt_lon(lon: float | None) -> str:
    """Format decimal longitude as ddd°mm.mmm' E/W."""
    if lon is None:
        return "N/A"
    hemi = "E" if lon >= 0 else "W"
    abs_lon = abs(lon)
    deg = int(abs_lon)
    minutes = (abs_lon - deg) * 60.0
    return f"{deg}°{minutes:07.4f}' {hemi}"


def fmt_time_utc(raw: str) -> str:
    """Format raw UTC hhmmss.ss → HH:MM:SS."""
    if not raw:
        return "N/A"
    try:
        h = raw[0:2]
        m = raw[2:4]
        s = raw[4:6]
        return f"{h}:{m}:{s} UTC"
    except IndexError:
        return raw


def fmt_date(raw: str) -> str:
    """Format raw ddmmyy → DD/MM/20YY."""
    if not raw or len(raw) < 6:
        return "N/A"
    try:
        return f"{raw[0:2]}/{raw[2:4]}/20{raw[4:6]}"
    except IndexError:
        return raw


FIX_LABELS: dict[int, str] = {
    0: "No Fix",
    1: "GPS Fix (SPS)",
    2: "DGPS Fix",
    4: "RTK Fixed",
    5: "RTK Float",
    6: "Dead Reckoning",
}


def main() -> None:
    print("=" * 68)
    print("  Phase 1D — GPS NMEA Test")
    print("  Module: L76K GNSS (Quectel) | 9600 baud 8N1")
    print("  READY — listen for", CAPTURE_DURATION, "seconds…")
    print("=" * 68)

    # ── Open UART ──────────────────────────────────────────────────────────
    ser = open_gps_uart()
    if ser is None:
        print("\nFAIL: Could not open any GPS UART device.")
        print("      Candidates:", ", ".join(UART_CANDIDATES))
        print("      Verify with:  ls -l /dev/ttyS* /dev/ttyAMA*")
        sys.exit(1)

    # ── Read NMEA sentences ────────────────────────────────────────────────
    sentence_counts: dict[str, int] = {}
    raw_lines: list[str] = []
    first_gga: dict | None = None
    first_rmc: dict | None = None
    buffer = ""

    deadline = time.monotonic() + CAPTURE_DURATION

    try:
        while time.monotonic() < deadline:
            byte = ser.read(1)
            if byte:
                ch = byte.decode("ascii", errors="ignore")
                if ch == "\n":
                    line = buffer.strip()
                    buffer = ""
                    if line:
                        raw_lines.append(line)
                else:
                    buffer += ch
            else:
                # timeout on no data — flush whatever partial line we have
                if buffer.strip():
                    raw_lines.append(buffer.strip())
                buffer = ""
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    finally:
        ser.close()

    # ── Parse every line ──────────────────────────────────────────────────
    print(f"\n  Captured {len(raw_lines)} lines in {CAPTURE_DURATION}s")
    print("  Parsing NMEA sentences…\n")

    for line in raw_lines:
        # keep only valid NMEA with good checksum
        if not line.startswith("$") or not nmea_checksum_ok(line):
            continue

        stype = identify_sentence_type(line)
        if stype is None:
            continue

        sentence_counts[stype] = sentence_counts.get(stype, 0) + 1
        fields = line.split(",")

        # ── Grab first valid GGA ──
        if first_gga is None and stype.endswith("GGA"):
            parsed = parse_gga(fields)
            if parsed:
                first_gga = parsed

        # ── Grab first valid RMC ──
        if first_rmc is None and stype.endswith("RMC"):
            parsed = parse_rmc(fields)
            if parsed:
                first_rmc = parsed

    # ── Sentence type summary ─────────────────────────────────────────────
    if not sentence_counts:
        print("  ⚠  No valid NMEA sentences found (checksum failures? no GPS signal?)")
        print("     Raw output sample:")
        for line in raw_lines[:10]:
            print(f"       {line[:80]}")
        return

    print("  Sentence types detected:")
    for stype in sorted(sentence_counts):
        count = sentence_counts[stype]
        bar = "#" * min(count, 40)
        print(f"    {stype:8s}  {count:4d}  {bar}")
    print()

    # ── GGA extraction ─────────────────────────────────────────────────────
    print("─" * 68)
    if first_gga:
        g = first_gga
        print("  First GGA Sentence:")
        print(f"    UTC Time:       {fmt_time_utc(g.get('time_utc', ''))}")
        print(f"    Latitude:       {fmt_lat(g.get('latitude'))}")
        print(f"    Longitude:      {fmt_lon(g.get('longitude'))}")
        print(f"    Fix Quality:    {g.get('fix_quality')} — "
              f"{FIX_LABELS.get(g.get('fix_quality', -1), 'Unknown')}")
        print(f"    Satellites:     {g.get('satellites_used', 'N/A')}")
        alt = g.get("altitude_m")
        print(f"    Altitude:       {alt:.1f} m" if alt is not None else "    Altitude:       N/A")
    else:
        print("  No valid GGA sentence received.")
    print()

    # ── RMC extraction ─────────────────────────────────────────────────────
    print("─" * 68)
    if first_rmc:
        r = first_rmc
        print("  First RMC Sentence:")
        print(f"    UTC Time:       {fmt_time_utc(r.get('time_utc', ''))}")
        print(f"    Status:         {'Active' if r.get('status') == 'A' else 'Void'}")
        print(f"    Latitude:       {fmt_lat(r.get('latitude'))}")
        print(f"    Longitude:      {fmt_lon(r.get('longitude'))}")
        spd = r.get("speed_knots")
        print(f"    Speed:          {spd:.2f} knots ({spd * 1.852:.1f} km/h)" if spd is not None else "    Speed:          N/A")
        trk = r.get("track_angle_deg")
        print(f"    Track Angle:    {trk:.1f}°" if trk is not None else "    Track Angle:    N/A")
        print(f"    Date:           {fmt_date(r.get('date', ''))}")
    else:
        print("  No valid RMC sentence received.")
    print()

    # ── Fix status determination ──────────────────────────────────────────
    print("─" * 68)
    print("  FIX STATUS")

    # Prioritize GGA fix quality
    fix_qual = None
    if first_gga:
        fix_qual = first_gga.get("fix_quality")

    if fix_qual is not None and fix_qual > 0:
        label = FIX_LABELS.get(fix_qual, f"Fix Type {fix_qual}")
        print(f"    → {label}  (GGA fix quality = {fix_qual})")
    elif first_rmc and first_rmc.get("status") == "A":
        print("    → Position Valid  (RMC status = Active)")
    else:
        # Check if we have any GSV sentences (satellites in view, just no fix)
        gsv_count = sum(c for st, c in sentence_counts.items() if st.endswith("GSV"))
        if gsv_count > 0:
            print(f"    → No Fix — but {gsv_count} GSV sentences received")
            print("      Satellites in view but no position fix yet.")
            print("      Indoors? Check antenna visibility / wait longer.")
        else:
            print("    → No Fix — no position data received")
            print("      Check antenna connection and sky visibility.")

    print()
    if first_gga:
        sats = first_gga.get("satellites_used", "?")
        print(f"  Satellites used: {sats}")
    total_sentences = sum(sentence_counts.values())
    print(f"  Total valid NMEA: {total_sentences} sentences across {len(sentence_counts)} types")
    print()
    print("  ✓ Phase 1D complete")
    print("=" * 68)


if __name__ == "__main__":
    main()
