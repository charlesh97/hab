# Padding, Packing, and CRC Block - GNU Radio Setup Guide

## Overview
The `padding_packing_crc_block.py` is a custom GNU Radio block that pads unpacked bits from FEC decoder, packs them into bytes, and validates CRC by trying all possible padding patterns.

## Key Features

- **Automatic Padding**: Pads missing bits to reach byte boundary
- **CRC Validation**: Tries all possible padding patterns and selects the one that makes CRC pass
- **Failure Reporting**: Prints detailed error messages if all CRC patterns fail
- **Pre-CRC Output**: Provides `precrc` port for debugging data before CRC validation

## Option 1: Keep in Packet Directory (Recommended for Local Use)

**Location**: Keep the file in the `debug_packet_rxtx/` directory alongside your other flowgraphs.

**Usage in GRC (Python Embedded Block)**:

1. Add a **Python Embedded Block** to your flowgraph
2. Set the **ID**: `padding_packing_crc_block`
3. In the **Code** section, use:

```python
from padding_packing_crc_block import padding_packing_crc_block

def __init__(self):
    self.blocks_padding_crc = padding_packing_crc_block()
```

4. Connect the ports:
   - Input: `fec.async_decoder` 'out' → `padding_packing_crc_block` 'in'
   - Output: `padding_packing_crc_block` 'out' → `digital.crc32_async_bb` 'in'
   - Optional debug: `padding_packing_crc_block` 'precrc' → `message_debug` 'print'

**Advantages**:
- ✅ Works immediately with your existing flowgraphs
- ✅ No file system permissions needed
- ✅ Easy to modify and test

---

## Option 2: Install to GRC Hierarchical Block Directory (System-wide)

**Location**: `/Users/charleshood/.local/state/gnuradio/`

**Setup Steps**:

1. Copy the file to the GRC hierarchical block directory:
   ```bash
   cp debug_packet_rxtx/padding_packing_crc_block.py ~/.local/state/gnuradio/
   ```

2. Ensure the directory exists:
   ```bash
   mkdir -p ~/.local/state/gnuradio
   ```

3. Restart GNU Radio Companion

**Usage in GRC**:

Same as Option 1, but the block will be available to all flowgraphs automatically.

**Advantages**:
- ✅ Available to all GRC flowgraphs
- ✅ No need to import path manipulation

---

## Option 3: Create as a Proper GRC Block (Advanced)

To make it appear in the GRC block library with a YAML file:

1. **Create YAML file**: `padding_packing_crc_block.block.yml`
   ```yaml
   id: padding_packing_crc_block
   label: Padding, Packing, and CRC Block
   category: '[Custom]'
   
   templates:
     imports: |
       from padding_packing_crc_block import padding_packing_crc_block
     make: padding_packing_crc_block()
   
   inputs:
   - domain: message
     id: in
   
   outputs:
   - domain: message
     id: out
   - domain: message
     id: precrc
     optional: True
   ```

2. **Install locations**:
   - Python file: `~/.local/state/gnuradio/padding_packing_crc_block.py`
   - YAML file: `~/.local/state/gnuradio/padding_packing_crc_block.block.yml` (or system install path)

3. **System install path** (if using system-wide GNU Radio):
   ```bash
   # Python file
   cp padding_packing_crc_block.py /opt/homebrew/Cellar/gnuradio/3.10.12.0_4/lib/python3.13/site-packages/
   
   # YAML file (create directory if needed)
   mkdir -p /opt/homebrew/Cellar/gnuradio/3.10.12.0_7/share/gnuradio/grc/blocks
   cp padding_packing_crc_block.block.yml /opt/homebrew/Cellar/gnuradio/3.10.12.0_7/share/gnuradio/grc/blocks
   ```

**Advantages**:
- ✅ Appears in GRC block library
- ✅ Drag-and-drop interface
- ✅ Full GUI integration

---

## Recommended Approach

For your current workflow, **Option 1** (keep in packet directory) is recommended because:

1. Your GRC files already use `hier_block_src_path: '.:'` (current directory)
2. It's the simplest and most portable
3. Easy to modify during development
4. No system-wide installation needed

## Verification

To verify the block can be imported:

```bash
cd debug_packet_rxtx
python3 -c "from padding_packing_crc_block import padding_packing_crc_block; print('✓ Block imported successfully')"
```

---

## File Structure (Current)

```
packet/debug_packet_rxtx/
├── padding_packing_crc_block.py  ← Your new block (keep here for Option 1)
├── packet_rx.py
├── packet_tx.py
├── packet_loopback_hier.py
└── ...
```

---

## Quick Reference: Using in Python Flowgraph

```python
from padding_packing_crc_block import padding_packing_crc_block

class my_flowgraph(gr.top_block):
    def __init__(self):
        # ... other blocks ...
        
        # Add padding, packing, and CRC block
        self.blocks_padding_crc = padding_packing_crc_block()
        
        # Connect
        self.msg_connect((self.fec_async_decoder_0, 'out'), 
                         (self.blocks_padding_crc, 'in'))
        self.msg_connect((self.blocks_padding_crc, 'out'), 
                         (self.digital_crc32_async_bb_0, 'in'))
        # Optional: Connect precrc port for debugging
        self.msg_connect((self.blocks_padding_crc, 'precrc'), 
                         (self.message_debug_0, 'print'))
```

---

## How It Works

1. **Receives unpacked bits** from FEC decoder (typically 190 bits for a 24-byte packet)
2. **Calculates padding needed** to reach byte boundary (typically 2 bits)
3. **Tries all possible padding patterns** (2^padding_needed, typically 4 patterns: 00, 01, 10, 11)
4. **For each pattern**:
   - Pads the unpacked bits
   - Packs into bytes (8 bits per byte, MSB first)
   - Computes CRC-32 on data portion (first 20 bytes)
   - Compares with received CRC (last 4 bytes)
5. **Selects the pattern that makes CRC pass**
6. **Outputs the validated data**, or prints failure message if all patterns fail

## Error Messages

If all CRC patterns fail, the block prints:
```
[PaddingPackingCrc] ERROR: CRC validation failed for all 4 padding patterns
[PaddingPackingCrc] Input: 190 bits, needed 2 padding bits
[PaddingPackingCrc] Packet sequence: <seq_number>
```

This indicates a more serious problem (e.g., data corruption, incorrect packet size, or FEC decoding error).

