# Dashboard UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize Mission Control dashboard into Map | Video | TelemetryCard | Terminal layout with live sparkline graphs and right-aligned values.

**Architecture:** Remove 7 scattered data cards, replace with a single `TelemetryCard` containing 4 always-expanded sections. Add a reusable `SparklineGraph` component using Recharts for line-only streaming graphs. Extend `useHabApi` with per-metric 60-second rolling buffers.

**Tech Stack:** React 18, TypeScript, Tailwind CSS 3, Recharts 2.12.7, framer-motion 11

---

### Task 1: Extend `useHabApi` with per-metric rolling window buffers

**Files:**
- Modify: `dashboard/web/src/hooks/useHabApi.ts`
- Modify: `dashboard/web/src/types.ts`

- [ ] **Step 1: Add `MetricPoint` type and return type placeholder to `types.ts`**

Add to the end of `dashboard/web/src/types.ts`:

```typescript
export interface MetricPoint {
  timestamp: number;
  value: number;
}
```

- [ ] **Step 2: Add `metricHistory` state and buffer logic to `useHabApi`**

In `dashboard/web/src/hooks/useHabApi.ts`, add the import for `MetricPoint`:

```typescript
import {
  TelemetrySample, FlightPhase, Packet, LinkStatus,
  PositionData, MotionData, EnvironmentData, PowerData,
  LogEntry, TelemetryMessage, MetricPoint,
} from '../types';
```

Add a `useRef` for the metric history (avoids re-render overhead, we'll compute a derived state):

After the existing refs (around line 106), add:

```typescript
const metricHistoryRef = useRef<{
  altitude: MetricPoint[];
  verticalSpeed: MetricPoint[];
  externalTemp: MetricPoint[];
  internalTemp: MetricPoint[];
  pressure: MetricPoint[];
  humidity: MetricPoint[];
  roll: MetricPoint[];
  pitch: MetricPoint[];
  yaw: MetricPoint[];
}>({
  altitude: [],
  verticalSpeed: [],
  externalTemp: [],
  internalTemp: [],
  pressure: [],
  humidity: [],
  roll: [],
  pitch: [],
  yaw: [],
});
```

Add a helper above the return statement (before `return {`):

```typescript
const ROLLING_WINDOW_MS = 60_000;

function pushMetric(key: keyof typeof metricHistoryRef.current, value: number) {
  const now = Date.now();
  const buf = metricHistoryRef.current;
  const arr = [...buf[key], { timestamp: now, value }];
  const cutoff = now - ROLLING_WINDOW_MS;
  buf[key] = arr.filter((p) => p.timestamp >= cutoff);
}
```

**Note:** `useRef` mutation does not trigger re-render. We expose a `useState`-based copy for the components. Add a state to drive re-renders:

After the existing state declarations (around line 96), add:

```typescript
const [metricHistory, setMetricHistory] = useState<typeof metricHistoryRef.current>(metricHistoryRef.current);
```

After each `pushMetric` call (in the websocket handler), we need to trigger a state update. Add a helper:

```typescript
function flushMetricHistory() {
  setMetricHistory({ ...metricHistoryRef.current });
}
```

Now wire the metrics into the WebSocket handler. In the `onmessage` handler, within the `if (msg.type === 'telemetry')` block:

After `if (data.type === 'position')` block (around line 159), inside the `setPosition(data)` line, add:

```typescript
pushMetric('altitude', data.alt_m);
```

After `if (data.type === 'motion')` block (around line 160-163), inside the `setMotion(data)` block, add:

```typescript
pushMetric('verticalSpeed', data.vs_mps);
pushMetric('roll', data.att_deg.roll);
pushMetric('pitch', data.att_deg.pitch);
pushMetric('yaw', data.att_deg.yaw);
```

After `if (data.type === 'environment')` block (around line 163-166), inside the `setEnvironment(data)` block, add:

```typescript
pushMetric('externalTemp', data.temp_ext_c);
pushMetric('internalTemp', data.temp_int_c);
pushMetric('pressure', data.pressure_hpa);
pushMetric('humidity', data.humidity_pct);
```

After all telemetry type handlers, call:

```typescript
flushMetricHistory();
```

Add `metricHistory` to the return object (around line 352-375):

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
};
```

- [ ] **Step 3: Verify the hook compiles**

Run: `npx tsc --noEmit` from `dashboard/web/`
Expected: No type errors.

- [ ] **Step 4: Commit**

```bash
git add dashboard/web/src/types.ts dashboard/web/src/hooks/useHabApi.ts
git commit -m "feat: add per-metric rolling window buffers to useHabApi"
```

---

### Task 2: Create `SparklineGraph` component

**Files:**
- Create: `dashboard/web/src/components/SparklineGraph.tsx`

- [ ] **Step 1: Write the component**

Create `dashboard/web/src/components/SparklineGraph.tsx`:

```typescript
import { useMemo } from 'react';
import { LineChart, Line, ReferenceLine, YAxis } from 'recharts';
import { MetricPoint } from '../types';

interface SparklineGraphProps {
  data: MetricPoint[];
  color: string;
  unitLabel: string;
  metricLabel: string;
  showZeroLine?: boolean;
}

function formatValue(value: number, metricLabel: string): string {
  if (metricLabel === 'ALT') return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value.toFixed(0);
  if (metricLabel === 'YAW') return value.toFixed(0);
  return value.toFixed(1);
}

function formatTick(value: number, metricLabel: string): string {
  if (metricLabel === 'ALT') return `${(value / 1000).toFixed(1)}k`;
  if (metricLabel === 'YAW') return value.toFixed(0);
  return value.toFixed(1);
}

export function SparklineGraph({
  data,
  color,
  unitLabel,
  metricLabel,
  showZeroLine = false,
}: SparklineGraphProps) {
  const currentValue = data.length > 0 ? data[data.length - 1].value : 0;

  const yTicks = useMemo(() => {
    if (data.length === 0) return [0, 0, 0];
    const values = data.map((d) => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return [min, min, min];
    const step = (max - min) / 3;
    return [max, max - step, min];
  }, [data]);

  const domain = useMemo(() => {
    if (data.length === 0) return [0, 1] as [number, number];
    const values = data.map((d) => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return [min - 1, max + 1] as [number, number];
    const padding = (max - min) * 0.1;
    return [min - padding, max + padding] as [number, number];
  }, [data]);

  if (data.length === 0) {
    return (
      <div>
        <div className="flex justify-between items-baseline mb-0.5">
          <span className="text-[9px] text-outline font-label-caps">{metricLabel}</span>
          <span>
            <span className="text-[11px] font-semibold text-on-surface">--</span>
            <span className="text-[8px] text-outline"> {unitLabel}</span>
          </span>
        </div>
        <div className="bg-surface-container-low rounded-[3px] h-12 flex items-center justify-center">
          <span className="text-[9px] text-outline">No data</span>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-baseline mb-0.5">
        <span className="text-[9px] text-outline font-label-caps">{metricLabel}</span>
        <span>
          <span className="text-[11px] font-semibold text-on-surface">{formatValue(currentValue, metricLabel)}</span>
          <span className="text-[8px] text-outline"> {unitLabel}</span>
        </span>
      </div>
      <div className="bg-surface-container-low rounded-[3px] h-12 relative overflow-hidden">
        <LineChart
          width={9999}
          height={48}
          data={data}
          margin={{ top: 4, right: 36, bottom: 4, left: 0 }}
        >
          {showZeroLine && (
            <ReferenceLine y={0} stroke="#414753" strokeDasharray="3 3" strokeWidth={0.5} />
          )}
          <YAxis
            type="number"
            domain={domain}
            hide
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>

        {/* Y-axis tick labels overlaid on right edge */}
        <div className="absolute right-1 top-1 bottom-1 flex flex-col justify-between pointer-events-none">
          {yTicks.map((tick, i) => (
            <span key={i} className="text-[6px] text-outline-variant text-right leading-none">
              {formatTick(tick, metricLabel)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the component compiles**

Run: `npx tsc --noEmit` from `dashboard/web/`
Expected: No type errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/web/src/components/SparklineGraph.tsx
git commit -m "feat: add SparklineGraph component with line-only rendering and y-axis ticks"
```

---

### Task 3: Create `TelemetryCard` component

**Files:**
- Create: `dashboard/web/src/components/TelemetryCard.tsx`

- [ ] **Step 1: Write the component**

Create `dashboard/web/src/components/TelemetryCard.tsx`:

```typescript
import {
  PositionData,
  MotionData,
  EnvironmentData,
  PowerData,
  LinkStatus,
  MetricPoint,
} from '../types';
import { SparklineGraph } from './SparklineGraph';

interface TelemetryCardProps {
  position: PositionData;
  motion: MotionData;
  environment: EnvironmentData;
  power: PowerData;
  linkStatus: LinkStatus;
  packetRate: number;
  metricHistory: {
    altitude: MetricPoint[];
    verticalSpeed: MetricPoint[];
    externalTemp: MetricPoint[];
    internalTemp: MetricPoint[];
    pressure: MetricPoint[];
    humidity: MetricPoint[];
    roll: MetricPoint[];
    pitch: MetricPoint[];
    yaw: MetricPoint[];
  };
}

function batteryColor(pct: number): string {
  if (pct > 50) return 'text-secondary';
  if (pct > 20) return 'text-tertiary';
  return 'text-reentry-red';
}

function linkDotColor(status: string): string {
  switch (status) {
    case 'NOMINAL': return 'bg-secondary';
    case 'DEGRADED': return 'bg-tertiary';
    default: return 'bg-reentry-red';
  }
}

function MetricRow({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-[9px] text-outline font-label-caps">{label}</span>
      <span>
        <span className="text-on-surface-variant">{value}</span>
        {unit && <span className="text-outline"> {unit}</span>}
      </span>
    </div>
  );
}

export function TelemetryCard({
  position,
  motion,
  environment,
  power,
  linkStatus,
  packetRate,
  metricHistory,
}: TelemetryCardProps) {
  return (
    <div className="bg-surface-container-low border border-outline-variant rounded-[20px] overflow-hidden flex flex-col h-full">
      {/* Card Header */}
      <div className="bg-surface-container-lowest px-4 py-3 border-b border-outline-variant">
        <span className="text-label-caps text-outline">TELEMETRY</span>
      </div>

      <div className="flex-1 overflow-y-auto">

        {/* Navigation Section */}
        <div className="px-3 py-3 border-b border-outline-variant/50">
          <span className="text-[9px] font-label-caps text-primary-container mb-3 block">NAVIGATION</span>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <SparklineGraph
              data={metricHistory.altitude}
              color="#2f80ed"
              unitLabel="m"
              metricLabel="ALT"
            />
            <SparklineGraph
              data={metricHistory.verticalSpeed}
              color="#4daa78"
              unitLabel="m/s"
              metricLabel="VS"
              showZeroLine
            />
          </div>

          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[9px]">
            <MetricRow label="GS" value={motion.gs_mps.toFixed(1)} unit="m/s" />
            <MetricRow label="HDG" value={motion.heading_deg.toFixed(0)} unit="°" />
            <MetricRow label="LAT" value={position.lat.toFixed(4)} unit="°N" />
            <MetricRow label="LON" value={position.lon.toFixed(4)} unit="°W" />
            <MetricRow label="SATS" value={String(position.sats)} />
            <MetricRow label="HDOP" value={position.hdop.toFixed(1)} />
          </div>
        </div>

        {/* Environment Section */}
        <div className="px-3 py-3 border-b border-outline-variant/50">
          <span className="text-[9px] font-label-caps text-primary-container mb-3 block">ENVIRONMENT</span>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <SparklineGraph
              data={metricHistory.externalTemp}
              color="#2f80ed"
              unitLabel="°C"
              metricLabel="EXT"
            />
            <SparklineGraph
              data={metricHistory.internalTemp}
              color="#e05344"
              unitLabel="°C"
              metricLabel="INT"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <SparklineGraph
              data={metricHistory.humidity}
              color="#7cd9a3"
              unitLabel="%"
              metricLabel="HUM"
            />
            <SparklineGraph
              data={metricHistory.pressure}
              color="#abc7ff"
              unitLabel="hPa"
              metricLabel="PRES"
            />
          </div>
        </div>

        {/* Power & Link Section */}
        <div className="px-3 py-3 border-b border-outline-variant/50">
          <span className="text-[9px] font-label-caps text-primary-container mb-3 block">POWER & LINK</span>

          <div className="flex justify-between items-baseline mb-2">
            <span className="text-[9px] text-outline font-label-caps">BAT</span>
            <div className="flex items-baseline gap-4">
              <span>
                <span className={`text-base font-semibold ${batteryColor(power.bat_pct)}`}>{power.bat_pct.toFixed(0)}</span>
                <span className="text-[10px] text-outline">%</span>
              </span>
              <span className="text-[9px] text-on-surface-variant">{power.bat_v.toFixed(1)}V / {power.bat_a.toFixed(1)}A</span>
            </div>
          </div>

          <div className="w-full h-1.5 bg-surface-container-highest rounded-full overflow-hidden mb-3">
            <div
              className="h-full rounded-full bg-secondary"
              style={{ width: `${Math.min(power.bat_pct, 100)}%` }}
            />
          </div>

          <div className="flex items-center gap-4 text-[9px]">
            <span className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${linkDotColor(linkStatus.telemetry)}`} />
              <span className="text-on-surface-variant">TEL</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${linkDotColor(linkStatus.packet)}`} />
              <span className="text-on-surface-variant">PKT</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${linkDotColor(linkStatus.video)}`} />
              <span className="text-on-surface-variant">VID</span>
            </span>
            <span className="ml-auto">
              <span className="text-[13px] font-semibold text-primary">{packetRate.toFixed(1)}</span>
              <span className="text-outline"> pkt/s</span>
            </span>
          </div>
        </div>

        {/* Attitude Section */}
        <div className="px-3 py-3">
          <span className="text-[9px] font-label-caps text-primary-container mb-3 block">ATTITUDE</span>

          <div className="grid grid-cols-3 gap-3">
            <SparklineGraph
              data={metricHistory.roll}
              color="#f5be4e"
              unitLabel="°"
              metricLabel="ROLL"
              showZeroLine
            />
            <SparklineGraph
              data={metricHistory.pitch}
              color="#f5be4e"
              unitLabel="°"
              metricLabel="PITCH"
              showZeroLine
            />
            <SparklineGraph
              data={metricHistory.yaw}
              color="#f5be4e"
              unitLabel="°"
              metricLabel="YAW"
            />
          </div>
        </div>

      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the component compiles**

Run: `npx tsc --noEmit` from `dashboard/web/`
Expected: No type errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/web/src/components/TelemetryCard.tsx
git commit -m "feat: add TelemetryCard with Navigation, Environment, Power&Link, and Attitude sections"
```

---

### Task 4: Rewrite `MissionControl` with new layout

**Files:**
- Modify: `dashboard/web/src/components/MissionControl.tsx`
- Modify: `dashboard/web/src/App.tsx`

- [ ] **Step 1: Rewrite `MissionControl.tsx`**

Replace the content of `dashboard/web/src/components/MissionControl.tsx` with:

```typescript
import { MapCard } from './MapCard';
import { CameraFeed } from './CameraFeed';
import { TelemetryCard } from './TelemetryCard';
import { PacketStream } from './PacketStream';
import {
  PositionData,
  MotionData,
  EnvironmentData,
  PowerData,
  LinkStatus,
  LogEntry,
  MetricPoint,
} from '../types';

interface MissionControlProps {
  position: PositionData;
  motion: MotionData;
  environment: EnvironmentData;
  power: PowerData;
  linkStatus: LinkStatus;
  packetRate: number;
  sequence: number;
  logEntries: LogEntry[];
  metricHistory: {
    altitude: MetricPoint[];
    verticalSpeed: MetricPoint[];
    externalTemp: MetricPoint[];
    internalTemp: MetricPoint[];
    pressure: MetricPoint[];
    humidity: MetricPoint[];
    roll: MetricPoint[];
    pitch: MetricPoint[];
    yaw: MetricPoint[];
  };
}

export function MissionControl({
  position,
  motion,
  environment,
  power,
  linkStatus,
  packetRate,
  sequence,
  logEntries,
  metricHistory,
}: MissionControlProps) {
  return (
    <>
      <main className="ml-[64px] mt-[72px] h-[calc(100vh-272px)] p-4 grid grid-cols-[2fr_3fr_2fr] gap-4">
        {/* Left Column: Map */}
        <section className="overflow-hidden">
          <MapCard lat={position.lat} lon={position.lon} alt_m={position.alt_m} />
        </section>

        {/* Center Column: Video Feed */}
        <section className="overflow-hidden">
          <CameraFeed />
        </section>

        {/* Right Column: Unified Telemetry Card */}
        <section className="overflow-hidden">
          <TelemetryCard
            position={position}
            motion={motion}
            environment={environment}
            power={power}
            linkStatus={linkStatus}
            packetRate={packetRate}
            metricHistory={metricHistory}
          />
        </section>
      </main>

      <PacketStream entries={logEntries} />
    </>
  );
}
```

- [ ] **Step 2: Update `App.tsx` to pass `metricHistory`**

In `dashboard/web/src/App.tsx`, add `metricHistory` to the destructured hook values (line 14-26):

```typescript
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
  metricHistory,
} = useHabApi();
```

(`lastPacketAge` stays — it's still used by TopBar.)

Then in the `<MissionControl>` JSX (around line 57), add the `metricHistory` prop:

```typescript
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
  metricHistory={metricHistory}
/>
```

- [ ] **Step 3: Verify full type-check**

Run: `npx tsc --noEmit` from `dashboard/web/`
Expected: No type errors.

- [ ] **Step 4: Commit**

```bash
git add dashboard/web/src/components/MissionControl.tsx dashboard/web/src/App.tsx
git commit -m "feat: rewrite MissionControl with Map|Video|TelemetryCard layout, pass metricHistory"
```

---

### Task 5: Delete old card components

**Files:**
- Delete: `dashboard/web/src/components/PositionCard.tsx`
- Delete: `dashboard/web/src/components/MotionCard.tsx`
- Delete: `dashboard/web/src/components/EnvironmentCard.tsx`
- Delete: `dashboard/web/src/components/PowerCard.tsx`
- Delete: `dashboard/web/src/components/RfLinkCard.tsx`
- Delete: `dashboard/web/src/components/AlertsCard.tsx`
- Delete: `dashboard/web/src/components/PacketRateCard.tsx`

- [ ] **Step 1: Delete the 7 card files**

```bash
rm dashboard/web/src/components/PositionCard.tsx
rm dashboard/web/src/components/MotionCard.tsx
rm dashboard/web/src/components/EnvironmentCard.tsx
rm dashboard/web/src/components/PowerCard.tsx
rm dashboard/web/src/components/RfLinkCard.tsx
rm dashboard/web/src/components/AlertsCard.tsx
rm dashboard/web/src/components/PacketRateCard.tsx
```

- [ ] **Step 2: Verify no broken imports**

Run: `npx tsc --noEmit` from `dashboard/web/`
Expected: No errors (no remaining imports of deleted files).

- [ ] **Step 3: Commit**

```bash
git add -u dashboard/web/src/components/
git commit -m "refactor: remove 7 obsolete data card components"
```

---

### Task 6: MapCard full-height adjustment

**Files:**
- Modify: `dashboard/web/src/components/MapCard.tsx`

The MapCard currently has a fixed height (`h-[35%] min-h-[200px]`). Now that it's the sole component in the left column, it should fill the available space.

- [ ] **Step 1: Remove fixed height, let MapCard fill the grid cell**

In `dashboard/web/src/components/MapCard.tsx`, change:

```
className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant flex flex-col h-[35%] min-h-[200px]"
```

to:

```
className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant flex flex-col h-full"
```

Full diff:

```diff
-<div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant flex flex-col h-[35%] min-h-[200px]">
+<div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant flex flex-col h-full">
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/web/src/components/MapCard.tsx
git commit -m "fix: make MapCard fill full column height"
```

---

### Task 7: Verify build and lint

- [ ] **Step 1: Run type-check**

Run: `npx tsc --noEmit` from `dashboard/web/`
Expected: No errors.

- [ ] **Step 2: Run lint**

```bash
npm run lint
```

Expected: No errors (may have pre-existing warnings unrelated to changes).

- [ ] **Step 3: Run build**

```bash
npm run build
```

Expected: Build succeeds without errors.

- [ ] **Step 4: Start dev server and inspect**

```bash
npm run dev
```

Open browser to verify:
- Three-column layout renders (Map | Video | TelemetryCard)
- Telemetry card shows all 4 sections
- Sparkline graphs render (even with simulated data from the hook defaults)
- Values are right-aligned against units
- Packet stream terminal at bottom
- Sidebar and TopBar still work

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: verify build, lint, and manual inspection pass"
```
