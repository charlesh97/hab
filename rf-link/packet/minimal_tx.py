#!/usr/bin/env python3
"""
Minimal HackRF Transmitter - Sends a repeating BPSK test pattern.
Fixed: throttle before SoapySDR sink, correct RRC filter gain.
"""
import numpy as np
from gnuradio import gr, blocks, filter, soapy
from gnuradio.filter import firdes
import argparse

class minimal_tx(gr.top_block):
    def __init__(self, freq=915e6, samp_rate=2e6, gain_vga=16, amp=True, serial=None):
        gr.top_block.__init__(self, "Minimal TX")
        
        samp_rate = int(samp_rate)
        sym_rate = 100000   # symbol rate = 100 kHz
        sps = samp_rate // sym_rate   # samples per symbol

        # Generate test symbols: BPSK values -1 and +1
        np.random.seed(42)
        bits = np.random.randint(0, 2, 10000).astype(np.float64)
        mapped = 2.0 * bits - 1.0  # 0→-1, 1→+1

        # Source: float symbols at symbol rate
        src = blocks.vector_source_f(mapped.tolist(), True, 1)

        # RRC pulse shaping with interpolation = sps
        # *** CRITICAL: gain must be sps to preserve symbol amplitude ***
        rrc_taps = firdes.root_raised_cosine(sps, sps, 1.0, 0.35, 11 * sps)
        rrc = filter.interp_fir_filter_fff(sps, rrc_taps)

        # Float to complex (I samples on real, Q = 0)
        f2c = blocks.float_to_complex(1)

        # Throttle is required before SoapySDR sink!
        throttle = blocks.throttle(gr.sizeof_gr_complex, samp_rate)

        # HackRF sink via SoapySDR
        dev = 'driver=hackrf'
        device_args = f'serial={serial}' if serial else ''
        sink = soapy.sink(dev, "fc32", 1, device_args, '', [''], [''])
        sink.set_sample_rate(0, samp_rate)
        sink.set_bandwidth(0, 0)
        sink.set_frequency(0, freq)
        sink.set_gain(0, 'AMP', 1.0 if amp else 0.0)
        sink.set_gain(0, 'VGA', float(gain_vga))

        # Connect
        self.connect(src, rrc)
        self.connect(rrc, f2c)
        self.connect(f2c, throttle)
        self.connect(throttle, sink)

        print(f"[MinimalTX] Starting on {freq/1e6:.3f} MHz, {samp_rate/1e6:.1f} Msps")
        print(f"[MinimalTX] VGA={gain_vga} dB, AMP={'ON' if amp else 'OFF'}")
        print(f"[MinimalTX] Symbol rate: {sym_rate/1e3:.1f} ksym/s, sps={sps}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Minimal HackRF TX')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--samp', type=float, default=2e6)
    parser.add_argument('--vga', type=float, default=16)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    args = parser.parse_args()

    tb = minimal_tx(freq=args.freq, samp_rate=args.samp,
                    gain_vga=args.vga, amp=args.amp, serial=args.serial)
    tb.start()
    try:
        input("TX running. Press Enter to stop...\n")
    except:
        pass
    tb.stop()
    tb.wait()
