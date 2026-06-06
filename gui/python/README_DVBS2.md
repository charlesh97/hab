# DVBS-2 TX Integration

This document describes the integration of the GNU Radio DVBS-2 transmitter into the HAB Ground Station GUI.

## Overview

The DVBS-2 TX tab provides functionality to transmit MP4 video files over the air using the DVBS-2 standard via HackRF devices.

## Architecture

### Components

1. **`dvbs2_flowgraph.py`** - Refactored GNU Radio flowgraph (PyQt5 → PySide6, PlutoSDR → SoapySDR/HackRF)
2. **`dvbs2_tx_tab.py`** - PySide6 GUI tab with file input, pipeline control, and spectrum visualization
3. **`connection_tab.py`** - Enhanced with device status helper methods
4. **`main.py`** - Updated to include the new DVBS-2 TX tab

### Integration Flow

```
1. Connection Tab → Select and connect HackRF device
2. DVBS-2 TX Tab → Select MP4 file
3. Start Pipeline → ffmpeg + tsp processes create /tmp/tsfifo
4. Start TX → GNU Radio flowgraph reads /tmp/tsfifo and transmits via HackRF
5. Spectrum Visualization → Real-time display (current: simulated, TODO: actual signal extraction)
```

## Features

### File Input
- Browse for MP4 files
- Display selected file path
- File validation

### Pipeline Control
- Start Pipeline button - launches ffmpeg and tsp processes
- Stop Pipeline button - terminates processes and cleans up
- Debug terminal showing real-time output from ffmpeg and tsp
- Status indicator

### Transmission Control
- Start TX button - validates device connection and starts GNU Radio flowgraph
- Stop TX button - stops flowgraph
- Device validation checks HackRF connection from Connection tab
- Status indicator

### Spectrum Visualization
- Frequency spectrum plot (pyqtgraph PlotWidget)
- Waterfall plot (pyqtgraph ImageView)
- Real-time updates (~20 Hz)

## Usage

1. **Connect Device**: Go to Connection tab, refresh devices, select HackRF, click Connect
2. **Select File**: Go to DVBS-2 TX tab, click Browse, select MP4 file
3. **Start Pipeline**: Click "Start Pipeline" (launches ffmpeg → tsp → /tmp/tsfifo)
4. **Start TX**: Click "Start TX" (validates device, starts GNU Radio flowgraph)
5. **Monitor**: Watch debug output and spectrum visualization
6. **Stop**: Click "Stop TX" then "Stop Pipeline" (in order)

## Technical Details

### GNU Radio Flowgraph (`dvbs2_flowgraph.py`)

**Key Changes from original `dvbs2_tx.py`:**
- Removed PyQt5 GUI elements (waterfall sink, gain slider)
- Removed PlutoSDR (`iio_pluto_sink_0`), added SoapySDR sink for HackRF
- Made embeddable - accepts parameters from Connection tab
- Configurable file source path (`/tmp/tsfifo`)
- Thread-safe spectrum data queue for GUI updates

**Flowgraph Chain:**
```
file_source → bbheader → bbscrambler → bch → ldpc → interleaver 
→ modulator → physical → fft_filter → soapy_sink
```

### Pipeline (`dvbs2_tx_tab.py`)

**ffmpeg Command:**
```bash
ffmpeg -re -fflags +genpts -i input.mp4 \
  -vf "scale=1920:1080,format=yuv420p" -r 30 \
  -c:v libx264 -preset veryfast -tune zerolatency \
  -g 30 -keyint_min 30 \
  -b:v 700k -maxrate 700k -bufsize 500k \
  -c:a mp2 -b:a 128k \
  -f mpegts -muxrate 965326 -mpegts_flags +resend_headers \
  "udp://239.1.1.1:5001?pkt_size=1316"
```

**tsp Command:**
```bash
tsp -I ip 239.1.1.1:5001 -P regulate --bitrate 965326 -O file /tmp/tsfifo
```

The pipeline:
1. ffmpeg encodes MP4 → MPEG-TS and sends to UDP multicast (239.1.1.1:5001)
2. tsp receives UDP → regulates bitrate → writes to /tmp/tsfifo (named pipe)
3. GNU Radio flowgraph reads /tmp/tsfifo

### Named Pipe Handling

The `/tmp/tsfifo` named pipe is:
- Created when pipeline starts (removed if exists)
- Removed when pipeline stops
- Read by GNU Radio file_source block

## Known Limitations & TODOs

1. **Spectrum Visualization**: Currently generates simulated spectrum data. Need to implement actual signal extraction from GNU Radio blocks using:
   - `blocks.stream_to_vector` or
   - Custom GNU Radio block with message port
   - Or use `blocks.throttle` + vector sink

2. **SoapySDR Sink Configuration**: Device arguments need proper formatting for SoapySDR. Current implementation converts dict to args string, but may need adjustment.

3. **Error Handling**: Add more robust error handling for:
   - Named pipe creation failures
   - Process crashes (ffmpeg/tsp)
   - GNU Radio flowgraph errors
   - Device connection issues

4. **Cleanup**: Ensure proper cleanup on:
   - Tab close
   - Application exit
   - Error conditions

5. **Testing**: Complete workflow testing needed:
   - End-to-end transmission test
   - Different MP4 file formats
   - Error recovery
   - Device hotplug scenarios

## Dependencies

- GNU Radio (system-installed, not pip)
- SoapySDR (system-installed, not pip)
- SoapyHackRF (system-installed, not pip)
- HackRF (hardware)
- ffmpeg (for encoding)
- tsp (TSP tools for TS processing)

Installation via Homebrew (macOS):
```bash
brew install gnuradio soapysdr soapyhackrf hackrf
brew install ffmpeg tsduck
```

## File Structure

```
hab-gui/
├── main.py                  # Main application (updated)
├── connection_tab.py        # Connection tab (enhanced)
├── dvbs2_flowgraph.py       # GNU Radio flowgraph (NEW)
├── dvbs2_tx_tab.py          # DVBS-2 TX tab (NEW)
├── dvbs2_tx.py              # Original GNURadio file (reference)
└── requirements.txt         # Python dependencies
```

## Future Enhancements

1. Add actual spectrum extraction from GNURadio blocks
2. Add TX gain control in DVBS-2 TX tab
3. Add frequency/rate controls in DVBS-2 TX tab
4. Add transmission statistics (bitrate, errors, etc.)
5. Support for multiple file formats (not just MP4)
6. Add preview of video before transmission
7. Add recording/playback of transmitted signal

