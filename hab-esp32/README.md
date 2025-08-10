# HAB ESP32

High-altitude balloon project using ESP32 microcontroller with Zephyr RTOS.

## Getting Started with Zephyr

This project uses the [Zephyr RTOS](https://docs.zephyrproject.org/latest/develop/getting_started/index.html) for embedded development on the ESP32.

### Prerequisites

- Python 3.10 or later
- CMake 3.20.5 or later
- Devicetree compiler 1.4.6 or later

### Setup Instructions

1. **Install dependencies** (macOS):
   ```bash
   brew install cmake ninja gperf python3 python-tk ccache qemu dtc libmagic wget openocd
   ```

2. **Create and activate virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install west**:
   ```bash
   pip install west
   ```

4. **Initialize Zephyr workspace**:
   ```bash
   west init zephyrproject
   cd zephyrproject
   west update
   west zephyr-export
   ```

5. **Install Python dependencies**:
   ```bash
   west packages pip --install
   ```

6. **Install Zephyr SDK**:
   ```bash
   cd zephyr
   west sdk install
   ```

### Building and Flashing

- **Build**: `west build -p always -b <board-name> <sample-path>`
- **Flash**: `west flash`

### Resources

- [Zephyr Getting Started Guide](https://docs.zephyrproject.org/latest/develop/getting_started/index.html)
- [Zephyr Project Documentation](https://docs.zephyrproject.org/)
- [Supported Boards](https://docs.zephyrproject.org/latest/boards/index.html)
