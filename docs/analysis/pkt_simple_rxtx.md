# Exhaustive Line-by-Line Analysis: `pkt_simple_rx.py` and `pkt_simple_tx.py`

> **Repository**: `~/git/hab/rf/packet/src/`
> **Date**: 2026-07-22
> **Related files**: `hello_decoder.py`, `gps_packet_tx.py`, `packet_codec.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Shared Protocol: Packet Format on the Air](#shared-protocol)
3. [`pkt_simple_rx.py` — Packet Receiver](#pkt_simple_rxpy)
   - [3.1 Imports and Globals (lines 1–36)](#31-imports-and-globals)
   - [3.2 FLL and Fine FO Estimation (lines 38–146)](#32-fll-and-fine-fo-estimation)
   - [3.3 `PacketDecoder` Class (lines 148–374)](#33-packetdecoder-class)
   - [3.4 `LiveReceiver` Class (lines 377–465)](#34-livereceiver-class)
4. [`pkt_simple_tx.py` — Packet Transmitter](#pkt_simple_txpy)
   - [4.1 Imports and Modulation Helpers (lines 1–69)](#41-imports-and-modulation-helpers)
   - [4.2 `make_packet()` and `make_test_packets()` (lines 41–90)](#42-make_packet-and-make_test_packets)
   - [4.3 `main()` Flowgraph (lines 93–152)](#43-main-flowgraph)
5. [TX/RX Symmetry Analysis](#txrx-symmetry-analysis)
6. [Resampling Rationale: `sps=20` vs `sps=4`](#resampling-rationale)

---

## 1. Overview

These two files form a complete, matched BPSK packet radio system:

| | **Transmit** | **Receive** |
|---|---|---|
| **File** | `pkt_simple_tx.py` | `pkt_simple_rx.py` |
| **Radio** | HackRF via GNU Radio `soapy.sink` | HackRF via raw SoapySDR (no GNU Radio blocks for SDR I/O) |
| **Modulation** | BPSK, RRC-shaped at `sps=20` | Same matched-filter RRC at `sps=20` |
| **Demodulation** | — | Custom Python DSP: FLL/FFT FO estimation, RRC filter, Costas loop, correlation sync |
| **Packet framing** | 256b preamble + 32b sync + 16b len + N×8b payload + 16b CRC | Same structure decoded in software |
| **Error detection** | CRC-16/XMODEM appended per packet | CRC-16/XMODEM validated on receive |

The RX is a **pure-Python DSP pipeline** — no GNU Radio flowgraph blocks for signal processing. It uses raw numpy for all filtering, correlation, and demodulation, with only temporary `gr.top_block()` mini-graphs for the band-edge FLL and Costas loop (run once, torn down immediately). The TX uses a minimal GNU Radio flowgraph (`vector_source_c → throttle → soapy.sink`) purely as a transmission harness; all waveform synthesis is done in numpy.

The design is intentionally **simple** — no FEC, no interleaving, no HDLC framing. The RX brute-forces phase alignment, bit inversion, and bit shifting rather than using a closed-loop symbol synchronizer. This makes the code transparent and debuggable at the cost of being less efficient than a streaming GNU Radio flowgraph.

---

## 2. Shared Protocol: Packet Format on the Air

Both TX and RX agree on a single packet structure (identical to that in `gps_packet_tx.py`):

```
|←──── preamble ────→|←─ sync ─→|← len →|←─── payload ───→|← CRC-16 ─→|
|   256 bits          | 32 bits  | 16 b  |    N × 8 bits    |  16 bits   |
| alternating 1,0     |0xE38FC0FC|  u16  |   raw bytes      | XMODEM     |
```

- **Preamble**: 256 bits of alternating `1,0,1,0,…`. This is a maximum-length run of transitions for the receiver's clock-recovery and phase-detection logic. At `sps=20`, this is 5,120 samples.
- **Sync word**: 32-bit pattern `0xE38FC0FC`. This is the **GNU Radio default access code** (`0xE38FC0FC`). It has good autocorrelation properties (approximating a Barker-like sequence for BPSK). The RX uses normalized cross-correlation against this.
- **Length field**: 2 bytes, big-endian unsigned 16-bit integer. Tells the RX how many payload bytes follow. Capped at `MAX_PAYLOAD_BYTES=128`.
- **Payload**: Raw bytes (text or binary). The TX default is `b"HELLO WORLD"` (11 ASCII bytes).
- **CRC-16**: CRC-16/XMODEM (polynomial `0x1021`) over the payload bytes only (not the length field).

---

## 3. `pkt_simple_rx.py` — Packet Receiver

### 3.1 Imports and Globals (lines 1–36)

```python
# Line 1: #!/usr/bin/env python3
```
Shebang for direct execution.

```python
# Lines 2–4: docstring
"""Packet Receiver - live BPSK decode from HackRF via native SoapySDR.
Uses sync-word-based correlation (proven approach from hello_decoder.py)."""
```
States the philosophy: native SoapySDR for low-overhead I/O, sync-word correlation for packet framing — a proven technique carried forward from the earlier `hello_decoder.py` prototype.

```python
# Line 6: import numpy as np
```
NumPy for all array math — filtering, correlation, FFT, statistics.

```python
# Line 7: import SoapySDR
```
**Direct SoapySDR, not GNU Radio's soapy block.** The RX uses raw SoapySDR for streaming I/Q from the HackRF. This avoids GNU Radio's scheduler overhead and gives full control over the receive buffer loop (accumulate → process → repeat). This is the key architectural decision of the RX.

```python
# Line 8: import sys, time, argparse
```
Standard library: `sys` for exit/argv, `time` for duration tracking, `argparse` for CLI.

```python
# Line 9–10: from gnuradio import gr, blocks, digital
#            from gnuradio.filter import firdes
```
GNU Radio is used **only** for two things:
1. `firdes.root_raised_cosine()` — tap generation for RRC filters
2. Temporary `gr.top_block()` graphs for the band-edge FLL and Costas loop (run once, not streaming)

```python
# Line 12–20: def crc16(data: bytes) -> int:
```
CRC-16/XMODEM implementation. Polynomial `0x1021`, initial value `0`, no final XOR. This is a standard CCITT CRC-16 variant used in XMODEM protocol. The implementation is bitwise:
- XOR each byte shifted left 8 bits into the running CRC
- For each of 8 bits: if MSB is set, shift left and XOR `0x1021`; otherwise just shift left
- Mask to 16 bits after each iteration

```python
# Line 22: SPS = 20; FS = 2000000
```
**`SPS=20`**: Samples per symbol. At `FS=2 MHz`, the symbol rate is `2e6 / 20 = 100 kbaud`. This is the same as the TX.
**`FS=2,000,000`**: The HackRF sample rate. 2 Msps is well within the HackRF's USB 2.0 bandwidth (~20 Msps max for complex samples). Chosen as a round number that gives clean symbol timing and adequate processing headroom.

```python
# Line 23: PRE_SYNC = 256; SYNC_BITS = 32; LEN_BITS = 16; CRC_BITS = 16; MAX_PAYLOAD_BYTES = 128
```
Protocol constants. `MAX_PAYLOAD_BYTES=128` limits the payload to 128 bytes (1,024 bits), keeping packet duration reasonable at ~3.8 ms of payload plus overhead.

```python
# Line 24: MAX_POST_SYNC = LEN_BITS + (MAX_PAYLOAD_BYTES + 2) * 8
```
`MAX_POST_SYNC = 16 + (128 + 2) * 8 = 1,056 bits`. This is the maximum number of bits the RX extracts after a sync-word hit for the `_decode_post_sync()` brute-force decoder. The `+2` accounts for the 2 CRC bytes being included in the byte count (since payload + CRC = `length + 2` bytes).

```python
# Line 25–29: Costas and FLL parameters
COSTAS_LOOP_BW = 2 * np.pi / 200       # Normalized loop bandwidth
COSTAS_MAX_OFFSET_HZ = 8_000           # Max frequency offset the Costas can track
FLL_LOOP_BW = 2 * np.pi / 400          # Band-edge FLL loop bandwidth
FLL_FILTER_SIZE = 45                   # Number of band-edge filter taps
FLL_MAX_OFFSET_HZ = 10_000            # Max frequency offset for the FLL pre-corrector
```
- **Costas loop bandwidth**: `2π/200 ≈ 0.0314` normalized. At symbol rate `100 kHz`, this is `~0.0314 × 100k / (2π) ≈ 500 Hz` equivalent noise bandwidth. Wide enough for residual FO after coarse correction (~hundreds of Hz), narrow enough to reject noise.
- **FLL loop bandwidth**: `2π/400 ≈ 0.0157` normalized. At sample rate 2 MHz, this is `~0.0157 × 2M / (2π) ≈ 5 kHz` equivalent bandwidth. The FLL is used for coarse correction of up to ±10 kHz.
- **`FLL_FILTER_SIZE=45`**: This is the number of filter taps in the band-edge FLL's internal filters. 45 taps at `sps=20` gives ~2.25 symbols of filter memory. The band-edge FLL works by comparing power in upper and lower band-edge filters centered at ±`Rs/2` (±50 kHz in our case).

```python
# Line 30–32: Sync word as BPSK symbols
SYNC_WORD = 0xE38FC0FC
_SYNC_BI = np.array([(SYNC_WORD >> (31-i)) & 1 for i in range(SYNC_BITS)], dtype=np.float64)
SYNC_BPSK = 2.0 * _SYNC_BI - 1.0
```
Converts the 32-bit sync word into a BPSK symbol vector for cross-correlation. Bit 0 → `+1.0`, bit 1 → `-1.0`. The correlation value at a perfect alignment is `32.0` (for normalized unity-amplitude symbols).

```python
# Line 34–36: def rcc_taps(sps=SPS, alpha=0.35, ntaps=11):
```
RRC matched-filter tap generator. Parameters:
- `sps=20`: Upsampling factor (must match TX)
- `alpha=0.35`: Roll-off factor. A moderate value balancing spectral efficiency (~35% excess bandwidth) with good timing recovery sensitivity.
- `ntaps=11`: Number of symbol periods in the filter → `11 × 20 = 220` total taps.
- Normalized to unit peak amplitude, preventing gain scaling through the filter.

### 3.2 FLL and Fine FO Estimation (lines 38–146)

#### `_run_fll(samples)` — Band-Edge FLL (lines 38–67)

```python
# Line 38–42: Input validation
def _run_fll(samples):
    samples = np.asarray(samples, dtype=np.complex64)
    if len(samples) == 0:
        return samples.copy(), 0.0
```
Empty vector guard — returns unchanged with zero offset.

```python
# Line 44–46: RMS normalization guard
    rms = float(np.sqrt(np.mean(np.abs(samples) ** 2)))
    if not np.isfinite(rms) or rms < 1e-8:
        return samples.copy(), 0.0
```
Checks for dead/zero-input buffers. Noise floor at 2e-8 RMS would be implausible for any real HackRF capture.

```python
# Line 48–52: Normalize and pad
    normalized = np.pad(
        np.asarray(samples / rms, dtype=np.complex64),
        (0, FLL_FILTER_SIZE),
    )
```
- RMS normalization: sets signal power to approximately 1.0, ensuring the FLL's internal AGC starts in a good state.
- **Zero-padding the tail by `FLL_FILTER_SIZE=45` samples**: The band-edge FLL's FIR filters introduce a group delay of `(45-1)/2 = 22` samples. Without padding, the last 22 samples of the FLL output would be transient garbage. The padding preserves valid output through the entire input buffer.

```python
# Line 53–61: GNU Radio mini-graph for FLL
    tb = gr.top_block()
    source = blocks.vector_source_c(normalized.tolist(), False)  # repeat=False
    fll = digital.fll_band_edge_cc(SPS, 0.35, FLL_FILTER_SIZE, FLL_LOOP_BW)
    fll_limit = 2 * np.pi * FLL_MAX_OFFSET_HZ / FS
    fll.set_min_freq(-fll_limit)
    fll.set_max_freq(fll_limit)
    sink = blocks.vector_sink_c()
    tb.connect(source, fll, sink)
    tb.run()
```
This creates a throwaway GNU Radio top_block that:
1. Feeds the normalized samples through a **band-edge FLL** (`digital.fll_band_edge_cc`)
2. The FLL parameters: `sps=20` (must match signal), roll-off `0.35` (must match RRC filter), `45` filter taps, loop bandwidth `2π/400`
3. Frequency limits clamped to `±10 kHz` via `set_min_freq/set_max_freq`. The conversion: `limit_rad = 2π × f_max / fs = 2π × 10000 / 2e6 ≈ 0.0314` rad/sample.
4. Output collected in `blocks.vector_sink_c()`

The band-edge FLL works by filtering the complex baseband signal through two band-edge filters centered at `±fs/(2×sps) = ±50 kHz`. It compares the power in the upper vs. lower sideband; any imbalance is proportional to the carrier frequency offset.

```python
# Line 63–67: Extract results
    corrected = np.asarray(sink.data(), dtype=np.complex64)
    input_fo_hz = -float(fll.get_frequency()) * FS / (2 * np.pi)
    return corrected, input_fo_hz
```
- `fll.get_frequency()` returns the NCO frequency in rad/sample. The **NCO applies the inverse of the input offset** (it's a correction oscillator). So the actual carrier offset at the input is the negative of this.
- Frequency in Hz: `fo_hz = -freq_rad × FS / (2π)`

#### `_fine_fo_estimate(samples, fs=FS)` — Squared-Signal FFT Estimator (lines 70–130)

This is a more sophisticated estimator that provides **sub-Hz accuracy** by squaring the BPSK signal and doing an FFT.

```python
# Line 70–80: Docstring
def _fine_fo_estimate(samples, fs=FS):
    """Estimate BPSK carrier offset with sub-Hz accuracy via squared-signal FFT.
    Squares the complex baseband to remove BPSK modulation (producing a
    clean tone at 2×Δf), then uses zero-padded FFT with parabolic
    interpolation for sub-bin resolution.
    """
```
The key insight: **squaring a BPSK signal removes the modulation.**

For a BPSK signal: `s(t) = A·exp(j(2πΔf·t + φ))` where the data is in the phase (0 or π). Squaring: `s²(t) = A²·exp(j(4πΔf·t + 2φ))`. The BPSK phase flips (0 or π) become 0 or 2π — indistinguishable. The result is a pure tone at **twice** the carrier offset. An FFT of the squared signal reveals this tone.

```python
# Line 81–83: Input validation
    samples = np.asarray(samples, dtype=np.complex64)
    if len(samples) < 1024:
        return 0.0
```
Requires at least 1,024 samples (~0.5 ms at 2 Msps). Below this, the FFT has too coarse resolution to be useful.

```python
# Line 85–86: Square to remove BPSK modulation
    squared = samples ** 2
```

```python
# Line 88–95: Decimate for FFT efficiency
    max_fft = 256 * 1024
    if len(squared) > max_fft:
        step = max(1, len(squared) // max_fft)
        squared = squared[::step]
        fs_eff = fs / step
    else:
        fs_eff = fs
```
If the capture is very long (>256k samples), decimate to keep the FFT size manageable. This is a simple decimation (no anti-alias filter) — acceptable because the tone energy is concentrated at a single frequency point and aliasing of noise into the band of interest is negligible for FO estimation.

```python
# Line 97–102: Zero-padded FFT
    n = len(squared)
    n_fft = n * 4                     # 4× zero-padding
    spectrum = np.fft.fft(squared, n=n_fft)
    spectrum = np.fft.fftshift(spectrum)
    freqs = np.fft.fftshift(np.fft.fftfreq(n_fft, d=1 / fs_eff))
    power = np.abs(spectrum)
```
- **4× zero-padding**: Quadruples the native FFT size. With ~256k input samples, `n_fft ≈ 1M`, giving bin spacing `fs_eff / 1M`. At `fs_eff=2 MHz`, bin spacing is ~2 Hz. The zero-padding interpolates the spectrum.
- `fftshift` centers the DC bin for easier indexing.

```python
# Line 104–109: Search region
    dc_idx = n_fft // 2
    bin_width = fs_eff / n_fft
    search_bins = int(20_000 / bin_width)
    lo = max(1, dc_idx - search_bins)
    hi = min(n_fft - 1, dc_idx + search_bins + 1)
```
Searches ±20 kHz around DC in the squared-signal spectrum. This corresponds to ±10 kHz carrier offset (since the tone is at `2×Δf`). Excludes DC bin itself (index `dc_idx`), which would be dominated by LO leakage and DC offset.

```python
# Line 111–122: Peak interpolation
    peak_offset = int(np.argmax(power[lo:hi]))
    peak_idx = lo + peak_offset
    y_peak = float(power[peak_idx])
    # Parabolic interpolation
    if 1 <= peak_idx < n_fft - 1:
        y_prev = float(power[peak_idx - 1])
        y_next = float(power[peak_idx + 1])
        denom = y_prev - 2 * y_peak + y_next
        delta = 0.5 * (y_prev - y_next) / denom if abs(denom) > 1e-15 else 0.0
    else:
        delta = 0.0
```
- Finds the strongest bin in the search range
- **Parabolic interpolation**: Fits a parabola through the peak and its two neighbors. The fractional bin offset `delta` gives sub-bin resolution. For a parabola `y(x) = ax² + bx + c` through points `(-1, y_prev)`, `(0, y_peak)`, `(1, y_next)`, the vertex is at `x = 0.5×(y_prev - y_next)/(y_prev - 2×y_peak + y_next)`.

```python
# Line 124–127: Validation
    median_power = float(np.median(power[lo:hi]))
    if y_peak < 5.0 * median_power:
        return 0.0
```
Requires the peak to be at least **5× the median power** (a rough SNR check). If no clear tone exists (noise-only capture), the squared signal has no distinct tone and the peak won't stand out.

```python
# Line 129–130: Convert to carrier offset
    peak_freq = freqs[peak_idx] + delta * bin_width
    return peak_freq / 2.0            # tone at 2×Δf → divide by 2
```

#### `scan_frequency(samples, fo_min, fo_max, step)` — Two-Stage FO Estimator (lines 133–146)

```python
def scan_frequency(samples, fo_min=-10000, fo_max=10000, step=100):
    del step  # step parameter is unused (legacy from hello_decoder.py)
    fo_hz = _fine_fo_estimate(samples)
    if not np.isfinite(fo_hz) or abs(fo_hz) < 0.5:
        _, fo_hz = _run_fll(samples)
    if not np.isfinite(fo_hz) or fo_hz < fo_min or fo_hz > fo_max:
        return 0.0
    return fo_hz
```
Two-stage strategy:
1. **Primary**: `_fine_fo_estimate()` (squared-signal FFT) — fast, sub-Hz accurate, but requires a clear tone
2. **Fallback**: `_run_fll()` (band-edge FLL) — robust, converges on any BPSK signal, but slower and less precise
3. **Sanity**: If the result is outside ±10 kHz, return 0.0 (assume no real signal)

The `step` parameter is accepted but deleted — it's kept for backward compatibility with `hello_decoder.py` which used a brute-force frequency scan.

### 3.3 `PacketDecoder` Class (lines 148–374)

This is the core demodulation engine. It receives complex baseband samples and returns decoded payloads.

#### `__init__` (lines 149–150)

```python
class PacketDecoder:
    def __init__(self):
        self.packets_found = 0
```
Simple counter for the live receiver's status reporting.

#### `_costas_correct()` — Fine Carrier Tracking (lines 152–177)

```python
def _costas_correct(self, complex_syms, initial_fo_hz=0.0, initial_phase=0.0):
```
Tracks residual carrier on a per-symbol (already downsampled) window using a GNU Radio Costas loop.

```python
# Line 154–160: Input validation and normalization
    complex_syms = np.asarray(complex_syms, dtype=np.complex64)
    if len(complex_syms) == 0:
        return complex_syms.copy(), 0.0
    rms = float(np.sqrt(np.mean(np.abs(complex_syms) ** 2)))
    if not np.isfinite(rms) or rms < 1e-8:
        return complex_syms.copy(), 0.0
    normalized = np.asarray(complex_syms / rms, dtype=np.complex64)
```
Same RMS normalization pattern. The Costas loop expects signals near unity amplitude.

```python
# Line 163–173: GNU Radio mini-graph
    tb = gr.top_block()
    source = blocks.vector_source_c(normalized.tolist(), False)
    costas = digital.costas_loop_cc(COSTAS_LOOP_BW, 2, False)
    costas_limit = COSTAS_MAX_OFFSET_HZ * 2 * np.pi * SPS / FS
    costas.set_min_freq(-costas_limit)
    costas.set_max_freq(costas_limit)
    costas.set_frequency(initial_fo_hz * 2 * np.pi * SPS / FS)
    costas.set_phase(initial_phase)
    sink = blocks.vector_sink_c()
    tb.connect(source, costas, sink)
    tb.run()
```
GNU Radio Costas loop configuration:
- **`COSTAS_LOOP_BW = 2π/200`**: Loop bandwidth in rad/sample (at symbol rate)
- **Order `2`**: BPSK Costas loop — the error detector uses the product of I×Q
- **`False`**: Not a differential BPSK loop (the code handles 180° ambiguity separately via `try_invert`)
- **Frequency limit conversion**: The Costas operates at symbol rate (`fs/SPS = 100 kHz`). To convert a max frequency offset in Hz to rad/symbol: `freq_limit = 2π × f_offset × SPS / FS = 2π × 8000 × 20 / 2e6 = 2π × 0.08 ≈ 0.503 rad/symbol`
- **Initial frequency seeding**: `costas.set_frequency(initial_fo_hz × 2π × SPS / FS)` seeds the loop with the coarse FO estimate, so it only needs to track the residual

```python
# Line 175–177: Extract results
    corrected = np.asarray(sink.data(), dtype=np.complex64)
    residual_fo_hz = float(costas.get_frequency()) * FS / (2 * np.pi * SPS)
    return corrected, residual_fo_hz
```
The total carrier offset for the packet is `coarse_fo + residual_fo`.

#### `_decode_post_sync()` — Brute-Force Payload Decoder (lines 179–213)

```python
@staticmethod
def _decode_post_sync(post_syms):
    """Return (payload, length) when length and CRC validate."""
    bits_hard = (np.asarray(post_syms).real < 0).astype(np.uint8)
```
Hard BPSK decision: real part < 0 → bit 1, real part ≥ 0 → bit 0. This matches the TX mapping (bit 0 → +1, bit 1 → -1).

```python
# Line 184–213: Brute-force search over ambiguity
    for try_invert in (False, True):
        bits = bits_hard if not try_invert else 1 - bits_hard
        for shift in range(8):
            shifted = bits[shift:]
```
This is the key brute-force approach. Two ambiguities exist:
1. **BPSK 180° ambiguity**: The Costas loop can lock with inverted polarity. `try_invert` handles this.
2. **Bit alignment ambiguity**: The sync-word correlation gives symbol-level alignment, but there may be a sub-symbol sample offset. `shift in range(8)` tests all 8 possible bit shifts within a byte.

```python
# Line 191–195: Parse length field
            length = 0
            for bit in shifted[:LEN_BITS]:
                length = (length << 1) | int(bit)
            if length < 1 or length > MAX_PAYLOAD_BYTES:
                continue
```
Reads the 16-bit big-endian length field. Immediately rejects implausible lengths (<1 or >128).

```python
# Line 197–199: Check buffer size
            pkt_bits = LEN_BITS + (length * 8) + CRC_BITS
            if pkt_bits > len(shifted):
                continue
```
`pkt_bits = 16 + length×8 + 16` — total bits needed. If the shifted buffer is too short, skip this trial.

```python
# Line 201–206: Bit-to-byte conversion (MSB first)
            packet_bytes = []
            for offset in range(0, pkt_bits, 8):
                value = 0
                for bit in shifted[offset:offset + 8]:
                    value = (value << 1) | int(bit)
                packet_bytes.append(value)
```
Groups bits into bytes, MSB first. This produces an array of bytes: `[len_hi, len_lo, payload[0], …, payload[N-1], crc_hi, crc_lo]`.

```python
# Line 208–211: CRC validation
            payload = bytes(packet_bytes[2:2 + length])
            rx_crc = (packet_bytes[2 + length] << 8) | packet_bytes[3 + length]
            if crc16(payload) == rx_crc:
                return payload, length
```
Extracts payload bytes and received CRC, computes expected CRC, and checks equality. On first match, returns immediately — **no duplicate checking**. The CRC-16 provides 1-in-65536 false-positive probability per trial (with up to 16 trials: 2 inversions × 8 shifts, actual false positive rate ~0.02%).

```python
# Line 213: return None
```
No valid combination found.

#### `_burst_regions()` — Burst Detection (lines 215–262)

```python
@staticmethod
def _burst_regions(samples, block_samples=2048):
    """Find gapped RF bursts, returning guarded sample ranges.
    When the capture is continuous or has no clear energy contrast, the
    whole vector is returned so carrier loops retain their streaming
    behavior. A one-block hole is merged to tolerate shaped packet edges.
    """
```
Finds regions of the sample buffer that contain actual RF energy (packets), allowing the decoder to skip dead air between bursts. This is critical for the live receiver, which accumulates ~1M samples at a time — most of which may be noise.

```python
# Line 223–225: Short buffer fallback
    samples = np.asarray(samples)
    if len(samples) < block_samples * 4:
        return [(0, len(samples))]
```
If fewer than 8,192 samples (4 blocks of 2,048 = ~4 ms), process everything as one region.

```python
# Line 227–233: Block RMS computation
    block_count = int(np.ceil(len(samples) / block_samples))
    padded = np.pad(samples, (0, block_count * block_samples - len(samples)))
    block_rms = np.sqrt(np.mean(
        np.abs(padded.reshape(block_count, block_samples)) ** 2,
        axis=1,
    ))
```
Reshapes the sample vector into `block_count` blocks of `block_samples` samples each, then computes RMS power per block. Padding ensures the last block is full length. Each block is 2,048 samples = ~1 ms at 2 Msps.

```python
# Line 233–238: Noise floor and signal estimate
    noise_rms = float(np.percentile(block_rms, 30))
    signal_rms = float(np.percentile(block_rms, 99))
    if not np.isfinite(noise_rms + signal_rms):
        return [(0, len(samples))]
    if signal_rms < max(noise_rms * 1.8, noise_rms + 1e-4):
        return [(0, len(samples))]
```
- `noise_rms`: 30th percentile — robust estimate of the noise floor (blocks without signal)
- `signal_rms`: 99th percentile — peak signal power
- If the contrast is less than 1.8× or less than 0.1 mV RMS, treat as continuous signal (no bursts to separate)

```python
# Line 240–243: Threshold and active blocks
    threshold = noise_rms + 0.25 * (signal_rms - noise_rms)
    active_blocks = np.flatnonzero(block_rms > threshold)
    if len(active_blocks) == 0:
        return [(0, len(samples))]
```
Threshold at 25% of the way from noise to signal. Finds blocks exceeding this threshold.

```python
# Line 245–247: Grouping
    splits = np.flatnonzero(np.diff(active_blocks) > 2) + 1
    groups = np.split(active_blocks, splits)
```
Splits active blocks into groups separated by **more than 2 consecutive inactive blocks** (~3 ms gap). A gap of 1-2 blocks is merged (tolerates shaped packet edges that may dip below threshold between adjacent blocks).

```python
# Line 248–262: Build regions with guard blocks
    guard_blocks = 2
    regions = []
    for group in groups:
        if len(group) < 2:
            continue            # skip single-block "blips"
        start_block = max(0, int(group[0]) - guard_blocks)
        end_block = min(block_count, int(group[-1]) + guard_blocks + 1)
        start = start_block * block_samples
        end = min(len(samples), end_block * block_samples)
        if regions and start <= regions[-1][1]:
            regions[-1] = (regions[-1][0], max(regions[-1][1], end))
        else:
            regions.append((start, end))
```
- Adds 2 guard blocks (~2 ms) before and after each active region to capture preamble and tail
- Merges overlapping/adjacent regions
- Returns list of `(start_sample, end_sample)` tuples

#### `decode()` — Top-Level Decode Entry Point (lines 264–290)

```python
def decode(self, samples_complex, raw_signal=None):
    samples = np.asarray(samples_complex, dtype=np.complex64)
    if len(samples) == 0:
        return []
```

```python
# Line 269–270: Direct decode path (no burst splitting)
    if raw_signal is not None:
        return self._decode_segment(samples, raw_signal=raw_signal)
```
When `raw_signal` is provided (a separate high-resolution capture for FO estimation), directly decode the entire segment without burst splitting.

```python
# Line 272–290: Burst-aware decode with deduplication
    results = []
    sync_positions = []
    for start, end in self._burst_regions(samples):
        for result in self._decode_segment(samples[start:end]):
            absolute_sync = start + result[3] + result[4] * SPS
            if any(abs(absolute_sync - prior) <= SPS for prior in sync_positions):
                continue
            sync_positions.append(absolute_sync)
            phase = absolute_sync % SPS
            sync_idx = absolute_sync // SPS
            results.append((
                result[0],      # payload bytes
                result[1],      # total packet length (payload + 10)
                result[2],      # total FO in Hz
                phase,          # fractional sample phase (0..SPS-1)
                sync_idx,       # integer sync symbol index
                result[5],      # payload length
            ))
    return sorted(results, key=lambda result: result[3] + result[4] * SPS)
```
Key logic:
1. Splits into burst regions
2. Decodes each region independently
3. **Deduplicates** across regions: if two hits are within `SPS` samples of each other (same sample in the original buffer), keeps only the first
4. Converts per-region sync positions to absolute sample positions
5. Sorts by absolute position for chronological output

The result tuple format: `(payload, total_len, fo_hz, phase, sync_idx, payload_len)`.

#### `_decode_segment()` — Core DSP Pipeline (lines 292–374)

This is the heart of the receiver. It processes a single contiguous sample buffer through the full demodulation chain.

```python
# Line 292–296: Setup
def _decode_segment(self, samples_complex, raw_signal=None):
    samples = np.asarray(samples_complex, dtype=np.complex64)
    if len(samples) == 0:
        return []
    samples = samples - np.mean(samples)
```
**DC offset removal**: Subtracts the mean of the complex samples. This removes any static DC offset from the HackRF's zero-IF architecture, which would otherwise appear as a tone at DC and confuse the FO estimation.

```python
# Line 298–305: Coarse frequency offset estimation
    if raw_signal is None:
        coarse_fo = _fine_fo_estimate(samples)
        if abs(coarse_fo) < 0.5:
            _, coarse_fo = _run_fll(samples)
    else:
        coarse_fo = _fine_fo_estimate(np.asarray(raw_signal, dtype=np.complex64))
        if abs(coarse_fo) < 0.5:
            _, coarse_fo = _run_fll(np.asarray(raw_signal, dtype=np.complex64))
```
Two-stage FO estimation (as in `scan_frequency()`). When `raw_signal` is provided, FO is estimated from the raw signal rather than the decimated segment — useful when the segment is too short for good FFT resolution.

```python
# Line 306–307: Mix down to true baseband
    t = np.arange(len(samples))
    bb = samples * np.exp(-2j * np.pi * coarse_fo * t / FS)
```
Complex mixing: multiplies by `exp(-j·2π·fo·t/fs)` to shift the signal so the carrier is centered at DC. This is a software equivalent of the HackRF's digital down-converter after the initial tuning.

```python
# Line 309–310: RRC matched filter
    rrc = rcc_taps()
    filt = np.convolve(bb, rrc, 'same')
```
Applies the RRC matched filter to the entire baseband signal. With 220 taps, `np.convolve(…, 'same')` produces output the same length as the input (centered). The matched filter maximizes SNR by correlating with the transmitted pulse shape.

```python
# Line 312–318: Per-phase downsampling
    phase_streams = []
    for phase in range(SPS):
        symbols = filt[phase::SPS]
        if len(symbols) < PRE_SYNC + SYNC_BITS + LEN_BITS + 8:
            continue
        phase_streams.append((phase, symbols))
```
**This is the key brute-force element.** Instead of using a symbol timing recovery loop (e.g., Mueller & Müller, Gardner), the code tries all 20 possible decimation phases. For each phase `p ∈ {0..19}`:
1. Downsample `filt[p::SPS]` — take every 20th sample starting at offset `p`
2. This gives one symbol-rate stream per phase
3. Each stream is tested independently for sync-word correlation

The minimum symbol count check ensures enough symbols exist for at least the preamble, sync word, length field, and a few payload bits.

```python
# Line 320–345: Per-phase correlation and candidate generation
    candidates = []
    for phase, symbols in phase_streams:
        corrected, residual_fo = self._costas_correct(symbols)

        corr = np.correlate(corrected, SYNC_BPSK, 'valid')
        cp = np.abs(corr)
        th = np.mean(cp) + 3.5 * np.std(cp)
```
For each phase:
1. **Costas correction**: Tracks out residual carrier on the symbol-rate stream
2. **Sync-word correlation**: Cross-correlation with the known 32-symbol BPSK sync pattern
3. **Adaptive threshold**: `mean(|corr|) + 3.5 × std(|corr|)`. This 3.5σ threshold is conservative — with Gaussian noise correlation statistics, peaks above 3.5σ occur with probability ~0.0002 per correlation bin. For a 1,000-symbol window, this gives ~0.2 false positives per phase, or ~4 across all 20 phases. These are filtered by CRC validation.

```python
# Line 330–345: Peak extraction
        for i in range(len(cp)):
            if cp[i] < th:
                continue
            lo = max(0, i - 10); hi = min(len(cp), i + 11)
            if cp[i] < np.max(cp[lo:hi]):
                continue     # not a local maximum
            if i < PRE_SYNC or i + SYNC_BITS + LEN_BITS + 8 > len(symbols):
                continue     # too close to edge
            candidates.append((
                float(cp[i]),        # correlation magnitude
                phase,               # decimation phase (0..19)
                i,                   # sync word start index (symbols)
                corrected,           # Costas-corrected symbols
                phase + i * SPS,     # absolute sample position
                residual_fo,         # residual FO in Hz
            ))
```
Peak detection with:
- **Local maximum check**: Radius 10 symbols. A peak is valid only if it's the maximum within ±10 symbols of itself.
- **Edge guard**: Requires at least `PRE_SYNC=256` symbols before the sync (preamble must exist) and at least `LEN_BITS + 8 = 24` symbols after (need room for length field + some payload).

```python
# Line 347–373: Candidate resolution
    results = []
    decoded_positions = []
    for _, phase, sync_idx, corrected, absolute_sync, residual_fo in sorted(
        candidates,
        key=lambda item: (item[4], -item[0]),
    ):
        if any(abs(absolute_sync - prior) <= SPS for prior in decoded_positions):
            continue
```
Sorts candidates by **absolute sample position** (ascending), then by **correlation strength** (descending). Deduplicates: skips candidates within `SPS` samples of an already-decoded position.

```python
        post_start = sync_idx + SYNC_BITS
        if len(corrected) < post_start + LEN_BITS + 8:
            continue
        decoded = self._decode_post_sync(corrected[post_start:post_start + MAX_POST_SYNC + 7])
        if decoded is None:
            continue
```
Extracts `MAX_POST_SYNC + 7` symbols after the sync word (the `+7` allows for up to 7 bits of shift in the brute-force decoder). Calls `_decode_post_sync()` which brute-forces polarity, bit shift, and validates CRC.

```python
        payload, length = decoded
        decoded_positions.append(absolute_sync)
        results.append((
            payload,
            length + 10,           # total bytes (payload + 2 len + 2 CRC + ~6 preamble overhead)
            coarse_fo + residual_fo,
            phase,
            sync_idx,
            length,
        ))
```
`length + 10` is an approximate total packet byte count for display purposes.

### 3.4 `LiveReceiver` Class (lines 377–465)

#### `__init__` (lines 378–381)

```python
class LiveReceiver:
    def __init__(self, freq=915e6, lna=8, vga=12, amp=False, serial=None, duration=30):
        self.fs = int(FS); self.decoder = PacketDecoder()
        self.freq = freq; self.lna = lna; self.vga = vga; self.amp = amp
        self.serial = serial; self.duration = duration
```
Default frequency: 915 MHz (ISM band). Default gains are conservative (LNA=8, VGA=12) — good for near-field testing. The `__main__` block overrides these with more aggressive defaults (LNA=32, VGA=40).

#### `run()` — Live Receive Loop (lines 383–434)

```python
# Line 384–391: HackRF configuration via SoapySDR
    dev_str = f'driver=hackrf,serial={self.serial}' if self.serial else 'driver=hackrf'
    print(f"[PktRx] Opening...")
    sdr = SoapySDR.Device(dev_str)
    sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, self.fs)
    sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, self.freq)
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'LNA', float(self.lna))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'VGA', float(self.vga))
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 'AMP', float(self.amp))
```
Direct SoapySDR device open and configuration. The HackRF driver string optionally includes a serial number for multi-device setups. Channel 0 is always used (single-channel RX).

```python
# Line 394–395: Stream setup
    rx_stream = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)
```
- `SOAPY_SDR_CF32`: Complex float32 format. The HackRF driver converts from its native 8-bit I/Q to float32.
- Stream activation starts the ADC and USB transfers.

```python
# Line 397–399: Buffer and accumulator
    buf = np.zeros(524288, dtype=np.complex64)
    accum = []
    start = time.time()
```
- **524,288 samples per read**: This is `2^19` samples = ~262 ms at 2 Msps. Large enough for efficient USB transfers, small enough for reasonable latency.
- **`accum`**: Accumulates multiple read buffers until ≥1M samples, then processes. This batch size gives good FO estimation accuracy (~0.5 Hz bin spacing at 1M samples with 4× zero padding).

```python
# Line 401–402: Main loop
    try:
        while self.duration == 0 or time.time() - start < self.duration:
```
- `duration=0` means run forever (until Ctrl-C)
- Otherwise, runs for `duration` seconds

```python
# Line 403–405: Read from HackRF
            sr = sdr.readStream(rx_stream, [buf], len(buf), timeoutUs=500000)
            if sr.ret > 0:
                accum.append(buf[:sr.ret].copy())
```
- `timeoutUs=500000` (500 ms timeout): Prevents blocking forever if the HackRF stops producing data
- `sr.ret`: Number of samples actually read. Copies only the valid portion.
- `accum` grows until ≥1M samples

```python
# Line 407–422: Process accumulated buffer
            total = sum(len(a) for a in accum)
            if total >= 1000000:
                chunk = np.concatenate(accum)
                texts = self.decoder.decode(chunk)
                for text, score, fo, phase, sync_idx, length in texts:
                    self.decoder.packets_found += 1
                    if args.hex_output:
                        print(f"[PktRx] #{self.decoder.packets_found} FO={fo/1e3:.1f} kHz phase={phase} | {text.hex()}", flush=True)
                    else:
                        clean = text.decode('ascii', errors='replace').strip()
                        if 'HELLO' in clean.upper() or 'WORLD' in clean.upper():
                            print(f"[PktRx] *** HELLO WORLD! *** FO={fo/1e3:.1f} kHz phase={phase} score={score} | {clean!r}", flush=True)
                        else:
                            print(f"[PktRx] #{self.decoder.packets_found} FO={fo/1e3:.1f} kHz | {clean!r}", flush=True)
                accum = []
```
Processing on ≥1M samples accumulated:
1. Concatenates all accumulated buffers
2. Calls `decoder.decode(chunk)` — runs full DSP pipeline
3. For each decoded packet, prints details

**The `--hex-output` flag** (line 414–421): When set, payloads are printed as hexadecimal (`text.hex()`) rather than ASCII. This is critical for binary payloads (e.g., GPS PositionFrame data from `gps_packet_tx.py`), which would produce garbage when decoded as ASCII. When not in hex mode, payloads are decoded as ASCII with replacement characters for non-printable bytes.

The special "HELLO WORLD" detection (lines 418–419) is a convenience for the default test payload — it highlights the canonical test message with asterisks.

```python
# Line 424–426: Progress reporting
                elapsed = time.time() - start
                if self.decoder.packets_found > 0:
                    print(f"[PktRx] Progress: {elapsed:.0f}s, {self.decoder.packets_found} good packets", flush=True)
```

```python
# Line 427–428: Ctrl-C handling
        except KeyboardInterrupt:
            pass
```

```python
# Line 430–434: Cleanup
        sdr.deactivateStream(rx_stream)
        sdr.closeStream(rx_stream)
        elapsed = time.time() - start
        if self.decoder.packets_found > 0:
            print(f"[PktRx] DONE. {elapsed:.0f}s, {self.decoder.packets_found} good packets.")
```

#### `__main__` — CLI Entry Point (lines 437–465)

```python
# Line 438–448: Argument parsing
parser = argparse.ArgumentParser(description='Packet RX')
parser.add_argument('--freq', type=float, default=915e6)
parser.add_argument('--lna', type=float, default=32)
parser.add_argument('--vga', type=float, default=40)
parser.add_argument('--amp', action='store_true', default=True)
parser.add_argument('--serial', type=str, default=None)
parser.add_argument('--duration', type=int, default=30)
parser.add_argument('--file', type=str, default=None)
parser.add_argument('--hex-output', action='store_true', default=False,
                    help='Output decoded payloads as hex (for binary data)')
```
Default gains are higher than the `LiveReceiver.__init__` defaults (LNA=32 vs 8, VGA=40 vs 12). The `--file` option enables offline processing of pre-recorded IQ files (8-bit interleaved I/Q format).

```python
# Line 450–461: File processing mode
if args.file:
    raw = np.fromfile(args.file, dtype=np.int8)
    I = raw[0::2].astype(np.float64); Q = raw[1::2].astype(np.float64)
    I -= np.mean(I); Q -= np.mean(Q)
    decoder = PacketDecoder()
    texts = decoder.decode(I + 1j*Q)
    for text, score, fo, phase, sync_idx, length in texts:
        if args.hex_output:
            print(f"FO={fo/1e3:.1f} kHz len={length} | {text.hex()}")
        else:
            clean = text.decode('ascii', errors='replace').strip()
            print(f"FO={fo/1e3:.1f} kHz score={score} len={length} | {clean!r}")
```
File mode reads raw 8-bit interleaved I/Q, converts to complex float64, removes DC per channel, and runs the full decoder. Same `--hex-output` behavior.

```python
# Line 462–465: Live mode
else:
    rx = LiveReceiver(freq=args.freq, lna=args.lna, vga=args.vga,
                      amp=args.amp, serial=args.serial, duration=args.duration)
    rx.run()
```

---

## 4. `pkt_simple_tx.py` — Packet Transmitter

### 4.1 Imports and Modulation Helpers (lines 1–69)

```python
# Line 1–5: Header
#!/usr/bin/env python3
"""Packet HELLO Transmitter - sends 'HELLO WORLD\n' as BPSK packets.
Uses hybrid approach: pre-computed waveform → vector_source_c → throttle → SoapySDR."""
```
The TX describes itself as "hybrid": waveform computation happens in numpy (pre-computed), then GNU Radio handles playback timing and SDR I/O.

```python
# Line 6–9: Imports
import numpy as np
from gnuradio import gr, blocks, soapy
from gnuradio.filter import firdes
import argparse, time, struct
```
GNU Radio `soapy.sink` for HackRF output (the newer GNU Radio soapy block, as opposed to the RX's raw SoapySDR).

```python
# Line 11: FS = 2_000_000
```
Sample rate, matching the RX.

```python
# Line 13–28: def bpsk_modulate(bits, sps=20, rrc_alpha=0.35):
```
Converts bits to a complex BPSK waveform with RRC pulse shaping.

```python
# Line 15–16: Bit to symbol mapping
    mapped = np.array(bits, dtype=np.float64) * -2.0 + 1.0
```
- Bit 0 → `+1.0` (I channel, zero phase)
- Bit 1 → `-1.0` (I channel, 180° phase)

This is standard BPSK: the signal is purely real (no Q component), so all energy goes into the I channel.

```python
# Line 17–19: Upsampling
    up = np.zeros(len(mapped) * sps, dtype=np.float64)
    up[::sps] = mapped
```
Zero-order hold upsampling: places each symbol value at `index*SPS`, leaves zeros everywhere else. The RRC filter will interpolate the zeros into a smooth waveform.

```python
# Line 20–23: RRC pulse shaping filter
    taps = firdes.root_raised_cosine(sps, sps, 1.0, rrc_alpha, 11 * sps)
    taps_np = np.array(taps)
    waveform = np.convolve(up, taps_np, 'same')
```
RRC filter parameters:
- **Gain `sps`**: This scales the filter so the output amplitude is ~1.0 (the filter integrates the upsampled impulses). The energy in one symbol at the input is spread across `sps` samples; the filter gain compensates.
- **Symbol rate `sps`**: The RRC filter is designed with unity symbol rate (the `sps` parameter in GNU Radio's `root_raised_cosine` is the interpolation factor, which equals the samples per symbol here since the input is already upsampled).
- **`rrc_alpha=0.35`**: Roll-off factor, must match the RX matched filter.
- **`ntaps = 11 * sps = 220`**: 11 symbol periods of filter memory. This is a trade-off: more taps give better stopband rejection but increase group delay and computational cost. 11 symbols is generous for α=0.35 (the impulse response decays to ~1% within ~5 symbol periods).

```python
# Line 24–28: Amplitude scaling
    peak = np.max(np.abs(waveform))
    if peak > 0.7:
        waveform = waveform * (0.7 / peak)
    return waveform.astype(np.complex64).tolist()
```
Scales the waveform so the peak amplitude never exceeds 0.7. The HackRF's DAC expects values in [-1.0, +1.0] for the complex baseband (though the USB protocol uses signed 8-bit integers, SoapySDR handles the conversion). The 0.7 headroom prevents clipping from filter ringing on symbol transitions. Returns as `complex64` list for direct use in `vector_source_c`.

#### `crc16()` — CRC-16/XMODEM (lines 30–38)

Identical to the RX version. The TX computes CRC-16 over the payload and appends it to the packet; the RX validates it.

#### `make_packet()` — Packet Waveform Builder (lines 41–69)

```python
def make_packet(payload_bytes, sps=20):
    """Build a complete packet waveform: preamble + sync + 2-byte len + payload + 2-byte CRC."""
```

```python
# Line 43–44: Preamble
    preamble_bits = ([1, 0] * 128)[:256]
```
256 bits of alternating `1,0` pattern. Multiplied to 128 pairs then sliced to exactly 256. This is a maximal-transition pattern: every bit period has a transition, giving the receiver's clock recovery the most information.

```python
# Line 45–47: Sync word
    sync_word = 0xE38FC0FC
    sync_bits = [(sync_word >> (31 - i)) & 1 for i in range(32)]
```
The 32-bit GNU Radio default access code, decomposed MSB-first into individual bits.

```python
# Line 49–51: Length field
    length = len(payload_bytes)
    len_bytes = struct.pack('>H', length)
```
2-byte big-endian unsigned short (`>H` format). This is the same format the RX's `_decode_post_sync()` expects when it reads `shifted[:LEN_BITS]`.

```python
# Line 53–55: CRC
    crc = crc16(payload_bytes)
    crc_bytes = struct.pack('>H', crc)
```
CRC-16/XMODEM, big-endian. The RX expects these two bytes immediately after the payload.

```python
# Line 57–62: _bytes_to_bits helper
    def _bytes_to_bits(bs):
        bits = []
        for b in bs:
            for i in range(8):
                bits.append((b >> (7 - i)) & 1)
        return bits
```
MSB-first bit decomposition. Each byte produces 8 bits, most significant first. This matches the RX's bit reassembly in `_decode_post_sync()`.

```python
# Line 64–69: Assembly and modulation
    all_bits = (preamble_bits + sync_bits +
                _bytes_to_bits(len_bytes) +
                _bytes_to_bits(payload_bytes) +
                _bytes_to_bits(crc_bytes))
    return bpsk_modulate(all_bits, sps)
```
Concatenates all bit fields and feeds them through the BPSK modulator. The bit ordering is:

```
[preamble(256)] [sync(32)] [len_hi(8)] [len_lo(8)] [payload(N×8)] [crc_hi(8)] [crc_lo(8)]
```

#### `make_test_packets()` — Burst Builder (lines 72–90)

```python
def make_test_packets(payload, sps=20, n_packets=20, gap_ms=50, sample_rate=FS):
```

```python
# Line 74–79: Compute dimensions
    packet_waveform = np.array(make_packet(payload, sps))
    total_packet_len = len(packet_waveform)
    gap_samples = int(round(gap_ms * sample_rate / 1000.0))
    packet_ms = total_packet_len / sample_rate * 1000.0
```
- `gap_samples`: 50 ms of silence → `50e-3 × 2e6 = 100,000` samples between packets
- `packet_ms`: For the default "HELLO WORLD" (11 bytes): `256 + 32 + 16 + 88 + 16 = 408 bits → 408 × 20 = 8,160 samples → ~4.1 ms`

```python
# Line 82–89: Build burst
    burst = []
    for i in range(n_packets):
        if i > 0:
            burst.extend([0j] * gap_samples)
        burst.extend(packet_waveform.tolist())
```
20 identical packets with 50 ms gaps. The gaps are silent (zero complex samples), giving the RX's burst detector clear boundaries between packets.

### 4.3 `main()` Flowgraph (lines 93–152)

```python
# Line 93–106: Argument parsing
def main():
    parser = argparse.ArgumentParser(description='Packet HELLO TX')
    parser.add_argument('--freq', type=float, default=915e6)
    parser.add_argument('--samp', type=float, default=2e6)
    parser.add_argument('--vga', type=float, default=30)
    parser.add_argument('--amp', action='store_true', default=False)
    parser.add_argument('--serial', type=str, default=None)
    parser.add_argument('--repeat', type=float, default=2.0)
    parser.add_argument('--message', type=str, default='HELLO WORLD')
    parser.add_argument('--gap', type=float, default=50)
```
Key parameters:
- `--repeat 2.0`: Burst period — the entire burst of 20 packets repeats every 2 seconds
- `--message 'HELLO WORLD'`: The payload string
- `--gap 50`: Inter-packet gap in milliseconds
- `--amp` defaults to `False` (TX amplifier off by default — safer for testing)

```python
# Line 108–109: Configure
    fs = int(args.samp)
    payload = args.message.encode('utf-8')
```
Encodes the message string as UTF-8 bytes. For ASCII text like "HELLO WORLD", this is identical to `bytes(message, 'ascii')`.

```python
# Line 111–112: Build burst
    burst = make_test_packets(payload, gap_ms=args.gap, sample_rate=fs)
```
Pre-computes the entire burst waveform.

```python
# Line 114–117: Add repeat gap
    burst_ms = len(burst) / fs * 1000
    repeat_gap = max(0, int(args.repeat * fs - len(burst)))
    full_waveform = burst + [0j] * repeat_gap
```
Computes the silence needed after the burst to achieve the requested repeat period. For example, if the burst is 20×4.1ms data + 19×50ms gaps ≈ 1,032 ms, and `--repeat=2.0`, then `repeat_gap = 2.0×2e6 - len(burst)` ≈ 1,936,000 zero samples of silence. The total waveform is ~2 seconds.

```python
# Line 122–128: GNU Radio flowgraph construction
    src = blocks.vector_source_c(full_waveform, True)
    thr = blocks.throttle(gr.sizeof_gr_complex, fs)
    sink = soapy.sink('driver=hackrf', 'fc32', 1,
                      f'serial={args.serial}' if args.serial else '',
                      '', [''], [''])
```
The flowgraph is minimal:
1. **`vector_source_c(full_waveform, repeat=True)`**: Plays the pre-computed waveform. `repeat=True` makes it loop indefinitely.
2. **`throttle(gr.sizeof_gr_complex, fs)`**: Rate-limits samples to exactly `fs` samples/second. This is a **host-side throttle**, not a hardware timer — it paces the GNU Radio scheduler to match the sample rate. Without it, the vector source would blast samples as fast as the CPU allows, overwhelming the HackRF's USB buffer.
3. **`soapy.sink('driver=hackrf', 'fc32', 1, …)`**: HackRF TX sink. The `soapy.sink` constructor arguments are: driver string, I/O type (`fc32` = complex float32), number of channels (1), device args (serial), stream args, channel args (antenna, gain).

```python
# Line 129–133: Sink configuration
    sink.set_sample_rate(0, fs)
    sink.set_bandwidth(0, 0)
    sink.set_frequency(0, args.freq)
    sink.set_gain(0, 'AMP', 1.0 if args.amp else 0.0)
    sink.set_gain(0, 'VGA', float(args.vga))
```
- `set_bandwidth(0, 0)`: Sets the TX bandwidth to 0 (= automatic). The HackRF firmware will set the analog baseband filter to match the sample rate.
- `set_gain('AMP', …)`: Controls the HackRF's TX amplifier. 1.0 = on, 0.0 = off. Off by default for safety.
- `set_gain('VGA', …)`: TX variable gain. Default 30 dB. The HackRF's TX VGA range is 0-47 dB.

```python
# Line 135–137: Connect and start
    tb = gr.top_block()
    tb.connect(src, thr)
    tb.connect(thr, sink)
```
Simple linear flowgraph: `src → throttle → sink`.

```python
# Line 139–148: Run loop
    print(f"[PktSimpleTX] TX started: '{args.message}'. Press Ctrl-C to stop.")
    tb.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    tb.stop()
    tb.wait()
```
- `tb.start()`: Starts the GNU Radio scheduler in a background thread
- `time.sleep(1)` in a loop: Keeps the main thread alive. The GNU Radio scheduler runs independently.
- `tb.stop() + tb.wait()`: Graceful shutdown

---

## 5. TX/RX Symmetry Analysis

### Matched Elements

| Feature | TX | RX |
|---|---|---|
| **Sample rate** | `FS = 2_000_000` | `FS = 2000000` |
| **Samples per symbol** | `sps=20` | `SPS=20` |
| **RRC roll-off** | `alpha=0.35` | `alpha=0.35` (in `rcc_taps()`) |
| **RRC filter length** | `11 * sps = 220` taps | `ntaps=11` → `11 * sps = 220` taps |
| **Sync word** | `0xE38FC0FC` | `SYNC_WORD = 0xE38FC0FC` |
| **Preamble** | 256 bits alternating 1,0 | `PRE_SYNC = 256` |
| **Length field** | 16-bit big-endian | `LEN_BITS = 16`, MSB-first parsing |
| **CRC** | CRC-16/XMODEM (0x1021) | Same polynomial, same implementation |
| **BPSK mapping** | bit 0 → +1, bit 1 → -1 | `bits_hard = (syms.real < 0)` → bit 1 |

### Asymmetries

1. **I/O architecture**: TX uses GNU Radio `soapy.sink`; RX uses raw SoapySDR. This is because the RX needs fine-grained control over the accumulate-buffer-and-process loop, which is harder to express in GNU Radio's streaming model.

2. **Filter normalization**: TX's RRC filter gain is `sps=20` (to compensate for upsampling); RX's RRC filter is normalized to max tap = 1.0. Both produce equivalent matched-filter outputs because the correlation's adaptive threshold is relative.

3. **Timing recovery**: TX has none (it generates the waveform). RX brute-forces 20 phases instead of using a closed-loop symbol synchronizer. This is a deliberate simplicity trade-off.

4. **BPSK ambiguity**: TX has deterministic polarity. RX tests both polarities (`try_invert`) because the Costas loop can lock 180° out of phase.

5. **Throttle**: TX has `blocks.throttle()` for rate control. RX has no throttle — it reads from the HackRF at the hardware's natural rate.

### Relationship to `gps_packet_tx.py`

`gps_packet_tx.py` **inherits the identical packet format** from `pkt_simple_tx.py`:

- Same constants: `FS=2_000_000`, `SPS=20`, `RRC_ALPHA=0.35`, `RRC_NTAPS=11`, `SYNC_WORD=0xE38FC0FC`
- Same `crce16()` implementation
- Same `bpsk_modulate()` function (minor difference: TX returns `list[complex]`, GPS returns `np.ndarray`)
- Same `make_packet()` logic (preamble + sync + len + payload + CRC)

The key difference: `gps_packet_tx.py` transmits **binary PositionFrame packets** (38 bytes of structured GPS telemetry) instead of ASCII "HELLO WORLD". The receiver in `pkt_simple_rx.py` can decode both, but binary payloads require `--hex-output` for readability.

Additionally, `gps_packet_tx.py` uses a **burst-per-cycle** approach: for each GPS reading, it builds a 1-second burst (single packet with silence before/after), creates a throwaway GNU Radio flowgraph, transmits it, and tears down. This is fundamentally different from `pkt_simple_tx.py`'s continuous looping approach, but the on-air waveform is identical.

---

## 6. Resampling Rationale: `sps=20` vs `sps=4`

> **Note**: The task mentions `sps=20` vs `sps=4` for RRC filter taps between TX and RX. In the current codebase, **both TX and RX use `sps=20`**. The `sps=4` reference likely refers to an alternative or historical configuration, or to the `gr-satellites`-style BPSK chain.

### Why `sps=20`

Both files use `sps=20` at `FS=2 MHz`, yielding a symbol rate of 100 kbaud. This is chosen for:

1. **Filter quality**: At `sps=20`, the RRC filter has 20 samples per symbol period, giving smooth pulse shaping. The 220-tap filter spans 11 symbols, providing excellent stopband rejection.

2. **Phase resolution**: The RX tests all 20 decimation phases, giving timing resolution of `1/20 = 0.05` symbol periods (~500 ns at 100 kbaud). This is adequate for BPSK with moderate ISI.

3. **Computational overhead**: The RX processes at 2 Msps for filtering but then downsamples to 100 kHz for symbol-rate processing. The 20-phase search adds 20× the symbol-rate work, but this is still lightweight compared to the sample-rate convolution.

4. **HackRF compatibility**: 2 Msps is well-supported by the HackRF's USB interface. Lower rates (<1 Msps) can encounter issues with the HackRF's minimum sample rate, while higher rates (>10 Msps) risk USB buffer overflows.

### Hypothetical `sps=4` variant

If a design used `sps=4` at `FS=2 MHz`, the symbol rate would be 500 kbaud — 5× faster. This would mean:

- **TX**: The same RRC filter but with 4× fewer samples per symbol. The 220-tap filter would span `220/4 = 55` symbols — extreme overkill. You'd reduce to `ntaps=11` → 44 taps.
- **RX**: Only 4 decimation phases to test (4× faster brute-force), but timing resolution degrades to 0.25 symbol periods — marginal for BPSK with α=0.35.
- **Packet duration**: The "HELLO WORLD" packet (408 bits) would be ~0.82 ms vs ~4.1 ms — 5× shorter, reducing collision probability but requiring faster burst detection.

For a high-altitude balloon link, 100 kbaud with `sps=20` is a reasonable choice: it prioritizes link margin (through RRC filter quality and fine timing resolution) over raw throughput. The 100 kbaud rate supports ~8 kbyte/s of payload throughput, which is ample for GPS telemetry at 1 Hz update rate.

---

## Appendix: Complete Signal Processing Chain (RX)

```
Raw IQ samples (2 Msps, complex float32)
    │
    ▼
DC offset removal (subtract mean)
    │
    ▼
Coarse FO estimation (squared-signal FFT + band-edge FLL fallback)
    │
    ▼
Complex mix-down to baseband (exp(-j·2π·fo·t/fs))
    │
    ▼
RRC matched filter (220 taps, α=0.35, normalized to peak=1.0)
    │
    ▼
Per-phase downsampling: filt[p::20] for p in 0..19
    │
    ▼
┌─────────────────────────────────┐
│ For each of 20 phase streams:   │
│   1. Costas loop tracking       │
│   2. Sync-word correlation      │
│   3. Adaptive peak detection    │
│   4. Extract post-sync symbols  │
│   5. Brute-force decode:        │
│      - Try both polarities      │
│      - Try 8 bit shifts         │
│      - Parse length field       │
│      - Extract payload          │
│      - Validate CRC-16          │
└─────────────────────────────────┘
    │
    ▼
Candidate merging + deduplication
    │
    ▼
Sorted decoded payload list
```

---

*End of analysis.*
