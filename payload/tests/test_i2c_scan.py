#!/usr/bin/env python3
"""
Phase 1A: I2C Bus Scan
=======================
Scans /dev/i2c-0 and /dev/i2c-1, prints all detected I2C addresses in a summary table.

Expected devices:
  Bus 0 (env sensors): 0x19 (LIS2DH), 0x48 (TMP100), 0x5D (LPS25HB)
  Bus 1 (fuel gauge):  0x36 (MAX17049)

Target: Radxa Rock 2A running Armbian Debian 13 (Trixie) Minimal CLI.
Uses smbus2 — the pure-Python I2C library backed by /dev/i2c-N.

Author: Hermes Agent (2026-07-20)
"""

import sys
import os
from typing import List, Tuple

try:
    from smbus2 import SMBus
except ImportError:
    print(
        "ERROR: smbus2 is not installed.\n"
        "Install it with: pip install smbus2"
    )
    sys.exit(1)


# ── expected devices (bus → {address: label}) ──────────────────────────
EXPECTED: dict = {
    0: {
        0x19: "LIS2DH (accel)",
        0x48: "TMP100 (temp)",
        0x5D: "LPS25HB (pressure)",
    },
    1: {
        0x36: "MAX17049 (fuel gauge)",
    },
}

# I2C scan range — the standard safe range for 7-bit addresses.
SCAN_START: int = 0x03
SCAN_END: int = 0x77


# ── helpers ────────────────────────────────────────────────────────────

def scan_bus(device: str, bus_num: int) -> List[Tuple[int, str]]:
    """Scan a single I2C bus and return any addresses that ACK.

    Returns:
        List of (address, label) tuples.  The label is the expected device
        name, or '' for unexpected devices.
    """
    if not os.path.exists(device):
        print(
            f"\n⚠  {device} does not exist — is the I2C kernel driver loaded?\n"
            f"   Try:  sudo modprobe i2c-dev\n"
            f"         ls -l /dev/i2c-*\n"
        )
        return []

    try:
        bus = SMBus(bus_num)
    except PermissionError:
        print(
            f"\n⚠  Permission denied opening {device}.\n"
            "   Run with:  sudo python3 tests/test_i2c_scan.py\n"
        )
        return []
    except OSError as exc:
        print(
            f"\n⚠  Could not open {device}: {exc}\n"
            "   Check that the I2C controller is enabled in the device tree.\n"
        )
        return []

    found: List[Tuple[int, str]] = []
    with bus:
        for addr in range(SCAN_START, SCAN_END + 1):
            try:
                # Quick-ping: send a dummy byte; ACK → device present.
                bus.read_byte(addr)
                label = EXPECTED.get(bus_num, {}).get(addr, "")
                found.append((addr, label))
            except OSError:
                # NACK — no device at this address; expected.
                pass

    return found


def print_summary_table(
    bus_results: List[Tuple[int, List[Tuple[int, str]]]],
    all_ok: bool,
) -> None:
    """Print a clean ASCII summary table with pass/fail annotations."""
    exp = EXPECTED

    print()
    print("┌──────────────────────────────────────────────────────────┐")
    print("│           I2C BUS SCAN — SUMMARY TABLE                   │")
    print("├──────────────────────────────────────────────────────────┤")
    print("│  Bus  │ Address  │ Label                  │ Status       │")
    print("├──────────────────────────────────────────────────────────┤")

    for bus_num, found in bus_results:
        found_addrs = {addr for addr, _ in found}

        # Print detected devices first.
        for addr, label in sorted(found, key=lambda x: x[0]):
            if label:
                status = "✅ found"
            else:
                status = "⚠  unexpected"

            print(
                f"│  i2c-{bus_num} │  0x{addr:02X}   │ {label:<23s} │ {status:<13s} │"
            )

        # Print missed (expected but not found) devices.
        missed = set(exp.get(bus_num, {}).keys()) - found_addrs
        for addr in sorted(missed):
            label = exp[bus_num][addr]
            print(
                f"│  i2c-{bus_num} │  0x{addr:02X}   │ {label:<23s} │ ❌ MISSING     │"
            )

    print("├──────────────────────────────────────────────────────────┤")

    # Footer summary line.
    total_found = sum(len(found) for _, found in bus_results)
    total_expected = sum(len(exp[b]) for b in exp)
    total_missed = 0
    for bus_num, found in bus_results:
        found_addrs = {addr for addr, _ in found}
        total_missed += len(set(exp.get(bus_num, {}).keys()) - found_addrs)

    print(
        f"│  Found: {total_found}  │ Expected: {total_expected}  │ Missed: {total_missed}  │ "
        + ("ALL OK ✅      │" if all_ok else "FAILED ❌      │")
    )
    print("└──────────────────────────────────────────────────────────┘")
    print()


# ── main ───────────────────────────────────────────────────────────────

def main() -> int:
    buses_to_scan = [
        (0, "/dev/i2c-0"),
        (1, "/dev/i2c-1"),
    ]

    bus_results: List[Tuple[int, List[Tuple[int, str]]]] = []
    all_ok = True

    for bus_num, device in buses_to_scan:
        print(f"Scanning {device} (bus {bus_num}) [0x{SCAN_START:02X}–0x{SCAN_END:02X}] … ", end="")
        sys.stdout.flush()

        found = scan_bus(device, bus_num)
        bus_results.append((bus_num, found))

        if not found:
            print("no devices detected.")
        else:
            names = ", ".join(
                f"0x{a:02X}" + (f" ({lbl})" if lbl else "")
                for a, lbl in sorted(found, key=lambda x: x[0])
            )
            print(f"{len(found)} device(s): {names}")

        # Check against expected.
        found_addrs = {addr for addr, _ in found}
        missed = set(EXPECTED.get(bus_num, {}).keys()) - found_addrs
        if missed:
            all_ok = False
            missed_labels = ", ".join(
                f"0x{a:02X} ({EXPECTED[bus_num][a]})" for a in sorted(missed)
            )
            print(f"   ⚠  MISSING: {missed_labels}")

    print_summary_table(bus_results, all_ok)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
