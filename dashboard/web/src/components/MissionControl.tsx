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
