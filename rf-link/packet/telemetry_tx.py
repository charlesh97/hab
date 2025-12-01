#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Packet Custom Tx
# GNU Radio version: 3.10.12.0

import os
import sys
import logging as log

from gnuradio import blocks
import pmt
from gnuradio import blocks, gr
from gnuradio import digital
from gnuradio import fec
from gnuradio import filter
from gnuradio.filter import firdes
from gnuradio import gr
from gnuradio.fft import window
import signal
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import pdu
from gnuradio import soapy
from packet_tx import packet_tx  # grc-generated hier_block
import numpy
import numpy

"""
example usage
python3 telemetry_tx.py --freq 915e6 --offset 200e3 --samp 2e6 --hackrf-amp --hackrf-vga 16 --hackrf-serial '000000000000000060a464dc3606610f'
"""


class packet_custom_tx(gr.top_block):

    def __init__(self, options):
        gr.top_block.__init__(self, "Packet Custom Tx", catch_exceptions=True)

        ##################################################
        # Variables
        ##################################################
        self.sps = sps = 2
        self.rep = rep = 3
        self.rate = rate = 2
        self.polys = polys = [109, 79]
        self.nfilts = nfilts = 32
        self.k = k = 7
        self.eb = eb = 0.22
        self.Const_PLD = Const_PLD = digital.constellation_calcdist(digital.psk_4()[0], digital.psk_4()[1],
        4, 1, digital.constellation.AMPLITUDE_NORMALIZATION).base()
        self.Const_PLD.set_npwr(1.0)
        self.Const_PLD.gen_soft_dec_lut(8)
        self.tx_rrc_taps = tx_rrc_taps = firdes.root_raised_cosine(nfilts, nfilts,1.0, eb, (5*sps*nfilts))
        self.hdr_format = hdr_format = digital.header_format_counter(digital.packet_utils.default_access_code, 3, Const_PLD.bits_per_symbol())
        self.enc_hdr = enc_hdr = fec.repetition_encoder_make(8000, rep)
        self.enc = enc = fec.cc_encoder_make(8000,k, rate, polys, 0, fec.CC_TERMINATED, False)
        self.Const_HDR = Const_HDR = digital.constellation_calcdist(digital.psk_2()[0], digital.psk_2()[1],
        2, 1, digital.constellation.AMPLITUDE_NORMALIZATION).base()
        self.Const_HDR.set_npwr(1.0)
        self.Const_HDR.gen_soft_dec_lut(8)

        ## Options Variables
        self.samp_rate = options.samp_rate
        self.freq = options.freq
        self.freq_offset = options.offset
        self.hackrf = {
            'amp': options.hackrf_amp,
            'vga': options.hackrf_vga,
            'serial': options.hackrf_serial
        }

        ##################################################
        # Blocks
        ##################################################
        self.soapy_hackrf_sink_0 = self.setup_hackrf_sink()


        self.pdu_random_pdu_0 = pdu.random_pdu(20, 200, 0xFF, 2)
        self.packet_tx_0 = packet_tx(
            hdr_const=Const_HDR,
            hdr_enc=enc_hdr,
            hdr_format=hdr_format,
            pld_const=Const_PLD,
            pld_enc=enc,
            psf_taps=tx_rrc_taps,
            sps=sps,
            post_padding=0  # Let BurstPad handle all padding for HackRF buffer
        )
        #self.freq_xlating_fir_filter_xxx_0 = filter.freq_xlating_fir_filter_ccc(1, [32], self.freq_offset, self.samp_rate)
        # Generate test packets every 1000ms
        self.blocks_message_strobe_0 = blocks.message_strobe(pmt.intern("TEST"), 1000)

        # Debug block to see if PDUs are being generated
        self.blocks_message_debug_0 = blocks.message_debug(True, gr.log_levels.info)
        
        print(f"[TelemetryTX] Initialized:")
        print(f"  - Packet generator: random PDU (20-200 bytes)")
        print(f"  - Message strobe: every 1000ms")
        print(f"  - HackRF sample rate: {self.samp_rate/1e6:.1f} MHz")
        print(f"  - HackRF frequency: {self.freq/1e6:.3f} MHz")
        padding_ms = 250000 / self.samp_rate * 1000
        print(f"  - Burst padding: 250K samples ({padding_ms:.1f}ms per burst)")
        print(f"  - Expected burst rate: ~{1000/padding_ms:.1f} bursts/second (limited by padding)")
        
        # Custom block to pad tagged stream bursts with zeros for HackRF buffer management
        # This appends zeros after each burst to ensure HackRF's TX buffer doesn't underflow
        class BurstPad(gr.sync_block):
            """
            Pads tagged stream bursts with zeros after each burst.
            Appends ~250K samples of zeros to each burst for HackRF buffer management.
            
            The block reads packet_len tags, copies the burst, then appends zeros.
            """
            def __init__(self, padding_samples=250000, tag_key='packet_len', debug=True):
                gr.sync_block.__init__(
                    self,
                    name="BurstPad",
                    in_sig=[numpy.complex64],
                    out_sig=[numpy.complex64]
                )
                self.padding_samples = padding_samples
                self.tag_key = pmt.intern(tag_key)
                self.debug = debug
                # Don't auto-propagate tags - we'll create new ones
                self.set_tag_propagation_policy(gr.TPP_DONT)
                # State tracking
                self.burst_remaining = 0
                self.padding_remaining = 0
                self.burst_start_output_offset = None  # Absolute output offset where burst starts
                self.burst_length = 0
                self.burst_count = 0
            
            def work(self, input_items, output_items):
                in0 = input_items[0]
                out = output_items[0]
                ninput = len(in0)
                noutput = len(out)
                
                nread = self.nitems_read(0)
                nwritten = self.nitems_written(0)
                
                consumed = 0
                produced = 0
                
                # Get all tags in this window
                tags = self.get_tags_in_range(0, nread, nread + ninput)
                
                # Process tags to find new bursts
                # Tags appear at the START of a burst and indicate the length
                for tag in tags:
                    if pmt.eq(tag.key, self.tag_key):
                        tag_offset = tag.offset - nread  # Relative offset in current buffer
                        burst_length = pmt.to_uint64(tag.value)
                        
                        # Skip to the tag position before starting the burst
                        if consumed < tag_offset:
                            # Copy data before the tag (shouldn't happen in normal tagged stream)
                            skip_len = tag_offset - consumed
                            if skip_len > 0 and produced < noutput and consumed < ninput:
                                copy_len = min(skip_len, noutput - produced, ninput - consumed)
                                if copy_len > 0:
                                    out[produced:produced+copy_len] = in0[consumed:consumed+copy_len]
                                    produced += copy_len
                                    consumed += copy_len
                        
                        # If we find a tag and we're not already processing a burst, start a new one
                        if self.burst_remaining == 0 and self.padding_remaining == 0 and consumed >= tag_offset:
                            self.burst_length = burst_length
                            self.burst_remaining = burst_length
                            self.burst_start_output_offset = nwritten + produced  # Mark where output burst starts
                            if self.debug:
                                print(f"[BurstPad] Starting burst #{self.burst_count}: length={burst_length}, input_offset={tag.offset}, output_start={self.burst_start_output_offset}")
                            self.burst_count += 1
                
                # Copy the burst itself
                if self.burst_remaining > 0 and produced < noutput and consumed < ninput:
                    copy_len = min(self.burst_remaining, noutput - produced, ninput - consumed)
                    if copy_len > 0:
                        out[produced:produced+copy_len] = in0[consumed:consumed+copy_len]
                        produced += copy_len
                        consumed += copy_len
                        self.burst_remaining -= copy_len
                    
                    # If burst is complete, add tag and start padding
                    if self.burst_remaining == 0 and self.burst_start_output_offset is not None:
                        self.padding_remaining = self.padding_samples
                        new_length = self.burst_length + self.padding_samples
                        # Tag goes at the start of the burst (which we already produced)
                        tag_pos = self.burst_start_output_offset
                        if self.debug:
                            print(f"[BurstPad] Burst complete: adding tag at offset={tag_pos}, new_length={new_length} (burst={self.burst_length} + pad={self.padding_samples})")
                        self.add_item_tag(0, tag_pos, self.tag_key, pmt.from_uint64(new_length))
                        self.burst_start_output_offset = None
                
                # Add padding zeros after the burst
                if self.padding_remaining > 0 and produced < noutput:
                    pad_len = min(self.padding_remaining, noutput - produced)
                    out[produced:produced+pad_len] = 0
                    produced += pad_len
                    self.padding_remaining -= pad_len
                    
                    if self.debug and self.padding_remaining == 0:
                        print(f"[BurstPad] Padding complete: added {self.padding_samples} zeros")
                
                # Copy any remaining input data (this may be post-padding from burst_shaper)
                # This is expected and normal - the burst_shaper adds post-padding for filter delay
                if consumed < ninput and produced < noutput:
                    copy_len = min(ninput - consumed, noutput - produced)
                    if copy_len > 0:
                        out[produced:produced+copy_len] = in0[consumed:consumed+copy_len]
                        produced += copy_len
                        consumed += copy_len
                        # This is expected - it's post-padding from burst_shaper for filter delay
                        # Only log occasionally to reduce noise
                        if self.debug and hasattr(self, '_post_burst_count'):
                            self._post_burst_count += 1
                        else:
                            self._post_burst_count = 0
                        
                        if self.debug and self._post_burst_count % 50 == 0 and copy_len > 1000:
                            print(f"[BurstPad] Processing post-burst padding: {copy_len} samples")
                
                # Only print debug periodically to reduce noise
                if not hasattr(self, '_debug_counter'):
                    self._debug_counter = 0
                self._debug_counter += 1
                
                if self.debug and self._debug_counter % 100 == 0 and (consumed > 0 or produced > 0):
                    print(f"[BurstPad] work() call #{self._debug_counter}: consumed={consumed}, produced={produced}, burst_rem={self.burst_remaining}, pad_rem={self.padding_remaining}")
                
                return consumed
        
        # Create padding block: adds 250K samples (125ms at 2 Msps) after each burst
        # This ensures HackRF buffer is always filled between bursts
        padding_samples = 500000
        self.blocks_burst_pad_0 = BurstPad(padding_samples=padding_samples, tag_key='packet_len', debug=True)


        ##################################################
        # Connections
        ##################################################
        # Message connections
        self.msg_connect((self.blocks_message_strobe_0, 'strobe'), (self.pdu_random_pdu_0, 'generate'))
        self.msg_connect((self.pdu_random_pdu_0, 'pdus'), (self.packet_tx_0, 'in'))
        # Debug connection to see if packets are being generated
        self.msg_connect((self.pdu_random_pdu_0, 'pdus'), (self.blocks_message_debug_0, 'print')) 

        #self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.soapy_hackrf_sink_0, 0))
        #self.connect((self.packet_tx_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))
        # Connect packet_tx → burst pad → HackRF sink
        # The burst pad block adds zeros after each burst for HackRF buffer management
        self.connect((self.packet_tx_0, 0), (self.blocks_burst_pad_0, 0))
        self.connect((self.blocks_burst_pad_0, 0), (self.soapy_hackrf_sink_0, 0))



        ##################################################
        # Custom Block
        ##################################################


    def setup_hackrf_sink(self):
        from gnuradio import soapy
        
        dev = 'driver=hackrf'
        stream_args = ''
        tune_args = ['']
        settings = ['']
        
        # Set device_args with serial number if provided
        if self.hackrf['serial'] is not None:
            device_args = 'serial=' + self.hackrf['serial']
        else:
            device_args = ''
        
        self.hackrf_sink = hackrf_sink = soapy.sink(
            dev, "fc32", 1, device_args, stream_args, tune_args, settings)
        
        hackrf_sink.set_sample_rate(0, self.samp_rate)
        hackrf_sink.set_bandwidth(0, 0)
        hackrf_sink.set_frequency(0, self.freq)
        hackrf_sink.set_gain(0, 'AMP', self.hackrf['amp'])
        hackrf_sink.set_gain(0, 'VGA', min(max(self.hackrf['vga'], 0.0), 47.0))
        
        return hackrf_sink


    def get_sps(self):
        return self.sps

    def set_sps(self, sps):
        self.sps = sps
        self.set_tx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts, 1.0, self.eb, (5*self.sps*self.nfilts)))
        self.packet_tx_0.set_sps(self.sps)

    def get_rep(self):
        return self.rep

    def set_rep(self, rep):
        self.rep = rep

    def get_rate(self):
        return self.rate

    def set_rate(self, rate):
        self.rate = rate

    def get_polys(self):
        return self.polys

    def set_polys(self, polys):
        self.polys = polys

    def get_nfilts(self):
        return self.nfilts

    def set_nfilts(self, nfilts):
        self.nfilts = nfilts
        self.set_tx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts, 1.0, self.eb, (5*self.sps*self.nfilts)))

    def get_k(self):
        return self.k

    def set_k(self, k):
        self.k = k

    def get_eb(self):
        return self.eb

    def set_eb(self, eb):
        self.eb = eb
        self.set_tx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts, 1.0, self.eb, (5*self.sps*self.nfilts)))

    def get_Const_PLD(self):
        return self.Const_PLD

    def set_Const_PLD(self, Const_PLD):
        self.Const_PLD = Const_PLD
        self.packet_tx_0.set_pld_const(self.Const_PLD)

    def get_tx_rrc_taps(self):
        return self.tx_rrc_taps

    def set_tx_rrc_taps(self, tx_rrc_taps):
        self.tx_rrc_taps = tx_rrc_taps
        self.packet_tx_0.set_psf_taps(self.tx_rrc_taps)

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.soapy_hackrf_sink_0.set_sample_rate(0, self.samp_rate)

    def get_hdr_format(self):
        return self.hdr_format

    def set_hdr_format(self, hdr_format):
        self.hdr_format = hdr_format
        self.packet_tx_0.set_hdr_format(self.hdr_format)

    def get_enc_hdr(self):
        return self.enc_hdr

    def set_enc_hdr(self, enc_hdr):
        self.enc_hdr = enc_hdr
        self.packet_tx_0.set_hdr_enc(self.enc_hdr)

    def get_enc(self):
        return self.enc

    def set_enc(self, enc):
        self.enc = enc
        self.packet_tx_0.set_pld_enc(self.enc)

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.soapy_hackrf_sink_0.set_frequency(0, self.center_freq)

    def get_Const_HDR(self):
        return self.Const_HDR

    def set_Const_HDR(self, Const_HDR):
        self.Const_HDR = Const_HDR
        self.packet_tx_0.set_hdr_const(self.Const_HDR)


def argument_parser():
    description = 'Telemetry Transmitter'
    
    parser = ArgumentParser(prog="telemetry-tx", description=description, formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        "--freq",
        type=eng_float,
        default=eng_notation.num_to_str(float(1e9)),
        help="RF center frequency [Hz]"
    )
    parser.add_argument(
        "--offset",
        type=eng_float,
        default=eng_notation.num_to_str(float(0)),
        help="Center frequency offset [Hz]"
    )
    parser.add_argument(
        "--samp",
        dest="samp_rate",
        type=eng_float,
        default=eng_notation.num_to_str(float(2e6)),
        help="Sample rate [Hz]"
    )
    hackrf_group = parser.add_argument_group('HackRF Options')
    hackrf_group.add_argument('--hackrf-amp',
                              action='store_true',
                              default=False,
                              help="Enable HackRF RF amplifier (0 or 14 dB)")
    hackrf_group.add_argument('--hackrf-vga',
                              type=float,
                              default=16,
                              help="HackRF VGA gain in dB (0-47 dB, step 1 dB)")
    hackrf_group.add_argument('--hackrf-serial',
                              type=str,
                              default=None,
                              help="HackRF device serial number (e.g., 000000000000000060a464dc3674640f)")


    options = parser.parse_args()
    return options


def main():

    options = argument_parser()

    tb = packet_custom_tx(options)
    
    print(f"[TelemetryTX] Starting flowgraph...")
    print(f"[TelemetryTX] Frequency: {options.freq} Hz")
    print(f"[TelemetryTX] Sample rate: {options.samp_rate} Hz")
    print(f"[TelemetryTX] HackRF serial: {options.hackrf_serial}")
    print(f"[TelemetryTX] HackRF amp: {options.hackrf_amp}")
    
    tb.start()
    print(f"[TelemetryTX] Flowgraph started - transmitting packets...")

    try:
        input('Press Enter to quit: ')
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == '__main__':
    main()
