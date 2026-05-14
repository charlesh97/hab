#!/usr/bin/env python3
"""
Minimal HackRF Receiver - Detects BPSK and prints signal power.
Use to verify the RX hardware sees the TX signal.
"""
import numpy as np
from gnuradio import gr, blocks, filter, soapy, analog
import argparse
import time

class signal_power_sink(gr.sync_block):
    """Simple block that prints received signal power periodically."""
    def __init__(self, label="", interval_sec=2.0):
        gr.sync_block.__init__(self, name="signal_power_sink",
                              in_sig=[np.float32],
                              out_sig=None)
        self._label = label
        self._interval = interval_sec
        self._last_print = time.time()
        self._sample_count = 0
        self._power_sum = 0.0
    
    def work(self, input_items, output_items):
        data = input_items[0]
        self._sample_count += len(data)
        self._power_sum += np.sum(data.astype(np.float64)**2)
        
        now = time.time()
        if now - self._last_print >= self._interval and self._sample_count > 0:
            avg_power = self._power_sum / self._sample_count
            print(f"[{self._label}] Power: {10*np.log10(avg_power + 1e-12):.1f} dBFS  |  "
                  f"RMS: {np.sqrt(avg_power):.4f}  |  "
                  f"Samples: {self._sample_count}")
            self._sample_count = 0
            self._power_sum = 0.0
            self._last_print = now
        return len(data)


class minimal_rx(gr.top_block):
    def __init__(self, freq=915e6, samp_rate=2e6, lna=16, vga=16, amp=False, serial=None,
                 offset=0):
        gr.top_block.__init__(self, "Minimal RX")

        samp_rate = int(samp_rate)

        # HackRF source
        dev = 'driver=hackrf'
        device_args = f'serial={serial}' if serial else ''
        src = soapy.source(dev, "fc32", 1, device_args, '', [''], [''])
        src.set_sample_rate(0, samp_rate)
        src.set_bandwidth(0, 0)
        src.set_frequency(0, freq)
        src.set_gain(0, 'AMP', 1.0 if amp else 0.0)
        src.set_gain(0, 'LNA', float(lna))
        src.set_gain(0, 'VGA', float(vga))

        rf_signal = src

        # Convert complex to float magnitude
        c2mag = blocks.complex_to_mag(1)
        self.connect(rf_signal, c2mag)

        # Low pass filter and downsample to reduce CPU
        lpf = filter.single_pole_iir_filter_ff(1.0, 1)
        decim = max(1, int(samp_rate) // 100000)
        if decim > 1:
            decimator = blocks.keep_one_in_n(gr.sizeof_float, int(decim))
            self.connect(c2mag, lpf)
            self.connect(lpf, decimator)
            self.connect(decimator, signal_power_sink(label=f"{freq/1e6:.1f}MHz"))
        else:
            self.connect(c2mag, lpf)
            self.connect(lpf, signal_power_sink(label=f"{freq/1e6:.1f}MHz"))

        print(f"[MinimalRX] Listening on {freq/1e6:.3f} MHz, {samp_rate/1e6:.1f} Msps")
        print(f"[MinimalRX] LNA={lna} dB, VGA={vga} dB, AMP={'ON' if amp else 'OFF'}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Minimal HackRF RX')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--samp', type=float, default=2e6)
    parser.add_argument('--lna', type=float, default=16)
    parser.add_argument('--vga', type=float, default=16)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--offset', type=float, default=0)
    args = parser.parse_args()

    tb = minimal_rx(freq=args.freq, samp_rate=args.samp,
                    lna=args.lna, vga=args.vga, amp=args.amp,
                    serial=args.serial, offset=args.offset)
    tb.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    tb.stop()
    tb.wait()
