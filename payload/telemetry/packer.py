from dataclasses import dataclass
import struct
import threading
import time


MAGIC = 0xFEED
_FRAME_STRUCT = struct.Struct(">HHIfffffddfBfB")
_sequence = 0
_sequence_lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class TelemetryFrame:
    magic: int
    sequence: int
    timestamp: int
    temp_c: float
    pressure_hpa: float
    accel_x: float
    accel_y: float
    accel_z: float
    lat: float
    lon: float
    alt_m: float
    fix_quality: int
    battery_v: float
    battery_soc: int


def _next_sequence() -> int:
    global _sequence
    with _sequence_lock:
        value = _sequence
        _sequence = (_sequence + 1) & 0xFFFF
        return value


def pack_frame(
    temp_c: float,
    pressure_hpa: float,
    accel_x: float,
    accel_y: float,
    accel_z: float,
    lat: float,
    lon: float,
    alt_m: float,
    fix_quality: int,
    battery_v: float,
    battery_soc: int,
) -> bytes:
    return _FRAME_STRUCT.pack(
        MAGIC,
        _next_sequence(),
        int(time.time()) & 0xFFFFFFFF,
        temp_c,
        pressure_hpa,
        accel_x,
        accel_y,
        accel_z,
        lat,
        lon,
        alt_m,
        fix_quality,
        battery_v,
        battery_soc,
    )


def unpack_frame(data: bytes) -> TelemetryFrame:
    if len(data) != _FRAME_STRUCT.size:
        raise ValueError(
            f"invalid frame length: expected {_FRAME_STRUCT.size} bytes, "
            f"received {len(data)}"
        )

    values = _FRAME_STRUCT.unpack(data)
    if values[0] != MAGIC:
        raise ValueError(f"invalid frame magic: 0x{values[0]:04X}")

    return TelemetryFrame(*values)
