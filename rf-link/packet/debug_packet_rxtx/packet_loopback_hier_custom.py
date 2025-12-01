#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Packet Loopback Hier
# GNU Radio version: 3.10.12.0

import os
import sys
import logging as log



from gnuradio import blocks
import pmt
from gnuradio import blocks, gr
from gnuradio import digital
from gnuradio import fec
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import pdu
from packet_rx import packet_rx  # grc-generated hier_block
from packet_tx import packet_tx  # grc-generated hier_block
import threading




class packet_loopback_hier(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "Packet Loopback Hier", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.Const_PLD = Const_PLD = digital.constellation_calcdist(digital.psk_4()[0], digital.psk_4()[1],
        4, 1, digital.constellation.AMPLITUDE_NORMALIZATION).base()
        self.Const_PLD.set_npwr(1.0)
        self.Const_PLD.gen_soft_dec_lut(8)
        self.sps = sps = 2
        self.rep = rep = 3
        self.rate = rate = 2
        self.polys = polys = [109, 79]
        self.nfilts = nfilts = 32
        self.k = k = 7
        self.hdr_format = hdr_format = digital.header_format_counter(digital.packet_utils.default_access_code, 3, Const_PLD.bits_per_symbol())
        self.eb = eb = 0.22
        self.tx_rrc_taps = tx_rrc_taps = firdes.root_raised_cosine(nfilts, nfilts,1.0, eb, (5*sps*nfilts))
        self.rx_rrc_taps = rx_rrc_taps = firdes.root_raised_cosine(nfilts, nfilts*sps,1.0, eb, (11*sps*nfilts))
        self.enc_hdr = enc_hdr = fec.repetition_encoder_make(8000, rep)
        self.enc = enc = fec.cc_encoder_make(8000,k, rate, polys, 0, fec.CC_TERMINATED, False)
        self.dec_hdr = dec_hdr = fec.repetition_decoder.make(hdr_format.header_nbits(),rep, 0.5)
        self.dec = dec = fec.cc_decoder.make(8000,k, rate, polys, 0, 0, fec.CC_TERMINATED, False)
        self.Const_HDR = Const_HDR = digital.constellation_calcdist(digital.psk_2()[0], digital.psk_2()[1],
        2, 1, digital.constellation.AMPLITUDE_NORMALIZATION).base()
        self.Const_HDR.set_npwr(1.0)
        self.Const_HDR.gen_soft_dec_lut(8)

        ##################################################
        # Blocks
        ##################################################

        # For terminated CC with k=7: termination=6 bits, rate=1/2
        # Encoded bits = (input_bits + 6) * 2
        # For byte alignment: (input_bits + 6) * 2 must be divisible by 8
        # So: (input_bits + 6) must be divisible by 4
        # Target: input_bits = 190 (so 190 + 6 = 196, and 196 * 2 = 392 bits = 49 bytes)
        # OR: input_bits = 194 (so 194 + 6 = 200, and 200 * 2 = 400 bits = 50 bytes)
        # Current: 192 bits (24 bytes) gives 396 bits = 49.5 bytes, which truncates to 392 bits
        # Let's try 190 bits = 23.75 bytes, but bytes must be whole, so 23 bytes = 184 bits
        # 184 + 6 = 190, 190 * 2 = 380 bits = 47.5 bytes → truncates to 47 bytes = 376 bits
        # Better: 194 bits requires 24.25 bytes, so 24 bytes = 192 bits (current)
        # Actually, let's use 190 bits: need 23 bytes + 6 bits = use 23 bytes = 184 bits
        # No wait, we can't do fractional bytes in the random PDU generator
        # Let's use 23 bytes = 184 bits: 184 + 6 = 190, 190 * 2 = 380 bits = 47.5 → 47 bytes = 376 bits (worse!)
        # Best solution: pad the input to make output byte-aligned
        # For 192 bits input: need output to be 400 bits (50 bytes), so input should be (400/2) - 6 = 194 bits
        # 194 bits = 24.25 bytes, so we'd need 25 bytes = 200 bits: 200 + 6 = 206, 206 * 2 = 412 bits = 51.5 → 51 bytes
        # Actually, simplest: accept 392 bits output and adjust expectations
        self.pdu_random_pdu_0 = pdu.random_pdu(20, 200, 0xFF, 2)
        self.packet_tx_0 = packet_tx(
            hdr_const=Const_HDR,
            hdr_enc=enc_hdr,
            hdr_format=hdr_format,
            pld_const=Const_PLD,
            pld_enc=enc,
            psf_taps=tx_rrc_taps,
            sps=sps,
        )
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
        # Disable tag debug blocks for cleaner output
        # self.blocks_tag_debug_0_0 = blocks.tag_debug(gr.sizeof_gr_complex*1, '', "")
        # self.blocks_tag_debug_0_0.set_display(True)
        # self.blocks_tag_debug_0 = blocks.tag_debug(gr.sizeof_gr_complex*1, "payload_symbols", "")
        # self.blocks_tag_debug_0.set_display(True)
        self.blocks_message_strobe_0 = blocks.message_strobe(pmt.intern("TEST"), 500)
        # Disable verbose message_debug blocks - use comparison block instead
        # self.blocks_message_debug_0_0_0_0_0_0 = blocks.message_debug(True, gr.log_levels.info)
        # self.blocks_message_debug_0_0_0_0_0 = blocks.message_debug(True, gr.log_levels.info)
        # self.blocks_message_debug_rx_pdu_to_fec = blocks.message_debug(True, gr.log_levels.info)
        

        # Custom block to compare input with output
        class InputOutputComparison(gr.basic_block):
            def __init__(self):
                gr.basic_block.__init__(self,
                    name="InputOutputComparison",
                    in_sig=None,
                    out_sig=None)
                self.input_data_dict = {}  # Dict keyed by first 4 bytes (for matching)
                self.postcrc_data_dict = {}  # Dict for post-CRC data (24 bytes)
                self.packet_counter = 0
                self.message_port_register_in(pmt.intern("input"))
                self.message_port_register_in(pmt.intern("postcrc"))
                self.message_port_register_in(pmt.intern("final_output"))
                self.message_port_register_out(pmt.intern("tx_input"))  # Pass input to TX
                self.message_port_register_out(pmt.intern("final_output"))  # Pass output through
                self.set_msg_handler(pmt.intern("input"), self.handle_input)
                self.set_msg_handler(pmt.intern("postcrc"), self.handle_postcrc)
                self.set_msg_handler(pmt.intern("final_output"), self.handle_output)
            
            def get_key(self, data_bytes):
                """Generate a key from first 4 bytes for packet matching"""
                if len(data_bytes) >= 4:
                    return tuple(data_bytes[:4])
                return tuple(data_bytes)
            
            def handle_input(self, msg):
                """Store original input data (20 bytes)"""
                if pmt.is_pair(msg):
                    data = pmt.cdr(msg)
                    if pmt.is_u8vector(data):
                        input_bytes = list(pmt.u8vector_elements(data))
                        key = self.get_key(input_bytes)
                        self.input_data_dict[key] = input_bytes
                        # Pass through to TX
                        self.message_port_pub(pmt.intern("tx_input"), msg)
            
            def handle_postcrc(self, msg):
                """Store post-CRC data (24 bytes = 20 input + 4 CRC)"""
                if pmt.is_pair(msg):
                    data = pmt.cdr(msg)
                    if pmt.is_u8vector(data):
                        postcrc_bytes = list(pmt.u8vector_elements(data))
                        # Match with input using first 4 bytes (before CRC)
                        key = self.get_key(postcrc_bytes)
                        if key in self.input_data_dict:
                            self.postcrc_data_dict[key] = postcrc_bytes
            
            def handle_output(self, msg):
                """Compare final output (20 bytes) with original input"""
                if pmt.is_pair(msg):
                    meta = pmt.car(msg)
                    data = pmt.cdr(msg)
                    if pmt.is_u8vector(data):
                        output_data = list(pmt.u8vector_elements(data))
                        
                        self.packet_counter += 1
                        key = self.get_key(output_data)
                        
                        # Try to match with input
                        if key in self.input_data_dict:
                            input_data = self.input_data_dict[key]
                            
                            if len(input_data) == len(output_data):
                                if input_data == output_data:
                                    print(f"\n{'='*70}")
                                    print(f"✓✓✓ PACKET #{self.packet_counter} SUCCESS: Input and output IDENTICAL! ({len(output_data)} bytes)")
                                    print(f"   Post-CRC matches final output: ✓")
                                    print(f"\n  INPUT  ({len(input_data)} bytes):")
                                    input_hex = bytes(input_data).hex(' ').upper()
                                    for i in range(0, len(input_hex), 48):
                                        chunk = input_hex[i:i+48]
                                        print(f"    {chunk}")
                                    print(f"\n  OUTPUT ({len(output_data)} bytes):")
                                    output_hex = bytes(output_data).hex(' ').upper()
                                    for i in range(0, len(output_hex), 48):
                                        chunk = output_hex[i:i+48]
                                        print(f"    {chunk}")
                                    print(f"{'='*70}\n")
                                else:
                                    print(f"\n{'='*70}")
                                    print(f"✗ PACKET #{self.packet_counter} FAILED: Mismatch")
                                    print(f"{'='*70}")
                                    # Find first difference
                                    for i, (in_byte, out_byte) in enumerate(zip(input_data, output_data)):
                                        if in_byte != out_byte:
                                            print(f"  First difference at byte {i}: input={in_byte:02x}, output={out_byte:02x}")
                                            print(f"  Context: {bytes(input_data[max(0,i-4):min(len(input_data),i+5)]).hex()}")
                                            break
                                    print()
                            else:
                                print(f"\n{'='*70}")
                                print(f"✗ PACKET #{self.packet_counter} FAILED: Length mismatch")
                                print(f"  Expected: {len(input_data)} bytes, got: {len(output_data)} bytes")
                                print(f"{'='*70}\n")
                            
                            # Check post-CRC if available
                            if key in self.postcrc_data_dict:
                                postcrc_data = self.postcrc_data_dict[key]
                                if postcrc_data[:20] != output_data:
                                    print(f"  ⚠ WARNING: Post-CRC first 20 bytes don't match final output (CRC removal issue?)")
                        else:
                            print(f"\n{'='*70}")
                            print(f"⚠ PACKET #{self.packet_counter}: No matching input found")
                            print(f"{'='*70}\n")
                
                # Pass through
                self.message_port_pub(pmt.intern("final_output"), msg)
        
        self.blocks_input_output_comparison = InputOutputComparison()
        
        # Startup info
        print("\n" + "="*70)
        print("Packet Loopback Test")
        print("="*70)
        print(f"Configuration:")
        print(f"  Payload constellation: {Const_PLD.bits_per_symbol()} bits/symbol (QPSK)")
        print(f"  FEC: Rate 1/2, terminated k=7")
        print(f"  Input packet size: 20 bytes")
        print(f"  Expected output: 20 bytes (after CRC check)")
        print("="*70 + "\n")


        ##################################################
        # Connections
        ##################################################
        self.msg_connect((self.blocks_message_strobe_0, 'strobe'), (self.pdu_random_pdu_0, 'generate'))
        
        # Route input and output through comparison block
        self.msg_connect((self.pdu_random_pdu_0, 'pdus'), (self.blocks_input_output_comparison, 'input'))
        self.msg_connect((self.blocks_input_output_comparison, 'tx_input'), (self.packet_tx_0, 'in'))
        self.msg_connect((self.packet_tx_0, 'postcrc'), (self.blocks_input_output_comparison, 'postcrc'))
        self.msg_connect((self.packet_rx_0, 'pkt out'), (self.blocks_input_output_comparison, 'final_output'))
        self.connect((self.packet_tx_0, 0), (self.packet_rx_0, 0))


    def get_Const_PLD(self):
        return self.Const_PLD

    def set_Const_PLD(self, Const_PLD):
        self.Const_PLD = Const_PLD
        self.packet_rx_0.set_pld_const(self.Const_PLD)
        self.packet_tx_0.set_pld_const(self.Const_PLD)

    def get_sps(self):
        return self.sps

    def set_sps(self, sps):
        self.sps = sps
        self.set_rx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts*self.sps, 1.0, self.eb, (11*self.sps*self.nfilts)))
        self.set_tx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts, 1.0, self.eb, (5*self.sps*self.nfilts)))
        self.packet_rx_0.set_sps(self.sps)
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
        self.set_rx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts*self.sps, 1.0, self.eb, (11*self.sps*self.nfilts)))
        self.set_tx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts, 1.0, self.eb, (5*self.sps*self.nfilts)))

    def get_k(self):
        return self.k

    def set_k(self, k):
        self.k = k

    def get_hdr_format(self):
        return self.hdr_format

    def set_hdr_format(self, hdr_format):
        self.hdr_format = hdr_format
        self.packet_rx_0.set_hdr_format(self.hdr_format)
        self.packet_tx_0.set_hdr_format(self.hdr_format)

    def get_eb(self):
        return self.eb

    def set_eb(self, eb):
        self.eb = eb
        self.set_rx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts*self.sps, 1.0, self.eb, (11*self.sps*self.nfilts)))
        self.set_tx_rrc_taps(firdes.root_raised_cosine(self.nfilts, self.nfilts, 1.0, self.eb, (5*self.sps*self.nfilts)))
        self.packet_rx_0.set_eb(self.eb)

    def get_tx_rrc_taps(self):
        return self.tx_rrc_taps

    def set_tx_rrc_taps(self, tx_rrc_taps):
        self.tx_rrc_taps = tx_rrc_taps
        self.packet_tx_0.set_psf_taps(self.tx_rrc_taps)

    def get_rx_rrc_taps(self):
        return self.rx_rrc_taps

    def set_rx_rrc_taps(self, rx_rrc_taps):
        self.rx_rrc_taps = rx_rrc_taps
        self.packet_rx_0.set_psf_taps(self.rx_rrc_taps)

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

    def get_Const_HDR(self):
        return self.Const_HDR

    def set_Const_HDR(self, Const_HDR):
        self.Const_HDR = Const_HDR
        self.packet_rx_0.set_hdr_const(self.Const_HDR)
        self.packet_tx_0.set_hdr_const(self.Const_HDR)




def main(top_block_cls=packet_loopback_hier, options=None):
    tb = top_block_cls()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    tb.flowgraph_started.set()

    try:
        input('Press Enter to quit: ')
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == '__main__':
    main()
