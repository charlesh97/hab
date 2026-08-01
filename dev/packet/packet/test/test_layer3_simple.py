#!/usr/bin/env python3
"""
Layer 3 — Hardware Loopback Tests (HackRF SMA cable).

Requires two HackRF Ones connected via SMA cable.
TX via hackrf_transfer, RX via SoapySDR → PacketDecoder → CRC validation.

The production decoder uses GNU Radio's band-edge FLL for acquisition and
its BPSK Costas loop for residual carrier tracking over long payloads.
"""
import gc
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_HAB = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(_HAB / "ground" / "rx"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import numpy as np
import SoapySDR

from pkt_simple_tx import make_packet
from demod import (
    FS,
    MAX_POST_SYNC,
    PRE_SYNC,
    SPS,
    SYNC_BITS,
    PacketDecoder,
)

FREQ = 433.5e6
TX_SERIAL = '60a464dc3674640f'
RX_SERIAL = '60a464dc3606610f'
TX_VGA = 47
RX_LNA = 32
RX_VGA = 40


def _iq8_write(path, wf, scale=80):
    wf_arr = np.array(wf, dtype=np.complex64)
    I = (wf_arr.real * scale).clip(-127, 127).astype(np.int8)
    Q = (wf_arr.imag * scale).clip(-127, 127).astype(np.int8)
    iq = np.empty(2 * len(I), dtype=np.int8)
    iq[0::2] = I; iq[1::2] = Q
    iq.tofile(path)


def _rx_capture_results(duration, lna=RX_LNA, vga=RX_VGA, amp=True):
    """Capture samples and return all CRC-valid decoder results."""
    dev_str = f'driver=hackrf,serial={RX_SERIAL}'
    sdr = SoapySDR.Device(dev_str)
    sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, int(FS))
    sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, FREQ)
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'LNA', float(lna))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'VGA', float(vga))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'AMP', float(amp))

    rx_stream = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)

    buf = np.zeros(262144, dtype=np.complex64)
    accum = []
    t0 = time.time()
    try:
        while time.time() - t0 < duration:
            sr = sdr.readStream(rx_stream, [buf], len(buf), timeoutUs=500000)
            if sr.ret > 0:
                accum.append(buf[:sr.ret].copy())
    except Exception:
        pass
    finally:
        sdr.deactivateStream(rx_stream)
        sdr.closeStream(rx_stream)

    if not accum:
        return []

    samples = np.concatenate(accum)
    max_packet_samples = (PRE_SYNC + SYNC_BITS + MAX_POST_SYNC + 7) * SPS
    chunk_samples = 1_000_000
    stride = chunk_samples - max_packet_samples
    results = []
    sync_positions = []

    # Bound GNU Radio vector-source memory while retaining enough overlap for
    # packets that straddle adjacent chunks.
    for start in range(0, len(samples), stride):
        chunk = samples[start:start + chunk_samples]
        if len(chunk) < (PRE_SYNC + SYNC_BITS + 24) * SPS:
            break
        for result in PacketDecoder().decode(chunk):
            absolute_sync = start + result[3] + result[4] * SPS
            if any(abs(absolute_sync - prior) <= SPS for prior in sync_positions):
                continue
            sync_positions.append(absolute_sync)
            results.append(result)
    return results


def _rx_capture_decode(duration, payload, lna=RX_LNA, vga=RX_VGA, amp=True):
    """Capture and decode, return count of matching CRC-valid payloads."""
    results = _rx_capture_results(duration, lna=lna, vga=vga, amp=amp)
    matches = sum(1 for r in results if r[0] == payload)
    return matches, len(results)


def _check_hardware(timeout=5.0):
    """Wait briefly for both configured HackRFs to enumerate."""
    deadline = time.time() + timeout
    while True:
        try:
            devices = SoapySDR.Device.enumerate('driver=hackrf')
            # SoapyHackRF reports the full 32-character serial while the CLI
            # and existing configuration use the significant 16-char suffix.
            serials = [dict(device).get('serial', '') for device in devices]
            if all(
                any(reported.endswith(required) for reported in serials)
                for required in (TX_SERIAL, RX_SERIAL)
            ):
                return True
        except Exception:
            pass
        if time.time() >= deadline:
            return False
        time.sleep(0.25)


def _hw_loopback(payload, capture_sec=3):
    """Run one TX→RX cycle. Returns (matches, total_decoded)."""
    if not _check_hardware():
        return -1, -1  # skip

    wf = np.tile(np.array(make_packet(payload, sps=SPS)), 40)

    with tempfile.NamedTemporaryFile(suffix='.iq8', delete=False) as f:
        iq_path = f.name
    _iq8_write(iq_path, wf)

    try:
        tx = subprocess.Popen([
            'hackrf_transfer', '-t', iq_path,
            '-d', TX_SERIAL,
            '-f', str(int(FREQ)), '-s', str(int(FS)),
            '-a', '1', '-l', '40', '-x', str(TX_VGA), '-R'
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.3)
        matches, total = _rx_capture_decode(capture_sec, payload)
        tx.send_signal(signal.SIGTERM)
        tx.wait(timeout=2)
    finally:
        os.unlink(iq_path)

    return matches, total


# ── Tests ─────────────────────────────────────────────────

def test_basic_loopback():
    """Short payload decodes through hardware with CRC validation."""
    if not _check_hardware():
        return "SKIP  no HackRFs"

    matches, total = _hw_loopback(b'HELLO')
    assert total > 0, f"No CRC-valid decodes at all"
    assert matches >= 1, f"No matching payloads ({total} total decoded)"
    return f"OK  {matches}/{total} decoded, CRC valid"


def test_signal_strength():
    """Signal peak confirms TX is radiating."""
    if not _check_hardware():
        return "SKIP  no HackRFs"

    # Quick capture just for peak
    sdr = SoapySDR.Device(f'driver=hackrf,serial={RX_SERIAL}')
    sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, int(FS))
    sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, FREQ)
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'LNA', float(RX_LNA))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'VGA', float(RX_VGA))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'AMP', 1.0)
    rx = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
    sdr.activateStream(rx)

    # Start TX
    wf = np.tile(np.array(make_packet(b'SIG', sps=SPS)), 40)
    with tempfile.NamedTemporaryFile(suffix='.iq8', delete=False) as f:
        iq_path = f.name
    _iq8_write(iq_path, wf)
    tx = subprocess.Popen([
        'hackrf_transfer', '-t', iq_path,
        '-d', TX_SERIAL,
        '-f', str(int(FREQ)), '-s', str(int(FS)),
        '-a', '1', '-l', '40', '-x', str(TX_VGA), '-R'
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.3)

    buf = np.zeros(131072, dtype=np.complex64)
    sr = sdr.readStream(rx, [buf], len(buf), timeoutUs=2000000)
    sdr.deactivateStream(rx); sdr.closeStream(rx)
    tx.send_signal(signal.SIGTERM); tx.wait()
    os.unlink(iq_path)

    peak = np.max(np.abs(buf[:sr.ret]))
    assert peak > 0.5, f"Weak signal: peak={peak:.3f} (need >0.5)"
    return f"OK  peak={peak:.3f}"


def test_packet_loss_rate():
    """At least 70% of 20 distinct short frames are received."""
    if not _check_hardware():
        return "SKIP  no HackRFs"

    payloads = [b'L' + sequence.to_bytes(3, 'big') for sequence in range(20)]
    expected = set(payloads)
    burst = _unique_burst(payloads, gap_ms=30)

    with tempfile.NamedTemporaryFile(suffix='.iq8', delete=False) as f:
        iq_path = f.name
    _iq8_write(iq_path, burst)

    try:
        tx = subprocess.Popen([
            'hackrf_transfer', '-t', iq_path,
            '-d', TX_SERIAL,
            '-f', str(int(FREQ)), '-s', str(int(FS)),
            '-a', '1', '-l', '40', '-x', str(TX_VGA), '-R'
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.3)
        results = _rx_capture_results(2.0)
        tx.send_signal(signal.SIGTERM)
        tx.wait(timeout=2)
    finally:
        os.unlink(iq_path)

    received = {result[0] for result in results} & expected
    loss_pct = (1 - len(received) / len(expected)) * 100
    assert loss_pct < 30, \
        f"High packet loss: {loss_pct:.0f}% ({len(received)}/{len(expected)})"
    return f"OK  {len(received)}/20 unique frames, {loss_pct:.0f}% loss"


def test_weak_signal_margin():
    """Reduced TX gain still decodes (signal margin check)."""
    if not _check_hardware():
        return "SKIP  no HackRFs"

    payload = b'WEAK'
    wf = np.tile(np.array(make_packet(payload, sps=SPS)), 40)

    with tempfile.NamedTemporaryFile(suffix='.iq8', delete=False) as f:
        iq_path = f.name
    _iq8_write(iq_path, wf)

    lowest_vga = TX_VGA
    for vga in [47, 30, 20, 15, 10]:
        try:
            tx = subprocess.Popen([
                'hackrf_transfer', '-t', iq_path,
                '-d', TX_SERIAL,
                '-f', str(int(FREQ)), '-s', str(int(FS)),
                '-a', '1', '-l', '40', '-x', str(vga), '-R'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.3)
            matches, total = _rx_capture_decode(0.5, payload)
            tx.send_signal(signal.SIGTERM)
            tx.wait(timeout=2)

            if matches > 0:
                lowest_vga = vga
            else:
                break
            gc.collect()
        except Exception:
            break

    os.unlink(iq_path)

    assert lowest_vga < TX_VGA, f"No margin: only works at VGA={lowest_vga}"
    return f"OK  decodes down to TX_VGA={lowest_vga} (from {TX_VGA})"


def test_crc_no_false_positives():
    """CRC prevents garbage from being accepted as valid."""
    if not _check_hardware():
        return "SKIP  no HackRFs"

    # Capture noise (no TX) — should produce zero CRC-valid decodes
    sdr = SoapySDR.Device(f'driver=hackrf,serial={RX_SERIAL}')
    sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, int(FS))
    sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, FREQ)
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'LNA', float(RX_LNA))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'VGA', float(RX_VGA))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'AMP', 1.0)
    rx = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
    sdr.activateStream(rx)

    buf = np.zeros(262144, dtype=np.complex64)
    accum = []
    t0 = time.time()
    while time.time() - t0 < 2:
        sr = sdr.readStream(rx, [buf], len(buf), timeoutUs=500000)
        if sr.ret > 0:
            accum.append(buf[:sr.ret].copy())
    sdr.deactivateStream(rx); sdr.closeStream(rx)

    samples = np.concatenate(accum)
    decoder = PacketDecoder()
    results = decoder.decode(samples)

    assert len(results) == 0, f"Noise produced {len(results)} CRC-valid decodes (false positives!)"
    return "OK  0 false positives on noise"


def _long_payload(sequence):
    """Build one deterministic, distinct 128-byte acceptance payload."""
    prefix = sequence.to_bytes(4, 'big')
    body = bytes((sequence * 37 + index * 19) & 0xFF for index in range(124))
    return prefix + body


def _unique_burst(payloads, gap_ms=20):
    """Build one cycle containing each payload exactly once."""
    gap = np.zeros(int(round(gap_ms * FS / 1000.0)), dtype=np.complex64)
    chunks = []
    for index, payload in enumerate(payloads):
        if index:
            chunks.append(gap)
        chunks.append(np.asarray(make_packet(payload, sps=SPS), dtype=np.complex64))
    return np.concatenate(chunks)


def test_long_payload_reliability():
    """At least 18/20 unique 128-byte frames decode in each of three runs."""
    if not _check_hardware():
        return "SKIP  required HackRF serials not found"

    payloads = [_long_payload(sequence) for sequence in range(20)]
    expected = set(payloads)
    waveform = _unique_burst(payloads)

    with tempfile.NamedTemporaryFile(suffix='.iq8', delete=False) as handle:
        iq_path = handle.name
    _iq8_write(iq_path, waveform)

    run_counts = []
    try:
        for run in range(3):
            tx = subprocess.Popen([
                'hackrf_transfer', '-t', iq_path,
                '-d', TX_SERIAL,
                '-f', str(int(FREQ)), '-s', str(int(FS)),
                '-a', '1', '-l', '40', '-x', str(TX_VGA), '-R'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                time.sleep(0.3)
                results = _rx_capture_results(2.0)
            finally:
                tx.send_signal(signal.SIGTERM)
                tx.wait(timeout=2)

            received = {result[0] for result in results} & expected
            run_counts.append(len(received))
            assert len(received) >= 18, \
                f"Run {run + 1}: only {len(received)}/20 unique 128-byte frames"
    finally:
        os.unlink(iq_path)

    return f"OK  unique 128B frames per run: {run_counts}"


# ── Test registry ────────────────────────────────────────
TESTS = [
    ("basic loopback",           test_basic_loopback),
    ("signal strength",          test_signal_strength),
    ("packet loss rate",         test_packet_loss_rate),
    ("weak signal margin",       test_weak_signal_margin),
    ("CRC no false positives",   test_crc_no_false_positives),
    ("128B reliability",         test_long_payload_reliability),
]


def _run_one(test_name):
    """Run one test and print its result for the process-isolated harness."""
    tests_by_name = dict(TESTS)
    fn = tests_by_name.get(test_name)
    if fn is None:
        print(f"Unknown test: {test_name}", flush=True)
        return 2

    try:
        result = fn()
        status = '✓' if 'OK' in str(result) else '○'
        print(f"  {status}  {test_name:<24s}  {result}", flush=True)
        return 0
    except Exception as exc:
        print(f"  ✗  {test_name:<24s}  {exc}", flush=True)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--run-one':
        sys.exit(_run_one(sys.argv[2]))

    # Isolate tests because repeated Soapy/libusb device teardown in one
    # Python process can terminate the native runtime on macOS.
    failed = 0
    for name, _ in TESTS:
        completed = subprocess.run([
            sys.executable,
            '-u',
            os.path.abspath(__file__),
            '--run-one',
            name,
        ])
        if completed.returncode != 0:
            failed += 1
    sys.exit(failed)
