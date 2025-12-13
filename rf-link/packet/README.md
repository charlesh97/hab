# Packet Communication System

This directory contains the packet-based communication system for the RF link project. The system uses GNU Radio for software-defined radio (SDR) packet transmission and reception.

## Directory Structure

### Core Modules

#### `packet_tx.py` and `packet_rx.py`
**Required hierarchical blocks** that implement the packet transmission and reception chains.

- **`packet_tx`**: Hierarchical block (`gr.hier_block2`) that implements the complete packet transmission chain including:
  - CRC-32 generation
  - Forward Error Correction (FEC) encoding
  - Header formatting
  - Symbol mapping
  - Pulse shaping and upsampling
  
- **`packet_rx`**: Hierarchical block (`gr.hier_block2`) that implements the complete packet reception chain including:
  - Matched filtering and downsampling
  - Symbol recovery
  - Header detection and decoding
  - FEC decoding
  - CRC-32 verification

These modules are imported and used by the test scripts and can be integrated into custom flowgraphs.

**Key Features:**
- Configurable FEC encoding/decoding (convolutional codes)
- Configurable modulation schemes (PSK constellations)
- Tagged stream processing for packet-based communication
- Message port interfaces for packet I/O

### Test Scripts (Hardware Interface)

#### `telemetry_tx.py`
**Test script for packet transmission with HackRF One.**

This script provides a complete, runnable transmitter that:
- Generates random test packets (20-200 bytes) at configurable intervals
- Interfaces with HackRF One via SoapySDR
- Includes burst padding for HackRF buffer management
- Supports command-line configuration of frequency, sample rate, and gain settings

**Usage:**
```bash
python3 telemetry_tx.py --freq 915e6 --offset 200e3 --samp 2e6 --hackrf-amp --hackrf-vga 16 --hackrf-serial '000000000000000060a464dc3606610f'
```

**Features:**
- Automatic burst padding (500K samples) to prevent HackRF TX buffer underflow
- Configurable RF parameters (frequency, sample rate, gains)
- Multiple HackRF support via serial number selection
- Debug output for monitoring packet generation and transmission

#### `telemetry_rx.py`
**Test script for packet reception with HackRF One.**

This script provides a complete, runnable receiver that:
- Receives packets via HackRF One
- Displays decoded packet contents
- Supports command-line configuration of frequency, sample rate, and gain settings

**Usage:**
```bash
python3 telemetry_rx.py --freq 915e6 --samp 2e6 --hackrf-lna 16 --hackrf-vga 16
```

**Features:**
- Real-time packet decoding and display
- Configurable RF parameters
- Error detection and reporting

### Debug and Development Tools

#### `debug_packet_rxtx/`
**Development and testing tools that do not require hardware.**

This directory contains modified versions of the packet modules and a loopback test system for development and debugging without requiring HackRF hardware.

**Contents:**
- `packet_loopback_hier_custom.py`: Loopback test flowgraph that connects TX → RX directly (no hardware)
- `packet_rx.py`: Modified RX module with additional debugging capabilities
- `packet_tx.py`: Modified TX module for testing
- `padding_and_packing_block.py`: Custom block for testing bit padding and packing logic
- `packet_chain_analysis.md`: Detailed analysis of the packet chain data flow and bit packing issues

**Purpose:**
- Test packet chain modifications without hardware
- Debug bit packing/unpacking issues
- Develop and test custom blocks (padding, packing, etc.)
- Analyze packet chain behavior and data formats
- Validate fixes for encoding/decoding edge cases

**Key Differences from Production Modules:**
- Enhanced debug output and logging
- Custom padding/packing blocks for testing
- Loopback configuration for software-only testing
- Analysis documentation and test utilities

## Typical Workflow

1. **Development**: Use `debug_packet_rxtx/` tools to develop and test custom blocks and modifications without hardware
2. **Hardware Testing**: Use `telemetry_tx.py` and `telemetry_rx.py` to test with HackRF hardware
3. **Integration**: Import `packet_tx` and `packet_rx` hierarchical blocks into custom flowgraphs

## Dependencies

- GNU Radio 3.10+
- SoapySDR (for HackRF support)
- Python 3.x
- NumPy
- HackRF One hardware (for `telemetry_*.py` scripts)

## Configuration

### Packet Parameters
- **Modulation**: QPSK for payload, BPSK for header
- **FEC**: Convolutional code (k=7, rate=1/2, terminated)
- **Sample Rate**: Configurable (default 2 MHz)
- **Symbol Rate**: Sample rate / SPS (Samples Per Symbol)

### HackRF Settings
- **Frequency**: Configurable via command-line (default 1 GHz)
- **Gains**: 
  - LNA (Low Noise Amplifier): 0-40 dB in 8 dB steps
  - VGA (Variable Gain Amplifier): 0-62 dB in 2 dB steps
  - AMP (RF Amplifier): 0 or 14 dB (on/off)

## Notes

- The telemetry scripts include burst padding to ensure HackRF's TX buffer remains filled between packets
- The debug tools are essential for developing custom blocks and understanding packet chain behavior
- All modules support tagged streams for packet-based processing

