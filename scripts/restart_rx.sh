#!/bin/bash
# restart_rx.sh — clean restart of the video-only RX on the Mac.
#
# Kills every RX-related process (combined_rx.py, DVB-S2 decoder, hackrf_transfer,
# MJPEG bridge ffmpeg on :8001) and starts a fresh video-only DVB-S2 receiver.
#
# Usage:   bash scripts/restart_rx.sh        (from ~/git/hab)
# Logs:    /tmp/rx.log                       (combined_rx.py + DVB-S2 decoder)
#
# Per Charles 08-02: BPSK parked; goal = reliable video on the dashboard.
# Config: Option A — 4 MS/s samp-rate, 1 Msym/s DVB-S2, no BPSK.
#         RX HackRF serial 60a464dc3606610f, LNA=32 VGA=40 AMP.

set -u

LOG=/tmp/rx.log

echo "=== restart_rx.sh: killing stale RX processes ==="

# Combined RX + its DVB-S2 decoder child + hackrf_transfer
pkill -9 -f 'combined_rx[.]py' 2>/dev/null
pkill -9 -f 'dvbs2/dvbs2/rx[.]py' 2>/dev/null
pkill -9 -f 'hackrf_transfer' 2>/dev/null

# MJPEG bridge (one-shot ffmpeg holding :8001 / UDP:1234)
pkill -9 -f 'udp://127.0.0.1:123[4]' 2>/dev/null
pkill -9 -f '0.0.0.0:800[1]' 2>/dev/null

sleep 1

echo "=== starting fresh RX ==="
cd /Users/charleslab/git/hab || exit 1
# PYTHONPATH set directly (sourcing dev/setup_env.sh trips on set -u in a
# fresh script shell; the env it builds is deterministic here):
PYTHONPATH=/opt/homebrew/lib/python3.14/site-packages:/Users/charleslab/git/hab/dev/dvbs2/dvbs2 \
nohup /opt/homebrew/bin/python3.14 -u ground/rx/combined_rx.py \
    --center-freq 914e6 \
    --sample-rate 4e6 \
    --sym-rate 1e6 \
    --no-bpsk \
    --serial 60a464dc3606610f \
    --lna 32 \
    --vga 40 \
    --amp \
    > "$LOG" 2>&1 &
RX_PID=$!
echo "RX started (pid $RX_PID) — log: $LOG"
echo "---"

sleep 8
echo "=== running processes ==="
pgrep -fl 'combined_rx[.]py|dvbs2/dvbs2/rx[.]py|hackrf_transfer|udp://127.0.0.1:123[4]' | grep -v pgrep
echo "=== log tail ==="
tail -8 "$LOG"
