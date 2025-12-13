# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Burst to Stream
# Description: Pads tagged stream packets to fixed buffer size (based on gr-foo pad_tagged_stream)
# GNU Radio version: 3.10.12.0

from gnuradio import gr
from gnuradio import blocks
import numpy
import pmt


class burst_to_stream(gr.hier_block2):
    """
    Hierarchical block that pads tagged stream packets to a fixed buffer size.
    
    Based on the gr-foo pad_tagged_stream implementation:
    https://github.com/bastibl/gr-foo/blob/maint-3.10/lib/pad_tagged_stream_impl.cc
    
    This block takes tagged stream packets and pads them to a fixed buffer size,
    ensuring continuous output stream for SDR hardware that requires fixed-size buffers.
    
    Input:
        - Tagged stream of complex samples (from packet_tx output port 0)
        - Tag key: 'packet_len' (standard for packet transmissions)
    
    Output:
        - Continuous stream of complex samples with fixed-size buffers
        - Each input packet is padded to buffer_size samples with random noise (or zeros)
    
    Parameters:
        - buffer_size: Fixed output size for each packet (default: 10000)
        - len_tag_name: Tag key to identify packet boundaries (default: 'packet_len')
        - noise_std: Standard deviation of random noise for padding (default: 0.01)
                    Set to 0.0 to use zeros instead of noise
    """
    
    def __init__(self, buffer_size=10000, len_tag_name='packet_len', noise_std=0.01):
        """
        Initialize the burst to stream block.
        
        Args:
            buffer_size: Fixed output size for each packet (default: 10000)
            len_tag_name: Tag key to identify packet boundaries (default: 'packet_len')
            noise_std: Standard deviation of random noise for padding (default: 0.01)
                      Set to 0.0 to use zeros instead of noise
        """
        gr.hier_block2.__init__(
            self, "Burst to Stream",
            gr.io_signature(1, 1, gr.sizeof_gr_complex*1),  # 1 input stream
            gr.io_signature(1, 1, gr.sizeof_gr_complex*1),  # 1 output stream
        )
        
        self.buffer_size = buffer_size
        self.len_tag_name = len_tag_name
        self.noise_std = noise_std
        
        # Create internal pad tagged stream block
        self._padder = PadTaggedStream(buffer_size, len_tag_name, noise_std)
        
        # Connect internal block
        self.connect((self, 0), (self._padder, 0))
        self.connect((self._padder, 0), (self, 0))
    
    def get_buffer_size(self):
        """
        Get the current buffer size (fixed output size for each packet).
        
        Returns:
            int: Buffer size
        """
        return self.buffer_size
    
    def set_buffer_size(self, buffer_size):
        """
        Update the buffer size (fixed output size for each packet).
        
        Args:
            buffer_size: New buffer size
        """
        self.buffer_size = buffer_size
        self._padder.buf_len = buffer_size
    
    def set_noise_std(self, noise_std):
        """
        Update the noise standard deviation for padding.
        
        Args:
            noise_std: New noise standard deviation (0.0 for zeros)
        """
        self.noise_std = noise_std
        self._padder.noise_std = noise_std
    
    def get_len_tag_name(self):
        """
        Get the current length tag name.
        
        Returns:
            str: Length tag name
        """
        return self.len_tag_name
    
    def set_len_tag_name(self, len_tag_name):
        """
        Update the length tag name.
        
        Args:
            len_tag_name: New length tag name
        """
        self.len_tag_name = len_tag_name
        self._padder.len_tag = pmt.intern(len_tag_name)


class PadTaggedStream(gr.basic_block):
    """
    Internal block that pads tagged stream packets to a fixed buffer size.
    
    Based on pad_tagged_stream_impl from gr-foo:
    https://github.com/bastibl/gr-foo/blob/maint-3.10/lib/pad_tagged_stream_impl.cc
    
    This block processes tagged stream packets one at a time, padding each
    to a fixed buffer_size. It mimics the behavior of a tagged_stream_block
    but uses basic_block for Python compatibility.
    """
    
    def __init__(self, buffer_size, len_tag_name, noise_std=0.01):
        """
        Initialize the pad tagged stream block.
        
        Args:
            buffer_size: Fixed output size for each packet
            len_tag_name: Tag key to identify packet boundaries
            noise_std: Standard deviation of random noise for padding (default: 0.01)
                      Set to 0.0 to use zeros instead of noise
        """
        gr.basic_block.__init__(
            self,
            name="PadTaggedStream",
            in_sig=[numpy.complex64],
            out_sig=[numpy.complex64]
        )
        
        self.buf_len = buffer_size
        self.len_tag = pmt.intern(len_tag_name)
        self.noise_std = noise_std
        self.debug = False  # Enable debug output
        
        # State tracking for current packet processing
        self.current_packet_length = 0  # Length of current packet from tag
        self.current_packet_produced = 0  # Samples already produced for current packet
        self.current_packet_consumed = 0  # Samples consumed from input for current packet
        self.state = 'waiting_tag'  # 'waiting_tag' or 'processing_packet'
        
        # Packet counter for debug output
        self.packet_count = 0
        
        # Set relative rate - we output fixed size packets
        # The actual rate depends on input packet sizes, but we'll handle it dynamically
        self.set_relative_rate(1.0)
        
        # Set minimum output buffer to avoid blocking
        # (buffer_size*2 as in C++ implementation)
        self.set_min_output_buffer(buffer_size * 2)
        
        # Don't auto-propagate tags - we'll handle them manually
        self.set_tag_propagation_policy(gr.TPP_DONT)
    
    def forecast(self, noutput_items, ninputs):
        """
        Forecast how many input items are needed to produce noutput_items.
        
        For tagged stream processing, we need enough input to:
        - Find the next packet tag
        - Process the packet (which might span multiple calls)
        We request a reasonable amount that won't exceed buffer limits.
        """
        # Request enough input to potentially find a tag and process a packet
        # But don't request more than what's reasonable (max 8192 items)
        # We'll process in chunks and handle partial packets
        requested = min(max(noutput_items, 4096), 8192)
        return [requested]
    
    def general_work(self, input_items, output_items):
        """
        Process tagged packets: for each packet, copy input and pad with zeros.
        
        Algorithm:
        1. Look for packet_len tags to identify packet boundaries
        2. For each packet, output exactly buffer_size samples:
           - Copy packet data (up to buffer_size)
           - Pad remainder with zeros
        
        Args:
            input_items: List of input buffers
            output_items: List of output buffers
            
        Returns:
            int: Number of output items produced
        """
        in0 = input_items[0]
        out = output_items[0]
        ninput = len(in0)
        noutput = len(out)
        
        consumed = 0
        produced = 0
        
        # Get current absolute read position
        current_abs_read = self.nitems_read(0)
        
        # Process while we have input and output space
        while consumed < ninput and produced < noutput:
            if self.state == 'waiting_tag':
                # Look for packet_len tags
                tags = self.get_tags_in_range(0, current_abs_read + consumed, 
                                              current_abs_read + ninput)
                packet_tags = [t for t in tags if pmt.eq(t.key, self.len_tag)]
                
                if packet_tags:
                    # Found a packet tag - start processing new packet
                    tag = packet_tags[0]
                    tag_offset = tag.offset - current_abs_read
                    
                    # Get packet length from tag
                    if pmt.is_integer(tag.value):
                        self.current_packet_length = pmt.to_long(tag.value)
                        self.current_packet_produced = 0
                        self.current_packet_consumed = 0
                        self.state = 'processing_packet'
                        self.packet_count += 1
                        
                        # Debug output: show original packet size and output buffer size
                        if self.debug:
                            padding_needed = max(0, self.buf_len - self.current_packet_length)
                            truncation_needed = max(0, self.current_packet_length - self.buf_len)
                            print(f"\n{'='*70}")
                            print(f"[PadTaggedStream] Packet #{self.packet_count}: "
                                  f"Original size={self.current_packet_length} samples, "
                                  f"Output buffer={self.buf_len} samples, "
                                  f"Padding={padding_needed} samples, "
                                  f"Truncation={truncation_needed} samples")
                            print(f"{'='*70}")
                        
                        # Skip to tag position
                        consumed = tag_offset
                        continue
                    else:
                        # Invalid tag, skip it
                        consumed = tag_offset + 1
                        continue
                else:
                    # No tag found yet, consume a small amount and wait
                    consumed += min(1024, ninput - consumed)
                    break
            
            elif self.state == 'processing_packet':
                # We're processing a packet - need to output exactly buf_len samples
                # First, copy packet data if we haven't finished the packet
                if self.current_packet_consumed < self.current_packet_length:
                    # Copy packet data
                    packet_remaining = self.current_packet_length - self.current_packet_consumed
                    packet_to_copy = min(packet_remaining, ninput - consumed, 
                                        self.buf_len - self.current_packet_produced,
                                        noutput - produced)
                    
                    if packet_to_copy > 0:
                        out[produced:produced + packet_to_copy] = in0[consumed:consumed + packet_to_copy]
                        
                        # Debug: Show last N samples of packet when we finish copying it
                        if self.debug and (self.current_packet_consumed + packet_to_copy >= self.current_packet_length):
                            # We just finished copying the packet
                            samples_before_end = min(32, self.current_packet_produced + packet_to_copy)
                            if samples_before_end > 0:
                                last_packet_samples = out[max(0, produced + packet_to_copy - samples_before_end):produced + packet_to_copy]
                                print(f"[PadTaggedStream] Packet #{self.packet_count} END (last {len(last_packet_samples)} samples of packet):")
                                for i in range(0, len(last_packet_samples), 8):
                                    chunk = last_packet_samples[i:i+8]
                                    real_str = ' '.join(f'{s.real:+.4f}' for s in chunk)
                                    imag_str = ' '.join(f'{s.imag:+.4f}' for s in chunk)
                                    mag_str = ' '.join(f'{abs(s):.4f}' for s in chunk)
                                    offset = len(last_packet_samples) - len(chunk) - i
                                    print(f"      [{offset:4d}:{offset+len(chunk)-1:4d}] Mag: {mag_str}")
                                    print(f"      [{offset:4d}:{offset+len(chunk)-1:4d}] Real: {real_str}")
                                    print(f"      [{offset:4d}:{offset+len(chunk)-1:4d}] Imag: {imag_str}")
                        
                        consumed += packet_to_copy
                        produced += packet_to_copy
                        self.current_packet_consumed += packet_to_copy
                        self.current_packet_produced += packet_to_copy
                
                # Now pad with noise (or zeros) if needed to reach buf_len
                if self.current_packet_produced < self.buf_len:
                    padding_needed = self.buf_len - self.current_packet_produced
                    padding_to_output = min(padding_needed, noutput - produced)
                    
                    if padding_to_output > 0:
                        if self.noise_std > 0.0:
                            # Generate random complex Gaussian noise
                            # Real and imaginary parts are independent Gaussian with std=noise_std
                            noise_real = numpy.random.randn(padding_to_output).astype(numpy.float32) * self.noise_std
                            noise_imag = numpy.random.randn(padding_to_output).astype(numpy.float32) * self.noise_std
                            out[produced:produced + padding_to_output] = noise_real + 1j * noise_imag
                        else:
                            # Use zeros if noise_std is 0.0
                            out[produced:produced + padding_to_output] = 0
                        
                        produced += padding_to_output
                        self.current_packet_produced += padding_to_output
                
                # Check if packet is complete (we've produced buf_len samples)
                if self.current_packet_produced >= self.buf_len:
                    # Packet complete - reset for next packet
                    # Warn if input packet was longer than buffer
                    if self.current_packet_length > self.buf_len:
                        if self.debug:
                            print(f"[PadTaggedStream] Packet #{self.packet_count} COMPLETE: "
                                  f"WARNING - Input packet ({self.current_packet_length} samples) "
                                  f"longer than buffer ({self.buf_len} samples), truncation occurred")
                    elif self.debug:
                        padding_added = self.buf_len - self.current_packet_length
                        print(f"[PadTaggedStream] Packet #{self.packet_count} COMPLETE: "
                              f"Original={self.current_packet_length} samples, "
                              f"Output={self.current_packet_produced} samples, "
                              f"Padding added={padding_added} samples")
                    
                    # Also warn if we didn't consume all packet data (shouldn't happen)
                    if self.current_packet_consumed < self.current_packet_length:
                        # Skip remaining packet data
                        skip_needed = self.current_packet_length - self.current_packet_consumed
                        consumed += min(skip_needed, ninput - consumed)
                        if self.debug:
                            print(f"[PadTaggedStream] Packet #{self.packet_count} WARNING: "
                                  f"Did not consume all input data ({self.current_packet_consumed}/{self.current_packet_length} samples)")
                    
                    self.state = 'waiting_tag'
                    self.current_packet_length = 0
                    self.current_packet_produced = 0
                    self.current_packet_consumed = 0
        
        # Consume input and return output
        self.consume(0, consumed)
        return produced


# For compatibility and direct instantiation
BurstToStream = burst_to_stream
PadTaggedStreamBlock = PadTaggedStream
