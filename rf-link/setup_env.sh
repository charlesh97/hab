#!/bin/bash
# Setup environment for dvbs2-rx standalone execution
# Source this file before running dvbs2-rx: source setup_env.sh

# Detect OS
OS="$(uname -s)"
ARCH="$(uname -m)"

# Detect GNU Radio installation path
if [[ "$OS" == "Darwin" ]]; then
    # macOS - check Homebrew locations
    if [[ "$ARCH" == "arm64" ]] || [[ "$ARCH" == "aarch64" ]]; then
        # Apple Silicon
        GNU_RADIO_PREFIX="/opt/homebrew"
    else
        # Intel
        GNU_RADIO_PREFIX="/usr/local"
    fi
    
    # Find the latest GNU Radio installation
    if [ -d "$GNU_RADIO_PREFIX/Cellar/gnuradio" ]; then
        GNU_RADIO_VERSION=$(ls -1 "$GNU_RADIO_PREFIX/Cellar/gnuradio" | sort -V | tail -1)
        GNU_RADIO_CELLAR="$GNU_RADIO_PREFIX/Cellar/gnuradio/$GNU_RADIO_VERSION"
        
        export DYLD_LIBRARY_PATH="$GNU_RADIO_CELLAR/lib:$DYLD_LIBRARY_PATH"
        # Find Python site-packages directory (handle multiple Python versions)
        for py_site in "$GNU_RADIO_CELLAR/lib/python"*/site-packages; do
            if [ -d "$py_site" ]; then
                export PYTHONPATH="$py_site:$PYTHONPATH"
                break
            fi
        done
    fi
    
    export DYLD_LIBRARY_PATH="$GNU_RADIO_PREFIX/lib:$DYLD_LIBRARY_PATH"
    
    # Fix Qt framework conflicts: Force PyQt5 to use system Qt instead of venv's bundled Qt
    # This prevents segmentation faults caused by duplicate Qt framework loading
    if [ -d "$GNU_RADIO_PREFIX/Cellar/qt@5" ]; then
        QT_VERSION=$(ls -1 "$GNU_RADIO_PREFIX/Cellar/qt@5" | sort -V | tail -1)
        QT_FRAMEWORK_PATH="$GNU_RADIO_PREFIX/Cellar/qt@5/$QT_VERSION/lib"
        # Prepend system Qt to framework path so it's loaded first
        if [ -z "$DYLD_FRAMEWORK_PATH" ]; then
            export DYLD_FRAMEWORK_PATH="$QT_FRAMEWORK_PATH"
        else
            export DYLD_FRAMEWORK_PATH="$QT_FRAMEWORK_PATH:$DYLD_FRAMEWORK_PATH"
        fi
        export QT_PLUGIN_PATH="$QT_FRAMEWORK_PATH/plugins"
    fi
    
    # Remove venv Qt frameworks from DYLD_FRAMEWORK_PATH to prevent conflicts
    if [ -n "$VIRTUAL_ENV" ] && [ -n "$DYLD_FRAMEWORK_PATH" ]; then
        export DYLD_FRAMEWORK_PATH=$(echo "$DYLD_FRAMEWORK_PATH" | tr ':' '\n' | grep -v "$VIRTUAL_ENV" | tr '\n' ':' | sed 's/:$//')
    fi
    
    # Check for system-wide installations in /usr/local (common for manually installed packages)
    if [ -d "/usr/local/lib/python3.14/site-packages" ]; then
        export PYTHONPATH="/usr/local/lib/python3.14/site-packages:$PYTHONPATH"
    fi
    # Also check for other Python versions in /usr/local
    for py_site in /usr/local/lib/python3.*/site-packages; do
        if [ -d "$py_site" ]; then
            export PYTHONPATH="$py_site:$PYTHONPATH"
        fi
    done
    
elif [[ "$OS" == "Linux" ]]; then
    # Linux - check common installation paths
    for prefix in "/usr/local" "/usr" "/opt/gnuradio"; do
        if [ -d "$prefix/lib" ] && [ -f "$prefix/lib/pkgconfig/gnuradio.pc" ]; then
            export LD_LIBRARY_PATH="$prefix/lib:$LD_LIBRARY_PATH"
            # Find Python site-packages directory
            for py_site in "$prefix/lib/python"*/site-packages; do
                if [ -d "$py_site" ]; then
                    export PYTHONPATH="$py_site:$PYTHONPATH"
                    break
                fi
            done
            break
        fi
    done
fi

# Add gr-dvbs2rx to Python path if built but not installed
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -d "$SCRIPT_DIR/gr-dvbs2rx/build/python" ]; then
    export PYTHONPATH="$SCRIPT_DIR/gr-dvbs2rx/build/python:$PYTHONPATH"
fi

# Add gr-dvbs2rx GRC blocks path if present
if [ -d "$SCRIPT_DIR/gr-dvbs2rx/build/grc" ]; then
    export GRC_BLOCKS_PATH="$SCRIPT_DIR/gr-dvbs2rx/build/grc:$GRC_BLOCKS_PATH"
fi

# Print status
echo "Environment setup for dvbs2-rx:"
echo "  PYTHONPATH: $PYTHONPATH"
if [[ "$OS" == "Darwin" ]]; then
    echo "  DYLD_LIBRARY_PATH: $DYLD_LIBRARY_PATH"
elif [[ "$OS" == "Linux" ]]; then
    echo "  LD_LIBRARY_PATH: $LD_LIBRARY_PATH"
fi

# Verify GNU Radio installation
if python3 -c "import gnuradio" 2>/dev/null; then
    echo "  ✓ GNU Radio found"
    python3 -c "import gnuradio; print(f\"    Version: {gnuradio.version()}\")" 2>/dev/null || true
else
    echo "  ✗ GNU Radio not found - please install GNU Radio first"
fi

# Verify gr-dvbs2rx
if python3 -c "import gnuradio.dvbs2rx" 2>/dev/null; then
    echo "  ✓ gr-dvbs2rx found"
else
    echo "  ✗ gr-dvbs2rx not found - building/installing may be needed"
    echo "    Run: cd gr-dvbs2rx && mkdir -p build && cd build && cmake .. && make && sudo make install"
fi

