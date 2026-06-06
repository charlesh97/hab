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
