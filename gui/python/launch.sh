#!/bin/bash
# Launch the HAB Ground Station GUI
# Source the environment and run main.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Source rf environment for GNU Radio + SoapySDR
RF_LINK_DIR="$SCRIPT_DIR/../../rf"
if [ -f "$RF_LINK_DIR/setup_env.sh" ]; then
    source "$RF_LINK_DIR/setup_env.sh" 2>/dev/null
fi

# Add this directory to Python path
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

echo "=== HAB Ground Station ==="
echo "Starting GUI..."
echo "Python: $(python3 --version 2>/dev/null || echo 'unknown')"
echo "GNU Radio: $(python3 -c 'from gnuradio import gr; print(gr.version())' 2>/dev/null || echo 'NOT AVAILABLE')"

python3 main.py "$@"
