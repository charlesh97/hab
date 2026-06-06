#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HAB_ROOT="$(dirname "$SCRIPT_DIR")"
VENV="${SCRIPT_DIR}/.venv"

# Homebrew Python is required (system Python 3.9 can't import SoapySDR)
HOMEBREW_PYTHON="/opt/homebrew/bin/python3.14"

# Activate the virtual environment if it exists, else use Homebrew Python directly
if [ -f "${VENV}/bin/activate" ]; then
  source "${VENV}/bin/activate"
  PYTHON="${VENV}/bin/python"
else
  PYTHON="${HOMEBREW_PYTHON}"
fi

# Add rf-link libraries to path
export PYTHONPATH="${HAB_ROOT}/rf/packet/src:${HAB_ROOT}/rf/dvbs2:${PYTHONPATH:-}"

# Add Homebrew site-packages (for SoapySDR, which is installed via brew not pip)
export PYTHONPATH="/opt/homebrew/lib/python3.14/site-packages:${PYTHONPATH}"

HOST="${HAB_HOST:-0.0.0.0}"
PORT="${HAB_PORT:-8000}"

echo "Starting HAB Ground Station server on ${HOST}:${PORT}..."
echo "  Dashboard: http://localhost:${PORT}"
echo "  WebSocket: ws://localhost:${PORT}/ws"
exec "${PYTHON}" -m uvicorn main:app --host "${HOST}" --port "${PORT}" --log-level info
