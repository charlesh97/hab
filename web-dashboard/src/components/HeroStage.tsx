import React from 'react';
import { TelemetrySample } from '../types';
import {
  CheckCircle2Icon,
  SearchIcon,
  CrosshairIcon,
  ZoomInIcon,
  ZoomOutIcon } from
'lucide-react';
interface HeroStageProps {
  current: TelemetrySample;
  engineStatus?: {
    running: boolean;
    tx_active: boolean;
    device_connected: boolean;
    frequency: number;
    symbol_rate: number;
    uptime_sec: number;
    pipeline: { running: boolean; file_path: string; bitrate: number } | null;
  } | null;
  connected?: boolean;
}
export function HeroStage({ current, engineStatus, connected }: HeroStageProps) {
  return (
    <div className="flex-1 relative overflow-hidden">
      {/* Background Image */}
      <img
        src="https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=2000&q=80"
        alt="Stratosphere"
        className="absolute inset-0 w-full h-full object-cover opacity-60 mix-blend-screen" />
      

      {/* Gradients for legibility and blending */}
      <div className="absolute inset-0 bg-gradient-to-b from-[#0a0a0b]/80 via-transparent to-[#0a0a0b]" />
      <div className="absolute inset-0 bg-gradient-to-r from-[#0a0a0b]/50 via-transparent to-[#0a0a0b]/50" />

      {/* Top Left Status Pill */}
      <div className="absolute top-24 left-8 flex items-center gap-3 bg-white/[0.03] backdrop-blur-md border border-white/10 rounded-full pl-2 pr-5 py-2 shadow-lg">
        <div className={`rounded-full p-1 ${connected ? 'bg-emerald-500/20' : 'bg-rose-500/20'}`}>
          <CheckCircle2Icon className={`w-4 h-4 ${connected ? 'text-emerald-400' : 'text-rose-400'}`} />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-white/70 text-xs font-light tracking-wide">
            Telemetry link {connected ? 'nominal' : 'offline'}
          </span>
          {engineStatus && (
            <>
              <span className="text-white/20">|</span>
              <span className={`text-[10px] font-mono ${engineStatus.running ? 'text-emerald-400/70' : 'text-rose-400/70'}`}>
                ENG:{engineStatus.running ? 'ON' : 'OFF'}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Right Edge Controls */}
      <div className="absolute top-1/2 -translate-y-1/2 right-8 flex flex-col gap-3">
        {[SearchIcon, CrosshairIcon, ZoomInIcon, ZoomOutIcon].map((Icon, i) =>
        <button
          key={i}
          className="w-10 h-10 rounded-full bg-white/[0.03] backdrop-blur-md border border-white/10 flex items-center justify-center text-white/50 hover:text-white hover:bg-white/10 transition-colors">
          
            <Icon className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Floating Orange Position Dot */}
      <div className="absolute top-[60%] left-[45%] -translate-x-1/2 -translate-y-1/2">
        <div className="relative flex items-center justify-center">
          <div className="absolute w-12 h-12 bg-orange-500/20 rounded-full animate-ping" />
          <div className="w-4 h-4 bg-orange-500 rounded-full border-2 border-[#0a0a0b] shadow-[0_0_15px_rgba(249,115,22,0.6)] z-10" />
        </div>
      </div>

      {/* Center Glass Telemetry Card */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80">
        <div className="relative bg-white/[0.02] backdrop-blur-2xl border border-white/10 rounded-3xl p-6 shadow-[0_0_50px_-15px_rgba(14,165,233,0.25)] overflow-hidden">
          {/* Soft inner glow */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-1/2 bg-sky-500/10 blur-3xl rounded-full pointer-events-none" />

          <div className="relative z-10">
            <h2 className="text-white text-lg font-normal tracking-wide mb-1">
              HAB-1 Stratos
            </h2>
            <p className="text-white/40 text-xs font-light tracking-wider mb-6">
              Recon Operation
            </p>

            {/* Minimalist Balloon Icon/Illustration */}
            <div className="w-full h-24 mb-6 flex items-center justify-center opacity-80">
              <svg
                viewBox="0 0 100 100"
                className="w-20 h-20 text-white/80 drop-shadow-[0_0_10px_rgba(255,255,255,0.3)]">
                
                <path
                  d="M50 10 C30 10 20 30 20 45 C20 65 45 85 50 90 C55 85 80 65 80 45 C80 30 70 10 50 10 Z"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5" />
                
                <path
                  d="M45 90 L45 95 L55 95 L55 90"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5" />
                
                <rect
                  x="42"
                  y="95"
                  width="16"
                  height="10"
                  rx="2"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5" />
                
              </svg>
            </div>

            <div className="space-y-3">
              <TelemetryRow
                label="Altitude"
                value={current.altitude.toFixed(0)}
                unit="m" />
              
              <TelemetryRow
                label="Climb"
                value={current.verticalSpeed.toFixed(1)}
                unit="m/s" />
              
              <TelemetryRow
                label="Ext Temp"
                value={current.externalTemp.toFixed(1)}
                unit="°C" />
              
              <TelemetryRow
                label="Pressure"
                value={current.pressure.toFixed(1)}
                unit="hPa" />
              
            </div>
          </div>
        </div>
      </div>
    </div>);

}
function TelemetryRow({
  label,
  value,
  unit




}: {label: string;value: string;unit: string;}) {
  return (
    <div className="flex justify-between items-center border-b border-white/5 pb-2 last:border-0 last:pb-0">
      <span className="text-white/40 text-xs font-light tracking-wide">
        {label}
      </span>
      <div className="flex items-baseline gap-1">
        <span className="text-white text-sm font-mono">{value}</span>
        <span className="text-white/40 text-[10px] font-mono">{unit}</span>
      </div>
    </div>);

}