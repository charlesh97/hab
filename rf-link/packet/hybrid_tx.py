#!/usr/bin/env python3
"""
Hybrid HackRF Transmitter - Pre-computes BPSK waveform with numpy,
then feeds via GNU Radio vector_source_c → throttle → SoapySDR sink.
"""
import numpy as np
from gnuradio import gr, blocks, soapy
from gnuradio.filter import firdes
import argparse, time

class hybrid_tx(gr.top_block):
    def __init__(self, freq=915e6, samp_rate=2e6, gain_vga=30, amp=True, serial=None):
        gr.top_block.__init__(self, "Hybrid TX")
        
        samp_rate = int(samp_rate)
        sym_rate = 100000
        sps = samp_rate // sym_rate

        print(f"[HybridTX] Building BPSK waveform...")
        
        # Generate test pattern (PN9-like)
        np.random.seed(42)
        n_syms = sym_rate // 2  # 0.5 seconds per repeat
        bits = np.random.randint(0, 2, n_syms).astype(np.float64)
        mapped = 2.0 * bits - 1.0  # BPSK: {+1, -1}

        # Upsample and RRC filter (same as working native Soapy test)
        upsampled = np.zeros(n_syms * sps, dtype=np.float64)
        upsampled[::sps] = mapped
        rrc_taps = np.array(firdes.root_raised_cosine(sps, sps, 1.0, 0.35, 11*sps))
        waveform = np.convolve(upsampled, rrc_taps, 'same')
        waveform_c = (waveform.astype(np.complex64) * 0.7).tolist()

        print(f"[HybridTX] Waveform: {len(waveform_c)} samples, max={max(abs(x) for x in waveform_c):.3f}")

        # GNU Radio chain: vector_source_c → throttle → soapy.sink
        src = blocks.vector_source_c(waveform_c, True)  # repeat
        thr = blocks.throttle(gr.sizeof_gr_complex, samp_rate)

        sink = soapy.sink('driver=hackrf', 'fc32', 1, 
                          f'serial={serial}' if serial else '', '', [''], [''])
        sink.set_sample_rate(0, samp_rate)
        sink.set_bandwidth(0, 0)
        sink.set_frequency(0, freq)
        sink.set_gain(0, 'AMP', 1.0 if amp else 0.0)
        sink.set_gain(0, 'VGA', float(gain_vga))

        self.connect(src, thr)
        self.connect(thr, sink)

        print(f"[HybridTX] Starting: {freq/1e6:.3f} MHz, {samp_rate/1e6:.1f} Msps")
        print(f"[HybridTX] VGA={gain_vga} dB, AMP={'ON' if amp else 'OFF'}")

    def stop(self):
        # Graceful stop
        try:
            gr.top_block.stop(self)
            gr.top_block.wait(self)
        except:
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hybrid HackRF TX')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--samp', type=float, default=2e6)
    parser.add_argument('--vga', type=float, default=30)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    args = parser.parse_args()

    tb = hybrid_tx(freq=args.freq, samp_rate=args.samp,
                   gain_vga=args.vga, amp=args.amp, serial=args.serial)
    tb.start()
    try:
        input("TX running. Press Enter to stop...\n")
    except:
        pass
    tb.stop()
