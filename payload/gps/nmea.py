"""Compatibility imports for the telemetry NMEA module.

New code should import :mod:`payload.telemetry.nmea`.  This module remains so
existing payload sensor and diagnostic code keeps working.
"""

try:
    from payload.telemetry.nmea import (  # noqa: F401
        GPS_BAUD,
        GPS_TIMEOUT,
        GPSState,
        NMEAParser,
        nmea_checksum_ok,
        parse_gga,
        parse_rmc,
    )
except ModuleNotFoundError:  # Compatibility when payload/ is sys.path[0].
    from telemetry.nmea import (  # type: ignore[no-redef]  # noqa: F401
        GPS_BAUD,
        GPS_TIMEOUT,
        GPSState,
        NMEAParser,
        nmea_checksum_ok,
        parse_gga,
        parse_rmc,
    )

__all__ = [
    "GPS_BAUD",
    "GPS_TIMEOUT",
    "GPSState",
    "NMEAParser",
    "nmea_checksum_ok",
    "parse_gga",
    "parse_rmc",
]
