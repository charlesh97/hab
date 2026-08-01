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
