# Data Logging + Live Map — Design Spec

**Date:** 2026-06-05
**Status:** Draft

## Overview

Add SQLite-based packet persistence to the receiver server and replace the static SVG placeholder map with a real Leaflet map showing live balloon position with a trail. These are two independent changes that complement each other.

## Backend: SQLite Data Logging

### Schema

Single `packets` table in `hab_data.db` (configurable path):

| Column | Type | Description |
|---|---|---|
| `seq` | INTEGER PRIMARY KEY | Packet sequence number |
| `received_at` | TEXT NOT NULL | ISO 8601 timestamp, server-side |
| `type` | TEXT NOT NULL | `position` / `motion` / `environment` / `power` |
| `payload` | TEXT NOT NULL | Full packet JSON blob |

### Changes

| File | Change |
|---|---|
| `dashboard/server/config.py` | Add `database_path: str = "hab_data.db"` to `ServerConfig` |
| `dashboard/server/receiver_manager.py` | On startup: open `sqlite3` connection, `CREATE TABLE IF NOT EXISTS`. On `ingest_packet()`: `INSERT` after deque append + WebSocket broadcast. Close on shutdown. |
| `dashboard/server/routes/rest.py` | Add `GET /api/positions?since=0&limit=5000` — queries only position-type packets from SQLite, returns `[{seq, received_at, lat, lon, alt_m}, ...]` ordered by seq ascending (extracts lat/lon/alt from payload on the server side so the frontend doesn't need to parse raw JSON) |

### Key design decision: non-blocking

The `INSERT` runs after the deque append and WebSocket broadcast. It never gates the live pipeline. If the DB write fails, it logs a warning and continues — packet delivery to the dashboard is unaffected.

### Dependencies

None. Python's `sqlite3` is part of the standard library.

## Frontend: Live Leaflet Map

### Current state

`MapCard.tsx` uses a hardcoded inline SVG with static coordinates. `react-leaflet` and `leaflet` are already in `package.json` but unused.

### New behavior

Replace the SVG with a real Leaflet map showing:

1. **Tile layer:** CartoDB Dark Matter (`https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`) — free, no API key, matches the dark dashboard theme
2. **Polyline trail:** All past position points connected as a line, loaded via `GET /api/positions` on mount
3. **Current position marker:** A balloon icon or circle marker at the latest position, updated live via WebSocket
4. **Auto-pan:** Map follows the balloon as it moves (fit bounds to trail on initial load, then pan to keep marker visible)

### Data flow

```
Page load:
  GET /api/positions ──► draw polyline trail + place initial marker

Live updates (WebSocket):
  {"type":"telemetry","data":{"type":"position", lat, lon, alt_m, ...}}
  ──► append point to trail polyline
  ──► move marker to new position
  ──► pan map if marker near edge
```

### File changes

| File | Change |
|---|---|
| `dashboard/web/src/components/MapCard.tsx` | Full rewrite: remove inline SVG, render `<MapContainer>` with `<TileLayer>`, `<Polyline>`, `<Marker>`, `<Popup>`. Subscribe to WebSocket telemetry hook for live position data. |
| `dashboard/web/src/hooks/useHabApi.ts` | Add `loadPositions()` function that fetches `GET /api/positions`, returns position array for initial trail. The hook already tracks `position` state from WebSocket telemetry — MapCard reads that directly for the live marker. |

### MapCard component spec

**Props:** none (pulls data from `useHabApi` hook)

**Internal state:**
- `trail: LatLngTuple[]` — all position points for the polyline
- `latestPosition: LatLngTuple` — current marker location
- `mapRef` — Leaflet map instance for auto-pan

**Rendering:**
- `MapContainer` with `center` at latest position (or default 39,-98), `zoom={5}`
- `TileLayer` with dark theme URL + attribution
- `Polyline` with trail array, styled in the dashboard's primary color (#abc7ff or similar)
- `Marker` at latest position with a custom balloon icon or circle marker
- Info bar overlay (optional, CSS-positioned) showing lat/lon/alt

**Edge cases:**
- No position data yet → center map on default US view, show empty state
- Position hasn't changed in >10s → marker stays, no special treatment
- Component unmounts → cleanup subscriptions

## Out of scope

- Mission replay / mission selector UI (future enhancement)
- CSV/JSON data export (future enhancement)
- Altitude-colored trail segments (future enhancement)
- Map layer toggles (future enhancement)
