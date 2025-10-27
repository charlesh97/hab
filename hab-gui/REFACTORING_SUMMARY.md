# HAB Ground Station Refactoring Summary

## Overview
The HAB Ground Station GUI has been successfully refactored to split the code into separate modules and replace the Bluetooth functionality with HackRF RF link support.

## Changes Made

### 1. File Structure
The monolithic `main.py` has been split into modular components:

```
hab-gui/
├── main.py                  # Main application entry point
├── telemetry_tab.py         # Telemetry display tab
├── connection_tab.py        # HackRF connection tab (replaces BLE)
├── telemetry_rx.py          # GNU Radio telemetry receiver
└── requirements.txt         # Updated dependencies
```

### 2. Tab Changes

#### **Telemetry Tab** (`telemetry_tab.py`)
- Created dedicated terminal display at the bottom
- Added Start/Stop RX buttons
- Added Export CSV button (placeholder for future implementation)
- Integrated with `telemetry_rx.py` for receiving telemetry data
- Includes `packet_processing()` function (currently returns hex string)

**Features:**
- Timestamped telemetry display
- Callback-based data reception
- Ready for custom packet parsing

#### **Connection Tab** (`connection_tab.py`)
- Replaced Bluetooth functionality with HackRF USB connection
- Uses SoapySDR library for device communication
- Tab renamed from "Bluetooth" to "Connection"

**Features:**
- **Device Discovery:** Refresh button to scan for HackRF devices over USB
- **Device Connection:** Connect/Disconnect to selected HackRF
- **Connection Parameters:**
  - Frequency (MHz)
  - LO ppm correction
  - Sample Rate (Msps)
  - LNA Gain slider (0-40 dB)
  - VGA Gain slider (0-62 dB)
- **Apply Parameters:** Button to apply settings to connected device
- Connection log for status messages

### 3. Telemetry Receiver (`telemetry_rx.py`)

Created GNU Radio-based telemetry receiver with:
- `TelemetryReceiver` class (GNU Radio top block)
- `TelemetryReceiverInterface` wrapper for GUI integration
- Placeholder structure for GNU Radio blocks
- Threading support for async message handling
- Callback mechanism for received packets

**Status:** ⚠️ **Requires GNU Radio Blocks**

The file has placeholder comments showing where to add your GNU Radio blocks:

```python
# TODO: Add your GNU Radio blocks here
# Example:
# self.source = soapy.source(...)
# self.demodulator = digital.fsk_demod(...)
# self.decoder = digital.packet_decoder(...)
```

### 4. Dependencies Updated

**Removed:**
- `bleak` (Bluetooth library)
- `qasync` (async Qt support)
- `pyobjc` (macOS Bluetooth support)

**Added:**
- `SoapySDR` - SDR device interface
- `gnuradio` - Signal processing framework
- `numpy` - Numerical computing (required by GNU Radio)

### 5. Main Application (`main.py`)

**Simplified:**
- Removed async event loop (no longer needed without BLE)
- Import tabs from separate modules
- Cleaner, more maintainable code

---

## Next Steps

### 1. Install Dependencies

```bash
cd /Users/charleshood/Documents/Github/hab/hab-gui
pip install -r requirements.txt
```

**Note:** GNU Radio and SoapySDR may require system-level installation:

```bash
# macOS with Homebrew
brew install gnuradio soapysdr soapyhackrf

# Then install Python bindings
pip install gnuradio SoapySDR
```

### 2. Add GNU Radio Blocks to `telemetry_rx.py`

You mentioned you'll provide GNU Radio blocks exported from GNU Radio Companion. Add them to the `TelemetryReceiver.__init__()` method in `telemetry_rx.py`.

**Example structure:**
```python
from gnuradio import blocks, digital, filter
import soapy

def __init__(self, callback_func):
    # ... existing code ...
    
    # Add your blocks
    self.source = soapy.source(...)
    self.lpf = filter.fir_filter_ccf(...)
    self.demod = digital.fsk_demod(...)
    self.decoder = digital.packet_decoder(...)
    
    # Connect the flowgraph
    self.connect((self.source, 0), (self.lpf, 0))
    self.connect((self.lpf, 0), (self.demod, 0))
    self.connect((self.demod, 0), (self.decoder, 0))
    
    # Connect message output to callback
    self.msg_connect((self.decoder, 'out'), (self, 'telemetry'))
```

### 3. Implement Packet Processing

Update the `packet_processing()` function in `telemetry_rx.py` to parse your telemetry format:

```python
def packet_processing(data: bytes) -> str:
    """
    Process received telemetry packet
    """
    # Example: Parse a simple telemetry format
    # Adjust based on your actual packet structure
    try:
        # Unpack your telemetry data
        # altitude = struct.unpack('f', data[0:4])[0]
        # temperature = struct.unpack('f', data[4:8])[0]
        # return f"Alt: {altitude}m, Temp: {temperature}°C"
        
        return f"Packet ({len(data)} bytes): {data.hex()}"
    except Exception as e:
        return f"Parse error: {e}"
```

### 4. Connect HackRF Parameters to Telemetry Receiver

Optionally, you can link the Connection tab parameters to the telemetry receiver. In `connection_tab.py`, add a reference to the telemetry tab:

```python
def apply_params_clicked(self) -> None:
    # ... existing code to apply to device ...
    
    # Also update telemetry receiver if running
    params = self.get_connection_params()
    # Pass to telemetry tab's receiver
    # self.parent().telemetry_tab.telemetry_rx.update_parameters(**params)
```

### 5. Test the Application

```bash
python main.py
```

**Test Workflow:**
1. Connect HackRF in Connection tab
2. Set frequency and gain parameters
3. Click "Apply Parameters"
4. Switch to Telemetry tab
5. Click "Start RX"
6. Verify telemetry appears in terminal

---

## Architecture Notes

### Flow of Telemetry Data

```
HackRF Device
    ↓ (USB)
SoapySDR
    ↓
GNU Radio Flowgraph (telemetry_rx.py)
    ↓
TelemetryReceiverInterface.callback
    ↓
TelemetryTab.on_telemetry_received()
    ↓
packet_processing()
    ↓
TelemetryTab.terminal (display)
```

### Key Design Decisions

1. **SoapySDR over direct HackRF library**: Provides unified API and easier device management
2. **GNU Radio for DSP**: Industry-standard SDR framework, extensible and well-documented
3. **Separate tab files**: Improves maintainability and code organization
4. **Callback-based telemetry**: Non-blocking, works well with Qt event loop

---

## Troubleshooting

### SoapySDR Not Found
```bash
# Install SoapySDR and HackRF support
brew install soapysdr soapyhackrf
```

### GNU Radio Import Errors
```bash
# GNU Radio requires system installation
brew install gnuradio
# Or use conda
conda install -c conda-forge gnuradio
```

### HackRF Not Detected
- Ensure HackRF is plugged in via USB
- Check USB cable quality (use USB 2.0 port)
- Verify device permissions (may need udev rules on Linux)
- Test with `hackrf_info` command line tool

### No Telemetry Received
- Verify frequency and sample rate settings
- Check gain levels (may need adjustment)
- Ensure GNU Radio blocks are properly connected
- Check that transmitter is active and in range

---

## Files Modified

- ✅ `main.py` - Simplified, removed BLE code
- ✅ `requirements.txt` - Updated dependencies
- ✨ `telemetry_tab.py` - New file
- ✨ `connection_tab.py` - New file
- ✨ `telemetry_rx.py` - New file

---

## Questions?

If you need help with:
- Adding specific GNU Radio blocks
- Parsing your telemetry format
- Connecting the tabs together
- Performance optimization

Just let me know!

