# Settings & Configuration — Design Spec

## Overview

The settings view is a separate configuration area for pre-flight RX hardware setup. It is not part of the mission control live view — the operator navigates here via the left sidebar (⚙ gear or 📡 antenna icons), configures everything before the flight, then returns to the mission control view for launch operations.

The settings view replaces the three-panel mission control body with a full-width configuration layout. The top bar, left sidebar, and bottom bar remain visible for continuity.

## Layout

```
┌──┬──────────────────────────────────────────────────────┐
│64│  72px TOP BAR (mission info, same as main view)      │
│px├──────────────────────────────────────────────────────┤
│le│  SETTINGS ⚙                                      [×] │
│ft│  ┌──────┬──────┬──────┬──────┬──────┐               │
│si│  │Device│  RF  │DVB-S2│Pipeln│About │               │
│de│  └──────┴──────┴──────┴──────┴──────┘               │
│ba│                                                      │
│r │  ┌─────────────────────┐  ┌──────────────────────┐  │
│  │  │ DEVICE DISCOVERY    │  │ RF PARAMETERS        │  │
│  │  │                     │  │                      │  │
│  │  │ HackRF #0           │  │ Freq: [915.000] MHz  │  │
│  │  │ ...60661  [Connect] │  │ Sym Rt: [1.000] Msps │  │
│  │  │                     │  │ LO ppm: [0        ]  │  │
│  │  │ HackRF #1           │  │                      │  │
│  │  │ ...67464  [Connect] │  │ LNA: ████░░░ 16 dB  │  │
│  │  │                     │  │ VGA: ██████░ 20 dB  │  │
│  │  │ [Refresh]           │  │ AMP: [ENABLE] +14dB │  │
│  │  └─────────────────────┘  │                      │  │
│  │                           │ [Apply Parameters]   │  │
│  │                           └──────────────────────┘  │
│  │                                                      │
│  │  ┌──────────────────────────────────────────────┐   │
│  │  │ CONNECTION LOG                                │   │
│  │  │ 14:10:01 Device HackRF #...67464 connected    │   │
│  │  │ 14:10:03 Frequency set: 915.000 MHz          │   │
│  │  │ 14:10:04 Sample rate set: 2.000 Msps         │   │
│  │  │ 14:10:05 LNA gain: 16 dB                     │   │
│  │  │ 14:10:05 VGA gain: 20 dB                     │   │
│  │  └──────────────────────────────────────────────┘   │
│  ├──────────────────────────────────────────────────────┤
│  │  ~200px PACKET STREAM (same as main view)            │
└──┴──────────────────────────────────────────────────────┘
```

### Navigation

- **⚙ Settings** sidebar icon → opens settings view, defaults to "Device" tab
- **📡 RF Config** sidebar icon → opens settings view, defaults to "RF Parameters" tab
- **× Close** button in top-right of settings header returns to mission control view
- Back navigation also available by clicking the active (blue) mission control icon in sidebar

### Sub-tabs

Rendered as a horizontal row of pill-shaped tabs below the settings header. Uses the same style as the main view — Gunmetal `#252B2F` background, active tab in Telemetry Blue `#2F80ED`.

| Tab | Icon | Content |
|-----|------|---------|
| Device | USB plug | HackRF device discovery and connection |
| RF | Sliders | Frequency, sample rate, gains, LO correction |
| DVB-S2 | Satellite dish | MODCOD, pilots, rolloff, FEC frame, symbol rate, SPS, RRC delay, gold code, fullscale, sink type, device args |
| Pipeline | Film | MP4 file source, ffmpeg + tsp pipeline controls, debug output |
| About | Info | Device info readout, HackRF device list, version |

---

## Tab 1: Device Discovery

### Layout

Two side-by-side cards in a 2-column grid.

#### Left Card — Device List

```
┌──────────────────────────────┐
│ DEVICE DISCOVERY             │
│                              │
│ ┌────────────────────────┐   │
│ │ ● HackRF One           │   │
│ │   Serial: ...60661     │   │
│ │   Firmware: 2024.02.1  │   │
│ │              [Connect] │   │
│ ├────────────────────────┤   │
│ │ ○ HackRF One           │   │
│ │   Serial: ...67464     │   │
│ │   Firmware: 2024.02.1  │   │
│ │              [Connect] │   │
│ └────────────────────────┘   │
│                              │
│ [Refresh Devices]            │
└──────────────────────────────┘
```

- Card: `var(--surface-card)`, 20px radius, 24px padding
- Header: "DEVICE DISCOVERY" in h2, `var(--text-secondary)`
- Device rows: each row is a compound row with:
  - Left: colored dot (green = connected, gray = available), device name in body `var(--text-primary)`, serial in mono-data `var(--text-muted)`, firmware version in small `var(--text-muted)`
  - Right: Connect/Disconnect button in Telemetry Blue primary or Reentry Red for disconnect
  - Rows alternate between `var(--surface-card)` and `var(--bg-frame)` subtle striping
  - 2px `var(--border)` separators between rows
- Refresh button: Ghost style, bottom of card, with refresh icon

#### Right Card — Connected Device Info

```
┌──────────────────────────────┐
│ CONNECTED DEVICE             │
│                              │
│ ● Connected                  │
│   HackRF One                 │
│   Serial: ...67464           │
│                              │
│ ──────────────────────────── │
│                              │
│ Frequency     915.000 MHz    │
│ Sample Rate     2.000 Msps   │
│ LNA Gain         16 dB       │
│ VGA Gain         20 dB       │
│ AMP            Disabled      │
│ TX Active       No           │
│                              │
│ [Disconnect]                 │
└──────────────────────────────┘
```

- Card: `var(--surface-card)`, 20px radius, 24px padding
- Header: "CONNECTED DEVICE" in h2, `var(--text-secondary)`
- Top: green dot "Connected" in small `var(--success)`, device name in body, serial in mono-data
- Divider
- Current parameters readout in compact rows: label in small `var(--text-muted)`, value in mono-data `var(--text-primary)`
- Disconnect button: Reentry Red secondary style

### Behavior

- Device discovery happens via HackRF/SoapySDR enumeration
- "No devices found" empty state with USB icon and "Connect a HackRF device" message in `var(--text-disabled)`
- Connecting assigns the device as the RX source for all reception
- Disconnecting stops all active RX/TX flows and releases the device

---

## Tab 2: RF Parameters

### Layout

```
┌──────────────────────────────────────────────┐
│ RF PARAMETERS                                │
│                                              │
│  Frequency                                   │
│  ┌────────────────────────┐  MHz            │
│  │ 915.000                │                 │
│  └────────────────────────┘                 │
│                                              │
│  Symbol Rate                                 │
│  ┌────────────────────────┐  Msps           │
│  │ 1.000                  │                 │
│  └────────────────────────┘                 │
│                                              │
│  LO PPM Correction                           │
│  ┌────────────────────────┐  ppm            │
│  │ 0                      │                 │
│  └────────────────────────┘                 │
│                                              │
│  LNA Gain                      16 dB         │
│  ●═══════════○════════════════○  [0 — 40]    │
│                                              │
│  VGA Gain                      20 dB         │
│  ●════════════════○═══════════○  [0 — 62]    │
│                                              │
│  AMP Enable                                 │
│  [ENABLED]  [DISABLED]  +14 dB when active  │
│                                              │
│  ──────────────────────────────────────────  │
│                                              │
│  [Apply Parameters]  [Reset]  [Reset All]   │
└──────────────────────────────────────────────┘
```

### Fields

| Field | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| Frequency | Number input | 915.000 | Any valid HackRF freq (1 MHz – 6 GHz) | Center frequency in MHz |
| Symbol Rate | Number input | 1.000 | 0.1 – 20.0 | Modulation symbol rate in Msps |
| LO PPM | Number input | 0 | -100 – 100 | Crystal frequency correction |
| LNA Gain | Range slider | 16 | 0 – 40 dB, step 8 | Low-noise amplifier gain |
| VGA Gain | Range slider | 20 | 0 – 62 dB, step 1 | Variable gain amplifier |
| AMP Enable | Toggle | Disabled | On/Off | +14 dB transmit amplifier boost |

### Input Styling

- Text inputs: `var(--surface-raised)` background, 1px `var(--border)` border, 14px radius, Signal White text, mono font
- Focus state: `var(--accent)` border + `0 0 0 3px rgba(47,128,237,0.18)` glow
- Unit labels to the right of each input, mono-data, `var(--text-muted)`
- Range sliders: track in `var(--surface-control)`, filled portion in `var(--accent)`, thumb in Signal White circle with `var(--accent)` border
- Live value readout next to slider label in telemetry-medium
- AMP toggle: segmented pill control. Active state in `var(--accent)` with white text, inactive in `var(--surface-control)` with `var(--text-secondary)` text

### Buttons

- **Apply Parameters:** Primary button, Telemetry Blue `var(--accent)` bg, Signal White text, rounded pill, 24px horizontal padding
- **Reset:** Ghost button, reverts to last-applied values
- **Reset All:** Ghost button with Reentry Red hover, resets all fields to defaults

### Behavior

- Parameters are NOT applied until "Apply Parameters" is clicked
- On apply: validates ranges, sends config to engine via WebSocket + HTTP POST `/api/config`
- Success: brief green flash on the apply button (300ms) then reverts
- Error: red flash on the apply button + inline error message below the problematic field
- Frequency change while actively receiving restarts the RX flowgraph
- Parameters persist in localStorage between sessions

---

## Tab 3: DVB-S2 Configuration

### Layout

2-column grid of configuration controls.

```
┌──────────────────────────────────────────────────────┐
│ DVB-S2 CONFIGURATION                                 │
│                                                      │
│  ┌───────────────────┐  ┌─────────────────────────┐  │
│  │ MODCOD            │  │ Pilots                  │  │
│  │ ┌───────────────┐ │  │ ┌──────┐ ┌──────┐      │  │
│  │ │ QPSK 1/2   ▼ │ │  │ │  ON  │ │ OFF  │      │  │
│  │ └───────────────┘ │  │ └──────┘ └──────┘      │  │
│  └───────────────────┘  └─────────────────────────┘  │
│                                                      │
│  ┌───────────────────┐  ┌─────────────────────────┐  │
│  │ Rolloff           │  │ FEC Frame               │  │
│  │ ┌───────────────┐ │  │ ┌────────┐ ┌────────┐  │  │
│  │ │ 0.35       ▼ │ │  │ │ NORMAL │ │ SHORT  │  │  │
│  │ └───────────────┘ │  │ └────────┘ └────────┘  │  │
│  └───────────────────┘  └─────────────────────────┘  │
│                                                      │
│  ┌───────────────────┐  ┌─────────────────────────┐  │
│  │ Symbol Rate       │  │ SPS                     │  │
│  │ ┌───────────────┐ │  │ ┌─────────────────┐    │  │
│  │ │ 1.000e6     │ │  │ │ 20            │    │  │
│  │ └───────────────┘ │  │ └─────────────────┘    │  │
│  └───────────────────┘  └─────────────────────────┘  │
│                                                      │
│  ┌───────────────────┐  ┌─────────────────────────┐  │
│  │ RRC Delay         │  │ Gold Code               │  │
│  │ ┌───────────────┐ │  │ ┌─────────────────┐    │  │
│  │ │ 0            │ │  │ │ 0              │    │  │
│  │ └───────────────┘ │  │ └─────────────────┘    │  │
│  └───────────────────┘  └─────────────────────────┘  │
│                                                      │
│  ┌───────────────────┐  ┌─────────────────────────┐  │
│  │ Fullscale         │  │ Sink Type               │  │
│  │ ┌───────────────┐ │  │ ┌─────────────────┐    │  │
│  │ │ 1.0          │ │  │ │ HackRF       ▼ │    │  │
│  │ └───────────────┘ │  │ └─────────────────┘    │  │
│  └───────────────────┘  └─────────────────────────┘  │
│                                                      │
│  Device Args                                         │
│  ┌────────────────────────────────────────────────┐  │
│  │ driver=hackrf,serial=...67464                  │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  [Apply DVB-S2 Config]                               │
└──────────────────────────────────────────────────────┘
```

### Fields

| Field | Type | Options/Default | Description |
|-------|------|-----------------|-------------|
| MODCOD | Dropdown | QPSK 1/4, QPSK 1/3, QPSK 2/5, QPSK 1/2, QPSK 3/5, QPSK 2/3, QPSK 3/4, QPSK 4/5, QPSK 5/6, QPSK 8/9, QPSK 9/10, 8PSK 3/5, 8PSK 2/3, 8PSK 3/4, 8PSK 5/6, 8PSK 8/9, 8PSK 9/10 | Modulation + coding rate |
| Pilots | Toggle | ON / OFF | DVB-S2 pilot symbols |
| Rolloff | Dropdown | 0.20 / 0.25 / 0.35 | RRC filter roll-off factor |
| FEC Frame | Toggle | NORMAL / SHORT | FEC frame size (64800 / 16200 bits) |
| Symbol Rate | Number input | Default 1.0e6 | Symbols per second |
| SPS | Number input | Default 20 | Samples per symbol |
| RRC Delay | Number input | Default 0 | RRC filter delay taps |
| Gold Code | Number input | Default 0 | Physical layer scrambling sequence |
| Fullscale | Number input | Default 1.0 | Output amplitude scaling |
| Sink Type | Dropdown | HackRF / USRP / bladeRF / PlutoSDR / File | SDR output device |
| Device Args | Text input | driver=hackrf | SoapySDR device arguments string |

### Dropdown Styling

- `var(--surface-raised)` background
- 1px `var(--border)` border
- Rounded 14px
- Signal White text, body size
- Custom chevron icon on right, `var(--text-muted)`
- Open state: `var(--border-strong)` border
- Options: `var(--surface-raised)` background, individually highlighted on hover

### Toggle Styling

- Segmented control: two side-by-side pills joined at the center
- Active: `var(--accent)` bg, Signal White text
- Inactive: `var(--surface-control)` bg, `var(--text-secondary)` text

### Apply Button

- Primary Telemetry Blue, centered below the 2-column grid
- On success: brief green pulse, "Config applied" text appears for 3 seconds in `var(--success)`
- On error: red pulse, error message in `var(--critical)`
- Config persists to localStorage

---

## Tab 4: Pipeline

### Layout

```
┌──────────────────────────────────────────────────────┐
│ PIPELINE                                             │
│                                                      │
│  Input File                                          │
│  ┌──────────────────────────────────────┐ [Browse]  │
│  │ /path/to/video.mp4                   │           │
│  └──────────────────────────────────────┘           │
│                                                      │
│  [▶ Start Pipeline]  [■ Stop Pipeline]              │
│                                                      │
│  ──────────────────────────────────────────────────  │
│  Pipeline Status                                     │
│                                                      │
│  Status      ● Running                               │
│  File        video.mp4                               │
│  Bitrate     965,326 bps                             │
│  Duration    00:47:32                                │
│  Errors      0                                       │
│                                                      │
│  ──────────────────────────────────────────────────  │
│                                                      │
│  ┌─────────────────────┐  ┌──────────────────────┐  │
│  │ ffmpeg output        │  │ tsp output           │  │
│  │                      │  │                      │  │
│  │ [ffmpeg] stream 0:  │  │ [tsp] input bitrate  │  │
│  │ video: h264, yuv420p│  │ 965,326 bps          │  │
│  │ 1920x1080, 30 fps   │  │ [tsp] output bitrate │  │
│  │ [ffmpeg] stream 1:  │  │ 965,326 bps          │  │
│  │ audio: mp2, 48000Hz │  │ [tsp] rate regulating│  │
│  │ stereo, 128 kb/s    │  │ ...                  │  │
│  │ [ffmpeg] frame=2842 │  │                      │  │
│  │ fps=30.0 q=28.0     │  │                      │  │
│  │ ...                 │  │                      │  │
│  │                 [✕] │  │                  [✕] │  │
│  └─────────────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### File Browser

- Disabled text input showing selected file path, `var(--surface-raised)` bg, mono font
- "Browse" button: Ghost style, opens OS file picker for `.mp4` files
- Placeholder when empty: "Select an MP4 video file..." in `var(--text-muted)`

### Pipeline Controls

- **Start Pipeline:** Primary Telemetry Blue button. Starts ffmpeg → UDP → tsp → FIFO chain.
- **Stop Pipeline:** Secondary button (Gunmetal). Only enabled when pipeline is running.
- Status indicator between buttons: colored dot + state text (Running = `var(--success)`, Stopped = `var(--text-disabled)`, Error = `var(--critical)`)

### Status Readout

Compact labeled rows:
- Label in small `var(--text-muted)`, value in body `var(--text-primary)`
- Bitrate, duration, and error count use mono-data
- Updates live at 2 Hz via WebSocket

### Debug Terminals

Two side-by-side scrolling terminals:

| Terminal | Source | Text Color | Max Lines |
|----------|--------|------------|-----------|
| ffmpeg | ffmpeg stderr | `var(--success)` (#4DAA78) | 500 |
| tsp | tsp stdout | `var(--text-secondary)` | 500 |

- Background: `var(--bg-frame)` or `#000000`
- Font: `var(--font-mono)`, 12px
- Auto-scroll to bottom when new output arrives
- Clear button [✕] in top-right of each terminal
- Line count displayed below terminal ("142 lines")
- If pipeline not running: terminals show "Pipeline not running" in `var(--text-disabled)`, centered

### Layout Notes

- File browser row at top
- Pipeline status + controls next
- Debug terminals at bottom, equal height (~300px), with a 16px gap between them

---

## Tab 5: About

### Layout

```
┌──────────────────────────────────────────────────────┐
│ ABOUT                                                │
│                                                      │
│  ┌──────────────────────┐  ┌──────────────────────┐  │
│  │ SYSTEM STATUS        │  │ HACKRF DEVICES       │  │
│  │                      │  │                      │  │
│  │ Connected    ● Yes   │  │ HackRF ...60661     │  │
│  │ Serial       ...67464│  │   Firmware 2024.02.1│  │
│  │ Frequency    915 MHz │  │ HackRF ...67464     │  │
│  │ Symbol Rate  1.0 Msps│  │   Firmware 2024.02.1│  │
│  │ TX Active    No      │  │                      │  │
│  │ Pipeline     Stopped │  │ Last refresh: 12s ago│  │
│  │ Uptime       03:14:22│  │                      │  │
│  │ WebSocket    ● Conn  │  │ [Refresh]           │  │
│  │ Errors       0       │  │                      │  │
│  └──────────────────────┘  └──────────────────────┘  │
│                                                      │
│  ──────────────────────────────────────────────────  │
│                                                      │
│  STRATOS v0.5-dev                                    │
│  HAB Ground Station                                  │
│  Mission Control Dashboard                            │
│                                                      │
│  Build: 2026-05-19                                   │
│  Engine: hab-engine 0.5.0                            │
│  GNU Radio: 3.10.x                                   │
│  SoapySDR: 0.8.x                                     │
└──────────────────────────────────────────────────────┘
```

### System Status Card

Read-only info rows:
- Label in small `var(--text-muted)`, value in body `var(--text-primary)`
- Boolean values shown as colored dots (green = yes/connected, gray = no/stopped)
- Values update live from engine status at 2 Hz

### HackRF Devices Card

- Lists all detected HackRF devices with serial and firmware version
- Auto-refreshes every 30 seconds
- Manual "Refresh" button
- "Last refresh: Xs ago" counter in small `var(--text-muted)`
- Empty state: "No HackRF devices detected" with USB icon

### Version Footer

- App name + version in h2
- Build date, engine version, dependency versions in small `var(--text-muted)`
- Separated from cards by a hairline divider

---

## Connection Log (shared across all tabs)

A horizontal card spanning the full settings area width, positioned below the tab content.

```
┌──────────────────────────────────────────────────────┐
│ CONNECTION LOG                           [All ▼] [✕] │
│ ────────────────────────────────────────────────────  │
│ ● 14:10:01  Device HackRF #...67464 connected        │
│ ● 14:10:03  Frequency set: 915.000 MHz               │
│ ● 14:10:04  Sample rate set: 2.000 Msps              │
│ ● 14:10:05  LNA gain set: 16 dB                      │
│ ● 14:10:05  VGA gain set: 20 dB                      │
│ ● 14:12:30  Pipeline started: video.mp4              │
│ ● 14:12:31  TX started at 915.000 MHz                │
│ ● 14:13:45  WebSocket disconnected (retrying...)     │
│ ● 14:13:48  WebSocket reconnected                    │
└──────────────────────────────────────────────────────┘
```

- Card: `var(--surface-card)`, 20px radius, 24px padding, max-height 150px with internal scroll
- Header: "CONNECTION LOG" in h2 + filter dropdown (All / Info / Errors) + clear button
- Each row: colored type dot + mono timestamp + message in body text
- Dot colors: green = success/connect, blue = info/config change, amber = warning, red = error/disconnect
- Max 500 entries, oldest evicted first
- Auto-scroll to bottom

---

## Behavior & State Management

### Navigation Between Tabs

- Tab state persists within a settings session (switching tabs doesn't reset state)
- Leaving settings (returning to mission control) does NOT stop any running pipeline or TX — those continue in background
- Returning to settings resumes where you left off (last active tab remembered)

### Configuration Persistence

All settings persist to `localStorage` keyed by category:
- `hab_rf_config`: Frequency, symbol rate, LO ppm, LNA gain, VGA gain, AMP state
- `hab_dvbs2_config`: MODCOD, pilots, rolloff, FEC frame, symbol rate, SPS, RRC delay, gold code, fullscale, sink type, device args
- `hab_pipeline_config`: Last file path

On page load, stored configs are loaded and applied to the UI. The operator must still click "Apply" to push to the engine.

### Validation

- Frequency: must be 1–6000 MHz, numeric. Error: "Frequency must be 1–6000 MHz"
- Symbol Rate: must be 0.1–20 Msps, numeric. Error: "Symbol rate must be 0.1–20 Msps"
- Gains: constrained by slider UI (no text input — slider only)
- MODCOD/rolloff/sink: constrained by dropdown (no free text)
- Invalid fields get red border + error message below in `var(--critical)` small text
- Apply button is disabled while any field has validation errors

### WebSocket Commands

Settings changes are sent to the engine via the existing WebSocket bridge at `ws://localhost:3000/ws`:

| Action | WS Command | HTTP Fallback |
|--------|-----------|---------------|
| Apply RF parameters | `set_frequency`, `set_gain` | POST `/api/config` |
| Apply DVB-S2 config | `set_modcod`, `set_pilots`, `set_rolloff`, `set_fec_frame`, `set_symbol_rate`, `set_sps`, `set_rrc_delay`, `set_gold_code`, `set_fullscale`, `set_sink_type`, `set_device_args` | POST `/api/config` |
| Apply pipeline config | `start_pipeline`, `stop_pipeline` | POST `/api/pipeline/config` |
| Refresh HackRF devices | — | GET `/api/hackrf` |
| Get pipeline logs | — | GET `/api/pipeline/logs` |

---

## Design Tokens (same as main dashboard)

Settings view uses the identical design system. No new tokens.

- Cards: `var(--surface-card)` bg, 20px radius, 1px `var(--border)` border, 24px padding, `var(--shadow-card)`
- Inputs: `var(--surface-raised)` bg, 14px radius, `var(--border)` border
- Active elements: `var(--accent)` — Telemetry Blue `#2F80ED`
- Errors/danger: `var(--critical)` — Reentry Red `#E05344`
- Success: `var(--success)` — Tracking Green `#4DAA78`
- Tab and pill controls: `var(--surface-control)` — Gunmetal `#252B2F`
- Text: `var(--text-primary)` Signal White, `var(--text-secondary)` Fog Gray, `var(--text-muted)` Dim Gray
- Fonts: Inter for UI, JetBrains Mono for values/inputs/logs
