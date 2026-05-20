You are a UI designer building an HTML/CSS wireframe for a high-altitude
balloon (HAB) mission control dashboard. This is a dark, technical,
single-screen operator workstation for monitoring live telemetry from a
stratospheric balloon.

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
  --font-sans: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}

Typography:
- display: 34px Medium (mission name)
- h1: 24px Semi-Bold
- h2: 18px Semi-Bold (card headers)
- h3: 16px Medium
- body: 14px Regular
- small: 12px Regular
- caption: 11px Medium
- telemetry-large: 32px Regular (hero metrics)
- telemetry-medium: 20px Medium (card values)
- mono-data: 13px Regular (coordinates, timestamps, frequencies)

Color semantics:
- Telemetry Blue (#2F80ED): active, selected, altitude, RF lock
- Tracking Green (#4DAA78): NOMINAL, GPS lock, battery>50%
- Solar Amber (#DCA83A): DEGRADED, battery 20-50%, negative temps
- Reentry Red (#E05344): CRITICAL, LIVE badge, battery<20%
- Slate Chip (#2A3035): neutral pill backgrounds

===== LAYOUT =====

Build a full-viewport, non-scrolling dashboard with this structure:

┌──┬──────────────────────────────────────────────────────┐
│64│  72px TOP BAR                                        │
│px│  mission name | phase badge | status + elapsed time  │
│le├──────────┬────────────────────────┬───────────────────┤
│ft│  MAP     │                        │  RF LINK          │
│si│  card    │    CAMERA FEED         │  3 status pills   │
│de│──────────│    (center panel,      │  freq/mod/snr     │
│ba│ POSITION │     largest area)      │  ─────────        │
│r │  card    │                        │  POWER            │
│  │──────────│    video placeholder   │  bat V/A/W/%      │
│  │ MOTION   │    with LIVE badge,    │  rails:5/3.3/1.8  │
│  │  card    │    bitrate overlay,    │  ─────────        │
│  │──────────│    RTSP URL bar,       │  ALERTS           │
│  │ ENVIRON. │    reconnect button    │  active alerts    │
│  │  card    │                        │  link margin      │
│  │          │                        │  ─────────        │
│  │          │                        │  PACKET RATE      │
│  │          │                        │  rate + sparkline │
│  ├──────────┴────────────────────────┴───────────────────┤
│  │  ~200px PACKET STREAM (scrollable log)                 │
│  │  header: stream name | RX rate | pause | clear         │
│  │  rows: timestamp [TYPE] payload data                   │
└──┴───────────────────────────────────────────────────────┘

Dimensions:
- Left sidebar: 64px fixed
- Left panel: ~340px
- Center panel: flex-fill (remaining space)
- Right panel: ~350px
- Bottom bar: ~200px

Cards: background var(--surface-card), border-radius var(--radius-card),
border 1px var(--border), padding 24px.

===== LEFT SIDEBAR (64px) =====

Background var(--bg-app). Vertical icon bar centered.
Icons inside 36px rounded-square containers, using Lucide icon SVG:
- Top: Hexagon icon (app mark), color var(--accent)
- Divider line (var(--border))
- Monitor icon (mission control) — active state: var(--accent) bg, white icon
- Settings gear icon
- Antenna icon (RF config)
- Info icon
- Divider
- Chevron-left icon (collapse)
Inactive icons: transparent bg, var(--text-secondary) color. Hover: var(--surface-control) bg.

Add tooltip labels on hover for each icon.

===== TOP BAR (72px) =====

Background var(--bg-frame), bottom border 1px var(--border).
Display as flex row, items centered:

Left section:
  "⦿ HAB-1 STRATOS" in display (34px) var(--text-primary)
  Small text below: "ID: #521514" in caption var(--text-muted)
  Next line: "39.3187°N / -120.3289°W" in mono-data var(--text-secondary)

Center section:
  Flight phase pill: "▲ ASCENT" in caption, var(--accent) bg, white text, rounded-pill
  (Show pills for all phases: PRE-LAUNCH/Slate, ASCENT/Blue, FLOAT/Green, DESCENT/Amber, RECOVERED/Green — only one active)

Right section:
  Status pill: "● NOMINAL" with var(--success) dot, caption
  Below: "● GPS LOCK" with var(--success) dot, small
  Next: "Last pkt: 1.2s" in small var(--text-muted) (color by age: green <5s, amber <15s, red >15s)
  Far right: "T+03:14:22" in telemetry-medium var(--text-primary)

===== LEFT PANEL (~340px) =====

Contains 4 stacked cards that fill the panel height. Each card: var(--surface-card),
var(--radius-card), border var(--border), padding 24px.

**MAP CARD** (largest, takes ~35% of panel height):
  - Header "LIVE MAP" in h2 var(--text-secondary)
  - Map area: dark placeholder (var(--bg-frame) bg) with a simple SVG mockup:
    - Draw a curved dotted path using SVG polyline in var(--accent)
    - Small circle marker at end in var(--accent) for balloon position
    - Small circle at start in var(--surface-control) for launch
    - Small circle at bottom in var(--success) for recovery target
  - Coord readout bottom-left: "39.3187°N -120.3289°W | Alt: 18,342m" in mono-data var(--text-secondary)
  - Floating zoom +/- buttons top-right: var(--surface-control) pill circles

**POSITION CARD**:
  - Header "POSITION" in h2 var(--text-secondary)
  - Values grid, 2 columns:
    Left col: label in small var(--text-muted), value in telemetry-medium var(--text-primary)
    Right col: same pattern
  - Fields: "SATS" (14, with "3D FIX" badge in var(--success) pill), "HDOP" (0.82), "VDOP" (1.34), "AGL" (17,210m in telemetry-large var(--accent))

**MOTION CARD**:
  - Header "MOTION" in h2 var(--text-secondary)
  - 2-column grid of labeled values:
    "GROUND SPEED" (13.8 m/s), "VERT SPEED" (5.4 m/s ▲ in var(--success)),
    "HEADING" (72.6°), "COURSE" (74.1°)
  - Sub-section "ACCELEROMETER": x:0.03 y:-0.08 z:9.71 in mono-data, single row
  - Sub-section "GYROSCOPE": r:0.4 p:-0.2 y:1.1 in mono-data, single row
  - Sub-section "ATTITUDE": roll 2.8° pitch -4.1° yaw 71.9° in mono-data, single row
  - Each sub-section has a dim label in caption var(--text-muted) above the row

**ENVIRONMENT CARD**:
  - Header "ENVIRONMENT" in h2 var(--text-secondary)
  - 2-column labeled values:
    "EXT TEMP" (-42.6°C, color var(--warning) for below 0),
    "INT TEMP" (12.4°C),
    "PRESSURE" (72.8 hPa),
    "HUMIDITY" (4.2%),
    "BARO ALT" (18,190m)

===== CENTER PANEL (flex-fill) =====

**CAMERA FEED CARD** (fills entire center area):
  - var(--bg-frame) background
  - var(--radius-card), border var(--border)
  - Dark video placeholder area: centered camera icon (Lucide Video icon, huge, var(--text-disabled))
  - "NO VIDEO SIGNAL" text centered below, var(--text-disabled)
  - Overlay elements (absolute positioned):
    - Top-left: "● LIVE" badge — var(--critical) bg pill, white caption text. Add CSS pulse animation to the dot.
    - Top-right: "2.4 Mbps  98%" in mono-data var(--text-primary)
    - Bottom-left: RTSP URL bar showing "rtsp://192.168.1.100/stream1" in mono-data var(--text-muted), with a small var(--surface-control) bg input style
    - Bottom-right: "Reconnect" button — var(--surface-control) pill, var(--text-secondary) text
  - These overlays should have semi-transparent dark backgrounds so they're readable over video

===== RIGHT PANEL (~350px) =====

Contains 4 stacked cards.

**RF LINK CARD**:
  - Header "RF LINK" in h2 var(--text-secondary)
  - Row of 3 status pills, each with colored dot + label:
    "● TLM NOMINAL" (var(--success)), "● PKT NOMINAL" (var(--success)), "● VID NOMINAL" (var(--success))
  - Pills use var(--surface-control) bg
  - Divider (1px var(--border))
  - Parameter rows in compact mono-data:
    Label in var(--text-muted), value in var(--text-primary):
    Frequency: 915.000 MHz
    Modulation: QPSK 1/2
    Symbol Rate: 1.000 Msps
    SNR: 12.3 dB (value in var(--success) since >10)
    RSSI: -68.4 dBm
    Packet Loss: 0.02% (value in var(--success) since very low)

**POWER CARD**:
  - Header "POWER" in h2 var(--text-secondary)
  - Battery values row: "7.62V  0.84A  6.4W" in telemetry-medium var(--text-primary)
  - Battery percentage: "68%" in telemetry-large var(--success) (green since >50%)
  - Battery bar: horizontal bar, var(--surface-control) bg track, var(--success) fill 68% width, 6px height, var(--radius-pill)
  - Divider
  - Rails row: "5V: 5.03V  |  3.3V: 3.31V  |  1.8V: 1.79V" in mono-data var(--text-secondary)
  - "Battery Temp: 8.1°C" in small var(--text-muted)

**ALERTS CARD**:
  - Header "ALERTS" in h2 var(--text-secondary)
  - Empty state: "No active alerts" in body var(--text-disabled), centered with some padding
  - Below, separated by divider:
  - "Last packet: 1.2s ago" in small (color var(--success) since <5s)
  - "Link margin: 11 dB" in small var(--text-primary)

**PACKET RATE CARD**:
  - Header "PACKET RATE" in h2 var(--text-secondary)
  - "2.4 pkt/s" in telemetry-medium var(--text-primary)
  - "Seq: #18430" in mono-data var(--text-muted)
  - Mini sparkline: SVG area chart, 60px height, var(--accent) line, var(--accent-soft) fill
  - Simulate a line that fluctuates between 1.8 and 2.8 over ~30 data points

===== BOTTOM BAR — PACKET STREAM (~200px) =====

Full-width card with internal scroll.

Header row:
  - "PACKET STREAM" in h2 var(--text-secondary)
  - "▸ RX: 2.4 pkt/s" in small var(--text-primary)
  - "Seq #18430" in mono-data var(--text-muted)
  - Pause icon button and X (clear) icon button — var(--surface-control) pill circles

Log area (scrollable, ~160px usable height):
  - Each row: 36px height, alternating backgrounds (var(--surface-card) / var(--bg-frame))
  - Row format: [timestamp in mono-data var(--text-muted)] [type badge] payload text
  - Type badges are small pills with color-coded background:
    "[POS]" = var(--accent) bg, "[MOT]" = var(--warning) bg, "[ENV]" = var(--success) bg, "[PWR]" = #2A3035 bg
  - Payload text in mono-data var(--text-secondary)
  - Show ~10 sample rows with realistic telemetry data:
    04:22:31 [POS] lat:39.31874 lon:-120.32892 alt:18,342m
    04:22:36 [MOT] gs:13.8 vs:5.4 hdg:72.6 cog:74.1
    04:22:41 [ENV] ext:-42.6°C int:12.4°C pres:72.8hPa hum:4.2%
    04:22:46 [PWR] bat:7.62V/0.84A 6.4W 68% rails:5.03/3.31/1.79
    04:22:51 [POS] lat:39.31882 lon:-120.32888 alt:18,345m
    04:22:56 [MOT] gs:13.9 vs:5.3 hdg:72.8 cog:74.3
    04:23:01 [ENV] ext:-42.7°C int:12.3°C pres:72.6hPa hum:4.1%
    04:23:06 [PWR] bat:7.61V/0.83A 6.3W 67% rails:5.02/3.31/1.78
    04:23:11 [POS] lat:39.31891 lon:-120.32883 alt:18,349m
    04:23:16 [MOT] gs:14.0 vs:5.4 hdg:73.0 cog:74.5

===== RULES =====

1. One single HTML file. Include all CSS in a <style> tag, no external dependencies except Google Fonts for Inter and JetBrains Mono.
2. Use CSS Grid for the main layout. Use flexbox inside cards.
3. No scrolling on the main viewport. Only the packet stream log scrolls internally.
4. Use Lucide icons via inline SVG (copy paths from https://lucide.dev).
5. All cards use the same design tokens — consistent border-radius, padding, border color.
6. Color-code values semantically: green for good, amber for warning, red for critical, blue for active.
7. The map area should contain a simple SVG drawing of a curved flight path with markers.
8. The camera area should clearly show it's a video placeholder with overlay controls.
9. Hover states on buttons/pills: brighten background slightly, 150ms transition.
10. No JavaScript needed — this is a static wireframe. All values are hardcoded sample data.
11. The design should fill exactly 1920x1080 viewport without scroll.
12. Add subtle depth: cards have box-shadow, sidebar sits flush left, top bar has bottom border.
13. Make text labels compact and muted. Values should pop with high contrast.
14. Add a subtle grid pattern or very low opacity noise texture on the background (optional, just makes it look premium).
15. ALL text must be realistic HAB mission data — not lorem ipsum.

Start with <!DOCTYPE html> and produce the complete file.
