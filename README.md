# HAB — High Altitude Balloon Project

## Overview

This project builds a high‑altitude balloon payload and matching ground station capable of:
- Capturing and transmitting onboard sensor data and imagery from the stratosphere
- Streaming a high‑bandwidth video downlink using DVB‑S2
- Sending a robust QPSK packet telemetry link for flight state (GPS, altitude, environment)

## System Architecture

### Balloon Payload
- Embedded Linux board (e.g., Orange Pi Zero 3)
- HackRF SDR as RF front end for transmission
- Cameras for video capture
- Weather and atmospheric sensors (see Sensor Suite)

### RF Links (two downlinks)
1. Video downlink: DVB‑S2
2. Telemetry downlink: QPSK packet telemetry (GPS, barometric altitude, temperature, etc.)

### Ground Station
- HackRF SDR receiver
- Custom GUI in `hab-gui/` to:
  - Demodulate DVB‑S2 video
  - Demodulate QPSK telemetry packets
  - Provide real‑time spectrum analysis and monitoring
  - Display and log telemetry

## Repository Structure

```
hab/
├── hab-gui/          # Ground station GUI (PySide6 + GNU Radio + SoapySDR)
├── hab-esp32/        # ESP32 + Zephyr RTOS firmware (sensors/control as needed)
├── rf-link/          # RF link utilities, GNU Radio graphs, tools
├── mechanical/       # Mechanical designs and enclosure files
├── photos/           # Project photos and documentation images
└── README.md         # This file
```

Refer to `hab-gui/README.md` for detailed ground‑station setup (GNU Radio, SoapySDR, HackRF) and run instructions.

## Current Status
- ✅ Ground station GUI scaffolding complete; HackRF integration in place
- 🚧 Bringing up GUI ground station to receive DVB‑S2 video and QPSK telemetry
- 📋 Next: Full telemetry pipeline and end‑to‑end flight test

## Sensor Suite (examples)

### Core sensors (essential)
- BME280/BME680 — Temperature, pressure, humidity (I2C)
- GPS module (u‑blox NEO‑M8N/M9N class) — Lat/Lon/Altitude, velocity (UART)

### Extended sensors (recommended)
- VEML6075 — UVA/UVB index (I2C)
- MQ131 (or electrochemical O3 sensor) — Ozone concentration (analog)
- PMS5003 — Particulate matter PM2.5/PM10 (UART)
- Geiger counter module — Cosmic radiation (pulse count)
- MAG3110 (or HMC5883L) — Magnetometer (I2C)
- MPU6050 (or ICM‑20948) — IMU 6‑9 DOF (I2C/SPI)

## Getting Started (Ground Station)
1. See `hab-gui/README.md` for system dependencies (Homebrew installs), venv setup, and running the app
2. Connect HackRF, configure frequency/sample rate/gains in the Connection tab
3. Start reception in the Telemetry tab; verify spectrum and packet flow

## References
- Orange Pi Zero 3 documentation (see PDFs in repo root)
- GNU Radio project and DVB‑S2 resources
- HackRF documentation (Great Scott Gadgets)
