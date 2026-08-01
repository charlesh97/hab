#!/usr/bin/env python3
"""Continuous TX: repeats a single HELLO WORLD packet with no gaps."""
import sys, os, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from pkt_enhanced_tx import make_packet_bits, bpsk_modulate
from gnuradio import gr, blocks, soapy
import time

serial = sys.argv[1] if len(sys.argv) > 1 else '000000000000000060a464dc3674640f'
fs = 2000000; sps = 20

# Single packet: preamble + sync + FEC payload
bits = make_packet_bits(b'HELLO WORLD\n')
wf = np.array(bpsk_modulate(bits, sps=sps))
print(f"Packet: {len(bits)} bits, {len(wf)} samples ({len(wf)/fs*1000:.1f}ms)", flush=True)

# Continuous repeat: no gap, just the packet over and over
full_waveform = wf.tolist()

src = blocks.vector_source_c(full_waveform, True)
thr = blocks.throttle(gr.sizeof_gr_complex, fs)
sink = soapy.sink(f'driver=hackrf,serial={serial}', 'fc32', 1, '', '', [''], [''])
sink.set_sample_rate(0, fs)
sink.set_frequency(0, 915e6)
sink.set_gain(0, 'AMP', 0.0)
sink.set_gain(0, 'VGA', 40.0)

tb = gr.top_block()
tb.connect(src, thr)
tb.connect(thr, sink)

print("TX: continuous HELLO WORLD (Ctrl-C to stop)", flush=True)
tb.start()
try:
    time.sleep(60)
except KeyboardInterrupt:
    pass
tb.stop()
tb.wait()
print("TX done", flush=True)
