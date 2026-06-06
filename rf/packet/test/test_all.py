#!/usr/bin/env python3
"""
Test harness: runs any combination of the 3 test layers.

Usage:
  ./test_all.py                  # all available layers
  ./test_all.py --layer 1        # layer 1 only
  ./test_all.py --layer 2        # layer 2 only
  ./test_all.py --layer 1 --layer 2  # layers 1 and 2

Exit code: 0 if all selected layers pass, 1 if any fail.
"""
import sys, os, subprocess, argparse

HERE = os.path.dirname(__file__)
PYTHON = '/opt/homebrew/bin/python3.14'


def run_layer(num, label):
    """Run one test layer.  Returns (passed, total)."""
    script = os.path.join(HERE, f'test_layer{num}.py')
    if not os.path.exists(script):
        return (0, 0, f"No script for layer {num}")

    print(f"\n{'='*60}")
    print(f"  Layer {num}: {label}")
    print(f"{'='*60}")

    result = subprocess.run(
        [PYTHON, script],
        capture_output=True, text=True, timeout=120
    )

    # Print output aligned
    for line in result.stdout.strip().split('\n'):
        if line:
            print(f"  {line}")
    if result.stderr.strip():
        for line in result.stderr.strip().split('\n'):
            if line:
                print(f"  stderr: {line}")

    passed = result.returncode == 0
    status = "PASS" if passed else "FAIL"
    print(f"  {'─'*50}")
    print(f"  Layer {num}: {status} (exit={result.returncode})")
    print()
    return (1 if passed else 0, 1, status)


def main():
    parser = argparse.ArgumentParser(description='RF Link test suite')
    parser.add_argument('--layer', type=int, action='append',
                        choices=[1, 2, 3],
                        help='Run a specific layer (can repeat)')
    args = parser.parse_args()

    layers = {
        1: "Direct Codec Unit Tests",
        2: "RF Software Loopback",
        3: "Hardware Cable Test",
    }

    if args.layer:
        selected = args.layer
    else:
        selected = [1, 2, 3]

    passed = 0
    total = 0
    for num in selected:
        p, t, status = run_layer(num, layers[num])
        passed += p
        total += t

    print(f"\n{'='*60}")
    if total > 0:
        print(f"  Result: {passed}/{total} passed")
    else:
        print(f"  No layers were run")
    print(f"{'='*60}")

    sys.exit(0 if passed == total else 1)


if __name__ == '__main__':
    main()
