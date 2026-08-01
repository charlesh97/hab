#!/usr/bin/env python3
"""GPS Packet Transmitter — reads GPS NMEA, packs PositionFrames, transmits BPSK.

Uses the same GNU Radio BPSK chain as rf/packet/src/pkt_simple_tx.py:
  256b preamble + 32b sync 0xE38FC0FC + 16b len + payload + CRC-16/XMODEM.

Payload is a typed binary PositionFrame (38 bytes, type 0x01).
Transmits at 1 Hz burst rate with 50 ms inter-packet gap.

Requires: gnuradio, python3-numpy, hackrf, soapysdr-module-hackrf
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

import numpy as np
from gnuradio import blocks, gr, soapy
from gnuradio.filter import firdes

# ── Add payload modules to path ────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_PAYLOAD = _HERE.parent
sys.path.insert(0, str(_PAYLOAD))

from gps.nmea import NMEAParser, parse_gga  # noqa: E402
from telemetry.packet_format import PositionFrame  # noqa: E402

# ── Constants (matching pkt_simple_tx.py baseline) ─────────────────

FS = 2_000_000          # sample rate
SPS = 20                # samples per symbol
RRC_ALPHA = 0.35
RRC_NTAPS = 11          # in units of SPS → 220 taps
SYNC_WORD = 0xE38FC0FC  # 32-bit
PREAMBLE_BITS = 256
GAP_MS = 50             # inter-packet silence


def crc16(data: bytes) -> int:
    """CRC-16/XMODEM (0x1021).  Returns 16-bit unsigned int."""
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


def bpsk_modulate(bits: list[int], sps: int = SPS) -> np.ndarray:
    """Convert bits (0/1 ints) to RRC-shaped BPSK complex waveform."""
    mapped = np.array(bits, dtype=np.float64) * -2.0 + 1.0  # 0→+1, 1→−1
    up = np.zeros(len(mapped) * sps, dtype=np.float64)
    up[::sps] = mapped
    taps = firdes.root_raised_cosine(sps, sps, 1.0, RRC_ALPHA, RRC_NTAPS * sps)
    taps_np = np.array(taps)
    waveform = np.convolve(up, taps_np, "same")
    peak = float(np.max(np.abs(waveform)))
    if peak > 0.7:
        waveform *= 0.7 / peak
    return waveform.astype(np.complex64)


def _bytes_to_bits(data: bytes) -> list[int]:
    bits: list[int] = []
    for b in data:
        for i in range(8):
            bits.append((b >> (7 - i)) & 1)
    return bits


def make_packet_waveform(payload: bytes) -> np.ndarray:
    """Build BPSK waveform for a single packet."""
    # Preamble
    preamble = [1, 0] * (PREAMBLE_BITS // 2)
    # Sync word
    sync = [(SYNC_WORD >> (31 - i)) & 1 for i in range(32)]
    # Length (big-endian uint16)
    length = len(payload)
    len_bytes = struct.pack(">H", length)
    # CRC-16 over payload
    crc = crc16(payload)
    crc_bytes = struct.pack(">H", crc)
    # Assemble
    all_bits = (
        preamble
        + sync
        + _bytes_to_bits(len_bytes)
        + _bytes_to_bits(payload)
        + _bytes_to_bits(crc_bytes)
    )
    return bpsk_modulate(all_bits)


def build_burst(payload: bytes, sample_rate: int = FS) -> list[complex]:
    """Single-packet burst with trailing silence for a 1-second cycle."""
    pkt = make_packet_waveform(payload)
    gap_samples = int(round(GAP_MS * sample_rate / 1000.0))
    # Silence before and after the packet
    total_wanted = sample_rate  # 1 second worth of samples
    available = len(pkt) + 2 * gap_samples
    if available < total_wanted:
        pad_before = gap_samples
        pad_after = total_wanted - len(pkt) - pad_before
    else:
        pad_before = gap_samples
        pad_after = gap_samples
    burst = [0j] * pad_before + pkt.tolist() + [0j] * pad_after
    return burst


def print_status(pkt_len: int, lat: float, lon: float, alt: float, sats: int) -> None:
    print(
        f"[GPSTx] pkt={pkt_len}B  "
        f"pos={lat:.5f},{lon:.5f}  "
        f"alt={alt:.1f}m  "
        f"sats={sats}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="GPS Packet TX via HackRF")
    parser.add_argument("--freq", type=float, default=915e6)
    parser.add_argument("--vga", type=float, default=47)
    parser.add_argument("--amp", action="store_true", default=True)
    parser.add_argument("--serial", type=str, default=None)
    parser.add_argument("--device", type=str, default="/dev/ttyS0",
                        help="GPS serial device")
    parser.add_argument("--baud", type=int, default=9600)
    args = parser.parse_args()

    freq = float(args.freq)
    fs = FS

    print(f"[GPSTx] Opening GPS on {args.device} @ {args.baud}")
    gps = NMEAParser(args.device)
    gps.serial.baudrate = args.baud

    seq = 0
    last_lat = 0.0
    last_lon = 0.0
    last_alt = 0.0
    last_fix = False
    last_fix_type = "none"
    last_sats = 0
    last_hdop = 0.0

    print(f"[GPSTx] Freq={freq/1e6:.3f} MHz  VGA={args.vga}  amp={args.amp}")
    if args.serial:
        print(f"[GPSTx] HackRF serial: {args.serial}")

    try:
        while True:
            # Collect the latest GPS fix
            sentence = gps.read_sentence()
            if sentence:
                fix = parse_gga(sentence)
                if fix is not None:
                    if fix.get("lat") is not None:
                        last_lat = float(fix["lat"])
                    if fix.get("lon") is not None:
                        last_lon = float(fix["lon"])
                    if fix.get("altitude") is not None:
                        last_alt = float(fix["altitude"])
                    fq = fix.get("fix_quality")
                    fq_int = int(fq) if fq is not None else 0
                    last_fix = fq_int > 0
                    if fq_int >= 2:
                        last_fix_type = "3d"
                    elif fq_int == 1:
                        last_fix_type = "2d"
                    else:
                        last_fix_type = "none"
                    if fix.get("satellites") is not None:
                        last_sats = int(fix["satellites"])
                    if fix.get("hdop") is not None:
                        last_hdop = float(fix["hdop"])

            # Pack position frame
            frame = PositionFrame(
                type=0x01,
                seq=seq,
                lat=last_lat,
                lon=last_lon,
                alt_m=last_alt,
                agl_m=max(0.0, last_alt - 10.0),  # rough AGL
                fix=last_fix,
                fix_type=last_fix_type,
                sats=last_sats,
                hdop=last_hdop,
                vdop=0.0,  # NMEA GGA doesn't have VDOP; GSA does
            )
            payload = frame.pack()
            seq = (seq + 1) & 0xFFFF

            print_status(len(payload), last_lat, last_lon, last_alt, last_sats)

            # Build burst waveform and transmit via GNU Radio
            burst = build_burst(payload)

            src = blocks.vector_source_c(burst, False)
            thr = blocks.throttle(gr.sizeof_gr_complex, fs)
            sink_kwargs: tuple = ("driver=hackrf", "fc32", 1, "", "", [""], [""])
            if args.serial:
                sink_kwargs = ("driver=hackrf", "fc32", 1, f"serial={args.serial}", "", [""], [""])
            sink = soapy.sink(*sink_kwargs)
            sink.set_sample_rate(0, fs)
            sink.set_bandwidth(0, 0)
            sink.set_frequency(0, freq)
            sink.set_gain(0, "AMP", 1.0 if args.amp else 0.0)
            sink.set_gain(0, "VGA", float(args.vga))

            tb = gr.top_block()
            tb.connect(src, thr, sink)
            tb.start()

            # Wait for the burst to complete (1 second of samples)
            time.sleep(1.05)

            tb.stop()
            tb.wait()

    except KeyboardInterrupt:
        pass
    finally:
        gps.close()
        print("[GPSTx] Stopped.")


if __name__ == "__main__":
    main()
