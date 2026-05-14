# Padding, Packing, and CRC Block

## The Root Problem

The FEC encoder/decoder chain loses 2 bits due to byte alignment truncation:

1. **TX Side (Encoding)**:
   - Input: 24 bytes (192 bits) = 20 bytes data + 4 bytes CRC
   - FEC encoder adds 6 termination bits → 198 bits
   - Encodes at rate 1/2 → 396 bits (49.5 bytes)
   - **Problem**: GNU Radio's `fec.async_encoder` truncates to whole bytes → 392 bits (49 bytes)
   - **Result**: 4 bits lost from encoded output

2. **RX Side (Decoding)**:
   - FEC decoder receives 392 bits (49 bytes)
   - Decodes at rate 1/2 → 196 bits
   - Removes 6 termination bits → 190 bits
   - **Problem**: Should be 192 bits, but we're missing 2 bits
   - **Result**: CRC validation fails because the data is incomplete

## The Temporary Solution

The `padding_packing_crc_block` tries all possible bit patterns for the 2 missing bits and uses CRC validation to find the correct one:

1. **Receives**: 190 unpacked bits from FEC decoder
2. **Calculates**: Needs 2 bits to reach 192 bits (24 bytes)
3. **Tries all 4 patterns**: `00`, `01`, `10`, `11`
4. **For each pattern**:
   - Pads the 190 bits with the 2-bit pattern
   - Packs into 24 bytes (192 bits)
   - Computes CRC-32 on first 20 bytes
   - Compares with received CRC (last 4 bytes)
5. **Selects**: The pattern that makes CRC pass
6. **Outputs**: 24 bytes with valid CRC, or prints error if all patterns fail

## Implementation

**File**: `padding_packing_crc_block.py`

**Usage in `packet_rx.py`**:
```python
from padding_packing_crc_block import padding_packing_crc_block

# In packet_rx.__init__():
self.blocks_padding = padding_packing_crc_block()

# Connections:
self.msg_connect((self.fec_async_decoder_0, 'out'), (self.blocks_padding, 'in'))
self.msg_connect((self.blocks_padding, 'out'), (self.digital_crc32_async_bb_0, 'in'))
```

**Ports**:
- `in`: Unpacked bits from FEC decoder (190 bits)
- `out`: Packed bytes with valid CRC (24 bytes)
- `precrc`: Debug output showing data before CRC validation

**Error Handling**:
If all 4 CRC patterns fail, the block prints:
```
[PaddingPackingCrc] ERROR: CRC validation failed for all 4 padding patterns
[PaddingPackingCrc] Input: 190 bits, needed 2 padding bits
[PaddingPackingCrc] Packet sequence: <seq>
```

This indicates data corruption or a more serious FEC decoding error.

