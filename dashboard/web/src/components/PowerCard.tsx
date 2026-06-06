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
