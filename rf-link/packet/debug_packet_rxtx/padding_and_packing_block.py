# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Hierarchical Block
# Title: Padding and Packing Block
# Description: Pads unpacked bits from FEC decoder and packs them into bytes for CRC checking
# GNU Radio version: 3.10.12.0

from gnuradio import gr
import pmt


class padding_and_packing_block(gr.hier_block2):
    """
    Hierarchical block that pads unpacked bits and converts them to packed bytes.
    
    This block addresses the byte-alignment issue in FEC encoding/decoding where
    termination bits can be lost due to truncation. It automatically pads input bits
    to the next byte boundary (modulo 8 = 0) before CRC checking.
    
    Input:
        - PDU message with u8vector containing unpacked bits (each byte = 1 bit, value 0 or 1)
        - Expected from FEC async decoder with packed=False
    
    Output:
        - PDU message with u8vector containing packed bytes (8 bits per byte)
        - Always byte-aligned (length divisible by 8)
        - Ready for CRC-32 checking
    
    Ports:
        - in: Input message port (unpacked bits)
        - out: Output message port (packed bytes)
        - precrc: Optional debug port (shows data before padding)
    
    The block automatically calculates padding needed to reach next byte boundary,
    ensuring output is always byte-aligned regardless of input size.
    """
    
    def __init__(self):
        """
        Initialize the padding and packing block.
        
        The block automatically pads input bits to the next byte boundary (modulo 8 = 0)
        to ensure byte-aligned output for CRC checking.
        """
        gr.hier_block2.__init__(
            self, "Padding and Packing Block",
            gr.io_signature(0, 0, 0),  # No stream I/O
            gr.io_signature(0, 0, 0),  # No stream I/O
        )
        
        # Register hierarchical message ports
        self.message_port_register_hier_in("in")
        self.message_port_register_hier_out("out")
        self.message_port_register_hier_out("precrc")  # Optional: for debugging
        
        # Create internal basic block for message processing
        self._processor = PaddingAndPackingProcessor()
        
        # Connect internal block message ports
        self.msg_connect((self, "in"), (self._processor, "in"))
        self.msg_connect((self._processor, "out"), (self, "out"))
        self.msg_connect((self._processor, "precrc"), (self, "precrc"))


class PaddingAndPackingProcessor(gr.basic_block):
    """
    Internal basic block that performs the actual padding and packing processing.
    This is wrapped by the hierarchical block for proper integration with GRC.
    """
    
    def __init__(self):
        gr.basic_block.__init__(self,
            name="PaddingAndPackingProcessor",
            in_sig=None,
            out_sig=None)
        
        # Register message ports
        self.message_port_register_in(pmt.intern("in"))
        self.message_port_register_out(pmt.intern("out"))
        self.message_port_register_out(pmt.intern("precrc"))  # Optional: for debugging
        
        # Set message handler
        self.set_msg_handler(pmt.intern("in"), self.handle_msg)
    
    def handle_msg(self, msg):
        """
        Handle incoming PDU message.
        
        Process unpacked bits from FEC decoder:
        1. Forward original message to precrc port (before padding) for debugging
        2. Check if padding is needed
        3. Pad with zero bits if necessary
        4. Pack unpacked bits into bytes (8 bits per byte, MSB first)
        5. Output packed bytes for CRC checking
        
        Expected format: PMT pair (metadata dict, u8vector)
        Input u8vector: Unpacked bits (each byte = 1 bit, value 0 or 1)
        Output u8vector: Packed bytes (8 bits per byte)
        """
        # Forward original message to precrc port (before padding) for debugging
        try:
            self.message_port_pub(pmt.intern("precrc"), msg)
        except:
            pass  # Port may not be connected, ignore
        
        # Process the message
        if pmt.is_pair(msg):
            meta = pmt.car(msg)
            data = pmt.cdr(msg)
            
            if pmt.is_u8vector(data):
                vec = list(pmt.u8vector_elements(data))
                # FEC decoder outputs unpacked bits (each byte = 1 bit, value 0 or 1)
                current_bits = len(vec)
                
                # Pad to next byte boundary (make current_bits divisible by 8)
                # For terminated convolutional codes, missing bits are termination bits (zeros)
                bits_mod_8 = current_bits % 8
                if bits_mod_8 != 0:
                    padding_needed = 8 - bits_mod_8
                    vec.extend([0x00] * padding_needed)
                
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
                
                # Create output PDU with packed bytes
                packed = pmt.init_u8vector(len(packed_bytes), packed_bytes)
                output_msg = pmt.cons(meta, packed)

                print(f"[Padding Block] Packed message: {output_msg}")
                self.message_port_pub(pmt.intern("out"), output_msg)
            else:
                # Not a u8vector, pass through unchanged
                raise ValueError(f"[Padding Block] ERROR: Not a u8vector: {data}")
        else:
            # Not a PDU pair, pass through unchanged
            raise ValueError(f"[Padding Block] ERROR: Not a PDU pair: {msg}")

# For compatibility and direct instantiation
PaddingAndPackingBlock = padding_and_packing_block

