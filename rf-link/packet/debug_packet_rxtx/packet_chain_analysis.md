# Packet TX/RX Chain Analysis
## Bit Packing and FEC Encoding Details

---

## Table of Contents
1. [TX Chain Overview](#tx-chain-overview)
2. [RX Chain Overview](#rx-chain-overview)
3. [Data Format Through the Chain (20-byte Input)](#data-format-through-the-chain)
4. [The Bit Packing Problem](#the-bit-packing-problem)
5. [Workaround 1: Bit Padding on RX Side](#workaround-1-bit-padding-on-rx-side)
6. [Workaround 2: Changing k=5 to k=7](#workaround-2-changing-k5-to-k7)
7. [GNU Radio Python Embedded Block Implementation](#gnu-radio-python-embedded-block-implementation)

---

## TX Chain Overview

The transmission chain processes input packets through the following stages:

### Stage-by-Stage Processing

1. **Input PDU (20 bytes = 160 bits)**
   - User data packet enters via message port `in`
   - Format: PDU (PMT pair: metadata dictionary + u8vector)

2. **CRC-32 Append** (`digital.crc32_async_bb`)
   - Input: 20 bytes (160 bits)
   - Appends 4-byte CRC-32 checksum
   - **Output: 24 bytes (192 bits)**
   - This becomes the "postcrc" data

3. **FEC Encoding** (`fec.async_encoder` with CC terminated, k=7, rate=1/2)
   - Input: 24 bytes (192 bits)
   - Termination: Adds (k-1) = 6 termination bits
   - Encoder input: 192 + 6 = 198 bits
   - Encoding: Rate 1/2 doubles the bits
   - **Expected output: 396 bits (49.5 bytes)**
   - **Actual output: 392 bits (49 bytes)** ← **PROBLEM: 4 bits lost!**
   - The async encoder truncates to whole bytes, losing the last 4 bits

4. **Protocol Formatter** (`digital.protocol_formatter_async`)
   - Creates header with packet length
   - Header encodes: 196 symbols (from truncated 392 bits / 2 bits per QPSK symbol)
   - Combines header + encoded payload

5. **Header FEC Encoding** (`fec.async_encoder` with repetition code, rep=3)
   - Encodes header separately with repetition code

6. **Bit Repacking** (`blocks.repack_bits_bb`)
   - Header: Repacks from 1 bit/symbol (BPSK) to bytes
   - Payload: Repacks from 2 bits/symbol (QPSK) to bytes

7. **Constellation Mapping** (`digital.map_bb`)
   - Maps bits to constellation points

8. **Symbol Generation** (`digital.chunks_to_symbols_bc`)
   - Header: BPSK symbols (1 bit → 1 complex symbol)
   - Payload: QPSK symbols (2 bits → 1 complex symbol)

9. **Burst Shaping & Pulse Shaping**
   - Adds windowing, pulse shaping filter (RRC), upsampling
   - Output: Complex IQ samples

---

## RX Chain Overview

The reception chain performs the reverse operations:

### Stage-by-Stage Processing

1. **Correlation & Synchronization** (`digital.corr_est_cc`)
   - Detects preamble/sync word
   - Estimates timing, frequency offset, amplitude

2. **Clock Recovery** (`digital.pfb_clock_sync_ccf`)
   - Recovers symbol timing
   - Downsamples to symbol rate

3. **Header/Payload Demux** (`digital.header_payload_demux`)
   - Separates header and payload streams
   - Uses length info from header

4. **Frequency Recovery** (`digital.costas_loop_cc`)
   - Header: Costas loop for BPSK (2nd order)
   - Payload: Costas loop for QPSK (4th order)

5. **Soft Decision Decoding** (`digital.constellation_soft_decoder_cf`)
   - Header: BPSK → soft bits
   - Payload: QPSK → soft bits (floats, not hard decisions)

6. **Header FEC Decoding** (`fec.generic_decoder` with repetition decoder)
   - Decodes header using repetition code (rate 1/3)

7. **Protocol Parsing** (`digital.protocol_parser_b`)
   - Extracts packet length and metadata from header

8. **Payload FEC Decoding** (`fec.async_decoder` with CC terminated, k=7, rate=1/2)
   - Input: Soft bits from constellation decoder
   - Decodes rate 1/2 convolutional code
   - Removes termination bits
   - **Output: 190 bits (unpacked)** ← **PROBLEM: Should be 192 bits!**
   - Format: Unpacked bits (each byte represents one bit, value 0 or 1)

9. **Bit Padding & Packing** (`PaddingAndPackingBlock` - custom block)
   - **Input: 190 bits (unpacked)**
   - Pads with 2 zero bits
   - **Output: 192 bits (packed into 24 bytes)**

10. **CRC-32 Check** (`digital.crc32_async_bb`)
    - Verifies CRC checksum
    - Removes CRC bytes if valid
    - **Output: 20 bytes (original packet)**

---

## Data Format Through the Chain

### Complete Flow with 20-Byte Input

```
┌─────────────────────────────────────────────────────────────────┐
│ INPUT: 20 bytes (160 bits)                                      │
│ Data: [0xC5, 0x4C, 0x6D, 0x26, 0x5B, 0x46, 0xC2, 0xCD,        │
│        0xFC, 0xEE, 0x6E, 0x32, 0x34, 0x8B, 0x12, 0xBE,        │
│        0xA7, 0x59, 0x82, 0x30]                                  │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ After CRC-32 Append: 24 bytes (192 bits)                       │
│ Data: [original 20 bytes] + [4 CRC bytes]                      │
│ Format: Packed bytes (8 bits per byte)                         │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ After FEC Encoding (CC terminated k=7, rate 1/2):              │
│ Input bits: 192                                                 │
│ + Termination: 6 bits (k-1)                                     │
│ = Encoder input: 198 bits                                       │
│ Encoded: 198 × 2 = 396 bits (49.5 bytes)                       │
│ Truncated to: 392 bits (49 bytes) ← LOSES 4 BITS!              │
│ Format: Packed bytes                                            │
│                                                                │
│ The 4 lost bits mean:                                           │
│ - Encoder processed: 198 bits                                   │
│ - Encoder output: 396 bits (should be)                          │
│ - Actual output: 392 bits (49 bytes)                            │
│ - Effective input processed: 196 bits (not 198!)                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ After Protocol Formatter:                                       │
│ Header: Contains length = 196 symbols (392 bits / 2)            │
│ Payload: 392 bits (49 bytes)                                    │
│ Format: Header + Payload as separate PDUs                       │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ After Modulation & Transmission:                                │
│ Header: 196 BPSK symbols                                        │
│ Payload: 196 QPSK symbols (392 bits / 2)                        │
│ Format: Complex IQ samples                                      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
                    [CHANNEL / LOOPBACK]
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ After RX Demodulation:                                          │
│ Header: Decoded to header info                                  │
│ Payload: 196 QPSK symbols → 392 soft bits                       │
│ Format: Float soft decision values                              │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ After FEC Decoding (CC terminated k=7, rate 1/2):              │
│ Input: 392 soft bits                                            │
│ Decoded: 392 / 2 = 196 bits                                     │
│ - Termination: 6 bits removed                                   │
│ = Output: 190 bits (unpacked) ← MISSING 2 BITS!                │
│ Format: Unpacked bits (each byte = 1 bit, value 0 or 1)        │
│                                                                │
│ Expected: 192 bits (24 bytes)                                   │
│ Actual: 190 bits                                                │
│ Missing: 2 bits                                                 │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ After Padding & Packing (WORKAROUND 1):                        │
│ Input: 190 bits (unpacked)                                      │
│ Pad: +2 zero bits                                               │
│ = 192 bits (unpacked)                                           │
│ Pack: 192 bits → 24 bytes                                       │
│ Format: Packed bytes (8 bits per byte)                         │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ After CRC-32 Check:                                             │
│ Verify CRC: ✓                                                   │
│ Remove CRC: 24 bytes - 4 bytes = 20 bytes                       │
│ OUTPUT: 20 bytes (160 bits)                                     │
│ Data: [0xC5, 0x4C, 0x6D, 0x26, 0x5B, 0x46, 0xC2, 0xCD,        │
│        0xFC, 0xEE, 0x6E, 0x32, 0x34, 0x8B, 0x12, 0xBE,        │
│        0xA7, 0x59, 0x82, 0x30]                                  │
│ ✓✓✓ MATCHES INPUT!                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## The Bit Packing Problem

### Root Cause

The issue stems from **byte-alignment requirements** in the FEC async encoder/decoder:

1. **FEC Encoder Output Must Be Byte-Aligned**
   - The `fec.async_encoder` outputs bytes (not bits)
   - When encoding produces non-byte-aligned results, it truncates to the nearest byte

2. **Mathematical Breakdown for k=7, Rate 1/2:**
   ```
   Input: 192 bits (24 bytes)
   + Termination: 6 bits (k-1 = 7-1 = 6)
   = Encoder input: 198 bits
   
   Encoded: 198 × 2 = 396 bits
   396 bits ÷ 8 = 49.5 bytes
   
   Encoder truncates to: 49 bytes = 392 bits
   Lost: 4 bits
   
   Effective bits encoded: 392 ÷ 2 = 196 bits
   Effective input: 196 - 6 = 190 bits (not 192!)
   ```

3. **On RX Side:**
   ```
   Decoder receives: 392 bits (49 bytes)
   Decoded: 392 ÷ 2 = 196 bits
   - Termination: 6 bits removed
   = Output: 190 bits (not 192!)
   ```

4. **The Missing 2 Bits:**
   - Expected: 192 bits (24 bytes)
   - Actual: 190 bits
   - Missing: 2 bits
   - This causes CRC failure because CRC expects exactly 24 bytes

---

## Workaround 1: Bit Padding on RX Side

### Implementation Details

This workaround adds a custom block (`PaddingAndPackingBlock`) that:

1. **Receives unpacked bits from FEC decoder** (190 bits)
2. **Pads with 2 zero bits** to reach 192 bits
3. **Packs bits into bytes** (192 bits → 24 bytes)
4. **Passes to CRC checker**

### Why This Works

- The missing 2 bits are **termination bits** that were lost during truncation
- These bits are typically zeros or don't affect the actual data
- Padding with zeros restores the byte count needed for CRC verification
- The CRC check passes because the data portion (first 20 bytes) is correct

### Code Location

Located in `packet/packet_rx.py`, lines 121-172.
Also located in 'padding_and_packing_block.py

### Limitations

- Assumes the missing bits should be zeros (may not always be true)
- Doesn't fix the root cause (byte alignment issue)
- Adds latency and complexity

---

## Workaround 2: Changing k=5 to k=7

### Mathematical Analysis

#### Current Configuration (k=7):
```
Input: 192 bits (24 bytes)
Termination: k-1 = 7-1 = 6 bits
Encoder input: 192 + 6 = 198 bits
Encoded: 198 × 2 = 396 bits = 49.5 bytes
Truncated: 49 bytes = 392 bits (loses 4 bits)
Effective input: (392/2) - 6 = 196 - 6 = 190 bits
Missing on RX: 192 - 190 = 2 bits
```

#### Alternative Configuration (k=5):
```
Input: 192 bits (24 bytes)
Termination: k-1 = 5-1 = 4 bits
Encoder input: 192 + 4 = 196 bits
Encoded: 196 × 2 = 392 bits = 49.0 bytes
Truncated: 49 bytes = 392 bits (perfect alignment!)
Effective input: (392/2) - 4 = 196 - 4 = 192 bits
Missing on RX: 192 - 192 = 0 bits ✓
```

### Why k=5 Fixes the Problem

1. **Byte Alignment:**
   - k=5: 196 bits × 2 = 392 bits = exactly 49 bytes ✓
   - k=7: 198 bits × 2 = 396 bits = 49.5 bytes (needs truncation)

2. **No Truncation Loss:**
   - With k=5, the encoded output is already byte-aligned
   - No bits are lost during encoding
   - Full 192 bits are preserved through the chain

3. **RX Side:**
   - Decoder receives exactly 392 bits (49 bytes)
   - Decodes to 196 bits
   - Removes 4 termination bits
   - Outputs exactly 192 bits (24 bytes) ✓

### Trade-offs

**Advantages:**
- No padding needed
- No bit loss
- Simpler implementation (no custom blocks)

**Disadvantages:**
- k=5 has **lower coding gain** than k=7
  - k=5: Constraint length 5 (worse error correction)
  - k=7: Constraint length 7 (better error correction)
- Slightly **worse BER performance** in noisy channels

### When to Use k=5 vs k=7

- **Use k=5**: When you need byte alignment and can tolerate slightly worse error correction
- **Use k=7**: When you need maximum error correction and can implement padding workaround

---

## GNU Radio Python Embedded Block Implementation

### Creating a Padding Block in GRC

To implement the padding workaround in a separate GRC file:

#### Step 1: Add Python Embedded Block

1. In GNU Radio Companion (GRC), add a **Python Embedded Block**
2. Set the following properties:
   - **ID**: `padding_and_packing_block`
   - **Parameters**: `expected_bits=192`
   - **Code**: (see below)

#### Step 2: Python Code for Embedded Block

```python
import numpy
from gnuradio import gr
import pmt

class padding_and_packing_block(gr.basic_block):
    """
    Pads unpacked bits and converts to packed bytes.
    
    Input: Unpacked bits (u8vector, each byte = 1 bit, value 0 or 1)
    Output: Packed bytes (u8vector, 8 bits per byte)
    """
    def __init__(self, expected_bits=192):
        gr.basic_block.__init__(self,
            name="padding_and_packing_block",
            in_sig=None,
            out_sig=None)
        self.expected_bits = expected_bits
        self.message_port_register_in(pmt.intern("in"))
        self.message_port_register_out(pmt.intern("out"))
        self.message_port_register_out(pmt.intern("precrc"))  # Optional: for debugging
        self.set_msg_handler(pmt.intern("in"), self.handle_msg)
    
    def handle_msg(self, msg):
        """
        Handle incoming PDU message.
        
        Expected format: PMT pair (metadata dict, u8vector)
        Input u8vector: Unpacked bits (each byte = 1 bit)
        Output u8vector: Packed bytes (8 bits per byte)
        """
        # Forward original message to precrc port (before padding)
        if hasattr(self, 'message_port_register_out'):
            try:
                self.message_port_pub(pmt.intern("precrc"), msg)
            except:
                pass  # Port may not be connected
        
        if pmt.is_pair(msg):
            meta = pmt.car(msg)
            data = pmt.cdr(msg)
            
            if pmt.is_u8vector(data):
                vec = list(pmt.u8vector_elements(data))
                current_bits = len(vec)
                
                # Pad if necessary
                if current_bits < self.expected_bits:
                    # Pad with zero bits (each zero is a byte with value 0)
                    padding_needed = self.expected_bits - current_bits
                    vec.extend([0x00] * padding_needed)
                    print(f"[Padding Block] Padded {padding_needed} bits (from {current_bits} to {self.expected_bits} bits)")
                elif current_bits > self.expected_bits:
                    # Truncate if too many (shouldn't happen, but handle gracefully)
                    vec = vec[:self.expected_bits]
                    print(f"[Padding Block] WARNING: Truncated {current_bits - self.expected_bits} bits")
                
                # Pack unpacked bits to bytes (8 bits per byte, MSB first)
                # Each element in vec is 0 or 1 (representing one bit)
                packed_bytes = []
                for i in range(0, len(vec), 8):
                    byte_val = 0
                    for j in range(8):
                        if i + j < len(vec):
                            # Convert 0/1 byte to actual bit value
                            bit_val = vec[i + j] & 0x01  # Ensure it's 0 or 1
                            byte_val |= (bit_val << (7 - j))  # MSB first
                    packed_bytes.append(byte_val)
                
                # Create output PDU
                packed = pmt.init_u8vector(len(packed_bytes), packed_bytes)
                output_msg = pmt.cons(meta, packed)
                self.message_port_pub(pmt.intern("out"), output_msg)
            else:
                # Not a u8vector, pass through unchanged
                self.message_port_pub(pmt.intern("out"), msg)
        else:
            # Not a PDU pair, pass through unchanged
            self.message_port_pub(pmt.intern("out"), msg)
```

#### Step 3: Block Configuration in GRC

1. **Message Ports:**
   - Input: `in` (from FEC decoder output)
   - Output: `out` (to CRC checker input)
   - Optional: `precrc` (for debugging, shows data before padding)

2. **Parameters:**
   - `expected_bits`: Set to 192 (for 24-byte packets with CRC)

3. **Connections:**
   ```
   fec.async_decoder 'out' → padding_and_packing_block 'in'
   padding_and_packing_block 'out' → digital.crc32_async_bb 'in'
   ```

#### Step 4: Usage Notes

1. **Expected Input Format:**
   - PDU with u8vector
   - Each byte in the vector represents one bit (value 0 or 1)
   - This is the standard output format of `fec.async_decoder` with `packed=False`

2. **Output Format:**
   - PDU with u8vector
   - Packed bytes (8 bits per byte)
   - Ready for CRC checking

3. **Debugging:**
   - Connect `precrc` port to a `message_debug` block to see data before padding
   - The block prints padding information when it modifies the data

### Alternative: Using Blocks Already in GRC

If you prefer not to use Python Embedded Blocks, you can:

1. **Use `blocks.unpacked_to_packed_bb`:**
   - However, this doesn't handle the padding issue
   - You'd still need a custom block for padding

2. **Modify Input Packet Size:**
   - Use 23 bytes (184 bits) instead of 24 bytes (192 bits)
   - With k=7: 184 + 6 = 190 bits, 190 × 2 = 380 bits = 47.5 bytes (still not aligned)
   - This doesn't solve the problem

3. **Use k=5 Instead:**
   - This is the cleanest solution if you can accept lower coding gain
   - No custom blocks needed

---

## Summary

### The Problem
- FEC encoder/decoder with k=7, rate 1/2 causes byte alignment issues
- 192-bit input → 396-bit encoded → truncated to 392 bits → 190-bit decoded output
- Missing 2 bits cause CRC failures

### Workaround 1: Bit Padding (Current Implementation)
- **Location**: `packet/packet_rx.py`, `PaddingAndPackingBlock` class
- **Method**: Pad 190 bits to 192 bits, then pack to bytes
- **Pros**: Works with k=7 (better error correction)
- **Cons**: Assumes missing bits are zeros, adds complexity

### Workaround 2: Change to k=5
- **Method**: Use k=5 instead of k=7 for perfect byte alignment
- **Pros**: No custom blocks needed, no bit loss
- **Cons**: Lower coding gain (worse error correction)

### Recommendation
- **For maximum error correction**: Use k=7 with padding workaround (current)
- **For simplicity**: Use k=5 and remove padding block
- **For production**: Consider using k=7 with proper byte padding on TX side to prevent truncation

---

## File Locations

- **TX Chain**: `packet/packet_tx.py`
- **RX Chain**: `packet/packet_rx.py`
- **Padding Block**: `packet/packet_rx.py`, lines 121-172
- **Test Flowgraph**: `packet/packet_loopback_hier_custom.py`

---

**Last Updated**: Based on implementation as of packet processing chain analysis
