#!/usr/bin/env python3
"""
Packet HELLO Transmitter - sends 'HELLO WORLD\n' as BPSK packets.
Uses hybrid approach: pre-computed waveform → vector_source_c → throttle → SoapySDR.
"""
import numpy as np
from gnuradio import gr, blocks, soapy
from gnuradio.filter import firdes
import argparse, time, struct

FS = 2_000_000

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

def crc16(data: bytes) -> int:
    """CRC-16/XMODEM (0x1021). Returns 16-bit unsigned int."""
    crc = 0
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


def make_packet(payload_bytes, sps=20):
    """Build a complete packet waveform: preamble + sync + 2-byte len + payload + 2-byte CRC."""
    # Preamble: 256 bits alternating 1,0 for clock recovery
    preamble_bits = ([1, 0] * 128)[:256]
    # Sync word: 32-bit known pattern (GNU Radio default access code)
    sync_word = 0xE38FC0FC  # 32 bits
    sync_bits = [(sync_word >> (31 - i)) & 1 for i in range(32)]

    # 2-byte length field (big-endian)
    length = len(payload_bytes)
    len_bytes = struct.pack('>H', length)

    # CRC-16 over payload
    crc = crc16(payload_bytes)
    crc_bytes = struct.pack('>H', crc)

    def _bytes_to_bits(bs):
        bits = []
        for b in bs:
            for i in range(8):
                bits.append((b >> (7 - i)) & 1)
        return bits

    # Combine all bits: preamble + sync + len + payload + crc
    all_bits = (preamble_bits + sync_bits +
                _bytes_to_bits(len_bytes) +
                _bytes_to_bits(payload_bytes) +
                _bytes_to_bits(crc_bytes))
    return bpsk_modulate(all_bits, sps)


def make_test_packets(payload, sps=20, n_packets=20, gap_ms=50, sample_rate=FS):
    """Create a burst of test packets with gaps between them."""
    packet_waveform = np.array(make_packet(payload, sps))
    total_packet_len = len(packet_waveform)
    gap_samples = int(round(gap_ms * sample_rate / 1000.0))

    packet_ms = total_packet_len / sample_rate * 1000.0
    print(f"[PktSimpleTX] Packet: {len(payload)}B payload → {total_packet_len} samples ({packet_ms:.1f} ms)")
    print(f"[PktSimpleTX] Gap: {gap_samples} samples ({gap_ms:.1f} ms)")

    # Build burst: packet + gap, repeated
    burst = []
    for i in range(n_packets):
        if i > 0:
            burst.extend([0j] * gap_samples)
        burst.extend(packet_waveform.tolist())

    print(f"[PktSimpleTX] Total burst: {len(burst)} samples ({len(burst)/sample_rate:.3f} sec)")
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
    parser.add_argument('--message', type=str, default='HELLO WORLD',
                       help='Payload string to transmit')
    parser.add_argument('--gap', type=float, default=50,
                       help='Gap between packets in ms (0 = continuous)')
    args = parser.parse_args()

    fs = int(args.samp)
    payload = args.message.encode('utf-8')

    # Build the burst waveform (all packets pre-computed)
    burst = make_test_packets(payload, gap_ms=args.gap, sample_rate=fs)

    # Repeat the entire burst as needed
    burst_ms = len(burst) / fs * 1000
    repeat_gap = max(0, int(args.repeat * fs - len(burst)))
    full_waveform = burst + [0j] * repeat_gap

    print(f"[PktSimpleTX] Waveform cycle: {len(full_waveform)} samples ({len(full_waveform)/fs:.2f}s)")
    print(f"[PktSimpleTX] TX via GNU Radio: freq={args.freq/1e6:.3f} MHz")

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

    print(f"[PktSimpleTX] TX started: '{args.message}'. Press Ctrl-C to stop.")
    tb.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    tb.stop()
    tb.wait()
    print("[PktSimpleTX] Stopped.")


if __name__ == '__main__':
    main()
