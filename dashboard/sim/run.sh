#!/usr/bin/env bash
# One-click launcher for the HAB Balloon Telemetry Simulator
# Runs in fast mode (10x) so you see results quickly.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🎈 HAB Balloon Simulator — Fast Mode (10x)"
echo "   Starting ascent phase..."
echo "   Ctrl-C to stop"
echo ""

exec python3 "$SCRIPT_DIR/sim.py" --fast
