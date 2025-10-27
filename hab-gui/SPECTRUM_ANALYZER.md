# Spectrum Analyzer Feature

## Overview
Added real-time spectrum analyzer functionality to the Telemetry tab with FFT visualization, configurable bandwidth parameters, and max hold capability.

## Features Added

### 1. Spectrum Analyzer Display
- **Real-time FFT plot** using PyQtGraph for high-performance rendering
- **Dark theme** matching the application aesthetic
- **Grid display** with frequency (Hz) on X-axis and power (dB) on Y-axis
- **Auto-scaling** plot that updates at ~20 Hz

### 2. Spectrum Controls
Located in a dedicated "Spectrum Controls" group box:

#### **RBW (Resolution Bandwidth)**
- Input field with kHz units
- Default: 10 kHz
- Controls the frequency resolution of the spectrum display
- Lower values = better frequency resolution but slower response

#### **VBW (Video Bandwidth)**
- Input field with kHz units
- Default: 10 kHz
- Controls the smoothing/averaging of the power measurements
- Lower values = smoother display but slower response to changes

#### **Max Hold Checkbox**
- When enabled, displays the maximum power level at each frequency bin over time
- Useful for capturing transient signals or finding peak emissions
- Persists until cleared

#### **Clear Button**
- Clears the spectrum display
- Resets max hold data
- Logs action to telemetry terminal

### 3. UI Layout
The Telemetry tab now uses a vertical splitter with:
- **Top section (75%):** Spectrum analyzer with controls and plot
- **Bottom section (25%):** Telemetry terminal

The splitter can be adjusted by dragging the divider.

## Technical Implementation

### Modified Files

#### `telemetry_tab.py`
**Added:**
- PyQtGraph integration for real-time plotting
- Spectrum analyzer controls (RBW, VBW, Max Hold, Clear)
- QSplitter layout to separate spectrum and terminal
- Timer-based plot updates (50ms interval = 20 Hz)
- Spectrum data handling with max hold logic
- Callback method `on_spectrum_data_received()` for FFT data

**Key Methods:**
- `on_spectrum_data_received(frequencies, power_db)` - Receives FFT data from receiver
- `update_spectrum_display()` - Updates plot with current or max hold data
- `clear_spectrum_clicked()` - Clears spectrum and max hold data

#### `telemetry_rx.py`
**Added:**
- FFT processing blocks (stream_to_vector, fft_vcc, complex_to_mag_squared)
- Vector sink to capture FFT data
- Spectrum callback support in `TelemetryReceiver` class
- `_update_spectrum()` method to extract and process FFT data
- Automatic FFT shifting to center DC component
- Power conversion to dB scale
- Frequency bin calculation relative to center frequency

**Key Features:**
- 1024-point FFT with Blackman-Harris window
- 10 Hz spectrum update rate
- Automatic frequency labeling based on center frequency
- dB power scaling with log protection

#### `requirements.txt`
**Added:**
- `pyqtgraph` - High-performance plotting library

## Data Flow

```
HackRF Device
    ↓
SoapySDR Source (in your GNU Radio blocks)
    ↓
├─→ Stream to Vector (1024 samples)
│       ↓
│   FFT Block (Blackman-Harris window)
│       ↓
│   Complex to Mag² (Power)
│       ↓
│   Vector Sink
│       ↓
│   _update_spectrum() [Extract FFT data]
│       ↓
│   Convert to dB, FFT shift, calculate frequencies
│       ↓
│   TelemetryReceiverInterface._handle_spectrum()
│       ↓
│   TelemetryTab.on_spectrum_data_received()
│       ↓
│   Apply max hold (if enabled)
│       ↓
│   QTimer triggers update_spectrum_display()
│       ↓
│   PyQtGraph PlotWidget displays spectrum
│
└─→ Your telemetry processing chain
```

## Usage

### Starting the Spectrum Analyzer

1. **Configure Connection** in the Connection tab:
   - Connect to HackRF
   - Set frequency, sample rate, and gains
   - Apply parameters

2. **Start Reception** in Telemetry tab:
   - Click "Start RX"
   - Spectrum analyzer will begin updating automatically
   - Adjust RBW/VBW as needed

3. **Use Max Hold** (optional):
   - Check "Max Hold" to capture peak signals
   - Click "Clear" to reset

4. **Stop Reception**:
   - Click "Stop RX"
   - Spectrum will freeze at last received data

### Interpreting the Display

- **X-axis:** Frequency in Hz (centered at your tuned frequency)
- **Y-axis:** Power in dB
- **Peak at center:** Usually DC offset or LO leakage
- **Signals:** Appear as peaks in the spectrum
- **Noise floor:** Baseline level (depends on gains)

### Adjusting Parameters

#### **RBW (Resolution Bandwidth)**
- **Increase** for faster updates, coarser frequency resolution
- **Decrease** for better frequency resolution, slower updates
- Note: This parameter is for display purposes in current implementation

#### **VBW (Video Bandwidth)**
- **Increase** for faster response to signal changes
- **Decrease** for smoother, more stable display
- Note: This parameter is for display purposes in current implementation

> **Note:** Full RBW/VBW implementation requires additional GNU Radio filtering blocks. Current implementation provides the UI framework.

## Integration with GNU Radio Blocks

When you add your GNU Radio source block (e.g., SoapySDR source), you need to connect it to the FFT chain:

```python
# In TelemetryReceiver.__init__() in telemetry_rx.py

# After creating your source block:
self.source = soapy.source(...)  # Your source block

# Connect to FFT chain for spectrum analyzer:
self.connect((self.source, 0), (self.stream_to_vector, 0))
self.connect((self.stream_to_vector, 0), (self.fft_block, 0))
self.connect((self.fft_block, 0), (self.c2mag, 0))
self.connect((self.c2mag, 0), (self.vector_sink, 0))

# Also connect source to your telemetry processing:
self.connect((self.source, 0), (your_demodulator, 0))
# ... etc
```

## Performance Considerations

### Update Rates
- **FFT Processing:** 10 Hz (configurable in `_message_poll_loop`)
- **Display Update:** 20 Hz (configurable via `spectrum_timer`)
- **FFT Size:** 1024 points (configurable via `self.fft_size`)

### Optimization Tips
1. **Increase FFT size** for better frequency resolution (but slower updates)
2. **Decrease update rate** if CPU usage is high
3. **Use max hold sparingly** - adds minimal overhead but accumulates data
4. **Clear regularly** when using max hold to free memory

### Memory Usage
- Minimal - only stores last FFT frame and max hold array
- ~8-16 KB per FFT frame (1024 floats)

## Future Enhancements

### Suggested Improvements
1. **Implement true RBW/VBW filtering** in GNU Radio flowgraph
2. **Add averaging modes** (exponential, moving average, etc.)
3. **Waterfall display** showing spectrum over time
4. **Peak markers** with frequency readout
5. **Reference level control** (Y-axis scale adjustment)
6. **Span control** (zoom into frequency range)
7. **Persistence display** (show signal history with fading)
8. **Measurement markers** (delta frequency, power measurements)
9. **Screenshot/export** spectrum data
10. **Color map options** for waterfall

### Example: Adding a Waterfall

To add a waterfall display below the spectrum:

```python
# In telemetry_tab.py __init__():
self.waterfall = pg.PlotWidget()
self.waterfall_img = pg.ImageItem()
self.waterfall.addItem(self.waterfall_img)
self.waterfall_data = np.zeros((100, self.fft_size))  # 100 time slices

# In on_spectrum_data_received():
# Roll waterfall data
self.waterfall_data = np.roll(self.waterfall_data, -1, axis=0)
self.waterfall_data[-1, :] = power_db
self.waterfall_img.setImage(self.waterfall_data.T)
```

## Troubleshooting

### No Spectrum Display
- **Check:** PyQtGraph installed? `pip install pyqtgraph`
- **Check:** GNU Radio source connected to FFT chain?
- **Check:** RX started and HackRF connected?

### Flat Line / No Signal
- **Check:** Antenna connected?
- **Check:** Gains set appropriately (try LNA=16, VGA=20)
- **Check:** Frequency set correctly
- **Check:** Sample rate matches your signal bandwidth

### Performance Issues / Laggy Display
- **Reduce:** FFT update rate in `_message_poll_loop` (increase sleep time)
- **Reduce:** Display update rate (increase `spectrum_timer` interval)
- **Reduce:** FFT size (lower frequency resolution)

### Max Hold Not Working
- **Check:** Max Hold checkbox is checked
- **Check:** New signals are actually stronger than previous
- **Try:** Click "Clear" to reset, then enable max hold again

## Dependencies

- `PySide6` - Qt GUI framework
- `pyqtgraph` - High-performance plotting
- `numpy` - Numerical operations
- `gnuradio` - SDR signal processing
- `SoapySDR` - Device abstraction layer

## Example Use Cases

### 1. Finding Your Transmitter Frequency
1. Enable Max Hold
2. Key your transmitter briefly
3. Look for peak in spectrum
4. Read frequency from X-axis

### 2. Adjusting Receiver Gains
1. Watch noise floor level
2. Increase gains until noise floor rises
3. Back off slightly for optimal SNR
4. Watch for overload (clipping)

### 3. Monitoring Channel Activity
1. Disable Max Hold for live view
2. Watch for signal activity
3. Adjust VBW for smoother display
4. Use RBW for frequency resolution

### 4. Signal Quality Assessment
1. Enable Max Hold
2. Transmit test signal
3. Check for clean peak
4. Look for spurious emissions
5. Verify bandwidth

---

## Summary

The spectrum analyzer provides real-time visualization of the RF spectrum, essential for:
- Signal identification
- Frequency verification
- Gain optimization
- Interference detection
- System debugging

All features are integrated seamlessly with the existing telemetry reception system and share the same HackRF connection configured in the Connection tab.

