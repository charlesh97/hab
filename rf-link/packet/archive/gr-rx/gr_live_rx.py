#!/usr/bin/env python3
"""
GNU Radio Live BPSK Receiver
=============================
Captures from HackRF via GNU Radio soapy.source (with native SoapySDR fallback).
Digital chain: AGC → RRC matched filter → pfb_clock_sync → costas_loop → binary_slicer.
Decodes "HELLO WORLD" packets from recovered bit stream.

Packet structure (matching pkt_hello_tx.py):
  [256-bit preamble (alt 1,0)] [32-bit sync word 0xE38FC0FC] [12-byte payload]

Usage:
    python3.14 gr_live_rx.py --freq 915e6 --samp 2e6 --lna 8 --vga 12 --offset 5.2

On finding HELLO/WORLD/ELLO, prints "SUCCESS: ..." and exits.
"""
import argparse
import time
import sys
import numpy as np
from gnuradio import gr, blocks, digital, filter, analog, soapy
from gnuradio.filter import firdes

# ── Packet constants (must match pkt_hello_tx.py) ──────────────────────────
SPS = 20
SYNC_WORD = 0xE38FC0FC
SYNC_BITS_N = 32
PREAMBLE_BITS_N = 256
PAYLOAD_BYTES_N = 12  # "HELLO WORLD\n"
PAYLOAD_BITS_N = PAYLOAD_BYTES_N * 8
PACKET_BITS_N = PREAMBLE_BITS_N + SYNC_BITS_N + PAYLOAD_BITS_N
SUCCESS_KEYWORDS = ["HELLO", "WORLD", "ELLO"]
RX_TIMEOUT = 30  # seconds


# ═══════════════════════════════════════════════════════════════════════════
#  Cross-correlation based packet detector
# ═══════════════════════════════════════════════════════════════════════════
class PacketDetector:
    """Find packets in a stream of sliced bits (0/1 as uint8)."""

    def __init__(self):
        # Sync word as [+1/-1] sequence for correlation
        sync_raw = np.array(
            [(SYNC_WORD >> (31 - i)) & 1 for i in range(SYNC_BITS_N)],
            dtype=np.float64,
        )
        self.sync_pm = 2.0 * sync_raw - 1.0  # 0→-1, 1→+1

        # Alternating preamble template for verification
        self.preamble_template = np.tile(np.array([1, 0], dtype=np.int8), 128)

    def find_packets(self, bit_arr):
        """
        Search for preamble + sync word in a 0/1 bit array.
        Returns list of (payload_bit_index, is_inverted, payload_bytes).
        """
        results = []
        n = len(bit_arr)
        if n < PACKET_BITS_N:
            return results

        bits = np.asarray(bit_arr, dtype=np.float64).flatten()

        for invert in (False, True):
            # Invert polarity if needed (costas π ambiguity)
            probe = 1.0 - bits if invert else bits.copy()
            probe_pm = 2.0 * probe - 1.0  # 0→-1, 1→+1

            # Cross-correlate with sync word (mode='valid' gives exact positions)
            corr = np.correlate(probe_pm, self.sync_pm, mode="valid")
            threshold = SYNC_BITS_N * 0.90  # >= 90% match

            match_indices = np.where(corr >= threshold)[0]
            for mi in match_indices:
                # mi = bit position where sync word starts
                if mi < PREAMBLE_BITS_N:
                    continue  # Can't have preamble before sync

                # ── Verify preamble (alternating 1,0 pattern) ──
                pre_start = mi - PREAMBLE_BITS_N
                pre_bits = probe[pre_start:mi].astype(np.int8)
                pre_score = np.sum(pre_bits == self.preamble_template)
                if pre_score < PREAMBLE_BITS_N * 0.70:
                    continue  # Preamble mismatch

                # ── Extract payload ──
                payload_start = mi + SYNC_BITS_N
                if payload_start + PAYLOAD_BITS_N > len(probe):
                    continue

                payload_bits = probe[payload_start : payload_start + PAYLOAD_BITS_N]

                # Pack bits to bytes (MSB first, matching TX)
                payload_bytes = bytearray()
                for bi in range(0, PAYLOAD_BITS_N, 8):
                    byte_val = 0
                    for bj in range(8):
                        byte_val |= int(payload_bits[bi + bj] + 0.5) << (7 - bj)
                    payload_bytes.append(byte_val)

                results.append((payload_start, invert, bytes(payload_bytes)))

        # Deduplicate by payload_start (keep first-found polarity)
        seen = set()
        deduped = []
        for ps, inv, pkt in results:
            if ps not in seen:
                seen.add(ps)
                deduped.append((ps, inv, pkt))
        return deduped


# ═══════════════════════════════════════════════════════════════════════════
#  GNU Radio processing chain builder
# ═══════════════════════════════════════════════════════════════════════════
def build_rrc_taps(samp_rate, sps=SPS):
    """RRC filter taps — must match TX."""
    return firdes.root_raised_cosine(1.0, samp_rate, 100e3, 0.35, 11 * sps)


def run_gr_chain_on_source(
    sr, rrc_taps, loop_bw, offset_khz, source_block, bit_sink, const_sink=None
):
    """Connect source → freq_corr → AGC → RRC → clock_sync → costas → slicer → bit_sink."""
    tb = gr.top_block()

    # Frequency correction
    if abs(offset_khz) > 0.001:
        nco = analog.sig_source_c(sr, analog.GR_COS_WAVE, offset_khz * 1000, 1.0, 0.0)
        mixer = blocks.multiply_cc()
        tb.connect(source_block, (mixer, 0))
        tb.connect(nco, (mixer, 1))
        rf_in = mixer
    else:
        rf_in = source_block

    # AGC
    agc = analog.agc3_cc(1e-3, 1e-3, 1e-6, 1)

    # RRC matched filter
    rrc = filter.interp_fir_filter_ccc(1, rrc_taps)

    # Polyphase clock sync
    clock_sync = digital.pfb_clock_sync_ccf(
        SPS, loop_bw, rrc_taps, 32, 16, 1.5, 1
    )

    # Costas loop (BPSK = order 2)
    costas = digital.costas_loop_cc(loop_bw, 2)

    # Complex → real (BPSK lives on real axis)
    c2r = blocks.complex_to_real()

    # Binary slicer
    slicer = digital.binary_slicer_fb()

    # Connect
    tb.connect(rf_in, agc)
    tb.connect(agc, rrc)
    tb.connect(rrc, clock_sync)
    tb.connect(clock_sync, costas)
    tb.connect(costas, c2r)
    tb.connect(c2r, slicer)
    tb.connect(slicer, bit_sink)

    if const_sink is not None:
        tb.connect(costas, const_sink)

    return tb


# ═══════════════════════════════════════════════════════════════════════════
#  Mode 1: Streaming GNU Radio with soapy.source
# ═══════════════════════════════════════════════════════════════════════════
def run_streaming_mode(args):
    """
    Full streaming mode: soapy.source → digital chain → bit_sink.
    Poll bit_sink periodically, run packet detection.
    """
    sr = int(args.samp)
    rrc_taps = build_rrc_taps(sr)
    loop_bw = 2.0 * np.pi / 200.0

    # ── SoapySDR source ──
    dev = "driver=hackrf"
    dev_args = f"serial={args.serial}" if args.serial else ""
    src = soapy.source(dev, "fc32", 1, dev_args, "", [""], [""])
    src.set_sample_rate(0, sr)
    src.set_bandwidth(0, 0)
    src.set_frequency(0, args.freq)
    src.set_gain(0, "AMP", 1.0 if args.amp else 0.0)
    src.set_gain(0, "LNA", float(args.lna))
    src.set_gain(0, "VGA", float(args.vga))

    # ── Digital chain ──
    bit_sink = blocks.vector_sink_b()
    const_sink = blocks.vector_sink_c()

    tb = run_gr_chain_on_source(
        sr, rrc_taps, loop_bw, args.offset, src, bit_sink, const_sink
    )

    print(f"[Streaming] Listening: {args.freq/1e6:.3f} MHz, {sr/1e6:.1f} Msps")
    print(f"[Streaming] LNA={args.lna}, VGA={args.vga}, AMP={'ON' if args.amp else 'OFF'}")
    print(f"[Streaming] Freq offset: {args.offset:.1f} kHz")

    tb.start()

    detector = PacketDetector()
    start_time = time.time()
    last_bit_count = 0
    found_text = None

    try:
        while found_text is None:
            time.sleep(0.5)
            elapsed = time.time() - start_time

            bits = bit_sink.data()
            new_bit_count = len(bits)

            # Process new bits in the accumulated buffer
            if new_bit_count >= PACKET_BITS_N and new_bit_count > last_bit_count:
                # Use the last ~10k bits (enough for several bursts)
                search_window = bits[-max(PACKET_BITS_N * 2, 20000) :]
                packets = detector.find_packets(search_window)

                for ps, invert, payload in packets:
                    text = payload.decode("ascii", errors="replace")
                    stripped = text.strip()
                    print(f"[Streaming] PKT | inv={int(invert)} | {stripped!r}", flush=True)

                    text_upper = stripped.upper()
                    if any(kw in text_upper for kw in SUCCESS_KEYWORDS):
                        found_text = stripped
                        print(f"[Streaming] SUCCESS: Decoded '{stripped}'", flush=True)
                        break

                if found_text:
                    break

                last_bit_count = new_bit_count

            # Progress
            const = const_sink.data()
            if len(const) > 50:
                syms = np.array(const[-2000:])
                I = syms.real
                mean_i = np.mean(I)
                std_i = np.std(I)
                # BPSK energy: fraction of symbols with |I| > 0.5
                energy = np.mean(np.abs(I) > 0.5) * 100
                print(
                    f"[t={elapsed:.0f}s] bits={new_bit_count} const={len(const)} "
                    f"I={mean_i:+.3f}±{std_i:.3f} |I|>0.5={energy:.0f}%",
                    flush=True,
                )
            else:
                print(
                    f"[t={elapsed:.0f}s] bits={new_bit_count} const={len(const)}",
                    flush=True,
                )

            if elapsed > RX_TIMEOUT:
                print(f"[Streaming] Timeout after {RX_TIMEOUT}s")
                break

    except KeyboardInterrupt:
        print("[Streaming] Interrupted")
    finally:
        tb.stop()
        tb.wait()

    return found_text


# ═══════════════════════════════════════════════════════════════════════════
#  Mode 2: Native SoapySDR capture + GR digital blocks (fallback)
# ═══════════════════════════════════════════════════════════════════════════
def run_fallback_mode(args):
    """
    Fallback: capture IQ with native SoapySDR API, then process each
    second's worth of samples through the GR digital chain (offline).
    """
    import SoapySDR

    sr = int(args.samp)
    rrc_taps = build_rrc_taps(sr)
    loop_bw = 2.0 * np.pi / 200.0

    # ── Open SDR ──
    dev_str = (
        f"driver=hackrf,serial={args.serial}"
        if args.serial
        else "driver=hackrf"
    )
    print(f"[Fallback] Opening {dev_str}...")
    sdr = SoapySDR.Device(dev_str)
    sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, sr)
    sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, args.freq)
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, "LNA", float(args.lna))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, "VGA", float(args.vga))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, "AMP", float(args.amp))

    rx_stream = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)

    print(f"[Fallback] Listening: {args.freq/1e6:.3f} MHz, {sr/1e6:.1f} Msps")
    print(f"[Fallback] LNA={args.lna}, VGA={args.vga}, AMP={'ON' if args.amp else 'OFF'}")
    print(f"[Fallback] Freq offset: {args.offset:.1f} kHz")

    # ── Capture loop ──
    detector = PacketDetector()
    buf = np.zeros(2 * sr, dtype=np.complex64)  # 2 seconds per read
    accumulator = []  # accumulated samples for periodic batch processing
    start_time = time.time()
    found_text = None
    samples_captured = 0

    # Pre-compute frequency offset correction
    freq_offset_hz = args.offset * 1000.0

    try:
        while found_text is None:
            elapsed = time.time() - start_time

            sr_ret = sdr.readStream(rx_stream, [buf], len(buf), timeoutUs=1000000)
            if sr_ret.ret > 0:
                chunk = buf[: sr_ret.ret].copy()
                accumulator.append(chunk)
                samples_captured += sr_ret.ret
            elif sr_ret.ret == 0:
                continue  # timeout, keep trying

            # Process batch every ~1 second worth of samples
            if samples_captured >= sr * 1:
                big_chunk = np.concatenate(accumulator)
                accumulator = []
                samples_captured = 0

                # Mix down for frequency offset
                if abs(freq_offset_hz) > 0.001:
                    t = np.arange(len(big_chunk), dtype=np.float64)
                    big_chunk = big_chunk * np.exp(
                        -2j * np.pi * freq_offset_hz * t / sr
                    )

                # Remove DC
                big_chunk = big_chunk - np.mean(big_chunk)

                # Process through GR digital chain
                # Build a temporary flowgraph: vector_source → digital chain → bit_sink
                try:
                    tb = gr.top_block()

                    vec_src = blocks.vector_source_c(
                        big_chunk.astype(np.complex64).tolist(), False
                    )

                    agc = analog.agc3_cc(1e-3, 1e-3, 1e-6, 1)
                    rrc = filter.interp_fir_filter_ccc(1, rrc_taps)

                    clock_sync = digital.pfb_clock_sync_ccf(
                        SPS, loop_bw, rrc_taps, 32, 16, 1.5, 1
                    )

                    costas = digital.costas_loop_cc(loop_bw, 2)
                    c2r = blocks.complex_to_real()
                    slicer = digital.binary_slicer_fb()
                    bit_sink = blocks.vector_sink_b()

                    tb.connect(vec_src, agc)
                    tb.connect(agc, rrc)
                    tb.connect(rrc, clock_sync)
                    tb.connect(clock_sync, costas)
                    tb.connect(costas, c2r)
                    tb.connect(c2r, slicer)
                    tb.connect(slicer, bit_sink)

                    tb.start()
                    tb.wait()

                    bits = bit_sink.data()
                    bit_count = len(bits)

                    if bit_count >= PACKET_BITS_N:
                        packets = detector.find_packets(bits)
                        for ps, invert, payload in packets:
                            text = payload.decode("ascii", errors="replace")
                            stripped = text.strip()
                            print(
                                f"[Fallback] PKT | inv={int(invert)} | {stripped!r}",
                                flush=True,
                            )

                            text_upper = stripped.upper()
                            if any(kw in text_upper for kw in SUCCESS_KEYWORDS):
                                found_text = stripped
                                print(
                                    f"[Fallback] SUCCESS: Decoded '{stripped}'",
                                    flush=True,
                                )
                                break

                    if found_text:
                        break

                    print(
                        f"[t={elapsed:.0f}s] batch={len(big_chunk)} bits={bit_count}",
                        flush=True,
                    )

                except Exception as e:
                    print(f"[Fallback] GR processing error: {e}", flush=True)

            if elapsed > RX_TIMEOUT:
                print(f"[Fallback] Timeout after {RX_TIMEOUT}s")
                break

    except KeyboardInterrupt:
        print("[Fallback] Interrupted")

    sdr.deactivateStream(rx_stream)
    sdr.closeStream(rx_stream)
    return found_text


# ═══════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="GNU Radio Live BPSK Receiver")
    parser.add_argument("--freq", type=float, default=915e6)
    parser.add_argument("--samp", type=float, default=2e6)
    parser.add_argument("--lna", type=float, default=8)
    parser.add_argument("--vga", type=float, default=12)
    parser.add_argument("--amp", action="store_true", default=False)
    parser.add_argument("--serial", type=str, default=None)
    parser.add_argument(
        "--offset",
        type=float,
        default=5.2,
        help="Frequency offset in kHz (positive = shift down)",
    )
    parser.add_argument(
        "--fallback",
        action="store_true",
        default=False,
        help="Force native SoapySDR + GR blocks (skip streaming mode)",
    )
    args = parser.parse_args()

    # Apply default serial
    if args.serial is None:
        args.serial = "000000000000000060a464dc3674640f"

    found_text = None

    if not args.fallback:
        # Try streaming mode (GR soapy.source)
        try:
            found_text = run_streaming_mode(args)
        except Exception as e:
            print(f"[Main] Streaming mode failed: {e}", flush=True)
            print("[Main] Falling back to native SoapySDR + GR blocks...", flush=True)

    if found_text is None:
        # Fallback mode
        found_text = run_fallback_mode(args)

    if found_text:
        print(f"\n{'='*50}")
        print(f"✅ SUCCESS: Decoded '{found_text}'")
        print(f"{'='*50}\n")
        sys.exit(0)
    else:
        print(f"\n{'='*50}")
        print("❌ No valid packets decoded within timeout")
        print(f"{'='*50}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
