# Dashboard UI Redesign — Design Spec

**Date:** 2026-06-05
**Status:** Draft

## Overview

Reorganize the Mission Control dashboard layout and replace scattered data cards with a single unified telemetry card. Add live streaming sparkline graphs for time-series metrics (environment, attitude, altitude/vertical-speed).

## Layout

```
┌──────────────────────────────────────────────────────────────┐
│ TopBar: HAB-1 STRATOS  ● NOMINAL  GPS LOCK  T+03:45:12     │
├────────┬─────────────────────────────────────────────────────┤
│        │                                                     │
│ Side   │  ┌──────────┐  ┌──────────────┐  ┌──────────────┐ │
│ bar    │  │          │  │              │  │  Telemetry   │ │
│ 64px   │  │  Live    │  │  Video       │  │  ─────────── │ │
│        │  │  Map     │  │  Feed        │  │  Navigation  │ │
│        │  │          │  │              │  │  Environment │ │
│        │  │          │  │              │  │  Power&Link  │ │
│        │  │          │  │              │  │  Attitude    │ │
│        │  └──────────┘  └──────────────┘  └──────────────┘ │
│        ├─────────────────────────────────────────────────────┤
│        │ > Packet Stream (terminal-style)                    │
└────────┴─────────────────────────────────────────────────────┘
```

- Left column: single full-height MapCard
- Center column: CameraFeed
- Right column: unified TelemetryCard (always expanded)
- Bottom: PacketStream in a terminal-style log

The existing TopBar and Sidebar remain unchanged.

## Component Changes

### Components to Remove
- `PositionCard.tsx` — merged into TelemetryCard Navigation section
- `MotionCard.tsx` — merged into TelemetryCard Navigation section
- `EnvironmentCard.tsx` — merged into TelemetryCard Environment section
- `PowerCard.tsx` — merged into TelemetryCard Power & Link section
- `RfLinkCard.tsx` — merged into TelemetryCard Power & Link section
- `AlertsCard.tsx` — removed (no active alerts in current data)
- `PacketRateCard.tsx` — merged into TelemetryCard Power & Link section

### New Component: TelemetryCard

A single card with four labeled sections, always expanded.

#### Section: Navigation
- **Graphs** (side-by-side, 48px tall):
  - Altitude (m) — blue line
  - Vertical speed (m/s) — green line, dashed zero-line reference
- **Text row** (2-column grid, label-left / value+unit-right):
  - GS (m/s), HDG (°), LAT (°N), LON (°W), SATS (count), HDOP

#### Section: Environment
- **Graphs** (2x2 grid, each 48px tall):
  - External temp (°C) — blue line
  - Internal temp (°C) — red line
  - Humidity (%) — green line
  - Pressure (hPa) — blue line

#### Section: Power & Link
- **Text only:**
  - BAT% (large, green), voltage/current (right-aligned)
  - Link status dots: TEL, PKT, VID (green/red)
  - Packet rate (right-aligned, blue)

#### Section: Attitude
- **Graphs** (3-across, 48px tall):
  - Roll (°) — yellow line, dashed zero-line
  - Pitch (°) — yellow line, dashed zero-line
  - Yaw (°) — yellow line

### Modified Component: PacketStream
- Current styling is fine; ensure it remains a terminal-style scrolling log at the bottom
- No structural changes needed

### Modified Component: MissionControl
- Replace the current 3-column grid with the new layout described above
- Pass all necessary data props to TelemetryCard
- Remove rendering of deleted card components

## Sparkline Graph Component

A reusable `SparklineGraph` component for the 48px-tall inline graphs:

```typescript
interface SparklineGraphProps {
  data: Array<{ timestamp: number; value: number }>;
  color: string;           // stroke color
  yAxisLabels: string[];   // 3 auto-scaled tick labels
  showZeroLine?: boolean;  // dashed center line for directional metrics
  valueLabel: string;      // current value (e.g., "24,348")
  unitLabel: string;       // unit (e.g., "m")
  metricLabel: string;     // left-aligned label (e.g., "ALT")
}
```

### Behavior
- Renders a Recharts `LineChart` with no fill (line-only)
- X-axis: hidden (always "last 60 seconds")
- Y-axis: hidden, but 3 tick labels rendered as absolute-positioned text on the right edge
- Optional dashed zero-line (for roll, pitch, VS)
- Label row above graph: metric label left, value+unit right-aligned

### Data Management
- `useHabApi` hook already exposes a `samples` buffer (or should be extended to maintain a 60-second rolling window per metric)
- Each SparklineGraph receives its own slice of time-series data

### Tech Stack
- **recharts** v2.12.7 (already in `package.json`) for the sparkline charts
- Tailwind CSS utility classes for layout
- No new dependencies required

## Value Alignment Rule

All metric rows follow a consistent pattern:
```
[LABEL]                    [VALUE unit]
```
- Label: left-aligned, muted color (`text-outline` / `#8b919f`)
- Value: font-semibold, `text-on-surface` (`#dae3ee`)
- Unit: muted, smaller font, directly after value (no extra gap)

Implementation: `flex justify-between items-baseline` with value+unit wrapped in a single `<span>`.

## Graph Style Rules

- Line-only stroke, no area fill (`fill="none"`)
- Stroke width: 1.5px
- No x-axis labels or grid lines
- Y-axis: 3 auto-scaled tick labels, positioned absolute on right edge
- Zero-line: dashed `#414753` on roll, pitch, VS graphs
- Background: `#141c24` (surface-container-low)
- Border radius: 3px
- Height: 48px (targeting ~2:1 aspect ratio in side-by-side layout)

## Files to Change

| File | Action |
|------|--------|
| `dashboard/web/src/components/MissionControl.tsx` | Rewrite layout: 3-column with MapCard, CameraFeed, TelemetryCard; keep PacketStream at bottom |
| `dashboard/web/src/components/TelemetryCard.tsx` | **New** — unified card with Navigation, Environment, Power & Link, Attitude sections |
| `dashboard/web/src/components/SparklineGraph.tsx` | **New** — reusable 48px sparkline with line-only stroke, y-axis ticks, zero-line option |
| `dashboard/web/src/hooks/useHabApi.ts` | Possibly extend to maintain 60s rolling window buffers per metric |
| `dashboard/web/src/components/PositionCard.tsx` | **Delete** |
| `dashboard/web/src/components/MotionCard.tsx` | **Delete** |
| `dashboard/web/src/components/EnvironmentCard.tsx` | **Delete** |
| `dashboard/web/src/components/PowerCard.tsx` | **Delete** |
| `dashboard/web/src/components/RfLinkCard.tsx` | **Delete** |
| `dashboard/web/src/components/AlertsCard.tsx` | **Delete** |
| `dashboard/web/src/components/PacketRateCard.tsx` | **Delete** |

## Out of Scope

- Bug fixes (none identified yet)
- Collapsible card sections (always expanded)
- Battery voltage/current sparkline graphs
- Settings page changes
- TopBar or Sidebar changes
- Camera feed implementation
- Packet stream restyling (keep existing terminal look)

## Verification

- Dashboard builds without errors: `npm run build`
- Lint passes: `npm run lint`
- Layout renders correctly with real WebSocket data (connect to receiver-server or sim)
- All 7 sparkline graphs render with streaming data
- Values are right-aligned against units
- No fill/area shading on any graph
