#!/usr/bin/env python3
"""Layer 3 TX subprocess helper."""
import sys, os
sys.path.insert(0, os.path.expanduser('~/Documents/git/hab/rf-link/packet/src'))
from pkt_enhanced_tx import make_test_burst
from gnuradio import gr, blocks, soapy
import time

serial = sys.argv[1] if len(sys.argv) > 1 else '000000000000000060a464dc3674640f'
burst = make_test_burst(b'LAYER3 TEST\n', n_packets=10, sps=20, fs=2000000)
full_waveform = burst + [0j] * int(0.1 * 2000000)
src = blocks.vector_source_c(full_waveform, True)
thr = blocks.throttle(gr.sizeof_gr_complex, 2000000)
sink = soapy.sink(f'driver=hackrf,serial={serial}', 'fc32', 1, '', '', [''], [''])
sink.set_sample_rate(0, 2000000)
sink.set_frequency(0, 915e6)
sink.set_gain(0, 'AMP', 0.0)
sink.set_gain(0, 'VGA', 40.0)
tb = gr.top_block()
tb.connect(src, thr)
tb.connect(thr, sink)
tb.start()
time.sleep(20)
tb.stop()
tb.wait()
print('TX_DONE')
