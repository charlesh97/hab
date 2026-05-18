#Cursor generated 

# Installing gr-dvbs2rx Blocks

## Issue
After building, the blocks may not appear in GNU Radio Companion because they haven't been installed to the system.

## Solution

1. **Install the module:**
   ```bash
   cd /Users/charleshood/Documents/Github/hab/rf-link/gr-dvbs2rx/build
   sudo make install
   ```

2. **On macOS, update library paths (if needed):**
   ```bash
   # The libraries should be installed to:
   # /opt/homebrew/Cellar/gnuradio/3.10.12.0_4/lib/
   # /opt/homebrew/Cellar/gnuradio/3.10.12.0_4/lib/python3.13/site-packages/
   # /opt/homebrew/Cellar/gnuradio/3.10.12.0_4/share/gnuradio/grc/blocks/
   ```

3. **Verify installation:**
   ```bash
   python3 -c "import dvbs2rx; print('✓ Module found'); print('Available blocks:', [x for x in dir(dvbs2rx) if not x.startswith('_')])"
   ```

4. **If blocks still don't appear in GRC:**
   - Restart GNU Radio Companion
   - Check that blocks are in: `/opt/homebrew/Cellar/gnuradio/3.10.12.0_4/share/gnuradio/grc/blocks/`
   - Verify Python can import: `python3 -c "import dvbs2rx"`

## Alternative: Use without installation

If you don't want to install system-wide, you can use the blocks from the build directory by setting PYTHONPATH:

```bash
export PYTHONPATH=/Users/charleshood/Documents/Github/hab/rf-link/gr-dvbs2rx/build/python:$PYTHONPATH
export GRC_BLOCKS_PATH=/Users/charleshood/Documents/Github/hab/rf-link/gr-dvbs2rx/build/grc:$GRC_BLOCKS_PATH
```

But installation is recommended for proper integration.

