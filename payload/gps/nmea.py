"""GPS NMEA parser using a 9600-baud 8N1 serial connection."""

from __future__ import annotations

import serial


GPS_BAUD = 9600
GPS_TIMEOUT = 1.0


def nmea_checksum_ok(sentence: str) -> bool:
    """Validate the XOR checksum of an NMEA sentence."""
    try:
        payload, checksum_str = sentence.split("*")
    except (AttributeError, ValueError):
        return False

    if not payload.startswith("$"):
        return False

    computed = 0
    for char in payload[1:]:
        computed ^= ord(char)

    try:
        expected = int(checksum_str.strip(), 16)
    except ValueError:
        return False

    return computed == expected


def _safe_float(value: str) -> float | None:
    if not value or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _nmea_dm_to_dd(raw: str, hemisphere: str) -> float | None:
    """Convert NMEA degrees/minutes coordinates to decimal degrees."""
    if not raw or not hemisphere:
        return None

    try:
        if "." in raw:
            int_part, frac_part = raw.split(".", 1)
        else:
            int_part, frac_part = raw, "0"

        if len(int_part) <= 4:
            degree_length = 2
        else:
            degree_length = 3 if hemisphere in ("E", "W") else 2

        degrees = float(int_part[:degree_length])
        minutes = float(int_part[degree_length:] + "." + frac_part)
        decimal_degrees = degrees + minutes / 60.0

        if hemisphere in ("S", "W"):
            decimal_degrees = -decimal_degrees

        return round(decimal_degrees, 6)
    except (ValueError, IndexError):
        return None


def parse_gga(sentence: str) -> dict[str, object] | None:
    """Parse a checksum-valid GGA sentence."""
    sentence = sentence.strip()
    if not nmea_checksum_ok(sentence):
        return None

    fields = sentence.split(",")
    if len(fields) < 11 or not fields[0].lstrip("$").endswith("GGA"):
        return None

    utc_time = fields[1]
    lat_raw = fields[2]
    lat_ns = fields[3]
    lon_raw = fields[4]
    lon_ew = fields[5]
    fix_quality = _safe_float(fields[6])
    satellites = _safe_float(fields[7])
    altitude = _safe_float(fields[9])

    if not utc_time or not lat_raw or not lon_raw:
        return None

    return {
        "time": utc_time,
        "lat": _nmea_dm_to_dd(lat_raw, lat_ns),
        "lon": _nmea_dm_to_dd(lon_raw, lon_ew),
        "fix_quality": int(fix_quality) if fix_quality is not None else None,
        "altitude": altitude,
        "satellites": int(satellites) if satellites is not None else None,
    }


def parse_rmc(sentence: str) -> dict[str, object] | None:
    """Parse a checksum-valid RMC sentence."""
    sentence = sentence.strip()
    if not nmea_checksum_ok(sentence):
        return None

    fields = sentence.split(",")
    if len(fields) < 10 or not fields[0].lstrip("$").endswith("RMC"):
        return None

    utc_time = fields[1]
    lat_raw = fields[3]
    lat_ns = fields[4]
    lon_raw = fields[5]
    lon_ew = fields[6]
    speed_knots = _safe_float(fields[7])
    track_angle = _safe_float(fields[8])
    date = fields[9]

    if not utc_time or not date:
        return None

    return {
        "time": utc_time,
        "lat": _nmea_dm_to_dd(lat_raw, lat_ns) if lat_raw and lat_ns else None,
        "lon": _nmea_dm_to_dd(lon_raw, lon_ew) if lon_raw and lon_ew else None,
        "speed_knots": speed_knots,
        "track_angle": track_angle,
        "date": date,
    }


class NMEAParser:
    """Read and parse NMEA sentences from a serial GPS receiver."""

    def __init__(self, device: str) -> None:
        self.serial = serial.Serial(
            port=device,
            baudrate=GPS_BAUD,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=GPS_TIMEOUT,
        )

    def read_sentence(self) -> str | None:
        """Return the next checksum-valid NMEA sentence, or None on timeout."""
        while True:
            raw_line = self.serial.readline()
            if not raw_line:
                return None

            sentence = raw_line.decode("ascii", errors="ignore").strip()
            if sentence and nmea_checksum_ok(sentence):
                return sentence

    @staticmethod
    def checksum_valid(sentence: str) -> bool:
        return nmea_checksum_ok(sentence)

    @staticmethod
    def parse_gga(sentence: str) -> dict[str, object] | None:
        return parse_gga(sentence)

    @staticmethod
    def parse_rmc(sentence: str) -> dict[str, object] | None:
        return parse_rmc(sentence)

    def close(self) -> None:
        self.serial.close()

    def __enter__(self) -> NMEAParser:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
