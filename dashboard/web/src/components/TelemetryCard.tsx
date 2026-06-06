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

function linkDotColor(status: 'NOMINAL' | 'DEGRADED' | 'OFFLINE'): string {
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
          <span className="font-label-caps text-primary-container mb-3 block">NAVIGATION</span>

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
          <span className="font-label-caps text-primary-container mb-3 block">ENVIRONMENT</span>

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
          <span className="font-label-caps text-primary-container mb-3 block">POWER & LINK</span>

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
          <span className="font-label-caps text-primary-container mb-3 block">ATTITUDE</span>

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
