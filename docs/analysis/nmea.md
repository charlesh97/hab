# Exhaustive Line-by-Line Analysis of `nmea.py`

**File:** `payload/gps/nmea.py` (180 lines)
**Context:** HAB (High-Altitude Balloon) packet radio — GPS-to-BPSK pipeline
**Hardware:** Quectel L76K GNSS module → Radxa Rock 2A UART0 (pins 8/10) at 9600 baud 8N1
**Used by:** `payload/tx/gps_packet_tx.py` (main TX loop), `payload/tests/test_gps.py` (Phase 1D validation)

---

## Table of Contents

1. [Module Docstring & Imports (Lines 1–6)](#1-module-docstring--imports-lines-16)
2. [Module-Level Constants (Lines 8–9)](#2-module-level-constants-lines-89)
3. [`nmea_checksum_ok()` — Checksum Validation (Lines 12–31)](#3-nmea_checksum_ok--checksum-validation-lines-1231)
4. [`_safe_float()` — Robust Float Parsing (Lines 34–40)](#4-_safe_float--robust-float-parsing-lines-3440)
5. [`_nmea_dm_to_dd()` — Coordinate Conversion (Lines 43–68)](#5-_nmea_dm_to_dd--coordinate-conversion-lines-4368)
6. [`parse_gga()` — GGA Sentence Parser (Lines 71–102)](#6-parse_gga--gga-sentence-parser-lines-71102)
7. [`parse_rmc()` — RMC Sentence Parser (Lines 105–134)](#7-parse_rmc--rmc-sentence-parser-lines-105134)
8. [`NMEAParser` Class (Lines 137–180)](#8-nmeaparser-class-lines-137180)
9. [Hardware Integration: L76K on Rock 2A](#9-hardware-integration-l76k-on-rock-2a)
10. [Usage in the Pipeline](#10-usage-in-the-pipeline)
11. [Error Handling & Robustness Summary](#11-error-handling--robustness-summary)
12. [Design Observations & Tradeoffs](#12-design-observations--tradeoffs)

---

## 1. Module Docstring & Imports (Lines 1–6)

### Line 1
```python
"""GPS NMEA parser using a 9600-baud 8N1 serial connection."""
```
The module docstring. Concise but precise: it names the protocol (NMEA), the physical layer (serial), the bit rate (9600 baud), and the framing (8 data bits, No parity, 1 stop bit — 8N1). This is not aspirational — it's the exact configuration the L76K ships with by default.

### Line 3
```python
from __future__ import annotations
```
Enables PEP 563 / PEP 604 `X | Y` union syntax without runtime cost. Available from Python 3.7+. Placed at the top of the file after the docstring, before any other imports, as required. This allows the module to use `str | None`, `float | None`, `dict[str, object] | None` in type hints without importing `Optional` or `Union` from `typing`.

### Line 5
```python
import serial
```
Single external dependency: `pyserial`. This is a pure-Python library that wraps OS-level serial port access (`/dev/ttyS0`, `/dev/ttyAMA0`, etc. on Linux; `COM` ports on Windows). On line 5, there is no try/except guard — the import is assumed to succeed. The TX pipeline and test scripts handle the `ImportError` at their own level. Given the target platform (Radxa Rock 2A running Armbian Debian 13), `pyserial` is installed via `apt` or `pip`.

---

## 2. Module-Level Constants (Lines 8–9)

### Line 8
```python
GPS_BAUD = 9600
```
The serial baud rate. 9600 is the L76K's factory default communication speed. This is intentionally low — GPS modules output at most a few dozen NMEA sentences per second, each under 100 bytes, so 9600 baud (~960 chars/sec) is more than sufficient. Higher baud rates (115200) are available on the L76K but would require explicit AT command configuration. 9600 baud was chosen because it's the module's power-on default — no init dance needed; just open the port.

### Line 9
```python
GPS_TIMEOUT = 1.0
```
Serial read timeout in seconds. Passed to `serial.Serial(timeout=...)`. With a 1-second timeout, `readline()` will block for at most 1 second waiting for a newline character. If no complete line arrives within that window, `readline()` returns whatever partial data has been buffered (or an empty bytes object if nothing was received at all). This is a critical design choice:

- **Too short** (e.g., 0.1s): risk of truncating valid NMEA sentences mid-stream, especially on a busy bus with GSV sentences arriving in bursts.
- **Too long** (e.g., 5s): the TX loop in `gps_packet_tx.py` runs at 1 Hz — a 5-second timeout would stall the loop and miss transmission windows if GPS data stops.
- **1.0s** is the sweet spot: it's a full GPS epoch (most modules output position fixes at 1 Hz), so if no data arrives in 1 second, something is wrong.

---

## 3. `nmea_checksum_ok()` — Checksum Validation (Lines 12–31)

### Line 12
```python
def nmea_checksum_ok(sentence: str) -> bool:
```
Module-level function (not inside the class). Takes a raw NMEA sentence string and returns `True` only if the checksum validates. The NMEA 0183 standard specifies that each sentence ends with `*HH` where `HH` is the two-character hexadecimal XOR checksum of all bytes between (but not including) `$` and `*`. The type hint `str -> bool` is simple and honest.

### Line 13
```python
    """Validate the XOR checksum of an NMEA sentence."""
```
Docstring. Brief but accurate. Does not mention the return type or edge cases — the code is self-documenting.

### Line 14–17
```python
    try:
        payload, checksum_str = sentence.split("*")
    except (AttributeError, ValueError):
        return False
```
The first computational block. `split("*")` on a string with no `*` raises `ValueError` (too few values to unpack). `AttributeError` is caught because `sentence` could theoretically be `None` (calling `.split()` on `None` raises `AttributeError`), though in practice callers don't pass `None`. Both exceptions return `False` — the sentence is considered invalid. This is a fail-closed approach: any structural anomaly means "not valid."

**`payload`** gets everything before the asterisk (e.g., `$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,`).
**`checksum_str`** gets everything after the asterisk (e.g., `47`). Note that `checksum_str` may include trailing whitespace or Carriage Return — that's handled at line 27.

### Line 19–20
```python
    if not payload.startswith("$"):
        return False
```
Guard: if the part before `*` doesn't start with `$`, it's not a proper NMEA sentence. This catches garbage lines, binary noise, or malformed data. Example of what fails: `GPGGA,120000,...*1A` (missing `$`).

### Lines 22–24
```python
    computed = 0
    for char in payload[1:]:
        computed ^= ord(char)
```
The core XOR checksum computation. The NMEA standard says: "The checksum is the 8-bit exclusive OR (no start or stop bits) of all characters in the sentence, including `,` delimiters, between but not including `$` and `*`."

- `computed = 0` initializes the accumulator.
- `payload[1:]` skips the leading `$` — this is crucial. Including `$` in the XOR would produce a wrong checksum.
- `ord(char)` converts each character to its ASCII byte value (0–127).
- `^=`: XOR-accumulation. `0 ^ X = X`, and each subsequent byte XORs with the running total.

For `$GPGGA,123519,...*47`:
- Payload after `$`: `GPGGA,123519,...`
- `computed = ord('G') ^ ord('P') ^ ord('G') ^ ord('G') ^ ord('A') ^ ord(',') ^ ...`

### Lines 26–29
```python
    try:
        expected = int(checksum_str.strip(), 16)
    except ValueError:
        return False
```
Parses the expected checksum from the string after `*`. `strip()` removes whitespace and trailing `\r` (carriage return, common in NMEA serial output). `int(..., 16)` parses hex: `"47"` → `0x47` (71 decimal). If `checksum_str` is not valid hex (e.g., `"ZZ"`, or empty), `ValueError` is caught and returns `False`.

### Line 31
```python
    return computed == expected
```
The final comparison. Returns `True` only if the XOR of the payload bytes matches the declared hex checksum. This is the gatekeeper: only sentences with valid checksums pass. In the HAB pipeline, a corrupted checksum means the sentence was damaged in transit over the UART connection (unlikely but possible with long wires or EMI) and the data is discarded — better to lose one fix than transmit bad coordinates.

---

## 4. `_safe_float()` — Robust Float Parsing (Lines 34–40)

### Line 34
```python
def _safe_float(value: str) -> float | None:
```
The leading underscore marks this as a module-internal helper. Takes a string (an NMEA field) and returns either a `float` or `None`. The return type `float | None` uses the PEP 604 union syntax.

### Lines 35–36
```python
    if not value or not value.strip():
        return None
```
Two-part guard:
- `not value`: catches `""` (empty string, which is falsy) and potentially `None` (though the type hint says `str`).
- `not value.strip()`: catches fields that are only whitespace, e.g., `"   "` or `"\r"`.

In NMEA, empty fields are common: for example, `$GPGGA,...*47,,,` has two adjacent commas, meaning the field between them is empty. Some receivers also output fields like `,,` for altitude when no fix is available. Return `None` for any of these cases — no attempt to parse as float.

### Lines 37–38
```python
    try:
        return float(value)
```
Attempts to parse the string as a float. Python's `float()` handles both integer-looking strings (`"08"` → `8.0`) and decimal strings (`"0.9"` → `0.9`). Strips leading/trailing whitespace automatically, but the guard above already handled blank fields.

### Lines 39–40
```python
    except ValueError:
        return None
```
Catches any non-numeric string (e.g., `"N/A"`, `"invalid"`, or corrupted binary garbage). Returns `None` — the caller must handle missing data.

---

## 5. `_nmea_dm_to_dd()` — Coordinate Conversion (Lines 43–68)

### Line 43
```python
def _nmea_dm_to_dd(raw: str, hemisphere: str) -> float | None:
```
Converts NMEA's Degrees-Minutes format (DDMM.MMMM or DDDMM.MMMM) to decimal degrees. Takes two arguments:
- `raw`: the coordinate string from the NMEA field (e.g., `"4807.038"` for 48°07.038', or `"01131.000"` for 11°31.000').
- `hemisphere`: `"N"`, `"S"`, `"E"`, or `"W"`. Determines sign.

Returns `float` (decimal degrees, rounded to 6 decimal places) or `None` on parse failure.

### Lines 45–46
```python
    if not raw or not hemisphere:
        return None
```
Guard: both arguments must be non-empty. If either is empty, the coordinate is meaningless.

### Lines 48–52
```python
    try:
        if "." in raw:
            int_part, frac_part = raw.split(".", 1)
        else:
            int_part, frac_part = raw, "0"
```
Splits the raw coordinate at the decimal point into integer and fractional parts. The `1` argument to `split` limits to one split — important if there were somehow multiple dots (though that shouldn't happen with valid NMEA). If there's no decimal point (unlikely in practice), treats the entire string as integer part and `"0"` as fractional.

Example: `"4807.038"` → `int_part="4807"`, `frac_part="038"`

The `try` wraps the entire function body — any `ValueError` or `IndexError` from any operation returns `None`.

### Lines 54–57
```python
        if len(int_part) <= 4:
            degree_length = 2
        else:
            degree_length = 3 if hemisphere in ("E", "W") else 2
```
This is the most subtly important logic in the file: determining how many digits represent degrees vs. minutes.

**Latitude (N/S):** Always 2 digits for degrees (max 90°). So `"4807.038"` → 2 degree digits + minutes.

**Longitude (E/W):** Either 2 or 3 digits (max 180°). The ambiguity arises because raw longitude can be `"01131.000"` (3 digits for 11°) or `"12045.678"` (3 digits for 120°). The heuristic:
- If `len(int_part) <= 4`: the total integer portion is short. If it's 4 digits like `"4807"`, that's 2 degree digits. If it's 5 digits like `"01131"`, that's 3 degree digits. But at this branch `len(int_part) <= 4`, so only ever 2 degree digits.
- If `len(int_part) > 4` (i.e., 5 digits like `"12045"` for 120°45'): degree_length is 3 for E/W (longitude can be up to 180°), 2 for N/S (latitude never exceeds 90°, so 5 digits would mean 2 degree digits + 3-minute integer digits for latitudes near the poles).

This logic is a simplified version of the test script's approach. It handles all valid NMEA coordinates but could theoretically misparse a 5-digit latitude if one were received (should never happen — latitudes are max ~90°, so the integer part is at most 2 digits for degrees, making the total integer part at most 4 digits: `"90"` + `"00"` = `"9000"`).

### Lines 59–61
```python
        degrees = float(int_part[:degree_length])
        minutes = float(int_part[degree_length:] + "." + frac_part)
        decimal_degrees = degrees + minutes / 60.0
```
The actual conversion:
- `int_part[:degree_length]` extracts the degree digits. For `"4807"` with `degree_length=2`: `"48"` → 48.0°.
- `int_part[degree_length:]` extracts the minute integer portion: `"07"`.
- `+ "." + frac_part` reconstructs the fractional minutes: `"07"` + `"."` + `"038"` → `"07.038"` → 7.038 minutes.
- `degrees + minutes / 60.0`: 48.0 + 7.038/60 = 48.0 + 0.1173 = 48.1173.

### Lines 63–64
```python
        if hemisphere in ("S", "W"):
            decimal_degrees = -decimal_degrees
```
Southern latitudes and western longitudes are negative. Northern latitudes and eastern longitudes are positive. This follows standard convention (WGS84).

### Line 66
```python
        return round(decimal_degrees, 6)
```
Rounds to 6 decimal places. At the equator, 0.000001° ≈ 0.111 meters. This is far more precision than the L76K's stated accuracy (2.5m CEP), so no meaningful precision is lost. Rounding also avoids floating-point display artifacts (e.g., `48.117300000000004`).

### Lines 67–68
```python
    except (ValueError, IndexError):
        return None
```
Catch-all for any parsing failure within the try block. Returns `None` — the caller (`parse_gga` or `parse_rmc`) propagates `None` to the result dict.

---

## 6. `parse_gga()` — GGA Sentence Parser (Lines 71–102)

### Line 71
```python
def parse_gga(sentence: str) -> dict[str, object] | None:
```
Module-level function. Takes a raw NMEA GGA sentence string. Returns a dictionary with parsed fields, or `None` if the sentence is invalid. The `object` type in the return annotation is a pragmatic choice — the dict contains `str`, `float`, `int`, and `None` values at runtime. Returns `None` for any sentence that is structurally invalid, has invalid checksum, is not a GGA sentence, or is missing critical fields.

### GGA Sentence Format (reference)

```
$GPGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
|      |         |         | |         | | |  |   |     | |     | |  |
0      1         2         3 4         5 6 7  8   9     10 11   12 13 14
```

| Field Index | Name           | Example      | Description                              |
|-------------|----------------|--------------|------------------------------------------|
| 0           | Talker+ID      | $GPGGA       | Sentence identifier                      |
| 1           | UTC Time       | 123519.00    | HHMMSS.SS UTC                            |
| 2           | Latitude       | 4807.038     | DDMM.MMMM                                |
| 3           | N/S indicator  | N            | 'N' or 'S'                               |
| 4           | Longitude      | 01131.000    | DDDMM.MMMM                               |
| 5           | E/W indicator  | E            | 'E' or 'W'                               |
| 6           | Fix Quality    | 1            | 0=invalid, 1=GPS fix, 2=DGPS, 6=DR       |
| 7           | Satellites     | 08           | Number of satellites used                |
| 8           | HDOP           | 0.9          | Horizontal dilution of precision         |
| 9           | Altitude       | 545.4        | Altitude above MSL (meters)              |
| 10          | Altitude units | M            | 'M' for meters                           |
| 11          | Geoid height   | 46.9         | Height of geoid above WGS84 ellipsoid    |
| 12          | Geoid units    | M            | 'M' for meters                           |
| 13          | DGPS age       | (empty)      | Time since last DGPS update              |
| 14          | DGPS station   | (empty)      | DGPS reference station ID                |

### Line 73
```python
    sentence = sentence.strip()
```
Strips leading and trailing whitespace (including `\r\n`). NMEA sentences from serial ports typically arrive as `$GPGGA,...*47\r\n`. The `\r\n` must be removed before checksum validation, since the checksum computation does not include `\r` or `\n`.

### Lines 74–75
```python
    if not nmea_checksum_ok(sentence):
        return None
```
Checksum validation is the first gate. If the checksum doesn't match, the sentence is discarded immediately — no parsing of fields.

### Lines 77–79
```python
    fields = sentence.split(",")
    if len(fields) < 11 or not fields[0].lstrip("$").endswith("GGA"):
        return None
```
Two checks:
1. **`len(fields) < 11`**: A valid GGA sentence has at least 11 comma-separated fields (indices 0–10). Fields 11–14 are optional. This check ensures we have enough fields to extract time, position, fix quality, satellites, HDOP, and altitude.
2. **`fields[0].lstrip("$").endswith("GGA")`**: The first field must identify as a GGA sentence. `lstrip("$")` removes the leading `$`, then `endswith("GGA")` matches any talker prefix: `GPGGA` (GPS), `GLGGA` (GLONASS), `GNGGA` (multi-constellation), `BDGGA` (BeiDou). The L76K is a multi-GNSS receiver and will output sentences with different talker IDs depending on which constellations are active.

### Lines 81–89 — Field Extraction

```python
    utc_time = fields[1]
    lat_raw = fields[2]
    lat_ns = fields[3]
    lon_raw = fields[4]
    lon_ew = fields[5]
    fix_quality = _safe_float(fields[6])
    satellites = _safe_float(fields[7])
    altitude = _safe_float(fields[9])
    hdop = _safe_float(fields[8])
```

Each field is extracted by positional index:

- **`utc_time` (field 1):** Raw UTC time string, e.g., `"123519.00"` for 12:35:19.00 UTC. Stored as-is; no parsing to datetime object.
- **`lat_raw` (field 2):** Raw latitude in DDMM.MMMM format, e.g., `"4807.038"`.
- **`lat_ns` (field 3):** Hemisphere for latitude — `"N"` or `"S"`.
- **`lon_raw` (field 4):** Raw longitude in DDDMM.MMMM format, e.g., `"01131.000"`.
- **`lon_ew` (field 5):** Hemisphere for longitude — `"E"` or `"W"`.
- **`fix_quality` (field 6):** Numeric fix quality indicator, parsed via `_safe_float`. Returns `None` if empty/invalid.
  - 0 = invalid / no fix
  - 1 = GPS fix (SPS)
  - 2 = DGPS fix
  - 4 = RTK fixed (not expected from L76K)
  - 5 = RTK float (not expected from L76K)
  - 6 = Dead reckoning (estimated)
- **`satellites` (field 7):** Number of satellites used in the position solution. `_safe_float` handles empty strings (no fix) → `None`.
- **`altitude` (field 9):** Altitude above Mean Sea Level in meters. Note: field 8 (HDOP) is extracted *after* field 9 — this is intentional: the order in the assignment doesn't matter since each is independent.
- **`hdop` (field 8):** Horizontal Dilution of Precision. A dimensionless number; lower is better. `<1.0` is excellent, `1-2` is good, `>5` is poor. hdop is extracted from field 8 (sandwiched between satellites and altitude) and parsed to `float` or `None`.

Note: altitude units (field 10, `"M"`) and geoid separation (fields 11–12) are not extracted — they're not needed for the PositionFrame.

### Lines 91–92
```python
    if not utc_time or not lat_raw or not lon_raw:
        return None
```
The three critical fields: time, latitude, and longitude. If any is empty or falsy (including `""`), the sentence is discarded. This handles the case where a GGA sentence has valid checksum but represents a "no fix" state with empty position fields. Without this guard, `_nmea_dm_to_dd` would get empty strings.

### Lines 94–102 — Return Dict Construction
```python
    return {
        "time": utc_time,
        "lat": _nmea_dm_to_dd(lat_raw, lat_ns),
        "lon": _nmea_dm_to_dd(lon_raw, lon_ew),
        "fix_quality": int(fix_quality) if fix_quality is not None else None,
        "altitude": altitude,
        "satellites": int(satellites) if satellites is not None else None,
        "hdop": hdop,
    }
```

Key field mappings:

| Dict Key       | Source       | Notes                                                               |
|----------------|--------------|---------------------------------------------------------------------|
| `"time"`       | `utc_time`   | Raw string, e.g., `"123519.00"`. Not parsed to structured time.    |
| `"lat"`        | `_nmea_dm_to_dd(lat_raw, lat_ns)` | Decimal degrees, e.g., `48.1173`. `None` if conversion fails. |
| `"lon"`        | `_nmea_dm_to_dd(lon_raw, lon_ew)` | Decimal degrees, e.g., `11.516667`. `None` if conversion fails. |
| `"fix_quality"`| `fix_quality` | Converted to `int` (e.g., `float(1.0)` → `int(1)`). `None` if unparseable. |
| `"altitude"`   | `altitude`    | `float` meters MSL or `None`.                                      |
| `"satellites"` | `satellites`  | Converted to `int`. `None` if unparseable.                          |
| `"hdop"`       | `hdop`        | `float` or `None`.                                                  |

The `int(fix_quality) if fix_quality is not None else None` pattern ensures that values like `1.0` (parsed by `_safe_float` which returns `float`) become `int` `1` rather than `1.0`. Similarly for `satellites`. This matters for downstream consumers (`gps_packet_tx.py` line 172: `int(fq) if fq is not None else 0`) which expect integer values.

**Important:** The `"altitude"` field is stored as a raw `float` — no `int()` conversion because altitude can legitimately have fractional meters (`545.4`). The TX pipeline assigns this directly to `PositionFrame.alt_m` (a float field).

---

## 7. `parse_rmc()` — RMC Sentence Parser (Lines 105–134)

### Line 105
```python
def parse_rmc(sentence: str) -> dict[str, object] | None:
```
Module-level function for parsing RMC (Recommended Minimum Navigation Information) sentences. RMC provides time, date, position, speed over ground, and track angle. While not currently used in the main TX pipeline (which only calls `parse_gga`), it's included for completeness and is exercised in the test script.

### RMC Sentence Format (reference)

```
$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A
|      |       | |         | |         | |     |     |      |     |
0      1       2 3         4 5         6 7     8     9      10    11
```

| Field Index | Name           | Example      | Description                              |
|-------------|----------------|--------------|------------------------------------------|
| 0           | Talker+ID      | $GPRMC       | Sentence identifier                      |
| 1           | UTC Time       | 123519       | HHMMSS UTC                               |
| 2           | Status         | A            | 'A'=valid, 'V'=warning                   |
| 3           | Latitude       | 4807.038     | DDMM.MMMM                                |
| 4           | N/S indicator  | N            | 'N' or 'S'                               |
| 5           | Longitude      | 01131.000    | DDDMM.MMMM                               |
| 6           | E/W indicator  | E            | 'E' or 'W'                               |
| 7           | Speed (knots)  | 022.4        | Speed over ground                         |
| 8           | Track angle    | 084.4        | Course over ground, degrees true          |
| 9           | Date           | 230394       | DDMMYY                                   |
| 10          | Mag variation  | 003.1        | Magnetic variation, degrees              |
| 11          | Var direction  | W            | 'E' or 'W'                               |

### Lines 107–109
```python
    sentence = sentence.strip()
    if not nmea_checksum_ok(sentence):
        return None
```
Same pattern as `parse_gga`: strip whitespace, validate checksum first.

### Lines 111–113
```python
    fields = sentence.split(",")
    if len(fields) < 10 or not fields[0].lstrip("$").endswith("RMC"):
        return None
```
Minimum 10 fields for RMC (indices 0–9). Matches any talker prefix ending with `RMC`: `GPRMC`, `GLRMC`, `GNRMC`.

### Lines 115–122 — Field Extraction
```python
    utc_time = fields[1]
    lat_raw = fields[3]
    lat_ns = fields[4]
    lon_raw = fields[5]
    lon_ew = fields[6]
    speed_knots = _safe_float(fields[7])
    track_angle = _safe_float(fields[8])
    date = fields[9]
```
Note the index offsets: in RMC, fields 3–6 are position (vs. 2–5 in GGA) because field 2 is the status byte. Speed is in knots, track angle in degrees true.

### Lines 124–125
```python
    if not utc_time or not date:
        return None
```
RMC's critical fields are time and date — position is optional (can be empty for a valid-but-no-fix RMC). This differs from GGA where lat/lon are required.

### Lines 127–134 — Return Dict Construction
```python
    return {
        "time": utc_time,
        "lat": _nmea_dm_to_dd(lat_raw, lat_ns) if lat_raw and lat_ns else None,
        "lon": _nmea_dm_to_dd(lon_raw, lon_ew) if lon_raw and lon_ew else None,
        "speed_knots": speed_knots,
        "track_angle": track_angle,
        "date": date,
    }
```
Key difference from GGA: lat/lon are guarded with `if lat_raw and lat_ns else None` — position is optional in RMC. A valid RMC sentence can have empty position fields (e.g., when there's no GPS fix but the receiver still outputs time from its internal clock).

**Fields not extracted:** magnetic variation (fields 10–11) and status (field 2). The status byte (`A`/`V`) is useful but not needed for the current pipeline.

---

## 8. `NMEAParser` Class (Lines 137–180)

### Line 137–138
```python
class NMEAParser:
    """Read and parse NMEA sentences from a serial GPS receiver."""
```
The class wraps the `serial.Serial` connection and provides methods to read validated NMEA sentences and parse them. It's designed as a context manager for clean resource cleanup.

### Line 140 — `__init__`

```python
    def __init__(self, device: str) -> None:
```
Constructor takes a single argument: `device` — the filesystem path to the serial device (e.g., `"/dev/ttyS0"`).

### Lines 141–148 — Serial Port Initialization
```python
        self.serial = serial.Serial(
            port=device,
            baudrate=GPS_BAUD,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=GPS_TIMEOUT,
        )
```
Creates a `serial.Serial` object with the following configuration:

| Parameter        | Value                  | Meaning                                              |
|------------------|------------------------|------------------------------------------------------|
| `port`           | `device` (e.g., `/dev/ttyS0`) | The serial device file                            |
| `baudrate`       | `9600`                 | 9600 bits per second                                 |
| `bytesize`       | `EIGHTBITS` (8)        | 8 data bits per byte                                 |
| `parity`         | `PARITY_NONE` ('N')    | No parity bit                                        |
| `stopbits`       | `STOPBITS_ONE` (1)     | 1 stop bit                                           |
| `timeout`        | `1.0`                  | 1-second read timeout                                |

This is the standard "9600 8N1" configuration that the L76K defaults to. No flow control (RTS/CTS) is configured — the L76K doesn't use hardware flow control for NMEA output.

**Important:** `serial.Serial()` may raise `serial.SerialException` if the device doesn't exist or can't be opened (e.g., permission denied). The `__init__` method does not catch this — it propagates to the caller. In `gps_packet_tx.py`, the caller is expected to handle the failure (though the current code at line 142 does not wrap in try/except — it assumes the device is available).

### Lines 150–159 — `read_sentence()`

```python
    def read_sentence(self) -> str | None:
        """Return the next checksum-valid NMEA sentence, or None on timeout."""
        while True:
            raw_line = self.serial.readline()
            if not raw_line:
                return None

            sentence = raw_line.decode("ascii", errors="ignore").strip()
            if sentence and nmea_checksum_ok(sentence):
                return sentence
```

This is the core read loop. Let's go line by line:

**Line 152: `while True:`** — An infinite loop that runs until either a valid sentence is found or a timeout occurs.

**Line 153: `raw_line = self.serial.readline()`** — Reads bytes from the serial port until a newline (`\n`) is encountered or the timeout expires. Returns a `bytes` object. With `timeout=1.0`, if no newline arrives within 1 second, `readline()` returns whatever partial data is in the buffer — or an empty `bytes` object if nothing was received at all.

**Lines 154–155:**
```python
            if not raw_line:
                return None
```
If `raw_line` is empty (falsy `bytes`, e.g., `b""`), the read timed out. Returns `None` to signal to the caller that no data is available. This is the only way to exit the loop without returning a valid sentence. The TX loop in `gps_packet_tx.py` checks for `None` and simply continues its 1 Hz cycle without updating position.

**Line 157:**
```python
            sentence = raw_line.decode("ascii", errors="ignore").strip()
```
Decodes the raw bytes to a string using ASCII encoding. `errors="ignore"` is defensive: if any non-ASCII bytes appear (due to electrical noise, buffer corruption, or a misconfigured baud rate), they are silently dropped rather than raising `UnicodeDecodeError`. `.strip()` removes the trailing `\r\n` (carriage return + newline) that most GPS receivers append.

**Lines 158–159:**
```python
            if sentence and nmea_checksum_ok(sentence):
                return sentence
```
Two guards:
1. `sentence` must be truthy — if decoding produced an empty string (all bytes were non-ASCII or just whitespace), skip it.
2. `nmea_checksum_ok(sentence)` must return `True` — the XOR checksum must validate.

If both pass, the valid sentence is returned. If not, the loop continues (`while True` goes back to line 153) to read the next line.

**Behavior under partial/malformed sentences:**
- If a line arrives without `*` (no checksum field), `nmea_checksum_ok` returns `False` → loop continues.
- If a line has `*` but the checksum is wrong (single-bit corruption), `nmea_checksum_ok` returns `False` → loop continues.
- If a line is just noise (garbage bytes), decoding with `errors="ignore"` may produce an empty string → `sentence` is falsy → loop continues.
- If `readline()` returns partial data (no `\n` within the timeout), that partial line is processed — if it happens to be a valid sentence ending in `\n` that arrives just before timeout, it works; otherwise the partial line fails checksum or is empty and the loop continues.

**Important timing implication:** The loop is potentially unbounded. If the GPS receiver is powered but not outputting valid NMEA (e.g., no satellite fix, antenna disconnected), `read_sentence()` will keep looping through `readline()` → timeout → empty → check → loop. Each iteration takes up to 1 second (the timeout). In `gps_packet_tx.py`, this is called once per 1-second burst cycle — so worst case, the TX loop takes one extra second per cycle if GPS data is unavailable. This is acceptable for the HAB use case.

### Lines 161–163 — `checksum_valid()` (Static)

```python
    @staticmethod
    def checksum_valid(sentence: str) -> bool:
        return nmea_checksum_ok(sentence)
```
A thin static wrapper around the module-level `nmea_checksum_ok`. This is a convenience method so callers using an `NMEAParser` instance can validate checksums without importing the module-level function. Marked `@staticmethod` because it doesn't use `self`.

### Lines 165–167 — `parse_gga()` (Static)

```python
    @staticmethod
    def parse_gga(sentence: str) -> dict[str, object] | None:
        return parse_gga(sentence)
```
Static method that delegates to the module-level `parse_gga` function. This is a convenience so callers can do `parser.parse_gga(sentence)` instead of needing to import `parse_gga` separately. In practice, `gps_packet_tx.py` imports `parse_gga` directly (line 30: `from gps.nmea import NMEAParser, parse_gga`) and calls the module-level function.

### Lines 169–171 — `parse_rmc()` (Static)

```python
    @staticmethod
    def parse_rmc(sentence: str) -> dict[str, object] | None:
        return parse_rmc(sentence)
```
Same pattern as `parse_gga` — static delegation to the module-level `parse_rmc`.

### Lines 173–174 — `close()`

```python
    def close(self) -> None:
        self.serial.close()
```
Closes the underlying serial port. This releases the file descriptor and makes the device available to other processes. Called explicitly in `gps_packet_tx.py` in the `finally` block (line 232). Also called by `__exit__`.

### Lines 176–177 — `__enter__()`

```python
    def __enter__(self) -> NMEAParser:
        return self
```
Context manager entry. Returns `self` so `with NMEAParser("/dev/ttyS0") as gps:` works. The return type annotation `NMEAParser` uses the forward-reference-capable PEP 563 syntax enabled by `from __future__ import annotations` at line 3.

### Lines 179–180 — `__exit__()`

```python
    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
```
Context manager exit. Calls `close()` on the serial port whether the `with` block exits normally or via exception. The `exc_type`, `exc_value`, and `traceback` parameters are typed as `object` (the standard type for `__exit__` parameters — they could be `None` or exception types). The method always calls `close()` and does not suppress exceptions (returns `None`/falsy, so exceptions propagate).

This means you can write:
```python
with NMEAParser("/dev/ttyS0") as gps:
    sentence = gps.read_sentence()
    if sentence:
        fix = gps.parse_gga(sentence)
# serial port is guaranteed closed here
```

---

## 9. Hardware Integration: L76K on Rock 2A

### Physical Connection

The Quectel L76K GNSS module connects to the Radxa Rock 2A via UART0:

```
L76K TX  ────  Rock 2A GPIO4_D0 (pin 8, RX)
L76K RX  ────  Rock 2A GPIO4_C7 (pin 10, TX)
L76K GND ────  Rock 2A GND
L76K VCC ────  Rock 2A 3.3V
```

The L76K is actually mounted on a Seeed Studio XIAO expansion board (schematic: `reference/109100021-L76K-GNSS-Module-for-Seeed-Studio-XIAO-Schematic.pdf`), which provides level shifting and power regulation.

### UART0 on the Rock 2A

`/dev/ttyS0` maps to UART0 on the Rockchip RK3528 SoC. This is a hardware UART — not a bit-banged software serial — so timing is reliable. The Rock 2A's Armbian Debian 13 image exposes this as a standard Linux serial device.

The test script (`payload/tests/test_gps.py`, lines 37–41) defines a fallback candidate list:
```python
UART_CANDIDATES = [
    "/dev/ttyS0",
    "/dev/ttyS1",
    "/dev/ttyAMA0",
]
```
On the current Rock 2A hardware, `/dev/ttyS0` is the correct device.

### Baud Rate: Why 9600?

The L76K defaults to 9600 baud at power-up. This is the standard for most GPS/GNSS modules. The module is capable of higher rates (up to 115200) but:
1. 9600 is sufficient for the ~50-80 bytes per NMEA sentence at 1–10 Hz update rate.
2. Using the default avoids any init sequence (AT commands to change baud rate).
3. Lower baud rates are more noise-immune over long wires.

The TX pipeline (`gps_packet_tx.py`, line 143) overrides the baud rate after construction:
```python
gps = NMEAParser(args.device)
gps.serial.baudrate = args.baud
```
This allows command-line override via `--baud`, but defaults to 9600.

### Power-Up Behavior

When the L76K powers on:
1. Cold start: acquires almanac/ephemeris data from satellites. Can take 30 seconds to several minutes.
2. During cold start, it outputs `$GPGGA` sentences with empty position fields and fix_quality=0.
3. `parse_gga()` rejects these (line 91: `if not utc_time or not lat_raw or not lon_raw: return None`).
4. `read_sentence()` keeps trying other sentences (e.g., GSV with satellite info, which have valid checksums but aren't GGA).
5. Once a 3D fix is acquired (typically 4+ satellites), GGA sentences populate position fields and the TX pipeline starts transmitting.

---

## 10. Usage in the Pipeline

### In `gps_packet_tx.py` (TX Pipeline)

The main usage pattern (lines 142–183):

```python
gps = NMEAParser(args.device)           # Open serial port
gps.serial.baudrate = args.baud         # Override baud rate if needed

while True:
    sentence = gps.read_sentence()       # Block until valid sentence or timeout
    if sentence:
        fix = parse_gga(sentence)        # Parse GGA
        if fix is not None:
            # Update last-known position from fix dict
            last_lat = float(fix["lat"])
            last_lon = float(fix["lon"])
            # ... etc

    # Build PositionFrame with last-known values (stale-safe)
    frame = PositionFrame(...)
    # Modulate and transmit via HackRF
```

Key design pattern: **last-known-good position**. If `read_sentence()` returns `None` (timeout) or `parse_gga()` returns `None` (no fix), the TX loop still transmits a PositionFrame with the last valid position values. This ensures:
- The downlink keeps transmitting (1 Hz cadence maintained)
- The receiver can detect stale data by checking sequence numbers
- No "gap" in the telemetry stream

### In `test_gps.py` (Phase 1D Test)

The test script bypasses `NMEAParser` entirely and implements its own byte-level serial reading (lines 308–327). This is because the test needs:
- Capture all sentences (not just checksum-valid ones) for debugging
- Count sentence types for reporting
- Lower-level control over the read loop

The test script duplicates the checksum validation and parsing logic from `nmea.py` rather than importing it — this is intentional for Phase 1D (hardware validation), where the test itself validates that the parsing logic is correct by testing against real hardware output.

---

## 11. Error Handling & Robustness Summary

| Failure Mode                          | How `nmea.py` Handles It                                         |
|---------------------------------------|------------------------------------------------------------------|
| Serial device doesn't exist           | `serial.Serial()` raises `SerialException` → propagated to caller |
| No data on serial (timeout)           | `readline()` returns empty → `read_sentence()` returns `None`    |
| Garbage bytes on serial               | `decode("ascii", errors="ignore")` drops non-ASCII silently     |
| No `$` at start                       | `nmea_checksum_ok` returns `False` → sentence skipped           |
| No `*` (no checksum field)            | `split("*")` raises `ValueError` → caught, `False`              |
| Invalid hex in checksum               | `int(..., 16)` raises `ValueError` → caught, `False`            |
| Wrong checksum (corruption)           | `computed != expected` → `False` → sentence skipped             |
| Not a GGA/RMC sentence                | `endswith("GGA"/"RMC")` check fails → `None`                    |
| Empty critical fields (time, lat, lon)| `not utc_time or not lat_raw` guard → `None`                    |
| Non-numeric field values              | `_safe_float` returns `None` → field is `None` in dict           |
| Invalid coordinate format             | `_nmea_dm_to_dd` catches `ValueError`/`IndexError` → `None`     |
| Too few fields in sentence            | `len(fields) < N` guard → `None`                                 |

**Defensive philosophy:** The code is maximally permissive on input (accepts any byte stream) and maximally strict on output (only returns validated, parsed data). Invalid data is silently discarded — no logging, no exceptions. This is appropriate for the embedded/headless HAB context where there's no operator to see error messages, and the only correct response to bad data is "try again next cycle."

---

## 12. Design Observations & Tradeoffs

### Strengths

1. **Single-purpose, minimal dependencies.** Only `pyserial`. No threading, no asyncio, no external protocol libraries. This makes it trivially portable to any Python 3.7+ environment.

2. **Stateless functions.** `nmea_checksum_ok`, `_safe_float`, `_nmea_dm_to_dd`, `parse_gga`, and `parse_rmc` are all pure functions — given the same input, they always produce the same output. This makes them easy to test and reason about.

3. **Fail-closed checksum validation.** Corrupted data is silently discarded — never passed through. In the HAB context, transmitting wrong coordinates is far worse than transmitting none.

4. **Coordinate precision at 6 decimal places.** ~0.11 m resolution is well beyond the L76K's accuracy (~2.5 m CEP), so no information is lost.

5. **Context manager support.** `__enter__`/`__exit__` guarantee the serial port is closed, even on exceptions.

6. **Empty-field handling.** NMEA sentences with empty fields (common during no-fix conditions) are handled gracefully — fields become `None` rather than crashing.

### Tradeoffs & Considerations

1. **Blocking I/O.** `read_sentence()` blocks the calling thread for up to 1 second per iteration. In the TX loop, this is acceptable because the GNU Radio flowgraph runs on its own thread. However, if `read_sentence()` were called in a GUI event loop or a synchronous HTTP handler, it would freeze the UI/server. A future async version could use `asyncio` with `serial_asyncio`.

2. **No field reordering protection.** The parser assumes NMEA fields are in standard order. If a receiver outputs a non-standard GGA sentence with different field ordering (unlikely but possible with some firmware), the parser would silently misinterpret fields. The checksum would still validate, making this a hard-to-detect error.

3. **No talker-ID discrimination.** `endswith("GGA")` matches any talker prefix. While this makes the parser compatible with multi-GNSS receivers (L76K outputs GPGGA, GLGGA, GNGGA, BDGGA), it doesn't distinguish between constellations. If multiple GGA sentences arrive from different constellations for the same epoch, the parser processes all of them — the TX loop would update position multiple times per cycle, always using the last one.

4. **No GSA parsing.** The GSA sentence contains DOP values (PDOP, HDOP, VDOP) and active satellite PRNs. The TX pipeline's `PositionFrame` has a `vdop` field that is hardcoded to `0.0` (line 197 of `gps_packet_tx.py`) because GGA only has HDOP. Parsing GSA would provide VDOP.

5. **No GSV parsing.** GSV sentences contain satellite elevation/azimuth/SNR data — useful for antenna orientation debugging and predicting signal dropouts, but not needed for the position telemetry pipeline.

6. **The `_nmea_dm_to_dd` degree-length heuristic (lines 54–57).** The logic uses `len(int_part) <= 4` to decide between 2 or 3 degree digits. This works for all real-world coordinates but relies on the assumption that latitude never exceeds 99°59.9999' (5 integer digits). A latitude of 100+ degrees would be misparsed, but this is physically impossible on Earth.

7. **`round(decimal_degrees, 6)` may lose precision for longitude at high latitudes.** At 89°N, 0.000001° of longitude ≈ 0.002 m, so this is still negligible. But for astronomical or non-terrestrial use, consider higher precision.

8. **The class delegates to module-level functions.** `NMEAParser.parse_gga`, `.parse_rmc`, and `.checksum_valid` are static methods that call module-level functions. This creates two ways to do the same thing — the caller can import `parse_gga` directly or use `parser.parse_gga()`. The TX pipeline imports both (line 30 of `gps_packet_tx.py`), then uses the module-level `parse_gga` (line 163), not the static method. The test script doesn't import from `nmea.py` at all — it has its own duplicated parsing logic.

---

## Appendix: Complete NMEA Sentence Examples

### Valid GGA (with fix)
```
$GPGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
```
→ `parse_gga` returns:
```python
{
    "time": "123519.00",
    "lat": 48.1173,
    "lon": 11.516667,
    "fix_quality": 1,
    "altitude": 545.4,
    "satellites": 8,
    "hdop": 0.9,
}
```

### Valid GGA (no fix)
```
$GPGGA,000000.00,,,,,0,00,99.99,,,,,,*66
```
→ `parse_gga` returns `None` (line 91: `lat_raw` is empty).

### Valid RMC (with fix)
```
$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A
```
→ `parse_rmc` returns:
```python
{
    "time": "123519",
    "lat": 48.1173,
    "lon": 11.516667,
    "speed_knots": 22.4,
    "track_angle": 84.4,
    "date": "230394",
}
```

### Malformed (checksum mismatch)
```
$GPGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*00
```
→ Both `nmea_checksum_ok` and `parse_gga` reject this. The correct checksum is `*47`, not `*00`.

### Malformed (no `$`)
```
GPGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
```
→ `nmea_checksum_ok` returns `False` at line 19 (`payload.startswith("$")` fails).

### Malformed (binary garbage)
```
b'\xff\xfe\x00\x01GPGGA...'
```
→ `read_sentence()` decodes with `errors="ignore"` — non-ASCII bytes are dropped. If enough ASCII remains to form a valid sentence, it passes; otherwise, it's skipped.

---

*Generated: 2026-07-22 | File analyzed: payload/gps/nmea.py (180 lines, 4,941 bytes)*
