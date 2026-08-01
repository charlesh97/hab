#!/usr/bin/env python3
"""Compatibility entry point for the composite payload transmitter."""

from __future__ import annotations

if __package__:
    from .combined_tx import main
else:  # Direct execution: python3 payload/tx/main.py
    from combined_tx import main


if __name__ == "__main__":
    raise SystemExit(main())
