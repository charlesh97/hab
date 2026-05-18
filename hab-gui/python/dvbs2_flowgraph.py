#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Dvbs2 Tx (Embedded Version)
# Converted from PyQt5 to PySide6, using SoapySDR for HackRF
#
# FIXED: Corrected sink name (soapy_hackrf_sink_0 → soapy_sink)
# FIXED: Corrected set_freq → set_frequency
# FIXED: set_frequency → set_frequency + set_sample_rate + set_gain via unified method
# ADDED: Real FFT spectrum extraction blocks connected to a data queue
# ADDED: Configurable frequency, symbol rate, gain from constructor

from gnuradio import blocks, dtv, fft, filter
from gnuradio.fft import window as gr_window
from gnuradio.filter import firdes
from gnuradio import gr
from gnuradio import soapy
import threading
import queue
import numpy as np
import time
import logging

logger = logging.getLogger(__name__)


class Dvbs2Flowgraph(gr.top_block):
    """
    Embedded DVBS-2 transmitter flowgraph for use in PySide6 GUI.
    No GUI elements, uses SoapySDR sink for HackRF support.
    Includes real FFT spectrum extraction.
    """

    def __init__(self,
                 device_args: str = "driver=hackrf",
                 center_freq: float = 915e6,
                 symbol_rate: float = 1e6,
                 tx_gain_vga: float = 16.0,
                 tx_gain_amp: bool = False,
                 file_path: str = "/tmp/tsfifo",
                 rolloff: float = 0.2,
                 modcod: str = "QPSK1/2",
                 pilots: bool = True):
        gr.top_block.__init__(self, "DVBS-2 TX", catch_exceptions=True)

        self.center_freq = center_freq
        self.symbol_rate = symbol_rate
        self.tx_gain_vga = tx_gain_vga
        self.tx_gain_amp = tx_gain_amp
        self.rolloff = rolloff
        self.pilots = pilots

        # Sample rate = 2x symbol rate for RRC filter
        self.samp_rate = symbol_rate * 2

        # FFT parameters for spectrum display
        self.fft_size = 1024
        self.fft_update_interval = 0.05  # 20 Hz

        # Spectrum data queue (thread-safe, drops stale frames)
        self.spectrum_queue = queue.Queue(maxsize=5)

        # Map modcod string to DVB-S2 constants
        self._modcod_map = {
            "QPSK1/2":  (dtv.C1_2, dtv.MOD_QPSK),
            "QPSK3/5":  (dtv.C3_5, dtv.MOD_QPSK),
            "QPSK2/3":  (dtv.C2_3, dtv.MOD_QPSK),
            "QPSK3/4":  (dtv.C3_4, dtv.MOD_QPSK),
            "QPSK4/5":  (dtv.C4_5, dtv.MOD_QPSK),
            "QPSK5/6":  (dtv.C5_6, dtv.MOD_QPSK),
            "QPSK8/9":  (dtv.C8_9, dtv.MOD_QPSK),
            "QPSK9/10": (dtv.C9_10, dtv.MOD_QPSK),
            "8PSK3/5":  (dtv.C3_5, dtv.MOD_8PSK),
            "8PSK2/3":  (dtv.C2_3, dtv.MOD_8PSK),
            "8PSK3/4":  (dtv.C3_4, dtv.MOD_8PSK),
            "8PSK5/6":  (dtv.C5_6, dtv.MOD_8PSK),
            "8PSK8/9":  (dtv.C8_9, dtv.MOD_8PSK),
            "8PSK9/10": (dtv.C9_10, dtv.MOD_8PSK),
        }

        code_rate, constellation = self._modcod_map.get(
            modcod.upper().replace("-", "").replace("/", ""),
            (dtv.C1_2, dtv.MOD_QPSK)  # default QPSK 1/2
        )

        pilots_mode = dtv.PILOTS_ON if pilots else dtv.PILOTS_OFF
        fec_frame = dtv.FECFRAME_NORMAL
        rolloff_const = dtv.RO_0_20

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

        # DVBS-2 encoder chain
        self.dtv_dvb_bbheader = dtv.dvb_bbheader_bb(
            dtv.STANDARD_DVBS2,
            fec_frame,
            code_rate,
            rolloff_const,
            dtv.INPUTMODE_NORMAL,
            dtv.INBAND_OFF,
            168,
            4000000
        )

        self.dtv_dvb_bbscrambler = dtv.dvb_bbscrambler_bb(
            dtv.STANDARD_DVBS2,
            fec_frame,
            code_rate
        )

        self.dtv_dvb_bch = dtv.dvb_bch_bb(
            dtv.STANDARD_DVBS2,
            fec_frame,
            code_rate
        )

        self.dtv_dvb_ldpc = dtv.dvb_ldpc_bb(
            dtv.STANDARD_DVBS2,
            fec_frame,
            code_rate,
            dtv.MOD_OTHER
        )

        self.dtv_dvbs2_interleaver = dtv.dvbs2_interleaver_bb(
            fec_frame,
            code_rate,
            constellation
        )

        self.dtv_dvbs2_modulator = dtv.dvbs2_modulator_bc(
            fec_frame,
            code_rate,
            constellation,
            dtv.INTERPOLATION_OFF
        )

        self.dtv_dvbs2_physical = dtv.dvbs2_physical_cc(
            fec_frame,
            code_rate,
            constellation,
            pilots_mode,
            0
        )

        # Root raised cosine filter
        rrc_taps = firdes.root_raised_cosine(
            1, self.samp_rate, self.samp_rate / 2, self.rolloff, 100
        )
        self.fft_filter = filter.fft_filter_ccc(1, rrc_taps, 1)

        # SoapySDR sink for HackRF
        self.soapy_sink = soapy.sink(
            device_args,    # device string
            "fc32",         # data type (complex float32)
            1,              # number of channels
            '',             # device args
            '',             # stream args
            [''],           # tune args
            ['']            # other settings
        )
        self.soapy_sink.set_sample_rate(0, self.samp_rate)
        self.soapy_sink.set_bandwidth(0, 0)  # auto bandwidth
        self.soapy_sink.set_frequency(0, self.center_freq)
        self.soapy_sink.set_gain(0, 'AMP', self.tx_gain_amp)
        self.soapy_sink.set_gain(0, 'VGA', min(max(self.tx_gain_vga, 0.0), 47.0))

        # ── Spectrum Extraction Blocks ──
        # Tap the modulated signal BEFORE the RRC filter for spectrum display
        # (signal at this point is after physical layer framing, clean constellation)
        #
        # Note: We tap after the physical layer but before the RRC filter because
        # the signal shape at that point better shows the modulation spectrum.
        # Alternatively, tap after the RRC filter for the transmitted spectrum.

        # For actual transmitted spectrum, tap after the RRC filter:
        self.spectrum_splitter = blocks.nop(gr.sizeof_gr_complex * 1)

        # FFT blocks
        self.spectrum_stream_to_vector = blocks.stream_to_vector(
            gr.sizeof_gr_complex, self.fft_size
        )
        self.spectrum_fft = fft.fft_vcc(
            self.fft_size,
            True,                                  # forward FFT
            gr_window.blackmanharris(self.fft_size),  # window
            True,                                  # shift (center DC)
            1                                      # number of threads
        )
        self.spectrum_c2mag = blocks.complex_to_mag_squared(
            self.fft_size
        )
        self.spectrum_vector_sink = blocks.vector_sink_f(
            self.fft_size
        )

        ##################################################
        # Connections
        ##################################################
        # Main DVBS2 chain
        self.connect((self.blocks_file_source, 0), (self.dtv_dvb_bbheader, 0))
        self.connect((self.dtv_dvb_bbheader, 0), (self.dtv_dvb_bbscrambler, 0))
        self.connect((self.dtv_dvb_bbscrambler, 0), (self.dtv_dvb_bch, 0))
        self.connect((self.dtv_dvb_bch, 0), (self.dtv_dvb_ldpc, 0))
        self.connect((self.dtv_dvb_ldpc, 0), (self.dtv_dvbs2_interleaver, 0))
        self.connect((self.dtv_dvbs2_interleaver, 0), (self.dtv_dvbs2_modulator, 0))
        self.connect((self.dtv_dvbs2_modulator, 0), (self.dtv_dvbs2_physical, 0))
        self.connect((self.dtv_dvbs2_physical, 0), (self.fft_filter, 0))
        self.connect((self.fft_filter, 0), (self.soapy_sink, 0))

        # Spectrum extraction chain (tap after RRC filter = transmitted spectrum)
        self.connect((self.fft_filter, 0), (self.spectrum_splitter, 0))
        self.connect((self.spectrum_splitter, 0), (self.spectrum_stream_to_vector, 0))
        self.connect((self.spectrum_stream_to_vector, 0), (self.spectrum_fft, 0))
        self.connect((self.spectrum_fft, 0), (self.spectrum_c2mag, 0))
        self.connect((self.spectrum_c2mag, 0), (self.spectrum_vector_sink, 0))

        ##################################################
        # Threading
        ##################################################
        self._spectrum_thread = None
        self._spectrum_running = False

    def start(self):
        """Start the flowgraph and spectrum thread"""
        gr.top_block.start(self)
        self._spectrum_running = True
        self._spectrum_thread = threading.Thread(
            target=self._spectrum_reader, daemon=True
        )
        self._spectrum_thread.start()

    def _spectrum_reader(self):
        """Background thread to read real FFT data from the vector sink"""
        while self._spectrum_running:
            time.sleep(self.fft_update_interval)
            try:
                data = np.array(self.spectrum_vector_sink.data())
                if len(data) < self.fft_size:
                    continue

                # Get the most recent FFT frame
                fft_data = data[-self.fft_size:]

                # Convert to dB with noise floor protection
                power_db = 10.0 * np.log10(np.maximum(fft_data, 1e-15))

                # FFT was already shifted, but generate frequency bins
                freq_bins = np.fft.fftshift(
                    np.fft.fftfreq(self.fft_size, 1.0 / self.samp_rate)
                )
                frequencies = self.center_freq + freq_bins

                # Clear the vector sink to keep only the latest frame
                self.spectrum_vector_sink.reset()

                try:
                    self.spectrum_queue.put_nowait((frequencies, power_db))
                except queue.Full:
                    # Drain and put fresh
                    try:
                        self.spectrum_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self.spectrum_queue.put_nowait((frequencies, power_db))

            except Exception as e:
                logger.error(f"Spectrum reader error: {e}")

    def get_spectrum_data(self):
        """Get latest spectrum data from queue (non-blocking)"""
        try:
            return self.spectrum_queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        """Stop the flowgraph"""
        self._spectrum_running = False
        if self._spectrum_thread and self._spectrum_thread.is_alive():
            self._spectrum_thread.join(timeout=1.0)
        gr.top_block.stop(self)

    def wait(self):
        """Wait for flowgraph to complete"""
        gr.top_block.wait(self)

    def reconfigure(self, center_freq=None, symbol_rate=None, tx_gain_vga=None,
                    tx_gain_amp=None):
        """Reconfigure parameters while running (where supported)"""
        if center_freq is not None:
            self.center_freq = center_freq
            self.soapy_sink.set_frequency(0, self.center_freq)
        if symbol_rate is not None:
            self.symbol_rate = symbol_rate
            self.samp_rate = symbol_rate * 2
            self.soapy_sink.set_sample_rate(0, self.samp_rate)
            # Note: full reconfig would require lock
        if tx_gain_vga is not None:
            self.tx_gain_vga = tx_gain_vga
            self.soapy_sink.set_gain(0, 'VGA', min(max(tx_gain_vga, 0.0), 47.0))
        if tx_gain_amp is not None:
            self.tx_gain_amp = tx_gain_amp
            self.soapy_sink.set_gain(0, 'AMP', tx_gain_amp)
