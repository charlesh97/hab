"""Typed binary frame format for packet radio telemetry.

Each on-air payload starts with a 1-byte type tag followed by
type-specific binary fields.  The outer BPSK framing (preamble +
sync + length + CRC-16/XMODEM) is handled by the TX/RX layer and is
not part of this module.

Dashboard mapping (see dashboard/server/routes/rest.py):
  - 0x01 → position  (38 bytes)
  - 0x02 → motion    (future)
  - 0x03 → environment (future)
  - 0x04 → power     (future)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import ClassVar


class FrameType(IntEnum):
    POSITION = 0x01
    # reserved: MOTION = 0x02, ENVIRONMENT = 0x03, POWER = 0x04


# ── Position frame (0x01) ──────────────────────────────────────────

_POS_STRUCT = struct.Struct("<B H d d f f B B B f f")
_POS_SIZE: int = _POS_STRUCT.size  # 38 bytes

# Fix type enum matching dashboard types.ts fix_type string values
_FIX_TYPE_NAMES: dict[int, str] = {0: "none", 1: "2d", 2: "3d"}


@dataclass(frozen=True, slots=True)
class PositionFrame:
    type: int  # 0x01
    seq: int
    lat: float
    lon: float
    alt_m: float
    agl_m: float
    fix: bool
    fix_type: str
    sats: int
    hdop: float
    vdop: float

    STRUCT: ClassVar[struct.Struct] = _POS_STRUCT

    def pack(self) -> bytes:
        fix_byte = 1 if self.fix else 0
        fix_type_byte = {v: k for k, v in _FIX_TYPE_NAMES.items()}.get(
            self.fix_type, 0
        )
        return _POS_STRUCT.pack(
            FrameType.POSITION,
            self.seq,
            self.lat,
            self.lon,
            self.alt_m,
            self.agl_m,
            fix_byte,
            fix_type_byte,
            self.sats,
            self.hdop,
            self.vdop,
        )

    @staticmethod
    def unpack(data: bytes) -> PositionFrame:
        if len(data) != _POS_SIZE:
            raise ValueError(
                f"position frame: expected {_POS_SIZE} bytes, got {len(data)}"
            )
        (
            _type,
            seq,
            lat,
            lon,
            alt_m,
            agl_m,
            fix_byte,
            fix_type_byte,
            sats,
            hdop,
            vdop,
        ) = _POS_STRUCT.unpack(data)
        if _type != FrameType.POSITION:
            raise ValueError(
                f"position frame: wrong type byte 0x{_type:02X}"
            )
        return PositionFrame(
            type=_type,
            seq=seq,
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            agl_m=agl_m,
            fix=bool(fix_byte),
            fix_type=_FIX_TYPE_NAMES.get(fix_type_byte, "none"),
            sats=sats,
            hdop=hdop,
            vdop=vdop,
        )


# ── Dispatcher ─────────────────────────────────────────────────────

_PARSERS: dict[int, type] = {
    FrameType.POSITION: PositionFrame,
}


def unpack_frame(data: bytes):
    """Return the appropriate typed frame dataclass, or None."""
    if len(data) < 1:
        return None
    frame_type = data[0]
    parser = _PARSERS.get(frame_type)
    if parser is None:
        return None
    return parser.unpack(data)


def pack_frame(frame) -> bytes:
    return frame.pack()
