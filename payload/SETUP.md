# Rock 2A Payload Setup Reference

> **SBC:** Radxa Rock 2A (RK3528A) · **OS:** Armbian Debian 13 (Trixie) Minimal CLI
> **Kernel:** 6.1.115-rockchip64 · **Hostname:** rock-2a · **User:** hab
> **IP:** 192.168.86.30 (DHCP) · **Last verified:** 2026-07-22

This document describes every hardware peripheral enabled on the Rock 2A for the HAB payload.
Follow this if you need to rebuild the SD card or replicate the setup on a new board.

---

## 1. Device Tree Overlays

All overlays live in `/boot/dtb/rockchip/overlay/` and are enabled via `overlays=` in `/boot/armbianEnv.txt`.

### Active overlays (loaded at boot)

| Overlay | Purpose | Pins freed/enabled |
|---|---|---|
| `rk3528-disable-pwm10` | Disable PWM on GPIO4_C4 (conflicts with I2C0 SCL) | Frees pin 5 for I2C0 |
| `rk3528-disable-fiq` | Disable FIQ debugger (claims UART pins) | Frees pins 8/10 for UART0 |
| `rk3528-uart0-m0` | Enable UART0 on pins 8 (TX) / 10 (RX) | `/dev/ttyS0` at 1.5 Mbps base |
| `rk3528-i2c0-m0` | Enable I2C bus 0 on pins 3 (SDA) / 5 (SCL) | `/dev/i2c-0` |
| `rk3528-i2c1-m0` | Enable I2C bus 1 on pins 27 (SDA) / 28 (SCL) | `/dev/i2c-1` |

### `/boot/armbianEnv.txt` (relevant lines)

```
overlays=rk3528-disable-pwm10 rk3528-disable-fiq rk3528-uart0-m0 rk3528-i2c0-m0 rk3528-i2c1-m0
extraargs=fiq_debugger.disable
```

**Note:** `rk3528-uart2-m0` is NOT enabled. UART2 was initially tried but the FIQ debugger binds to the same pins as UART0 and UART2 can't claim them. UART0 M0 is used instead — it maps to the same physical pins (8/10).

### Overlay source files

Source DTS files used to compile these overlays (for reference/recreation):

#### `rk3528-disable-fiq.dts`
```dts
/dts-v1/;
/ {
    fragment@0 {
        target-path = "/fiq-debugger";
        __overlay__ {
            status = "disabled";
        };
    };
};
```

#### `rk3528-disable-pwm10.dts`
```dts
/dts-v1/;
/ {
    fragment@0 {
        target-path = "/pwm@ffa90010";
        __overlay__ {
            status = "disabled";
        };
    };
};
```

#### `rk3528-uart0-m0.dts`
```dts
/dts-v1/;
/ {
    fragment@0 {
        target = <&uart0>;
        __overlay__ {
            status = "okay";
            pinctrl-names = "default";
            pinctrl-0 = <&uart0m0_xfer>;
        };
    };
};
```

#### `rk3528-i2c0-m0.dts`
```dts
/dts-v1/;
/ {
    fragment@0 {
        target = <&i2c0>;
        __overlay__ {
            status = "okay";
            pinctrl-0 = <&i2c0m0_xfer>;
        };
    };
};
```

#### `rk3528-i2c1-m0.dts`
```dts
/dts-v1/;
/ {
    fragment@0 {
        target = <&i2c1>;
        __overlay__ {
            status = "okay";
            pinctrl-0 = <&i2c1m0_xfer>;
        };
    };
};
```

Compile each with:
```bash
dtc -I dts -O dtb -o /boot/dtb/rockchip/overlay/rk3528-<name>.dtbo rk3528-<name>.dts
```

---

## 2. Peripheral Pin Mapping

### 2.1 I2C Bus 0 — Environmental Sensors

| Header Pin | Rockchip GPIO | Function | Device | Address | Status |
|---|---|---|---|---|---|
| 3 | GPIO4_C3 | SDA0 | TMP100, LIS2DH, LPS25HB | — | ⚠️ Sensors broken |
| 5 | GPIO4_C4 | SCL0 | — | — | — |
| — | — | — | TMP100 | 0x48 | ⚠️ Not ACKing |
| — | — | — | LIS2DH | 0x19 | ⚠️ Not ACKing |
| — | — | — | LPS25HB | 0x5D | ⚠️ Not ACKing |

**Status:** I2C bus 0 shows all addresses responding (bus float). Sensors are physically broken — confirmed by user. Drivers written but untestable until sensors are replaced.

### 2.2 I2C Bus 1 — Fuel Gauge

| Header Pin | Rockchip GPIO | Function | Device | Address | Status |
|---|---|---|---|---|---|
| 27 | GPIO4_A2 | SDA1 | MAX17049 | 0x36 | ✅ WORKING |
| 28 | GPIO4_A3 | SCL1 | — | — | ✅ |

**Verified:** `i2cdetect -y 1` shows 0x36. Test script reads VCELL, SOC, VERSION successfully.

### 2.3 UART0 — GPS (L76K)

| Header Pin | Rockchip GPIO | Function | Direction | Status |
|---|---|---|---|---|
| 8 | GPIO0_B1 | UART0 TX (SBC → GPS) | Output | ✅ |
| 10 | GPIO0_B0 | UART0 RX (GPS → SBC) | Input | ✅ |

**Device:** `/dev/ttyS0` at 9600 baud, 8N1
**GPS Module:** Quectel L76K (inside Seeed XIAO GPS board)
**Antenna:** Active GPS patch antenna, powered by VDD_RF on module (no external bias-T)

**WARNING:** The FIQ debugger (`fiq-debugger`) is a kernel debugging feature that claims UART0 pins at boot. Without `fiq_debugger.disable` in the kernel command line, `/dev/ttyS0` receives nothing. This was the #1 cause of GPS silence during bringup. The `rk3528-disable-fiq` overlay + `extraargs=fiq_debugger.disable` handle this.

**Also disabled:** `serial-getty@ttyS0`, `serial-getty@ttyS2`, `serial-getty@ttyFIQ0` — any getty on the GPS UART will consume NMEA data.

### 2.4 GPIO Control Lines — GPS

| Header Pin | gpiochip | Line | GPIO Name | Signal | Active | Status |
|---|---|---|---|---|---|---|
| 33 | gpiochip1 | 9 | GPIO1_B1 | GPS_WAKE | HIGH = enabled | ✅ Verified |
| 35 | gpiochip1 | 14 | GPIO1_B6 | GPS_RST_N | HIGH = not reset | ✅ Verified (probed) |

Both pins must be driven HIGH for GPS operation:
```bash
sudo gpioset -t0 -c gpiochip1 9=1 14=1
```

### 2.5 GPIO Control Lines — Heater + PA (Power Amplifier)

| Header Pin | gpiochip | Line | GPIO Name | Signal | Active | Status |
|---|---|---|---|---|---|---|
| 16 | gpiochip1 | 7 | GPIO1_A7 | 5V_PA_EN | LOW | Off |
| 18 | gpiochip1 | 9 | GPIO1_B1 | 5V_HEATER_EN | LOW | Off |

Both are active-LOW (LOW = off). Verified by probing.

### 2.6 GPIO — LEDs (on devboard)

| Header Pin | gpiochip | Line | GPIO Name | Active |
|---|---|---|---|---|
| 36 | gpiochip1 | 12 | GPIO1_B4 | HIGH = on |
| 38 | gpiochip1 | 15 | GPIO1_B7 | HIGH = on |
| 40 | gpiochip1 | 16 | GPIO1_C0 | HIGH = on |

---

## 3. udev Rules

### `/etc/udev/rules.d/99-i2c.rules`
```
SUBSYSTEM=="i2c-dev", GROUP="i2c", MODE="0660"
```

### `/etc/udev/rules.d/99-tty.rules`
```
KERNEL=="ttyS*", GROUP="dialout", MODE="0660"
```

### Group memberships for user `hab`
```bash
sudo usermod -aG i2c,dialout,video hab
```

---

## 4. sudo Configuration

### `/etc/sudoers.d/hab`
```
hab ALL=(ALL:ALL) NOPASSWD: ALL
```

---

## 5. Python Environment

All Python code lives in `/home/hab/payload/`.

**Dependencies** (installed via `pip install`):
```
smbus2      # I2C on Linux (/dev/i2c-N)
pyserial    # UART for GPS
```

No virtual environment — installed system-wide since this is a single-purpose payload SBC.

---

## 6. GPS (Quectel L76K) — Detailed Notes

### 6.1 The FIQ Debugger Problem

This was the single hardest bug to diagnose during bringup:

1. `rk3528-uart2-m0.dtbo` was loaded to enable UART2 on pins 8/10
2. `i2cdetect` on the GPS pins showed UART traffic (probed by user)
3. But `/dev/ttyS2` returned zero bytes — even with GPS powered and RST_N high
4. Root cause: `agetty` was consuming data on `/dev/ttyS2` — disabled via systemd
5. Still zero bytes — second root cause: the FIQ debugger kernel feature claims the UART0 pins (which overlap with UART2 M0 on pins 8/10) at boot, *before the DT overlay activates*
6. The debugger creates `/dev/ttyFIQ0` and silently consumes all NMEA data
7. **Fix:** Disable FIQ debugger in kernel cmdline + switch to UART0 M0 (not UART2)

### 6.2 GPS Bringup Sequence

```bash
# 1. Set control pins
sudo pkill gpioset  # kill any stale daemon
sudo gpioset -t0 -c gpiochip1 9=1 14=1   # WAKE HIGH, RST_N HIGH

# 2. Verify pinmux
cat /sys/kernel/debug/pinctrl/pinctrl-rockchip-pinctrl/pinmux-pins | grep -E "gpio0-[01]"

# 3. Read GPS
python3 -c "import serial; s=serial.Serial('/dev/ttyS0',9600,timeout=1); print(s.readline()); s.close()"
```

### 6.3 GPS Features Not Yet Configured

The L76K has several features accessible via PMTK/PCAS commands that are not yet utilized:

- **EASY™** — Self-generated ephemeris prediction. Fast reacquisition after signal loss (critical for balloon tumbles). Enable via `$PMTK869,1*29`
- **LOCUS™** — Internal 16,000-waypoint logger. Autonomous black-box flight recorder. Configure via `$PMTK185`
- **Update rate > 1 Hz** — Up to 10 Hz. Configure via `$PMTK220,<interval_ms>`
- **AIC** — Active Interference Cancellation for in-band jammers. Enable via `$PMTK886,1`

PMTK commands have not yet been confirmed working on this module — initial send attempts got no response. May need correct checksum verification or the module may be in a broadcast-only mode.

---

## 7. Test Results

### Phase 1 Test Status (as of 2026-07-22)

| Test | File | Status | Notes |
|---|---|---|---|
| 1A — I2C Scan | `test_i2c_scan.py` | ⚠️ Partial | Bus 1 shows MAX17049 @ 0x36. Bus 0 shows all float (sensors broken) |
| 1B — Sensors | `test_sensors.py` | ❌ Blocked | Sensors broken on I2C bus 0 — cannot test |
| 1C — Fuel Gauge | `test_fuel_gauge.py` | ✅ PASS | VCELL, SOC, VERSION all read correctly |
| 1D — GPS | `test_gps.py` | ✅ PASS | 180 lines/15s, 179 valid NMEA, 8 sats, 3D fix, antenna OK |
| 1E — Camera | `test_camera.py` | ⏳ Not run | No USB camera connected yet |

### GPS Test Output (2026-07-22)
```
Phase 1D — GPS NMEA Test
  Opened /dev/ttyS0 at 9600 baud 8N1
  Captured 180 lines in 15s
  9 NMEA sentence types detected
  Fix Quality: 1 — GPS Fix (SPS)
  Satellites: 8
  Position: 37°45.194'N 122°23.581'W
  Altitude: 35.4 m
  Speed: 0.93 knots
  Date: 22/07/2026
  Antenna: OK
```

---

## 8. Boot-Time Automation (TODO)

The following should run at boot for full autonomy:
1. Assert GPS_WAKE and GPS_RST_N HIGH (gpioset daemon)
2. Optionally: configure GPS update rate / EASY / LOCUS via PMTK
3. Start payload main.py as a systemd service

Not yet implemented — GPS control pins currently set manually via SSH.
