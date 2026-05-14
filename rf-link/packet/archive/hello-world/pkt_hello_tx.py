#!/usr/bin/env python3
"""
Packet HELLO Transmitter - sends 'HELLO WORLD\n' as BPSK packets.
Uses hybrid approach: pre-computed waveform → vector_source_c → throttle → SoapySDR.
"""
import numpy as np
from gnuradio import gr, blocks, soapy
from gnuradio.filter import firdes
import argparse, time, struct

def bpsk_modulate(bits, sps=20, rrc_alpha=0.35):
    """Convert bits (list of 0/1 ints) to RRC-shaped BPSK complex waveform."""
    # BPSK map: 0→+1, 1→-1
    mapped = np.array(bits, dtype=np.float64) * -2.0 + 1.0
    # Upsample
    up = np.zeros(len(mapped) * sps, dtype=np.float64)
    up[::sps] = mapped
    # RRC filter
    taps = firdes.root_raised_cosine(sps, sps, 1.0, rrc_alpha, 11 * sps)
    taps_np = np.array(taps)
    waveform = np.convolve(up, taps_np, 'same')
    # Scale to avoid clipping
    peak = np.max(np.abs(waveform))
    if peak > 0.7:
        waveform = waveform * (0.7 / peak)
    return waveform.astype(np.complex64).tolist()

def make_packet(payload_bytes, sps=20):
    """Build a complete packet waveform: preamble + sync + payload."""
    # Preamble: 256 bits alternating 1,0 for clock recovery
    preamble_bits = ([1, 0] * 128)[:256]
    # Sync word: 32-bit known pattern (GNU Radio default access code)
    sync_word = 0xE38FC0FC  # 32 bits
    sync_bits = [(sync_word >> (31 - i)) & 1 for i in range(32)]
    # Payload: byte stream → bits MSB first
    payload_bits = []
    for b in payload_bytes:
        for i in range(8):
            payload_bits.append((b >> (7 - i)) & 1)
    # Combine all bits
    all_bits = preamble_bits + sync_bits + payload_bits
    return bpsk_modulate(all_bits, sps)


def make_test_packets(sps=20, n_packets=20, gap_ms=50):
    """Create a burst of test packets with gaps between them."""
    payload = b"HELLO WORLD\n"
    packet_waveform = np.array(make_packet(payload, sps))
    total_packet_len = len(packet_waveform)
    gap_samples = int(gap_ms * 2000 / 1000)  # at 2 Msps
    
    print(f"[PktHelloTX] Packet: {len(payload)} bytes payload")
    print(f"[PktHelloTX] Waveform: {total_packet_len} samples ({total_packet_len/2000:.1f} ms)")
    print(f"[PktHelloTX] Gap: {gap_samples} samples ({gap_ms} ms)")
    
    # Build burst: packet + gap, repeated
    burst = []
    for i in range(n_packets):
        if i > 0:
            burst.extend([0j] * gap_samples)
        burst.extend(packet_waveform.tolist())
    
    print(f"[PktHelloTX] Total burst: {len(burst)} samples ({len(burst)/2000:.1f} sec)")
    return burst


def main():
    parser = argparse.ArgumentParser(description='Packet HELLO TX')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--samp', type=float, default=2e6)
    parser.add_argument('--vga', type=float, default=30)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--repeat', type=float, default=2.0,
                       help='Seconds between packet bursts')
    args = parser.parse_args()

    fs = int(args.samp)
    
    # Build the burst waveform (all packets pre-computed)
    burst = make_test_packets()

    # Repeat the entire burst as needed
    burst_ms = len(burst) / fs * 1000
    repeat_gap = max(0, int(args.repeat * fs - len(burst)))
    full_waveform = burst + [0j] * repeat_gap
    
    print(f"[PktHelloTX] Waveform cycle: {len(full_waveform)} samples ({len(full_waveform)/fs:.2f}s)")
    print(f"[PktHelloTX] TX via GNU Radio: freq={args.freq/1e6:.3f} MHz")

    # GNU Radio chain
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

    print(f"[PktHelloTX] TX started. Sending '{'HELLO WORLD'}'. Press Ctrl-C to stop.")
    tb.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    tb.stop()
    tb.wait()
    print("[PktHelloTX] Stopped.")


if __name__ == '__main__':
    main()
