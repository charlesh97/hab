# Data Logging + Live Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SQLite packet persistence to the receiver server and replace the static SVG map with a real Leaflet map showing balloon position + trail.

**Architecture:** Backend writes packets to SQLite asynchronously (non-blocking, after deque + broadcast). Frontend loads the position trail via a new `GET /api/positions` REST endpoint on mount, then appends live positions from the existing WebSocket telemetry stream. The live pipeline (deque → broadcast) is untouched — SQLite is purely additive.

**Tech Stack:** Python 3.14 + sqlite3 (stdlib), FastAPI, React 18 + TypeScript, react-leaflet + leaflet (already installed), CartoDB Dark Matter tiles.

---

## File Structure

| Action | File | Responsibility |
|---|---|---|
| Modify | `dashboard/server/config.py` | Add `database_path` to `ServerConfig` |
| Modify | `dashboard/server/receiver_manager.py` | Open DB on init, INSERT on ingest, close on cleanup |
| Modify | `dashboard/server/routes/rest.py` | Add `GET /api/positions` endpoint |
| Modify | `dashboard/server/main.py` | Pass `database_path` when constructing `ReceiverManager` |
| Modify | `dashboard/web/src/hooks/useHabApi.ts` | Add `loadPositions()` function and export it |
| Modify | `dashboard/web/src/components/MapCard.tsx` | Full Leaflet rewrite |

---

### Task 1: Add `database_path` to ServerConfig

**Files:**
- Modify: `dashboard/server/config.py:10-16`

- [ ] **Step 1: Add the field**

In `dashboard/server/config.py`, in the `ServerConfig` dataclass, add `database_path`:

```python
@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    packet_buffer_size: int = 1000
    status_interval_sec: float = 1.0
    spectrum_points: int = 256
    spectrum_chunk_interval: int = 20
    database_path: str = "hab_data.db"
```

- [ ] **Step 2: Verify the file is still valid Python**

Run: `python -c "from dashboard.server.config import ServerConfig; c = ServerConfig(); print(c.database_path)"`

Expected output: `hab_data.db`

- [ ] **Step 3: Commit**

```bash
git add dashboard/server/config.py
git commit -m "feat: add database_path to ServerConfig"
```

---

### Task 2: Add SQLite logging to ReceiverManager

**Files:**
- Modify: `dashboard/server/receiver_manager.py`

- [ ] **Step 1: Add imports**

In `dashboard/server/receiver_manager.py`, add to the existing imports (after line 10 `from config import ReceiverConfig`):

```python
import json
import sqlite3
from datetime import datetime, timezone
```

- [ ] **Step 2: Accept database_path in __init__ and open DB connection**

Modify the `__init__` method (line 20):

```python
class ReceiverManager:
    def __init__(self, ws_manager, config: ReceiverConfig, db_path: str | None = None):
        self._ws = ws_manager
        self._config = config
        self._state = ReceiverState.IDLE
        self._packet_buffer: deque[dict] = deque(maxlen=1000)
        self._receiver = None
        self._bridge_task: asyncio.Task | None = None
        self._status_task: asyncio.Task | None = None
        self._packets_total = 0
        self._packets_valid = 0
        self._spectrum_frame = None
        self._start_time: float | None = None
        self._db_path = db_path
        self._db_conn: sqlite3.Connection | None = None
        if db_path:
            self._db_conn = sqlite3.connect(str(db_path))
            self._db_conn.execute(
                "CREATE TABLE IF NOT EXISTS packets ("
                "  seq INTEGER PRIMARY KEY,"
                "  received_at TEXT NOT NULL,"
                "  type TEXT NOT NULL,"
                "  payload TEXT NOT NULL"
                ")"
            )
            self._db_conn.commit()
```

- [ ] **Step 3: Add _save_packet helper method**

Add this method to the `ReceiverManager` class (after `_build_status` at line 121):

```python
def _save_packet(self, packet: dict):
    if self._db_conn is None:
        return
    try:
        self._db_conn.execute(
            "INSERT OR REPLACE INTO packets (seq, received_at, type, payload) VALUES (?, ?, ?, ?)",
            (
                packet.get("seq", 0),
                datetime.now(timezone.utc).isoformat(),
                packet.get("type", "unknown"),
                json.dumps(packet),
            ),
        )
        self._db_conn.commit()
    except Exception:
        import logging
        logging.getLogger("receiver_manager").warning(
            "Failed to write packet seq=%s to database", packet.get("seq"),
            exc_info=True,
        )
```

- [ ] **Step 4: Call _save_packet from ingest_packet**

In the `ingest_packet` method (line 96), add `self._save_packet(packet)` after the broadcast:

```python
async def ingest_packet(self, packet: dict):
    """Receive and broadcast a telemetry packet from external sources.
    ...
    """
    self._packet_buffer.append(packet)
    self._packets_total += 1
    self._packets_valid += 1
    await self._ws.broadcast({"type": "telemetry", "data": packet})
    self._save_packet(packet)
```

- [ ] **Step 5: Close DB connection in _cleanup**

In the `_cleanup` method (line 108), add DB close after the receiver stop:

```python
async def _cleanup(self):
    self._stop_receiver()
    self._receiver = None
    if self._db_conn:
        self._db_conn.close()
        self._db_conn = None
    if self._status_task and not self._status_task.done():
        self._status_task.cancel()
        try:
            await self._status_task
        except asyncio.CancelledError:
            pass
    self._bridge_task = None
    self._status_task = None
```

- [ ] **Step 6: Run a quick smoke test with the sim**

```bash
cd dashboard && bash sim/run.sh &
sleep 3
python -c "
import sqlite3
conn = sqlite3.connect('hab_data.db')
rows = conn.execute('SELECT COUNT(*) FROM packets').fetchone()
print(f'Rows after 3s of sim: {rows[0]}')
assert rows[0] > 0, 'No packets were saved!'
print('PASS: packets saved to DB')
conn.close()
"
kill %1 2>/dev/null
```

Expected: `PASS: packets saved to DB` with a count > 0

- [ ] **Step 7: Commit**

```bash
git add dashboard/server/receiver_manager.py
git commit -m "feat: add SQLite packet persistence to ReceiverManager"
```

---

### Task 3: Add GET /api/positions endpoint

**Files:**
- Modify: `dashboard/server/routes/rest.py`

- [ ] **Step 1: Add the /api/positions endpoint**

In `dashboard/server/routes/rest.py`, add an import at the top and a new route after the `/api/packet` endpoint (after line 49):

First, add `import sqlite3, json` at the top:

```python
# receiver-server/routes/rest.py
"""REST endpoints — health check, packet query, device enumeration."""

from typing import Optional
import sqlite3
import json

from fastapi import APIRouter, Body, HTTPException, Query
```

Then add the new route (after line 49, before the `/api/devices` route):

```python
@router.get("/api/positions")
async def get_positions(since: int = Query(0), limit: int = Query(5000)):
    """Return position packets from SQLite for map trail rendering."""
    if receiver_manager is None or receiver_manager._db_conn is None:
        return []
    try:
        conn = receiver_manager._db_conn
        rows = conn.execute(
            "SELECT seq, received_at, payload FROM packets "
            "WHERE type = 'position' AND seq > ? "
            "ORDER BY seq ASC LIMIT ?",
            (since, limit),
        ).fetchall()
        result = []
        for seq, received_at, payload_str in rows:
            payload = json.loads(payload_str)
            result.append({
                "seq": seq,
                "received_at": received_at,
                "lat": payload.get("lat", 0),
                "lon": payload.get("lon", 0),
                "alt_m": payload.get("alt_m", 0),
            })
        return result
    except Exception:
        return []
```

- [ ] **Step 2: Test the endpoint**

Start the server and sim, then curl:

```bash
curl -s http://localhost:8000/api/positions?since=0 | python -c "
import json, sys
data = json.load(sys.stdin)
assert isinstance(data, list), 'Expected a list'
if len(data) > 0:
    first = data[0]
    assert 'lat' in first, f'Missing lat in {first}'
    assert 'lon' in first, f'Missing lon in {first}'
    print(f'PASS: got {len(data)} positions, first: lat={first[\"lat\"]} lon={first[\"lon\"]}')
else:
    print('WARN: no positions yet (maybe sim not running)')
"
```

Expected: `PASS: got N positions...` or `WARN: no positions yet` (acceptable if sim not running)

- [ ] **Step 3: Commit**

```bash
git add dashboard/server/routes/rest.py
git commit -m "feat: add GET /api/positions endpoint for map trail data"
```

---

### Task 4: Wire database_path through main.py

**Files:**
- Modify: `dashboard/server/main.py`

- [ ] **Step 1: Import ServerConfig and pass db_path to ReceiverManager**

In `dashboard/server/main.py`, change the import from `from config import ReceiverConfig` to `from config import ServerConfig, ReceiverConfig`, then pass database_path:

```python
from config import ServerConfig, ReceiverConfig
from ws_manager import WebSocketManager
from receiver_manager import ReceiverManager
```

Then in `create_app()` (line 34), add `ServerConfig` and pass `database_path`:

```python
def create_app() -> FastAPI:
    server_config = ServerConfig()
    receiver_config = ReceiverConfig()
    ws_manager = WebSocketManager()
    receiver_manager = ReceiverManager(
        ws_manager,
        receiver_config,
        db_path=server_config.database_path,
    )
```

- [ ] **Step 2: Verify the server starts without errors**

```bash
cd dashboard/server && python main.py &
sleep 2
curl -s http://localhost:8000/health
kill %1 2>/dev/null
```

Expected: `{"status":"ok"}`

- [ ] **Step 3: Commit**

```bash
git add dashboard/server/main.py
git commit -m "feat: wire database_path from ServerConfig to ReceiverManager"
```

---

### Task 5: Add loadPositions to useHabApi hook

**Files:**
- Modify: `dashboard/web/src/hooks/useHabApi.ts`

- [ ] **Step 1: Add loadPositions function and export it**

In `dashboard/web/src/hooks/useHabApi.ts`, add this function before the `return` statement (after line 399, before line 401):

```typescript
const loadPositions = useCallback(async (since: number = 0): Promise<Array<{seq: number; lat: number; lon: number; alt_m: number}>> => {
  try {
    const host = window.location.hostname;
    const res = await fetch(`http://${host}:8000/api/positions?since=${since}&limit=5000`);
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}, []);
```

Then add `loadPositions` to the return object (after `metricHistory` on line 424):

```typescript
return {
    connected,
    connecting,
    phase,
    missionTime,
    current,
    history,
    packets,
    packetsReceiving,
    newLinkStatus,
    engineStatus,
    spectrum,
    sendCommand,
    connectionLog,
    clearLog,
    position,
    motion,
    environment,
    power,
    logEntries,
    packetRate,
    lastPacketAge,
    packetSeq,
    metricHistory,
    loadPositions,
};
```

- [ ] **Step 2: Build the frontend to check for type errors**

```bash
cd dashboard/web && npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add dashboard/web/src/hooks/useHabApi.ts
git commit -m "feat: add loadPositions function to useHabApi hook"
```

---

### Task 6: Rewrite MapCard to use live Leaflet map

**Files:**
- Modify: `dashboard/web/src/components/MapCard.tsx`

- [ ] **Step 1: Replace MapCard with Leaflet implementation**

Replace the entire contents of `dashboard/web/src/components/MapCard.tsx`:

```tsx
import { useEffect, useRef, useState, useMemo } from 'react';
import { MapContainer, TileLayer, Polyline, CircleMarker, Popup } from 'react-leaflet';
import type { LatLngTuple } from 'leaflet';
import L from 'leaflet';

interface PositionPoint {
  seq: number;
  lat: number;
  lon: number;
  alt_m: number;
}

interface MapCardProps {
  lat: number;
  lon: number;
  alt_m: number;
  loadPositions: (since: number) => Promise<PositionPoint[]>;
}

const DARK_TILE_URL = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
const DARK_TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>';

const TRAIL_COLOR = { color: '#abc7ff', weight: 2, opacity: 0.8 };

function formatLatLng(lat: number, lon: number): string {
  const latDir = lat >= 0 ? 'N' : 'S';
  const lonDir = lon >= 0 ? 'E' : 'W';
  return `${Math.abs(lat).toFixed(4)}°${latDir} ${Math.abs(lon).toFixed(4)}°${lonDir}`;
}

export function MapCard({ lat, lon, alt_m, loadPositions }: MapCardProps) {
  const [trail, setTrail] = useState<LatLngTuple[]>([]);
  const [lastLoadedSeq, setLastLoadedSeq] = useState(0);
  const mapRef = useRef<L.Map | null>(null);
  const prevPositionRef = useRef<LatLngTuple | null>(null);

  // Load initial trail on mount
  useEffect(() => {
    let cancelled = false;
    loadPositions(0).then((positions) => {
      if (cancelled) return;
      if (positions.length > 0) {
        const points: LatLngTuple[] = positions.map((p) => [p.lat, p.lon]);
        setTrail(points);
        setLastLoadedSeq(positions[positions.length - 1].seq);
      }
    });
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Append new position to trail when props change
  useEffect(() => {
    const pos: LatLngTuple = [lat, lon];
    // Avoid duplicates if the position hasn't changed
    if (
      prevPositionRef.current &&
      prevPositionRef.current[0] === pos[0] &&
      prevPositionRef.current[1] === pos[1]
    ) {
      return;
    }
    prevPositionRef.current = pos;
    setTrail((prev) => [...prev, pos]);
  }, [lat, lon]);

  // Reload trail from DB when sim restarts (seq wraps)
  useEffect(() => {
    const interval = setInterval(() => {
      loadPositions(lastLoadedSeq).then((positions) => {
        if (positions.length > 0) {
          setTrail((prev) => {
            const newPoints: LatLngTuple[] = positions.map((p) => [p.lat, p.lon]);
            return [...prev, ...newPoints];
          });
          setLastLoadedSeq(positions[positions.length - 1].seq);
        }
      });
    }, 10000);
    return () => clearInterval(interval);
  }, [lastLoadedSeq, loadPositions]);

  // Auto-pan on new position
  useEffect(() => {
    if (mapRef.current) {
      mapRef.current.panTo([lat, lon], { animate: true, duration: 1 });
    }
  }, [lat, lon]);

  const center: LatLngTuple = useMemo(() => {
    if (trail.length > 0) return trail[trail.length - 1];
    return [lat || 39.0, lon || -98.0] as LatLngTuple;
  }, [trail, lat, lon]);

  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant flex flex-col h-[35%] min-h-[200px]">
      <div className="p-3 border-b border-outline-variant flex justify-between items-center">
        <span className="data-label text-label-caps text-outline">LIVE MAP</span>
        <span className="text-[10px] font-mono text-outline">
          {trail.length > 0 ? `${trail.length} pts` : 'NO DATA'}
        </span>
      </div>
      <div className="flex-1 relative overflow-hidden">
        <MapContainer
          center={center}
          zoom={5}
          className="h-full w-full"
          zoomControl={false}
          ref={mapRef}
          style={{ background: '#1a1a2e' }}
        >
          <TileLayer url={DARK_TILE_URL} attribution={DARK_TILE_ATTR} />
          {trail.length >= 2 && (
            <Polyline positions={trail} pathOptions={TRAIL_COLOR} />
          )}
          <CircleMarker
            center={[lat, lon]}
            radius={5}
            pathOptions={{ color: '#abc7ff', fillColor: '#abc7ff', fillOpacity: 0.8, weight: 2 }}
          >
            <Popup>
              <div className="text-xs font-mono">
                <div>{formatLatLng(lat, lon)}</div>
                <div>Altitude: {alt_m.toFixed(0)} m</div>
              </div>
            </Popup>
          </CircleMarker>
        </MapContainer>
        <div className="absolute bottom-2 left-2 right-2 bg-surface/80 p-2 text-[10px] font-mono card-border border border-outline-variant/50 rounded z-[1000] pointer-events-none">
          {formatLatLng(lat, lon)} | Alt: {alt_m.toFixed(0)}m
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update MissionControl to pass loadPositions**

In `dashboard/web/src/components/MissionControl.tsx`, add `loadPositions` to the interface and pass it to MapCard.

```tsx
interface MissionControlProps {
  position: PositionData;
  motion: MotionData;
  environment: EnvironmentData;
  power: PowerData;
  linkStatus: LinkStatus;
  packetRate: number;
  sequence: number;
  logEntries: LogEntry[];
  lastPacketAge: number;
  loadPositions: (since: number) => Promise<Array<{seq: number; lat: number; lon: number; alt_m: number}>>;
}
```

And update the destructured props (after line 30):

```tsx
export function MissionControl({
  position,
  motion,
  environment,
  power,
  linkStatus,
  packetRate,
  sequence,
  logEntries,
  lastPacketAge,
  loadPositions,
}: MissionControlProps) {
```

And update the MapCard usage (line 48):

```tsx
<MapCard lat={position.lat} lon={position.lon} alt_m={position.alt_m} loadPositions={loadPositions} />
```

- [ ] **Step 3: Update App.tsx to pass loadPositions**

In `dashboard/web/src/App.tsx`, add `loadPositions` to the destructured hook values (line 13):

```tsx
const {
    connected,
    phase,
    missionTime,
    position,
    motion,
    environment,
    power,
    logEntries,
    packetRate,
    lastPacketAge,
    packetSeq,
    engineStatus,
    loadPositions,
} = useHabApi();
```

Then pass it to MissionControl (line 57):

```tsx
<MissionControl
    position={position}
    motion={motion}
    environment={environment}
    power={power}
    linkStatus={{
        telemetry: connected ? 'NOMINAL' : 'OFFLINE',
        packet: connected ? 'NOMINAL' : 'OFFLINE',
        video: engineStatus?.pipeline?.running ? 'NOMINAL' : 'OFFLINE',
    }}
    packetRate={packetRate}
    sequence={packetSeq}
    logEntries={logEntries}
    lastPacketAge={lastPacketAge}
    loadPositions={loadPositions}
/>
```

- [ ] **Step 4: Build and typecheck**

```bash
cd dashboard/web && npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 5: Build for production**

```bash
cd dashboard/web && npm run build
```

Expected: build succeeds, `dist/` directory created

- [ ] **Step 6: Full integration test**

```bash
# Terminal 1: Start server
cd dashboard/server && python main.py

# Terminal 2: Start simulator
cd dashboard/sim && python sim.py --fast

# Terminal 3: Test the full stack
sleep 5
curl -s http://localhost:8000/api/positions?since=0 | python -c "
import json, sys
data = json.load(sys.stdin)
print(f'Positions loaded: {len(data)}')
assert len(data) > 0, 'Expected at least some positions'
print('PASS: positions endpoint working')
"

# Open browser at http://localhost:8000 — map should show trail + moving marker
```

- [ ] **Step 7: Commit**

```bash
git add dashboard/web/src/components/MapCard.tsx
git add dashboard/web/src/components/MissionControl.tsx
git add dashboard/web/src/App.tsx
git commit -m "feat: replace static SVG map with live Leaflet map showing balloon trail"
```
