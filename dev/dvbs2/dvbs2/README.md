# DVB-S2 Video Link for HAB
https://github.com/igorauad/gr-dvbs2rx


## Files
| File | Purpose |
|------|---------|
| `tx.py` | Full-featured DVB-S2 transmitter (CLI, supports HackRF/USRP/BladeRF/PlutoSDR/file) |
| `rx.py` | Full-featured DVB-S2 receiver (CLI, supports HackRF/RTL-SDR/USRP/BladeRF/file) |
| `flowgraph.py` | GRC-generated transmitter flowgraph (standalone PyQt5 GUI version) |
| `flowgraph.grc` | GNU Radio Companion source for the flowgraph |
| `soapy-tx.py` | Simple SoapySDR test transmitter |

## Quick Test (File-to-File Loopback)

```bash
source setup_env.sh

# Encode test video
ffmpeg -y -f lavfi -i "testsrc=duration=10:size=1280x720:rate=15" \
  -f lavfi -i "sine=frequency=440:duration=10" \
  -c:v libx264 -preset ultrafast -b:v 400k \
  -c:a mp2 -b:a 64k \
  -f mpegts -muxrate 965326 -mpegts_flags +resend_headers \
  /tmp/test_video.ts

# Transmit TS → DVB-S2 IQ samples
python3 dvbs2/tx.py \
  --source file --in-file /tmp/test_video.ts \
  --sink file --out-file /tmp/test_output.iq \
  --sym-rate 1e6 --modcod QPSK1/2 --rolloff 0.2 --pilots

# Receive IQ → decoded TS
python3 dvbs2/rx.py \
  --source file --in-file /tmp/test_output.iq \
  --sink file --out-file /tmp/test_decoded.ts \
  --sym-rate 1e6 --modcod QPSK1/2 --rolloff 0.2

# Play the result
ffplay /tmp/test_decoded.ts
```

## Over-the-Air Test

### Transmitter
```bash
source setup_env.sh
python3 dvbs2/tx.py \
  --source file --in-file /tmp/test_video.ts \
  --sink hackrf --hackrf-vga 10 --hackrf-amp \
  --hackrf-serial '000000000000000060a464dc3606610f' \
  --freq 915e6 --sym-rate 1e6 --modcod QPSK1/2 \
  --rolloff 0.35 --pilots
```

### Receiver
```bash
source setup_env.sh
python3 dvbs2/rx.py \
  --sink file --out-file /tmp/rx_video.ts \
  --source hackrf --hackrf-vga 10 --hackrf-lna 3 \
  --hackrf-serial '000000000000000060a464dc3674640f' \
  --freq 915e6 --sym-rate 1e6 --modcod QPSK1/2 \
  --rolloff 0.35 --gui
```

## Bitrate Reference

For QPSK 1/2 at 1 Msym/s with pilots ON: **965,326 bps** transport stream bitrate.
Adjust video encode bitrate accordingly (e.g. `-b:v 700k -b:a 128k`).

See `../dtv-utils-master/dvbs2rate` for other modcods.
(https://github.com/drmpeg/dtv-utils/tree/master)