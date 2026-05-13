#!/usr/bin/env python3
"""Final decoder for cable-connected packet test."""
import numpy as np
from gnuradio.filter import firdes
import sys

fs = 2e6; sps = 20

filename = sys.argv[1] if len(sys.argv) > 1 else '/tmp/rx_cable_good.iq'
raw = np.fromfile(filename, dtype=np.int8)
I = raw[0::2].astype(np.float64) - np.mean(raw[0::2])
Q = raw[1::2].astype(np.float64) - np.mean(raw[1::2])
s = I + 1j*Q
print(f"Loaded {len(s)} samples")

# Frequency offset
nfft = min(524288, len(s))
center = nfft//2
fft = np.fft.fftshift(np.fft.fft(s[:nfft]*np.hanning(nfft)))
fp = np.abs(fft)**2
fo = 0; bp = 0
for i in range(center-int(50e3/fs*nfft), center-int(500/fs*nfft)):
    if fp[i] > bp: bp = fp[i]; fo = (i-center)/fs*2e6
for i in range(center+int(500/fs*nfft), center+int(50e3/fs*nfft)):
    if fp[i] > bp: bp = fp[i]; fo = (i-center)/fs*2e6
print(f"FO: {fo/1e3:.3f} kHz")

t = np.arange(len(s))
bb = s * np.exp(-2j*np.pi*fo*t/fs)

# RRC filter
rrc = np.array(firdes.root_raised_cosine(1.0, sps, 1.0, 0.35, 11*sps))
rrc = rrc / np.sum(rrc)
filt = np.convolve(bb.real, rrc, 'same')

# Try ALL phases, for each FINE frequency correction using preamble
for phase in range(sps):
    syms = filt[phase::sps]
    if len(syms) < 400: continue
    
    # Use preamble for freq correction
    pre = syms[:256]
    diff = pre[1:] * np.conj(pre[:-1])
    w = np.abs(pre[1:]) * np.abs(pre[:-1])
    mean_diff = np.angle(np.sum(diff * w) / np.sum(w))
    resid = mean_diff - np.pi
    
    k = np.arange(len(syms))
    sc = syms * np.exp(-1j * resid * k)
    
    # Use preamble correlation to find packets
    pre_template = np.tile([1.0, -1.0], 128)
    corr = np.correlate(sc, pre_template, 'same')
    corr_power = np.abs(corr)
    
    threshold = np.mean(corr_power) + 4 * np.std(corr_power)
    peaks = []
    for i in range(len(corr_power)):
        if corr_power[i] > threshold and i > 280 and i+96 < len(sc):
            if corr_power[i] == np.max(corr_power[max(0,i-5):min(len(corr_power),i+6)]):
                peaks.append(i)
    
    for peak in peaks:
        # Try many fine offsets around expected position
        for shift in range(-30, 31):
            payload_start = peak + 288 + shift
            if payload_start + 96 > len(sc): continue
            
            pkt = sc[payload_start:payload_start+96]
            
            for invert in [False, True]:
                bits = ((pkt.real > 0) ^ invert).astype(np.uint8)
                by = []
                for i in range(0, 96, 8):
                    b = 0
                    for j in range(8):
                        b |= (int(bits[i+j]) << (7-j))
                    by.append(b)
                text = bytes(by).decode('ascii', errors='replace')
                text_inv = bytes([(~x)&0xFF for x in by]).decode('ascii', errors='replace')
                
                for t in [text, text_inv]:
                    # Score against expected
                    expected = "HELLO WORLD\n\x05"
                    score = sum(1 for a, b in zip(t, expected) if a == b) if len(t) >= len(expected) else 0
                    
                    if score >= 6:  # At least 6/12 correct chars
                        print(f"phase={phase:2d} peak={peak:6d} shift={shift:+3d} inv={int(invert)} score={score:2d}: {t.strip()!r}")
                        if score >= 11:
                            print("*** NEAR-PERFECT DECODE! ***")
