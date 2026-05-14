#!/usr/bin/env python3
"""
BPSK Receiver for HackRF - captures and demodulates signals
"""
import numpy as np
from gnuradio import gr, blocks, digital, filter, soapy, analog
from gnuradio.filter import firdes
import argparse, time

class bpsk_rx(gr.top_block):
    def __init__(self, freq=915e6, samp_rate=2e6, lna=16, vga=16, amp=False, 
                 serial=None, offset_khz=7):
        gr.top_block.__init__(self, "BPSK RX")
        
        samp_rate = int(samp_rate)
        sym_rate = 100000   # must match TX
        sps = samp_rate // sym_rate

        # HackRF source
        dev = 'driver=hackrf'
        dev_args = f'serial={serial}' if serial else ''
        src = soapy.source(dev, "fc32", 1, dev_args, '', [''], [''])
        src.set_sample_rate(0, samp_rate)
        src.set_bandwidth(0, 0)
        src.set_frequency(0, freq)
        src.set_gain(0, 'AMP', 1.0 if amp else 0.0)
        src.set_gain(0, 'LNA', float(lna))
        src.set_gain(0, 'VGA', float(vga))

        # Frequency correction for LO offset
        offset_rad = 2.0 * np.pi * offset_khz * 1000.0 / samp_rate
        nco = analog.sig_source_c(samp_rate, analog.GR_COS_WAVE, 
                                  offset_khz * 1000.0, 1.0, 0.0)
        mixer = blocks.multiply_cc()
        self.connect(src, (mixer, 0))
        self.connect(nco, (mixer, 1))

        # RRC matched filter
        rrc_taps = firdes.root_raised_cosine(1.0, sps, 1.0, 0.35, 11 * sps)
        rrc = filter.interp_fir_filter_ccc(1, rrc_taps)

        # Clock recovery
        clock_sync = digital.pfb_clock_sync_ccf(sps, 0.01, rrc_taps, 32, 16, 1.5, 1.0)
        
        # Costas loop for carrier recovery (BPSK = 2nd order)
        costas = digital.costas_loop_cc(0.01, 2, False)
        
        # Binary slicer (hard decision)
        slicer = digital.binary_slicer_fb()

        # Debug: print constellation points
        self._const_sink = blocks.vector_sink_c()

        # Connect
        self.connect(mixer, rrc)
        self.connect(rrc, clock_sync)
        self.connect(clock_sync, costas)
        self.connect(costas, blocks.complex_to_arg(1))  # phase
        self.connect(costas, self._const_sink)
        
        print(f"[BPSK RX] Listening on {freq/1e6:.3f} MHz, {samp_rate/1e6:.1f} Msps")
        print(f"[BPSK RX] LNA={lna}, VGA={vga}, offset={offset_khz} kHz")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BPSK HackRF RX')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--samp', type=float, default=2e6)
    parser.add_argument('--lna', type=float, default=20)
    parser.add_argument('--vga', type=float, default=20)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--offset', type=float, default=7.0, help='Frequency offset kHz')
    args = parser.parse_args()

    tb = bpsk_rx(freq=args.freq, samp_rate=args.samp, lna=args.lna, vga=args.vga,
                 amp=args.amp, serial=args.serial, offset_khz=args.offset)
    tb.start()
    
    try:
        # Monitor constellation
        for i in range(30):
            time.sleep(1)
            data = tb._const_sink.data()
            if len(data) > 0:
                syms = np.array(data[-5000:])
                power = np.mean(np.abs(syms)**2)
                phase = np.angle(np.mean(syms)) if len(syms) > 0 else 0
                print(f"[const] pts={min(5000, len(syms))}  power={10*np.log10(power+1e-12):.1f} dB  phase={np.degrees(phase):.0f} deg  "
                      f"I={np.mean(syms.real):+.4f}  Q={np.mean(syms.imag):+.4f}")
    except KeyboardInterrupt:
        pass
    
    tb.stop()
    tb.wait()
