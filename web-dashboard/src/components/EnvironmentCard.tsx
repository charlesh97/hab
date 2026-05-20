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
              {environment.temp_ext_c.toFixed(1)}\u00B0C
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
            <div className="font-mono text-xl text-on-surface">{environment.temp_int_c.toFixed(1)}\u00B0C</div>
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
