# HAB GUI

A PySide6 desktop application for a High Altitude Balloon ground station.

**Features:**
- Dark theme with modern Fusion dark palette
- HackRF SDR integration via SoapySDR
- GNU Radio signal processing pipeline
- Telemetry reception and display
- Spectrum analyzer
- Real-time frequency and gain control

## Setup

This project requires system-level installation of GNU Radio and SoapySDR before installing Python packages.

### Prerequisites (macOS)

Install system dependencies via Homebrew:

```bash
# Install SoapySDR, HackRF support, and GNU Radio
brew install soapysdr soapyhackrf hackrf gnuradio
```

### Python Environment

**IMPORTANT:** GNU Radio and SoapySDR are installed system-wide by Homebrew. Your virtual environment needs access to these system packages.

Create virtual environment with `--system-site-packages` flag:

```bash
# Create venv with system site packages access (REQUIRED for GNU Radio)
python3 -m venv .venv --system-site-packages

# Activate venv
source .venv/bin/activate

# Upgrade pip and install Python packages
pip install --upgrade pip
pip install -r requirements.txt
```

**Why `--system-site-packages`?**

This flag allows your virtual environment to import packages installed system-wide (outside the venv). Since GNU Radio and SoapySDR are installed via Homebrew in the system's Python library path, this flag is **essential** for the application to find and use these libraries. Without it, you'll get `ModuleNotFoundError: No module named 'gnuradio'`.

### Alternative: Use Conda (Recommended for SDR projects)

Conda simplifies SDR dependency management since GNU Radio and SoapySDR are available via conda-forge:

```bash
conda create -n hab-gui python=3.10
conda activate hab-gui
conda install -c conda-forge gnuradio soapysdr
pip install -r requirements.txt
```

**Note:** With Conda, you don't need the `--system-site-packages` flag because Conda manages all dependencies within the conda environment itself.

### OS-specific notes

- **macOS:** GNU Radio and SoapySDR must be installed via Homebrew first
- **Linux:** Install packages via apt: `sudo apt-get install gnuradio python3-gnuradio soapysdr soapysdr-module-hackrf`
- **Windows:** Use pre-built GNU Radio binaries from gnuradio.org

## Run

```bash
python main.py
```

## Using the Application

### Connection Tab

1. **Refresh Devices:** Click "Refresh Devices" to scan for available HackRF hardware
2. **Connect:** Select a device and click "Connect" to establish USB connection
3. **Configure Parameters:**
   - Set frequency (MHz)
   - Adjust sample rate
   - Set LO ppm correction
   - Configure LNA and VGA gains
4. **Apply:** Click "Apply Parameters" to update the HackRF settings
5. **Disconnect:** Click "Disconnect" when finished

### Telemetry Tab

1. **Start RX:** Click "Start RX" to begin receiving telemetry data
2. **View Data:** Telemetry packets appear in the terminal display
3. **Export:** Use "Export CSV" button to save telemetry data (future feature)
4. **Stop RX:** Click "Stop RX" to stop reception

### Troubleshooting

**GNU Radio not found:**
- Ensure GNU Radio is installed: `brew list gnuradio`
- Check if accessible from venv: `python -c "import gnuradio"`
- **This error occurs if your venv was created without `--system-site-packages`**
- Solution: Recreate venv with the flag:
  ```bash
  deactivate
  rm -rf .venv
  python3 -m venv .venv --system-site-packages
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

**HackRF not detected:**
- Plug in HackRF via USB
- Test with command line: `hackrf_info`
- Check USB cable quality (use USB 2.0 port)

**SoapySDR errors:**
- Verify installation: `SoapySDRUtil --info`
- Check modules: `SoapySDRUtil --modules` (should show hackrf)
- Reinstall if needed: `brew reinstall soapyhackrf`

## Project Structure

```
hab-gui/
├── main.py                  # Application entry point
├── connection_tab.py         # HackRF device connection tab
├── telemetry_tab.py          # Telemetry display and control tab
├── telemetry_rx.py           # GNU Radio signal processing
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── REFACTORING_SUMMARY.md    # Detailed refactoring notes
└── SPECTRUM_ANALYZER.md      # Spectrum analyzer implementation guide
```
