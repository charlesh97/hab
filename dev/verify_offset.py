#!/usr/bin/env python3
"""Verify the --offset default was changed to 100e3 in both TX and RX."""
import subprocess
import sys

files = [
    ("payload/tx/combined_tx.py", "default=100e3"),
    ("ground/rx/combined_rx.py", "default=100e3"),
]

all_ok = True
for path, expected in files:
    with open(path) as f:
        content = f.read()
    # Find the offset argument
    import re
    match = re.search(r'--offset.*?default=([\d.e]+)', content)
    if match:
        value = match.group(1)
        ok = "100e3" in value or value == "100000.0"
        status = "✓" if ok else "✗"
        if not ok:
            all_ok = False
        print(f"{status} {path}: --offset default={value}")
    else:
        print(f"✗ {path}: could not find --offset default")
        all_ok = False

sys.exit(0 if all_ok else 1)
