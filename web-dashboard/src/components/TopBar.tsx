import React from 'react';
import { FlightPhase } from '../types';
import { ChevronDownIcon, CrosshairIcon, SunIcon } from 'lucide-react';

interface TopBarProps {
  phase: FlightPhase;
  missionTime: number;
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'telemetry', label: 'Telemetry' },
  { id: 'map', label: 'Map' },
  { id: 'settings', label: 'Settings' },
];

export function TopBar({ phase, missionTime, activeTab, onTabChange }: TopBarProps) {
  return (
    <header className="absolute top-0 left-0 w-full h-20 px-8 flex items-center justify-between z-50">
      {/* Left: Logo & Brand */}
      <div className="flex items-center gap-3 w-64">
        <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center backdrop-blur-md border border-white/10">
          <CrosshairIcon className="w-4 h-4 text-white" />
        </div>
        <span className="text-white text-sm font-light tracking-widest">
          STRATOS
        </span>
      </div>

      {/* Center: Pill Navigation */}
      <nav className="flex items-center gap-2 bg-white/[0.02] backdrop-blur-xl border border-white/10 rounded-full p-1.5 shadow-2xl">
        {TABS.map((tab) => (
          <NavPill
            key={tab.id}
            label={tab.label}
            isActive={activeTab === tab.id}
            onClick={() => onTabChange(tab.id)}
          />
        ))}
      </nav>

      {/* Right: Mission ID & Status */}
      <div className="flex items-center justify-end gap-3 w-64">
        <div className="flex items-center gap-3 bg-white/[0.03] backdrop-blur-md border border-white/10 rounded-full pl-4 pr-3 py-2 cursor-pointer hover:bg-white/[0.06] transition-colors">
          <div className="flex flex-col">
            <span className="text-white text-xs font-normal">
              HAB-1 Stratos
            </span>
            <span className="text-white/40 text-[10px] font-light tracking-wider">
              ID: #521514
            </span>
          </div>
          <ChevronDownIcon className="w-4 h-4 text-white/50 ml-2" />
        </div>

        <div className="flex items-center gap-2 bg-white/[0.03] backdrop-blur-md border border-white/10 rounded-full px-4 py-2.5">
          <SunIcon className="w-4 h-4 text-orange-500" />
          <span className="text-white text-xs font-light tracking-wide">
            {phase}
          </span>
        </div>
      </div>
    </header>
  );
}

function NavPill({ label, isActive, onClick }: { label: string; isActive: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-6 py-2 rounded-full text-xs font-light tracking-wide transition-all duration-300 ${
        isActive
          ? 'bg-white/10 text-white border border-white/10 shadow-[inset_0_0_10px_rgba(255,255,255,0.05)]'
          : 'text-white/50 hover:text-white/80 hover:bg-white/5 border border-transparent'
      }`}
    >
      {label}
    </button>
  );
}
