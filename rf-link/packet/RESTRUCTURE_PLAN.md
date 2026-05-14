# Project Restructure Plan — RF Packet Transmission

## 1. Current State Analysis

The `packet/` directory has evolved from a simple hello-world BPSK test into a
layered packet link with CRC-32 + FEC, an enhanced TX/RX chain, and a 3-layer
test pipeline.  However, all ~38 files live in one flat directory alongside the
parent `rf-link/` level which also contains unrelated DVB-S2 binaries, large TS
files, and old deprecated scripts.

### 1.1 What to Keep (Active / Worth Preserving)

| File | Lines | Role | Depends On |
|------|-------|------|------------|
| `fec_cc.py` | 282 | CC encoder + Viterbi decoder (k=7, rate=1/2) | — (standalone, also importable) |
| `packet_codec.py` | 210 | CRC-32 + FEC framing (packet_encode/decode) | `fec_cc` |
| `pkt_enhanced_tx.py` | 146 | Enhanced BPSK transmitter (SoapySDR) | `packet_codec` |
| `pkt_enhanced_rx.py` | 355 | Enhanced BPSK receiver (sync-word corr + FEC decode) | `packet_codec` |
| `ALIGNMENT_PLAN.md` | — | Future feature roadmap | — |
| `README.md` | — | Project-level docs | — |
| `HELLO_TX_RX.md` | — | Legacy hello-world documentation | — |
| `test/` (dir) | — | 3-layer test pipeline + harness + README | varies |

### 1.2 What to Archive (Historical Reference Only, No Active Use)

These files represent the development path — GRC-generated blocks, early decoders,
and the original (unprotected) hello-world chain.  They have been succeeded by the
enhanced TX/RX chain but contain useful reference code.

**GNU Radio hierarchical blocks (GRC-generated originals):**
- `packet_tx.py` — Original hierarchical block, 224 lines (GRC output)
- `packet_rx.py` — Original hierarchical block, 327 lines (GRC output)
- `telemetry_tx.py` — Original HackRF TX script, 463 lines (imports `packet_tx`)
- `telemetry_rx.py` — Original HackRF RX script, 290 lines (imports `packet_rx`)

**Hello-world BPSK chain (no CRC, no FEC):**
- `pkt_hello_tx.py` — Simple BPSK burst TX
- `pkt_hello_rx.py` — Simple BPSK capture RX
- `pkt_rx_final.py` — Final hello-world live receiver
- `hello_decoder.py` — Offline decode for hello-world captures

**Experimental/development decoders (evolved into `pkt_enhanced_rx.py`):**
- `decode_complex.py` — Offline decode experiments
- `decode_offline.py` — Offline decode v1
- `decode_offline_v2.py` — Offline decode v2
- `decode_precise.py` — Precise decode experiments
- `final_decode.py` — Final decode iteration before enhanced RX

**GRC flowgraph Python stubs (the GRC `.grc` files are in `grc/`):**
- `bpsk_gr_rx.py` — GRC-generated BPSK RX
- `gr_live_rx.py` — GRC-based live receiver
- `native_gr_rx.py` — Native GNU Radio RX chain
- `simple_bpsk_rx.py` — Minimal GR RX test
- `hybrid_tx.py` — Hybrid numpy+GR TX
- `minimal_tx.py` — Minimal GR TX
- `minimal_rx.py` — Minimal GR RX

**Test stubs / one-off experiments:**
- `test_demux_loopback.py` — Header demux experiment (superseded by formal test/test_layer*.py)
- `test_sps4.py` — SPS=4 experiment (moved to enhanced TX/RX SPS param)
- `pkt_enhanced_tx_backup.py` — Backup of enhanced TX before import-scope refactor (trivial diff)

**GRC flowgraph files (reference; keep in place or move to `grc/`):**
- `backup/` — Contains `.grc` + `.py` copies that duplicate `grc/` content
- `grc/` — Current GRC flowgraphs

### 1.3 What to Remove / Delete (No Value)

| File | Reason |
|------|--------|
| `backup/` dir | `grc/` already has the same GRC flowgraphs + `debug_packet_rxtx/` covers the PY duplicates |
| `pkt_enhanced_tx_backup.py` | Trivial diff from `pkt_enhanced_tx.py` (SPS=4 vs SPS=20, import scoping) |
| `.pytest_cache/` | Transient cache, never committed |
| `__pycache__/` | Transient bytecode, never committed |

### 1.4 What's at the Parent Level (`rf-link/`) That Should Move Out

These are **not** part of the packet project and clutter the repo:

| File | Size | Action |
|------|------|--------|
| `dvbs2-rx-mod` | 72 KB | Move to `deprecated/` (already has `deprecated/dvbs2_tx.py` etc.) |
| `dvbs2-tx-mod` | 48 KB | Move to `deprecated/` |
| `gr-dvbs2rx/` | dir | Move to `deprecated/` |
| `dtv-utils-master/` | dir | Move to `deprecated/` |
| `output.ts` | 36 MB | Delete (video capture, unrelated to packet RF) |
| `thefuryclip.ts` | 7.2 MB | Delete or move to a media archive |
| `hackrf-2024.02.1-fw.zip` | 28 MB | Keep (firmware is relevant to the SDR hardware), move to `deprecated/` |
| `Untitled.rtf` | 2 KB | Delete (orphaned untitled document) |

---

## 2. Proposed New Directory Tree

```
rf-link/
├── README.md                          # Updated — scope narrowed to packet RF link
├── requirements.txt                   # Keep as-is
├── setup_env.sh                       # Keep as-is
├── .gitignore                         # Keep as-is (add *.ts, *.rtf?)
│
├── deprecated/                        # Already exists — expand for all old/experimental files
│   ├── README.md                      # [NEW] Short header explaining what's here
│   ├── dvbs2_tx.grc                   # (existing)
│   ├── dvbs2_tx.py                    # (existing)
│   ├── soapy-tx.py                    # (existing)
│   ├── videorx_example.grc            # (existing)
│   ├── videotx_example.grc            # (existing)
│   ├── dvbs2-rx-mod                   # ← moved from rf-link/
│   ├── dvbs2-tx-mod                   # ← moved from rf-link/
│   ├── gr-dvbs2rx/                    # ← moved from rf-link/
│   ├── dtv-utils-master/              # ← moved from rf-link/
│   ├── hackrf-2024.02.1-fw.zip        # ← moved from rf-link/
│   └── ...                            # (kept for historical reference only)
│
├── packet/                            # Main project — focused, navigable
│   ├── README.md                      # Keep — project overview + usage
│   ├── ALIGNMENT_PLAN.md             # Keep — feature roadmap
│   ├── HELLO_TX_RX.md                # Keep — historical reference
│   │
│   ├── src/                          # [NEW] Core library code
│   │   ├── __init__.py               # [NEW] Makes this a proper Python package
│   │   ├── fec_cc.py                 # ← moved from packet/
│   │   ├── packet_codec.py           # ← moved from packet/
│   │   ├── pkt_enhanced_tx.py        # ← moved from packet/
│   │   └── pkt_enhanced_rx.py        # ← moved from packet/
│   │
│   ├── test/                         # Keep — already well-structured
│   │   ├── README.md                 # Keep
│   │   ├── test_all.py               # Keep
│   │   ├── test_layer1.py            # Keep
│   │   ├── test_layer2.py            # Keep
│   │   └── test_layer3.py            # Keep
│   │
│   ├── grc/                          # Keep — GRC flowgraph reference files
│   │   ├── packet_custom_rx.grc
│   │   ├── packet_custom_tx.grc
│   │   ├── packet_loopback_hier.grc
│   │   ├── packet_rx.grc
│   │   └── packet_tx.grc
│   │
│   ├── debug/                        # [NEW] Development / debugging tools
│   │   └── (moved from debug_packet_rxtx/)
│   │       ├── burst_to_stream.py
│   │       ├── packet_gap_filler.py
│   │       ├── packet_loopback_hier.py
│   │       ├── packet_rx.py
│   │       ├── packet_tx.py
│   │       ├── padding_packing_crc_block.py
│   │       ├── padding_packing_crc_block.block.yml
│   │       ├── padding_packing_crc.md
│   │       ├── padding_packing_crc_block_setup.md
│   │       └── packet_chain_analysis.md
│   │
│   └── archive/                     # [NEW] Deprecated/development scripts (keep for reference)
│       ├── README.md                # Header: "Historical scripts — not in active use"
│       ├── grc-blocks/              # Original GRC-generated hierarchical blocks
│       │   ├── packet_tx.py
│       │   ├── packet_rx.py
│       │   ├── telemetry_tx.py
│       │   └── telemetry_rx.py
│       ├── hello-world/             # Original (unprotected) BPSK hello chain
│       │   ├── pkt_hello_tx.py
│       │   ├── pkt_hello_rx.py
│       │   ├── pkt_rx_final.py
│       │   ├── hello_decoder.py
│       │   └── decode_precise.py
│       ├── experimental-rx/         # Offline decode iterations
│       │   ├── decode_complex.py
│       │   ├── decode_offline.py
│       │   ├── decode_offline_v2.py
│       │   ├── final_decode.py
│       │   └── simple_bpsk_rx.py
│       ├── gr-rx/                   # GRC-based / native GNU Radio RX scripts
│       │   ├── bpsk_gr_rx.py
│       │   ├── gr_live_rx.py
│       │   ├── native_gr_rx.py
│       │   └── minimal_rx.py
│       ├── gr-tx/                   # GRC-based / minimal TX scripts
│       │   ├── hybrid_tx.py
│       │   └── minimal_tx.py
│       └── experiments/             # One-off test scripts
│           ├── test_demux_loopback.py
│           └── test_sps4.py
```

---

## 3. Rationale for Grouping Decisions

### `src/` — Core Library (importable package)

- **Why a package**: The test files (`test/`) already `import from packet_codec`, `from pkt_enhanced_tx`, etc. Making `src/` a proper package (`__init__.py`) lets imports like `from packet.src import fec_cc` work cleanly.
- **Why only 5 files here**: Only `fec_cc.py`, `packet_codec.py`, `pkt_enhanced_tx.py`, `pkt_enhanced_rx.py` form the active, maintained codebase. Everything else is either a test or historical.

### `test/` — Test Suite (keep in place, already well-organized)

- Already properly structured with layer-per-file and a test harness. No changes needed except updating import paths.

### `grc/` — GNU Radio Companion Flowgraphs (keep in place)

- These `.grc` files are design artifacts, not runtime code. They belong in their own directory, which they already have.

### `debug/` — Development/Investigation Tools (rename + consolidate)

- `debug_packet_rxtx/` contains genuinely useful debug tools (burst-to-stream gap filler, padding analysis, loopback hier block). These are *development* tools, not production code, but they're actively useful during development. Renaming to `debug/` is cleaner.

### `archive/` — Historical Reference Only

- These files document the project's evolution but are not actively maintained or run. Grouped by theme (GRC blocks, hello-world, experimental RX, etc.) to make the history navigable.
- Having an `archive/` directory (rather than deleting) means:
  - No permanent data loss
  - Easy to reference old behavior during debugging
  - Can be fully removed later with confidence if the project stabilizes

### What Stays at Root Level in `packet/`

- `README.md` — Must be immediately discoverable
- `ALIGNMENT_PLAN.md` — Feature roadmap, high-visibility reference
- `HELLO_TX_RX.md` — Mentioned by README, reference material

### What Gets Removed Entirely

- `backup/` — Content is fully duplicated in `grc/` and `debug/`
- `pkt_enhanced_tx_backup.py` — Trivial diff, not worth preserving
- `__pycache__/` — `.gitignore` typically covers this

---

## 4. Import Path Impact

This is the most important migration concern. Currently:

| File | Current Import | New Import |
|------|---------------|------------|
| `packet_codec.py` | `from fec_cc import ...` | `from packet.src.fec_cc import ...` |
| `pkt_enhanced_tx.py` | `from packet_codec import ...` | `from packet.src.packet_codec import ...` |
| `pkt_enhanced_rx.py` | `from packet_codec import ...` | `from packet.src.packet_codec import ...` |
| `test/test_layer1.py` | `from packet_codec import ...` | `from packet.src.packet_codec import ...` |
| `test/test_layer2.py` | `from pkt_enhanced_tx import ...` | `from packet.src.pkt_enhanced_tx import ...` |
| `test/test_layer2.py` | `from pkt_enhanced_rx import ...` | `from packet.src.pkt_enhanced_rx import ...` |
| `test/test_layer3.py` | `from pkt_enhanced_tx import ...` | `from packet.src.pkt_enhanced_tx import ...` |
| `test/test_layer3.py` | `from pkt_enhanced_rx import ...` | `from packet.src.pkt_enhanced_rx import ...` |
| `test_demux_loopback.py` | `from packet_codec/pkt_enhanced_tx/pkt_enhanced_rx` | will be archived, no change needed |
| `test_sps4.py` | `importlib.util.spec_from_file_location(...)` | will be archived, no change needed |

**Mitigation**: Use relative imports within the package (`from .fec_cc import ...`) for files inside `src/`. For test files, either add `src/` to `sys.path` or use `PYTHONPATH=src/` in the test runner.  The simplest approach: update test harness to `sys.path.insert(0, os.path.join(HERE, '..', 'src'))` and keep imports as `from packet_codec import ...`.

---

## 5. Migration Steps (Single Git Commit)

### Step 1: Parent-level cleanup (`rf-link/`)

```bash
cd rf-link

# Move unrelated files to deprecated/
mv dvbs2-rx-mod dvbs2-tx-mod deprecated/
mv gr-dvbs2rx/ dtv-utils-master/ deprecated/
mv hackrf-2024.02.1-fw.zip deprecated/

# Delete TS files and orphaned RTF
rm output.ts thefuryclip.ts Untitled.rtf
```

### Step 2: Create new directory structure (inside `packet/`)

```bash
cd packet

# Create target directories
mkdir -p src debug archive/grc-blocks archive/hello-world \
         archive/experimental-rx archive/gr-rx archive/gr-tx archive/experiments

# Create __init__.py for src package
touch src/__init__.py
```

### Step 3: Move core files into `src/`

```bash
mv fec_cc.py packet_codec.py pkt_enhanced_tx.py pkt_enhanced_rx.py src/
```

### Step 4: Rename `debug_packet_rxtx/` → `debug/`

```bash
mv debug_packet_rxtx debug
```

### Step 5: Move deprecated files into `archive/`

```bash
# GRC-generated hierarchical blocks
mv packet_tx.py packet_rx.py archive/grc-blocks/
mv telemetry_tx.py telemetry_rx.py archive/grc-blocks/

# Hello-world chain
mv pkt_hello_tx.py pkt_hello_rx.py pkt_rx_final.py archive/hello-world/
mv hello_decoder.py decode_precise.py archive/hello-world/

# Experimental decoders
mv decode_complex.py decode_offline.py decode_offline_v2.py archive/experimental-rx/
mv final_decode.py simple_bpsk_rx.py archive/experimental-rx/

# GRC-based RX scripts
mv bpsk_gr_rx.py gr_live_rx.py native_gr_rx.py minimal_rx.py archive/gr-rx/

# GRC-based TX scripts
mv hybrid_tx.py minimal_tx.py archive/gr-tx/

# One-off test scripts
mv test_demux_loopback.py test_sps4.py archive/experiments/
```

### Step 6: Remove redundant files

```bash
rm -rf backup/ .pytest_cache/ __pycache__/
rm pkt_enhanced_tx_backup.py
```

### Step 7: Update imports

Apply changes to all affected files:

1. `src/fec_cc.py` — no import changes needed (no local imports)
2. `src/packet_codec.py` — change `from fec_cc import ...` → `from .fec_cc import ...`
3. `src/pkt_enhanced_tx.py` — change `from packet_codec import ...` → `from .packet_codec import ...`
4. `src/pkt_enhanced_rx.py` — change `from packet_codec import ...` → `from .packet_codec import ...`
5. `test/test_all.py` — add `sys.path.insert(0, os.path.join(HERE, '..', 'src'))`
6. `test/test_layer1.py` — unchanged (uses `sys.path.insert(0, '.')` → change to `..` or rely on test_all.py)
7. `test/test_layer2.py` — same as layer1
8. `test/test_layer3.py` — same as layer1

### Step 8: Create archive README

Write an `archive/README.md` explaining the contents.

### Step 9: Update top-level README

Update `packet/README.md` to reflect the new structure.

### Step 10: Verify

```bash
cd packet && python3 -m pytest test/ -v
# Or
cd packet && python3 test/test_all.py --layer 1 --layer 2
```

---

## 6. Risks and Gotchas

### 🚨 Circular imports
None expected — the dependency chain is strictly linear:
`fec_cc ← packet_codec ← {pkt_enhanced_tx, pkt_enhanced_rx}`

### 🚨 Relative imports in `src/` block direct script execution
`python3 src/pkt_enhanced_tx.py` will fail with `ImportError: attempted relative import with no known parent package`.  Mitigation: either use `python3 -m src.pkt_enhanced_tx` from the `packet/` directory, or use `PYTHONPATH=. python3 src/pkt_enhanced_tx.py`.  Document this in README.

### 🚨 Test import paths
The test files currently do `import sys; sys.path.insert(0, '.')` which finds files in the current directory.  After the move, tests need `sys.path.insert(0, '../src')` (or the test harness updates `PYTHONPATH`).  The simplest fix: update `test_all.py` to set `sys.path.insert(0, os.path.join(HERE, '..', 'src'))` before running individual tests, so individual layer scripts can keep their relative imports.

### 🚨 `pkt_enhanced_rx.py` imports from `gnuradio.filter import firdes`
This is a system-level import (not local), so it's unaffected by the restructure.

### 🚨 Archive scripts may reference removed neighbors
E.g., `telemetry_tx.py` does `from packet_tx import packet_tx` — both are now in `archive/grc-blocks/` so they can still find each other.  But `telemetry_tx.py` also references `fec_cc.py` in a comment — no runtime issue.

### 🚨 `test_sps4.py` uses `importlib.util.spec_from_file_location`
This script constructs paths relative to `__file__`.  Moving it to `archive/experiments/` will break its path resolution.  Since this is archived, that's acceptable.

### 🚨 Single-commit discipline
This plan is designed for one atomic git commit.  All moves and import updates must happen together.  The commit author should be aware that `git mv` preserves history better than `mv` (so `git mv fec_cc.py src/` instead of shell `mv`), but the plan above uses shell `mv` for clarity.

---

## 7. Before/After Tree Summary

### Before (flat, 38 items in `packet/` + 7+ clutter items in `rf-link/`)

```
rf-link/
├── dvbs2-rx-mod, dvbs2-tx-mod, gr-dvbs2rx/,
│   dtv-utils-master/, hackrf-2024.02.1-fw.zip,
│   output.ts, thefuryclip.ts, Untitled.rtf
│
├── packet/
│   ├── fec_cc.py, packet_codec.py
│   ├── pkt_enhanced_tx.py, pkt_enhanced_rx.py
│   ├── packet_tx.py, packet_rx.py (GRC blocks)
│   ├── telemetry_tx.py, telemetry_rx.py
│   ├── pkt_hello_tx.py, pkt_hello_rx.py, ...
│   ├── decode_*.py, final_decode.py
│   ├── bpsk_gr_rx.py, gr_live_rx.py, ...
│   ├── hybrid_tx.py, minimal_*.py
│   ├── test_demux_loopback.py, test_sps4.py
│   ├── pkt_enhanced_tx_backup.py
│   ├── backup/, debug_packet_rxtx/, grc/, test/
│   ├── ALIGNMENT_PLAN.md, HELLO_TX_RX.md, README.md
│   └── __pycache__/, .pytest_cache/
```

### After (navigable 6-directory structure)

```
rf-link/
├── deprecated/
│   ├── dvbs2-rx-mod, dvbs2-tx-mod
│   ├── gr-dvbs2rx/, dtv-utils-master/
│   ├── hackrf-2024.02.1-fw.zip
│   └── (existing dvbs2_tx.grc etc.)
│
├── packet/
│   ├── README.md
│   ├── ALIGNMENT_PLAN.md
│   ├── HELLO_TX_RX.md
│   ├── src/            (5 files: core library)
│   ├── test/           (5 files: test pipeline)
│   ├── grc/            (5 files: GRC flowgraphs)
│   ├── debug/          (10 files: dev/investigation tools)
│   └── archive/        (18 files in 6 subdirs: historical reference)
│       ├── grc-blocks/   (packet_tx.py, packet_rx.py, telemetry_tx/rx.py)
│       ├── hello-world/  (pkt_hello_tx/rx.py, pkt_rx_final.py, etc.)
│       ├── experimental-rx/ (decode_*.py, final_decode.py)
│       ├── gr-rx/         (bpsk_gr_rx.py, gr_live_rx.py, etc.)
│       ├── gr-tx/         (hybrid_tx.py, minimal_tx.py)
│       └── experiments/   (test_demux_loopback.py, test_sps4.py)
```

**Root-level file count**: ~38 → ~8 visible items (+ archive/ sub-items)
**Clutter at parent level**: 7+ items → all in `deprecated/` or deleted
