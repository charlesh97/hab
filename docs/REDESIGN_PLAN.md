#!/usr/bin/env python3
"""
HAB Ground Station — Visual Redesign Plan

## Current Issues vs Reference

| Aspect | Current (v0.2) | Reference | Fix |
|--------|---------------|-----------|-----|
| Card bg | `rgba(255,255,255,0.02)` near-invisible | `rgba(15,17,20,0.75)` dark frosted | Use `rgba(18,20,22,0.82)` with subtle blur |
| Border | `rgba(255,255,255,0.10)` | `rgba(255,255,255,0.06)` | Thinner, more subtle borders |
| Accent | Sky blue #0284c7 everywhere | Orange #f97316 for active, blue for data | Orange for active states, sky blue for data readouts |
| Glass effect | None (flat transparent) | `backdrop-filter: blur(20px)` | Use QGraphicsBlurEffect behind cards |
| Dashboard | Metric tiles grid | Live mission summary | Full redesign (see below) |

## Dashboard Layout (New)

```
┌────────────────────────────────────────────────────────┐
│  HAB-1 STRATOS    ● Telemetry nominal    14:23:45 UTC │  ← TopBar
├────────────────────────────────────────────────────────┤
│ ┌──────────┐  ┌───────────────────┐  ┌──────────────┐ │
│ │ Camera   │  │  Live Map         │  │ Telemetry    │ │
│ │ Feed     │  │  (leaflet-style)  │  │ ─────────── │ │
│ │          │  │                   │  │ Alt 24,348 m │ │
│ │ [stream] │  │    ○ balloon      │  │ Clmb  9.4 m/s│ │
│ │          │  │   ╱ ╲ path        │  │ Temp -52.3°C │ │
│ │          │  │  ╱   ╲            │  │ Pres  68.5hPa│ │
│ │          │  │ ╱     ╲           │  │ Batt   88.5% │ │
│ │          │  │○launch ○recovery   │  │ GPS    11sat │ │
│ └──────────┘  └───────────────────┘  └──────────────┘ │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Event Log / Packet Stream                          │ │
│ │ [14:10:23] [TLM] A:24348m V:9.4m/s T:-52.3C       │ │
│ │ [14:10:22] [EVT] STATUS_UPDATE_NOMINAL              │ │
│ │ [14:10:21] [TLM] A:24347m V:9.5m/s T:-52.3C       │ │
│ └────────────────────────────────────────────────────┘ │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌────┐ │
│ │START │ │ STOP │ │PIPELN│ │SET FR│ │CONFIG│ │MORE│ │
│ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └────┘ │
└────────────────────────────────────────────────────────┘
```

## Implementation Steps

### Step 1: Fix Visual Design System
- Update styles.py with proper glassmorphism colors
- Update widgets.py GlassCard to use `rgba(18,20,22,0.82)` + blur effect
- Add FrostedGlass mixin using QGraphicsBlurEffect

### Step 2: Build Live Dashboard
- Earth background with dark overlay
- Camera feed placeholder (QFrame with gradient)
- Live Map section (SVG-style map with balloon position)
- Telemetry panel (all metrics in a readable glass card)
- Event log / packet stream
- Quick action buttons

### Step 3: Apply to Other Tabs
- Connection tab: same glass card style
- DVBS-2 TX tab: same glass card style
- Telemetry tab: same glass card style

### Step 4: Screenshot & Deliver
- Tab-through all 4 views
- Send to Slack
- Commit
"""
