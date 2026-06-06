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
    power,
    logEntries,
    packetRate,
    lastPacketAge,
    metricHistory,
    newLinkStatus,
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
          power={power}
          linkStatus={newLinkStatus}
          packetRate={packetRate}
          logEntries={logEntries}
          metricHistory={metricHistory}
        />
      )}

      {activeView === 'settings' && (
        <SettingsPage onClose={() => setActiveView('mission-control')} />
      )}
    </div>
  );
}
