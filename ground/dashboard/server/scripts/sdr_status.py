#!/usr/bin/env python3
"""Connect to dashboard WebSocket, dump SDR status, exit."""
import asyncio
import json
import sys

try:
    import websockets  # type: ignore
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)

WS_URL = "ws://localhost:8000/ws"


async def main():
    async with websockets.connect(WS_URL) as ws:  # type: ignore[attr-defined]
        print(f"Connected to {WS_URL}")
        seen_status = False
        async for msg_text in ws:
            try:
                msg = json.loads(msg_text)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "status":
                data = msg.get("data", {}) if "data" in msg else msg
                if isinstance(data, dict):
                    hackrf = data.get("hackrf", {})
                    dvbs2 = data.get("dvbs2", {})
                    pipeline = data.get("pipeline", {})

                    print(f"\n{'='*60}")
                    print("PIPELINE")
                    print(f"  running:  {pipeline.get('running', '?')}")
                    print(f"\nHACKRF")
                    print(f"  serial:   {hackrf.get('serial', '?')}")
                    print(f"  freq:     {hackrf.get('freq_hz', 0)/1e6:.3f} MHz" if hackrf.get("freq_hz") else "  freq:     --")
                    print(f"  samp_rate:{hackrf.get('sample_rate', 0)/1e6:.3f} Msps" if hackrf.get("sample_rate") else "  samp_rate: --")
                    print(f"  lna:      {hackrf.get('lna', '--')} dB")
                    print(f"  vga:      {hackrf.get('vga', '--')} dB")
                    print(f"  amp:      {hackrf.get('amp', '--')}")
                    print(f"\nDVB-S2")
                    print(f"  locked:   {dvbs2.get('locked', '--')}")
                    print(f"  snr_db:   {dvbs2.get('snr_db', '--')}")
                    print(f"  modcod:   {dvbs2.get('modcod', '--')}")
                    print(f"  offset:   {dvbs2.get('offset_hz', 0)/1e6:.3f} MHz" if dvbs2.get("offset_hz") else "  offset:    --")
                    print(f"{'='*60}\n")

                seen_status = True
                break  # one status dump is enough

        if not seen_status:
            print("No status message received. Is the SDR pipeline running?")


if __name__ == "__main__":
    asyncio.run(main())
