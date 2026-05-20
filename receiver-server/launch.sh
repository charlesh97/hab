#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HAB_ROOT="$(dirname "$SCRIPT_DIR")"

export PYTHONPATH="${HAB_ROOT}/rf-link/packet/src:${HAB_ROOT}/rf-link/dvbs2:${PYTHONPATH:-}"

HOST="${HAB_HOST:-0.0.0.0}"
PORT="${HAB_PORT:-8000}"

echo "Starting receiver server on ${HOST}:${PORT}..."
exec python3 -m uvicorn main:app --host "${HOST}" --port "${PORT}" --log-level info
