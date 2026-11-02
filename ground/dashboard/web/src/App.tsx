import { useState, useEffect } from 'react';
import { useHabApi } from './hooks/useHabApi';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { MissionControl } from './components/MissionControl';
import { PacketStream } from './components/PacketStream';
import { SettingsPage } from './components/SettingsPage';

type View = 'mission-control' | 'settings';

export function App() {
  const [activeView, setActiveView] = useState<View>('mission-control');
  const [footerHeight, setFooterHeight] = useState(200);

  const {
    connected,
    phase,
    missionTime,
    uptime,
    systemHealth,
    position,
    motion,
    power,
    packetEntries,
    logEntries,
    packetRate,
    packetSeq,
    lastPacketAge,
    metricHistory,
    newLinkStatus,
    loadPositions,
    engineStatus,
    sdrStatus,
    sendCommand,
  } = useHabApi();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'f' || e.key === 'F') {
        if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
        e.preventDefault();
        if (document.fullscreenElement) {
          document.exitFullscreen();
        } else {
          document.documentElement.requestFullscreen().catch(() => undefined);
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
        currentFix={position.fix}
        lastPacketAge={lastPacketAge}
      />

      {activeView === 'mission-control' && (
        <>
          <MissionControl
            position={position}
            motion={motion}
            power={power}
            linkStatus={newLinkStatus}
            packetRate={packetRate}
            metricHistory={metricHistory}
            loadPositions={loadPositions}
            sendCommand={sendCommand}
            sdrStatus={sdrStatus}
            engineStatus={engineStatus}
            connected={connected}
            footerHeight={footerHeight}
          />
          <PacketStream
            entries={packetEntries}
            logEntries={logEntries}
            packetRate={packetRate}
            packetSeq={packetSeq}
            uptime={uptime}
            systemHealth={systemHealth}
            onHeightChange={setFooterHeight}
          />
        </>
      )}

      {activeView === 'settings' && (
        <SettingsPage
          onClose={() => setActiveView('mission-control')}
          sendCommand={sendCommand}
          sdrStatus={sdrStatus}
          engineStatus={engineStatus}
          connected={connected}
        />
      )}
    </div>
  );
}
