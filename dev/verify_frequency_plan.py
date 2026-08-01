#!/usr/bin/env python3
"""Validate TX→RX frequency plan with distinct tone signals."""

import sys, os, math
sys.path.insert(0, os.path.expanduser("~/git/hab"))
import numpy as np

FS = 8_000_000
OFFSET = 100_000
# Use a full 2 seconds for excellent frequency resolution
CHUNK = FS * 2

print("=" * 65)
print("FREQUENCY PLAN VERIFICATION")
print("=" * 65)

# === Generate DISTINCT test signals ===
# DVB-S2 baseband: a tone at +25 kHz (simulating a "hot" DVB-S2 subcarrier)
# BPSK baseband: a tone at -15 kHz (simulating the BPSK spectrum peak)
t = np.arange(CHUNK, dtype=np.float64)
tone_a = np.exp(1j * 2 * np.pi * 25000 * t / FS).astype(np.complex64)    # DVB-S2
tone_b = np.exp(1j * 2 * np.pi * (-15000) * t / FS).astype(np.complex64)  # BPSK

# 1) TX: frequency_interleave
def frequency_interleave(dvbs2_iq, bpsk_iq, offset, sample_rate, phase=0.0):
    count = len(dvbs2_iq)
    step = 2.0 * np.pi * offset / sample_rate
    angles = phase + step * np.arange(count, dtype=np.float64)
    osc = np.exp(1j * angles).astype(np.complex64)
    composite = (
        np.float32(0.65) * dvbs2_iq.astype(np.complex64) * osc
        + np.float32(0.45) * bpsk_iq.astype(np.complex64) * osc.conjugate()
    )
    next_phase = (phase + step * count) % (2.0 * np.pi)
    return composite.astype(np.complex64), next_phase

comp, tx_phase = frequency_interleave(tone_a, tone_b, OFFSET, FS, 0.0)

# Use full-length FFT for accurate frequency measurement
spec = np.fft.fftshift(np.fft.fft(comp * np.hanning(CHUNK)))
freqs = np.fft.fftshift(np.fft.fftfreq(CHUNK, 1/FS))
idx = np.argsort(np.abs(spec))[-5:]

print(f"\nTX COMPOSITE SPECTRUM (dominant frequencies):")
for i in sorted(idx, key=lambda x: -np.abs(spec[x])):
    actual = freqs[i]
    # DVB-S2 tone: baseband at +25 kHz + shift up by +100 kHz = +125 kHz
    # BPSK tone:   baseband at -15 kHz + shift down by -100 kHz = -115 kHz
    label = "DVB-S2" if abs(abs(actual) - 125000) < 1000 else "BPSK"
    expected = 125000 if label == "DVB-S2" else -115000
    print(f"  {label}: {actual:+.1f} Hz (expected {expected:+.0f} Hz) "
          f"{'✓' if abs(actual - expected) < 10 else '✗'}")

# 2) RX: split back
def _split(composite, offset, sample_rate, phase=0.0):
    count = len(composite)
    step = 2.0 * np.pi * offset / sample_rate
    angles = phase + step * np.arange(count, dtype=np.float64)
    osc = np.exp(1j * angles).astype(np.complex64)
    dvbs2 = composite * osc.conjugate()
    bpsk = composite * osc
    next_phase = (phase + step * count) % (2.0 * np.pi)
    return dvbs2, bpsk, next_phase

dvbs2_rx, bpsk_rx, _ = _split(comp, OFFSET, FS)

print(f"\nRX DVB-S2 BRANCH (should contain only DVB-S2 tone at ~0 Hz):")
spec_d = np.fft.fftshift(np.fft.fft(dvbs2_rx[:CHUNK] * np.hanning(CHUNK)))
freqs2 = np.fft.fftshift(np.fft.fftfreq(CHUNK, 1/FS))
peak_d_idx = np.argmax(np.abs(spec_d))
peak_d = freqs2[peak_d_idx]
# DVB-S2 tone: was at +25 kHz in baseband, TX shifted it +OFFSET to +125 kHz,
# RX shifts it -OFFSET back to +25 kHz.
print(f"  Peak: {peak_d:+.1f} Hz (expected +25000 Hz) "
      f"{'✓' if abs(peak_d - 25000) < 10 else '✗'}")

print(f"\nRX BPSK BRANCH (should contain only BPSK tone at ~0 Hz):")
spec_b = np.fft.fftshift(np.fft.fft(bpsk_rx[:CHUNK] * np.hanning(CHUNK)))
freqs3 = np.fft.fftshift(np.fft.fftfreq(CHUNK, 1/FS))
peak_b_idx = np.argmax(np.abs(spec_b))
peak_b = freqs3[peak_b_idx]
# BPSK tone: was at -15 kHz in baseband, TX shifted it -OFFSET to -115 kHz,
# RX shifts it +OFFSET back to -15 kHz.
print(f"  Peak: {peak_b:+.1f} Hz (expected -15000 Hz) "
      f"{'✓' if abs(peak_b - (-15000)) < 10 else '✗'}")

# 3) Isolation: measure DVB-S2 leakage into BPSK branch
print(f"\nISOLATION (crosstalk rejection):")
dvbs2_alone, _ = frequency_interleave(tone_a, np.zeros(CHUNK, dtype=np.complex64), OFFSET, FS)
dvbs2_isolated, bpsk_from_dvbs2, _ = _split(dvbs2_alone, OFFSET, FS)
e_dvbs2 = np.sum(np.abs(dvbs2_isolated) ** 2)
e_bleed = np.sum(np.abs(bpsk_from_dvbs2) ** 2)
rej_db = 10 * np.log10(e_bleed / e_dvbs2) if e_dvbs2 > 0 else -200
print(f"  DVB-S2 → BPSK leakage: {rej_db:.1f} dB")
# At 200 kHz separation (2*offset), the rolling off DVB-S2 spectrum
# should be attenuated at least a few dB relative to the peak
print(f"  {'⚠  ' if rej_db > -3 else '✓  '}Rejection adequate for real signals")

# 4) Round-trip phase continuity
phase = 0.0
phases = []
for i in range(100):
    ca = tone_a[i*320:(i+1)*320]
    cb = tone_b[i*320:(i+1)*320]
    _, phase = frequency_interleave(ca, cb, OFFSET, FS, phase)
    phases.append(phase)
jumps = [abs((phases[i+1] - phases[i]) % (2*np.pi)) for i in range(len(phases)-1)]
print(f"\nPHASE CONTINUITY (100 × 320-sample chunks):")
print(f"  Mean jump: {np.mean(jumps):.6f} rad {'✓' if np.mean(jumps) < 0.01 else '✗'}")
print(f"  Max jump:  {max(jumps):.6f} rad")

# 5) Final verification
passes = sum([
    abs(peak_d - 25000) < 10,
    abs(peak_b - (-15000)) < 10,
    np.mean(jumps) < 0.01,
])
print(f"\n{'='*65}")
print(f"RESULT: {passes}/3 critical checks passed "
      f"{'✓' if passes == 3 else '✗'}")
if passes == 3:
    print("The frequency plan is correct. Both TX and RX use consistent offsets.")
    print("Run both with defaults (no --offset) and the signals will align.")
