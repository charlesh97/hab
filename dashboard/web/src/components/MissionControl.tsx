import { MapCard } from './MapCard';
import { CameraFeed } from './CameraFeed';
import { TelemetryCard } from './TelemetryCard';
import { PacketStream } from './PacketStream';
import {
  PositionData,
  MotionData,
  PowerData,
  LinkStatus,
  LogEntry,
  MetricPoint,
} from '../types';

interface MissionControlProps {
  position: PositionData;
  motion: MotionData;
  power: PowerData;
  linkStatus: LinkStatus;
  packetRate: number;
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
  loadPositions: (since: number) => Promise<Array<{seq: number; lat: number; lon: number; alt_m: number}>>;
}

export function MissionControl({
  position,
  motion,
  power,
  linkStatus,
  packetRate,
  logEntries,
  metricHistory,
  loadPositions,
}: MissionControlProps) {
  return (
    <>
      <main className="ml-[64px] mt-[72px] h-[calc(100vh-272px)] p-4 grid grid-cols-[2fr_3fr_2fr] gap-4">
        {/* Left Column: Map */}
        <section className="overflow-hidden">
          <MapCard lat={position.lat} lon={position.lon} alt_m={position.alt_m} loadPositions={loadPositions} />
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
