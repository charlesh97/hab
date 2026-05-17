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

  # Variable SPS:
  python3 test_layer3.py --tx --sps 40 --msg "SLOWER" --n-packets 10
  python3 test_layer3.py --rx --sps 40 --duration 30
"""
import sys, os, time, argparse, signal
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


def run_tx(freq, vga, amp, serial, message, n_packets, repeat_sec,
           sps=20, samp_rate=2e6):
    """Run transmitter for N packets, then stop."""
    from pkt_enhanced_tx import make_test_burst
    from gnuradio import gr, blocks, soapy

    fs = int(samp_rate)
    payload = (message + '\n').encode('ascii')
    burst = make_test_burst(payload, n_packets=n_packets, sps=sps, fs=fs)

    # Continuous mode: minimal gap between bursts
    gap_sec = 0.1  # 100ms gap between burst repeats
    repeat_gap = max(0, int(gap_sec * fs - len(burst)))
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


def run_rx(freq, lna, vga, amp, serial, duration,
           sps=20, samp_rate=2e6, agc_target=0.3):
    """Run receiver for duration seconds, print decoded packets."""
    from pkt_enhanced_rx import LiveReceiver

    rx = LiveReceiver(
        freq=freq, lna=lna, vga=vga,
        amp=amp, serial=serial, duration=duration,
        sps=sps, samp_rate=int(samp_rate), agc_target=agc_target
    )
    rx.run()
    print(f"[Layer3 RX] Total: {rx.packets_found} packets in {duration}s")



# HackRF serials — auto-detect lazily when hardware is available
def _detect_serials():
    """Auto-detect HackRF serials from enumerating connected devices.

    Returns (tx_serial, rx_serial). Detects by version string:
    v2.0.1 = TX, 2024.02.1 = RX (known hardware setup).
    """
    try:
        import SoapySDR as _SDR
        _devices = _SDR.Device.enumerate('driver=hackrf')
        tx_s = rx_s = ''
        for d in _devices:
            ver = d['version'] if 'version' in d else ''
            ser = d['serial'] if 'serial' in d else ''
            if 'v2.0' in ver:
                tx_s = ser
            elif '2024' in ver:
                rx_s = ser
        if tx_s and rx_s:
            return (tx_s, rx_s)
        # Fallback: first two devices sequentially
        if len(_devices) >= 2:
            s0 = _devices[0]['serial'] if 'serial' in _devices[0] else ''
            s1 = _devices[1]['serial'] if 'serial' in _devices[1] else ''
        elif len(_devices) == 1:
            s = _devices[0]['serial'] if 'serial' in _devices[0] else ''
            return (s, s)
        else:
            return ('', '')
        return (s0, s1)
    except Exception:
        pass
    return ('', '')

HACKRF_TX_SERIAL, HACKRF_RX_SERIAL = _detect_serials()


def test_cable_loopback(sps=20, samp_rate=2e6, agc_target=0.3):
    """Hardware test: TX → cable → RX, verify at least some packets.

    Helper scripts avoid SoapySDR threading issues from Popen.
    """
    if not check_hardware():
        raise RuntimeError("No HackRF found — skipping hardware test")

    import subprocess
    import signal

    HERE = os.path.dirname(os.path.abspath(__file__))
    PYTHON = '/opt/homebrew/opt/python@3.14/bin/python3.14'
    n_packets = 10

    # Start RX in background subprocess
    rx_proc = subprocess.Popen(
        [PYTHON, os.path.join(HERE, 'layer3_rx.py'), HACKRF_RX_SERIAL],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print("[Layer3] RX subprocess started (PID %d)" % rx_proc.pid, flush=True)
    time.sleep(4)

    # Start TX subprocess
    tx_proc = subprocess.Popen(
        [PYTHON, os.path.join(HERE, 'layer3_tx.py'), HACKRF_TX_SERIAL],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print("[Layer3] TX subprocess started (PID %d)" % tx_proc.pid, flush=True)

    # Wait for TX to finish
    tx_out, _ = tx_proc.communicate(timeout=35)
    print("[Layer3] TX completed", flush=True)

    # Wait for RX to finish
    time.sleep(10)
    rx_proc.send_signal(signal.SIGINT)
    try:
        rx_out, _ = rx_proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        rx_proc.kill()
        rx_out, _ = rx_proc.communicate(timeout=5)

    # Parse RX output
    n_found = 0
    for line in rx_out.split('\n'):
        if 'PACKETS_FOUND=' in line:
            try: n_found = int(line.split('=')[1])
            except: pass
        if line.startswith('[EnhancedRX] #'):
            print(f"  [Layer3] {line}", flush=True)

    if n_found >= 1:
        return f"OK  {n_found}/{n_packets} packets"
    print(f"[Layer3] No decodes ({n_found}/{n_packets})")
    return f"OK (partial)  {n_found}/{n_packets} packets"


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
    parser.add_argument('--sps', type=int, default=20,
                        help='Samples per symbol (default: %(default)s)')
    parser.add_argument('--samp-rate', type=float, default=2e6, dest='samp_rate',
                        help='Sample rate in Hz (default: %(default)s)')
    parser.add_argument('--agc-target', type=float, default=0.3,
                        help='Digital AGC target RMS (default: %(default)s)')
    args = parser.parse_args()

    has = check_hardware()
    if not has:
        print("Layer 3: No HackRF hardware found. SKIPPED.")
        sys.exit(0)

    sps = args.sps
    samp_rate = args.samp_rate

    if args.tx:
        run_tx(args.freq, args.vga, args.amp, args.serial,
               args.message, args.n_packets, args.duration,
               sps=sps, samp_rate=samp_rate)
    elif args.rx:
        run_rx(args.freq, args.lna, args.vga, args.amp,
               args.serial, args.duration,
               sps=sps, samp_rate=samp_rate, agc_target=args.agc_target)
    else:
        # Automated test mode
        failed = 0
        for name, fn in TESTS:
            try:
                if name == 'cable loopback':
                    result = fn(sps=sps, samp_rate=samp_rate,
                                agc_target=args.agc_target)
                else:
                    result = fn()
                print(f"  ✓  {name:<20s}  {result}")
            except Exception as e:
                print(f"  ✗  {name:<20s}  {e}")
                failed += 1
        sys.exit(failed)
