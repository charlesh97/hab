#!/usr/bin/env python3
"""Layer 3 RX subprocess helper."""
import sys, os
sys.path.insert(0, os.path.expanduser('~/Documents/git/hab/rf-link/packet/src'))
from pkt_enhanced_rx import LiveReceiver
import time

serial = sys.argv[1] if len(sys.argv) > 1 else '000000000000000060a464dc3606610f'
rx = LiveReceiver(freq=915e6, lna=16, vga=20, amp=True,
                  serial=serial, duration=25,
                  sps=20, samp_rate=2000000, agc_target=0.3)
rx.run()
print(f'PACKETS_FOUND={rx.packets_found}')
