#!/usr/bin/env python3
"""
GNU Radio BPSK Receiver - uses built-in blocks for clock recovery & demod.
Captures via SoapySDR then pipes through pfb_clock_sync → costas → binary_slicer
"""
from gnuradio import gr, blocks, digital, filter, soapy, analog
from gnuradio.filter import firdes
import numpy as np
import argparse, time

class bpsk_gr_rx(gr.top_block):
    def __init__(self, freq=915e6, samp_rate=2e6, lna=16, vga=20, amp=False,
                 serial=None, offset_khz=6.5, sps=20):
        gr.top_block.__init__(self, "BPSK GR RX")
        
        sr = int(samp_rate)
        
        # Source
        dev = 'driver=hackrf'
        dev_args = f'serial={serial}' if serial else ''
        src = soapy.source(dev, "fc32", 1, dev_args, '', [''], [''])
        src.set_sample_rate(0, sr)
        src.set_bandwidth(0, 0)
        src.set_frequency(0, freq)
        src.set_gain(0, 'AMP', 1.0 if amp else 0.0)
        src.set_gain(0, 'LNA', float(lna))
        src.set_gain(0, 'VGA', float(vga))
        
        # Frequency correction (coarse)
        if abs(offset_khz) > 0:
            nco = analog.sig_source_c(sr, analog.GR_COS_WAVE, offset_khz*1000, 1.0, 0.0)
            mixer = blocks.multiply_cc()
            self.connect(src, (mixer, 0))
            self.connect(nco, (mixer, 1))
            rf_in = mixer
        else:
            rf_in = src
        
        # AGC to normalize signal level
        agc = blocks.agc3_cc(1e-2, 1e-2, 1e-4, 1)
        
        # RRC matched filter
        rrc_taps = firdes.root_raised_cosine(1.0, sr, 100e3, 0.35, 11*sps)
        rrc = filter.interp_fir_filter_ccc(1, rrc_taps)
        
        # Clock recovery (polyphase filterbank)
        clock_sync = digital.pfb_clock_sync_ccf(sps, 2*np.pi/200.0, 
                                                 rrc_taps, 32, 16, 1.5, 1.0)
        
        # Costas loop for carrier recovery (BPSK = 2)
        costas = digital.costas_loop_cc(2*np.pi/200.0, 2, False)
        
        # Binary slicer: decodes BPSK symbols to bits
        slicer = digital.binary_slicer_fb()
        
        # Debug: vector sinks
        self._const_sink = blocks.vector_sink_c()
        self._bit_sink = blocks.vector_sink_b()
        
        # Connect
        self.connect(rf_in, agc)
        self.connect(agc, rrc)
        self.connect(rrc, clock_sync)
        self.connect(clock_sync, costas)
        self.connect(costas, self._const_sink)
        
        if 0:  # No built-in conversion
            pass
        
        print(f"[BPSK GR RX] Listening: {freq/1e6:.3f} MHz, {sr/1e6:.1f} Msps")
        print(f"[BPSK GR RX] LNA={lna}, VGA={vga}, AMP={'ON' if amp else 'OFF'}")
        print(f"[BPSK GR RX] Offset: {offset_khz} kHz")
    
    def get_constellation(self):
        return np.array(self._const_sink.data())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='GNU Radio BPSK RX')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--samp', type=float, default=2e6)
    parser.add_argument('--lna', type=float, default=8)
    parser.add_argument('--vga', type=float, default=12)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--offset', type=float, default=0.0)
    args = parser.parse_args()
    
    tb = bpsk_gr_rx(freq=args.freq, samp_rate=args.samp, lna=args.lna, 
                    vga=args.vga, amp=args.amp, serial=args.serial,
                    offset_khz=args.offset)
    tb.start()
    
    try:
        for i in range(30):
            time.sleep(1)
            const = tb.get_constellation()
            if len(const) > 100:
                syms = const[-5000:]
                I = syms.real
                Q = syms.imag
                iqr = np.percentile(I, 75) - np.percentile(I, 25)
                qqr = np.percentile(Q, 75) - np.percentile(Q, 25)
                mean_i = np.mean(I)
                std_i = np.std(I)
                # BPSK should show two clusters
                h, edges = np.histogram(I, bins=15)
                peaks = np.sum(h > len(I)/15)  # count bins above average
                print(f"[t={i}s] {len(const)} syms  I={mean_i:+.3f}±{std_i:.3f} "
                      f"IQR={iqr:.3f} Q_IQR={qqr:.3f} hist_peaks={peaks}")
    except KeyboardInterrupt:
        pass
    
    tb.stop()
    tb.wait()
