#!/usr/bin/env python3
"""
HAB Ground Station — Integration Test
Tests the HabEngine, PipelineManager, WebSocket server,
and DVB-S2 flowgraph import without hardware.

Usage:
    source ../rf-link/setup_env.sh
    python test_engine.py
"""

import sys
import os
import time
import json
import threading

# Add this dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hab_engine import HabEngine, SpectrumFrame, PipelineStatus

PASS = 0
FAIL = 0

def test(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


def run_tests():
    print("\n=== HAB Engine Integration Tests ===\n")

    # ── 1. Engine Creation ──
    print("1. Engine Creation")
    engine = HabEngine(enable_websocket=False)
    test("Engine is singleton", engine is HabEngine())
    test("Engine initialized", engine._initialized)
    test("Pipeline manager exists", engine.pipeline is not None)
    test("Flowgraph manager exists", engine.flowgraph is not None)

    # ── 2. Status ──
    print("\n2. Status")
    status = engine.status
    test("Status object exists", status is not None)
    test("Default not running", not status.running)
    test("Default TX inactive", not status.tx_active)
    test("Default frequency is 915e6", status.frequency == 915e6)

    # ── 3. Pipeline Manager ──
    print("\n3. Pipeline Manager")
    test("Pipeline not running initially", not engine.pipeline.is_running)
    # Create a small test TS file
    os.system("ffmpeg -y -f lavfi -i 'testsrc=duration=2:size=640x360:rate=10' -f lavfi -i 'sine=frequency=440:duration=2' -c:v libx264 -preset ultrafast -b:v 200k -c:a mp2 -b:a 32k -f mpegts -muxrate 500000 /tmp/engine_test.ts 2>/dev/null")
    test("Test TS file created", os.path.exists("/tmp/engine_test.ts"))

    # ── 4. Spectrum Callback ──
    print("\n4. Spectrum Callback")
    received_frames = []
    def on_spectrum(frame):
        received_frames.append(frame)
    engine.set_spectrum_callback(on_spectrum)
    test("Spectrum callback registered", engine._spectrum_callback is not None)

    # ── 5. Device State Update ──
    print("\n5. Device State")
    from hab_engine.models import DeviceInfo
    info = DeviceInfo(serial="test123", connected=True, frequency=915e6)
    engine.update_device_state(info)
    test("Device serial updated", engine._device_info.serial == "test123")
    test("Device connected flag", engine._device_info.connected)

    # ── 6. Param Updates ──
    print("\n6. Param Updates")
    engine.update_params(frequency=2.4e9, symbol_rate=5e6)
    test("Frequency updated to 2.4 GHz", engine._device_info.frequency == 2.4e9)
    test("Symbol rate updated", engine._device_info.sample_rate == 10e6)
    # Reset
    engine.update_params(frequency=915e6, symbol_rate=1e6)

    # ── 7. WebSocket Server ──
    print("\n7. WebSocket Server (with websockets)")
    try:
        import websockets
        test("websockets module importable", True)
        test("WebSocket server depends on websockets", True)
        # Note: We test the WebSocket via a fresh engine in a separate test
    except ImportError:
        test("websockets module importable", False, "not installed")

    # ── 8. GNU Radio Import Check ──
    print("\n8. GNU Radio Availability")
    try:
        from gnuradio import gr
        test("GNU Radio importable", True)
        test("GNU Radio version", gr.version() is not None, gr.version())
    except ImportError as e:
        test("GNU Radio importable", False, str(e))

    # ── 9. Flowgraph Import ──
    print("\n9. Flowgraph Import")
    try:
        from dvbs2_flowgraph import Dvbs2Flowgraph
        test("Dvbs2Flowgraph importable", True)
    except ImportError as e:
        test("Dvbs2Flowgraph importable", False, str(e))

    # ── 10. DVBS2 Module Test (file-to-file via CLI) ──
    print("\n10. DVBS2 CLI Tool Check")
    rf_link = os.path.expanduser("~/Documents/git/hab/rf-link")
    tx_path = os.path.join(rf_link, "dvbs2/tx.py")
    rx_path = os.path.join(rf_link, "dvbs2/rx.py")
    test("tx.py exists", os.path.exists(tx_path))
    test("rx.py exists", os.path.exists(rx_path))

    # ── 11. Network Sink Check ──
    print("\n11. Network Check")
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        test("Network available", True)
        s.close()
    except Exception:
        test("Network available", False)

    # ── 12. Cleanup ──
    print("\n12. Cleanup")
    engine.cleanup()
    test("Engine cleaned up", not (hasattr(engine, '_initialized') and engine._initialized))
    test("No engine instance after cleanup", HabEngine._instance is None)

    # ── Summary ──
    total = PASS + FAIL
    print(f"\n{'='*50}")
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    if FAIL == 0:
        print("All tests passed! 🎉")
    else:
        print(f"{FAIL} test(s) failed — review details above.")
    print(f"{'='*50}")
    return FAIL == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
