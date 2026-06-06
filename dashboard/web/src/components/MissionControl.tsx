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
