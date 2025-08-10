# HAB GUI

A simple PySide6 desktop app for a High Altitude Balloon ground station.

- Dark theme (Fusion dark palette), modern feel
- Two tabs:
  - Telemetry (placeholder)
  - Bluetooth (scan, connect, read/notify and save data)

## Setup

It's recommended to use a Python virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### OS-specific notes
- macOS: `bleak` uses CoreBluetooth. The first time you scan or connect, macOS will ask for Bluetooth permissions for Python. If it does not, open System Settings → Privacy & Security → Bluetooth and ensure your Python interpreter has access. If needed, `pyobjc` is included in requirements.
- Linux: Install BlueZ and development headers before `pip install`:
  - Debian/Ubuntu: `sudo apt-get install bluetooth bluez bluez-tools libbluetooth-dev libglib2.0-dev`
  - Then run the `pip install` command above.
- Windows: No extra system packages typically required.

## Run

```bash
python main.py
```

## Using the Bluetooth tab

1. Click "Scan" to search for nearby BLE devices (5 seconds). Select your device.
2. Click "Connect" to connect to the selected device.
3. To download data:
   - Enter the characteristic UUID that your payload exposes for data.
   - Option A: Click "Read Once → Save" to read a single value and save it to a file.
   - Option B: Click "Start Notifications → Append" to subscribe to notifications and append all incoming chunks to the chosen file. Click "Stop Notifications" when finished.
4. Use "Disconnect" to end the session.

Saved files default to your `~/Downloads` directory unless you specify a path via the "Browse…" button.

## Next steps
- Implement live telemetry and graphs (e.g., using PyQtGraph or Matplotlib with QtAgg backend).
- Define a stable BLE data characteristic on the payload for bulk transfer and progress reporting.
- Add auto-reconnect and device filtering by name/UUID.
