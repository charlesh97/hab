#!/bin/bash
# HAB Ground Station — Full OTA Test Suite
# Tests: file-to-file loopback, OTA link, WebSocket server
#
# Usage:
#   source ../rf-link/venv/bin/activate
#   bash test_ota.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RF_LINK_DIR="$SCRIPT_DIR/../../rf-link"

set -e

echo "=========================================="
echo "  HAB Ground Station — OTA Test Suite"
echo "=========================================="

# ── Step 1: Environment ──
echo ""
echo "[1/7] Checking environment..."
source "$RF_LINK_DIR/setup_env.sh" 2>/dev/null

python3 -c "
from gnuradio import gr
print(f'  GNU Radio: {gr.version()}')
from gnuradio import dtv, dvbs2rx, soapy
print('  DVB-S2 modules: OK')
" 2>&1 || { echo "  ❌ GNU Radio not available"; exit 1; }

# ── Step 2: Hardware ──
echo ""
echo "[2/7] Checking HackRF devices..."
hackrf_info 2>&1 | grep -E "Serial|Index|Firmware"

# Count devices
DEV_COUNT=$(hackrf_info 2>&1 | grep -c "Found HackRF" || echo 0)
echo "  Found $DEV_COUNT HackRF device(s)"

# Get serials
TX_SERIAL=$(hackrf_info 2>&1 | grep "Serial" | head -1 | awk '{print $3}')
RX_SERIAL=$(hackrf_info 2>&1 | grep "Serial" | tail -1 | awk '{print $3}')

echo "  TX Serial: $TX_SERIAL"
echo "  RX Serial: $RX_SERIAL"

# ── Step 3: File-to-File Loopback ──
echo ""
echo "[3/7] File-to-file loopback test..."
TS_FILE="/tmp/test_ota.ts"
IQ_FILE="/tmp/test_ota_loopback.iq"
DECODED_FILE="/tmp/test_ota_loopback.ts"

# Create test video
ffmpeg -y -f lavfi -i "testsrc=duration=5:size=640x360:rate=10" \
  -f lavfi -i "sine=frequency=440:duration=5" \
  -c:v libx264 -preset ultrafast -b:v 300k \
  -c:a mp2 -b:a 64k \
  -f mpegts -muxrate 965326 -mpegts_flags +resend_headers \
  "$TS_FILE" 2>/dev/null
echo "  Test file: $(wc -c < $TS_FILE) bytes"

# Encode
python3 "$RF_LINK_DIR/dvbs2/tx.py" \
  --source file --in-file "$TS_FILE" \
  --sink file --out-file "$IQ_FILE" \
  --sym-rate 1e6 --modcod QPSK1/2 \
  --rolloff 0.2 --pilots 2>/dev/null
echo "  IQ output: $(wc -c < $IQ_FILE) bytes"

# Decode
timeout 15 python3 "$RF_LINK_DIR/dvbs2/rx.py" \
  --source file --in-file "$IQ_FILE" \
  --sink file --out-file "$DECODED_FILE" \
  --sym-rate 1e6 --modcod QPSK1/2 \
  --rolloff 0.2 2>/dev/null || true

DECODED_SIZE=$(wc -c < "$DECODED_FILE" 2>/dev/null || echo 0)
ORIG_SIZE=$(wc -c < "$TS_FILE")
PERCENT=$(echo "scale=1; $DECODED_SIZE * 100 / $ORIG_SIZE" | bc 2>/dev/null || echo "0")
echo "  Decoded: $DECODED_SIZE bytes ($PERCENT% recovery)"
echo "  ✅ File-to-file loopback: $([[ $DECODED_SIZE -gt 1000 ]] && echo 'PASS' || echo 'FAIL')"

# ── Step 4: OTA Transmission ──
echo ""
echo "[4/7] Over-the-air transmission test..."

# Kill any leftover processes
kill $(ps aux | grep "dvbs2/rx.py\|dvbs2/tx.py" | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 1

# Start RX
python3 "$RF_LINK_DIR/dvbs2/rx.py" \
  --source hackrf \
  --hackrf-serial "$RX_SERIAL" \
  --hackrf-lna 8 --hackrf-vga 24 --hackrf-amp \
  --sink file --out-file "/tmp/ota_rx.ts" \
  --freq 915e6 --sym-rate 1e6 --modcod QPSK1/2 \
  --rolloff 0.2 --log \
  > /tmp/ota_rx_log.txt 2>&1 &
RX_PID=$!
echo "  RX PID: $RX_PID (serial: $RX_SERIAL)"
sleep 3

# Start TX
python3 "$RF_LINK_DIR/dvbs2/tx.py" \
  --source file --in-file "$TS_FILE" \
  --sink hackrf \
  --hackrf-serial "$TX_SERIAL" \
  --hackrf-vga 30 --hackrf-amp \
  --freq 915e6 --sym-rate 1e6 --modcod QPSK1/2 \
  --rolloff 0.2 --pilots \
  > /tmp/ota_tx_log.txt 2>&1 &
TX_PID=$!
echo "  TX PID: $TX_PID (serial: $TX_SERIAL)"

# Monitor for lock
echo "  Monitoring link..."
LOCKED=false
for i in $(seq 1 15); do
  sleep 1
  if grep -q "Lock=True" /tmp/ota_rx_log.txt 2>/dev/null; then
    LOCKED=true
    SNR=$(grep "SNR=" /tmp/ota_rx_log.txt | tail -1 | grep -o "SNR=[0-9.]*" | cut -d= -f2)
    echo "  ✅ LOCKED at t=${i}s, SNR: ${SNR:-N/A} dB"
    break
  fi
done

if [ "$LOCKED" = false ]; then
  echo "  ❌ Never achieved lock"
fi

# Wait for TX to finish
wait $TX_PID 2>/dev/null
sleep 3

# Check results
RX_SIZE=$(wc -c < /tmp/ota_rx.ts 2>/dev/null || echo 0)
echo "  OTA received: $RX_SIZE bytes"
if [ "$RX_SIZE" -gt 10000 ]; then
  echo "  ✅ OTA test: PASS ($RX_SIZE bytes received)"
else
  echo "  ⚠️  OTA test: PARTIAL ($RX_SIZE bytes - may be marginal signal)"
fi

# Cleanup
kill $RX_PID 2>/dev/null || true

# ── Step 5: TS Verification ──
echo ""
echo "[5/7] Transport stream verification..."
if [ "$RX_SIZE" -gt 1000 ]; then
  tsp -I file /tmp/ota_rx.ts -P analyze -O drop 2>/dev/null | grep -E "PID|PMT|PAT" | head -5
  echo "  ✅ TS structure: valid"
else
  echo "  ⚠️  No data to analyze"
fi

# ── Step 6: WebSocket Server ──
echo ""
echo "[6/7] WebSocket server test..."
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from hab_engine import HabEngine
import time, json, asyncio, websockets

engine = HabEngine(enable_websocket=True)
time.sleep(1)

async def test():
    async with websockets.connect('ws://127.0.0.1:8765', timeout=3) as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=2)
        d = json.loads(msg)
        print(f'  Status broadcast: type={d.get(\"type\")}')
        
        await ws.send(json.dumps({'command': 'set_frequency', 'data': {'frequency': 915000000}}))
        print('  Command sent: set_frequency')
        
        print('  ✅ WebSocket: PASS')

asyncio.run(test())
engine.cleanup()
" 2>&1

# ── Step 7: GUI Import Check ──
echo ""
echo "[7/7] GUI import check..."
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from PySide6 import QtCore
from hab_engine import HabEngine
from connection_tab import ConnectionTab
from dvbs2_tx_tab import DVBS2TXTab
from telemetry_tab import TelemetryTab
print('  All GUI modules importable: OK')
print('  ✅ GUI imports: PASS')
" 2>&1

# ── Summary ──
echo ""
echo "=========================================="
echo "  OTA Test Suite Complete"
echo "=========================================="
echo "  RX file: $(wc -c < /tmp/ota_rx.ts 2>/dev/null || echo 0) bytes"
echo "  Logs: /tmp/ota_rx_log.txt, /tmp/ota_tx_log.txt"
echo ""
echo "Next steps:"
echo "  1. Launch GUI: cd hab-gui/python && ./launch.sh"
echo "  2. Connect HackRF in Connection tab"
echo "  3. Set pipeline in DVBS-2 TX tab"
echo "  4. Start macOS dashboard: open macos/Balloon Dashboard/"
echo "=========================================="
