import { useState, useEffect } from 'react';
import { useHabApi } from './hooks/useHabApi';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { MissionControl } from './components/MissionControl';
import { SettingsPage } from './components/SettingsPage';

type View = 'mission-control' | 'settings';

export function App() {
  const [activeView, setActiveView] = useState<View>('mission-control');

  const {
    connected,
    phase,
    missionTime,
    position,
    motion,
    environment,
    power,
    logEntries,
    packetRate,
    lastPacketAge,
    packetSeq,
    sendCommand,
    connectionLog,
    clearLog,
    ffmpegOutput,
    tspOutput,
    clearFfmpegOutput,
    clearTspOutput,
    engineStatus,
  } = useHabApi();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'f' || e.key === 'F') {
        if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
        e.preventDefault();
        if (document.fullscreenElement) {
          document.exitFullscreen();
        } else {
          document.documentElement.requestFullscreen().catch(() => {});
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

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
          linkStatus={{
            telemetry: connected ? 'NOMINAL' : 'OFFLINE',
            packet: connected ? 'NOMINAL' : 'OFFLINE',
            video: engineStatus?.pipeline?.running ? 'NOMINAL' : 'OFFLINE',
          }}
          packetRate={packetRate}
          sequence={packetSeq}
          logEntries={logEntries}
          lastPacketAge={lastPacketAge}
        />
      )}

      {activeView === 'settings' && (
        <SettingsPage
          sendCommand={sendCommand}
          engineStatus={engineStatus}
          connected={connected}
          ffmpegOutput={ffmpegOutput}
          tspOutput={tspOutput}
          clearFfmpegOutput={clearFfmpegOutput}
          clearTspOutput={clearTspOutput}
          connectionLog={connectionLog}
          clearLog={clearLog}
        />
      )}
    </div>
  );
}
