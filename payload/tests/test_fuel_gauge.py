#!/usr/bin/env python3
"""
Phase 1C: MAX17049 Fuel Gauge Test
===================================
Reads the MAX17049 fuel gauge IC on I2C bus 1, address 0x36.

Registers read (per PLAN.md §3.4):
  - VCELL   0x02: Battery voltage (raw * 78.125e-6 V)
  - SOC     0x04: State of charge  (raw / 256.0 %)
  - VERSION 0x08: IC version

Expected for LiPo:
  - VCELL: 3.0 – 4.2 V
  - SOC:   0 – 100%
  - VERSION: non-zero

Dependencies: smbus2 (pip install smbus2)
"""

import sys
import time
import struct


# ── Constants ────────────────────────────────────────────────────────────────

BUS = 1                # I2C bus 1 (pins 27 SDA, 28 SCL on Rock 2A)
ADDR = 0x36            # MAX17049 I2C address

REG_VCELL   = 0x02     # Battery voltage
REG_SOC     = 0x04     # State of charge
REG_VERSION = 0x08     # IC version

VCELL_SCALE = 78.125e-6   # V per LSB
SOC_SCALE   = 1.0 / 256.0  # % per LSB

# ── I2C helpers ──────────────────────────────────────────────────────────────

def read_i2c_word(bus, addr, register):
    """
    Read a 16-bit word (2 bytes) from an I2C device.
    MAX17049 uses MSB-first byte order.
    Returns the raw integer.
    """
    data = bus.read_i2c_block_data(addr, register, 2)
    # MSB at data[0], LSB at data[1]
    raw = (data[0] << 8) | data[1]
    return raw


def try_read(bus, addr, register, label):
    """
    Attempt to read a register and return (raw, error_string_or_None).
    If the device is not present or I2C fails, this catches the exception
    so the script can still report on other registers.
    """
    try:
        raw = read_i2c_word(bus, addr, register)
        return raw, None
    except OSError as exc:
        return None, f"[ERR] I2C read failed on {label}: {exc}"
    except Exception as exc:
        return None, f"[ERR] Unexpected error on {label}: {exc}"


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Import smbus2 here so the help/usage is accessible even without it
    try:
        from smbus2 import SMBus
    except ImportError:
        print("ERROR: smbus2 is not installed.")
        print("Install it with: pip install smbus2")
        sys.exit(1)

    print("=" * 52)
    print("  MAX17049 Fuel Gauge Test  (Phase 1C)")
    print("  I2C bus %d, address 0x%02X" % (BUS, ADDR))
    print("=" * 52)

    # Open the bus
    try:
        bus = SMBus(BUS)
    except FileNotFoundError:
        print(f"\nERROR: /dev/i2c-{BUS} not found.")
        print("Is the I2C kernel driver loaded? Try:  ls /dev/i2c-*")
        sys.exit(1)
    except PermissionError:
        print(f"\nERROR: Permission denied opening /dev/i2c-{BUS}.")
        print("Add your user to the i2c group or run with sudo.")
        sys.exit(1)

    errors = 0

    try:
        # ── Read VERSION first (quick hardware presence check) ────────────
        raw_ver, err = try_read(bus, ADDR, REG_VERSION, "VERSION")
        if err:
            print(f"\n{err}")
            print("Device may not be present or I2C bus may be down.")
            bus.close()
            sys.exit(2)

        print(f"\n  IC Version (raw):   0x{raw_ver:04X}  ({'OK' if raw_ver != 0 else '⚠ zero'})")

        # ── Read VCELL ────────────────────────────────────────────────────
        raw_vcell, err = try_read(bus, ADDR, REG_VCELL, "VCELL")
        if err:
            print(f"\n{err}")
            errors += 1
        else:
            voltage = raw_vcell * VCELL_SCALE
            status = "OK" if 3.0 <= voltage <= 4.2 else "⚠ out of range"
            print(f"  Battery Voltage:    {voltage:.3f} V  ({status})")

        # ── Read SOC ──────────────────────────────────────────────────────
        raw_soc, err = try_read(bus, ADDR, REG_SOC, "SOC")
        if err:
            print(f"\n{err}")
            errors += 1
        else:
            soc = raw_soc * SOC_SCALE
            status = "OK" if 0.0 <= soc <= 100.0 else "⚠ out of range"
            print(f"  State of Charge:    {soc:.1f} %  ({status})")

    finally:
        bus.close()

    # ── Summary ─────────────────────────────────────────────────────────
    print()
    print("-" * 52)
    if errors:
        print(f"  Result: PARTIAL — {errors} register(s) failed to read")
    else:
        print("  Result: PASS — all registers read successfully")
    print("-" * 52)

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
