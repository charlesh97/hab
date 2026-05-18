import React, { useState } from 'react';
import { useHabApi } from './hooks/useHabApi';
import { TopBar } from './components/TopBar';
import { HeroStage } from './components/HeroStage';
import { AssetCard } from './components/AssetCard';
import { MissionSettingsGrid } from './components/MissionSettingsGrid';
import { TrajectoryCard } from './components/TrajectoryCard';
import { TelemetryGrid } from './components/TelemetryGrid';
import { TelemetryCharts } from './components/TelemetryCharts';
import { LowerTabs } from './components/LowerTabs';
import { FlightMap } from './components/FlightMap';
import { RfConfig } from './components/RfConfig';
import { SpectrumWaterfall } from './components/SpectrumWaterfall';
import { StatusBar } from './components/StatusBar';
import { DeviceStatusPanel } from './components/DeviceStatusPanel';

type PageTab = 'overview' | 'missions' | 'telemetry' | 'map' | 'settings';

export function App() {
  const [activeTab, setActiveTab] = useState<PageTab>('overview');
  const {
    connected,
    phase,
    missionTime,
    current,
    history,
    packets,
    packetsReceiving,
    engineStatus,
    spectrum,
    sendCommand,
  } = useHabApi();

  return (
    <div className="h-screen w-screen bg-slate-300 p-4 md:p-6 flex overflow-hidden font-sans">
      <div className="flex-1 bg-[#0a0a0b] rounded-[2rem] overflow-hidden relative shadow-2xl ring-1 ring-white/10 flex flex-col">
        {/* Connection indicator */}
        <div
          className={`absolute top-6 right-8 z-[100] flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-mono shadow-lg ${
            connected
              ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 backdrop-blur-md'
              : 'bg-rose-500/15 text-rose-400 border border-rose-500/30 backdrop-blur-md'
          }`}
        >
          <span className="relative flex items-center justify-center">
            <span
              className={`w-2 h-2 rounded-full ${
                connected
                  ? packetsReceiving
                    ? 'bg-emerald-400'
                    : 'bg-emerald-400/60'
                  : 'bg-rose-400'
              }`}
            />
            {connected && packetsReceiving && (
              <span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping" />
            )}
          </span>
          {connected ? 'LIVE' : 'DISCONNECTED'}
          {connected && <span className="text-emerald-400/60 ml-1 text-[9px]">ws:3000</span>}
        </div>

        {/* Top navigation bar */}
        <TopBar
          phase={phase}
          missionTime={missionTime}
          activeTab={activeTab}
          onTabChange={(tab: string) => setActiveTab(tab as PageTab)}
        />

        {/* Page content */}
        <div className="flex-1 relative flex flex-col min-h-0">
          {(activeTab === 'overview' || activeTab === 'missions') && (
            <>
              <HeroStage
                current={current}
                engineStatus={engineStatus}
                connected={connected}
              />
              {/* Device Status Panel */}
              <DeviceStatusPanel
                deviceConnected={engineStatus?.device_connected ?? false}
                pipelineRunning={engineStatus?.pipeline?.running ?? false}
                txActive={engineStatus?.tx_active ?? false}
                wsConnected={connected}
              />
              {/* Spectrum mini-widget */}
              <div className="px-6 relative z-10">
                <div className="bg-[rgba(18,20,22,0.6)] border border-white/5 rounded-xl overflow-hidden">
                  <SpectrumWaterfall spectrumData={spectrum} height={80} />
                </div>
              </div>
              <div className="h-[280px] grid grid-cols-12 gap-4 p-6 relative z-10 bg-gradient-to-t from-[#0a0a0b] via-[#0a0a0b]/90 to-transparent">
                <AssetCard current={current} className="col-span-3" />
                <MissionSettingsGrid className="col-span-6" />
                <TrajectoryCard className="col-span-3" />
              </div>
            </>
          )}

          {activeTab === 'telemetry' && (
            <div className="flex-1 overflow-y-auto">
              <SpectrumWaterfall spectrumData={spectrum} height={180} />
              <div className="border-t border-white/5" />
              <TelemetryGrid current={current} />
              <div className="border-t border-white/5" />
              <TelemetryCharts history={history} />
              <div className="border-t border-white/5" />
              <LowerTabs packets={packets} sendCommand={sendCommand} engineStatus={engineStatus} />
            </div>
          )}

          {activeTab === 'map' && (
            <div className="flex-1 relative min-h-0">
              <FlightMap current={current} history={history} />
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="flex-1 overflow-y-auto">
              <RfConfig sendCommand={sendCommand} engineStatus={engineStatus} />
            </div>
          )}
        </div>
        {/* Bottom Status Bar */}
        <StatusBar
          connected={connected}
          engineStatus={engineStatus}
          packetCount={packets.length}
          sendCommand={sendCommand}
        />
      </div>
    </div>
  );
}
