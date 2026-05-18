import React from 'react';
import { useHabApi } from './hooks/useHabApi';
import { TopBar } from './components/TopBar';
import { HeroStage } from './components/HeroStage';
import { AssetCard } from './components/AssetCard';
import { MissionSettingsGrid } from './components/MissionSettingsGrid';
import { TrajectoryCard } from './components/TrajectoryCard';

export function App() {
  const { connected, phase, missionTime, current, engineStatus, sendCommand } = useHabApi();

  return (
    <div className="h-screen w-screen bg-slate-300 p-4 md:p-6 flex overflow-hidden font-sans">
      <div className="flex-1 bg-[#0a0a0b] rounded-[2rem] overflow-hidden relative shadow-2xl ring-1 ring-white/10 flex flex-col">
        {/* Connection indicator */}
        <div className={`absolute top-6 right-8 z-[100] flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-mono shadow-lg ${
          connected ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 backdrop-blur-md' : 'bg-rose-500/15 text-rose-400 border border-rose-500/30 backdrop-blur-md'
        }`}>
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`} />
          {connected ? 'LIVE' : 'DISCONNECTED'}
          {connected && <span className="text-emerald-400/60 ml-1 text-[9px]">ws:8765</span>}
        </div>

        <TopBar phase={phase} missionTime={missionTime} />

        <div className="flex-1 relative flex flex-col">
          <HeroStage current={current} />

          <div className="h-[280px] grid grid-cols-12 gap-4 p-6 relative z-10 bg-gradient-to-t from-[#0a0a0b] via-[#0a0a0b]/90 to-transparent">
            <AssetCard current={current} className="col-span-3" />
            <MissionSettingsGrid className="col-span-6" />
            <TrajectoryCard className="col-span-3" />
          </div>
        </div>
      </div>
    </div>
  );
}
