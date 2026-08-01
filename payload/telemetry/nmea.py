"""NMEA parsing and accumulated GPS state for payload telemetry.

The pure parsing functions are intentionally separate from the serial reader so
they can be reused in tests and by transmitters that receive NMEA data through a
different transport.
"""

from __future__ import annotations

from dataclasses import dataclass

import serial


GPS_BAUD = 9600
GPS_TIMEOUT = 1.0
KNOTS_TO_METRES_PER_SECOND = 0.514444


def nmea_checksum_ok(sentence: str) -> bool:
    """Return whether *sentence* has a valid NMEA XOR checksum."""
    try:
        payload, checksum_text = sentence.strip().rsplit("*", 1)
    except (AttributeError, ValueError):
        return False
    if not payload.startswith("$") or len(checksum_text) < 2:
        return False

    checksum = 0
    for character in payload[1:]:
        checksum ^= ord(character)
    try:
        return checksum == int(checksum_text[:2], 16)
    except ValueError:
        return False


def _safe_float(value: str) -> float | None:
    try:
        return float(value) if value.strip() else None
    except (AttributeError, ValueError):
        return None


def _nmea_dm_to_dd(raw: str, hemisphere: str) -> float | None:
    """Convert an NMEA degrees/minutes coordinate to decimal degrees."""
    if not raw or hemisphere not in {"N", "S", "E", "W"}:
        return None
    try:
        degree_digits = 3 if hemisphere in {"E", "W"} else 2
        degrees = float(raw[:degree_digits])
        minutes = float(raw[degree_digits:])
    except (TypeError, ValueError):
        return None
    coordinate = degrees + minutes / 60.0
    if hemisphere in {"S", "W"}:
        coordinate = -coordinate
    return round(coordinate, 6)


def parse_gga(sentence: str) -> dict[str, object] | None:
    """Parse a checksum-valid GGA fix sentence."""
    sentence = sentence.strip()
    if not nmea_checksum_ok(sentence):
        return None
    fields = sentence.split(",")
    if len(fields) < 11 or not fields[0].lstrip("$").endswith("GGA"):
        return None

    fix_quality = _safe_float(fields[6])
    satellites = _safe_float(fields[7])
    return {
        "time": fields[1],
        "lat": _nmea_dm_to_dd(fields[2], fields[3]),
        "lon": _nmea_dm_to_dd(fields[4], fields[5]),
        "fix_quality": int(fix_quality) if fix_quality is not None else None,
        "satellites": int(satellites) if satellites is not None else None,
        "hdop": _safe_float(fields[8]),
        "altitude": _safe_float(fields[9]),
    }


def parse_rmc(sentence: str) -> dict[str, object] | None:
    """Parse a checksum-valid RMC position/course sentence."""
    sentence = sentence.strip()
    if not nmea_checksum_ok(sentence):
        return None
    fields = sentence.split(",")
    if len(fields) < 10 or not fields[0].lstrip("$").endswith("RMC"):
        return None

    speed_knots = _safe_float(fields[7])
    return {
        "time": fields[1],
        "status": fields[2],
        "valid": fields[2] == "A",
        "lat": _nmea_dm_to_dd(fields[3], fields[4]),
        "lon": _nmea_dm_to_dd(fields[5], fields[6]),
        "speed_knots": speed_knots,
        "speed_mps": (
            speed_knots * KNOTS_TO_METRES_PER_SECOND
            if speed_knots is not None
            else None
        ),
        "track_angle": _safe_float(fields[8]),
        "date": fields[9],
    }


@dataclass
class GPSState:
    """Latest fields assembled from interleaved GGA and RMC sentences."""

    lat: float = 0.0
    lon: float = 0.0
    altitude_m: float = 0.0
    speed_mps: float = 0.0
    heading_deg: float = 0.0
    fix: bool = False
    fix_type: str = "none"
    satellites: int = 0
    hdop: float = 0.0
    vdop: float = 0.0

    def update(self, sentence: str) -> bool:
        """Merge one GGA or RMC sentence, returning whether it was recognized."""
        gga = parse_gga(sentence)
        if gga is not None:
            self._update_position(gga)
            quality = int(gga.get("fix_quality") or 0)
            self.fix = quality > 0
            self.fix_type = "3d" if quality >= 2 else (
                "2d" if quality == 1 else "none"
            )
            if gga.get("altitude") is not None:
                self.altitude_m = float(gga["altitude"])
            if gga.get("satellites") is not None:
                self.satellites = max(0, min(255, int(gga["satellites"])))
            if gga.get("hdop") is not None:
                self.hdop = max(0.0, float(gga["hdop"]))
            return True

        rmc = parse_rmc(sentence)
        if rmc is None:
            return False
        self._update_position(rmc)
        if rmc.get("speed_mps") is not None:
            self.speed_mps = max(0.0, float(rmc["speed_mps"]))
        if rmc.get("track_angle") is not None:
            self.heading_deg = float(rmc["track_angle"]) % 360.0
        if rmc.get("valid") is True:
            self.fix = True
            if self.fix_type == "none":
                self.fix_type = "2d"
        else:
            self.fix = False
            self.fix_type = "none"
        return True

    def _update_position(self, values: dict[str, object]) -> None:
        if values.get("lat") is not None:
            self.lat = float(values["lat"])
        if values.get("lon") is not None:
            self.lon = float(values["lon"])

    def position_fields(self) -> dict[str, object]:
        """Return fields consumed by :class:`protocol.telemetry.PositionFrame`."""
        return {
            "lat": self.lat,
            "lon": self.lon,
            "alt_m": self.altitude_m,
            "agl_m": max(0.0, self.altitude_m - 10.0),
            "fix": self.fix,
            "fix_type": self.fix_type,
            "sats": self.satellites,
            "hdop": self.hdop,
            "vdop": self.vdop,
        }


class NMEAParser:
    """Read complete, checksum-valid NMEA sentences from a serial device."""

    def __init__(
        self,
        device: str,
        baudrate: int = GPS_BAUD,
        timeout: float = GPS_TIMEOUT,
    ) -> None:
        self.serial = serial.Serial(
            port=device,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
        )
        self._buffer = bytearray()
        self._nonblocking = timeout == 0

    def _pop_buffered_sentence(self) -> str | None:
        while b"\n" in self._buffer:
            raw_line, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            sentence = raw_line.decode("ascii", errors="ignore").strip()
            if sentence and nmea_checksum_ok(sentence):
                return sentence
        return None

    def read_sentence(self) -> str | None:
        """Return the next valid sentence, or ``None`` when no line is ready."""
        sentence = self._pop_buffered_sentence()
        if sentence is not None:
            return sentence

        if self._nonblocking:
            waiting = int(getattr(self.serial, "in_waiting", 0))
            if waiting <= 0:
                return None
            self._buffer.extend(self.serial.read(waiting))
            return self._pop_buffered_sentence()

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

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.close()
