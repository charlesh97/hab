#!/usr/bin/env python3
"""Boot entry point for the payload composite transmitter."""

from __future__ import annotations

import sys
from pathlib import Path


_HAB_ROOT = Path(__file__).resolve().parent.parent
if str(_HAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_HAB_ROOT))

from payload.tx.combined_tx import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
