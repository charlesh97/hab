# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Packet Rx
# GNU Radio version: 3.10.12.0

from gnuradio import blocks
from gnuradio import digital
from gnuradio import fec
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from gnuradio import gr, pdu
import pmt
import threading







class packet_rx(gr.hier_block2):
    def __init__(self, eb=0.35, hdr_const=digital.constellation_calcdist((digital.psk_2()[0]), (digital.psk_2()[1]), 2, 1).base(), hdr_dec= fec.dummy_decoder.make(8000), hdr_format=digital.header_format_default(digital.packet_utils.default_access_code, 0), pld_const=digital.constellation_calcdist((digital.psk_2()[0]), (digital.psk_2()[1]), 2, 1).base(), pld_dec= fec.dummy_decoder.make(8000), psf_taps=[0,], sps=2):
        gr.hier_block2.__init__(
            self, "Packet Rx",
                gr.io_signature(1, 1, gr.sizeof_gr_complex*1),
                gr.io_signature.makev(5, 5, [gr.sizeof_gr_complex*1, gr.sizeof_gr_complex*1, gr.sizeof_gr_complex*1, gr.sizeof_gr_complex*1, gr.sizeof_gr_complex*1]),
        )
        self.message_port_register_hier_out("pkt out")
        self.message_port_register_hier_out("precrc")

        ##################################################
        # Parameters
        ##################################################
        self.eb = eb
        self.hdr_const = hdr_const
        self.hdr_dec = hdr_dec
        self.hdr_format = hdr_format
        self.pld_const = pld_const
        self.pld_dec = pld_dec
        self.psf_taps = psf_taps
        self.sps = sps

        ##################################################
        # Variables
        ##################################################
        self.preamble_rep = preamble_rep = [0xe3, 0x8f, 0xc0, 0xfc, 0x7f, 0xc7, 0xe3, 0x81, 0xc0, 0xff, 0x80, 0x38, 0xff, 0xf0, 0x38, 0xe0, 0x0f, 0xc0, 0x03, 0x80, 0x00, 0xff, 0xff, 0xc0]
        self.preamble_dummy = preamble_dummy = [0xac, 0xdd, 0xa4, 0xe2, 0xf2, 0x8c, 0x20, 0xfc]
        self.preamble_select = preamble_select = {1: preamble_dummy, 3: preamble_rep}
        self.rxmod = rxmod = digital.generic_mod(hdr_const, False, sps, True, eb, False, False)
        self.preamble = preamble = preamble_select[int(1.0/hdr_dec.rate())]
        self.mark_delays = mark_delays = [0, 0, 34, 56, 87, 119]
        self.nfilts = nfilts = 32
        self.modulated_sync_word = modulated_sync_word = digital.modulate_vector_bc(rxmod.to_basic_block(), preamble, [1])
        self.mark_delay = mark_delay = mark_delays[sps]

        ##################################################
        # Blocks
        ##################################################

        self.pdu_tagged_stream_to_pdu_0 = pdu.tagged_stream_to_pdu(gr.types.float_t, "payload symbols")
        self.fec_generic_decoder_0 = fec.decoder(hdr_dec, gr.sizeof_float, gr.sizeof_char)
        self.fec_async_decoder_0 = fec.async_decoder(pld_dec, False, False, (1500*8))
        self.digital_protocol_parser_b_0 = digital.protocol_parser_b(hdr_format)
        self.digital_pfb_clock_sync_xxx_0 = digital.pfb_clock_sync_ccf(sps, (6.28/400.0), psf_taps, nfilts, (nfilts/2), 1.5, 1)
        self.digital_header_payload_demux_0 = digital.header_payload_demux(
            ((hdr_format.header_nbits() * int(1.0/hdr_dec.rate())) //  hdr_const.bits_per_symbol()),
            1,
            0,
            "payload symbols",
            "time_est",
            True,
            gr.sizeof_gr_complex,
            "rx_time",
            1,
            [],
            0)
        self.digital_crc32_async_bb_0 = digital.crc32_async_bb(True)
        self.digital_costas_loop_cc_0_0_0 = digital.costas_loop_cc((6.28/200.0), pld_const.arity(), False)
        self.digital_costas_loop_cc_0_0 = digital.costas_loop_cc((6.28/200.0), hdr_const.arity(), False)
        self.digital_corr_est_cc_0 = digital.corr_est_cc(modulated_sync_word, sps, mark_delay, 0.9, digital.THRESHOLD_ABSOLUTE)
        self.digital_constellation_soft_decoder_cf_0_0 = digital.constellation_soft_decoder_cf(hdr_const, -1)
        self.digital_constellation_soft_decoder_cf_0 = digital.constellation_soft_decoder_cf(pld_const, -1)
        self.blocks_tagged_stream_multiply_length_0 = blocks.tagged_stream_multiply_length(gr.sizeof_float*1, "payload symbols", pld_const.bits_per_symbol())
        self.blocks_multiply_by_tag_value_cc_0 = blocks.multiply_by_tag_value_cc("amp_est", 1)
        
        # Debug blocks (disabled for cleaner output)
        # self.blocks_message_debug_header_info = blocks.message_debug(True, gr.log_levels.info)
        # self.blocks_message_debug_pdu_to_fec = blocks.message_debug(True, gr.log_levels.info)
        
        # Custom message handler block for detailed header info
        class HeaderInfoDebug(gr.basic_block):
            def __init__(self, pld_const):
                gr.basic_block.__init__(self,
                    name="HeaderInfoDebug",
                    in_sig=None,
                    out_sig=None)
                self.pld_const = pld_const
                self.message_port_register_in(pmt.intern("in"))
                self.message_port_register_out(pmt.intern("out"))
                self.set_msg_handler(pmt.intern("in"), self.handle_msg)
            
            def handle_msg(self, msg):
                # Verbose header info disabled for cleaner output
                # if pmt.is_dict(msg):
                #     print("\n[DEBUG RX] Header Info Dictionary:")
                #     ...
                self.message_port_pub(pmt.intern("out"), msg)
        
        self.blocks_header_info_debug = HeaderInfoDebug(pld_const)
        
        # Padding and packing block to restore missing bits before CRC check
        # FEC decoder outputs unpacked bits that may not be byte-aligned due to truncation
        # We pad to next byte boundary (modulo 8 = 0), then pack to bytes for CRC32
        class PaddingAndPackingBlock(gr.basic_block):
            def __init__(self):
                gr.basic_block.__init__(self,
                    name="PaddingAndPackingBlock",
                    in_sig=None,
                    out_sig=None)
                self.message_port_register_in(pmt.intern("in"))
                self.message_port_register_out(pmt.intern("out"))
                self.message_port_register_out(pmt.intern("precrc"))  # Output port for debugging
                self.set_msg_handler(pmt.intern("in"), self.handle_msg)
            
            def handle_msg(self, msg):
                # Forward original message to precrc port for debugging (before padding)
                
                self.message_port_pub(pmt.intern("precrc"), msg)
                
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
                        
                        # If packing more than 2 bits, please make warning message
                        if padding_needed > 2:
                            print(f"[Padding Block] WARNING: Packing {padding_needed} bits more than 2 bits")

                        # Pack unpacked bits to bytes (8 bits per byte, MSB first)
                        # Convert each bit (0 or 1) to actual bit values
                        packed_bytes = []
                        for i in range(0, len(vec), 8):
                            byte_val = 0
                            for j in range(8):
                                if i + j < len(vec):
                                    # Convert 0/1 byte to bit
                                    bit_val = vec[i + j] & 0x01  # Ensure it's 0 or 1
                                    byte_val |= (bit_val << (7 - j))  # MSB first
                            packed_bytes.append(byte_val)
                        
                        packed = pmt.init_u8vector(len(packed_bytes), packed_bytes)
                        self.message_port_pub(pmt.intern("out"), pmt.cons(meta, packed))
                    else:
                        #throw error message
                        raise ValueError(f"[Padding Block] ERROR: Not a u8vector: {data}")
                else:
                    #throw error message
                    raise ValueError(f"[Padding Block] ERROR: Not a PDU pair: {msg}")
        
        self.blocks_padding = PaddingAndPackingBlock()


        ##################################################
        # Connections
        ##################################################
        self.msg_connect((self.digital_crc32_async_bb_0, 'out'), (self, 'pkt out'))
        self.msg_connect((self.digital_protocol_parser_b_0, 'info'), (self.blocks_header_info_debug, 'in'))
        self.msg_connect((self.blocks_header_info_debug, 'out'), (self.digital_header_payload_demux_0, 'header_data'))
        # Disabled for cleaner output
        # self.msg_connect((self.blocks_header_info_debug, 'out'), (self.blocks_message_debug_header_info, 'print'))
        self.msg_connect((self.fec_async_decoder_0, 'out'), (self.blocks_padding, 'in'))
        self.msg_connect((self.blocks_padding, 'out'), (self.digital_crc32_async_bb_0, 'in'))
        self.msg_connect((self.blocks_padding, 'precrc'), (self, 'precrc'))  # Debug output before padding
        self.msg_connect((self.pdu_tagged_stream_to_pdu_0, 'pdus'), (self.fec_async_decoder_0, 'in'))
        # Disabled for cleaner output
        # self.msg_connect((self.pdu_tagged_stream_to_pdu_0, 'pdus'), (self.blocks_message_debug_pdu_to_fec, 'print'))
        self.connect((self.blocks_multiply_by_tag_value_cc_0, 0), (self.digital_pfb_clock_sync_xxx_0, 0))
        self.connect((self.blocks_tagged_stream_multiply_length_0, 0), (self.pdu_tagged_stream_to_pdu_0, 0))
        self.connect((self.digital_constellation_soft_decoder_cf_0, 0), (self.blocks_tagged_stream_multiply_length_0, 0))
        self.connect((self.digital_constellation_soft_decoder_cf_0_0, 0), (self.fec_generic_decoder_0, 0))
        self.connect((self.digital_corr_est_cc_0, 0), (self.blocks_multiply_by_tag_value_cc_0, 0))
        self.connect((self.digital_corr_est_cc_0, 1), (self, 4))
        self.connect((self.digital_costas_loop_cc_0_0, 0), (self.digital_constellation_soft_decoder_cf_0_0, 0))
        self.connect((self.digital_costas_loop_cc_0_0_0, 0), (self.digital_constellation_soft_decoder_cf_0, 0))
        self.connect((self.digital_costas_loop_cc_0_0_0, 0), (self, 2))
        self.connect((self.digital_header_payload_demux_0, 0), (self.digital_costas_loop_cc_0_0, 0))
        self.connect((self.digital_header_payload_demux_0, 1), (self.digital_costas_loop_cc_0_0_0, 0))
        self.connect((self.digital_header_payload_demux_0, 0), (self, 0))
        self.connect((self.digital_header_payload_demux_0, 1), (self, 1))
        self.connect((self.digital_pfb_clock_sync_xxx_0, 0), (self.digital_header_payload_demux_0, 0))
        self.connect((self.digital_pfb_clock_sync_xxx_0, 0), (self, 3))
        self.connect((self.fec_generic_decoder_0, 0), (self.digital_protocol_parser_b_0, 0))
        self.connect((self, 0), (self.digital_corr_est_cc_0, 0))


    def get_eb(self):
        return self.eb

    def set_eb(self, eb):
        self.eb = eb
        self.set_rxmod(digital.generic_mod(self.hdr_const, False, self.sps, True, self.eb, False, False))

    def get_hdr_const(self):
        return self.hdr_const

    def set_hdr_const(self, hdr_const):
        self.hdr_const = hdr_const
        self.set_rxmod(digital.generic_mod(self.hdr_const, False, self.sps, True, self.eb, False, False))
        self.digital_constellation_soft_decoder_cf_0_0.set_constellation(self.hdr_const)

    def get_hdr_dec(self):
        return self.hdr_dec

    def set_hdr_dec(self, hdr_dec):
        self.hdr_dec = hdr_dec

    def get_hdr_format(self):
        return self.hdr_format

    def set_hdr_format(self, hdr_format):
        self.hdr_format = hdr_format

    def get_pld_const(self):
        return self.pld_const

    def set_pld_const(self, pld_const):
        self.pld_const = pld_const
        self.digital_constellation_soft_decoder_cf_0.set_constellation(self.pld_const)

    def get_pld_dec(self):
        return self.pld_dec

    def set_pld_dec(self, pld_dec):
        self.pld_dec = pld_dec

    def get_psf_taps(self):
        return self.psf_taps

    def set_psf_taps(self, psf_taps):
        self.psf_taps = psf_taps
        self.digital_pfb_clock_sync_xxx_0.update_taps(self.psf_taps)

    def get_sps(self):
        return self.sps

    def set_sps(self, sps):
        self.sps = sps
        self.set_mark_delay(self.mark_delays[self.sps])
        self.set_rxmod(digital.generic_mod(self.hdr_const, False, self.sps, True, self.eb, False, False))

    def get_preamble_rep(self):
        return self.preamble_rep

    def set_preamble_rep(self, preamble_rep):
        self.preamble_rep = preamble_rep
        self.set_preamble_select({1: self.preamble_dummy, 3: self.preamble_rep})

    def get_preamble_dummy(self):
        return self.preamble_dummy

    def set_preamble_dummy(self, preamble_dummy):
        self.preamble_dummy = preamble_dummy
        self.set_preamble_select({1: self.preamble_dummy, 3: self.preamble_rep})

    def get_preamble_select(self):
        return self.preamble_select

    def set_preamble_select(self, preamble_select):
        self.preamble_select = preamble_select
        self.set_preamble(self.preamble_select[int(1.0/hdr_dec.rate())])

    def get_rxmod(self):
        return self.rxmod

    def set_rxmod(self, rxmod):
        self.rxmod = rxmod

    def get_preamble(self):
        return self.preamble

    def set_preamble(self, preamble):
        self.preamble = preamble

    def get_mark_delays(self):
        return self.mark_delays

    def set_mark_delays(self, mark_delays):
        self.mark_delays = mark_delays
        self.set_mark_delay(self.mark_delays[self.sps])

    def get_nfilts(self):
        return self.nfilts

    def set_nfilts(self, nfilts):
        self.nfilts = nfilts

    def get_modulated_sync_word(self):
        return self.modulated_sync_word

    def set_modulated_sync_word(self, modulated_sync_word):
        self.modulated_sync_word = modulated_sync_word

    def get_mark_delay(self):
        return self.mark_delay

    def set_mark_delay(self, mark_delay):
        self.mark_delay = mark_delay
        self.digital_corr_est_cc_0.set_mark_delay(self.mark_delay)

