# Mission Control Dashboard — Design Spec

## Overview

Replace the existing React web dashboard with a single-screen, RX-only mission control interface for HAB (High Altitude Balloon) operations. The primary view shows all telemetry, a live map, camera feed, link health, alerts, and packet stream at a glance — no scrolling, no tab switching during flight. A separate settings area handles pre-flight RX hardware configuration.

## Design System

Adopted from the HAB Design System (`docs/DESIGN_SYSTEM.md` v2):

```
:root {
  --color-bg-app: #030505;
  --color-bg-frame: #080A0A;
  --color-surface-card: #111517;
  --color-surface-raised: #181D20;
  --color-surface-control: #252B2F;
  --color-surface-control-hover: #303840;
  --color-text-primary: #F4F6F7;
  --color-text-secondary: #A5AAAD;
  --color-text-muted: #6D7478;
  --color-text-disabled: #444A4E;
  --color-border: #242A2E;
  --color-border-strong: #343B41;
  --color-accent: #2F80ED;
  --color-accent-glow: #1C5FDB;
  --color-accent-soft: #10233F;
  --color-warning: #DCA83A;
  --color-critical: #E05344;
  --color-success: #4DAA78;
  --radius-frame: 32px;
  --radius-card: 20px;
  --radius-control: 14px;
  --radius-pill: 999px;
  --shadow-card: 0 18px 40px rgba(0, 0, 0, 0.28);
  --shadow-floating: 0 24px 60px rgba(0, 0, 0, 0.38);
  --space-1: 8px;
  --space-2: 16px;
  --space-3: 24px;
  --space-4: 32px;
  --space-5: 48px;
  --font-sans: Inter, SF Pro Text, Helvetica Neue, sans-serif;
  --font-mono: JetBrains Mono, IBM Plex Mono, monospace;
}
```

### Typography Scale

| Token | Size | Weight | Usage |
|-------|------|--------|-------|
| `display` | 34px | Medium | Mission name |
| `h1` | 24px | Semi-Bold | Section headers |
| `h2` | 18px | Semi-Bold | Card headers |
| `h3` | 16px | Medium | Sub-labels |
| `body` | 14px | Regular | Body text |
| `small` | 12px | Regular | Supporting text |
| `caption` | 11px | Medium | Badges, chips |
| `telemetry-large` | 32px | Regular | Hero metrics (altitude) |
| `telemetry-medium` | 20px | Medium | Card values |
| `mono-data` | 12-14px | Regular | Coordinates, timestamps, frequencies |

### Color Semantics

| Color | Usage |
|-------|-------|
| Telemetry Blue `#2F80ED` | Active nav, selected, live data, altitude, RF lock |
| Tracking Green `#4DAA78` | NOMINAL status, GPS lock, battery > 50%, packets received |
| Solar Amber `#DCA83A` | DEGRADED status, battery 20-50%, negative temps, link margin caution |
| Reentry Red `#E05344` | LOS/CRITICAL status, battery < 20%, LIVE badge, cutdown risk |
| Slate Chip `#2A3035` | Neutral status pills, inactive badges |

## Layout Structure

```
┌──┬──────────────────────────────────────────────────────┐
│64│  72px Top Bar                                         │
│px│                                                       │
│le├──────────┬────────────────────────┬───────────────────┤
│ft│  MAP     │                        │  RF LINK          │
│si│          │                        │  ─────────        │
│de│──────────│    CAMERA FEED         │  POWER            │
│ba│ POSITION │                        │  ─────────        │
│r │──────────│    [video stream]      │  ALERTS           │
│  │ MOTION   │                        │  ─────────        │
│  │──────────│                        │  PACKET RATE      │
│  │ ENVIRON. │                        │                   │
│  ├──────────┴────────────────────────┴───────────────────┤
│  │  ~200px PACKET STREAM (scrollable)                     │
└──┴───────────────────────────────────────────────────────┘
```

### Dimensions

| Zone | Width | Notes |
|------|-------|-------|
| Left sidebar | 64px | Fixed, icons only |
| Left panel | ~320px | Map + 3 telemetry cards |
| Center panel | Flex-fill | Camera feed |
| Right panel | ~340px | RF link + power + alerts + packet rate |
| Bottom bar | ~200px | Packet stream, scrollable |

No viewport scrolling — the main grid fills exactly one screen at 1080p+. Bottom packet stream scrolls internally.

## Components

### 1. Top Bar (72px)

```
⦿ HAB-1 STRATOS          ▲ ASCENT         ● NOMINAL   T+03:14:22
   ID: #521514                              ● GPS LOCK
   39.3187°N / -120.3289°W                  Last pkt: 1.2s
```

- Background: `#080A0A`, bottom hairline `#242A2E` border
- Left: mission name (display 34px), ID below (caption Dim Gray), coordinates (mono small)
- Center: flight phase badge — pill in phase-appropriate color
- Right: NOMINAL/DEGRADED/CRITICAL status pill, GPS lock indicator, last packet age (green <5s, amber <15s, red >15s), elapsed time (telemetry-medium)

### 2. Left Sidebar (64px)

- Background: `#030505`
- Icons in 36px rounded-square containers
- Active: Telemetry Blue `#2F80ED` bg, Signal White icon
- Inactive: transparent, Fog Gray icon
- Icons: ⦿ app mark, ◉ mission control (active), ⚙ settings, 📡 RF config, ⓘ about, ☰ collapse
- Divider between app mark and nav icons

### 3. Left Panel (~320px)

#### 3a. Map Card (~35% of left panel height)
- Card: `#111517`, 20px radius, 1px `#242A2E` border
- Dark map tiles (Leaflet with CARTO dark basemap or equivalent)
- Balloon position marker: Telemetry Blue dot with subtle ping animation
- Flight path: Telemetry Blue polyline, 3px weight
- Launch marker: small Slate Chip circle
- Recovery/last-known marker: Tracking Green circle
- Coordinate readout in bottom of card: mono small, Dim Gray
- Controls: zoom +/- in Gunmetal pills, floating on map

#### 3b. Position Card
- Header: "POSITION" in h2, Fog Gray
- Values in telemetry-medium, Signal White, mono:
  - sats: 14 (with 3D fix indicator)
  - lat/lon: 39.3187°N / -120.3289°W
  - hdop: 0.82
  - vdop: 1.34
  - agl: 17,210m (telemetry-large, Telemetry Blue)

#### 3c. Motion Card
- Header: "MOTION" in h2, Fog Gray
- Values in telemetry-medium:
  - GROUND SPEED: 13.8 m/s
  - VERT SPEED: 5.4 m/s (▲ ascent green, ▼ descent amber)
  - HEADING: 72.6°
  - COURSE: 74.1°
  - ACCELERATION: x:0.03 y:-0.08 z:9.71 (inline mono small)
  - GYRO: r:0.4 p:-0.2 y:1.1 (inline mono small)
  - ATTITUDE: roll 2.8° pitch -4.1° yaw 71.9° (inline mono small)
- ACCEL/GYRO/ATT shown in compact row or mini-table format to save vertical space

#### 3d. Environment Card
- Header: "ENVIRONMENT" in h2, Fog Gray
- Values in telemetry-medium:
  - EXT TEMP: -42.6°C (Solar Amber for subzero)
  - INT TEMP: 12.4°C
  - PRESSURE: 72.8 hPa
  - HUMIDITY: 4.2%
  - BARO ALT: 18,190m

All cards in left panel are `#111517` with 20px radius and 24px padding. No scroll — if content is tight at smaller resolutions, ACCEL/GYRO/ATT move to a collapsible subsection within Motion.

### 4. Center Panel — Camera Feed

- Full center column, dark `#080A0A` background when no video feed
- Card has 20px radius, 1px `#242A2E` border
- Video fills the card area
- Overlay elements:
  - Top-left: ● LIVE badge — Reentry Red `#E05344` pill with pulsing dot, caption
  - Top-right: bitrate + signal quality — mono small, "2.4 Mbps  98%"
  - Bottom-left: RTSP URL bar — monospace, Dim Gray text, Gunmetal background, subtle border. Example: `rtsp://192.168.1.100/stream1`
  - Bottom-right: Reconnect button — Gunmetal `#252B2F` pill, Fog Gray text
- No feed state: centered "NO VIDEO SIGNAL" in Dim Gray, with animated connecting indicator

### 5. Right Panel (~340px)

#### 5a. RF Link Card
- Header: "RF LINK" in h2, Fog Gray
- 3 status pills in a row: TLM, PKT, VID
  - NOMINAL: Tracking Green dot + text
  - DEGRADED: Solar Amber dot + text
  - OFFLINE: Reentry Red dot + text
- Divider
- Key params in compact rows, mono small:
  - Frequency: 915.000 MHz
  - Modulation: QPSK 1/2
  - Symbol Rate: 1.000 Msps
  - SNR: 12.3 dB (color-coded: green >10, amber 5-10, red <5)
  - RSSI: -68.4 dBm
  - Packet Loss: 0.02%

#### 5b. Power Card
- Header: "POWER" in h2, Fog Gray
- Battery row: large telemetry-medium values
  - 7.62V  0.84A  6.4W  68%
  - Battery % with horizontal bar (color: green >50%, amber 20-50%, red <20%)
- Divider
- Rails in compact 3-column: 5V: 5.03V | 3.3V: 3.31V | 1.8V: 1.79V
- Battery temp: 8.1°C (mono small)

#### 5c. Alerts Card
- Header: "ALERTS" in h2, Fog Gray
- Empty state: "No active alerts" in Dim Gray body
- Active alerts: rows with severity dot (red critical, amber warning) + message + timestamp
- Last packet age: freshness indicator showing seconds since last received packet
- Link margin: 11 dB (color-coded)

#### 5d. Packet Rate Card
- Header: "PACKET RATE" in h2, Fog Gray
- Rate counter: 2.4 pkt/s (telemetry-medium, Signal White)
- Sequence: #18430 (mono small)
- Mini sparkline: last 30 seconds of packet rate, Telemetry Blue line, Deep Blue Wash fill, 60px height

### 6. Bottom Bar — Packet Stream (~200px)

```
PACKET STREAM  ▸ RX: 2.4 pkt/s  ▸ Seq #18430    ⏸  ✕
───────────────────────────────────────────────────────
04:22:31 [POS] lat:39.31874 lon:-120.32892 alt:18,342m
04:22:36 [MOT] gs:13.8 vs:5.4 hdg:72.6 cog:74.1
04:22:41 [ENV] ext:-42.6°C int:12.4°C pres:72.8hPa
04:22:46 [PWR] bat:7.62V/0.84A 6.4W 68% rails:OK
```

- Card: `#111517`, 20px radius, full width
- Header bar: title h2, live RX rate, sequence counter, pause/clear Gunmetal icon buttons
- Entries: mono small, timestamps in Dim Gray
- Type tags color-coded: POS in Telemetry Blue, MOT in Solar Amber, ENV in Tracking Green, PWR in Slate Chip
- Row stripes: alternating `#111517` / `#080A0A`
- New entries slide in from top (150ms ease-out), oldest exit bottom (max 200 entries in view)
- Auto-scroll — when scrolled up, "↓ New" floating button (Gunmetal pill) appears
- Pause freezes display, clear flushes visible log

### 7. Settings / Configuration View

**Full spec moved to:** `docs/superpowers/specs/2026-05-19-settings-config-design.md`

When the Settings ⚙ or RF Config 📡 sidebar icon is selected, the three-panel body transitions to a full-width settings layout with 5 sub-tabs:

| Tab | Content |
|-----|---------|
| Device | HackRF device discovery, connection, connected device info readout |
| RF Parameters | Frequency, symbol rate, LO ppm, LNA/VGA gain sliders, AMP toggle |
| DVB-S2 | MODCOD dropdown, pilots, rolloff, FEC frame, SPS, sink type, device args |
| Pipeline | MP4 file browser, ffmpeg/tsp pipeline controls, dual debug terminals |
| About | System status, HackRF device list, version info |

All settings pages share a connection log at the bottom. Configuration persists to localStorage and is sent to the engine via WebSocket commands and HTTP API fallbacks. See the separate spec for full component layouts, field tables, validation rules, and behavior.

## Telemetry Data Schema

The dashboard receives JSON packets via WebSocket at 2+ Hz. Four packet types:

```typescript
// Packet envelope (common to all types)
{
  v: number;        // schema version
  id: string;       // payload ID (e.g. "HAB001")
  mid: string;      // mission ID (e.g. "donner-01")
  seq: number;      // sequence number
  t: string;        // ISO 8601 timestamp
  type: "position" | "motion" | "environment" | "power";
}

// type: "position"
{
  lat: number;      // decimal degrees
  lon: number;      // decimal degrees
  alt_m: number;    // GPS altitude (meters)
  agl_m: number;    // above ground level (meters)
  fix: boolean;     // GPS fix acquired
  fix_type: string; // "2d" | "3d"
  sats: number;     // satellite count
  hdop: number;     // horizontal dilution
  vdop: number;     // vertical dilution
}

// type: "motion"
{
  gs_mps: number;   // ground speed (m/s)
  vs_mps: number;   // vertical speed (m/s)
  heading_deg: number;
  cog_deg: number;  // course over ground
  accel: { x: number, y: number, z: number };
  gyro_dps: { r: number, p: number, y: number };
  att_deg: { roll: number, pitch: number, yaw: number };
}

// type: "environment"
{
  temp_ext_c: number;
  temp_int_c: number;
  pressure_hpa: number;
  humidity_pct: number;
  baro_alt_m: number;
}

// type: "power"
{
  bat_v: number;     // battery voltage
  bat_a: number;     // battery current
  bat_w: number;     // battery wattage
  bat_pct: number;   // battery percentage
  bat_temp_c: number;
  rails_v: {
    v5: number;
    v3v3: number;
    v1v8: number;
  };
}
```

## Flight Phases

| Phase | Criteria | Pill Color |
|-------|----------|------------|
| PRE-LAUNCH | altitude < 100m, |vs| < 1 | Slate Chip |
| ASCENT | vs > 1, altitude > 100m | Telemetry Blue |
| FLOAT | |vs| < 1, altitude > 1000m | Tracking Green |
| DESCENT | vs < -1, altitude > 100m | Solar Amber |
| RECOVERED | altitude < 100m, |vs| < 1 | Tracking Green |

## Link Status States

| State | Criteria | Color |
|-------|----------|-------|
| NOMINAL | Packets arriving within 5s, SNR > 5 dB | Tracking Green |
| DEGRADED | Packets 5-15s stale, or SNR 2-5 dB | Solar Amber |
| OFFLINE / LOS | Packets >15s stale, or SNR < 2 dB | Reentry Red |

## Behavior Rules

- **No scroll on main view** — all components fit viewport at 1080p+. Bottom packet stream scrolls internally.
- **Stale telemetry is obvious** — values grey out to Dim Gray after 5s, Ghost Gray after 15s.
- **Alerts surface in the alerts card** — no popups or toasts during flight.
- **Settings is a separate view** — operator navigates via sidebar, not tabs.
- **Color coding is consistent** — green = good, amber = watch, red = bad, blue = active/informational.
- **Animation is minimal** — 150ms transitions, subtle ping on map marker, slide-in for new packets, pulsing dot on LIVE badge.
- **Monospace is selective** — coordinates, timestamps, frequencies, bitrates, packet IDs, and serial logs only.

## Tech Stack (for implementation)

- React 18 + TypeScript
- Vite
- Tailwind CSS (with CSS variables for design tokens)
- Leaflet + CARTO dark tiles (map)
- Recharts (sparklines/time-series if needed in future drill-downs)
- Framer Motion (subtle animations)
- Lucide React (icons)
- WebSocket for live data, SSE for spectrum fallback
