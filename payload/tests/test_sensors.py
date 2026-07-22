#!/usr/bin/env python3
"""
Phase 1B: I2C Sensor Readback Test

Independently tests each environmental sensor on I2C Bus 0:
  - TMP100  (0x48): temperature
  - LIS2DH  (0x19): 3-axis accelerometer
  - LPS25HB (0x5D): pressure + temperature

Usage:
  python3 test_sensors.py all           # test every sensor on the bus
  python3 test_sensors.py tmp100         # test only the TMP100
  python3 test_sensors.py lis2dh         # test only the LIS2DH
  python3 test_sensors.py lps25hb        # test only the LPS25HB

Each sensor is tested independently — failure of one does not block others.
Register maps and conversion formulas are from PLAN.md section 3.
"""

import sys

try:
    from smbus2 import SMBus, SMBusError
except ImportError:
    print("ERROR: smbus2 is not installed. Run: pip install smbus2")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Sensor addresses on I2C Bus 0
# ---------------------------------------------------------------------------

I2C_BUS = 0

SENSORS = {
    "tmp100":   0x48,
    "lis2dh":   0x19,
    "lps25hb":  0x5D,
}


# ---------------------------------------------------------------------------
# TMP100  —  Temperature Sensor  (I2C 0x48)
# ---------------------------------------------------------------------------
#
# Register  | Address | Size   | Description
# Temp      | 0x00    | 2 bytes | 12-bit, MSB first. °C = raw × 0.0625
#
# The lower 4 bits of the 16-bit read are zero (12-bit sensor); shift right
# by 4 before converting.

def test_tmp100(bus):
    """Read the TMP100 temperature register.

    Returns (ok: bool, data: float | None, error: str | None).
    """
    addr = 0x48
    try:
        raw_bytes = bus.read_i2c_block_data(addr, 0x00, 2)
        raw = (raw_bytes[0] << 8) | raw_bytes[1]        # MSB first
        raw_12bit = raw >> 4                              # discard 4 zero LSBs
        temp_c = raw_12bit * 0.0625
        return True, temp_c, None
    except (SMBusError, OSError) as exc:
        return False, None, str(exc)


# ---------------------------------------------------------------------------
# LIS2DH  —  3-Axis Accelerometer  (I2C 0x19)
# ---------------------------------------------------------------------------
#
# Register    | Address | Size   | Description
# WHO_AM_I    | 0x0F    | 1 byte | Identity: expect 0x33
# CTRL_REG1   | 0x20    | 1 byte | Set to 0x47 (ODR=50 Hz, ±2g, all axes on)
# OUT_X_L     | 0x28    | 1 byte | X-axis low byte
# OUT_X_H     | 0x29    | 1 byte | X-axis high byte
# OUT_Y_L     | 0x2A    | 1 byte |
# OUT_Y_H     | 0x2B    | 1 byte |
# OUT_Z_L     | 0x2C    | 1 byte |
# OUT_Z_H     | 0x2D    | 1 byte |
#
# Axes are signed 10-bit, left-justified in a 16-bit word.
# Conversion: right-shift raw 16-bit by 6 to get the 10-bit signed value,
# then multiply by 4 mg/LSB to get milli-g.

def _lis2dh_decode_axis(high_byte, low_byte):
    """Decode one LIS2DH axis from its two register bytes.

    Returns the signed acceleration value in milli-g (mg).
    """
    raw = (high_byte << 8) | low_byte
    # Sign-extend from bit 15
    if raw & 0x8000:
        raw -= 0x10000
    # Left-justified 10-bit → right-justify
    value_10bit = raw >> 6
    return value_10bit * 4  # mg per LSB


def test_lis2dh(bus):
    """Identify, configure, and read the LIS2DH accelerometer.

    Returns (ok: bool, data: dict | None, error: str | None).
    """
    addr = 0x19
    try:
        # --- WHO_AM_I ---
        whoami = bus.read_byte_data(addr, 0x0F)
        if whoami != 0x33:
            return (
                False,
                None,
                f"WHO_AM_I mismatch: read 0x{whoami:02X}, expected 0x33",
            )

        # --- Configure ---
        # 0x47 = 0b01000111
        #   ODR[3:0]=0111 → 50 Hz (normal / low-power mode)
        #   LPen=0       → normal mode
        #   Zen=1, Yen=1, Xen=1 → all axes enabled
        bus.write_byte_data(addr, 0x20, 0x47)

        # --- Read acceleration data (6 bytes from 0x28) ---
        data = bus.read_i2c_block_data(addr, 0x28, 6)
        # data = [OUT_X_L, OUT_X_H, OUT_Y_L, OUT_Y_H, OUT_Z_L, OUT_Z_H]

        x_mg = _lis2dh_decode_axis(data[1], data[0])
        y_mg = _lis2dh_decode_axis(data[3], data[2])
        z_mg = _lis2dh_decode_axis(data[5], data[4])

        return True, {
            "whoami": whoami,
            "x_mg": x_mg,
            "y_mg": y_mg,
            "z_mg": z_mg,
        }, None
    except (SMBusError, OSError) as exc:
        return False, None, str(exc)


# ---------------------------------------------------------------------------
# LPS25HB  —  Pressure & Temperature Sensor  (I2C 0x5D)
# ---------------------------------------------------------------------------
#
# Register       | Address | Size    | Description
# WHO_AM_I       | 0x0F    | 1 byte  | Identity: expect 0xBD
# CTRL_REG1      | 0x20    | 1 byte  | Set to 0xC0 (ODR=25 Hz, BDU=1)
# PRESS_OUT_XL   | 0x28    | 1 byte  | Pressure LSB
# PRESS_OUT_L    | 0x29    | 1 byte  | Pressure mid-byte
# PRESS_OUT_H    | 0x2A    | 1 byte  | Pressure MSB
# TEMP_OUT_L     | 0x2B    | 1 byte  | Temperature LSB
# TEMP_OUT_H     | 0x2C    | 1 byte  | Temperature MSB
#
# Pressure: 24-bit unsigned.  hPa = raw / 4096
# Temperature: 16-bit signed, 2's complement.  °C = 42.5 + raw / 480

def test_lps25hb(bus):
    """Identify, configure, and read the LPS25HB barometer.

    Returns (ok: bool, data: dict | None, error: str | None).
    """
    addr = 0x5D
    try:
        # --- WHO_AM_I ---
        whoami = bus.read_byte_data(addr, 0x0F)
        if whoami != 0xBD:
            return (
                False,
                None,
                f"WHO_AM_I mismatch: read 0x{whoami:02X}, expected 0xBD",
            )

        # --- Configure ---
        # 0xC0 = 0b11000000
        #   ODR[2:0]=000 → one-shot (we'll set 25 Hz below)
        #   Actually per datasheet, for 25 Hz: PD=1, ODR2-ODR0=100
        #   The PLAN says CTRL_REG1 = 0xC0, which is PD=1, ODR=100 (25 Hz),
        #   BDU=0.  Let's also set BDU (block data update) for consistency:
        #   0xC4 = 0b11000100 (PD=1, ODR=25Hz, BDU=1)
        #   But PLAN.md says 0xC0 exactly, so we follow the spec:
        bus.write_byte_data(addr, 0x20, 0xC0)

        # --- Pressure (3 bytes, 24-bit little-endian) ---
        press_data = bus.read_i2c_block_data(addr, 0x28, 3)
        # press_data = [PRESS_OUT_XL, PRESS_OUT_L, PRESS_OUT_H]
        press_raw = (
            (press_data[2] << 16) | (press_data[1] << 8) | press_data[0]
        )
        pressure_hpa = press_raw / 4096.0

        # --- Temperature (2 bytes, 16-bit signed little-endian) ---
        temp_data = bus.read_i2c_block_data(addr, 0x2B, 2)
        # temp_data = [TEMP_OUT_L, TEMP_OUT_H]
        temp_raw = (temp_data[1] << 8) | temp_data[0]
        # Sign-extend 16-bit 2's complement
        if temp_raw & 0x8000:
            temp_raw -= 0x10000
        temp_c = 42.5 + temp_raw / 480.0

        return True, {
            "whoami": whoami,
            "pressure_hpa": pressure_hpa,
            "temp_c": temp_c,
        }, None
    except (SMBusError, OSError) as exc:
        return False, None, str(exc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _fmt_header(label):
    """Format a section header for console output."""
    return f"\n{'=' * 60}\n  {label}\n{'=' * 60}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_sensors.py [all|tmp100|lis2dh|lps25hb]")
        sys.exit(1)

    target = sys.argv[1].lower()
    valid = ["all", "tmp100", "lis2dh", "lps25hb"]

    if target not in valid:
        print(
            f"Invalid argument '{target}'. "
            f"Valid choices: {', '.join(valid)}"
        )
        sys.exit(1)

    # Determine which sensors to test
    to_test = list(SENSORS.keys()) if target == "all" else [target]

    # Open the bus
    try:
        bus = SMBus(I2C_BUS)
    except (SMBusError, OSError) as exc:
        print(f"FATAL: Cannot open /dev/i2c-{I2C_BUS}: {exc}")
        print(
            "  Is i2c-dev loaded? Try: sudo modprobe i2c-dev && "
            "ls /dev/i2c-*"
        )
        sys.exit(1)

    print(f"Phase 1B — I2C Sensor Readback  (Bus {I2C_BUS})")
    print(f"Sensors to test: {', '.join(to_test)}")

    # Registry of test functions
    tests = {
        "tmp100":   test_tmp100,
        "lis2dh":   test_lis2dh,
        "lps25hb":  test_lps25hb,
    }

    results = {}   # name → True (pass) / False (fail)

    for name in to_test:
        addr = SENSORS[name]
        print(_fmt_header(f"{name.upper()}  @  0x{addr:02X}"))

        ok, data, err_msg = tests[name](bus)
        results[name] = ok

        if not ok:
            print(f"  ❌  FAIL  —  {err_msg}")
            continue

        # --- Pretty-print decoded values ---
        if name == "tmp100":
            print(f"  Temperature   {data:7.2f} °C")

        elif name == "lis2dh":
            print(f"  WHO_AM_I      0x{data['whoami']:02X}  ✓")
            print(f"  X             {data['x_mg']:+6d} mg")
            print(f"  Y             {data['y_mg']:+6d} mg")
            print(f"  Z             {data['z_mg']:+6d} mg")

        elif name == "lps25hb":
            print(f"  WHO_AM_I      0x{data['whoami']:02X}  ✓")
            print(f"  Pressure      {data['pressure_hpa']:7.2f} hPa")
            print(f"  Temperature   {data['temp_c']:7.2f} °C")

        print("  ✅  PASS")

    bus.close()

    # --- Final summary ---
    passed = sum(1 for v in results.values() if v)
    failed = len(results) - passed
    print(_fmt_header("RESULTS"))
    print(f"  {passed} passed, {failed} failed")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
