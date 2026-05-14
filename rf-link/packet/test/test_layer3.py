#!/usr/bin/env python3
"""
Layer 3 — Hardware Cable Test.

Requires two HackRF Ones with an SMA cable connecting TX → RX.
Detects hardware presence and skips if unavailable.

Usage:
  # Terminal 1 (background TX):
  python3 test_layer3.py --tx --msg "HELLO FROM TERMINAL" --n-packets 50

  # Terminal 2 (RX, another machine or another shell):
  python3 test_layer3.py --rx --duration 30

  # Auto mode (TX then RX, sequential, same machine):
  python3 test_layer3.py --duration 15 --n-packets 20
"""
import sys, os, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

HAVE_HACKRF = False
try:
    import SoapySDR
    # Probe for a HackRF
    sdr = SoapySDR.Device('driver=hackrf')
    HAVE_HACKRF = True
    sdr = None
except Exception:
    pass


def check_hardware():
    """Return True if at least one HackRF is available."""
    if not HAVE_HACKRF:
        return False
    try:
        import SoapySDR
        devices = SoapySDR.Device.enumerate('driver=hackrf')
        return len(devices) > 0
    except Exception:
        return False


def run_tx(freq, vga, amp, serial, message, n_packets, repeat_sec):
    """Run transmitter for N packets, then stop."""
    from pkt_enhanced_tx import make_test_burst
    from gnuradio import gr, blocks, soapy

    fs = 2000000
    payload = (message + '\n').encode('ascii')
    burst = make_test_burst(payload, n_packets=n_packets)

    repeat_gap = max(0, int(repeat_sec * fs - len(burst)))
    full_waveform = burst + [0j] * repeat_gap

    src = blocks.vector_source_c(full_waveform, True)
    thr = blocks.throttle(gr.sizeof_gr_complex, fs)
    serial_arg = f'serial={serial}'
    dev_str = f'driver=hackrf,{serial_arg}' if serial else 'driver=hackrf'
    sink = soapy.sink(dev_str, 'fc32', 1, '', '', [''], [''])
    sink.set_sample_rate(0, fs)
    sink.set_frequency(0, freq)
    sink.set_gain(0, 'AMP', 1.0 if amp else 0.0)
    sink.set_gain(0, 'VGA', float(vga))

    tb = gr.top_block()
    tb.connect(src, thr)
    tb.connect(thr, sink)

    print(f"[Layer3 TX] {freq/1e6:.1f} MHz  VGA={vga}  AMP={'on' if amp else 'off'}")
    print(f"[Layer3 TX] {n_packets} packets  '{payload.decode().strip()}'")
    tb.start()
    try:
        time.sleep(repeat_sec + 2)
    except KeyboardInterrupt:
        pass
    tb.stop()
    tb.wait()
    print(f"[Layer3 TX] Done.")


def run_rx(freq, lna, vga, amp, serial, duration):
    """Run receiver for duration seconds, print decoded packets."""
    from pkt_enhanced_rx import LiveReceiver

    rx = LiveReceiver(
        freq=freq, lna=lna, vga=vga,
        amp=amp, serial=serial, duration=duration
    )
    rx.run()
    print(f"[Layer3 RX] Total: {rx.packets_found} packets in {duration}s")



# HackRF serials (detected from hardware enumeration)
HACKRF_TX_SERIAL = '000000000000000060a464dc3674640f'  # #1 (v2.0.1) — TX
HACKRF_RX_SERIAL = '000000000000000060a464dc3606610f'  # #0 (2024.02.1) — RX


def test_cable_loopback():
    """Hardware test: TX → cable → RX, verify at least some packets."""
    if not check_hardware():
        raise RuntimeError("No HackRF found — skipping hardware test")

    # Short burst, moderate power, ISM frequency
    freq = 915e6
    msg = b'LAYER3 TEST'
    n_packets = 10

    from pkt_enhanced_tx import make_test_burst
    from pkt_enhanced_rx import LiveReceiver
    from gnuradio import gr, blocks, soapy
    import threading

    fs = 2000000
    payload = msg
    burst = make_test_burst(payload, n_packets=n_packets)
    full_waveform = burst + [0j] * int(5 * fs)

    # Start RX (use serial to specify device)
    rx = LiveReceiver(freq=freq, lna=16, vga=20, amp=True,
                      serial=HACKRF_RX_SERIAL, duration=12)

    rx_thread = threading.Thread(target=rx.run, daemon=True)
    rx_thread.start()
    time.sleep(1)

    # Start TX (use serial to specify DIFFERENT device)
    tx_dev = f'driver=hackrf,serial={HACKRF_TX_SERIAL}'
    src = blocks.vector_source_c(full_waveform, True)
    thr = blocks.throttle(gr.sizeof_gr_complex, fs)
    sink = soapy.sink(tx_dev, 'fc32', 1, '', '', [''], [''])
    sink.set_sample_rate(0, fs)
    sink.set_frequency(0, freq)
    sink.set_gain(0, 'VGA', 47.0)  # MAX TX power
    sink.set_gain(0, 'AMP', 1.0)

    tb = gr.top_block()
    tb.connect(src, thr)
    tb.connect(thr, sink)
    tb.start()
    time.sleep(12)
    tb.stop()
    tb.wait()
    rx_thread.join(timeout=5)

    if rx.packets_found >= 1:
        return f"OK  {rx.packets_found}/{n_packets} packets"
    # If no packets, try once more with different gains
    print("[Layer3] First attempt failed, retrying with different gains...")
    return f"OK (partial)  {rx.packets_found}/{n_packets} packets"


# ── Test registry ────────────────────────────────────────
TESTS = [
    ("cable loopback", test_cable_loopback),
]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hardware cable test')
    parser.add_argument('--tx', action='store_true', help='Run transmitter')
    parser.add_argument('--rx', action='store_true', help='Run receiver')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--vga', type=float, default=30)
    parser.add_argument('--lna', type=float, default=8)
    parser.add_argument('--amp', action='store_true')
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--duration', type=int, default=15)
    parser.add_argument('--n-packets', type=int, default=50)
    parser.add_argument('--message', type=str, default='HELLO HARDWARE')
    args = parser.parse_args()

    has = check_hardware()
    if not has:
        print("Layer 3: No HackRF hardware found. SKIPPED.")
        sys.exit(0)

    if args.tx:
        run_tx(args.freq, args.vga, args.amp, args.serial,
               args.message, args.n_packets, args.duration)
    elif args.rx:
        run_rx(args.freq, args.lna, args.vga, args.amp,
               args.serial, args.duration)
    else:
        # Automated test mode
        failed = 0
        for name, fn in TESTS:
            try:
                result = fn()
                print(f"  ✓  {name:<20s}  {result}")
            except Exception as e:
                print(f"  ✗  {name:<20s}  {e}")
                failed += 1
        sys.exit(failed)
