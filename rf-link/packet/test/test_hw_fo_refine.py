#!/usr/bin/env python3
"""Test FO refinement with real HackRF hardware."""
import sys, os, numpy as np, time
sys.path.insert(0, '/Users/charlesclaw/Documents/git/hab/rf-link/packet/src')
import SoapySDR
from pkt_enhanced_rx import (
    scan_frequency, rcc_taps, apply_digital_agc,
    SYNC_BPSK, SYNC_BITS, MAX_FEC_SYMS, decode_payload_symbols,
    PREAMBLE_BITS
)

def refine_fo(symbols, sync_idx, sps=20, fs=2000000):
    """Refine FO estimate using known sync word symbols."""
    sync_syms = symbols[sync_idx:sync_idx + SYNC_BITS]
    expected = SYNC_BPSK
    # Remove BPSK modulation: multiply by expected (±1)
    demod = sync_syms * expected  # demod is exp(j*phi_k)
    phases = np.angle(demod)
    phases_unwrapped = np.unwrap(phases)
    t_sym = np.arange(SYNC_BITS, dtype=np.float64)
    A = np.vstack([t_sym, np.ones(SYNC_BITS)]).T
    slope, intercept = np.linalg.lstsq(A, phases_unwrapped, rcond=None)[0]
    symbol_rate = fs / sps
    dfo = slope * symbol_rate / (2 * np.pi)
    return dfo

def decode_packet(symbols, idx, fo, sps, fs):
    """Decode one packet at sync position idx using refined FO."""
    # Refine FO from sync word
    dfo = refine_fo(symbols, idx, sps, fs)
    fine_fo = fo + dfo
    
    # Re-rotate: we need to remix the raw samples... 
    # Actually, we can rotate the symbols directly
    # The symbols are complex after RRC. Residual phase = exp(j*2*pi*t*dfo/symbol_rate)
    # At symbol position k (from sync start), phase = 2*pi*k*dfo/symbol_rate
    k = np.arange(len(symbols) - idx, dtype=np.float64)
    symbol_rate = fs / sps
    correction = np.exp(-2j * np.pi * dfo * k / symbol_rate)
    payload_start = idx + SYNC_BITS
    payload_n = min(MAX_FEC_SYMS, len(symbols) - payload_start)
    payload = symbols[payload_start:payload_start + payload_n]
    payload_corrected = payload * correction[:payload_n]
    
    msg, polarity = decode_payload_symbols(payload_corrected)
    if msg:
        return msg, f"refined(dFO={dfo:.1f}Hz)"
    
    # Try without refinement
    msg2, pol2 = decode_payload_symbols(payload)
    if msg2:
        return msg2, f"coarse(dFO=0)"
    return None, None

# Setup RX
serial = '000000000000000060a464dc3606610f'
fs = 2000000; sps = 20
sdr = SoapySDR.Device(f'driver=hackrf,serial={serial}')
sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, fs)
sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, 915e6)
sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'LNA', 16.0)
sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'VGA', 20.0)
sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'AMP', 1.0)
rx_stream = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
sdr.activateStream(rx_stream)

buf = np.zeros(524288, dtype=np.complex64)
accum = []
start = time.time()
print("RX ready, waiting for TX...", flush=True)

while time.time() - start < 20:
    sr = sdr.readStream(rx_stream, [buf], len(buf), timeoutUs=500000)
    if sr.ret > 0:
        accum.append(buf[:sr.ret].copy())
        total = sum(len(a) for a in accum)
        if total >= 1_000_000:
            chunk = np.concatenate(accum); accum = []
            raw = chunk - np.mean(chunk)
            max_m = np.max(np.abs(raw))
            if max_m < 0.1:
                continue
            
            fo = scan_frequency(raw, sps=sps, samp_rate=fs)
            samples = apply_digital_agc(raw)
            t = np.arange(len(samples), dtype=np.float64)
            bb = samples * np.exp(-2j * np.pi * fo * t / fs)
            bb -= np.mean(bb)
            rrc = rcc_taps(sps=sps)
            filtered = np.convolve(bb, rrc, 'same')
            
            for phase in range(min(sps, 20)):
                sym = filtered[phase::sps]
                corr = np.abs(np.correlate(sym, SYNC_BPSK, 'valid'))
                th = np.mean(corr) + 2.5 * np.std(corr)
                
                radius = 10
                for i in range(len(corr)):
                    if corr[i] < th: continue
                    lo = max(0,i-radius); hi = min(len(corr),i+radius+1)
                    if corr[i] < np.max(corr[lo:hi]): continue
                    
                    msg, how = decode_packet(sym, i, fo, sps, fs)
                    if msg:
                        print(f"DECODED: FO={fo}Hz phase={phase} idx={i} {how}  {msg!r}", flush=True)

sdr.deactivateStream(rx_stream); sdr.closeStream(rx_stream)
print("Done.", flush=True)
