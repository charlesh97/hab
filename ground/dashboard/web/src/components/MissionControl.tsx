import { MapCard } from './MapCard';
import { CameraFeed } from './CameraFeed';
import { TelemetryCard } from './TelemetryCard';
import {
  PositionData,
  MotionData,
  PowerData,
  LinkStatus,
  MetricPoint,
  EngineStatus,
} from '../types';
import { PositionPoint } from '../utils/position';

interface MissionControlProps {
  position: PositionData;
  motion: MotionData;
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
  loadPositions: (since: number) => Promise<PositionPoint[]>;
  sendCommand: (command: string, data?: any) => void;
  sdrStatus: any;
  engineStatus: EngineStatus | null;
  connected: boolean;
  footerHeight: number;
}

export function MissionControl({
  position,
  motion,
  power,
  linkStatus,
  packetRate,
  metricHistory,
  loadPositions,
  sdrStatus,
  footerHeight,
}: MissionControlProps) {
  return (
    <main
      className="ml-[64px] mt-[72px] flex-1 min-h-0 overflow-y-auto p-4 grid grid-cols-1 lg:grid-cols-[minmax(250px,1fr)_minmax(300px,2fr)_minmax(220px,1fr)] gap-4"
      style={{ height: `calc(100vh - 72px - ${footerHeight}px)` }}
    >
      {/* Left Column: Map */}
      <section className="min-h-[300px] overflow-hidden">
        <MapCard
          lat={position.lat}
          lon={position.lon}
          alt_m={position.alt_m}
          fix={position.fix}
          loadPositions={loadPositions}
        />
      </section>

      {/* Center Column: Video Feed */}
      <section className="min-h-[300px] overflow-hidden flex">
        <CameraFeed
          isConnected={linkStatus.video === 'NOMINAL'}
          locked={sdrStatus?.dvbs2?.locked || false}
          sdrStatus={sdrStatus}
        />
      </section>

      {/* Right Column: Unified Telemetry Card */}
      <section className="min-h-[300px] overflow-hidden">
        <TelemetryCard
          position={position}
          motion={motion}
          power={power}
          linkStatus={linkStatus}
          packetRate={packetRate}
          metricHistory={metricHistory}
        />
      </section>
    </main>
  );
}
