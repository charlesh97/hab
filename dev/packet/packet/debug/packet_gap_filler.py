# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Hierarchical Block
# Title: Packet Gap Filler
# Description: Continuous transmission with packet insertion - always transmits dummy data, inserts packets when available
# GNU Radio version: 3.10.12.0

from gnuradio import gr
from gnuradio import blocks
from gnuradio import analog
import numpy
import pmt
import logging


class packet_gap_filler(gr.hier_block2):
    """
    Hierarchical block that provides continuous transmission with packet insertion.
    
    This block is designed for SDR hardware (like HackRF) that requires continuous
    stream transmission. It always generates a continuous dummy data stream (noise),
    and asynchronously inserts packet data when packets arrive.
    
    Architecture:
    1. Continuous dummy data stream (noise source) - always running
    2. Packet input stream - async packets with tags
    3. Mux block - selects between dummy and packet data based on packet tags
    
    Input:
        - Tagged stream of complex samples (from packet_tx output port 0)
        - Tag key: 'packet_len' (standard for packet transmissions)
    
    Output:
        - Continuous stream of complex samples
        - Always transmitting dummy data, with packets inserted when available
    
    Parameters:
        - dummy_amplitude: Amplitude for noise (default: 0.01)
        - tag_key: Tag key to identify packet boundaries (default: 'packet_len')
    """
    
    def __init__(self, dummy_amplitude=0.01, tag_key='packet_len'):
        """
        Initialize the packet gap filler block.
        
        Args:
            dummy_amplitude: Amplitude for noise (default: 0.01)
            tag_key: Tag key to identify packet boundaries (default: 'packet_len')
        """
        gr.hier_block2.__init__(
            self, "Packet Gap Filler",
            gr.io_signature(1, 1, gr.sizeof_gr_complex*1),  # 1 input stream (packets)
            gr.io_signature(1, 1, gr.sizeof_gr_complex*1),  # 1 output stream (continuous)
        )
        
        self.dummy_amplitude = dummy_amplitude
        self.tag_key = tag_key
        
        # Create continuous dummy data source (noise)
        self.analog_noise_source_x_0 = analog.noise_source_c(
            analog.GR_GAUSSIAN, dummy_amplitude, 0
        )
        
        # Create packet mux block that selects between dummy and packet streams
        self._packet_mux = PacketMux(tag_key)
        
        # Connect: dummy source -> mux input 0, packet input -> mux input 1
        self.connect((self.analog_noise_source_x_0, 0), (self._packet_mux, 0))
        self.connect((self, 0), (self._packet_mux, 1))
        self.connect((self._packet_mux, 0), (self, 0))
    
    def get_dummy_amplitude(self):
        """Get the current dummy amplitude."""
        return self.dummy_amplitude
    
    def set_dummy_amplitude(self, dummy_amplitude):
        """Update the dummy amplitude."""
        self.dummy_amplitude = dummy_amplitude
        self.analog_noise_source_x_0.set_amplitude(dummy_amplitude)


class PacketMux(gr.basic_block):
    """
    Simple 2-input mux:
    - Input 0: continuous dummy (noise) stream
    - Input 1: packet tagged stream (with packet_len)
    Output dummy unless packet samples are present; when present, forward them (and their tags).
    No state machine – we just pass what is available.
    """
    
    def __init__(self, tag_key='packet_len'):
        gr.basic_block.__init__(
            self,
            name="PacketMux",
            in_sig=[numpy.complex64, numpy.complex64],  # dummy stream, packet stream
            out_sig=[numpy.complex64]
        )
        
        self.tag_key = pmt.intern(tag_key)
        self.debug_enabled = True
        self.samples_output_dummy = 0
        self.samples_output_packet = 0
        self.last_debug_output = 0
        self.debug_interval = 100000
        self.logger = logging.getLogger(f"gnuradio.{self.name()}")
        self.set_relative_rate(1.0)
        self.set_tag_propagation_policy(gr.TPP_DONT)
        self.set_min_noutput_items(1)
        if self.debug_enabled:
            self.logger.debug(f"Initialized simple mux, tag_key='{tag_key}'")
    
    def forecast(self, noutput_items, ninputs):
        # Always ask for dummy; packet can be zero
        return [noutput_items, 0]
    
    def general_work(self, input_items, output_items):
        dummy_in = input_items[0]
        packet_in = input_items[1]
        out = output_items[0]
        ninput_dummy = len(dummy_in)
        ninput_packet = len(packet_in)
        noutput = len(out)
        
        produced = 0
        consumed_dummy = 0
        consumed_packet = 0

        abs_read_packet = self.nitems_read(1)
        
        # If packet samples are available, forward as many as possible and propagate their tags
        if ninput_packet > 0:
            ncopy = min(ninput_packet, noutput)
            out[:ncopy] = packet_in[:ncopy]
            produced += ncopy
            consumed_packet += ncopy
            self.samples_output_packet += ncopy

            tags = self.get_tags_in_range(1, abs_read_packet, abs_read_packet + ncopy)
            for t in tags:
                rel = t.offset - abs_read_packet
                self.add_item_tag(0, self.nitems_written(0) + rel, t.key, t.value, t.srcid)

        # Fill remaining with dummy
        remaining = noutput - produced
        if remaining > 0 and consumed_dummy < ninput_dummy:
            nfill = min(remaining, ninput_dummy - consumed_dummy)
            out[produced:produced + nfill] = dummy_in[consumed_dummy:consumed_dummy + nfill]
            consumed_dummy += nfill
            produced += nfill
            self.samples_output_dummy += nfill

        self.consume(0, consumed_dummy)
        self.consume(1, consumed_packet)
        
        if self.debug_enabled:
            current_output_pos = self.nitems_written(0) + produced
            if current_output_pos - self.last_debug_output >= self.debug_interval:
                self.logger.debug(f"Dummy={self.samples_output_dummy} Packet={self.samples_output_packet} Output_pos={current_output_pos}")
                self.last_debug_output = current_output_pos

        return produced


# For compatibility and direct instantiation
PacketGapFiller = packet_gap_filler
