#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Packet Custom Rx
# GNU Radio version: 3.10.12.0

import os
import sys
import logging as log

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
from gnuradio import soapy
from packet_rx import packet_rx  # grc-generated hier_block




class packet_custom_rx(gr.top_block):

    def __init__(self, options):
        gr.top_block.__init__(self, "Packet Custom Rx", catch_exceptions=True)

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
        self.rx_rrc_taps = rx_rrc_taps = firdes.root_raised_cosine(nfilts, nfilts*sps,1.0, eb, (11*sps*nfilts))
        self.hdr_format = hdr_format = digital.header_format_counter(digital.packet_utils.default_access_code, 3, Const_PLD.bits_per_symbol())
        self.dec_hdr = dec_hdr = fec.repetition_decoder.make(hdr_format.header_nbits(),rep, 0.5)
        self.dec = dec = fec.cc_decoder.make(8000,k, rate, polys, 0, (-1), fec.CC_TERMINATED, False)
        self.Const_HDR = Const_HDR = digital.constellation_calcdist(digital.psk_2()[0], digital.psk_2()[1],
        2, 1, digital.constellation.AMPLITUDE_NORMALIZATION).base()
        self.Const_HDR.set_npwr(1.0)
        self.Const_HDR.gen_soft_dec_lut(8)

        ## Options Variables
        self.freq = options.freq
        self.samp_rate = options.samp_rate
        self.freq_offset = options.offset
        self.hackrf = {
            'amp': options.hackrf_amp,
            'vga': options.hackrf_vga,
            'lna': options.hackrf_lna,
            'serial': options.hackrf_serial
        }

        ##################################################
        # Blocks
        ##################################################
        self.soapy_hackrf_source_0 = self.setup_hackrf_source()
        self.packet_rx_0 = packet_rx(
            eb=eb,
            hdr_const=Const_HDR,
            hdr_dec=dec_hdr,
            hdr_format=hdr_format,
            pld_const=Const_PLD,
            pld_dec=dec,
            psf_taps=rx_rrc_taps,
            sps=sps,
        )
        self.freq_xlating_fir_filter_xxx_0 = filter.freq_xlating_fir_filter_ccc(1, [32], 200e3, samp_rate)
        self.blocks_message_debug_0_0_0 = blocks.message_debug(True, gr.log_levels.info)


        ##################################################
        # Connections
        ##################################################
        self.msg_connect((self.packet_rx_0, 'pkt out'), (self.blocks_message_debug_0_0_0, 'print_pdu'))
        self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.packet_rx_0, 0))
        self.connect((self.soapy_hackrf_source_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))

    def setup_hackrf_source(self):
        from gnuradio import soapy
        
        dev = 'driver=hackrf'
        stream_args = ''
        tune_args = ['']
        settings = ['']
        
        if self.hackrf['serial'] is not None:
            device_args = 'serial=' + self.hackrf['serial']
        else:
            device_args = ''
        
        self.hackrf_source = hackrf_source = soapy.source(
            dev, "fc32", 1, device_args, stream_args, tune_args, settings)
        
        hackrf_source.set_sample_rate(0, self.samp_rate)
        hackrf_source.set_bandwidth(0, 0)
        hackrf_source.set_frequency(0, self.freq)
        hackrf_source.set_gain(0, 'AMP', self.hackrf['amp'])
        hackrf_source.set_gain(0, 'LNA', min(max(self.hackrf['lna'], 0.0), 40.0))
        hackrf_source.set_gain(0, 'VGA', min(max(self.hackrf['vga'], 0.0), 62.0))
        
        return hackrf_source

    def get_Const_PLD(self):
        return self.Const_PLD

    def set_Const_PLD(self, Const_PLD):
        self.Const_PLD = Const_PLD
        self.packet_rx_0.set_pld_const(self.Const_PLD)

    def get_sps(self):
        return self.sps

    def set_sps(self, sps):
        self.sps = sps
        self.set_rx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts*self.sps, 1.0, self.eb, (11*self.sps*self.nfilts)))
        self.packet_rx_0.set_sps(self.sps)

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
        self.set_rx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts*self.sps, 1.0, self.eb, (11*self.sps*self.nfilts)))

    def get_k(self):
        return self.k

    def set_k(self, k):
        self.k = k

    def get_hdr_format(self):
        return self.hdr_format

    def set_hdr_format(self, hdr_format):
        self.hdr_format = hdr_format
        self.packet_rx_0.set_hdr_format(self.hdr_format)

    def get_eb(self):
        return self.eb

    def set_eb(self, eb):
        self.eb = eb
        self.set_rx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts*self.sps, 1.0, self.eb, (11*self.sps*self.nfilts)))
        self.packet_rx_0.set_eb(self.eb)

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.soapy_hackrf_source_0.set_sample_rate(0, self.samp_rate)

    def get_rx_rrc_taps(self):
        return self.rx_rrc_taps

    def set_rx_rrc_taps(self, rx_rrc_taps):
        self.rx_rrc_taps = rx_rrc_taps
        self.packet_rx_0.set_psf_taps(self.rx_rrc_taps)

    def get_dec_hdr(self):
        return self.dec_hdr

    def set_dec_hdr(self, dec_hdr):
        self.dec_hdr = dec_hdr
        self.packet_rx_0.set_hdr_dec(self.dec_hdr)

    def get_dec(self):
        return self.dec

    def set_dec(self, dec):
        self.dec = dec
        self.packet_rx_0.set_pld_dec(self.dec)

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.soapy_hackrf_source_0.set_frequency(0, self.center_freq)

    def get_Const_HDR(self):
        return self.Const_HDR

    def set_Const_HDR(self, Const_HDR):
        self.Const_HDR = Const_HDR
        self.packet_rx_0.set_hdr_const(self.Const_HDR)


def argument_parser():
    description = 'Telemetry Receiver'
    
    parser = ArgumentParser(prog="telemetry-rx", description=description, formatter_class=ArgumentDefaultsHelpFormatter)
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
    hackrf_group.add_argument('--hackrf-lna',
                              type=float,
                              default=16,
                              help="HackRF LNA gain in dB (0-40 dB, step 8 dB)")
    hackrf_group.add_argument('--hackrf-serial',
                              type=str,
                              default=None,
                              help="HackRF device serial number (e.g., 000000000000000060a464dc3674640f)")

    


    options = parser.parse_args()
    return options


def main():

    options = argument_parser()

    tb = packet_custom_rx(options)
    tb.start()

    try:
        input('Press Enter to quit: ')
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == '__main__':
    main()
