#!/bin/bash
# Setup environment for dvbs2-tx/rx/dashboard execution
# Source this file before running: source setup_env.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS="$(uname -s)"

# Locate the Homebrew Python (3.14) that has GNU Radio installed
BREW_PYTHON=""
for p in /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3; do
    if [ -x "$p" ]; then
        BREW_PYTHON="$p"
        break
    fi
done

if [ -z "$BREW_PYTHON" ]; then
    echo "ERROR: Homebrew Python not found at /opt/homebrew/bin/python3.14"
    echo "Install with: brew install python@3.14"
    exit 1
fi

# Create a wrapper function so 'python3' resolves to the right Python
python3() {
    "$BREW_PYTHON" "$@"
}
export -f python3

# Also create 'python' alias
python() {
    "$BREW_PYTHON" "$@"
}
export -f python

# Set PYTHONPATH for GNU Radio modules (Homebrew on Apple Silicon)
if [ -d "/opt/homebrew/lib/python3.14/site-packages" ]; then
    export PYTHONPATH="/opt/homebrew/lib/python3.14/site-packages:$PYTHONPATH"
fi

# Add local module paths
export PYTHONPATH="$SCRIPT_DIR/dvbs2:$PYTHONPATH"
export PYTHONPATH="$SCRIPT_DIR/../gui/python:$PYTHONPATH"
export PYTHONPATH="$SCRIPT_DIR/deprecated:$PYTHONPATH"

# Fix Qt framework conflicts (Homebrew Qt5 vs venv)
if [ -d "/opt/homebrew/Cellar/qt@5" ]; then
    QT_VERSION=$(ls -1 /opt/homebrew/Cellar/qt@5 | sort -V | tail -1)
    QT_FRAMEWORK_PATH="/opt/homebrew/Cellar/qt@5/$QT_VERSION/lib"
    if [ -z "$DYLD_FRAMEWORK_PATH" ]; then
        export DYLD_FRAMEWORK_PATH="$QT_FRAMEWORK_PATH"
    else
        export DYLD_FRAMEWORK_PATH="$QT_FRAMEWORK_PATH:$DYLD_FRAMEWORK_PATH"
    fi
    export QT_PLUGIN_PATH="$QT_FRAMEWORK_PATH/plugins"
fi

# Verify
echo "=== Environment Ready ==="
python3 -c "
import sys
try:
    from gnuradio import gr
    print(f'GNU Radio: {gr.version()}')
    from gnuradio import dtv, dvbs2rx, soapy
    print('DVB-S2 modules: OK')
except ImportError as e:
    print(f'ERROR: {e}')
    sys.exit(1)
" || echo "WARNING: GNU Radio not found in this environment"
