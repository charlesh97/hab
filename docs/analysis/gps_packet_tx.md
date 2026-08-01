# GPS Packet Transmitter — Exhaustive Line-by-Line Analysis

> **File:** `payload/tx/gps_packet_tx.py` (237 lines)
> **Role:** Main TX loop for the HAB packet radio payload — reads GPS NMEA from a serial receiver, packs `PositionFrame` binary structures, BPSK-modulates them with RRC pulse shaping, and transmits via HackRF SDR at 915 MHz.
> **Target hardware:** Rock 2A (arm64, Armbian Debian 13, GNU Radio 3.10.12)
> **Baseline reference:** `rf/packet/src/pkt_simple_tx.py` (standalone BPSK test TX)

---

## 1. Shebang and Docstring (Lines 1–11)

```python
#!/usr/bin/env python3
```
**Line 1:** Standard hash-bang for direct execution (`./gps_packet_tx.py …`). Uses `env` to locate `python3` on the `PATH` rather than hardcoding `/usr/bin/python3`, which matters because the Rock 2A runs Python 3.12 from system packages, while a developer on macOS might use Python 3.14 from Homebrew.

```python
"""GPS Packet Transmitter — reads GPS NMEA, packs PositionFrames, transmits BPSK.

Uses the same GNU Radio BPSK chain as rf/packet/src/pkt_simple_tx.py:
  256b preamble + 32b sync 0xE38FC0FC + 16b len + payload + CRC-16/XMODEM.

Payload is a typed binary PositionFrame (38 bytes, type 0x01).
Transmits at 1 Hz burst rate with 50 ms inter-packet gap.

Requires: gnuradio, python3-numpy, hackrf, soapysdr-module-hackrf
"""
```
**Lines 2–11:** Module docstring. Five things established:

1. **Heritage:** The BPSK chain is the same as `pkt_simple_tx.py`. That file is a standalone test tool; this file adapts its waveform construction into a live GPS-fed loop.
2. **Framing format:** Preamble → sync → length → payload → CRC-16/XMODEM. Every packet on the air follows this envelope regardless of payload type.
3. **Payload type:** PositionFrame, 38 bytes, type tag `0x01`. The type byte enables multi-frame multiplexing (future frames: motion `0x02`, environment `0x03`, power `0x04`).
4. **Burst rate:** 1 Hz — one transmission per second. The `GAP_MS = 50` gives 50 ms of silence padding.
5. **Dependencies:** All Rock 2A system packages (`apt`). No pip-only packages.

---

## 2. Imports (Lines 13–31)

### 2.1 Future annotations (Line 13)
```python
from __future__ import annotations
```
Enables PEP 563 (deferred evaluation of annotations). This means all type hints in the file — `np.ndarray`, `list[int]`, `list[complex]` — are treated as strings and not evaluated at runtime. Two practical effects:

- **Forward references work** without quoting (e.g., `def build_burst(…) -> list[complex]` works even though `complex` is a builtin, but the pattern applies to user types).
- **Slight import-time speedup** because the interpreter doesn't construct type objects for annotations.

### 2.2 Standard library (Lines 15–19)
```python
import argparse
import struct
import sys
import time
from pathlib import Path
```
| Import | Why needed |
|---|---|
| `argparse` | CLI: `--freq`, `--vga`, `--amp`, `--serial`, `--device`, `--baud` |
| `struct` | Binary packing: big-endian `>H` for length and CRC fields in the packet envelope |
| `sys` | `sys.path.insert(0, …)` to add `../payload` to the module search path |
| `time` | `time.sleep(1.05)` — waits for burst transmission to complete each cycle |
| `pathlib.Path` | Resolves `__file__` to derive the payload root for `sys.path` manipulation |

### 2.3 GNU Radio and numpy (Lines 21–23)
```python
import numpy as np
from gnuradio import blocks, gr, soapy
from gnuradio.filter import firdes
```

| Import | Why needed |
|---|---|
| `numpy as np` | Array math: upsampling (`np.zeros`), BPSK mapping (`-2.0*arr + 1.0`), convolution, peak detection, `complex64` casting |
| `gnuradio.blocks` | `blocks.vector_source_c(burst, False)` — feeds pre-computed IQ samples into the flowgraph; `False` = don't repeat (single-shot burst) |
| `gnuradio.gr` | `gr.top_block()` — the flowgraph container; `gr.sizeof_gr_complex` — size in bytes of a complex sample (8 bytes: two `float32`s) |
| `gnuradio.soapy` | `soapy.sink(*sink_kwargs)` — the HackRF sink via SoapySDR abstraction layer |
| `gnuradio.filter.firdes` | `firdes.root_raised_cosine(…)` — designs RRC filter taps for pulse shaping |

### 2.4 Path manipulation and project imports (Lines 25–31)
```python
_HERE = Path(__file__).resolve().parent
```
**Line 26:** `Path(__file__).resolve()` gives the absolute path to `gps_packet_tx.py`. `.parent` strips the filename, yielding `…/payload/tx/`. Using `resolve()` is important because `__file__` can be a relative path depending on how the script is invoked, and `resolve()` normalizes it to an absolute path, also following symlinks.

```python
_PAYLOAD = _HERE.parent
```
**Line 27:** Goes up one level: `…/payload/`. This is the root of the payload Python package.

```python
sys.path.insert(0, str(_PAYLOAD))
```
**Line 28:** Inserts the payload root at the front of `sys.path` so that `from gps.nmea import …` and `from telemetry.packet_format import …` resolve correctly, regardless of the current working directory. Using `insert(0, …)` (front) rather than `append` means this directory takes priority over any identically-named packages elsewhere on `sys.path`.

```python
from gps.nmea import NMEAParser, parse_gga  # noqa: E402
from telemetry.packet_format import PositionFrame  # noqa: E402
```
**Lines 30–31:** Imports happen *after* the `sys.path` manipulation. The `# noqa: E402` suppresses flake8's "module level import not at top of file" warning, which is correct here because the import depends on the preceding `sys.path.insert`. Without that line, `from gps.nmea` would fail if the script is run from an arbitrary working directory.

The two imported symbols:

- **`NMEAParser`** (class): Wraps `serial.Serial`, opens the GPS at 9600-8N1, provides `read_sentence()` which blocks until it gets a checksum-valid NMEA sentence.
- **`parse_gga`** (function): Parses a `$GPGGA` sentence into a `dict` with keys `time`, `lat`, `lon`, `fix_quality`, `altitude`, `satellites`, `hdop`.
- **`PositionFrame`** (dataclass): Frozen dataclass with `pack()` method that serializes to 38-byte little-endian struct.

---

## 3. Constants (Lines 35–41)

```python
FS = 2_000_000          # sample rate
```

**`FS = 2_000_000` (2 MS/s):** The HackRF's DAC sample rate. Chosen because:
- HackRF supports sample rates from 2 MS/s to 20 MS/s.
- 2 MS/s is the *lowest* reliable rate — minimizes CPU load on the Rock 2A, reduces file/buffer sizes, and is still more than adequate for the ~100 ksym/s symbol rate (see `SPS` below).
- The matching receiver (`pkt_simple_rx.py`) uses the same rate for clock recovery.

```python
SPS = 20                # samples per symbol
```

**`SPS = 20` (samples per symbol):** Each BPSK symbol (one bit) is represented by 20 IQ samples. This gives:

$$R_{\text{sym}} = \frac{FS}{SPS} = \frac{2 \times 10^6}{20} = 100{,}000 \text{ symbols/second}$$

So the effective bitrate is 100 kbps (1 bit/symbol for BPSK).

Why 20? It's a tradeoff:
- Higher SPS = more oversampling = better pulse shaping, easier clock recovery at the receiver, but larger waveform buffers.
- Lower SPS = less oversampling = smaller buffers, but sharper transitions and harder clock recovery.
- 20 is a common value in GNU Radio BPSK examples and provides 20× oversampling, which is generous for RRC with α=0.35.

```python
RRC_ALPHA = 0.35
```

**`RRC_ALPHA = 0.35` (root raised cosine roll-off factor):**

The roll-off factor α (also called excess bandwidth) controls the tradeoff between spectral efficiency and inter-symbol interference (ISI) robustness.

- α = 0: ideal sinc pulse, zero excess bandwidth, perfect spectral efficiency but infinite-length impulse response — unrealizable.
- α = 0.35: 35% excess bandwidth. The occupied bandwidth is:

$$BW = (1 + \alpha) \times R_{\text{sym}} = 1.35 \times 100{,}000 = 135{,}000 \text{ Hz}$$

This fits comfortably within the HackRF's minimum 1.75 MHz analog bandwidth. The moderate roll-off gives good ISI rejection while keeping the spectrum reasonably compact.

This value comes directly from `pkt_simple_tx.py` and is a standard choice in GNU Radio BPSK examples.

```python
RRC_NTAPS = 11          # in units of SPS → 220 taps
```

**`RRC_NTAPS = 11` (filter length in symbol periods):**

The RRC filter spans 11 symbol periods. With `SPS=20`, the total number of taps is:

$$N_{\text{taps}} = 11 \times 20 = 220$$

This is the value passed to `firdes.root_raised_cosine(…, RRC_NTAPS * SPS)`.

- 11 symbol periods means the filter's impulse response extends ±5.5 symbols from center.
- 220 taps is a reasonable filter length: long enough to approximate the RRC shape well, short enough that convolution is fast.
- The convolution in `bpsk_modulate()` uses `mode='same'`, so the output length equals the input length (the filter delay is absorbed, not prepended).

```python
SYNC_WORD = 0xE38FC0FC  # 32-bit
```

**`SYNC_WORD = 0xE38FC0FC` (32-bit frame synchronization word):**

This is a fixed bit pattern that marks the boundary between the preamble and the data portion of the packet. It is the *same* sync word used by GNU Radio's default correlation-based packet framing (`gr::digital::correlate_access_code_bb`).

Properties of `0xE38FC0FC`:
- 32 bits long — long enough that false positives from random data are astronomically unlikely (probability ≈ 2⁻³² ≈ 2.3×10⁻¹⁰ per 32-bit window).
- Good autocorrelation properties: minimal sidelobes so the correlator produces a sharp peak.
- Standard in GNU Radio examples — the receiver (`pkt_simple_rx.py`) uses the same sync word in its `correlate_access_code_bb` block.

Bit decomposition (MSB first):
```
0xE38FC0FC = 1110 0011 1000 1111 1100 0000 1111 1100
```

```python
PREAMBLE_BITS = 256
```

**`PREAMBLE_BITS = 256` (preamble length in bits):**

A 256-bit alternating `101010…` pattern precedes the sync word. Two purposes:

1. **Clock/carrier recovery:** The alternating pattern produces a strong spectral line at half the symbol rate (50 kHz with SPS=20), which clock-recovery loops (e.g., Mueller & Müller, Costas loop) can lock onto.
2. **AGC settling:** At the receiver, the automatic gain control needs time to adjust to the incoming signal level before the actual data starts.

256 bits at 100 ksym/s = 2.56 ms of preamble — a reasonable duration. Longer preambles improve lock reliability at the cost of throughput.

```python
GAP_MS = 50             # inter-packet silence
```

**`GAP_MS = 50` (inter-packet silence gap in milliseconds):**

50 ms of zero (carrier-off) samples before and after the packet within the 1-second burst cycle. The purpose:

- Gives the receiver clear "no signal" periods to reset its AGC and symbol timing recovery between packets.
- Prevents the receiver from seeing back-to-back packets as one continuous stream.
- At 2 MS/s, 50 ms = 100,000 samples of silence on each side.

The actual total silence is *up to* 2 × 50 ms = 100 ms; see `build_burst()` for the padding logic.

---

## 4. `crc16(data: bytes) -> int` (Lines 44–52)

```python
def crc16(data: bytes) -> int:
    """CRC-16/XMODEM (0x1021).  Returns 16-bit unsigned int."""
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc
```

### Algorithm

This is a bitwise, table-free implementation of CRC-16/XMODEM (also known as CRC-16-CCITT with polynomial `0x1021`).

**Poly representation:** The hexadecimal polynomial `0x1021` corresponds to $x^{16} + x^{12} + x^5 + 1$ in normal form. This is the CRC-CCITT polynomial used in XMODEM, HDLC, and many embedded protocols.

### Line-by-line

**Line 46:** `crc = 0` — Initial CRC register value is zero (not `0xFFFF`). This is the XMODEM variant; some CRC-16 variants initialize to `0xFFFF`.

**Line 47:** `for b in data:` — Process each byte of the payload.

**Line 48:** `crc ^= b << 8` — XOR the byte into the *upper* byte of the 16-bit CRC register. This shifts the byte up to bits 15–8 before XORing, which is equivalent to processing the byte's MSB first. In a typical CRC-16, the byte would be XORed into the *lower* byte, but this implementation effectively processes bytes big-endian style — the MSB of the first data byte is the first bit fed into the shift register.

**Line 49:** `for _ in range(8):` — Process all 8 bits of the byte.

**Line 50:** `crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)` — The core LFSR step:
- `crc << 1`: Shift the register left by one bit.
- `crc & 0x8000`: Check if the bit about to be shifted out (the MSB, bit 15) is 1.
- If it is, XOR with the polynomial `0x1021` (the feedback taps). If not, just the shift.
- This is a standard bitwise CRC — the polynomial is applied whenever the shifted-out bit is 1.

**Line 51:** `crc &= 0xFFFF` — Mask to 16 bits (defensive; after XOR with `0x1021` the value stays within 16 bits, but masking is cheap insurance).

**Line 52:** `return crc` — Returns the final 16-bit unsigned CRC value.

### Usage context

The CRC is computed over the *payload bytes only* — not over the length field or any framing. This is stated in `make_packet_waveform()` where `crc = crc16(payload)` is called before packing. The receiver computes the CRC over the extracted payload and compares it to the received CRC bytes to detect bit errors.

The same CRC function appears identically in `pkt_simple_tx.py` (lines 30–38) and is assumed to appear in the receiver as well.

### Edge cases / assumptions

- **Empty payload:** `crc16(b"")` returns `0`. The CRC of an empty payload is zero, which is correct — no data, no shift.
- **No final XOR:** Unlike CRC-16-CCITT/ARC which finalizes with XOR `0x0000`, this implementation returns the raw register value.
- **Byte ordering in on-air format:** The CRC is transmitted as big-endian 16-bit (`struct.pack(">H", crc)`), consistent with the length field.

---

## 5. `bpsk_modulate(bits, sps) -> np.ndarray` (Lines 55–66)

```python
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
```

### Line 57 — BPSK mapping `0 → +1, 1 → −1`

```python
mapped = np.array(bits, dtype=np.float64) * -2.0 + 1.0
```

**Math:**
| Input bit | `bit * -2.0` | `+ 1.0` | Result |
|---|---|---|---|
| 0 | 0.0 | 1.0 | **+1.0** |
| 1 | −2.0 | −1.0 | **−1.0** |

This is the standard BPSK constellation: two antipodal points on the real axis. The mapping is `0 → +1` (0° phase) and `1 → −1` (180° phase).

**`dtype=np.float64`:** Double precision is used for the modulation chain because `firdes.root_raised_cosine()` returns double-precision taps and convolution in double precision avoids cumulative quantization error. The final cast to `np.complex64` (line 66) happens only after all scaling.

**Why the real axis only?** BPSK uses only the in-phase (I) component. The quadrature (Q) component is always zero. The waveform is a `complex64` array where every value is `(real_value + 0j)`. GNU Radio expects complex samples for the SoapySDR sink. A purely-real HackRF transmission would be possible, but the complex API is the standard GNU Radio convention.

### Line 58–59 — Upsampling (zero-stuffing)

```python
up = np.zeros(len(mapped) * sps, dtype=np.float64)
up[::sps] = mapped
```

**`len(mapped) * sps`:** If there are N bits, the upsampled array has N × SPS = N × 20 samples. For a 38-byte PositionFrame packet, the total bit count is:
- Preamble: 256 bits
- Sync: 32 bits
- Length: 16 bits
- Payload: 38 × 8 = 304 bits
- CRC: 16 bits
- **Total: 624 bits**
- **Upsampled samples:** 624 × 20 = 12,480 samples

**`up[::sps] = mapped`:** Places each symbol at every 20th position, leaving zeros in between. This is "zero-stuffing" upsampling — also called "zero-order hold followed by a low-pass filter." The RRC filter (which is a low-pass / pulse-shaping filter) will interpolate the zeros.

**NumPy slicing:** `up[::sps]` is a strided view; `up[0]`, `up[20]`, `up[40]`, … receive the mapped symbol values. The assignment operates in-place on the slice.

### Line 60 — RRC filter design

```python
taps = firdes.root_raised_cosine(sps, sps, 1.0, RRC_ALPHA, RRC_NTAPS * sps)
```

**`firdes.root_raised_cosine(gain, sampling_freq, symbol_rate, alpha, ntaps)`** signature:

| Parameter | Value | Meaning |
|---|---|---|
| `gain` | `sps` (= 20) | Overall filter gain. Using `sps` as the gain compensates for the energy loss from upsampling — since only 1 in 20 samples is non-zero, the convolution output would otherwise be attenuated by a factor of ≈20. Multiplying the taps by `sps` restores unity gain for the symbol values. |
| `sampling_freq` | `sps` (= 20) | The sampling frequency *relative to the symbol rate*. Since we're designing in the discrete-time domain, this is `sps`. |
| `symbol_rate` | `1.0` | Symbol rate normalized to 1.0. Together with `sampling_freq=sps`, this means the Nyquist frequency is normalized to `sps/2`. |
| `alpha` | `RRC_ALPHA` (0.35) | Roll-off factor (excess bandwidth). |
| `ntaps` | `RRC_NTAPS * sps` (220) | Number of filter taps. 11 symbol periods × 20 samples/symbol = 220 taps. Must be odd to give a symmetric impulse response with a well-defined center tap. 220 is even? Let's check: 11 × 20 = 220. GNU Radio's `firdes` typically adds 1 if ntaps is even, to ensure odd-length symmetry. |

**Why `gain=sps`?** When you zero-stuff and then filter, the average power of the upsampled signal is 1/SPS of the original. The RRC filter with unity gain would preserve that attenuated level. Setting `gain=sps` scales the taps so that the filtered output has the same amplitude as the original symbols.

### Lines 61–62 — Convolution

```python
taps_np = np.array(taps)
waveform = np.convolve(up, taps_np, "same")
```

**`np.array(taps)`:** `firdes.root_raised_cosine()` returns a Python list of `float`. Converting to a numpy array enables the fast NumPy convolution.

**`np.convolve(up, taps_np, "same")`:** Convolves the upsampled symbol stream with the RRC filter taps. Mode `"same"` returns an output the same length as `up` — the filter's transient (leading/trailing tails) is absorbed. This means:
- The first ≈110 samples are the filter's rising transient (partial convolution).
- The middle samples are full, valid filtered symbols.
- The last ≈110 samples are the filter's falling transient.

This is appropriate because the preamble (256 bits) provides plenty of transient samples for the filter to settle before the sync word and data.

**Computational cost:** Convolution of a 12,480-sample signal with 220 taps ≈ 2.7 million multiply-adds — negligible on any modern CPU, even the Rock 2A's RK3528.

### Lines 63–65 — Peak scaling (clipping prevention)

```python
peak = float(np.max(np.abs(waveform)))
if peak > 0.7:
    waveform *= 0.7 / peak
```

**`np.max(np.abs(waveform))`:** Finds the maximum absolute amplitude in the waveform. Since BPSK is real-valued (Q=0), this is effectively the maximum absolute real value.

**Why 0.7?** The DAC in the HackRF expects floating-point samples in the range [-1.0, +1.0]. Values outside this range clip. However, the RRC filter's peak-to-average power ratio (PAPR) and the filter's impulse response can produce peaks above 1.0, especially with the `gain=sps` setting. The threshold 0.7 provides headroom to prevent clipping:

- 0.7 amplitude = 0.49 power = −3 dB below full scale.
- This leaves 3 dB of headroom for any residual peaks.
- The value 0.7 is also used identically in `pkt_simple_tx.py` (line 26).

**Backoff math:** If `peak = 1.2`, the waveform is scaled by `0.7/1.2 ≈ 0.583`, bringing the new peak to exactly 0.7. If `peak ≤ 0.7`, no scaling is applied.

### Line 66 — Final cast to complex64

```python
return waveform.astype(np.complex64)
```

Casts from `float64` to `complex64` (two 32-bit floats: real + imaginary). The imaginary part is implicitly zero for all samples. GNU Radio's `gr.sizeof_gr_complex` is 8 bytes, matching `complex64`.

**Why not `complex64` throughout?** The RRC filter design and convolution operate in `float64` to avoid quantization artifacts. Only the final waveform is downcast, once all processing is done. The quantization error from `float64 → float32` is below −140 dB relative to full scale — well below the HackRF's ~40 dB SNR.

### Comparison to `pkt_simple_tx.py`

The original in `pkt_simple_tx.py` (lines 13–28) is functionally identical but:
- Returns `.tolist()` (Python list) instead of `np.ndarray` — `gps_packet_tx.py` returns an ndarray for direct use with `build_burst()`.
- Takes `sps` and `rrc_alpha` as parameters rather than module constants — `gps_packet_tx.py` uses module-level `SPS` and `RRC_ALPHA`.
- The convolution and peak-scaling logic is the same.

---

## 6. `_bytes_to_bits(data) -> list[int]` (Lines 69–74)

```python
def _bytes_to_bits(data: bytes) -> list[int]:
    bits: list[int] = []
    for b in data:
        for i in range(8):
            bits.append((b >> (7 - i)) & 1)
    return bits
```

### Purpose

Converts a `bytes` object into a flat list of integer `0`/`1` bits, MSB first (big-endian bit ordering within each byte).

### Line-by-line

**Line 70:** `bits: list[int] = []` — Empty accumulator list. Type hint clarifies it's a list of ints.

**Line 71:** `for b in data:` — Iterate over each byte. `b` is an `int` in Python 3 (0–255).

**Line 72:** `for i in range(8):` — Iterate over bit positions 0–7.

**Line 73:** `(b >> (7 - i)) & 1` — Extract bit at position `7-i` (MSB first):
- `i=0`: `b >> 7` — extracts bit 7 (MSB).
- `i=1`: `b >> 6` — extracts bit 6.
- …
- `i=7`: `b >> 0` — extracts bit 0 (LSB).

### Usage

Called three times in `make_packet_waveform()`:
- `_bytes_to_bits(len_bytes)` — 16 bits (big-endian uint16 length)
- `_bytes_to_bits(payload)` — 304 bits (38-byte PositionFrame)
- `_bytes_to_bits(crc_bytes)` — 16 bits (big-endian uint16 CRC)

### Why a separate function?

In `pkt_simple_tx.py`, `_bytes_to_bits` is nested inside `make_packet()` as a local closure. In `gps_packet_tx.py`, it's promoted to a module-level function — cleaner and testable in isolation.

### Edge case: empty bytes

`_bytes_to_bits(b"")` returns `[]` — an empty bit list. This is safe because the CRC and length fields are always non-empty (2 bytes each).

---

## 7. `make_packet_waveform(payload) -> np.ndarray` (Lines 77–97)

```python
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
```

This function constructs the complete on-air packet: framing envelope + payload + error detection, then BPSK-modulates the whole thing into IQ samples.

### Line 80 — Preamble construction

```python
preamble = [1, 0] * (PREAMBLE_BITS // 2)
```

`[1, 0]` is a 2-element list. Multiplying by `PREAMBLE_BITS // 2 = 128` repeats it 128 times → `[1, 0, 1, 0, …, 1, 0]` = 256 bits.

**Why `PREAMBLE_BITS // 2` rather than `PREAMBLE_BITS`?** Because each repetition produces *two* bits. The list multiplication works on elements, not bits. `[1, 0] * N` produces `2N` elements.

**Bit-to-symbol mapping:** Bit `1` maps to `−1` and bit `0` maps to `+1` in `bpsk_modulate()` (line 57: `bit * -2.0 + 1.0`). So the preamble produces alternating `+1, −1, +1, −1, …` — a square wave at half the symbol rate. This is ideal for clock recovery because it has a strong spectral line.

### Lines 81–82 — Sync word decomposition

```python
sync = [(SYNC_WORD >> (31 - i)) & 1 for i in range(32)]
```

List comprehension that extracts each bit of the 32-bit sync word, MSB first:

| i | Expression | Bit position |
|---|---|---|
| 0 | `(SYNC_WORD >> 31) & 1` | Bit 31 (MSB) |
| 1 | `(SYNC_WORD >> 30) & 1` | Bit 30 |
| … | … | … |
| 31 | `(SYNC_WORD >> 0) & 1` | Bit 0 (LSB) |

So for `SYNC_WORD = 0xE38FC0FC`:
```
0xE38FC0FC → binary: 1110 0011 1000 1111 1100 0000 1111 1100
sync = [1, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1,
        1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0]
```

The receiver's `correlate_access_code_bb` block slides this exact 32-bit pattern across the incoming bit stream. When it finds a match (correlation peak), it declares frame sync and the following bits are interpreted as the length field, then payload, then CRC.

### Lines 84–85 — Length field encoding

```python
length = len(payload)
len_bytes = struct.pack(">H", length)
```

**`len(payload)`:** Byte length of the payload. For a PositionFrame, this is always 38.

**`struct.pack(">H", length)`:** Packs as big-endian unsigned 16-bit integer:
- `>` = big-endian byte order
- `H` = unsigned short (2 bytes)

For length=38: `struct.pack(">H", 38)` → `b'\x00\x26'`.

The length field tells the receiver how many bytes to read after the sync word. Without it, the receiver wouldn't know where the payload ends and the CRC begins. The maximum payload size is 65535 bytes (16-bit length field), though in practice it's 38 bytes.

### Lines 87–88 — CRC computation

```python
crc = crc16(payload)
crc_bytes = struct.pack(">H", crc)
```

**`crc16(payload)`:** Computes the 16-bit CRC over the payload bytes (see §4).

**`struct.pack(">H", crc)`:** Packs as big-endian 16-bit, matching the length field's byte order.

The CRC is appended to the payload in the bit stream but transmitted *after* the payload. This is standard framing: the receiver reads `length` bytes, then reads the 2-byte CRC, computes its own CRC over the received payload, and compares. A mismatch indicates bit errors.

### Lines 90–96 — Bit assembly and modulation

```python
all_bits = (
    preamble
    + sync
    + _bytes_to_bits(len_bytes)
    + _bytes_to_bits(payload)
    + _bytes_to_bits(crc_bytes)
)
return bpsk_modulate(all_bits)
```

The five segments are concatenated into a single flat bit list:

| Segment | Bits | Source |
|---|---|---|
| Preamble | 256 | `[1, 0] * 128` |
| Sync word | 32 | `SYNC_WORD` bit decomposition |
| Length | 16 | `struct.pack(">H", len(payload))` |
| Payload | len(payload)×8 | Raw payload bytes |
| CRC-16 | 16 | `struct.pack(">H", crc16(payload))` |
| **Total** | **320 + 8×len(payload)** | For 38B payload: **624 bits** |

The assembled bit list is passed to `bpsk_modulate()`, which maps each bit to a BPSK symbol, upsamples by SPS=20, applies RRC pulse shaping, and returns a `complex64` numpy array.

**Total waveform length:** 624 bits × 20 samples/bit = **12,480 samples**.

**On-air duration:** 12,480 / 2,000,000 = **6.24 ms**.

### Implicit assumptions

1. **Payload length fits in 16 bits:** A PositionFrame is 38 bytes — well within the 65535-byte limit. Future frame types up to 65535 bytes work without code changes.
2. **No scrambling:** The raw bits are transmitted without whitening/scrambling. The alternating preamble provides some spectral whitening, but long runs of zeros or ones in the payload could produce DC bias. A 38-byte structured binary payload is unlikely to have pathological runs, but it's an implicit assumption.
3. **No forward error correction (FEC):** Only CRC-16 error *detection* is used. No FEC (convolutional, Reed-Solomon, LDPC) is applied. The CRC tells the receiver "this packet has errors," but cannot correct them. This is acceptable for the anticipated link budget at balloon distances (<100 km line-of-sight).

---

## 8. `build_burst(payload, sample_rate) -> list[complex]` (Lines 100–114)

```python
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
```

### Purpose

`make_packet_waveform()` produces a standalone packet waveform (~6.24 ms = 12,480 samples). `build_burst()` embeds that packet into exactly 1 second of samples (2,000,000 samples at FS=2 MS/s) with silence padding. This is necessary because the GNU Radio flowgraph is torn down and rebuilt on every cycle — the vector source must contain exactly the samples to be transmitted in that cycle.

### Line 102 — Packet waveform

```python
pkt = make_packet_waveform(payload)
```

Calls `make_packet_waveform()` to get the BPSK-modulated packet as a `complex64` numpy array. For a 38-byte PositionFrame payload: 12,480 samples.

### Line 103 — Gap sample count

```python
gap_samples = int(round(GAP_MS * sample_rate / 1000.0))
```

**Math:**
$$\text{gap\_samples} = \left\lfloor \frac{50 \text{ ms} \times 2{,}000{,}000 \text{ S/s}}{1000 \text{ ms/s}} + 0.5 \right\rfloor = 100{,}000 \text{ samples}$$

`round()` is used because `50 × 2000000 / 1000 = 100000.0` exactly, but for non-integer `GAP_MS` values (e.g., 47.3 ms) the rounding ensures an integer sample count.

Each gap sample is `0j` — complex zero, meaning no RF carrier. The HackRF DAC outputs 0V during these samples (DC offset aside), effectively keying the carrier off.

### Lines 105–112 — Padding logic

```python
total_wanted = sample_rate  # 1 second worth of samples
available = len(pkt) + 2 * gap_samples
if available < total_wanted:
    pad_before = gap_samples
    pad_after = total_wanted - len(pkt) - pad_before
else:
    pad_before = gap_samples
    pad_after = gap_samples
```

**`total_wanted = sample_rate`:** Always 2,000,000 samples = 1 second. This is the hard requirement — the `vector_source_c` with `repeat=False` sends exactly this many samples, and the `throttle` block paces them at 2 MS/s. At exactly 2,000,000 samples, the flowgraph runs for exactly 1 second.

**`available = len(pkt) + 2 * gap_samples`:** The "natural" length with symmetric leading and trailing gaps. For a 38-byte payload: `12,480 + 2 * 100,000 = 212,480` samples.

**The `if` branch (normal case):** `212,480 < 2,000,000` → True. Then:
- `pad_before = 100,000` (the standard gap)
- `pad_after = 2,000,000 - 12,480 - 100,000 = 1,887,520` samples

So the packet is transmitted near the *beginning* of the 1-second cycle, with 100k samples of silence before it and a much longer silence tail after it. This maximizes time for the receiver to process the packet before the next one arrives.

**The `else` branch (pathological):** If the packet + 2×gap were already ≥ 1 second (impossible with a 38-byte payload — that would require ~1.8M samples just for the packet), the function falls back to symmetric gaps.

**Implicit assumption:** The 1-second cycle is synchronous — each burst takes exactly 1 second of wall-clock time. The `time.sleep(1.05)` in `main()` provides a small overrun buffer.

### Line 113 — Burst assembly

```python
burst = [0j] * pad_before + pkt.tolist() + [0j] * pad_after
```

**`[0j] * pad_before`:** Creates a Python list of `pad_before` complex zeros (leading silence).

**`pkt.tolist()`:** Converts the numpy array to a Python list. The `vector_source_c` block accepts Python lists of complex numbers.

**`[0j] * pad_after`:** Trailing silence.

**Total:** `pad_before + len(pkt) + pad_after = 2,000,000` samples = 1 second.

**Why `list[complex]` and not `np.ndarray`?** The `vector_source_c` block expects an iterable. While it might accept a numpy array, the `.tolist()` conversion is explicit and safe. The overhead of converting 2,000,000 complex values from numpy to list is noticeable but acceptable for a 1 Hz cycle.

**Return type annotation `-> list[complex]`:** The Python `complex` type maps to the GNU Radio `gr_complex` type (two `float32`s). GNU Radio's Python bindings handle the conversion.

---

## 9. `print_status(pkt_len, lat, lon, alt, sats)` (Lines 117–124)

```python
def print_status(pkt_len: int, lat: float, lon: float, alt: float, sats: int) -> None:
    print(
        f"[GPSTx] pkt={pkt_len}B  "
        f"pos={lat:.5f},{lon:.5f}  "
        f"alt={alt:.1f}m  "
        f"sats={sats}",
        flush=True,
    )
```

### Purpose

Single-line status output per transmission cycle. Provides telemetry feedback to the operator.

### Line-by-line

**`pkt={pkt_len}B`:** Packet payload size in bytes. Always 38 for PositionFrame, but future frame types may differ.

**`pos={lat:.5f},{lon:.5f}`:** Latitude and longitude to 5 decimal places (~1.1 m precision at the equator). This is appropriate for balloon tracking — GPS precision is typically 3–5 meters horizontal.

**`alt={alt:.1f}m`:** Altitude in meters with one decimal place (10 cm resolution). GPS altitude is inherently less accurate than horizontal position, but the tenth-meter display is still useful for observing trends during ascent.

**`sats={sats}`:** Number of satellites used in the fix. Useful for diagnosing GPS antenna placement and sky visibility.

**`flush=True`:** Forces the output buffer to flush immediately. Without this, when stdout is piped (e.g., `python3 gps_packet_tx.py | tee tx.log`), the output might be line-buffered or fully buffered, delaying visibility. `flush=True` ensures each status line appears immediately — critical when the operator is watching the TX start up or diagnosing issues.

### Missing fields

The status line deliberately omits:
- Sequence number (`seq`): Not critical for human monitoring; the receiver's dashboard tracks this.
- Fix type / fix quality: Operator can infer from `sats=0` or position `0.00000,0.00000` that there's no fix.
- HDOP: Useful but verbose for a one-line status.
- Burst timing / RSSI: TX-side; not available in this loop.

---

## 10. `main() -> None` (Lines 127–237)

This is the main entry point — the infinite transmission loop. Every line matters.

### 10.1 Argument parsing (Lines 128–136)

```python
parser = argparse.ArgumentParser(description="GPS Packet TX via HackRF")
parser.add_argument("--freq", type=float, default=915e6)
parser.add_argument("--vga", type=float, default=47)
parser.add_argument("--amp", action="store_true", default=True)
parser.add_argument("--serial", type=str, default=None)
parser.add_argument("--device", type=str, default="/dev/ttyS0",
                    help="GPS serial device")
parser.add_argument("--baud", type=int, default=9600)
args = parser.parse_args()
```

| Argument | Type | Default | Meaning |
|---|---|---|---|
| `--freq` | float | `915_000_000.0` | Center frequency in Hz. 915 MHz is in the ISM band (902–928 MHz in ITU Region 2). |
| `--vga` | float | `47.0` | HackRF VGA (variable gain amplifier) gain in dB. Range: 0–47 dB. 47 = maximum TX power. |
| `--amp` | bool | `True` | HackRF TX amplifier enable. When True, adds ~14 dB gain after the VGA. |
| `--serial` | str | `None` | HackRF serial number for disambiguation when multiple HackRFs are connected. |
| `--device` | str | `/dev/ttyS0` | GPS serial device path. `/dev/ttyS0` is UART0 on the Rock 2A (pins 8/10), connected to the L76K GPS module. |
| `--baud` | int | `9600` | GPS serial baud rate. 9600 is the default for most GPS receivers (NMEA 0183 standard). |

**Interesting: `--amp` defaults to `True`.** In `pkt_simple_tx.py`, `--amp` defaults to `False`. This difference reflects real-world usage: the operational TX always runs with the amplifier on for maximum range. The test tool defaults off for bench testing at close range without overloading the receiver.

### 10.2 GPS initialization (Lines 138–143)

```python
freq = float(args.freq)
fs = FS

print(f"[GPSTx] Opening GPS on {args.device} @ {args.baud}")
gps = NMEAParser(args.device)
gps.serial.baudrate = args.baud
```

**Line 138:** `freq = float(args.freq)` — Redundant cast (argparse already produces float), but safe. The explicit cast clarifies intent: frequency is a float.

**Line 139:** `fs = FS` — Local alias. `FS` is `2_000_000` (module constant). This copy is never modified, so it's effectively a constant. Could have been `FS` directly throughout, but the local copy makes it clear this value could vary in a future multi-sample-rate implementation.

**Line 142:** `gps = NMEAParser(args.device)` — Constructs the NMEA parser, which internally opens `serial.Serial(port=device, baudrate=9600, …)`. See `nmea.py` §137 for the constructor details.

**Line 143:** `gps.serial.baudrate = args.baud` — Overrides the baud rate. The `NMEAParser` constructor hardcodes `GPS_BAUD = 9600` (line 8 of `nmea.py`), so this line only matters if the user passes `--baud` something other than 9600, or if the constructor default changes independently. It's defensive — ensures the actual serial port matches the CLI argument.

### 10.3 State variables (Lines 145–152)

```python
seq = 0
last_lat = 0.0
last_lon = 0.0
last_alt = 0.0
last_fix = False
last_fix_type = "none"
last_sats = 0
last_hdop = 0.0
```

These variables hold the *latest known* GPS state. They persist across loop iterations so that if a particular cycle fails to get a valid fix (e.g., `read_sentence()` times out, or the sentence fails checksum), the transmitter still sends the *last known good* position.

| Variable | Type | Initial | Updated by `parse_gga()` field |
|---|---|---|---|
| `seq` | int | 0 | Incremented per packet (not from GPS) |
| `last_lat` | float | 0.0 | `fix["lat"]` (decimal degrees, ±90°) |
| `last_lon` | float | 0.0 | `fix["lon"]` (decimal degrees, ±180°) |
| `last_alt` | float | 0.0 | `fix["altitude"]` (meters above MSL) |
| `last_fix` | bool | False | `fix["fix_quality"] > 0` |
| `last_fix_type` | str | `"none"` | Derived from `fix_quality`: 0→none, 1→2d, ≥2→3d |
| `last_sats` | int | 0 | `fix["satellites"]` |
| `last_hdop` | float | 0.0 | `fix["hdop"]` (horizontal dilution of precision) |

**Initial values:** Position `(0.0, 0.0)` off the coast of Africa (Null Island). Altitude 0.0 m. No fix. These are obviously invalid — the receiver should reject these until a real fix arrives. The dashboard can detect this from `fix=False` and `fix_type="none"`.

### 10.4 Startup messages (Lines 154–156)

```python
print(f"[GPSTx] Freq={freq/1e6:.3f} MHz  VGA={args.vga}  amp={args.amp}")
if args.serial:
    print(f"[GPSTx] HackRF serial: {args.serial}")
```

Operator feedback showing the TX configuration at startup. Frequency displayed in MHz (e.g., `915.000 MHz`). The serial number line only prints if a serial filter is active.

### 10.5 The main loop (Lines 158–227)

```python
try:
    while True:
```

**`try:`** wraps the entire infinite loop. The only expected exit is `KeyboardInterrupt` (Ctrl+C). An unhandled exception (e.g., GPS serial port disconnection, SoapySDR driver failure) would crash the script, which is acceptable — the operator is expected to be present during flight and can restart.

**`while True:`** — Infinite loop, one iteration per second. There is no graceful shutdown mechanism beyond the keyboard interrupt. The loop cannot be exited by a timer or sentinel value.

#### 10.5.1 GPS sentence collection (Lines 161–183)

```python
sentence = gps.read_sentence()
```

**`gps.read_sentence()`** (from `nmea.py` lines 150–159):
- Calls `self.serial.readline()` with a 1-second timeout.
- If `readline()` returns nothing (timeout), returns `None`.
- If a line is received, strips, decodes from ASCII, and validates the NMEA checksum via `nmea_checksum_ok()`.
- If checksum valid: returns the sentence string.
- If checksum invalid: loops back and tries again (blocking until a valid sentence or timeout).

**Important timing implication:** If the GPS is outputting sentences at 1 Hz and the TX loop runs at 1 Hz, there's a race condition: `read_sentence()` might need up to 1 second to get the next sentence. The total loop iteration (including TX) takes ~1.05 seconds. This means the TX loop and GPS output can drift relative to each other, and occasionally a cycle will get `sentence = None` because the GPS's 1-second timer hasn't fired yet.

```python
if sentence:
    fix = parse_gga(sentence)
```

**Guard:** Only attempt to parse if we got a sentence. If `sentence is None` (GPS timeout), skip parsing and use the `last_*` values from the previous cycle.

**`parse_gga(sentence)`** (from `nmea.py` lines 71–102):
- Strips and validates checksum again (belt-and-suspenders).
- Splits on commas.
- Verifies the sentence type ends with "GGA".
- Extracts: UTC time, latitude raw, N/S, longitude raw, E/W, fix quality, satellites, HDOP, altitude.
- Converts lat/lon from NMEA degrees-minutes to decimal degrees.
- Returns a dict with keys: `time`, `lat`, `lon`, `fix_quality`, `altitude`, `satellites`, `hdop`.
- Returns `None` if the sentence is not a valid GGA or if critical fields are missing.

```python
if fix is not None:
    if fix.get("lat") is not None:
        last_lat = float(fix["lat"])
    if fix.get("lon") is not None:
        last_lon = float(fix["lon"])
    if fix.get("altitude") is not None:
        last_alt = float(fix["altitude"])
```

**Conditional updates:** Each field is updated independently — if `lat` is valid but `altitude` is not, only `last_lat` changes. This is defensive: a partial GGA sentence (possible with a marginal GPS signal) won't corrupt all fields.

**`fix.get("lat")` vs `fix["lat"]`:** Using `.get()` with default `None` prevents `KeyError` if `parse_gga()` returns a dict without a field (e.g., a future parser change). The current `parse_gga()` always includes all keys or returns `None`, but `.get()` is future-proof.

```python
fq = fix.get("fix_quality")
fq_int = int(fq) if fq is not None else 0
last_fix = fq_int > 0
```

**Fix quality mapping:**
- `fq_int = 0`: No fix (or missing field)
- `fq_int = 1`: GPS fix (SPS)
- `fq_int = 2`: Differential GPS fix
- `fq_int ≥ 3`: PPS fix (rare in consumer GPS)

`last_fix = fq_int > 0` is `True` for any fix (GPS, DGPS, PPS).

```python
if fq_int >= 2:
    last_fix_type = "3d"
elif fq_int == 1:
    last_fix_type = "2d"
else:
    last_fix_type = "none"
```

**fix_type mapping (string values for dashboard):**
| `fq_int` | `fix_type` | Meaning |
|---|---|---|
| 0 | `"none"` | No fix |
| 1 | `"2d"` | Standard GPS fix (3D position but marked "2d" for compatibility) |
| ≥2 | `"3d"` | Differential or augmented fix — assumed 3D |

**Note on nomenclature:** In NMEA, `fix_quality=1` means "GPS fix (SPS)" which actually *is* a 3D fix — GPS inherently provides 3D position. The mapping `1 → "2d"` is a simplification. The dashboard uses `fix_type` as a display string, not a literal dimensionality claim. The intent is: `0 = no fix`, `1 = basic fix`, `2+ = high quality fix`. The exact values match the dashboard's TypeScript `fix_type` enum.

```python
if fix.get("satellites") is not None:
    last_sats = int(fix["satellites"])
if fix.get("hdop") is not None:
    last_hdop = float(fix["hdop"])
```

Update satellite count and HDOP. HDOP is horizontal dilution of precision — lower is better. Values < 1.0 are excellent, 1–2 is good, 2–5 is acceptable, > 10 is poor.

#### 10.5.2 PositionFrame construction (Lines 185–200)

```python
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
```

**`PositionFrame`** is a frozen dataclass from `telemetry.packet_format.py` (line 38). Each field:

| Field | Value | Source |
|---|---|---|
| `type` | `0x01` | Hardcoded — this is always a position frame |
| `seq` | `seq` | Rolling 16-bit counter (see below) |
| `lat` | `last_lat` | Latest GPS latitude (decimal degrees) |
| `lon` | `last_lon` | Latest GPS longitude (decimal degrees) |
| `alt_m` | `last_alt` | Latest GPS altitude MSL (meters) |
| `agl_m` | `max(0.0, last_alt - 10.0)` | **Estimated AGL** — see below |
| `fix` | `last_fix` | Boolean: has fix? |
| `fix_type` | `last_fix_type` | String: "none", "2d", "3d" |
| `sats` | `last_sats` | Number of satellites |
| `hdop` | `last_hdop` | Horizontal DOP |
| `vdop` | `0.0` | **Hardcoded zero** — see below |

**`agl_m = max(0.0, last_alt - 10.0)` — the rough AGL:**

This is a placeholder estimate. It subtracts 10 meters from the GPS altitude (MSL) and floors at zero. The assumption is that the launch site is roughly at 10 m above sea level (typical for many locations). During flight, this becomes increasingly inaccurate as the balloon climbs — at 30 km altitude, the error from this 10 m offset is negligible (0.03%).

The `max(0.0, …)` prevents negative AGL values before launch (e.g., if GPS altitude reads 5 m MSL at a site that's 10 m above sea level, `5 - 10 = -5` would floor to `0.0`).

**This is a known issue** — documented in `ARCHITECTURE.md` line 186: "AGL calculation: Currently hardcoded `alt_m - 10.0` as rough AGL. Needs barometric sensor or terrain database."

**`vdop = 0.0`:** The `$GPGGA` NMEA sentence doesn't include VDOP (vertical dilution of precision). The `$GPGSA` sentence does, but `parse_gga()` only handles GGA. The transmitter hardcodes `vdop=0.0` as a sentinel value meaning "unavailable." The dashboard treats this as "no VDOP data" rather than "literally zero VDOP" (which would imply impossibly perfect vertical accuracy).

```python
payload = frame.pack()
seq = (seq + 1) & 0xFFFF
```

**`frame.pack()`** (from `packet_format.py` lines 53–70):
- Maps `fix_type` string → byte (reverse lookup of `_FIX_TYPE_NAMES`: `{"none": 0, "2d": 1, "3d": 2}`).
- Packs all fields using `struct.Struct("<B H d d f f B B B f f")`: little-endian, 38 bytes total.
- The struct format string: type(1B) + seq(2B) + lat(8B) + lon(8B) + alt_m(4B) + agl_m(4B) + fix(1B) + fix_type(1B) + sats(1B) + hdop(4B) + vdop(4B).

**`seq = (seq + 1) & 0xFFFF`:** Increment and wrap at 16 bits (0–65535). The bitwise AND is equivalent to `% 65536` but slightly faster. After 65535, the counter wraps to 0. This gives the receiver ~18 hours of unique sequence numbers at 1 Hz before wrapping, enough to detect missing/duplicate packets in a typical balloon flight (2–4 hours).

#### 10.5.3 Status output (Line 202)

```python
print_status(len(payload), last_lat, last_lon, last_alt, last_sats)
```

Calls the status printer (see §9). Prints one line per TX cycle: `[GPSTx] pkt=38B  pos=37.75326,-122.39294  alt=41.7m  sats=12`.

#### 10.5.4 Burst waveform construction (Line 205)

```python
burst = build_burst(payload)
```

Calls `build_burst()` (see §8) with the default `sample_rate=FS`. Returns a Python list of exactly 2,000,000 complex numbers — 1 second of samples with the packet near the start and silence padding.

#### 10.5.5 GNU Radio flowgraph construction (Lines 207–221)

This section builds, starts, runs, and tears down a GNU Radio flowgraph on *every iteration*. This is arguably the most architecturally significant decision in the file.

```python
src = blocks.vector_source_c(burst, False)
```

**`blocks.vector_source_c(data, repeat)`:** GNU Radio source block that outputs a pre-computed vector of complex samples.
- `data`: The 2,000,000-element complex list from `build_burst()`.
- `repeat=False`: One-shot mode. After outputting all samples, the block signals "done" and the flowgraph stops naturally. This is *critical* — without `repeat=False`, the flowgraph would loop the burst indefinitely, requiring external coordination to stop.

**Why not `repeat=True` with a head/tail block?** Repeating the waveform would transmit the same GPS position repeatedly. Since each packet has a unique sequence number and may have updated GPS data, each burst must be unique. Building a new vector_source per cycle is the simplest way to guarantee uniqueness.

**Memory cost:** 2,000,000 complex values × 8 bytes/complex = 16 MB per burst. This is allocated and freed each second. On the Rock 2A (4 GB RAM), this is negligible.

```python
thr = blocks.throttle(gr.sizeof_gr_complex, fs)
```

**`blocks.throttle(itemsize, sample_rate)`:** A rate-limiting block that paces samples at exactly `sample_rate` samples/second. Without this, the `vector_source_c` would dump samples as fast as the CPU can push them (potentially overrunning the HackRF's USB buffer). The throttle enforces real-time pacing: 2 MS/s → exactly 1 second per burst.

**`gr.sizeof_gr_complex`:** The size of one complex sample in bytes (8). This tells the throttle the stride of each "item."

```python
sink_kwargs: tuple = ("driver=hackrf", "fc32", 1, "", "", [""], [""])
if args.serial:
    sink_kwargs = ("driver=hackrf", "fc32", 1, f"serial={args.serial}", "", [""], [""])
```

**The SoapySDR sink constructor — 7-element tuple:**

This is a critical platform-specific detail, documented in `ARCHITECTURE.md` line 172:

> *"On arm64 GNU Radio 3.10, `soapy.sink()` requires 7 positional args: `("driver=hackrf", "fc32", 1, "", "", [""], [""])`."*

The 7 elements are, in order:

| Index | Value | Meaning |
|---|---|---|
| 0 | `"driver=hackrf"` | SoapySDR driver name. Tells SoapySDR to load the HackRF module (`libSoapyHackRF.so`). |
| 1 | `"fc32"` | Sample format string. `fc32` = "float complex 32-bit" — a pair of 32-bit floats per sample. Matches GNU Radio's `gr_complex` type. |
| 2 | `1` | Number of channels. The HackRF has one TX channel (`CHANNEL_TX = 0`). |
| 3 | `"serial=XXXX"` or `""` | Device arguments. When `args.serial` is provided, this becomes `"serial=60a464dc3606610f"`. The empty string `""` means "first available HackRF." |
| 4 | `""` | Stream arguments. Empty = defaults. |
| 5 | `[""]` | Tuning arguments (list of strings, one per channel). Empty = defaults. |
| 6 | `[""]` | Other arguments (list of strings, one per channel). Empty = defaults. |

**Why a tuple of 7 positional arguments?** The arm64 GNU Radio 3.10 Python bindings for `soapy.sink()` don't accept keyword arguments properly — they must be passed positionally. The `tuple` with spread operator (`*sink_kwargs`) is the canonical workaround. On x86 GNU Radio 3.10, keyword arguments might work, but the HAB project targets arm64 exclusively for the TX side.

**Why `fc32` and not `cf32`?** In SoapySDR, the format string is `fc32` (float complex 32) or `sc16` (signed complex 16-bit integer). GNU Radio uses `gr_complex` internally, which is two `float32`s — this matches `fc32`. The HackRF driver accepts `fc32` and handles the float-to-integer conversion internally.

**Serial number logic:** If `args.serial is None` (default), arg[3] is `""` — SoapySDR opens the first HackRF it finds. If `args.serial` is set, arg[3] becomes `"serial=60a464dc3606610f"`, which SoapySDR uses to select a specific HackRF by its USB serial number. This is essential when multiple HackRFs are connected (e.g., one for TX, one for RX during testing).

```python
sink = soapy.sink(*sink_kwargs)
sink.set_sample_rate(0, fs)
sink.set_bandwidth(0, 0)
sink.set_frequency(0, freq)
sink.set_gain(0, "AMP", 1.0 if args.amp else 0.0)
sink.set_gain(0, "VGA", float(args.vga))
```

**`sink.set_sample_rate(0, fs)`:** Channel 0, sample rate = 2,000,000 S/s. The HackRF supports rates from 2 MS/s to 20 MS/s. 2 MS/s is the lowest; higher rates consume more CPU and USB bandwidth.

**`sink.set_bandwidth(0, 0)`:** Channel 0, bandwidth = 0 (auto). When bandwidth is set to 0, the HackRF driver automatically selects the baseband filter bandwidth. For 2 MS/s sample rate, this is typically around 1.75 MHz (0.875 × sample rate). This is more than sufficient for the 135 kHz occupied bandwidth (see RRC_ALPHA discussion in §3).

**`sink.set_frequency(0, freq)`:** Channel 0, center frequency in Hz. Default 915 MHz. The HackRF can tune from 1 MHz to 6 GHz with < 1 Hz resolution.

**`sink.set_gain(0, "AMP", 1.0 if args.amp else 0.0)`:** Channel 0, amplifier gain. The HackRF TX chain has two gain stages:
- **AMP:** 0 or 1 (on/off). Adds approximately 14 dB of gain. `1.0` = on, `0.0` = off.
- **VGA:** 0 to 47 dB (variable). Set in the next line.

**`sink.set_gain(0, "VGA", float(args.vga))`:** Channel 0, VGA gain. Default 47 dB (max). Total TX power with AMP on + VGA max ≈ 10 mW (+10 dBm). This is the approximate maximum legal output for the 915 MHz ISM band under FCC Part 15 without a license.

**Gain vs. power:** The HackRF doesn't have calibrated power output. The gain values are relative. The actual radiated power depends on the antenna, cable losses, and frequency. 47 + AMP on is approximately +5 to +10 dBm at the SMA connector, verified empirically.

```python
tb = gr.top_block()
tb.connect(src, thr, sink)
tb.start()
```

**`gr.top_block()`:** Creates the GNU Radio flowgraph container. This is a directed graph of blocks connected by sample streams.

**`tb.connect(src, thr, sink)`:** Connects three blocks in series:
```
vector_source_c → throttle → soapy.sink
```
- `src` (vector_source_c): Produces complex samples from the burst list.
- `thr` (throttle): Paces samples at exactly 2 MS/s.
- `sink` (soapy.sink): Sends samples to the HackRF via USB.

GNU Radio handles the type checking and buffer allocation between blocks automatically.

**`tb.start()`:** Starts the flowgraph. The blocks begin executing in separate threads. The `vector_source_c` starts producing samples, the `throttle` paces them, and the `soapy.sink` feeds them to the HackRF. With `repeat=False`, the flowgraph will stop automatically when the `vector_source_c` runs out of samples.

**Implicit assumption: the flowgraph runs to completion before the next iteration.** With 2,000,000 samples at 2 MS/s, the burst takes exactly 1 second to transmit. The `time.sleep(1.05)` in the next section provides a 50 ms margin.

#### 10.5.6 Wait and teardown (Lines 223–227)

```python
# Wait for the burst to complete (1 second of samples)
time.sleep(1.05)

tb.stop()
tb.wait()
```

**`time.sleep(1.05)`:** Sleeps for 1.05 seconds. The burst is 1.0 seconds of samples, but GNU Radio's startup (thread creation, USB initialization) adds a small overhead. The 50 ms overrun ensures the flowgraph has definitely finished before we try to tear it down.

**Why 1.05 and not check programmatically?** GNU Radio 3.10's Python API doesn't have a clean "flowgraph done" callback in Python (it exists in C++). `tb.stop()` + `tb.wait()` is the standard pattern, but calling `tb.stop()` before the flowgraph finishes naturally can cause dropped samples. Sleeping slightly longer than the burst duration guarantees the flowgraph is done.

**`tb.stop()`:** Signals all blocks to stop. For blocks that are still running, this interrupts their `work()` function.

**`tb.wait()`:** Blocks until all flowgraph threads have exited. This ensures the HackRF is fully released before the next iteration tries to open it again. Without `tb.wait()`, the next `soapy.sink()` construction could fail with "device busy" because the previous flowgraph's HackRF handle hasn't been released yet.

**The teardown/reconstruction cycle:** This is the most expensive part of the loop. Each iteration:
1. Constructs `soapy.sink()` — opens the HackRF via USB, initializes the SoapySDR driver.
2. Constructs `gr.top_block()` — allocates thread pool, buffer infrastructure.
3. Starts the flowgraph — spawns threads.
4. Waits 1.05 seconds.
5. Tears down the flowgraph — `stop()` + `wait()`, joins threads, destructors release the HackRF.

This pattern is chosen because it's simple and robust: each cycle gets a clean HackRF state. The alternative — a persistent flowgraph with block-level parameter updates — would be more complex and risk HackRF driver state corruption. For a 1 Hz cycle, the overhead is acceptable.

### 10.6 Signal handling and cleanup (Lines 229–233)

```python
except KeyboardInterrupt:
    pass
finally:
    gps.close()
    print("[GPSTx] Stopped.")
```

**`except KeyboardInterrupt:`** — Catches Ctrl+C (SIGINT). The `pass` body means "do nothing" — the `finally` block handles cleanup regardless.

**`finally:`** — This block runs whether the loop exits normally (never happens; `while True`), via Ctrl+C, or via an unhandled exception.

**`gps.close()`** — Closes the serial port to the GPS receiver. The `NMEAParser.close()` method (from `nmea.py` line 174) calls `self.serial.close()`, which releases the `/dev/ttyS0` file descriptor. Without this, the serial port would remain open after the script exits, potentially blocking the next launch.

**`print("[GPSTx] Stopped.")`** — Final status message to confirm clean shutdown.

### 10.7 Entry point guard (Lines 236–237)

```python
if __name__ == "__main__":
    main()
```

Standard Python guard: only run `main()` when the script is executed directly, not when imported as a module. While this file is unlikely to be imported (it's the top-level TX entry point), the guard is a best practice that costs nothing.

---

## 11. Cross-Cutting Concerns

### 11.1 The SoapySDR Sink 7-Arg Tuple — Deep Dive

The `soapy.sink(*sink_kwargs)` construction is one of the most fragile parts of this file. Here's why it's 7 positional args and why that matters:

**GNU Radio 3.10 SoapySDR Python bindings on arm64:**

The `soapy.sink()` block is a GNU Radio wrapper around SoapySDR's C API. On arm64 (aarch64) platforms, the Python bindings generated by SWIG or PyBind11 expose the constructor with positional-only arguments. The constructor signature (from the GNU Radio source) is conceptually:

```cpp
soapy_sink(const std::string& device,
           const std::string& type,
           size_t num_channels,
           const std::string& device_args,
           const std::string& stream_args,
           const std::vector<std::string>& tune_args,
           const std::vector<std::string>& other_args);
```

On x86, keyword arguments might work due to different binding generation. On arm64 (Debian 13 / GNU Radio 3.10.12), they don't — hence the tuple unpacking pattern.

**The `[""]` syntax for lists:** The last two arguments are lists of strings (one per channel). For a single-channel HackRF, `[""]` is a list with one empty string, meaning "defaults for channel 0." Attempting to pass `""` (a string, not a list) for these would cause a type error.

### 11.2 Burst Timing — The 1 Hz Cycle

The timing is:

```
|<────────────────── 1.05 second cycle ──────────────────>|
|         |<────────── 1.000 second burst ──────────>|    |
| create  |  50ms gap  |  6.24ms packet  |  ~943ms   |    |
| flow-   |  silence   |    waveform     |  silence  |    |
| graph   |            |                 |           |    |
|         |<── gap ──> |                                  |
```

**`gap_samples = 100,000` (50 ms):** Leading silence.
**`packet waveform = 12,480` (6.24 ms):** The actual BPSK transmission.
**`pad_after = 1,887,520` (~943.76 ms):** Trailing silence to fill 1 second.

The receiver sees: off → 50 ms of noise floor → 6.24 ms of BPSK signal → 943.76 ms of noise floor → repeat at t=1s.

### 11.3 GPS Read Loop — NMEA Sentence Flow

```
GPS Module (L76K)
    │
    │ UART @ 9600 8N1
    ▼
/dev/ttyS0 → serial.readline() → NMEA sentence string
    │
    │ $GPGGA,123519.00,3737.1958,N,12223.2345,W,1,12,1.0,41.7,M,-25.7,M,,*66
    ▼
parse_gga()
    │
    │ Checksum validation (XOR of bytes between $ and *)
    │ Field splitting on commas
    │ DM→DD coordinate conversion
    ▼
dict: {"time": "123519.00", "lat": 37.75326, "lon": -122.39294,
       "fix_quality": 1, "altitude": 41.7, "satellites": 12, "hdop": 1.0}
    │
    ▼
PositionFrame(type=0x01, seq=N, lat=37.75326, ...)
    │
    │ .pack()
    ▼
38-byte binary: b'\x01\x00\x00\xa0\x1a\x0b...'
```

**Fix quality to fix_type mapping (revisited):**

The NMEA `$GPGGA` field 6 is "GPS Quality indicator":
- 0 = Fix not valid
- 1 = GPS fix (SPS)
- 2 = Differential GPS fix (DGPS)
- 3 = PPS fix
- 4 = Real Time Kinematic (RTK)
- 5 = Float RTK
- 6 = Estimated (dead reckoning)
- 7 = Manual input mode
- 8 = Simulation mode

The transmitter's mapping to `fix_type` is:

```
fq_int >= 2 → "3d"
fq_int == 1 → "2d"
else        → "none"
```

This conflates DGPS/RTK/PPS into "3d" and maps basic SPS fix to "2d." While technically incorrect (a basic GPS fix is 3D), this is an intentional simplification for the dashboard display. The `fix` boolean (`fq_int > 0`) provides a binary "has fix / no fix" signal.

### 11.4 Error Handling Summary

| Scenario | Behavior |
|---|---|
| GPS serial port fails to open | `serial.Serial()` raises `SerialException` — script crashes. Operator restarts. |
| GPS timeout (1 second, no sentence) | `read_sentence()` returns `None`. Loop uses last-known values. |
| GPS checksum failure | `read_sentence()` internally retries (while loop). |
| Non-GGA sentence (e.g., $GPRMC) | `parse_gga()` returns `None`. Loop uses last-known values. |
| `parse_gga()` returns dict with missing fields | `.get()` with defaults; fields not updated. |
| HackRF not connected / busy | `soapy.sink()` raises exception — script crashes. |
| USB underrun (HackRF buffer empty) | GNU Radio silently drops; visible as gaps at receiver. Not caught. |
| `time.sleep()` interrupted by signal | Python raises `InterruptedError` in Python 3.5+ — unhandled, would crash. In practice, SIGINT during sleep still raises `KeyboardInterrupt`. |
| Flowgraph doesn't finish in 1.05s | `tb.stop()` called while still running — may lose last few samples. Unlikely with 1.05s sleep for a 1.00s burst. |

### 11.5 Implicit Assumptions and Edge Cases

1. **FS = 2,000,000 is hardcoded.** Changing it requires updating `SPS`, `RRC_NTAPS`, and possibly the RRC filter design. The `main()` function copies `fs = FS` but never modifies it. A `--sample-rate` CLI argument could be added for flexibility.

2. **Only GGA sentences are used.** The GPS module likely outputs multiple NMEA sentence types ($GPGGA, $GPRMC, $GPGSA, $GPGSV). Only GGA is parsed. RMC (which contains speed and course over ground) is ignored. GSA (which contains VDOP) is ignored. This means:
   - `vdop` is always 0.0 (sentinel for "not available").
   - No speed/course data in the position frame.
   - Missing satellite PRN/SNR data (from GSV).

3. **`last_*` state is never reset.** If the GPS loses fix mid-flight (e.g., during rapid ascent or parachute descent with antenna occlusion), the transmitter continues sending the last-known position with `fix=False` and `fix_type="none"`. The receiver must interpret this correctly — a position with `fix=False` should be treated as "stale/unreliable," not "current."

4. **Sequence number wraps at 65535 with no special handling.** After 18 hours, the sequence number repeats. The receiver's `seq` tracking should handle wrap-around gracefully (difference calculations using unsigned modulo arithmetic).

5. **No TX confirmation.** The transmitter doesn't verify that the HackRF actually transmitted the samples. USB underruns, amplifier failures, or antenna disconnection are invisible to this code. The only feedback is the absence of packets at the receiver.

6. **Single-threaded loop.** GPS reading, packet construction, and TX wait are all in one thread. If GPS parsing takes > 50 ms, it could eat into the 50 ms overrun margin (`time.sleep(1.05)`), causing the flowgraph teardown to overlap with the next iteration.

7. **No logging to file.** All output goes to stdout. In a flight scenario, this is typically piped to `tee` or a log file by the launch script. The script itself has no file-based logging.

8. **HackRF calibration.** The HackRF has a TCXO with ±1 ppm frequency accuracy. No frequency correction (PPM offset) is applied. At 915 MHz, ±1 ppm = ±915 Hz — acceptable for a BPSK receiver with adequate AFC (automatic frequency control).

9. **AGC on the HackRF TX.** The HackRF has no TX AGC. The gain values (VGA=47, AMP=on) are fixed for the duration of the flight. Atmospheric attenuation at 915 MHz over 100 km line-of-sight is < 0.1 dB — not a concern.

10. **Burst waveform rebuilt every cycle.** Even if GPS data hasn't changed, the burst is rebuilt from scratch. This wastes CPU but ensures correctness. The Rock 2A's RK3528 (quad-core Cortex-A55) handles this easily.

### 11.6 Comparison to `pkt_simple_tx.py`

| Feature | `pkt_simple_tx.py` | `gps_packet_tx.py` |
|---|---|---|
| Purpose | Standalone BPSK test transmitter | Operational GPS-to-packet transmitter |
| Payload | User-specified string (e.g., "HELLO WORLD") | `PositionFrame` binary (38 bytes, type 0x01) |
| Modulation | `bpsk_modulate()` with RRC shaping | Same function, imported pattern |
| Framing | Preamble + sync + len + payload + CRC | Same format |
| Flowgraph lifetime | Created once, runs continuously | **Created and destroyed each cycle** |
| Burst pattern | Multiple packets with gaps, then repeat | Single packet per cycle, 1 Hz |
| GPS integration | None | Serial NMEA parsing, live fix updates |
| `vector_source_c` repeat | `True` (continuous loop) | **`False` (single shot)** |
| `--vga` default | 30 | **47** (maximum, for operational range) |
| `--amp` default | `False` | **`True`** |
| HackRF serial handling | Inline in `soapy.sink()` call | Builds `sink_kwargs` tuple conditionally |
| `_bytes_to_bits()` | Local closure inside `make_packet()` | Module-level function |

The fundamental architectural difference: `pkt_simple_tx.py` builds one waveform and loops it indefinitely in a persistent flowgraph. `gps_packet_tx.py` builds a new waveform each second in a disposable flowgraph. This reflects the different requirements: the test tool repeats a static message; the operational tool transmits live, changing GPS data.

### 11.7 Software Layers in Context

```
┌─────────────────────────────────────────┐
│  gps_packet_tx.py  (this file)          │  ← Main TX loop, orchestration
├─────────────────────────────────────────┤
│  packet_format.py  (PositionFrame)      │  ← Binary serialization layer
│  nmea.py  (NMEAParser, parse_gga)       │  ← GPS protocol layer
├─────────────────────────────────────────┤
│  GNU Radio  (gr, blocks, soapy, firdes) │  ← SDR framework
│  SoapySDR + HackRF driver               │  ← Hardware abstraction
│  NumPy                                   │  ← Array math
├─────────────────────────────────────────┤
│  HackRF One  (USB 2.0)                  │  ← SDR hardware
│  L76K GPS  (UART /dev/ttyS0)            │  ← GPS hardware
└─────────────────────────────────────────┘
```

---

## 12. Operational Notes

### 12.1 Launch Command

```bash
python3 tx/gps_packet_tx.py --freq 915e6 --device /dev/ttyS0 --baud 9600
```

Defaults (`--vga 47`, `--amp`) are optimal for maximum range. Adding `--serial XXXX` only needed with multiple HackRFs.

### 12.2 Expected Output

```
[GPSTx] Opening GPS on /dev/ttyS0 @ 9600
[GPSTx] Freq=915.000 MHz  VGA=47.0  amp=True
[GPSTx] pkt=38B  pos=0.00000,0.00000  alt=0.0m  sats=0
[GPSTx] pkt=38B  pos=0.00000,0.00000  alt=0.0m  sats=0
...
[GPSTx] pkt=38B  pos=37.75326,-122.39294  alt=41.7m  sats=12
[GPSTx] pkt=38B  pos=37.75326,-122.39295  alt=41.7m  sats=12
...
^C[GPSTx] Stopped.
```

Initial cycles show Null Island (0,0) until first GPS fix. After fix acquisition, real coordinates appear.

### 12.3 Graceful Shutdown

`Ctrl+C` triggers `KeyboardInterrupt` → `finally` block → `gps.close()` → exit. The flowgraph in the *current* iteration is not cleaned up (the `except` block executes immediately during `time.sleep()`). This is acceptable because the process exit releases all OS resources (USB, serial port). The next launch of the script starts with a clean state.

---

## Appendix A: Packet On-Air Format (Complete)

```
PositionFrame 38 bytes:
┌──────┬──────┬──────────┬──────────┬───────┬───────┬─────┬──────────┬──────┬───────┬───────┐
│ type │ seq  │   lat    │   lon    │ alt_m │ agl_m │ fix │ fix_type │ sats │ hdop  │ vdop  │
│  u8  │ u16  │   f64    │   f64    │  f32  │  f32  │ u8  │    u8    │  u8  │  f32  │  f32  │
│  1B  │  2B  │   8B     │   8B     │  4B   │  4B   │ 1B  │    1B    │  1B  │  4B   │  4B   │
└──────┴──────┴──────────┴──────────┴───────┴───────┴─────┴──────────┴──────┴───────┴───────┘
Little-endian ("<"): struct.Struct("<B H d d f f B B B f f") = 38 bytes

BPSK Framing (outer envelope):
┌──────────────┬──────────────┬──────────────┬──────────────────┬──────────────┐
│   Preamble   │  Sync Word   │   Length     │    Payload       │   CRC-16     │
│   256 bits   │   32 bits    │   16 bits    │  N×8 bits        │   16 bits    │
│   1/0 alt.   │  0xE38FC0FC  │  big-endian  │  PositionFrame   │  XMODEM      │
│              │              │   uint16     │  (38 bytes)      │  polynomial  │
└──────────────┴──────────────┴──────────────┴──────────────────┴──────────────┘

Total bits on air: 256 + 32 + 16 + (38×8) + 16 = 624 bits
Symbol rate: 100,000 sym/s
Packet duration: 624 / 100,000 = 6.24 ms
Occupied bandwidth: 135 kHz (RRC α=0.35)
```

---

## Appendix B: Constants Quick Reference

| Constant | Value | Derivation / Rationale |
|---|---|---|
| `FS` | 2,000,000 | Minimum reliable HackRF sample rate; adequate for 100 ksym/s |
| `SPS` | 20 | 20× oversampling; standard GNU Radio BPSK value |
| `RRC_ALPHA` | 0.35 | Moderate roll-off; 135 kHz occupied BW @ 100 ksym/s |
| `RRC_NTAPS` | 11 | 11 symbol periods × 20 SPS = 220 taps; good ISI rejection |
| `SYNC_WORD` | 0xE38FC0FC | GNU Radio default correlation access code; good autocorrelation |
| `PREAMBLE_BITS` | 256 | 2.56 ms of alternating 1/0 for clock/AGC lock |
| `GAP_MS` | 50 | 50 ms silence = 100,000 samples; allows receiver AGC reset |
