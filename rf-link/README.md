# RF-Link: DVB-S2 Transmitter and Receiver for HAB

This repository contains a complete DVB-S2 transmission and reception system for high-altitude balloon (HAB) applications, built on GNU Radio and the `gr-dvbs2rx` module. The system supports video streaming over DVB-S2 using HackRF One devices.

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Installation and Setup](#installation-and-setup)
  - [Prerequisites](#prerequisites)
  - [Building gr-dvbs2rx](#building-gr-dvbs2rx)
  - [Virtual Environment Setup](#virtual-environment-setup)
  - [Environment Configuration](#environment-configuration)
  - [Verification](#verification)
- [Bitrate Calculation with dvbs2rate](#bitrate-calculation-with-dvbs2rate)
- [Video Encoding Pipeline](#video-encoding-pipeline)
  - [FFmpeg Encoding](#ffmpeg-encoding)
  - [TSP Rate Regulation](#tsp-rate-regulation)
- [HackRF Support](#hackrf-support)
  - [Finding Your HackRF Serial Number](#finding-your-hackrf-serial-number)
  - [HackRF Modifications](#hackrf-modifications)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)
- [Additional Resources](#additional-resources)

## Overview

This project provides:

- **DVB-S2 Transmitter (`dvbs2-tx-mod`)**: Encodes MPEG transport streams into DVB-S2 modulated IQ samples for transmission via HackRF One
- **DVB-S2 Receiver (`dvbs2-rx-mod`)**: Receives and decodes DVB-S2 signals from HackRF One, outputting MPEG transport streams
- **Bitrate Calculator (`dvbs2rate`)**: Calculates precise transport stream bitrates for given symbol rates and DVB-S2 parameters
- **Video Encoding Pipeline**: FFmpeg + TSP tools to encode video at controlled bitrates matching DVB-S2 parameters

The system is designed for real-time video streaming over radio links, with configurable modulation schemes (QPSK, 8PSK, etc.), code rates, and symbol rates to match link conditions.

## Project Structure

```
rf-link/
├── gr-dvbs2rx/           # GNU Radio out-of-tree module with DVB-S2 blocks
├── dtv-utils-master/     # Utilities including dvbs2rate calculator
├── dvbs2-tx-mod          # Modified transmitter application with HackRF support
├── dvbs2-rx-mod          # Modified receiver application with HackRF support
├── setup_env.sh          # Environment setup script
├── requirements.txt      # Python dependencies
├── sdr-commands.txt      # Ready-to-use command examples
├── QUICKSTART.md         # Quick setup guide (superseded by this README)
└── README.txt            # Original notes (superseded by this README)
```

## Installation and Setup

### Prerequisites

1. **GNU Radio** (version 3.10+ recommended)
   - macOS: `brew install gnuradio`
   - Linux: Install via your package manager (e.g., `apt-get install gnuradio-dev`)

2. **SoapySDR and HackRF Support**
   - macOS: `brew install soapysdr hackrf`
   - Linux: `apt-get install soapysdr-module-hackrf` or build from source

3. **Build Tools**
   - CMake (3.10+)
   - C++ compiler with C++14 support
   - Python 3.x

4. **Video Tools** (for encoding pipeline)
   - FFmpeg: `brew install ffmpeg` or `apt-get install ffmpeg`
   - TSDuck: `brew install tsduck` or download from [tsduck.io](https://tsduck.io)

### Building gr-dvbs2rx

The `gr-dvbs2rx` module provides the core DVB-S2 signal processing blocks. Build it as follows:

```bash
cd gr-dvbs2rx
mkdir -p build && cd build
cmake ..
make -j$(nproc)  # Use $(sysctl -n hw.ncpu) on macOS
sudo make install
```

**Note**: The `setup_env.sh` script will automatically detect and add the build directory to your Python path if the module isn't installed system-wide.

### Virtual Environment Setup

**Important**: Modern Python installations (especially on macOS) require using a virtual environment. The project includes a `venv/` directory with the necessary dependencies.

To create or activate the virtual environment:

```bash
# If venv doesn't exist, create it:
python3 -m venv venv

# Activate the virtual environment:
source venv/bin/activate  # macOS/Linux
```

### Environment Configuration

The `setup_env.sh` script configures all necessary environment variables for running the DVB-S2 applications. **You must source this script before running dvbs2-tx or dvbs2-rx:**

```bash
source setup_env.sh
```

This script:

1. **Detects GNU Radio installation**: Automatically finds GNU Radio installed via Homebrew (macOS) or system packages (Linux)
2. **Sets library paths**: Configures `DYLD_LIBRARY_PATH` (macOS) or `LD_LIBRARY_PATH` (Linux) to find GNU Radio libraries
3. **Configures Python path**: Adds GNU Radio and gr-dvbs2rx Python modules to `PYTHONPATH`
4. **Handles Qt frameworks**: Resolves Qt framework conflicts between system Qt and venv Qt on macOS
5. **Verifies installation**: Checks that GNU Radio and gr-dvbs2rx are accessible

The script will print status information showing what it found and configured.

### Verification

After sourcing `setup_env.sh`, verify everything works:

```bash
# Check GNU Radio
python3 -c "import gnuradio; print('GNU Radio:', gnuradio.version())"

# Check gr-dvbs2rx
python3 -c "import gnuradio.dvbs2rx; print('gr-dvbs2rx: OK')"

# Check HackRF support
SoapySDRUtil --find=driver=hackrf
```

If any of these fail, check the troubleshooting section below.

## Bitrate Calculation with dvbs2rate

The `dvbs2rate` utility calculates the precise transport stream bitrate for a given symbol rate and DVB-S2 parameters (modulation, code rate, pilots on/off).

### Compiling dvbs2rate

```bash
cd dtv-utils-master
gcc -o dvbs2rate dvbs2rate.c -lm
```

### Usage

```bash
./dvbs2rate <symbol_rate>
./dvbs2rate -s <symbol_rate>    # Short FECFRAME rates
./dvbs2rate -x <symbol_rate>    # DVB-S2X rates
./dvbs2rate -sx <symbol_rate>   # Short FECFRAME DVB-S2X rates
```

### Example Output

For a 1 Msymb/s symbol rate:

```bash
$ ./dvbs2rate 1000000
DVB-S2 normal FECFRAME
QPSK, pilots off
coderate = 1/4,  BCH rate = 12, ts rate = 490243.151739
coderate = 1/3,  BCH rate = 12, ts rate = 656448.137889
coderate = 2/5,  BCH rate = 12, ts rate = 789412.126808
coderate = 1/2,  BCH rate = 12, ts rate = 988858.110188
...
QPSK, pilots on
coderate = 1/4,  BCH rate = 12, ts rate = 478577.008593
coderate = 1/3,  BCH rate = 12, ts rate = 640826.873385
coderate = 2/5,  BCH rate = 12, ts rate = 770626.765218
coderate = 1/2,  BCH rate = 12, ts rate = 965326.602969
...
```

**Note**: When using pilots, the bitrate is slightly lower due to the overhead of pilot blocks. For example, at 1 Msymb/s with QPSK 1/2 and pilots on, the transport stream bitrate is **965,326 bits/s** (~965 kbps).

This calculated bitrate must match the bitrate of your video encoder to avoid buffer underruns or overruns.

## Video Encoding Pipeline

To stream video over DVB-S2, you need to encode your video source at a bitrate that matches the calculated DVB-S2 transport stream bitrate. This is typically done with FFmpeg for encoding and TSP (TSDuck) for rate regulation.

### FFmpeg Encoding

FFmpeg encodes the video/audio into an MPEG transport stream. Example command:

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

Key parameters:
- `-muxrate 965326`: Sets the multiplex rate to match the calculated DVB-S2 bitrate (from dvbs2rate)
- `-b:v 700k`: Video bitrate (adjust based on desired quality)
- `-b:a 128k`: Audio bitrate
- `-mpegts_flags +resend_headers`: Ensures headers are resent for robustness
- Output goes to UDP multicast address (can be changed to a FIFO)

### TSP Rate Regulation

TSP (TSDuck) regulates the transport stream bitrate to exactly match the target. It reads from UDP (or a file) and writes to a FIFO:

```bash
# Create a FIFO (named pipe) for the transport stream
mkfifo /tmp/tsfifo

# Regulate the bitrate (in another terminal or background)
tsp -I ip 239.1.1.1:5001 -P regulate --bitrate 965326 -O file /tmp/tsfifo
```

The `-P regulate --bitrate 965326` option ensures the output bitrate is exactly 965,326 bits/s, matching the DVB-S2 calculation.

### Complete Pipeline

```bash
# Terminal 1: Create FIFO
mkfifo /tmp/tsfifo

# Terminal 2: FFmpeg encoding to UDP
ffmpeg -re -fflags +genpts -i input.mp4 \
  -vf "scale=1920:1080,format=yuv420p" -r 30 \
  -c:v libx264 -preset veryfast -tune zerolatency \
  -g 30 -keyint_min 30 \
  -b:v 700k -maxrate 700k -bufsize 500k \
  -c:a mp2 -b:a 128k \
  -f mpegts -muxrate 965326 -mpegts_flags +resend_headers \
  "udp://239.1.1.1:5001?pkt_size=1316"

# Terminal 3: TSP rate regulation
tsp -I ip 239.1.1.1:5001 -P regulate --bitrate 965326 -O file /tmp/tsfifo

# Terminal 4: DVB-S2 transmitter (reads from FIFO)
source setup_env.sh
python3 dvbs2-tx-mod \
  --source file \
  --in-file /tmp/tsfifo \
  --sink hackrf \
  --hackrf-vga 10 \
  --hackrf-amp \
  --hackrf-serial '000000000000000060a464dc3606610f' \
  --freq 915e6 \
  --sym-rate 1e6 \
  --modcod QPSK1/2 \
  --rolloff 0.35 \
  --pilots
```

## HackRF Support

The original `gr-dvbs2rx` applications (`dvbs2-tx` and `dvbs2-rx`) support USRP, BladeRF, PlutoSDR, and RTL-SDR, but **not HackRF**. This repository includes modified versions (`dvbs2-tx-mod` and `dvbs2-rx-mod`) that add full HackRF One support via SoapySDR.

### Finding Your HackRF Serial Number

Each HackRF One device has a unique serial number. To find it:

```bash
# Method 1: Using hackrf_info
hackrf_info

# Method 2: Using SoapySDR
SoapySDRUtil --find=driver=hackrf
```

The serial number will look like: `000000000000000060a464dc3606610f`

You can extract just the serial portion (without the leading zeros) or use the full string. The modified applications accept either format.

### HackRF Modifications

The following modifications were made to add HackRF support:

#### dvbs2-tx-mod Changes

1. **Added HackRF sink support**:
   - Uses SoapySDR with `driver=hackrf`
   - Supports serial number specification for multi-device setups
   - Implements dual-stage gain control (AMP + VGA)

2. **Command-line options added**:
   - `--hackrf-amp`: Enable RF amplifier (0 or 14 dB boost)
   - `--hackrf-vga`: VGA gain (0-47 dB, step 1 dB)
   - `--hackrf-serial`: Device serial number

3. **Gain management**:
   - Total TX gain = VGA (0-47 dB) + AMP (0 or 14 dB)
   - Maximum TX gain: 61 dB (47 + 14)

#### dvbs2-rx-mod Changes

1. **Added HackRF source support**:
   - Uses SoapySDR with `driver=hackrf`
   - Supports serial number specification
   - Implements three-stage gain control (AMP + LNA + VGA)

2. **Command-line options added**:
   - `--hackrf-amp`: Enable RF amplifier (0 or 14 dB boost)
   - `--hackrf-lna`: LNA gain (0-40 dB, step 8 dB)
   - `--hackrf-vga`: VGA gain (0-62 dB, step 2 dB)
   - `--hackrf-serial`: Device serial number

3. **Gain management**:
   - Total RX gain = LNA (0-40 dB) + VGA (0-62 dB) + AMP (0 or 14 dB)
   - Maximum RX gain: 116 dB (40 + 62 + 14)

### HackRF Gain Recommendations

**Transmitter (TX)**:
- Start with VGA = 10-20 dB and AMP off for testing
- Enable AMP only if you need more output power
- Be careful with high gain to avoid saturation

**Receiver (RX)**:
- Start with LNA = 8-16 dB, VGA = 10-20 dB, AMP off
- Increase LNA first (better noise figure)
- Use VGA for fine-tuning
- Enable AMP only if absolutely necessary (adds noise)

## Usage Examples

See `sdr-commands.txt` for ready-to-use command examples. Here are the complete examples:

### Transmitting Video

```bash
# Activate virtual environment and setup environment
source venv/bin/activate
source setup_env.sh

# Transmit from a transport stream file
python3 dvbs2-tx-mod \
  --source file \
  --in-file thefuryclip.ts \
  --sink hackrf \
  --hackrf-vga 10 \
  --hackrf-amp \
  --hackrf-serial '000000000000000060a464dc3606610f' \
  --freq 915e6 \
  --sym-rate 1e6 \
  --modcod QPSK1/2 \
  --rolloff 0.35 \
  --pilots
```

**Parameters explained**:
- `--source file`: Read from a file (or use `fd` for stdin)
- `--in-file thefuryclip.ts`: Input MPEG transport stream file
- `--sink hackrf`: Use HackRF One as transmitter
- `--hackrf-vga 10`: VGA gain of 10 dB
- `--hackrf-amp`: Enable RF amplifier (+14 dB)
- `--hackrf-serial`: Your HackRF's serial number
- `--freq 915e6`: Center frequency 915 MHz (ISM band)
- `--sym-rate 1e6`: Symbol rate 1 million symbols/second
- `--modcod QPSK1/2`: QPSK modulation with 1/2 code rate
- `--rolloff 0.35`: Root-raised cosine filter rolloff factor
- `--pilots`: Enable pilot symbols for better synchronization

### Receiving Video

```bash
# Activate virtual environment and setup environment
source venv/bin/activate
source setup_env.sh

# Receive and save to file
python3 dvbs2-rx-mod \
  --sink file \
  --out-file video.ts \
  --source hackrf \
  --hackrf-vga 10 \
  --hackrf-lna 3 \
  --hackrf-amp \
  --hackrf-serial '000000000000000060a464dc3674640f' \
  --freq 915e6 \
  --sym-rate 1e6 \
  --modcod QPSK1/2 \
  --rolloff 0.35 \
  --gui \
  --log
```

**Parameters explained**:
- `--source hackrf`: Use HackRF One as receiver
- `--hackrf-lna 3`: LNA gain (3 × 8 = 24 dB, typical values: 0-5)
- `--gui`: Enable graphical user interface (shows signal quality, spectrum, etc.)
- `--log`: Print periodic statistics (SNR, frame counts, etc.)
- Other parameters must match the transmitter settings

### Testing with File-to-File

Before testing with hardware, verify everything works with file I/O:

```bash
# Transmit to file
python3 dvbs2-tx-mod \
  --source file \
  --in-file input.ts \
  --sink file \
  --out-file output.iq \
  --sym-rate 1e6 \
  --modcod QPSK1/2 \
  --rolloff 0.35 \
  --pilots

# Receive from file
python3 dvbs2-rx-mod \
  --source file \
  --in-file output.iq \
  --sink file \
  --out-file decoded.ts \
  --sym-rate 1e6 \
  --modcod QPSK1/2 \
  --rolloff 0.35 \
  --gui
```

Then play the decoded transport stream:
```bash
ffplay decoded.ts
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'gnuradio.dvbs2rx'"

**Solution**: The gr-dvbs2rx module is not found. Try:

1. Make sure you've sourced `setup_env.sh`
2. Build and install gr-dvbs2rx:
   ```bash
   cd gr-dvbs2rx/build
   sudo make install
   ```
3. Or add the build directory to PYTHONPATH manually:
   ```bash
   export PYTHONPATH=$PWD/gr-dvbs2rx/build/python:$PYTHONPATH
   ```

### Library loading errors on macOS

**Solution**: Add to your shell profile (`~/.zshrc` or `~/.bash_profile`):

```bash
export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
```

Then restart your terminal or run `source ~/.zshrc`.

### HackRF not found

**Solution**: 

1. Check that HackRF drivers are installed:
   ```bash
   brew install hackrf  # macOS
   ```

2. Verify HackRF is detected:
   ```bash
   SoapySDRUtil --find=driver=hackrf
   hackrf_info
   ```

3. Check USB permissions (Linux):
   ```bash
   sudo usermod -a -G plugdev $USER
   # Then log out and back in
   ```

### Qt framework conflicts on macOS

The `setup_env.sh` script handles this automatically, but if you still have issues:

1. Make sure you're using the virtual environment's Qt (or system Qt, not both)
2. The script removes venv Qt from `DYLD_FRAMEWORK_PATH` to prevent conflicts

### Transport stream bitrate mismatch

**Symptom**: Video stuttering, buffer underruns, or sync issues

**Solution**: 
1. Calculate the exact bitrate using `dvbs2rate`
2. Match FFmpeg's `-muxrate` and TSP's `--bitrate` to the calculated value
3. Ensure video encoding bitrate + audio bitrate + overhead ≈ calculated bitrate

### Poor reception quality

**Solutions**:
1. Adjust HackRF gain settings (increase LNA first, then VGA)
2. Check antenna connections and positioning
3. Verify frequency, symbol rate, and MODCOD match between TX and RX
4. Use `--gui` to monitor signal quality in real-time
5. Try different code rates (lower code rates are more robust)

## Additional Resources

- **gr-dvbs2rx Official Documentation**: See `gr-dvbs2rx/docs/usage.md` for detailed application documentation
- **gr-dvbs2rx Installation Guide**: See `gr-dvbs2rx/docs/installation.md` for build instructions
- **gr-dvbs2rx Support Matrix**: See `gr-dvbs2rx/docs/support.md` for supported features and limitations
- **GNU Radio Wiki**: [Out-of-Tree Modules](https://wiki.gnuradio.org/index.php/OutOfTreeModules)
- **HackRF One Documentation**: [Great Scott Gadgets](https://greatscottgadgets.com/hackrf/)
- **DVB-S2 Standard**: ETSI EN 302 307 (Digital Video Broadcasting)

## License

This project includes code from:
- **gr-dvbs2rx**: GPLv3 (Copyright Igor Freire, Ahmet Inan, Ron Economos)
- **dtv-utils**: GPLv3 (Copyright Ron Economos)

See individual component licenses for details.

## Credits

- **gr-dvbs2rx Authors**: Igor Freire, Ahmet Inan, Ron Economos
- **HackRF Support**: Added for this project
- **Integration and Documentation**: HAB RF-Link Project

