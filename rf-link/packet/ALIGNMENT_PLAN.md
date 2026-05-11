# Packet Structure Alignment — Progress

## Step 1: Packet Structure (Payload) ✅ **DONE**

- **`fec_cc.py`** — CC encoder + Viterbi decoder, bit-exact with GNU Radio
- **`packet_codec.py`** — CRC-32 + FEC encode/decode, `packet_encode()` / `packet_decode()`
- Key innovation: 2-bit pre-padding avoids the GR byte-alignment truncation bug

## Step 2: True Preamble ✅ **DONE** (merged into Step 1 integration)

- Replaced 256-bit alternating preamble with the actual 24-byte preamble from `packet_rx.py`
- Replaced `0xE38FC0FC` sync word with `0xACDDA4E2` (GNU Radio access code, NOT in preamble)
- Eliminated false-correlation problem from alternating preamble harmonics

## Step 3: Header + Payload Demux 🔲 **NEXT**

- Currently: receiver assumes fixed FEC payload size. Need to decode a header that carries the payload length.
- The original uses `digital.protocol_formatter_async` / `digital.protocol_parser_b` with
  `header_format_default` or `header_format_counter`.
- Simplify: use a 1-byte length field at the start of the payload (before CRC), or decode the
  GNU Radio default header format.

## Step 4: GNU Radio Hierarchical Block Integration 🔲

- Currently: native Python TX/RX chain with separate packet codec.
- The original uses `packet_tx.py`/`packet_rx.py` hierarchical blocks.
- For final alignment: wrap the GR blocks with SoapySDR, removing the native Python chain.

## Step 5: Burst Shaping 🔲

- Original adds Hann ramp, 10K pre-padding, filter delay padding to avoid spectral splatter.
- The current enhanced TX just adds silent gaps between packets.

## Step 6: Multiple Constellation Support 🔲

- Original uses BPSK header, QPSK payload.
- Current is all-BPSK.

## Files Created/Modified

| File | Status | Purpose |
|------|--------|---------|
| `fec_cc.py` | ✅ | CC encoder + Viterbi decoder |
| `packet_codec.py` | ✅ | CRC-32 + FEC framing |
| `pkt_enhanced_tx.py` | ✅ | Enhanced transmitter |
| `pkt_enhanced_rx.py` | ✅ | Enhanced receiver |
| `HELLO_TX_RX.md` | Updated | Documentation |
| `ALIGNMENT_PLAN.md` | ✅ This file | Progress tracking |
