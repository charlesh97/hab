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
            post_padding=10000 # 10000 samples = 5ms at 2e6 samples/second
        )
        #self.freq_xlating_fir_filter_xxx_0 = filter.freq_xlating_fir_filter_ccc(1, [32], self.freq_offset, self.samp_rate)
        self.blocks_message_strobe_0 = blocks.message_strobe(pmt.intern("TEST"), 1000)

        self.blocks_message_debug_0 = blocks.message_debug(True, gr.log_levels.info)


        ##################################################
        # Connections
        ##################################################
        self.msg_connect((self.blocks_message_strobe_0, 'strobe'), (self.pdu_random_pdu_0, 'generate'))
        self.msg_connect((self.pdu_random_pdu_0, 'pdus'), (self.packet_tx_0, 'in'))
        self.msg_connect((self.blocks_message_strobe_0, 'strobe'), (self.blocks_message_debug_0, 'print')) #Add debug 

        #self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.soapy_hackrf_sink_0, 0))
        #self.connect((self.packet_tx_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))
        self.connect((self.packet_tx_0, 0), (self.soapy_hackrf_sink_0, 0))



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
    tb.start()

    try:
        input('Press Enter to quit: ')
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == '__main__':
    main()
