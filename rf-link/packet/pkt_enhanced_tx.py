#!/usr/bin/env python3
"""
Enhanced Packet Transmitter — CRC-32 + FEC protected BPSK packets.

Packet structure (aligned to original):
  [ preamble (24 bytes / 192 bits) ] [ sync word (4 bytes / 32 bits) ]
  [ FEC payload ]

Preamble: 0xE38FC0FC7FC7E381C0FF8038FFF038E00FC0038000FFFFC0 (from packet_rx.py)
Sync word: 0xE38FC0FC (first 4 bytes of preamble — same as original working TX)

Combined preamble+sync gives SHARP correlation with no false peaks.
"""
import numpy as np
from gnuradio import gr, blocks, soapy
from gnuradio.filter import firdes
import argparse, time
from packet_codec import packet_encode, encode_size_for_payload

SPS = 20
FS = 2_000_000
RRC_ALPHA = 0.35

# ── Original preamble from packet_rx.py ─────────────────────
PREAMBLE_BYTES = bytes([
    0xe3, 0x8f, 0xc0, 0xfc, 0x7f, 0xc7, 0xe3, 0x81,
    0xc0, 0xff, 0x80, 0x38, 0xff, 0xf0, 0x38, 0xe0,
    0x0f, 0xc0, 0x03, 0x80, 0x00, 0xff, 0xff, 0xc0
])  # 24 bytes = 192 bits

# Sync word: GNU Radio default access code (from preamble_dummy in packet_rx.py)
# This is DIFFERENT from the first 4 bytes of the preamble, giving unambiguous
# correlation.
SYNC_WORD = 0xACDDA4E2


def make_preamble_bits():
    """Convert PREAMBLE_BYTES to a bit list (MSB first)."""
    bits = []
    for b in PREAMBLE_BYTES:
        for i in range(8):
            bits.append((b >> (7 - i)) & 1)
    return bits


def make_sync_bits():
    """Convert SYNC_WORD to a bit list (MSB first)."""
    return [(SYNC_WORD >> (31 - i)) & 1 for i in range(32)]


def bpsk_modulate(bits, sps=SPS, alpha=RRC_ALPHA):
    """Convert bits (list of 0/1) to RRC-shaped BPSK complex waveform."""
    mapped = np.array(bits, dtype=np.float64) * -2.0 + 1.0
    up = np.zeros(len(mapped) * sps, dtype=np.float64)
    up[::sps] = mapped
    taps = np.array(firdes.root_raised_cosine(sps, sps, 1.0, alpha, 11 * sps))
    waveform = np.convolve(up, taps, 'same')
    peak = np.max(np.abs(waveform))
    if peak > 0.7:
        waveform *= 0.7 / peak
    return waveform.astype(np.complex64).tolist()


def make_packet_bits(payload_bytes):
    """Build full packet bit stream: preamble + sync + FEC payload."""
    preamble_bits = make_preamble_bits()
    sync_bits = make_sync_bits()
    fec_bytes = packet_encode(payload_bytes)
    payload_bits = []
    for b in fec_bytes:
        for i in range(8):
            payload_bits.append((b >> (7 - i)) & 1)
    return preamble_bits + sync_bits + payload_bits


def make_test_burst(payload, n_packets=20, gap_ms=50):
    """Build a burst of multiple packets with gaps."""
    bits = make_packet_bits(payload)
    waveform = np.array(bpsk_modulate(bits))
    gap_samples = int(gap_ms * FS / 1000)

    fec_len = encode_size_for_payload(len(payload))
    print(f"[EnhancedTX] Payload: {len(payload)}B → FEC: {fec_len}B "
          f"({len(bits)} packet bits, {len(waveform)/FS*1000:.1f} ms)")

    burst = []
    for i in range(n_packets):
        if i > 0:
            burst.extend([0j] * gap_samples)
        burst.extend(waveform.tolist())

    print(f"[EnhancedTX] Burst: {n_packets} packets, "
          f"{len(burst)} samples ({len(burst)/FS:.1f}s)")
    return burst


def main():
    parser = argparse.ArgumentParser(description='Enhanced Packet TX (CRC+FEC)')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--samp', type=float, default=2e6)
    parser.add_argument('--vga', type=float, default=30)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--repeat', type=float, default=2.0)
    parser.add_argument('--message', type=str, default='HELLO WORLD')
    parser.add_argument('--n-packets', type=int, default=20)
    args = parser.parse_args()

    fs = int(args.samp)
    payload = (args.message + '\n').encode('ascii')
    burst = make_test_burst(payload, n_packets=args.n_packets)

    repeat_gap = max(0, int(args.repeat * fs - len(burst)))
    full_waveform = burst + [0j] * repeat_gap
    print(f"[EnhancedTX] Cycle: {len(full_waveform)} samples "
          f"({len(full_waveform)/fs:.2f}s)")

    src = blocks.vector_source_c(full_waveform, True)
    thr = blocks.throttle(gr.sizeof_gr_complex, fs)
    sink = soapy.sink('driver=hackrf', 'fc32', 1,
                      f'serial={args.serial}' if args.serial else '',
                      '', [''], [''])
    sink.set_sample_rate(0, fs)
    sink.set_bandwidth(0, 0)
    sink.set_frequency(0, args.freq)
    sink.set_gain(0, 'AMP', 1.0 if args.amp else 0.0)
    sink.set_gain(0, 'VGA', float(args.vga))

    tb = gr.top_block()
    tb.connect(src, thr)
    tb.connect(thr, sink)

    print(f"[EnhancedTX] TX started. Press Ctrl-C to stop.")
    tb.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    tb.stop()
    tb.wait()
    print("[EnhancedTX] Stopped.")


if __name__ == '__main__':
    main()
