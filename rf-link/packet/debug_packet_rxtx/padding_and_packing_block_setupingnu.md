# Padding and Packing Block - GNU Radio Setup Guide

## Overview
The `padding_and_packing_block.py` is a custom GNU Radio block that pads unpacked bits from FEC decoder and packs them into bytes for CRC checking.

## Option 1: Keep in Packet Directory (Recommended for Local Use)

**Location**: Keep the file in the `packet/` directory alongside your other flowgraphs.

**Usage in GRC (Python Embedded Block)**:

1. Add a **Python Embedded Block** to your flowgraph
2. Set the **ID**: `padding_block`
3. In the **Code** section, use:

```python
from padding_and_packing_block import padding_and_packing_block

def __init__(self):
    self.blocks_padding = padding_and_packing_block(expected_bits=192)
```

4. Connect the ports:
   - Input: `fec.async_decoder` 'out' → `padding_and_packing_block` 'in'
   - Output: `padding_and_packing_block` 'out' → `digital.crc32_async_bb` 'in'
   - Optional debug: `padding_and_packing_block` 'precrc' → `message_debug` 'print'

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
   cp packet/padding_and_packing_block.py ~/.local/state/gnuradio/
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

1. **Create YAML file**: `padding_and_packing_block.block.yml`
   ```yaml
   id: padding_and_packing_block
   label: Padding and Packing Block
   category: '[Custom]'
   
   templates:
     imports: |
       from padding_and_packing_block import padding_and_packing_block
     make: padding_and_packing_block(${expected_bits})
   
   parameters:
   - id: expected_bits
     label: Expected Bits
     dtype: int
     default: '192'
   
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
   - Python file: `~/.local/state/gnuradio/padding_and_packing_block.py`
   - YAML file: `~/.local/state/gnuradio/padding_and_packing_block.block.yml` (or system install path)

3. **System install path** (if using system-wide GNU Radio):
   ```bash
   # Python file
   cp padding_and_packing_block.py /opt/homebrew/Cellar/gnuradio/3.10.12.0_4/lib/python3.13/site-packages/
   
   # YAML file (create directory if needed)cd
   mkdir -p /opt/homebrew/Cellar/gnuradio/3.10.12.0_7/share/gnuradio/grc/blocks
   cp padding_and_packing_block.block.yml /opt/homebrew/Cellar/gnuradio/3.10.12.0_7/share/gnuradio/grc/blocks
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
cd packet
python3 -c "from padding_and_packing_block import padding_and_packing_block; print('✓ Block imported successfully')"
```

---

## File Structure (Current)

```
packet/
├── padding_and_packing_block.py  ← Your new block (keep here for Option 1)
├── packet_rx.py
├── packet_tx.py
├── packet_loopback_hier.py
└── ...
```

---

## Quick Reference: Using in Python Flowgraph

```python
from padding_and_packing_block import padding_and_packing_block

class my_flowgraph(gr.top_block):
    def __init__(self):
        # ... other blocks ...
        
        # Add padding block
        self.blocks_padding = padding_and_packing_block(expected_bits=192)
        
        # Connect
        self.msg_connect((self.fec_async_decoder_0, 'out'), 
                         (self.blocks_padding, 'in'))
        self.msg_connect((self.blocks_padding, 'out'), 
                         (self.digital_crc32_async_bb_0, 'in'))
```

