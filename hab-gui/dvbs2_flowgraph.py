#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Dvbs2 Tx (Embedded Version)
# Converted from PyQt5 to PySide6, using SoapySDR for HackRF

from gnuradio import blocks
from gnuradio import dtv
from gnuradio import filter
from gnuradio.filter import firdes
from gnuradio import gr
from gnuradio import soapy
import threading
import queue
import numpy as np
import time


class Dvbs2Flowgraph(gr.top_block):
    """
    Embedded DVBS-2 transmitter flowgraph for use in PySide6 GUI.
    No GUI elements, uses SoapySDR sink for HackRF support.
    """
    
    def __init__(self, device_args, center_freq, symbol_rate, tx_gain, file_path, callback=None):
        gr.top_block.__init__(self, "DVBS-2 TX", catch_exceptions=True)
        
        self.center_freq = center_freq
        self.symbol_rate = symbol_rate
        self.tx_gain = tx_gain
        self.callback = callback
        
        # Compute sample rate (2x symbol rate for RRC filter)
        self.samp_rate = symbol_rate * 2
        
        # DVBS-2 parameters
        self.rolloff = 0.2
        self.taps = 100
        
        # Create spectrum data queue for GUI visualization
        self.spectrum_queue = queue.Queue(maxsize=10)
        
        ##################################################
        # Blocks
        ##################################################
        
        # File source - reads from TS FIFO
        self.blocks_file_source = blocks.file_source(
            gr.sizeof_char * 1, 
            file_path, 
            False, 
            0, 
            0
        )
        self.blocks_file_source.set_begin_tag(None)
        
        # DVBS-2 encoder chain
        self.dtv_dvb_bbheader = dtv.dvb_bbheader_bb(
            dtv.STANDARD_DVBS2,
            dtv.FECFRAME_NORMAL,
            dtv.C1_2,
            dtv.RO_0_20,
            dtv.INPUTMODE_NORMAL,
            dtv.INBAND_OFF,
            168,
            4000000
        )
        
        self.dtv_dvb_bbscrambler = dtv.dvb_bbscrambler_bb(
            dtv.STANDARD_DVBS2,
            dtv.FECFRAME_NORMAL,
            dtv.C1_2
        )
        
        self.dtv_dvb_bch = dtv.dvb_bch_bb(
            dtv.STANDARD_DVBS2,
            dtv.FECFRAME_NORMAL,
            dtv.C1_2
        )
        
        self.dtv_dvb_ldpc = dtv.dvb_ldpc_bb(
            dtv.STANDARD_DVBS2,
            dtv.FECFRAME_NORMAL,
            dtv.C1_2,
            dtv.MOD_OTHER
        )
        
        self.dtv_dvbs2_interleaver = dtv.dvbs2_interleaver_bb(
            dtv.FECFRAME_NORMAL,
            dtv.C1_2,
            dtv.MOD_QPSK
        )
        
        self.dtv_dvbs2_modulator = dtv.dvbs2_modulator_bc(
            dtv.FECFRAME_NORMAL,
            dtv.C1_2,
            dtv.MOD_QPSK,
            dtv.INTERPOLATION_OFF
        )
        
        self.dtv_dvbs2_physical = dtv.dvbs2_physical_cc(
            dtv.FECFRAME_NORMAL,
            dtv.C1_2,
            dtv.MOD_QPSK,
            dtv.PILOTS_ON,
            0
        )
        
        # Root raised cosine filter
        self.fft_filter = filter.fft_filter_ccc(
            1, 
            firdes.root_raised_cosine(
                1, 
                self.samp_rate, 
                self.samp_rate / 2, 
                self.rolloff, 
                self.taps
            ), 
            1
        )
        
        # SoapySDR sink for HackRF
        # Simple configuration - let SoapySDR auto-detect the device

        # The correct usage of soapy.sink (per the pybind signature) is:
        # soapy.sink(device, type, nchan, dev_args, stream_args, tune_args, other_settings)
        dev = "device=hackrf"
        chan = 1
        stream_args = ""
        tune_args = ['']
        settings = ['']
        self.soapy_sink = soapy.sink(
            dev,  # device string as required by SoapySDR (could be just "hackrf" if only one device)
            "fc32",      # data type (complex float32)
            chan,           # number of channels
            '',           # device args (empty string unless extra needed)
            stream_args,  # stream args (empty string for simple case)
            tune_args,    # tune args and other settings passed as comma-separated string (or as required)
            settings     # other settings (empty string unless extra needed)
        )
        self.soapy_hackrf_sink_0.set_sample_rate(0, self.samp_rate)
        self.soapy_hackrf_sink_0.set_bandwidth(0, 0) #auto bandwidth
        self.soapy_hackrf_sink_0.set_frequency(0, self.center_freq)
        self.soapy_hackrf_sink_0.set_gain(0, 'AMP', False) #auto gain
        self.soapy_hackrf_sink_0.set_gain(0, 'VGA', min(max(16, 0.0), 47.0)) #auto gain
        
        ##################################################
        # Connections
        ##################################################
        self.connect((self.blocks_file_source, 0), (self.dtv_dvb_bbheader, 0))
        self.connect((self.dtv_dvb_bbheader, 0), (self.dtv_dvb_bbscrambler, 0))
        self.connect((self.dtv_dvb_bbscrambler, 0), (self.dtv_dvb_bch, 0))
        self.connect((self.dtv_dvb_bch, 0), (self.dtv_dvb_ldpc, 0))
        self.connect((self.dtv_dvb_ldpc, 0), (self.dtv_dvbs2_interleaver, 0))
        self.connect((self.dtv_dvbs2_interleaver, 0), (self.dtv_dvbs2_modulator, 0))
        self.connect((self.dtv_dvbs2_modulator, 0), (self.dtv_dvbs2_physical, 0))
        self.connect((self.dtv_dvbs2_physical, 0), (self.fft_filter, 0))
        
        # Connect to SoapySDR sink
        self.connect((self.fft_filter, 0), (self.soapy_sink, 0))
        
        # TODO: Add spectrum extraction blocks here
        # For now, we'll generate dummy spectrum data
        # Future enhancement: Use splitter or head block to extract IQ samples
        # for spectrum visualization
        
        # Thread for reading spectrum data
        self.spectrum_thread = None
        self.spectrum_running = False
        
    def start(self):
        """Start the flowgraph"""
        gr.top_block.start(self)
        
        # Start spectrum extraction thread
        self.spectrum_running = True
        self.spectrum_thread = threading.Thread(target=self._spectrum_reader)
        self.spectrum_thread.daemon = True
        self.spectrum_thread.start()
    
    def _spectrum_reader(self):
        """Background thread to read spectrum data from the probe"""
        samples_per_read = 1024
        
        while self.spectrum_running:
            try:
                # TODO: Read actual spectrum data from GNURadio blocks
                # For now, generate simulated spectrum data
                time.sleep(0.05)  # ~20 Hz update rate
                
                # Generate simulated spectrum data
                # Frequency array
                freqs = np.fft.fftshift(np.fft.fftfreq(samples_per_read, 1.0 / self.samp_rate)) + self.center_freq
                
                # Generate simulated signal with some peaks
                # In real implementation, this would come from FFT of actual signal
                power_db = -120 + 30 * np.abs(np.random.randn(samples_per_read))
                
                # Add some simulated peaks
                center_index = samples_per_read // 2
                power_db[center_index - 10:center_index + 10] += 20  # Center peak
                
                try:
                    self.spectrum_queue.put_nowait((freqs, power_db))
                except queue.Full:
                    pass  # Drop frame if queue is full
                    
            except Exception as e:
                print(f"Spectrum reader error: {e}")
                break
    
    def get_spectrum_data(self):
        """Get latest spectrum data from queue"""
        try:
            return self.spectrum_queue.get_nowait()
        except queue.Empty:
            return None
    
    def stop(self):
        """Stop the flowgraph"""
        self.spectrum_running = False
        if self.spectrum_thread:
            self.spectrum_thread.join(timeout=1.0)
        gr.top_block.stop(self)
    
    def wait(self):
        """Wait for flowgraph to complete"""
        gr.top_block.wait(self)
    
    def set_frequency(self, freq):
        """Update center frequency"""
        self.center_freq = freq
        self.soapy_sink.set_freq(freq)
    
    def set_gain(self, gain):
        """Update TX gain"""
        self.tx_gain = gain
        self.soapy_sink.set_gain(gain)

