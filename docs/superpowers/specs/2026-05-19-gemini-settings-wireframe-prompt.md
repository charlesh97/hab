You are a UI designer building an HTML/CSS wireframe for the settings and
configuration page of a high-altitude balloon (HAB) mission control dashboard.
This is a dark, technical configuration interface for pre-flight hardware
setup. Produce a single HTML file.

===== CONTEXT =====

This is the configuration companion to the main mission control dashboard.
The mission control view shows live telemetry — this settings view is where
the operator configures the HackRF SDR receiver, DVB-S2 parameters, video
pipeline, and other pre-flight settings before launch.

The settings view has its own sub-tab navigation with 5 tabs:
Device, RF Parameters, DVB-S2, Pipeline, About.

===== DESIGN SYSTEM =====

Use these CSS variables exactly:

:root {
  --bg-app: #030505;
  --bg-frame: #080A0A;
  --surface-card: #111517;
  --surface-raised: #181D20;
  --surface-control: #252B2F;
  --surface-control-hover: #303840;
  --text-primary: #F4F6F7;
  --text-secondary: #A5AAAD;
  --text-muted: #6D7478;
  --text-disabled: #444A4E;
  --border: #242A2E;
  --border-strong: #343B41;
  --accent: #2F80ED;
  --accent-glow: #1C5FDB;
  --accent-soft: #10233F;
  --warning: #DCA83A;
  --critical: #E05344;
  --success: #4DAA78;
  --radius-frame: 32px;
  --radius-card: 20px;
  --radius-control: 14px;
  --radius-pill: 999px;
  --shadow-card: 0 18px 40px rgba(0, 0, 0, 0.28);
  --font-sans: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}

Typography:
- display: 34px Medium
- h1: 24px Semi-Bold
- h2: 18px Semi-Bold (card headers)
- h3: 16px Medium
- body: 14px Regular
- small: 12px Regular
- caption: 11px Medium
- telemetry-medium: 20px Medium
- mono-data: 13px Regular (inputs, log text)

Color semantics:
- Telemetry Blue (#2F80ED): active tabs, primary buttons, connected indicators
- Tracking Green (#4DAA78): success, connected, running
- Reentry Red (#E05344): errors, disconnect, stop, destructive actions
- Slate Chip (#2A3035): neutral pills, toggle backgrounds

===== LAYOUT =====

The settings page shares the same outer shell as the main dashboard:
- 64px left sidebar (same as main view)
- 72px top bar (mission info, same as main view)
- ~200px bottom bar (packet stream, same as main view)

Only the middle content area changes. Build a full-viewport layout:

┌──┬──────────────────────────────────────────────────────┐
│64│  TOP BAR (same as main view)                         │
│px├──────────────────────────────────────────────────────┤
│le│  SETTINGS                                      [×]   │
│ft│  ┌──────┬──────┬──────┬──────┬──────┐               │
│si│  │Device│  RF  │DVB-S2│Pipeln│About │               │
│de│  └──────┴──────┴──────┴──────┴──────┘               │
│ba│                                                      │
│r │  [TAB CONTENT — 2-column card layout]               │
│  │                                                      │
│  │  ┌──────────────────────────────────────────────┐   │
│  │  │ CONNECTION LOG                                │   │
│  │  │ ● 14:10:01 Device HackRF #...67464 connected  │   │
│  │  │ ● 14:10:03 Frequency set: 915.000 MHz        │   │
│  │  └──────────────────────────────────────────────┘   │
│  ├──────────────────────────────────────────────────────┤
│  │  PACKET STREAM (same as main view)                   │
└──┴──────────────────────────────────────────────────────┘

===== SETTINGS HEADER =====

- "SETTINGS" in h1, var(--text-primary), left-aligned
- [×] close button on the right: var(--surface-control) circle, var(--text-secondary) icon, returns to mission control view
- Below: horizontal row of 5 sub-tab pills

===== SUB-TABS =====

Horizontal row of pill-shaped tab buttons:
- Active tab: var(--accent) bg, var(--text-primary) text, no border
- Inactive tabs: var(--surface-control) bg, var(--text-secondary) text
- Hover on inactive: var(--surface-control-hover) bg
- Labels: "Device", "RF", "DVB-S2", "Pipeline", "About"
- Small icons to the left of each label (USB, sliders, satellite, film, info — Lucide SVG inline)
- 150ms background transition
- Show ALL tabs, with "Device" as the active tab by default

===== TAB 1: DEVICE =====

Two side-by-side cards.

**Left card — DEVICE DISCOVERY:**
- Header "DEVICE DISCOVERY" in h2 var(--text-secondary)
- List area with 2 device entries, each as a card-row:
  Row 1: "● HackRF One" (green dot + name in body var(--text-primary))
         "Serial: ...60661" in mono-data var(--text-muted) below
         "Firmware: 2024.02.1" in small var(--text-muted)
         [Connect] button on the right — var(--accent) pill, white text
  Row 2: Same layout with "○ HackRF One" (gray dot, not connected)
         Serial: ...67464
         [Connect] button
  Rows separated by 1px var(--border) line
- [Refresh Devices] ghost button at bottom of card — icon + text, var(--text-secondary)

**Right card — CONNECTED DEVICE:**
- Header "CONNECTED DEVICE" in h2 var(--text-secondary)
- Top area: "● Connected" in small var(--success), "HackRF One" in body, "Serial: ...67464" in mono-data
- Divider (1px var(--border))
- Parameter readout rows, compact:
  Label in small var(--text-muted), value in mono-data var(--text-primary):
  "Frequency     915.000 MHz"
  "Sample Rate     2.000 Msps"
  "LNA Gain          16 dB"
  "VGA Gain          20 dB"
  "AMP            Disabled"
  "TX Active          No"
- [Disconnect] button at bottom — var(--critical) bg, white text pill

===== TAB 2: RF PARAMETERS =====

**Note:** Only the Device tab content is visible by default. The other tabs (RF, DVB-S2, Pipeline, About) are hidden behind CSS. But include their HTML so a reviewer can see all tabs. Use a comment to indicate: "<!-- Tabs 2-5 are hidden by default, visible when their sub-tab is clicked -->"

Single full-width card.

- Header "RF PARAMETERS" in h2 var(--text-secondary)
- Form layout with labeled rows:

  Row: "Frequency" label in body var(--text-secondary)
       ┌──────────────────────┐
       │ 915.000              │  MHz
       └──────────────────────┘
       (Input: var(--surface-raised) bg, 14px radius, var(--border), mono-data white text, width ~300px)
       (Unit label "MHz" in mono-data var(--text-muted) beside input)

  Row: "Symbol Rate" label
       ┌──────────────────────┐
       │ 1.000                │  Msps
       └──────────────────────┘

  Row: "LO PPM Correction" label
       ┌──────────────────────┐
       │ 0                    │  ppm
       └──────────────────────┘

  Row: "LNA Gain" label                                    16 dB
       (custom range slider:
        - var(--surface-control) track, 6px height, rounded
        - var(--accent) filled track from 0 to current value
        - Signal White circle thumb, 16px diameter, var(--accent) border
        - Tick marks at 0, 8, 16, 24, 32, 40
        - Live value "16 dB" in telemetry-medium on the right
        - Label "[0 — 40]" in small var(--text-muted) below track)

  Row: "VGA Gain" label                                    20 dB
       (same slider style, range 0–62, tick marks every 10)
       (Live value "20 dB" in telemetry-medium)

  Row: "AMP Enable"
       Two side-by-side toggle pills:
       [ENABLED]  — inactive (var(--surface-control) bg, var(--text-secondary) text)
       [DISABLED] — active (var(--accent) bg, Signal White text)
       "+14 dB when active" in small var(--text-muted) beside the toggle

- Divider line (1px var(--border))

- Button row:
  [Apply Parameters] — Primary: var(--accent) bg, white text, pill, 24px padding
  [Reset] — Ghost: transparent, var(--text-secondary) text, pill, hover: var(--surface-control) bg
  [Reset All] — Ghost: same style

===== TAB 3: DVB-S2 =====

Single full-width card in a 2-column grid layout.

- Header "DVB-S2 CONFIGURATION" in h2 var(--text-secondary)
- 2-column CSS grid with 16px gap

  Column 1, Row 1: "MODCOD" label
       ┌────────────────────┐
       │ QPSK 1/2        ▼ │
       └────────────────────┘
       (Dropdown: var(--surface-raised) bg, 14px radius, var(--border), white text, custom ▼ chevron)

  Column 2, Row 1: "Pilots" label
       [  ON  ] [ OFF ]
       (Toggle: ON active in var(--accent), OFF inactive in var(--surface-control))

  Column 1, Row 2: "Rolloff" label
       ┌────────────────────┐
       │ 0.35            ▼ │
       └────────────────────┘

  Column 2, Row 2: "FEC Frame" label
       [ NORMAL ] [ SHORT ]
       (Toggle: NORMAL active in var(--accent), SHORT inactive)

  Column 1, Row 3: "Symbol Rate" label
       ┌────────────────────┐
       │ 1.000e6            │
       └────────────────────┘

  Column 2, Row 3: "SPS" label
       ┌────────────────────┐
       │ 20                 │
       └────────────────────┘

  Column 1, Row 4: "RRC Delay" label
       ┌────────────────────┐
       │ 0                  │
       └────────────────────┘

  Column 2, Row 4: "Gold Code" label
       ┌────────────────────┐
       │ 0                  │
       └────────────────────┘

  Column 1, Row 5: "Fullscale" label
       ┌────────────────────┐
       │ 1.0                │
       └────────────────────┘

  Column 2, Row 5: "Sink Type" label
       ┌────────────────────┐
       │ HackRF          ▼ │
       └────────────────────┘

- Below grid, full-width:
  "Device Args" label
  ┌──────────────────────────────────────────────────┐
  │ driver=hackrf,serial=...67464                    │
  └──────────────────────────────────────────────────┘
  (Full-width mono input)

- Centered below: [Apply DVB-S2 Config] — Primary blue pill button

===== TAB 4: PIPELINE =====

Single full-width card.

- Header "PIPELINE" in h2 var(--text-secondary)

- "Input File" label in body var(--text-secondary)
  Row with file input + browse button:
  ┌──────────────────────────────────────┐ [Browse]
  │ /Users/charlesclaw/videos/flight.mp4 │
  └──────────────────────────────────────┘
  (Input: var(--surface-raised) bg, mono-data, read-only style)
  (Browse: ghost button, var(--text-secondary))

- Button row:
  [▶ Start Pipeline] — Primary: var(--accent) bg, white text, pill, with play icon
  [■ Stop Pipeline] — Secondary: var(--surface-control) bg, var(--text-secondary) text, pill, with stop icon

- Status indicator between buttons: "● Running" (var(--success) dot + text) or "○ Stopped" (var(--text-disabled))

- Divider

- "Pipeline Status" sub-header in h3 var(--text-secondary)
  Compact rows:
  "Status      ● Running" (in var(--success))
  "File        flight.mp4" (in mono-data)
  "Bitrate     965,326 bps" (in mono-data)
  "Duration    00:47:32" (in mono-data)
  "Errors      0" (in mono-data var(--success))
  Label in small var(--text-muted), value in body/mono-data var(--text-primary)

- Divider

- Two side-by-side debug terminals:

  Left: "ffmpeg output" header in caption var(--text-muted)
  ┌──────────────────────────┐
  │ [ffmpeg] stream 0: video │  ← green text (#4DAA78)
  │ h264, yuv420p, 1920x1080 │     on black (#000000) bg
  │ 30 fps                   │
  │ [ffmpeg] stream 1: audio │
  │ mp2, 48000Hz, stereo     │
  │ 128 kb/s                 │
  │ [ffmpeg] frame=2842      │
  │ fps=30.0 q=28.0          │
  │                     [✕]  │  ← clear button top-right
  └──────────────────────────┘
  "142 lines" in small var(--text-muted) below terminal

  Right: "tsp output" header in caption var(--text-muted)
  ┌──────────────────────────┐
  │ [tsp] input bitrate:     │  ← var(--text-secondary)
  │ 965,326 bps              │     on black (#000000) bg
  │ [tsp] output bitrate:    │
  │ 965,326 bps              │
  │ [tsp] rate regulating    │
  │ to 965,326 bps           │
  │                          │
  │                     [✕]  │
  └──────────────────────────┘
  "89 lines" in small var(--text-muted) below terminal

  Terminals: black (#000000) bg, 12px var(--font-mono), 300px height, scrollable (use overflow-y: auto), 1px var(--border), 8px padding

===== TAB 5: ABOUT =====

Two side-by-side cards.

**Left card — SYSTEM STATUS:**
- Header "SYSTEM STATUS" in h2 var(--text-secondary)
- Info rows:
  "Connected     ● Yes" (var(--success) dot)
  "Serial        ...67464"
  "Frequency     915 MHz"
  "Symbol Rate   1.0 Msps"
  "TX Active     No" (var(--text-disabled))
  "Pipeline      Stopped" (var(--text-disabled))
  "Uptime        03:14:22"
  "WebSocket     ● Connected" (var(--success) dot)
  "Errors        0" (var(--success) text)
  Label in small var(--text-muted), value in body var(--text-primary), mono-data where appropriate

**Right card — HACKRF DEVICES:**
- Header "HACKRF DEVICES" in h2 var(--text-secondary)
- Device list:
  "HackRF ...60661" in body var(--text-primary)
  "Firmware 2024.02.1" in small var(--text-muted) below
  Divider line
  "HackRF ...67464" in body
  "Firmware 2024.02.1" in small var(--text-muted)
- "Last refresh: 12s ago" in small var(--text-muted)
- [Refresh] ghost button

- Below both cards, divider, then footer:
  "STRATOS v0.5-dev" in h2 var(--text-primary)
  "HAB Ground Station — Mission Control Dashboard" in body var(--text-secondary)
  "Build: 2026-05-19  ·  Engine: hab-engine 0.5.0  ·  GNU Radio: 3.10.x  ·  SoapySDR: 0.8.x" in small var(--text-muted)

===== CONNECTION LOG (shared bottom) =====

Full-width card below tab content, above packet stream.

- Header row: "CONNECTION LOG" in h2 var(--text-secondary), [All ▼] filter dropdown, [✕] clear button
- Scrollable log (max-height 150px):
  Rows with colored dot + mono timestamp + message:
  "● 14:10:01  Device HackRF #...67464 connected" (green dot)
  "● 14:10:03  Frequency set: 915.000 MHz" (blue dot, var(--accent))
  "● 14:10:04  Sample rate set: 2.000 Msps" (blue dot)
  "● 14:10:05  LNA gain set: 16 dB" (blue dot)
  "● 14:10:05  VGA gain set: 20 dB" (blue dot)
  "● 14:12:30  Pipeline started: flight.mp4" (green dot)
  "● 14:12:31  TX started at 915.000 MHz" (green dot)
  "● 14:13:45  WebSocket disconnected (retrying...)" (amber dot, var(--warning))
  "● 14:13:48  WebSocket reconnected" (green dot)
  Dots are 8px circles. Timestamps in mono-data var(--text-muted). Messages in body var(--text-secondary).
  Alternate row backgrounds: var(--surface-card) / var(--bg-frame)

===== RULES =====

1. ONE single HTML file. All CSS in a <style> tag.
2. Only Google Fonts for Inter and JetBrains Mono. No other external deps.
3. Use CSS Grid for main layout. Flexbox inside cards.
4. Use Lucide SVG icons inline (copy from https://lucide.dev):
   - Sidebar: hexagon, monitor, settings, antenna, info, chevron-left
   - Tabs: usb, sliders, satellite, film, info
   - Buttons: play, square (stop), x, refresh-cw, chevron-down, search
   - Status: circle (colored dots)
5. The page should fill 1920x1080 without scrolling. Internal scroll only where noted (connection log, debug terminals).
6. All cards use identical design tokens: var(--surface-card) bg, 20px radius, 24px padding, 1px var(--border) border, shadow.
7. Inputs: var(--surface-raised) bg, 14px radius, 1px var(--border), Signal White text on focus, mono font.
8. Focus state on inputs: var(--accent) border + box-shadow 0 0 0 3px rgba(47,128,237,0.18).
9. Buttons: 150ms transition, hover brightens background. Primary buttons use var(--accent) bg. Ghost buttons are transparent with var(--text-secondary) text, hover var(--surface-control) bg.
10. Toggle pills: active = var(--accent) bg + white text, inactive = var(--surface-control) bg + var(--text-secondary) text.
11. Include the sidebar and top bar from the main dashboard (same layout, slightly simplified — sidebar still has icons, top bar still has mission info). The main content area is what changes.
12. No JavaScript needed — this is a static wireframe. All values hardcoded.
13. ALL text must be realistic HAB data — no lorem ipsum.
14. Show the Device tab as active by default. Include HTML for all 5 tabs but comment out the hidden ones: <!-- Tab 2: RF Parameters --> etc. This lets a reviewer see all content.
15. Actually: include all 5 tabs' content in the HTML, stacked vertically with clear section headers. This is a wireframe for review, not a functional app. Add a label above each tab section: "═══════ TAB 2: RF PARAMETERS ═══════" etc. so the reviewer can scroll through all content.

Start with <!DOCTYPE html> and produce the complete file.
