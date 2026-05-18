#!/bin/bash
# Setup environment for dvbs2-tx/rx standalone execution
# Source this file before running: source setup_env.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS="$(uname -s)"

# Try venv first (preferred)
if [ -d "$SCRIPT_DIR/venv/bin" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Add Python path for GNU Radio (Homebrew on Apple Silicon)
if [ -d "/opt/homebrew/lib/python3.14/site-packages" ]; then
    export PYTHONPATH="/opt/homebrew/lib/python3.14/site-packages:$PYTHONPATH"
fi

# Add local modules
export PYTHONPATH="$SCRIPT_DIR/dvbs2:$PYTHONPATH"
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

# Remove venv Qt frameworks to prevent conflicts
if [ -n "$VIRTUAL_ENV" ] && [ -n "$DYLD_FRAMEWORK_PATH" ]; then
    export DYLD_FRAMEWORK_PATH=$(echo "$DYLD_FRAMEWORK_PATH" | tr ':' '\n' | grep -v "$VIRTUAL_ENV" | tr '\n' ':' | sed 's/:$//')
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
" 2>&1 || echo "WARNING: GNU Radio not found in this environment"
