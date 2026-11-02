#!/bin/bash
# restart_tx.sh — clean restart of the video-only TX on the Rock 2A.
#
# Kills every TX-related process (composite TX, DVB-S2 encoder, ffmpeg, GPS
# gpioset holders) and starts a fresh video-only DVB-S2 transmitter.
#
# Usage:   bash /home/hab/restart_tx.sh
# Logs:    /tmp/tx_video.log  (combined_tx.py output)
#
# Per Charles 08-02: BPSK parked; goal = reliable video on the dashboard.
# Config: Option A — 4 MS/s samp-rate, 1 Msym/s DVB-S2, rrc-delay 1,
#         testsrc 640x360, no timestamp overlay, no BPSK.

set -u

LOG=/tmp/tx_video.log
cd /home/hab/git/hab || exit 1

echo "=== restart_tx.sh: killing stale TX processes ==="

# Composite TX wrapper + combined_tx.py (bracket patterns avoid self-match)
pkill -9 -f 'payload/tx/main[.]py' 2>/dev/null
pkill -9 -f 'combined_tx[.]py' 2>/dev/null

# DVB-S2 encoder (dev/dvbs2/dvbs2/tx.py) and its ffmpeg source
pkill -9 -f 'dvbs2/dvbs2/tx[.]py' 2>/dev/null
pkill -9 -f 'ffmpeg.*-f lavfi -i testsrc' 2>/dev/null

# GPS gpioset holders — combined_tx.py re-asserts them at startup
pkill -9 -f 'gpiose[t].*gpiochip1' 2>/dev/null

sleep 1

echo "=== starting fresh TX ==="
nohup python3 -u payload/tx/main.py \
    --center-freq 914e6 \
    --sample-rate 4e6 \
    --sym-rate 1e6 \
    --rrc-delay 1 \
    --video-size 640x360 \
    --no-timestamp-overlay \
    --video-source testsrc \
    --no-bpsk \
    --serial 60a464dc3674640f \
    > "$LOG" 2>&1 &
TX_PID=$!
echo "TX started (pid $TX_PID) — log: $LOG"
echo "---"

sleep 3
echo "=== running processes ==="
pgrep -fl 'payload/tx/main[.]py|combined_tx[.]py|dvbs2/dvbs2/tx[.]py|ffmpeg' | grep -v pgrep
echo "=== log head ==="
head -5 "$LOG"
