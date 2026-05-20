#!/opt/homebrew/bin/python3.14
"""
DVB-S2 TX Worker — Runs as a subprocess managed by the server.
Communicates via stdin/stdout JSON-RPC style messages.
"""

import json
import logging
import os
import signal
import sys
import time
import traceback
from pathlib import Path

# Add paths for GNU Radio
sys.path.insert(0, str(Path(__file__).parent.resolve()))
sys.path.insert(0, "/opt/homebrew/lib/python3.14/site-packages")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [dvbs2-worker] %(levelname)s: %(message)s",
)
logger = logging.getLogger("dvbs2-worker")

_flowgraph = None


def _send_response(response: dict):
    """Send a JSON response to the parent process."""
    print(json.dumps(response), flush=True)


def cmd_start(config: dict):
    """Create and start the DVB-S2 TX flowgraph."""
    global _flowgraph

    if _flowgraph is not None:
        _send_response({"error": "Flowgraph already running"})
        return

    try:
        from dvbs2_flowgraph import Dvbs2Flowgraph

        logger.info(f"Creating flowgraph: freq={config.get('center_freq', 915e6)}, "
                     f"srate={config.get('symbol_rate', 1e6)}, "
                     f"modcod={config.get('modcod', 'QPSK1/4')}")

        _flowgraph = Dvbs2Flowgraph(
            device_args=config.get("device_args", "driver=hackrf"),
            center_freq=float(config.get("center_freq", 915e6)),
            symbol_rate=float(config.get("symbol_rate", 1e6)),
            tx_gain_vga=float(config.get("tx_gain_vga", 16.0)),
            tx_gain_amp=bool(config.get("tx_gain_amp", False)),
            file_path=config.get("file_path", "/tmp/tsfifo"),
            rolloff=float(config.get("rolloff", 0.2)),
            modcod=str(config.get("modcod", "QPSK1/4")),
            pilots=bool(config.get("pilots", True)),
        )
        logger.info("Flowgraph created, starting...")
        _flowgraph.start()
        logger.info("Flowgraph started successfully")
        _send_response({"status": "started"})

    except Exception as e:
        logger.error(f"Failed to start flowgraph: {e}")
        logger.error(traceback.format_exc())
        _send_response({"error": str(e), "traceback": traceback.format_exc()})
        _flowgraph = None


def cmd_stop(config: dict = None):
    """Stop the DVB-S2 TX flowgraph."""
    global _flowgraph

    if _flowgraph is None:
        _send_response({"status": "already_stopped"})
        return

    try:
        logger.info("Stopping flowgraph...")
        _flowgraph.stop()
        _flowgraph.wait()
        logger.info("Flowgraph stopped")
        _send_response({"status": "stopped"})
    except Exception as e:
        logger.error(f"Error stopping flowgraph: {e}")
        _send_response({"error": str(e)})
    finally:
        _flowgraph = None


def cmd_reconfigure(config: dict):
    """Reconfigure running flowgraph parameters."""
    global _flowgraph

    if _flowgraph is None:
        _send_response({"error": "Flowgraph not running"})
        return

    try:
        _flowgraph.reconfigure(**config)
        _send_response({"status": "reconfigured"})
    except Exception as e:
        logger.error(f"Reconfigure error: {e}")
        _send_response({"error": str(e)})


_COMMANDS = {
    "start": cmd_start,
    "stop": cmd_stop,
    "reconfigure": cmd_reconfigure,
}


def main():
    """Main loop: read JSON commands from stdin, execute, respond via stdout."""
    # Ignore SIGINT/SIGTERM — parent handles cleanup
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

    # Notify parent we're ready
    _send_response({"status": "ready"})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            cmd = msg.get("command", "")
            data = msg.get("data", {})
            handler = _COMMANDS.get(cmd)
            if handler:
                handler(data)
            else:
                _send_response({"error": f"Unknown command: {cmd}"})
        except json.JSONDecodeError:
            _send_response({"error": "Invalid JSON"})
        except Exception as e:
            logger.error(f"Command handler error: {e}")
            _send_response({"error": str(e)})

    # Clean shutdown
    cmd_stop()


if __name__ == "__main__":
    main()
