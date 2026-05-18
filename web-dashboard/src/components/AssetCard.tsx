import React from 'react';
import { TelemetrySample } from '../types';
import { ArrowUpRightIcon } from 'lucide-react';
interface AssetCardProps {
  current: TelemetrySample;
  className?: string;
}
export function AssetCard({ current, className = '' }: AssetCardProps) {
  return (
    <div
      className={`bg-white/[0.02] border border-white/10 rounded-3xl p-5 flex flex-col relative overflow-hidden ${className}`}>
      
      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-white text-sm font-normal tracking-wide">
            STRATOS HAB-1
          </h3>
          <p className="text-white/40 text-[10px] font-light tracking-wider mt-0.5">
            ID: #521514
          </p>
        </div>
        <button className="w-6 h-6 rounded-full bg-white/5 flex items-center justify-center text-white/50 hover:text-white hover:bg-white/10 transition-colors">
          <ArrowUpRightIcon className="w-3 h-3" />
        </button>
      </div>

      {/* Payload Illustration */}
      <div className="flex-1 flex items-center justify-center mb-4 relative">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent to-[#0a0a0b]/50 rounded-xl" />
        <svg
          viewBox="0 0 200 100"
          className="w-full h-full max-h-24 opacity-80 drop-shadow-2xl">
          
          {/* Stylized Payload Box */}
          <rect
            x="50"
            y="30"
            width="100"
            height="40"
            rx="4"
            fill="#1a1a1c"
            stroke="rgba(255,255,255,0.2)"
            strokeWidth="1" />
          
          {/* Solar Panels / Texture */}
          <rect
            x="55"
            y="35"
            width="25"
            height="30"
            rx="2"
            fill="rgba(249,115,22,0.15)"
            stroke="rgba(249,115,22,0.3)"
            strokeWidth="0.5" />
          
          <rect
            x="85"
            y="35"
            width="25"
            height="30"
            rx="2"
            fill="rgba(255,255,255,0.05)"
            stroke="rgba(255,255,255,0.1)"
            strokeWidth="0.5" />
          
          <rect
            x="115"
            y="35"
            width="25"
            height="30"
            rx="2"
            fill="rgba(255,255,255,0.05)"
            stroke="rgba(255,255,255,0.1)"
            strokeWidth="0.5" />
          
          {/* Text overlay */}
          <text
            x="67.5"
            y="52"
            fill="rgba(249,115,22,0.8)"
            fontSize="6"
            fontFamily="sans-serif"
            textAnchor="middle">
            
            Active
          </text>
          {/* Antennas */}
          <line
            x1="100"
            y1="30"
            x2="100"
            y2="10"
            stroke="rgba(255,255,255,0.3)"
            strokeWidth="1" />
          
          <circle cx="100" cy="10" r="1.5" fill="rgba(255,255,255,0.5)" />
        </svg>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-2 mt-auto">
        <StatCol
          value={`${current.battery.toFixed(0)}%`}
          label="Battery charge" />
        
        <StatCol value={current.verticalSpeed.toFixed(1)} label="Vert Speed" />
        <StatCol value={current.gpsSats.toString()} label="GPS Sats" />
        <StatCol value="Good" label="Link Signal" />
      </div>
    </div>);

}
function StatCol({ value, label }: {value: string;label: string;}) {
  return (
    <div className="flex flex-col">
      <span className="text-white text-xs font-mono mb-1">{value}</span>
      <span className="text-white/40 text-[9px] font-light tracking-wide leading-tight">
        {label}
      </span>
    </div>);

}