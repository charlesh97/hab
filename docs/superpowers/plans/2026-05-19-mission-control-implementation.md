# Mission Control Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing multi-page React dashboard with a single-screen mission control interface matching the Gemini wireframe layout (64px sidebar, 72px top bar, 3-column body with left telemetry/map, center camera, right RF/power/alerts, 200px bottom packet stream), plus a separate settings view with 5 sub-tabs.

**Architecture:** Single React SPA with two views (mission control, settings) toggled via sidebar nav. Keep existing Vite/React/TypeScript/Tailwind data hooks and WebSocket integration. Replace all presentational components with the wireframe layout. Use the exact Tailwind color tokens from the wireframe (`surface`, `surface-container-low`, `primary`, `secondary`, etc.) adapted into the existing Tailwind config. Retain Lucide React for icons.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS 3.4, Lucide React (icons), Framer Motion (packet stream animations), Leaflet/React-Leaflet (map), Recharts (charts — retained for future use but not on main view)

---

## File Structure

```
web-dashboard/
├── src/
│   ├── index.tsx                    # MODIFY: entry point (minor change)
│   ├── App.tsx                      # REPLACE: new two-view layout
│   ├── types.ts                     # MODIFY: add new telemetry types
│   ├── hooks/
│   │   └── useHabApi.ts            # MODIFY: adapt to new telemetry schema
│   └── components/
│       ├── TopBar.tsx               # REPLACE: wireframe-style top bar
│       ├── Sidebar.tsx              # CREATE: 64px icon sidebar
│       ├── MissionControl.tsx       # CREATE: main three-panel layout
│       ├── MapCard.tsx              # CREATE: SVG map placeholder in left panel
│       ├── PositionCard.tsx         # CREATE: position telemetry card
│       ├── MotionCard.tsx           # CREATE: motion telemetry card
│       ├── EnvironmentCard.tsx      # CREATE: environment telemetry card
│       ├── CameraFeed.tsx           # CREATE: center panel video placeholder
│       ├── RfLinkCard.tsx           # CREATE: RF link status card
│       ├── PowerCard.tsx            # CREATE: power telemetry card
│       ├── AlertsCard.tsx           # CREATE: system alerts card
│       ├── PacketRateCard.tsx       # CREATE: packet rate + sparkline
│       ├── PacketStream.tsx         # REPLACE: bottom packet stream log
│       ├── SettingsPage.tsx         # REPLACE: settings with 5 sub-tabs
│       ├── SettingsTabs.tsx         # CREATE: settings sub-tab navigation
│       ├── SettingsDevice.tsx       # CREATE: device discovery tab
│       ├── SettingsRf.tsx           # CREATE: RF parameters tab
│       ├── SettingsDvbs2.tsx        # CREATE: DVB-S2 config tab
│       ├── SettingsPipeline.tsx     # CREATE: pipeline controls tab
│       ├── SettingsAbout.tsx        # CREATE: about/system info tab
│       ├── ConnectionLog.tsx        # KEEP (minor style update)
│       └── ErrorBoundary.tsx        # KEEP (no changes)
```

### Files to DELETE

```
web-dashboard/src/components/
├── HeroStage.tsx                    # DELETE
├── AssetCard.tsx                    # DELETE
├── MissionSettingsGrid.tsx          # DELETE
├── TrajectoryCard.tsx               # DELETE
├── TelemetryGrid.tsx                # DELETE
├── TelemetryCharts.tsx              # DELETE
├── LowerTabs.tsx                    # DELETE
├── VideoFeeds.tsx                   # DELETE
├── DataStream.tsx                   # DELETE (replaced by PacketStream)
├── DeviceStatusPanel.tsx            # DELETE
├── SpectrumWaterfall.tsx            # DELETE (no spectrum in main view)
├── StatusBar.tsx                    # DELETE (no status bar in wireframe)
├── PipelineControls.tsx             # DELETE (replaced by SettingsPipeline)
├── PipelineDebug.tsx                # DELETE (merged into SettingsPipeline)
├── RfConfig.tsx                     # DELETE (replaced by SettingsRf/SettingsDvbs2)
├── TxControls.tsx                   # DELETE (merged into SettingsRf)
├── FlightMap.tsx                    # DELETE (replaced by MapCard with SVG placeholder)
├── Shared.tsx                       # DELETE (no longer needed)
```

### Files to KEEP (no changes)

```
web-dashboard/src/
├── index.css                        # KEEP
├── vite-env.d.ts                    # KEEP
├── components/ErrorBoundary.tsx     # KEEP
├── components/ConnectionLog.tsx     # KEEP (minor style updates inline)
```

---

### Task 1: Update Tailwind Config and Types

**Files:**
- Modify: `web-dashboard/tailwind.config.js`
- Modify: `web-dashboard/src/types.ts`
- Modify: `web-dashboard/src/index.css`

- [ ] **Step 1: Update Tailwind theme with wireframe colors**

Replace `web-dashboard/tailwind.config.js`:

```js
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'surface': '#0b141c',
        'surface-container': '#182028',
        'surface-container-low': '#141c24',
        'surface-container-lowest': '#060f16',
        'surface-container-high': '#222b33',
        'surface-container-highest': '#2d363e',
        'surface-bright': '#313a43',
        'surface-dim': '#0b141c',
        'surface-variant': '#2d363e',
        'outline': '#8b919f',
        'outline-variant': '#414753',
        'primary': '#abc7ff',
        'primary-container': '#448ffd',
        'secondary': '#7cd9a3',
        'secondary-container': '#027548',
        'tertiary': '#f5be4e',
        'tertiary-container': '#b9891a',
        'on-surface': '#dae3ee',
        'on-surface-variant': '#c1c6d5',
        'on-primary': '#002f65',
        'on-primary-container': '#002959',
        'on-secondary': '#003920',
        'on-secondary-container': '#9af8bf',
        'on-tertiary': '#412d00',
        'on-tertiary-container': '#382700',
        'telemetry-blue': '#2f80ed',
        'tracking-green': '#4daa78',
        'reentry-red': '#e05344',
        'background': '#0b141c',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        'mono-data': ['13px', { lineHeight: '16px', fontWeight: '400' }],
        'label-caps': ['11px', { lineHeight: '12px', letterSpacing: '0.06em', fontWeight: '600' }],
        'telemetry-lg': ['32px', { lineHeight: '32px', letterSpacing: '-0.04em', fontWeight: '600' }],
        'mission-name': ['34px', { lineHeight: '40px', letterSpacing: '-0.02em', fontWeight: '700' }],
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 2: Update types.ts with new telemetry schema**

Replace `web-dashboard/src/types.ts`:

```ts
export type FlightPhase = 'PRE-LAUNCH' | 'ASCENT' | 'FLOAT' | 'DESCENT' | 'RECOVERED';

export interface PositionData {
  lat: number;
  lon: number;
  alt_m: number;
  agl_m: number;
  fix: boolean;
  fix_type: string;
  sats: number;
  hdop: number;
  vdop: number;
}

export interface MotionData {
  gs_mps: number;
  vs_mps: number;
  heading_deg: number;
  cog_deg: number;
  accel: { x: number; y: number; z: number };
  gyro_dps: { r: number; p: number; y: number };
  att_deg: { roll: number; pitch: number; yaw: number };
}

export interface EnvironmentData {
  temp_ext_c: number;
  temp_int_c: number;
  pressure_hpa: number;
  humidity_pct: number;
  baro_alt_m: number;
}

export interface PowerData {
  bat_v: number;
  bat_a: number;
  bat_w: number;
  bat_pct: number;
  bat_temp_c: number;
  rails_v: { v5: number; v3v3: number; v1v8: number };
}

export interface TelemetryPacket {
  v: number;
  id: string;
  mid: string;
  seq: number;
  t: string;
  type: 'position' | 'motion' | 'environment' | 'power';
}

export interface PositionPacket extends TelemetryPacket, PositionData { type: 'position'; }
export interface MotionPacket extends TelemetryPacket, MotionData { type: 'motion'; }
export interface EnvironmentPacket extends TelemetryPacket, EnvironmentData { type: 'environment'; }
export interface PowerPacket extends TelemetryPacket, PowerData { type: 'power'; }

export type TelemetryMessage = PositionPacket | MotionPacket | EnvironmentPacket | PowerPacket;

export interface LogEntry {
  timestamp: string;
  type: 'POS' | 'MOT' | 'ENV' | 'PWR' | 'SYS';
  payload: string;
}

export interface EngineStatus {
  running: boolean;
  tx_active: boolean;
  device_connected: boolean;
  device_serial?: string;
  frequency: number;
  symbol_rate: number;
  uptime_sec: number;
  pipeline: { running: boolean; file_path: string; bitrate: number } | null;
  error_count?: number;
  last_error?: string;
  rx_active?: boolean;
}

export interface LinkStatus {
  telemetry: 'NOMINAL' | 'DEGRADED' | 'OFFLINE';
  packet: 'NOMINAL' | 'DEGRADED' | 'OFFLINE';
  video: 'NOMINAL' | 'DEGRADED' | 'OFFLINE';
}

export interface RfConfig {
  frequency: number;
  symbol_rate: number;
  lo_ppm: number;
  lna_gain: number;
  vga_gain: number;
  amp_enabled: boolean;
}

export interface Dvbs2Config {
  modcod: string;
  pilots: boolean;
  rolloff: number;
  fec_frame: 'NORMAL' | 'SHORT';
  symbol_rate: number;
  sps: number;
  rrc_delay: number;
  gold_code: number;
  fullscale: number;
  sink_type: string;
  device_args: string;
}

export interface PipelineConfig {
  file_path: string;
  running: boolean;
  bitrate: number;
  duration: string;
  errors: number;
}

export interface ConnectionLogEntry {
  timestamp: number;
  message: string;
  type: 'info' | 'error' | 'warning';
}
```

- [ ] **Step 3: Simplify index.css background**

Replace the body background in `web-dashboard/src/index.css` by adding after the existing custom scrollbar section:

```css
body {
  background-color: #0b141c;
  background-image: radial-gradient(circle at 2px 2px, #30363d 1px, transparent 0);
  background-size: 32px 32px;
}
```

- [ ] **Step 4: Commit**

```bash
git add web-dashboard/tailwind.config.js web-dashboard/src/types.ts web-dashboard/src/index.css
git commit -m "feat: update Tailwind theme, types, and styles for mission control dashboard"
```

---

### Task 2: Create Sidebar Component

**Files:**
- Create: `web-dashboard/src/components/Sidebar.tsx`
- Modify: `web-dashboard/src/index.tsx` (check import)

- [ ] **Step 1: Write Sidebar component**

Create `web-dashboard/src/components/Sidebar.tsx`:

```tsx
import { Monitor, Settings, Radio, Info, ChevronLeft } from 'lucide-react';

interface SidebarProps {
  activeView: 'mission-control' | 'settings';
  onViewChange: (view: 'mission-control' | 'settings') => void;
}

export function Sidebar({ activeView, onViewChange }: SidebarProps) {
  return (
    <aside className="fixed left-0 top-0 h-full w-[64px] bg-surface-container-low border-r border-outline-variant flex flex-col items-center py-4 z-40">
      <div className="mb-8 text-primary">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
        </svg>
      </div>

      <nav className="flex flex-col gap-4 flex-1">
        <button
          onClick={() => onViewChange('mission-control')}
          className={`w-12 h-12 flex items-center justify-center rounded-lg transition-colors ${
            activeView === 'mission-control'
              ? 'bg-primary-container text-on-primary-container scale-95'
              : 'text-on-surface-variant hover:bg-surface-container-highest'
          }`}
          title="Mission Control"
        >
          <Monitor size={22} />
        </button>
        <button
          onClick={() => onViewChange('settings')}
          className={`w-12 h-12 flex items-center justify-center rounded-lg transition-colors ${
            activeView === 'settings'
              ? 'bg-primary-container text-on-primary-container scale-95'
              : 'text-on-surface-variant hover:bg-surface-container-highest'
          }`}
          title="Settings"
        >
          <Settings size={22} />
        </button>
        <button
          className="w-12 h-12 flex items-center justify-center text-on-surface-variant hover:bg-surface-container-highest transition-colors rounded-lg"
          title="RF Config"
        >
          <Radio size={22} />
        </button>
        <button
          className="w-12 h-12 flex items-center justify-center text-on-surface-variant hover:bg-surface-container-highest transition-colors rounded-lg"
          title="About"
        >
          <Info size={22} />
        </button>
      </nav>

      <button className="w-12 h-12 flex items-center justify-center text-outline hover:text-on-surface transition-colors">
        <ChevronLeft size={22} />
      </button>
    </aside>
  );
}
```

- [ ] **Step 2: Verify TypeScript compilation**

```bash
npx tsc --noEmit --project web-dashboard/tsconfig.json
```

Expected: No errors related to Sidebar.tsx

- [ ] **Step 3: Commit**

```bash
git add web-dashboard/src/components/Sidebar.tsx
git commit -m "feat: add sidebar navigation component"
```

---

### Task 3: Create TopBar Component

**Files:**
- Replace: `web-dashboard/src/components/TopBar.tsx`

- [ ] **Step 1: Write TopBar component**

Replace `web-dashboard/src/components/TopBar.tsx`:

```tsx
import { FlightPhase } from '../types';

const phaseColors: Record<FlightPhase, string> = {
  'PRE-LAUNCH': 'bg-slate-700 text-slate-300',
  'ASCENT': 'bg-primary-container text-on-primary-container',
  'FLOAT': 'bg-secondary-container text-on-secondary-container',
  'DESCENT': 'bg-tertiary-container text-on-tertiary',
  'RECOVERED': 'bg-secondary-container text-on-secondary-container',
};

interface TopBarProps {
  phase: FlightPhase;
  missionTime: number;
  connected: boolean;
  currentLat?: number;
  currentLon?: number;
  lastPacketAge?: number;
}

function formatMissionTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `T+${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function lastPacketColor(age: number): string {
  if (age < 5) return 'text-secondary';
  if (age < 15) return 'text-tertiary';
  return 'text-reentry-red';
}

export function TopBar({ phase, missionTime, connected, currentLat, currentLon, lastPacketAge = 1.2 }: TopBarProps) {
  return (
    <header className="fixed top-0 left-[64px] right-0 h-[72px] bg-surface flex justify-between items-center px-[12px] z-50 border-b border-outline-variant">
      <div className="flex items-center gap-6">
        <div className="flex flex-col">
          <h1 className="font-mission-name text-mission-name font-bold leading-tight text-on-surface">
            ⦿ HAB-1 STRATOS
          </h1>
          <div className="flex gap-4 text-[10px] text-outline font-mono">
            <span>ID: #521514</span>
            {currentLat !== undefined && currentLon !== undefined && (
              <span>COORDS: {currentLat.toFixed(4)}°N / {currentLon.toFixed(4)}°W</span>
            )}
          </div>
        </div>
        <div className="h-8 w-px bg-outline-variant" />
        <div className={`px-3 py-1 font-label-caps text-label-caps rounded-sm flex items-center gap-2 ${phaseColors[phase]}`}>
          <span className="text-[14px]">{phase === 'ASCENT' ? '▲' : phase === 'DESCENT' ? '▼' : '●'}</span>
          {phase}
        </div>
      </div>

      <div className="flex items-center gap-8">
        <div className="flex items-center gap-6 text-[12px] font-mono">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-secondary' : 'bg-reentry-red'}`} />
            <span className={connected ? 'text-secondary' : 'text-reentry-red'}>
              {connected ? 'NOMINAL' : 'OFFLINE'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-secondary" />
            <span className="text-secondary">GPS LOCK</span>
          </div>
          <div className="text-outline">
            Last pkt: <span className={`${lastPacketColor(lastPacketAge)} text-on-surface`}>{lastPacketAge.toFixed(1)}s</span>
          </div>
        </div>
        <div className="font-telemetry-lg text-telemetry-lg tracking-tighter text-primary">
          {formatMissionTime(missionTime)}
        </div>
      </div>
    </header>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web-dashboard/src/components/TopBar.tsx
git commit -m "feat: replace top bar with wireframe-style mission header"
```

---

### Task 4: Create Left Panel Cards (Map, Position, Motion, Environment)

**Files:**
- Create: `web-dashboard/src/components/MapCard.tsx`
- Create: `web-dashboard/src/components/PositionCard.tsx`
- Create: `web-dashboard/src/components/MotionCard.tsx`
- Create: `web-dashboard/src/components/EnvironmentCard.tsx`

- [ ] **Step 1: Create MapCard**

Create `web-dashboard/src/components/MapCard.tsx`:

```tsx
interface MapCardProps {
  lat: number;
  lon: number;
  alt_m: number;
}

export function MapCard({ lat, lon, alt_m }: MapCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant flex flex-col h-[35%] min-h-[200px]">
      <div className="p-3 border-b border-outline-variant flex justify-between items-center">
        <span className="data-label text-label-caps text-outline">LIVE MAP</span>
        <span className="text-[10px] font-mono text-outline">v2.4-STABLE</span>
      </div>
      <div className="flex-1 bg-surface-container-lowest relative overflow-hidden">
        <div className="absolute inset-0 opacity-20 pointer-events-none"
          style={{
            backgroundImage: 'linear-gradient(#30363d 1px, transparent 1px), linear-gradient(90deg, #30363d 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        />
        <svg className="w-full h-full p-4" viewBox="0 0 200 120">
          <path d="M 20 100 Q 100 0 180 80" fill="none" stroke="#2F80ED" strokeDasharray="4 2" strokeWidth="2" />
          <circle cx="20" cy="100" fill="#4daa78" r="3" />
          <circle className="animate-pulse" cx="120" cy="35" fill="#abc7ff" r="4" />
          <path d="M 175 75 L 185 85 M 185 75 L 175 85" stroke="#e05344" strokeWidth="2" />
        </svg>
        <div className="absolute bottom-2 left-2 right-2 bg-surface/80 p-2 text-[10px] font-mono card-border border border-outline-variant/50 rounded">
          {lat.toFixed(4)}°N {lon.toFixed(4)}°W | Alt: {alt_m.toFixed(0)}m
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create PositionCard**

Create `web-dashboard/src/components/PositionCard.tsx`:

```tsx
import { PositionData } from '../types';

interface PositionCardProps {
  position: PositionData;
}

export function PositionCard({ position }: PositionCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant p-3 flex flex-col gap-4">
      <div>
        <span className="data-label block mb-2 text-label-caps text-outline">POSITION DATA</span>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-[10px] text-outline font-label-caps">SATS</div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xl text-primary">{position.sats}</span>
              <span className="px-1 text-[8px] border border-secondary text-secondary rounded">
                {position.fix_type.toUpperCase()} FIX
              </span>
            </div>
          </div>
          <div>
            <div className="text-[10px] text-outline font-label-caps">HDOP / VDOP</div>
            <div className="font-mono text-xl text-on-surface">
              {position.hdop.toFixed(2)} <span className="text-outline">/</span> {position.vdop.toFixed(2)}
            </div>
          </div>
        </div>
        <div className="mt-2">
          <div className="text-[10px] text-outline font-label-caps">AGL (ALTITUDE)</div>
          <div className="font-telemetry-lg text-primary">
            {position.agl_m.toFixed(0)}<span className="text-sm opacity-50 ml-1">m</span>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create MotionCard**

Create `web-dashboard/src/components/MotionCard.tsx`:

```tsx
import { MotionData } from '../types';

interface MotionCardProps {
  motion: MotionData;
}

export function MotionCard({ motion }: MotionCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant p-3 flex flex-col gap-3">
      <span className="data-label block text-label-caps text-outline">MOTION</span>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        <div className="flex flex-col">
          <span className="text-[10px] text-outline font-label-caps">GROUND SPEED</span>
          <span className="font-mono text-lg text-on-surface">
            {motion.gs_mps.toFixed(1)} <span className="text-[10px] opacity-50">m/s</span>
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-outline font-label-caps">VERT SPEED</span>
          <span className={`font-mono text-lg ${motion.vs_mps >= 0 ? 'text-secondary' : 'text-tertiary'}`}>
            {motion.vs_mps.toFixed(1)} <span className="text-[10px]">{motion.vs_mps >= 0 ? '▲' : '▼'} m/s</span>
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-outline font-label-caps">HEADING</span>
          <span className="font-mono text-lg text-on-surface">{motion.heading_deg.toFixed(1)}°</span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-outline font-label-caps">COURSE</span>
          <span className="font-mono text-lg text-on-surface">{motion.cog_deg.toFixed(1)}°</span>
        </div>
      </div>

      <div className="border-t border-outline-variant/50 pt-2">
        <div className="text-[10px] text-outline font-label-caps mb-1">ACCELEROMETER</div>
        <div className="font-mono text-xs text-on-surface-variant">
          x:{motion.accel.x.toFixed(2)} y:{motion.accel.y.toFixed(2)} z:{motion.accel.z.toFixed(2)}
        </div>
      </div>

      <div>
        <div className="text-[10px] text-outline font-label-caps mb-1">GYROSCOPE</div>
        <div className="font-mono text-xs text-on-surface-variant">
          r:{motion.gyro_dps.r.toFixed(1)} p:{motion.gyro_dps.p.toFixed(1)} y:{motion.gyro_dps.y.toFixed(1)}
        </div>
      </div>

      <div>
        <div className="text-[10px] text-outline font-label-caps mb-1">ATTITUDE</div>
        <div className="font-mono text-xs text-on-surface-variant">
          roll {motion.att_deg.roll.toFixed(1)}° pitch {motion.att_deg.pitch.toFixed(1)}° yaw {motion.att_deg.yaw.toFixed(1)}°
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create EnvironmentCard**

Create `web-dashboard/src/components/EnvironmentCard.tsx`:

```tsx
import { EnvironmentData } from '../types';

interface EnvironmentCardProps {
  environment: EnvironmentData;
}

export function EnvironmentCard({ environment }: EnvironmentCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant p-3 flex-1">
      <span className="data-label block mb-2 text-label-caps text-outline">ENVIRONMENT</span>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <div>
            <div className="text-[10px] text-outline font-label-caps">EXT TEMP</div>
            <div className={`font-mono text-xl ${environment.temp_ext_c < 0 ? 'text-tertiary' : 'text-on-surface'}`}>
              {environment.temp_ext_c.toFixed(1)}°C
            </div>
          </div>
          <div>
            <div className="text-[10px] text-outline font-label-caps">PRESSURE</div>
            <div className="font-mono text-xl text-on-surface">
              {environment.pressure_hpa.toFixed(1)} <span className="text-xs opacity-50">hPa</span>
            </div>
          </div>
        </div>
        <div className="space-y-2">
          <div>
            <div className="text-[10px] text-outline font-label-caps">INT TEMP</div>
            <div className="font-mono text-xl text-on-surface">{environment.temp_int_c.toFixed(1)}°C</div>
          </div>
          <div>
            <div className="text-[10px] text-outline font-label-caps">HUMIDITY</div>
            <div className="font-mono text-xl text-on-surface">{environment.humidity_pct.toFixed(1)}%</div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add web-dashboard/src/components/MapCard.tsx web-dashboard/src/components/PositionCard.tsx web-dashboard/src/components/MotionCard.tsx web-dashboard/src/components/EnvironmentCard.tsx
git commit -m "feat: add left panel telemetry cards (map, position, motion, environment)"
```

---

### Task 5: Create Right Panel Cards (RF Link, Power, Alerts, Packet Rate)

**Files:**
- Create: `web-dashboard/src/components/RfLinkCard.tsx`
- Create: `web-dashboard/src/components/PowerCard.tsx`
- Create: `web-dashboard/src/components/AlertsCard.tsx`
- Create: `web-dashboard/src/components/PacketRateCard.tsx`

- [ ] **Step 1: Create RfLinkCard**

Create `web-dashboard/src/components/RfLinkCard.tsx`:

```tsx
import { LinkStatus } from '../types';

interface RfLinkCardProps {
  linkStatus: LinkStatus;
  frequency?: number;
  snr?: number;
}

function statusColor(status: string): string {
  switch (status) {
    case 'NOMINAL': return 'bg-secondary-container text-on-secondary-container';
    case 'DEGRADED': return 'bg-tertiary-container/30 text-tertiary';
    default: return 'bg-reentry-red/20 text-reentry-red';
  }
}

export function RfLinkCard({ linkStatus, frequency = 915, snr = 12.3 }: RfLinkCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant p-3">
      <span className="data-label block mb-3 text-label-caps text-outline">RF LINK STATUS</span>
      <div className="flex gap-2 mb-4">
        <div className={`px-2 py-1 text-[10px] font-bold rounded-sm ${statusColor(linkStatus.telemetry)}`}>TLM</div>
        <div className={`px-2 py-1 text-[10px] font-bold rounded-sm ${statusColor(linkStatus.packet)}`}>PKT</div>
        <div className={`px-2 py-1 text-[10px] font-bold rounded-sm ${statusColor(linkStatus.video)}`}>VID</div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-[10px] text-outline font-label-caps">FREQ</div>
          <div className="font-mono text-xl text-on-surface">
            {frequency} <span className="text-xs opacity-50">MHz</span>
          </div>
        </div>
        <div>
          <div className="text-[10px] text-outline font-label-caps">SNR</div>
          <div className={`font-mono text-xl ${snr > 10 ? 'text-secondary' : snr > 5 ? 'text-tertiary' : 'text-reentry-red'}`}>
            {snr.toFixed(1)} <span className="text-xs">dB</span>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create PowerCard**

Create `web-dashboard/src/components/PowerCard.tsx`:

```tsx
import { PowerData } from '../types';

interface PowerCardProps {
  power: PowerData;
}

function batteryColor(pct: number): string {
  if (pct > 50) return 'bg-secondary text-secondary';
  if (pct > 20) return 'bg-tertiary text-tertiary';
  return 'bg-reentry-red text-reentry-red';
}

export function PowerCard({ power }: PowerCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant p-3">
      <span className="data-label block mb-3 text-label-caps text-outline">POWER SYSTEMS</span>
      <div className="flex justify-between items-end mb-2">
        <div className="font-mono text-xl text-on-surface">
          {power.bat_v.toFixed(2)}<span className="text-xs opacity-50">V</span> {power.bat_a.toFixed(2)}<span className="text-xs opacity-50">A</span>
        </div>
        <div className={`font-mono text-2xl ${batteryColor(power.bat_pct).split(' ')[1]}`}>
          {power.bat_pct.toFixed(0)}%
        </div>
      </div>
      <div className="w-full h-2 bg-surface-container-highest rounded-full overflow-hidden mb-4">
        <div
          className={`h-full rounded-full ${batteryColor(power.bat_pct).split(' ')[0]}`}
          style={{ width: `${power.bat_pct}%` }}
        />
      </div>
      <div className="text-[10px] font-mono text-outline grid grid-cols-3 gap-2">
        <div>3.3V: {power.rails_v.v3v3.toFixed(2)}V</div>
        <div>5.0V: {power.rails_v.v5.toFixed(2)}V</div>
        <div>1.8V: {power.rails_v.v1v8.toFixed(2)}V</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create AlertsCard**

Create `web-dashboard/src/components/AlertsCard.tsx`:

```tsx
interface AlertsCardProps {
  lastPacketAge: number;
  linkMargin: number;
}

function lastPacketColor(age: number): string {
  if (age < 5) return 'text-secondary';
  if (age < 15) return 'text-tertiary';
  return 'text-reentry-red';
}

export function AlertsCard({ lastPacketAge, linkMargin }: AlertsCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant p-3 flex-1">
      <span className="data-label block mb-3 text-label-caps text-outline">SYSTEM ALERTS</span>
      <div className="flex flex-col gap-2">
        <div className="text-outline text-xs italic">No active alerts...</div>
        <div className="mt-4 pt-4 border-t border-outline-variant space-y-2">
          <div className="flex justify-between text-[11px] font-mono">
            <span className="text-outline">Last packet:</span>
            <span className={lastPacketColor(lastPacketAge)}>{lastPacketAge.toFixed(1)}s ago</span>
          </div>
          <div className="flex justify-between text-[11px] font-mono">
            <span className="text-outline">Link margin:</span>
            <span className={linkMargin > 10 ? 'text-secondary' : linkMargin > 5 ? 'text-tertiary' : 'text-reentry-red'}>
              {linkMargin} dB
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create PacketRateCard**

Create `web-dashboard/src/components/PacketRateCard.tsx`:

```tsx
interface PacketRateCardProps {
  rate: number;
  sequence: number;
}

export function PacketRateCard({ rate, sequence }: PacketRateCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant p-3">
      <div className="flex justify-between items-start mb-2">
        <div>
          <span className="data-label block text-label-caps text-outline">PACKET RATE</span>
          <div className="font-mono text-2xl text-on-surface">
            {rate.toFixed(1)} <span className="text-xs opacity-50">pkt/s</span>
          </div>
        </div>
        <div className="text-right">
          <span className="data-label block text-label-caps text-outline">SEQUENCE</span>
          <div className="font-mono text-lg text-primary">#{sequence}</div>
        </div>
      </div>
      <div className="h-12 w-full mt-2">
        <svg className="w-full h-full" viewBox="0 0 300 40">
          <path
            d="M 0 30 L 20 25 L 40 35 L 60 15 L 80 20 L 100 10 L 120 28 L 140 12 L 160 30 L 180 15 L 200 22 L 220 5 L 240 18 L 260 32 L 280 25 L 300 20"
            fill="none"
            stroke="#abc7ff"
            strokeWidth="1.5"
          />
        </svg>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add web-dashboard/src/components/RfLinkCard.tsx web-dashboard/src/components/PowerCard.tsx web-dashboard/src/components/AlertsCard.tsx web-dashboard/src/components/PacketRateCard.tsx
git commit -m "feat: add right panel cards (RF link, power, alerts, packet rate)"
```

---

### Task 6: Create CameraFeed and PacketStream

**Files:**
- Create: `web-dashboard/src/components/CameraFeed.tsx`
- Create: `web-dashboard/src/components/PacketStream.tsx`

- [ ] **Step 1: Create CameraFeed**

Create `web-dashboard/src/components/CameraFeed.tsx`:

```tsx
import { Video } from 'lucide-react';

interface CameraFeedProps {
  bitrate?: number;
  signalQuality?: number;
  rtspUrl?: string;
}

export function CameraFeed({ bitrate = 2.4, signalQuality = 98, rtspUrl = 'rtsp://192.168.1.100/stream1' }: CameraFeedProps) {
  return (
    <div className="card-border bg-surface-container-lowest rounded-[20px] border border-outline-variant flex-1 relative flex flex-col items-center justify-center">
      <div className="flex flex-col items-center gap-4 opacity-30">
        <Video size={64} />
        <span className="font-label-caps text-xl tracking-widest">NO VIDEO SIGNAL</span>
      </div>

      <div className="absolute top-4 left-4 flex gap-2">
        <div className="px-2 py-0.5 bg-reentry-red/20 text-reentry-red text-[10px] font-bold flex items-center gap-2 card-border border border-outline-variant/50">
          <span className="w-2 h-2 rounded-full bg-reentry-red animate-pulse" /> LIVE
        </div>
        <div className="px-2 py-0.5 bg-surface/60 text-on-surface text-[10px] font-mono card-border border border-outline-variant/50">
          {bitrate.toFixed(1)} Mbps {signalQuality}%
        </div>
      </div>

      <div className="absolute top-4 right-4 text-[10px] font-mono text-outline bg-surface/60 px-2 py-0.5 card-border border border-outline-variant/50 rounded">
        {rtspUrl}
      </div>

      <button className="absolute bottom-6 px-6 py-2 bg-primary text-on-primary font-label-caps rounded-sm hover:opacity-80 transition-opacity">
        RECONNECT
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Create PacketStream**

Create `web-dashboard/src/components/PacketStream.tsx`:

```tsx
import { useRef, useEffect } from 'react';
import { Pause, Trash2 } from 'lucide-react';
import { LogEntry } from '../types';

interface PacketStreamProps {
  entries: LogEntry[];
}

const typeColors: Record<string, string> = {
  POS: 'bg-primary/20 text-primary',
  MOT: 'bg-secondary/20 text-secondary',
  ENV: 'bg-tertiary/20 text-tertiary',
  PWR: 'bg-secondary/20 text-secondary',
  SYS: 'bg-reentry-red/20 text-reentry-red',
};

export function PacketStream({ entries }: PacketStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries.length]);

  return (
    <footer className="fixed bottom-0 right-0 left-[64px] h-[200px] bg-surface-container-lowest border-t border-outline-variant flex flex-col z-50">
      <div className="h-10 border-b border-outline-variant px-4 flex justify-between items-center bg-surface-container-low">
        <div className="flex items-center gap-4">
          <span className="data-label text-label-caps text-outline">PACKET STREAM</span>
          <span className="text-[10px] font-mono text-outline">RX: 2.4 PKT/S | SEQ: 18430</span>
        </div>
        <div className="flex gap-4">
          <button className="text-outline hover:text-on-surface transition-colors flex items-center gap-1">
            <Pause size={16} />
            <span className="text-[10px] font-label-caps">PAUSE</span>
          </button>
          <button className="text-outline hover:text-on-surface transition-colors flex items-center gap-1">
            <Trash2 size={16} />
            <span className="text-[10px] font-label-caps">CLEAR</span>
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto font-mono text-[12px] p-2 leading-relaxed">
        {entries.map((entry, i) => (
          <div
            key={`${entry.timestamp}-${i}`}
            className={`flex gap-3 px-2 py-0.5 rounded ${i % 2 === 0 ? 'bg-surface-container-high/20' : ''}`}
          >
            <span className="text-outline">{entry.timestamp}</span>
            <span className={`px-1 rounded text-[10px] font-bold ${typeColors[entry.type] || 'bg-surface-container text-outline'}`}>
              {entry.type}
            </span>
            <span className="text-on-surface-variant">{entry.payload}</span>
          </div>
        ))}
      </div>

      <div className="h-6 bg-surface-container-lowest px-4 border-t border-outline-variant flex justify-between items-center text-[10px] text-outline font-mono">
        <span>FLIGHT OPERATIONS SYSTEM v4.2</span>
        <span>SYSTEM HEALTH: NOMINAL</span>
        <span>UPTIME: 03:14:22</span>
      </div>
    </footer>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add web-dashboard/src/components/CameraFeed.tsx web-dashboard/src/components/PacketStream.tsx
git commit -m "feat: add camera feed placeholder and packet stream component"
```

---

### Task 7: Create MissionControl Main View

**Files:**
- Create: `web-dashboard/src/components/MissionControl.tsx`

- [ ] **Step 1: Write MissionControl layout**

Create `web-dashboard/src/components/MissionControl.tsx`:

```tsx
import { MapCard } from './MapCard';
import { PositionCard } from './PositionCard';
import { MotionCard } from './MotionCard';
import { EnvironmentCard } from './EnvironmentCard';
import { CameraFeed } from './CameraFeed';
import { RfLinkCard } from './RfLinkCard';
import { PowerCard } from './PowerCard';
import { AlertsCard } from './AlertsCard';
import { PacketRateCard } from './PacketRateCard';
import { PacketStream } from './PacketStream';
import {
  PositionData,
  MotionData,
  EnvironmentData,
  PowerData,
  LinkStatus,
  LogEntry,
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
  lastPacketAge: number;
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
  lastPacketAge,
}: MissionControlProps) {
  return (
    <>
      <main className="ml-[64px] mt-[72px] h-[calc(100vh-272px)] p-4 grid grid-cols-[340px_1fr_350px] gap-4">
        {/* Left Column */}
        <section className="flex flex-col gap-4 overflow-hidden">
          <MapCard lat={position.lat} lon={position.lon} alt_m={position.alt_m} />
          <PositionCard position={position} />
          <MotionCard motion={motion} />
          <EnvironmentCard environment={environment} />
        </section>

        {/* Center Column */}
        <section className="flex flex-col gap-4">
          <CameraFeed />
        </section>

        {/* Right Column */}
        <section className="flex flex-col gap-4 overflow-hidden">
          <RfLinkCard linkStatus={linkStatus} />
          <PowerCard power={power} />
          <AlertsCard lastPacketAge={lastPacketAge} linkMargin={11} />
          <PacketRateCard rate={packetRate} sequence={sequence} />
        </section>
      </main>

      <PacketStream entries={logEntries} />
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web-dashboard/src/components/MissionControl.tsx
git commit -m "feat: add mission control main three-panel layout"
```

---

### Task 8: Write New App.tsx with Two-View Architecture

**Files:**
- Replace: `web-dashboard/src/App.tsx`
- Modify: `web-dashboard/src/hooks/useHabApi.ts` (export additional data)

- [ ] **Step 1: Update useHabApi to export new telemetry state**

Add these return values to the existing `useHabApi` hook. At the end of `web-dashboard/src/hooks/useHabApi.ts`, add the new state variables before the return statement. Add these imports at the top of the file:

```ts
import {
  PositionData, MotionData, EnvironmentData, PowerData,
  LinkStatus, LogEntry, TelemetryMessage,
} from '../types';
```

Add these state variables after the existing state declarations (after `const [connectionLog, setConnectionLog] = useState...`):

```ts
const [position, setPosition] = useState<PositionData>({
  lat: 39.3187, lon: -120.3289, alt_m: 18342.7, agl_m: 17210.3,
  fix: true, fix_type: '3d', sats: 14, hdop: 0.82, vdop: 1.34,
});
const [motion, setMotion] = useState<MotionData>({
  gs_mps: 13.8, vs_mps: 5.4, heading_deg: 72.6, cog_deg: 74.1,
  accel: { x: 0.03, y: -0.08, z: 9.71 },
  gyro_dps: { r: 0.4, p: -0.2, y: 1.1 },
  att_deg: { roll: 2.8, pitch: -4.1, yaw: 71.9 },
});
const [environment, setEnvironment] = useState<EnvironmentData>({
  temp_ext_c: -42.6, temp_int_c: 12.4, pressure_hpa: 72.8,
  humidity_pct: 4.2, baro_alt_m: 18190.5,
});
const [power, setPower] = useState<PowerData>({
  bat_v: 7.62, bat_a: 0.84, bat_w: 6.4, bat_pct: 68,
  bat_temp_c: 8.1, rails_v: { v5: 5.03, v3v3: 3.31, v1v8: 1.79 },
});
const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
const [packetRate, setPacketRate] = useState(2.4);
const [lastPacketAge, setLastPacketAge] = useState(1.2);
const [linkStatus, setLinkStatus] = useState<LinkStatus>({
  telemetry: 'NOMINAL', packet: 'NOMINAL', video: 'NOMINAL',
});
const [packetSeq, setPacketSeq] = useState(18430);
```

Add a function to process incoming telemetry in the WebSocket `onmessage` handler. Find the existing `if (msg.type === 'telemetry')` block and modify/add this logic:

```ts
} else if (msg.type === 'telemetry') {
  const data: TelemetryMessage = msg.data;
  setPacketSeq(data.seq);

  const time = data.t.split('T')[1]?.substring(0, 8) || new Date().toISOString().substring(11, 19);

  if (data.type === 'position') {
    setPosition(data);
    setCurrent((prev) => ({ ...prev, lat: data.lat, lng: data.lon, altitude: data.alt_m, gpsSats: data.sats }));
    addLogEntry(time, 'POS', `lat:${data.lat.toFixed(5)} lon:${data.lon.toFixed(5)} alt:${data.alt_m.toFixed(0)}m sats:${data.sats} fix:${data.fix_type}`);
  } else if (data.type === 'motion') {
    setMotion(data);
    setCurrent((prev) => ({ ...prev, verticalSpeed: data.vs_mps, groundSpeed: data.gs_mps, heading: data.heading_deg }));
    addLogEntry(time, 'MOT', `gs:${data.gs_mps.toFixed(1)} vs:${data.vs_mps.toFixed(1)} hdg:${data.heading_deg.toFixed(1)}`);
  } else if (data.type === 'environment') {
    setEnvironment(data);
    setCurrent((prev) => ({ ...prev, externalTemp: data.temp_ext_c, internalTemp: data.temp_int_c, pressure: data.pressure_hpa }));
    addLogEntry(time, 'ENV', `ext:${data.temp_ext_c.toFixed(1)}°C int:${data.temp_int_c.toFixed(1)}°C pres:${data.pressure_hpa.toFixed(1)}hPa hum:${data.humidity_pct.toFixed(1)}%`);
  } else if (data.type === 'power') {
    setPower(data);
    setCurrent((prev) => ({ ...prev, battery: data.bat_pct }));
    addLogEntry(time, 'PWR', `v:${data.bat_v.toFixed(2)}V a:${data.bat_a.toFixed(2)}A w:${data.bat_w.toFixed(1)}W ${data.bat_pct.toFixed(0)}%`);
  }

  const now = Date.now();
  setPackets((prev) => {
    const next = [...prev, { id: `PKT-${data.seq}`, timestamp: now, type: 'TELEMETRY', payload: JSON.stringify(data) }];
    return next.length > 200 ? next.slice(next.length - 200) : next;
  });
}
```

Add the `addLogEntry` helper function near the top of the hook:

```ts
const addLogEntry = useCallback((timestamp: string, type: LogEntry['type'], payload: string) => {
  setLogEntries((prev) => {
    const next = [...prev, { timestamp, type, payload }];
    return next.length > 500 ? next.slice(next.length - 500) : next;
  });
}, []);
```

Update the existing state update for link status in the HTTP polling section to use the new LinkStatus interface:

```ts
setLinkStatus((prev: LinkStatus) => ({
  ...prev,
  telemetry: connected ? 'NOMINAL' : 'OFFLINE',
  packet: connected ? 'NOMINAL' : 'OFFLINE',
  gps: data.gpsSats > 0 ? 'NOMINAL' : 'OFFLINE',
}));
```

Add new return values at the bottom of the hook's return statement:

```ts
position,
motion,
environment,
power,
logEntries,
packetRate,
setPacketRate,
lastPacketAge,
setLastPacketAge,
packetSeq,
```

- [ ] **Step 2: Write App.tsx with two-view architecture**

Replace `web-dashboard/src/App.tsx`:

```tsx
import { useState } from 'react';
import { useHabApi } from './hooks/useHabApi';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { MissionControl } from './components/MissionControl';

type View = 'mission-control' | 'settings';

export function App() {
  const [activeView, setActiveView] = useState<View>('mission-control');
  const {
    connected,
    connecting,
    phase,
    missionTime,
    position,
    motion,
    environment,
    power,
    linkStatus,
    logEntries,
    packetRate,
    lastPacketAge,
    packetSeq,
  } = useHabApi();

  return (
    <div className="h-screen w-screen flex overflow-hidden" style={{ backgroundColor: '#0b141c' }}>
      <Sidebar activeView={activeView} onViewChange={setActiveView} />
      <TopBar
        phase={phase}
        missionTime={missionTime}
        connected={connected}
        currentLat={position.lat}
        currentLon={position.lon}
        lastPacketAge={lastPacketAge}
      />

      {activeView === 'mission-control' && (
        <MissionControl
          position={position}
          motion={motion}
          environment={environment}
          power={power}
          linkStatus={linkStatus}
          packetRate={packetRate}
          sequence={packetSeq}
          logEntries={logEntries}
          lastPacketAge={lastPacketAge}
        />
      )}

      {activeView === 'settings' && (
        <div className="ml-[64px] mt-[72px] h-[calc(100vh-72px)] flex items-center justify-center text-outline">
          <span className="text-xl">Settings — coming soon</span>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Delete old component files**

```bash
rm web-dashboard/src/components/HeroStage.tsx
rm web-dashboard/src/components/AssetCard.tsx
rm web-dashboard/src/components/MissionSettingsGrid.tsx
rm web-dashboard/src/components/TrajectoryCard.tsx
rm web-dashboard/src/components/TelemetryGrid.tsx
rm web-dashboard/src/components/TelemetryCharts.tsx
rm web-dashboard/src/components/LowerTabs.tsx
rm web-dashboard/src/components/VideoFeeds.tsx
rm web-dashboard/src/components/DataStream.tsx
rm web-dashboard/src/components/DeviceStatusPanel.tsx
rm web-dashboard/src/components/SpectrumWaterfall.tsx
rm web-dashboard/src/components/StatusBar.tsx
rm web-dashboard/src/components/PipelineControls.tsx
rm web-dashboard/src/components/PipelineDebug.tsx
rm web-dashboard/src/components/RfConfig.tsx
rm web-dashboard/src/components/TxControls.tsx
rm web-dashboard/src/components/FlightMap.tsx
rm web-dashboard/src/components/Shared.tsx
rm web-dashboard/src/components/SettingsPage.tsx
```

- [ ] **Step 4: Verify build**

```bash
npm run build --prefix web-dashboard
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add web-dashboard/src/App.tsx web-dashboard/src/hooks/useHabApi.ts
git add -u web-dashboard/src/components/
git commit -m "feat: complete mission control dashboard migration — new two-view architecture with all panels"
```

---

### Task 9: Build Settings Page with Sub-Tabs

**Files:**
- Create: `web-dashboard/src/components/SettingsPage.tsx`
- Create: `web-dashboard/src/components/SettingsTabs.tsx`
- Create: `web-dashboard/src/components/SettingsDevice.tsx`
- Create: `web-dashboard/src/components/SettingsRf.tsx`
- Create: `web-dashboard/src/components/SettingsDvbs2.tsx`
- Create: `web-dashboard/src/components/SettingsPipeline.tsx`
- Create: `web-dashboard/src/components/SettingsAbout.tsx`
- Modify: `web-dashboard/src/App.tsx` (wire settings view)

**All steps in this task use the settings wireframe from the second half of `docs/superpowers/specs/dashboard.html` as the visual reference.**

- [ ] **Step 1: Create SettingsTabs**

Create `web-dashboard/src/components/SettingsTabs.tsx`:

```tsx
import { Cpu, Radio, Satellite, GitBranch, HelpCircle } from 'lucide-react';

export type SettingsTab = 'device' | 'rf' | 'dvbs2' | 'pipeline' | 'about';

interface SettingsTabsProps {
  activeTab: SettingsTab;
  onTabChange: (tab: SettingsTab) => void;
}

const tabs: { key: SettingsTab; label: string; Icon: typeof Cpu }[] = [
  { key: 'device', label: 'DEVICE', Icon: Cpu },
  { key: 'rf', label: 'RF', Icon: Radio },
  { key: 'dvbs2', label: 'DVB-S2', Icon: Satellite },
  { key: 'pipeline', label: 'PIPELINE', Icon: GitBranch },
  { key: 'about', label: 'ABOUT', Icon: HelpCircle },
];

export function SettingsTabs({ activeTab, onTabChange }: SettingsTabsProps) {
  return (
    <nav className="flex gap-2 mb-10 overflow-x-auto pb-2">
      {tabs.map(({ key, label, Icon }) => (
        <button
          key={key}
          onClick={() => onTabChange(key)}
          className={`flex items-center gap-2 px-6 py-3 rounded-full font-label-caps whitespace-nowrap transition-colors ${
            activeTab === key
              ? 'bg-telemetry-blue text-white'
              : 'bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest'
          }`}
        >
          <Icon size={18} /> {label}
        </button>
      ))}
    </nav>
  );
}
```

- [ ] **Step 2: Create SettingsDevice**

Create `web-dashboard/src/components/SettingsDevice.tsx`:

```tsx
import { MemoryStick as Memory } from 'lucide-react';

export function SettingsDevice() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Device Discovery */}
      <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6">
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-label-caps text-sm text-primary uppercase">Device Discovery</h3>
          <button className="text-xs font-label-caps text-telemetry-blue hover:underline">RESCAN</button>
        </div>
        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 bg-surface rounded-xl border border-outline-variant/30">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-surface-container-highest flex items-center justify-center text-tracking-green">
                <Memory size={20} />
              </div>
              <div>
                <p className="font-mono text-sm text-on-surface">HackRF One</p>
                <p className="text-[10px] font-label-caps text-outline">Serial: ...60661</p>
              </div>
            </div>
            <button className="px-4 py-2 bg-telemetry-blue text-white rounded-lg font-label-caps text-[10px] hover:opacity-90">CONNECT</button>
          </div>
          <div className="flex items-center justify-between p-4 bg-surface rounded-xl border border-outline-variant/30 opacity-50">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-surface-container-highest flex items-center justify-center text-outline">
                <Memory size={20} />
              </div>
              <div>
                <p className="font-mono text-sm text-on-surface">HackRF One</p>
                <p className="text-[10px] font-label-caps text-outline">Serial: ...67464</p>
              </div>
            </div>
            <button className="px-4 py-2 border border-outline rounded-lg font-label-caps text-[10px] cursor-not-allowed text-outline">BUSY</button>
          </div>
        </div>
      </div>

      {/* Connected Device */}
      <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6 flex flex-col">
        <h3 className="font-label-caps text-sm text-primary uppercase mb-6">Connected Device</h3>
        <div className="grid grid-cols-2 gap-4 flex-1">
          <div className="p-3 bg-surface rounded border border-outline-variant/30">
            <p className="text-[10px] font-label-caps text-outline mb-1">CENTER FREQUENCY</p>
            <p className="font-telemetry-lg text-2xl text-on-surface">915.000 <span className="text-xs text-outline">MHz</span></p>
          </div>
          <div className="p-3 bg-surface rounded border border-outline-variant/30">
            <p className="text-[10px] font-label-caps text-outline mb-1">SAMPLE RATE</p>
            <p className="font-telemetry-lg text-2xl text-on-surface">2.000 <span className="text-xs text-outline">Msps</span></p>
          </div>
          <div className="p-3 bg-surface rounded border border-outline-variant/30">
            <p className="text-[10px] font-label-caps text-outline mb-1">LNA GAIN</p>
            <p className="font-telemetry-lg text-2xl text-on-surface">16 <span className="text-xs text-outline">dB</span></p>
          </div>
          <div className="p-3 bg-surface rounded border border-outline-variant/30">
            <p className="text-[10px] font-label-caps text-outline mb-1">VGA GAIN</p>
            <p className="font-telemetry-lg text-2xl text-on-surface">24 <span className="text-xs text-outline">dB</span></p>
          </div>
        </div>
        <button className="mt-6 w-full py-3 bg-reentry-red/20 text-reentry-red border border-reentry-red/50 rounded-lg font-label-caps hover:bg-reentry-red hover:text-white transition-all">DISCONNECT DEVICE</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create SettingsRf**

Create `web-dashboard/src/components/SettingsRf.tsx`:

```tsx
export function SettingsRf() {
  return (
    <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">FREQUENCY (MHz)</label>
          <input
            className="w-full bg-surface-container-lowest border border-outline-variant rounded p-3 font-mono text-on-surface focus:border-telemetry-blue outline-none"
            type="text"
            defaultValue="915.000"
          />
        </div>
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">SYMBOL RATE (Msps)</label>
          <input
            className="w-full bg-surface-container-lowest border border-outline-variant rounded p-3 font-mono text-on-surface focus:border-telemetry-blue outline-none"
            type="text"
            defaultValue="1.000"
          />
        </div>
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">LO OFFSET (PPM)</label>
          <input
            className="w-full bg-surface-container-lowest border border-outline-variant rounded p-3 font-mono text-on-surface focus:border-telemetry-blue outline-none"
            type="number"
            defaultValue="0"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-12 mb-8">
        <div>
          <div className="flex justify-between mb-2">
            <label className="text-[10px] font-label-caps text-outline">LNA GAIN (0-40 dB)</label>
            <span className="font-mono text-telemetry-blue">16 dB</span>
          </div>
          <input
            className="w-full h-1 bg-surface-container-highest rounded-lg appearance-none cursor-pointer accent-telemetry-blue"
            type="range"
            min="0"
            max="40"
            defaultValue="16"
          />
        </div>
        <div>
          <div className="flex justify-between mb-2">
            <label className="text-[10px] font-label-caps text-outline">VGA GAIN (0-62 dB)</label>
            <span className="font-mono text-telemetry-blue">24 dB</span>
          </div>
          <input
            className="w-full h-1 bg-surface-container-highest rounded-lg appearance-none cursor-pointer accent-telemetry-blue"
            type="range"
            min="0"
            max="62"
            defaultValue="24"
          />
        </div>
      </div>

      <div className="flex items-center justify-between pt-6 border-t border-outline-variant/30">
        <div className="flex items-center gap-4">
          <span className="text-[10px] font-label-caps text-outline">AMP ENABLE</span>
          <div className="flex p-1 bg-surface-container-lowest rounded-lg border border-outline-variant">
            <button className="px-4 py-1 text-[10px] font-label-caps rounded transition-colors bg-surface-container-highest text-on-surface">DISABLED</button>
            <button className="px-4 py-1 text-[10px] font-label-caps rounded transition-colors text-outline hover:text-on-surface">ENABLED</button>
          </div>
        </div>
        <div className="flex gap-3">
          <button className="px-6 py-2 border border-outline-variant rounded text-[10px] font-label-caps hover:bg-surface-container-highest">RESET</button>
          <button className="px-6 py-2 bg-telemetry-blue text-white rounded text-[10px] font-label-caps hover:bg-blue-600">APPLY PARAMETERS</button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create SettingsDvbs2**

Create `web-dashboard/src/components/SettingsDvbs2.tsx`:

```tsx
export function SettingsDvbs2() {
  return (
    <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-8">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-6 mb-8">
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">MODCOD</label>
          <select className="w-full bg-surface-container-lowest border border-outline-variant rounded p-2 font-mono text-xs text-on-surface">
            <option>QPSK 1/2</option>
            <option>QPSK 3/4</option>
            <option>8PSK 2/3</option>
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">PILOTS</label>
          <select className="w-full bg-surface-container-lowest border border-outline-variant rounded p-2 font-mono text-xs text-on-surface">
            <option>OFF</option>
            <option>ON</option>
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">ROLLOFF</label>
          <select className="w-full bg-surface-container-lowest border border-outline-variant rounded p-2 font-mono text-xs text-on-surface">
            <option>0.35</option>
            <option>0.25</option>
            <option>0.20</option>
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">FEC FRAME</label>
          <select className="w-full bg-surface-container-lowest border border-outline-variant rounded p-2 font-mono text-xs text-on-surface">
            <option>NORMAL</option>
            <option>SHORT</option>
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">SPS</label>
          <input className="w-full bg-surface-container-lowest border border-outline-variant rounded p-2 font-mono text-xs text-on-surface focus:border-telemetry-blue outline-none" type="number" defaultValue="2" />
        </div>
      </div>

      <div className="space-y-6">
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">DEVICE ARGUMENTS (ADVANCED)</label>
          <input
            className="w-full bg-surface-container-lowest border border-outline-variant rounded p-4 font-mono text-xs text-tracking-green focus:border-telemetry-blue outline-none"
            type="text"
            defaultValue="hackrf=0,bias=0,pack_stream=1,buffer_size=1048576"
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="flex items-center justify-between p-4 bg-surface-container-lowest rounded border border-outline-variant/30">
            <span className="text-xs font-label-caps text-outline">RRC DELAY</span>
            <span className="font-mono text-xs text-on-surface">10 taps</span>
          </div>
          <div className="flex items-center justify-between p-4 bg-surface-container-lowest rounded border border-outline-variant/30">
            <span className="text-xs font-label-caps text-outline">SINK TYPE</span>
            <span className="font-mono text-xs text-on-surface">TCP SERVER :5000</span>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create SettingsPipeline**

Create `web-dashboard/src/components/SettingsPipeline.tsx`:

```tsx
import { Play, Square } from 'lucide-react';

export function SettingsPipeline() {
  return (
    <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-8">
      <div className="flex gap-4 mb-8">
        <div className="flex-1 bg-surface-container-lowest border border-outline-variant rounded px-4 py-3 flex items-center justify-between text-outline">
          <span className="font-mono text-xs">/opt/stratos/capture/telemetry_915mhz.ts</span>
          <button className="px-3 py-1 bg-surface-container-high rounded text-[10px] font-label-caps hover:text-on-surface">BROWSE</button>
        </div>
        <button className="px-6 py-2 bg-tracking-green text-white rounded font-label-caps flex items-center gap-2">
          <Play size={16} /> START PIPELINE
        </button>
        <button className="px-6 py-2 bg-reentry-red/20 text-reentry-red border border-reentry-red/50 rounded font-label-caps opacity-50">
          <Square size={16} /> STOP
        </button>
      </div>

      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-surface p-4 rounded border border-outline-variant/30">
          <p className="text-[10px] font-label-caps text-outline mb-1">BITRATE</p>
          <p className="font-mono text-lg text-tracking-green">965,326 <span className="text-xs opacity-50">bps</span></p>
        </div>
        <div className="bg-surface p-4 rounded border border-outline-variant/30">
          <p className="text-[10px] font-label-caps text-outline mb-1">DURATION</p>
          <p className="font-mono text-lg text-on-surface">00:47:32</p>
        </div>
        <div className="bg-surface p-4 rounded border border-outline-variant/30">
          <p className="text-[10px] font-label-caps text-outline mb-1">DROP RATIO</p>
          <p className="font-mono text-lg text-reentry-red">0.02%</p>
        </div>
        <div className="bg-surface p-4 rounded border border-outline-variant/30">
          <p className="text-[10px] font-label-caps text-outline mb-1">SINK HEALTH</p>
          <p className="font-mono text-lg text-tracking-green">ACTIVE</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 h-[250px]">
        <div className="bg-black rounded-lg p-4 flex flex-col">
          <div className="flex justify-between items-center mb-2 border-b border-white/10 pb-1">
            <span className="text-[10px] font-mono text-outline">FFMPEG_STREAM_OUT</span>
            <span className="w-2 h-2 rounded-full bg-tracking-green animate-pulse" />
          </div>
          <div className="flex-1 overflow-y-auto font-mono text-[11px] text-green-500 leading-relaxed" style={{ scrollbarWidth: 'thin' }}>
            <div>[h264 @ 0x559e86c] frame=1240 fps=30 q=28.0 size=450kB</div>
            <div>[h264 @ 0x559e86c] frame=1270 fps=30 q=28.0 size=482kB</div>
            <div>[h264 @ 0x559e86c] frame=1300 fps=30 q=29.0 size=512kB</div>
          </div>
        </div>
        <div className="bg-black rounded-lg p-4 flex flex-col">
          <div className="flex justify-between items-center mb-2 border-b border-white/10 pb-1">
            <span className="text-[10px] font-mono text-outline">TSP_PACKET_PROCESSOR</span>
            <span className="w-2 h-2 rounded-full bg-tracking-green animate-pulse" />
          </div>
          <div className="flex-1 overflow-y-auto font-mono text-[11px] text-blue-400 leading-relaxed" style={{ scrollbarWidth: 'thin' }}>
            <div>* tsp: PID 0x0100 (SDT) pkt: 4,502, rate: 1,200 b/s</div>
            <div>* tsp: PID 0x1FFF (Null) pkt: 1,204,502, rate: 45,600 b/s</div>
            <div>* tsp: PID 0x0010 (NIT) pkt: 890, rate: 200 b/s</div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Create SettingsAbout**

Create `web-dashboard/src/components/SettingsAbout.tsx`:

```tsx
export function SettingsAbout() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6 md:col-span-2">
        <h3 className="font-label-caps text-sm text-primary uppercase mb-6">System Status</h3>
        <div className="space-y-4 font-mono text-sm">
          <div className="flex justify-between py-2 border-b border-outline-variant/20">
            <span className="text-outline">SYSTEM UPTIME</span>
            <span className="text-on-surface">72h 14m 05s</span>
          </div>
          <div className="flex justify-between py-2 border-b border-outline-variant/20">
            <span className="text-outline">WEBSOCKET STATUS</span>
            <span className="text-tracking-green">CONNECTED</span>
          </div>
          <div className="flex justify-between py-2 border-b border-outline-variant/20">
            <span className="text-outline">CORE LOAD</span>
            <span className="text-on-surface">12.4%</span>
          </div>
          <div className="flex justify-between py-2 border-b border-outline-variant/20">
            <span className="text-outline">DISK USAGE (CAPTURE)</span>
            <span className="text-on-surface">244 GB / 1024 GB</span>
          </div>
        </div>
      </div>
      <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6 flex flex-col justify-between">
        <div>
          <h3 className="font-label-caps text-sm text-primary uppercase mb-6">Software Build</h3>
          <div className="space-y-2">
            <p className="text-xl font-bold font-mission-name text-on-surface">STRATOS v0.5-dev</p>
            <p className="text-[10px] font-mono text-outline">HASH: 7a8c3d1f_main_stable</p>
            <p className="text-[10px] font-mono text-outline">BUILD: 2026-05-19</p>
          </div>
        </div>
        <button className="mt-8 py-3 border border-outline rounded font-label-caps text-xs hover:bg-surface-container-highest text-outline">CHECK FOR UPDATES</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Create main SettingsPage**

Create `web-dashboard/src/components/SettingsPage.tsx`:

```tsx
import { useState } from 'react';
import { X } from 'lucide-react';
import { SettingsTabs, SettingsTab } from './SettingsTabs';
import { SettingsDevice } from './SettingsDevice';
import { SettingsRf } from './SettingsRf';
import { SettingsDvbs2 } from './SettingsDvbs2';
import { SettingsPipeline } from './SettingsPipeline';
import { SettingsAbout } from './SettingsAbout';

interface SettingsPageProps {
  onClose: () => void;
}

export function SettingsPage({ onClose }: SettingsPageProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>('device');

  return (
    <div className="ml-[64px] mt-[72px] h-[calc(100vh-72px)] overflow-y-auto">
      <div className="p-8 max-w-[1400px] mx-auto">
        <div className="flex justify-between items-start mb-8">
          <h1 className="font-mission-name text-4xl font-bold tracking-tight text-on-surface">SETTINGS</h1>
          <button
            onClick={onClose}
            className="p-2 border border-outline-variant rounded-full hover:bg-surface-container-highest transition-colors text-on-surface-variant"
          >
            <X size={20} />
          </button>
        </div>

        <SettingsTabs activeTab={activeTab} onTabChange={setActiveTab} />

        {activeTab === 'device' && <SettingsDevice />}
        {activeTab === 'rf' && <SettingsRf />}
        {activeTab === 'dvbs2' && <SettingsDvbs2 />}
        {activeTab === 'pipeline' && <SettingsPipeline />}
        {activeTab === 'about' && <SettingsAbout />}
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Wire settings view into App.tsx**

In `web-dashboard/src/App.tsx`, replace the settings placeholder. Add the import:

```tsx
import { SettingsPage } from './components/SettingsPage';
```

Replace the `activeView === 'settings'` block:

```tsx
{activeView === 'settings' && (
  <SettingsPage onClose={() => setActiveView('mission-control')} />
)}
```

Also update the sidebar's RF Config button to navigate to settings. In `Sidebar.tsx`, change the `Radio` icon button to:

```tsx
<button
  onClick={() => onViewChange('settings')}
  className="w-12 h-12 flex items-center justify-center text-on-surface-variant hover:bg-surface-container-highest transition-colors rounded-lg"
  title="RF Config"
>
  <Radio size={22} />
</button>
```

- [ ] **Step 9: Build and verify**

```bash
npm run build --prefix web-dashboard
```

Expected: Build succeeds. Then test:

```bash
npm run dev --prefix web-dashboard
```

Verify the dashboard renders at localhost.

- [ ] **Step 10: Commit**

```bash
git add web-dashboard/src/components/SettingsPage.tsx web-dashboard/src/components/SettingsTabs.tsx web-dashboard/src/components/SettingsDevice.tsx web-dashboard/src/components/SettingsRf.tsx web-dashboard/src/components/SettingsDvbs2.tsx web-dashboard/src/components/SettingsPipeline.tsx web-dashboard/src/components/SettingsAbout.tsx web-dashboard/src/App.tsx web-dashboard/src/components/Sidebar.tsx
git commit -m "feat: add settings page with 5 sub-tabs (device, RF, DVB-S2, pipeline, about)"
```

---

### Task 10: Integration Testing and Polish

**Files:**
- Modify: `web-dashboard/src/index.tsx` (ensure ErrorBoundary wraps properly)
- Modify: `web-dashboard/src/hooks/useHabApi.ts` (final cleanup)

- [ ] **Step 1: Update index.tsx entry point**

Replace `web-dashboard/src/index.tsx`:

```tsx
import './index.css';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { ErrorBoundary } from './components/ErrorBoundary';

const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  );
}
```

- [ ] **Step 2: Verify the full dashboard renders**

```bash
npm run dev --prefix web-dashboard &
sleep 3
curl -s http://localhost:5173 | head -20
```

Expected: HTML output with the dashboard shell.

- [ ] **Step 3: Run TypeScript check**

```bash
npx tsc --noEmit --project web-dashboard/tsconfig.json
```

Expected: No errors.

- [ ] **Step 4: Final build**

```bash
npm run build --prefix web-dashboard
```

Expected: Build succeeds, `web-dashboard/dist/` populated.

- [ ] **Step 5: Commit**

```bash
git add web-dashboard/src/index.tsx web-dashboard/dist/
git commit -m "feat: finalize mission control dashboard — integration testing and build"
```
