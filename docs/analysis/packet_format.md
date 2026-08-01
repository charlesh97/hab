# `packet_format.py` — Exhaustive Line-by-Line Analysis

**File:** `payload/telemetry/packet_format.py` (129 lines, 3,452 bytes)
**Purpose:** Typed binary frame format for BPSK packet radio telemetry in the HAB (High-Altitude Balloon) project.
**Date of analysis:** 2026-07-22

---

## 1. Module Docstring (Lines 1–13)

```python
"""Typed binary frame format for packet radio telemetry.
```

**Line 1:** The module's one-line summary. This is a `packet_format` module for *packet radio* telemetry — distinct from the MPEG-TS/DVB-S2 telemetry path in `packer.py`. The word "typed" is central: every on-air payload has a 1-byte type tag, enabling a single radio channel to carry multiple frame types (position, motion, environment, power).

```python
Each on-air payload starts with a 1-byte type tag followed by
type-specific binary fields.
```

**Lines 3–4:** Explicit design contract. The first byte **always** encodes the frame type. The remaining bytes are interpreted based on that type. This is a classic tagged-union / variant-record pattern at the binary level.

```python
The outer BPSK framing (preamble +
sync + length + CRC-16/XMODEM) is handled by the TX/RX layer and is
not part of this module.
```

**Lines 5–7:** Critical separation of concerns. This module defines the *payload* only. The outer envelope — 256-bit preamble, 32-bit sync word `0xE38FC0FC`, 16-bit big-endian length, and CRC-16/XMODEM over the payload — is the responsibility of `gps_packet_tx.py` (TX) and `pkt_simple_rx.py` (RX). This module never touches CRC or radio framing.

```python
Dashboard mapping (see dashboard/server/routes/rest.py):
  - 0x01 → position  (38 bytes)
  - 0x02 → motion    (future)
  - 0x03 → environment (future)
  - 0x04 → power     (future)
```

**Lines 8–12:** Documented forward reference to the dashboard REST API. The bridge (`gps_bridge.py`) unpacks raw frames and POSTs JSON to `POST /api/packet`. Types 0x02–0x04 are **reserved but unimplemented** — the architecture plans for them but only 0x01 is live. This comment serves as the canonical type registry.

---

## 2. Imports (Lines 15–21)

```python
from __future__ import annotations
```

**Line 15:** PEP 563 deferred annotation evaluation. Makes all annotations into strings, enabling forward references without `from __future__ import annotations`. In this file, `ClassVar[struct.Struct]` on line 51 would otherwise require a runtime import of `ClassVar` at definition time. With this future import, the annotation is just a string until `typing.get_type_hints()` inspects it. This also reduces import-time overhead.

```python
import struct
```

**Line 17:** The `struct` module from the standard library. Used to create a precompiled `struct.Struct` object (`_POS_STRUCT`) for packing/unpacking binary data. Precompiling via `struct.Struct()` is faster than calling `struct.pack()`/`struct.unpack()` repeatedly because the format string is parsed only once.

```python
from dataclasses import dataclass
```

**Line 18:** Standard library `dataclasses.dataclass`. Used to define `PositionFrame` as an immutable, slot-optimized data container.

```python
from enum import IntEnum
```

**Line 19:** `enum.IntEnum` for `FrameType`. Chosen over plain `Enum` so that enum members are also `int` subclasses — they can be compared to raw bytes and used directly in `struct.pack()` without `.value` boilerplate.

```python
from typing import ClassVar
```

**Line 20:** `ClassVar` marks `STRUCT` as a class-level constant, not a dataclass field. Without `ClassVar`, the dataclass decorator would try to include `STRUCT` as a field in `__init__`, `__eq__`, etc.

---

## 3. FrameType Enum (Lines 23–25)

```python
class FrameType(IntEnum):
    POSITION = 0x01
    # reserved: MOTION = 0x02, ENVIRONMENT = 0x03, POWER = 0x04
```

**Line 23:** Inherits from `IntEnum`. Each member **is** an `int`. `FrameType.POSITION == 0x01` is `True`. This allows direct use in `struct.pack('B', FrameType.POSITION)` without `.value`.

**Line 24:** The only live frame type. Value `0x01` matches the dashboard mapping in the docstring.

**Line 25:** Reserved types documented inline as a comment rather than as enum members. This is a **deliberate choice**: defining them as enum members would add them to the `IntEnum` namespace but no parser exists for them yet. The comment serves as a specification without creating dead code. When motion/environment/power frames are implemented, these will be un-commented.

### Why `IntEnum` over plain `int` constants?

| Approach | Pros | Cons |
|---|---|---|
| `IntEnum` | Namespaced, iterable, self-documenting, type-checkable | Slightly more overhead (negligible) |
| `int` constants | Zero overhead | No namespacing, no iteration, no type safety |
| `Enum` (non-int) | Type safety | Requires `.value` everywhere |

The project chose `IntEnum` for the ergonomic tradeoff: works naturally with `struct` while providing namespacing.

---

## 4. Position Frame Struct Definition (Lines 28–34)

### 4.1 The Format String: `<B H d d f f B B B f f`

```python
_POS_STRUCT = struct.Struct("<B H d d f f B B B f f")
```

**Line 30:** Creates a precompiled `struct.Struct`. The `<` prefix means **little-endian** byte order for all multi-byte fields. This is the x86/ARM native endianness for the Rock 2A payload computer, eliminating byte-swap overhead.

#### Field-by-field breakdown:

| Index | Format | C Type | Python Type | Size (bytes) | Field Name | Range / Notes |
|-------|--------|--------|-------------|--------------|------------|---------------|
| 1 | `B` | `unsigned char` | `int` (0–255) | 1 | `type` | Always `0x01` for position frames |
| 2 | `H` | `unsigned short` | `int` (0–65535) | 2 | `seq` | Packet sequence number, wraps at 65535 |
| 3 | `d` | `double` | `float` | 8 | `lat` | IEEE 754 binary64, ±90° |
| 4 | `d` | `double` | `float` | 8 | `lon` | IEEE 754 binary64, ±180° |
| 5 | `f` | `float` | `float` | 4 | `alt_m` | IEEE 754 binary32, altitude in meters |
| 6 | `f` | `float` | `float` | 4 | `agl_m` | Above-ground level in meters |
| 7 | `B` | `unsigned char` | `int` (0–1) | 1 | `fix` | Boolean as byte: 0=no fix, 1=fix acquired |
| 8 | `B` | `unsigned char` | `int` (0–2) | 1 | `fix_type` | 0=none, 1=2d, 2=3d |
| 9 | `B` | `unsigned char` | `int` (0–255) | 1 | `sats` | Number of satellites in use |
| 10 | `f` | `float` | `float` | 4 | `hdop` | Horizontal dilution of precision |
| 11 | `f` | `float` | `float` | 4 | `vdop` | Vertical dilution of precision |

**Total:** 1 + 2 + 8 + 8 + 4 + 4 + 1 + 1 + 1 + 4 + 4 = **38 bytes**

### 4.2 Endianness: Why Little-Endian (`<`)?

```python
_POS_STRUCT = struct.Struct("<B H d d f f B B B f f")
```

The `<` prefix sets the byte order. Little-endian means the least significant byte comes first:

- `seq = 0x0102` (258 decimal) is packed as `02 01` (not `01 02`)
- `lat = 37.75326` as IEEE 754 binary64 is packed with the least significant byte first

**Rationale:** The Rock 2A payload computer is ARM-based (little-endian native). Packing little-endian avoids byte-swap instructions. The ground station (likely x86, also little-endian) similarly benefits. The choice is consistent with all other multi-byte fields in the BPSK outer frame except the length and CRC fields, which use big-endian by convention (matching the baseline `pkt_simple_tx.py`).

### 4.3 Size Calculation

```python
_POS_SIZE: int = _POS_STRUCT.size  # 38 bytes
```

**Line 31:** `struct.Struct.size` is a property that returns the total packed size. The inline comment `# 38 bytes` is both documentation and a canary — if someone modifies the format string, the comment should be updated. The `_POS_SIZE` constant is used in `unpack()` for length validation (line 74).

---

## 5. Fix Type Mapping (Lines 33–34)

```python
_FIX_TYPE_NAMES: dict[int, str] = {0: "none", 1: "2d", 2: "3d"}
```

**Line 33–34:** Module-level constant mapping integer fix-type values to human-readable strings. This mirrors the dashboard's TypeScript `fix_type` string enum values (`"none" | "2d" | "3d"`). The mapping is:

| Byte | String | GPS Fix Quality | Meaning |
|------|--------|-----------------|---------|
| 0 | `"none"` | 0 | No fix / invalid |
| 1 | `"2d"` | 1 | GPS fix (2D — lat/lon only, no altitude) |
| 2 | `"3d"` | 2+ | DGPS/GPS fix (3D — lat/lon + altitude) |

The string values match `payload/PLAN.md` line 492: `u8 fix_type (0=none, 1=2d, 2=3d)` and the dashboard spec at `docs/superpowers/specs/2026-05-19-mission-control-design.md` line 281: `fix_type: string; // "2d" | "3d"`.

---

## 6. PositionFrame Dataclass (Lines 37–107)

### 6.1 Decorator and Field Declarations (Lines 37–49)

```python
@dataclass(frozen=True, slots=True)
class PositionFrame:
```

**Line 37:** `frozen=True` makes instances **immutable** — no field can be reassigned after construction. This is critical for a wire-format data object: you should never accidentally mutate a frame between packing and transmission. `slots=True` replaces the default `__dict__` with a fixed `__slots__` tuple, reducing memory from ~640 bytes (dict overhead) to ~104 bytes (11 slots × 8 bytes + object header). At 1 Hz transmission with potentially thousands of frames in flight, this is a meaningful optimization.

```python
    type: int  # 0x01
```

**Line 39:** The frame type byte. Always `0x01` (i.e., `FrameType.POSITION`). Stored as `int` rather than `FrameType` to avoid import coupling between the dataclass and the enum — though both are in the same module, keeping it `int` means `pack()` and `unpack()` work with raw struct values directly.

```python
    seq: int
```

**Line 40:** 16-bit unsigned sequence number (0–65535). Wraps on overflow. The transmitter increments this on each frame (`seq = (seq + 1) & 0xFFFF`). The ground station uses it to detect missed packets.

```python
    lat: float
    lon: float
```

**Lines 41–42:** Latitude and longitude as IEEE 754 binary64 (8 bytes each). `float64` is used instead of `float32` for sub-meter precision: a `float32` at mid-latitudes has ~2.4m resolution; `float64` provides nanometer precision (~1e-7 degrees ≈ 1.1 cm). This is overkill for a balloon but costs only 8 extra bytes (total 16 vs 8), and the bandwidth is not the constraint on a 20 sps BPSK link at 1 Hz burst rate.

```python
    alt_m: float
    agl_m: float
```

**Lines 43–44:** Altitude (MSL) and Above-Ground Level, both as IEEE 754 binary32 (4 bytes). `float32` provides ~1mm precision at balloon altitudes (0–40 km), which is more than sufficient. Using `float32` saves 8 bytes vs `float64` for these two fields.

```python
    fix: bool
```

**Line 45:** Whether the GPS has a valid fix. Derived from `fix_quality > 0` in `gps_packet_tx.py` line 173. Stored as a Python `bool` but packed as a byte (0 or 1).

```python
    fix_type: str
```

**Line 46:** Human-readable fix type: `"none"`, `"2d"`, or `"3d"`. Stored as a string in Python but packed as a byte per the `_FIX_TYPE_NAMES` mapping. The string representation is for ergonomics; the wire format uses the byte for compactness.

```python
    sats: int
```

**Line 47:** Number of satellites in use (0–255). Single byte on the wire. Derived from NMEA GGA sentence field 7.

```python
    hdop: float
    vdop: float
```

**Lines 48–49:** Horizontal and Vertical Dilution of Precision. `float32` on the wire (4 bytes each). DOP values are unit-less ratios typically in range 0.5–99.9; `float32` provides ample precision.

### 6.2 ClassVar for Struct (Line 51)

```python
    STRUCT: ClassVar[struct.Struct] = _POS_STRUCT
```

**Line 51:** `ClassVar` tells the dataclass machinery: "this is a class-level attribute, not an instance field." Without `ClassVar`, the `@dataclass` decorator would generate an `__init__` parameter `STRUCT`, include it in `__eq__`/`__hash__`, and (with `slots=True`) fail because `ClassVar` can't be a slot. Exposing `_POS_STRUCT` as `PositionFrame.STRUCT` allows external code to access the format without importing the module-private `_POS_STRUCT`. It also serves as documentation.

---

## 7. `pack()` Method (Lines 53–70)

```python
    def pack(self) -> bytes:
```

**Line 53:** Instance method. Called on a fully-populated `PositionFrame` to produce the 38-byte wire-format payload. Returns `bytes`.

### 7.1 Boolean-to-Byte Conversion (Lines 54–55)

```python
        fix_byte = 1 if self.fix else 0
```

**Line 54:** Python `bool` → `int` byte. `struct.pack('B', True)` would pack as `\x01`, but the explicit conversion is clearer and avoids relying on Python's `bool`-is-`int` behavior.

```python
        fix_type_byte = {v: k for k, v in _FIX_TYPE_NAMES.items()}.get(
            self.fix_type, 0
        )
```

**Lines 55–57:** String-to-byte reverse lookup. Builds the inverse dictionary `{"none": 0, "2d": 1, "3d": 2}` on every `pack()` call, then does `.get(self.fix_type, 0)`. The default `0` means unknown fix type strings silently map to `"none"`.

**Performance note:** Building the reverse dict on every call is O(3) — negligible for a map of 3 entries. If fix types ever grow to dozens, this should be precomputed as a module-level constant `_FIX_TYPE_BYTES`.

### 7.2 Struct Packing (Lines 58–70)

```python
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
```

**Lines 58–70:** Calls `struct.Struct.pack()` with 11 positional arguments matching the 11 format characters in `"<B H d d f f B B B f f"`. Notably:

- `FrameType.POSITION` is used directly (line 59) — `IntEnum` members are ints, so `struct.pack('B', FrameType.POSITION)` works.
- `self.lat` and `self.lon` are Python `float` → packed as IEEE 754 binary64 (`d` format).
- `self.alt_m`, `self.agl_m`, `self.hdop`, `self.vdop` are Python `float` → packed as IEEE 754 binary32 (`f` format). Values outside the representable range of float32 (±3.4e38) will raise `struct.error`.
- `self.seq` is Python `int` → packed as unsigned 16-bit (`H` format). Values > 65535 or < 0 raise `struct.error`.
- `self.sats` is Python `int` → packed as unsigned 8-bit (`B` format). Values > 255 or < 0 raise `struct.error`.

**Return value:** The raw 38-byte `bytes` object ready for BPSK framing.

---

## 8. `unpack()` Static Method (Lines 72–107)

```python
    @staticmethod
    def unpack(data: bytes) -> PositionFrame:
```

**Line 72:** Decorated as `@staticmethod` (not `@classmethod`). This is a factory method that takes raw bytes and returns a `PositionFrame`. It does **not** receive `cls` — it always returns `PositionFrame`, not a subclass.

### 8.1 Length Validation (Lines 74–77)

```python
        if len(data) != _POS_SIZE:
            raise ValueError(
                f"position frame: expected {_POS_SIZE} bytes, got {len(data)}"
            )
```

**Lines 74–77:** Strict length check. The position frame is a fixed-size format (38 bytes). Any deviation is an error. The error message includes both expected and actual lengths for debugging. This check catches:

- Truncated packets (CRC passed but payload was cut)
- Wrong frame type routed to `PositionFrame.unpack()` (e.g., a future motion frame might be 52 bytes)
- Bit errors in the length field of the outer BPSK frame

### 8.2 Struct Unpacking (Lines 78–90)

```python
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
```

**Lines 78–90:** `struct.Struct.unpack()` returns a tuple of 11 values matching the format string. Each value is converted from binary to the corresponding Python type:

| Format | Binary → Python |
|--------|----------------|
| `B` | raw byte → `int` |
| `H` | 2 bytes LE → `int` |
| `d` | 8 bytes LE → `float` (IEEE 754 binary64) |
| `f` | 4 bytes LE → `float` (IEEE 754 binary32) |

The leading underscore on `_type` signals "this is validated but not directly used as a field" (it's re-validated below).

### 8.3 Type Byte Validation (Lines 91–94)

```python
        if _type != FrameType.POSITION:
            raise ValueError(
                f"position frame: wrong type byte 0x{_type:02X}"
            )
```

**Lines 91–94:** Validates that the first byte is `0x01`. This is a **defense-in-depth** check. Even though `unpack_frame()` (the dispatcher) should only route `0x01` to this method, someone could call `PositionFrame.unpack()` directly with raw bytes of a different frame type. The hex formatting (`0x{_type:02X}`) makes the error message immediately diagnostic.

### 8.4 Frame Construction (Lines 95–107)

```python
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
```

**Lines 95–107:** Constructs and returns a `PositionFrame`. Notable conversions:

- **Line 102:** `fix=bool(fix_byte)` — converts the raw byte to a Python `bool`. Any non-zero byte becomes `True`. If the byte is 0, `False`. This is slightly more lenient than the `pack()` side (which only produces 0 or 1), making the unpacker robust to bit errors that flip a 0 to, say, 0xFF.

- **Line 103:** `fix_type=_FIX_TYPE_NAMES.get(fix_type_byte, "none")` — maps the byte back to a string. The default `"none"` handles unknown fix type bytes gracefully. If a bit error corrupts this byte, the dashboard will display "none" rather than crashing.

- The `type` field is set to `_type` (the validated byte) rather than `FrameType.POSITION`. This preserves the original byte value, which is always `0x01` after validation.

**Because the dataclass is `frozen=True`**, the returned `PositionFrame` is immutable. Any attempt to modify a field post-construction raises `FrozenInstanceError`.

---

## 9. Dispatcher (Lines 110–129)

### 9.1 Parser Registry (Lines 112–114)

```python
_PARSERS: dict[int, type] = {
    FrameType.POSITION: PositionFrame,
}
```

**Lines 112–114:** Module-level registry mapping frame type bytes to their parser classes. Currently only one entry. The value type is `type` (not `Callable`) because each parser class has a `.unpack()` static method. This design is extensible:

```python
# Future:
_PARSERS = {
    FrameType.POSITION: PositionFrame,
    FrameType.MOTION: MotionFrame,       # 0x02
    FrameType.ENVIRONMENT: EnvironmentFrame,  # 0x03
    FrameType.POWER: PowerFrame,         # 0x04
}
```

Adding a new frame type requires: (1) define the dataclass with `pack()`/`unpack()`, (2) add the enum member to `FrameType`, (3) register it in `_PARSERS`. The dispatcher code itself never changes.

### 9.2 `unpack_frame()` (Lines 117–125)

```python
def unpack_frame(data: bytes):
    """Return the appropriate typed frame dataclass, or None."""
```

**Line 117–118:** Module-level function. Takes raw bytes from the BPSK receiver (after CRC validation and outer frame stripping). Returns a frame dataclass instance or `None`.

```python
    if len(data) < 1:
        return None
```

**Line 119–120:** Guard against empty payloads. If the BPSK receiver delivers a zero-length payload (should never happen if CRC passed, but defensive), returns `None` rather than raising. This is the **graceful degradation** path — the caller can log and continue.

```python
    frame_type = data[0]
```

**Line 121:** Extract the first byte. `data[0]` returns an `int` on Python 3 (not a `bytes` of length 1). This is the type tag.

```python
    parser = _PARSERS.get(frame_type)
    if parser is None:
        return None
```

**Lines 122–124:** Look up the parser class. If the type byte is unknown (e.g., `0xFF` from bit errors, or a future type not yet registered), returns `None`. Again, graceful degradation. The ground station can log "unknown frame type 0xFF" without crashing the pipeline.

```python
    return parser.unpack(data)
```

**Line 125:** Delegate to the parser class's static `unpack()` method. This is dispatch by dictionary lookup — O(1) regardless of how many frame types exist. The entire raw `data` is passed (not `data[1:]`), because each parser's `unpack()` does its own length and type validation.

**Chain of responsibility:**
```
RX → CRC check → strip outer frame → unpack_frame(raw_payload)
                                          │
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                    PositionFrame    MotionFrame    EnvironmentFrame
                    .unpack(data)   .unpack(data)  .unpack(data)
```

### 9.3 `pack_frame()` (Lines 128–129)

```python
def pack_frame(frame) -> bytes:
    return frame.pack()
```

**Lines 128–129:** Thin wrapper around the frame's `pack()` method. Exists for API symmetry with `unpack_frame()`. The type annotation is omitted (just `frame`), relying on duck typing: any object with a `.pack() -> bytes` method works. This is the **strategy pattern**: the dispatcher doesn't need to know the concrete frame type.

**Usage in `gps_packet_tx.py`:**
```python
payload = frame.pack()          # line 199 — direct call
# OR equivalently:
payload = pack_frame(frame)     # line 128–129 — through dispatcher
```

Both produce identical output. The dispatcher version is preferred when frame types are determined at runtime (e.g., a generic TX loop that iterates over mixed frame types).

---

## 10. CRC-16/XMODEM Relationship (Cross-Module)

While `packet_format.py` does **not** implement CRC, the CRC is applied to its output in `gps_packet_tx.py`:

```python
# gps_packet_tx.py, lines 44–52
def crc16(data: bytes) -> int:
    """CRC-16/XMODEM (0x1021).  Returns 16-bit unsigned int."""
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc
```

And applied in the packet assembly (lines 87–88):
```python
    crc = crc16(payload)            # CRC over the 38-byte PositionFrame
    crc_bytes = struct.pack(">H", crc)  # Big-endian 16-bit
```

### The full on-air packet structure:

```
| Preamble  | Sync       | Length | Payload          | CRC-16      |
| 256 bits  | 32 bits    | 16b BE | (packet_format)  | 16b BE      |
| 1010...   | 0xE38FC0FC | 0x0026 | 0x01 + 37 bytes  | XMODEM      |
                                                  ============
                                                  THIS MODULE
```

- **Preamble:** 256 bits of alternating 1/0 for clock recovery
- **Sync word:** `0xE38FC0FC` (32-bit) for frame alignment
- **Length:** 16-bit big-endian = 38 (`0x0026`)
- **Payload:** 38 bytes produced by `PositionFrame.pack()` — **this module's output**
- **CRC-16/XMODEM:** Computed over payload only, big-endian

The CRC validates exactly the bytes that `packet_format.py` produces. If `packet_format.py` ever changes the format string, the length field and CRC expectations must be updated.

---

## 11. The 38-Byte On-Air Size and Its Implications

### 11.1 Size Derivation

| Field | Type | Bytes |
|-------|------|-------|
| type | u8 | 1 |
| seq | u16 | 2 |
| lat | f64 | 8 |
| lon | f64 | 8 |
| alt_m | f32 | 4 |
| agl_m | f32 | 4 |
| fix | u8 | 1 |
| fix_type | u8 | 1 |
| sats | u8 | 1 |
| hdop | f32 | 4 |
| vdop | f32 | 4 |
| **Total** | | **38** |

### 11.2 Transmission Time

With BPSK at 20 samples per symbol (SPS) and 2 MSPS sample rate:
- **Symbol rate:** 2,000,000 / 20 = 100,000 symbols/second = 100 kbps
- **Payload bits:** 38 × 8 = 304 bits
- **Payload time:** 304 / 100,000 = 3.04 ms
- **Full packet bits:** 256 (preamble) + 32 (sync) + 16 (length) + 304 (payload) + 16 (CRC) = 624 bits
- **Full packet time:** 624 / 100,000 = 6.24 ms
- **Burst cycle:** 1 Hz (1 second gap between packets)
- **Duty cycle:** 6.24 ms / 1000 ms = **0.624%**

The 38-byte payload is dwarfed by the 36-byte overhead (preamble + sync + length + CRC). At 1 Hz, the link is **99.4% idle**. This means:

1. **Multiple frame types could be multiplexed** within the same 1-second cycle without contention
2. **Frame size could grow** (e.g., adding a 256-byte image chunk) without affecting duty cycle significantly
3. **Future frame types** (motion at 52B, environment at 28B, power at 20B) all fit comfortably

### 11.3 Comparison with `packer.py`

The MPEG-TS telemetry path (`packer.py`) uses a separate 54-byte format:
```python
_FRAME_STRUCT = struct.Struct(">HHIfffffddfBfB")  # 54 bytes, big-endian
```

| Aspect | `packet_format.py` | `packer.py` |
|--------|-------------------|-------------|
| Transport | BPSK packet radio | MPEG-TS / DVB-S2 |
| Endianness | Little-endian (`<`) | Big-endian (`>`) |
| Size | 38 bytes | 54 bytes |
| Type tag | Yes (1 byte) | No (magic number 0xFEED) |
| Extensible | Yes (type dispatch) | No (fixed format) |
| CRC | External (TX layer) | External (MPEG-TS) |
| Design pattern | Tagged union | Fixed struct |

The two formats exist because the HAB has **redundant downlinks**: the DVB-S2 video link (high bandwidth, directional) and the BPSK packet radio link (low bandwidth, omnidirectional). `packet_format.py` serves the latter.

---

## 12. Design Patterns and Principles

### 12.1 Tagged Union / Discriminated Union

The `type` byte + `_PARSERS` registry is a binary implementation of the tagged union pattern. Each frame type has its own dataclass with its own `pack()`/`unpack()`, and the dispatcher routes by type byte. This is the same pattern used by Protobuf `oneof`, Cap'n Proto unions, and Rust `enum` with data.

### 12.2 Immutable Value Objects

`frozen=True` + `slots=True` makes `PositionFrame` an immutable value object. Frames are created, transmitted, and discarded — never mutated. This prevents entire classes of bugs (e.g., accidentally modifying a frame after queuing it for transmission).

### 12.3 Separation of Concerns

| Concern | Module |
|---------|--------|
| GPS parsing | `gps/nmea.py` |
| Frame format definition | `telemetry/packet_format.py` |
| Frame packing for TX | `gps_packet_tx.py` |
| BPSK modulation | `gps_packet_tx.py` |
| CRC / outer framing | `gps_packet_tx.py` |
| Ground station RX | `pkt_simple_rx.py` |
| Bridge to dashboard | `gps_bridge.py` |
| Dashboard display | `dashboard/` |

`packet_format.py` sits at the **exact boundary** between "what the GPS produces" and "what goes on the air." It knows nothing about GPS, NMEA, BPSK, CRC, or the dashboard. It defines a pure data contract.

### 12.4 Graceful Degradation

Both `unpack()` and `unpack_frame()` return `None` or raise descriptive `ValueError` rather than crashing on malformed data. Unknown type bytes, wrong lengths, and type mismatches are all handled explicitly. This is essential for a system receiving data over a noisy RF link where bit errors are expected.

---

## 13. Potential Issues and Future Considerations

### 13.1 Reverse Dict Construction on Every `pack()`

```python
fix_type_byte = {v: k for k, v in _FIX_TYPE_NAMES.items()}.get(self.fix_type, 0)
```

Building a new dict on every `pack()` call is wasteful. At 1 Hz this is negligible, but a precomputed `_FIX_TYPE_BYTES = {"none": 0, "2d": 1, "3d": 2}` module-level constant would be cleaner.

### 13.2 No Version Field

The frame format has no version byte. If the format changes (e.g., adding fields to `PositionFrame`), old receivers will misinterpret the data. A version nibble in the type byte (e.g., `0x11` = position v1, `0x12` = position v2) would allow backward compatibility.

### 13.3 No Timestamp Field

`PositionFrame` has no embedded timestamp. The bridge adds `t` (time) to the dashboard JSON, but the frame itself has no way to represent "when was this GPS fix acquired." The NMEA sentence contains a UTC timestamp (`$GPGGA,hhmmss.ss,...`) that is discarded during parsing.

### 13.4 Type Byte Ambiguity

If a bit error flips `0x01` to `0x00`, `unpack_frame()` returns `None` (unknown type 0x00) rather than attempting to parse it as a corrupted position frame. This is correct behavior, but the error is silent — the caller must check for `None` and log appropriately.

### 13.5 `fix` Field Is Redundant with `fix_type`

`fix=True` is equivalent to `fix_type != "none"`. Both are packed separately, consuming an extra byte. This redundancy exists because the dashboard schema has separate `fix: boolean` and `fix_type: string` fields. The byte-level redundancy means bit errors could produce the inconsistent state `fix=True, fix_type="none"`.

---

## 14. Summary Table

| Aspect | Detail |
|--------|--------|
| **File** | `payload/telemetry/packet_format.py` |
| **Lines** | 129 |
| **Format string** | `"<B H d d f f B B B f f"` |
| **Endianness** | Little-endian |
| **Frame size** | 38 bytes |
| **Live frame type** | `0x01` (POSITION) |
| **Reserved types** | `0x02` (MOTION), `0x03` (ENVIRONMENT), `0x04` (POWER) |
| **Dataclass config** | `frozen=True, slots=True` |
| **Dispatch pattern** | Dictionary lookup by type byte |
| **CRC** | External (CRC-16/XMODEM in `gps_packet_tx.py`) |
| **Related modules** | `gps_packet_tx.py` (TX), `packer.py` (alternate format), `gps_bridge.py` (RX→dashboard) |
