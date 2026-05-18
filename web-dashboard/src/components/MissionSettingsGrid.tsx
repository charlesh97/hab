import React from 'react';
import { ArrowUpRightIcon } from 'lucide-react';
interface MissionSettingsGridProps {
  className?: string;
}
export function MissionSettingsGrid({
  className = ''
}: MissionSettingsGridProps) {
  return (
    <div
      className={`bg-white/[0.02] border border-white/10 rounded-3xl p-5 flex flex-col ${className}`}>
      
      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-white text-sm font-normal tracking-wide">
            Mission settings
          </h3>
          <p className="text-white/40 text-[10px] font-light tracking-wider mt-0.5">
            ID: #633112
          </p>
        </div>
        <button className="w-6 h-6 rounded-full bg-white/5 flex items-center justify-center text-white/50 hover:text-white hover:bg-white/10 transition-colors">
          <ArrowUpRightIcon className="w-3 h-3" />
        </button>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-4 grid-rows-2 gap-3 flex-1">
        <Tile label="Beacon" svg={<BeaconSVG />} />
        <Tile label="Predict" svg={<PredictSVG />} />
        <Tile label="Recover" svg={<RecoverSVG />} isActive />
        <Tile label="Terrain" svg={<TerrainSVG />} />
        <Tile label="Track" svg={<TrackSVG />} />
        <Tile label="Analyze" svg={<AnalyzeSVG />} />
        <Tile label="Cutdown" svg={<CutdownSVG />} />
        <Tile label="Telemetry" svg={<TelemetrySVG />} />
      </div>
    </div>);

}
function Tile({
  label,
  svg,
  isActive = false




}: {label: string;svg: React.ReactNode;isActive?: boolean;}) {
  return (
    <div
      className={`relative rounded-2xl p-3 flex flex-col overflow-hidden group cursor-pointer transition-all duration-300 ${isActive ? 'bg-orange-500/10 border border-orange-500/30 shadow-[inset_0_0_20px_rgba(249,115,22,0.1)]' : 'bg-white/[0.02] border border-white/5 hover:bg-white/[0.04] hover:border-white/10'}`}>
      
      <span
        className={`text-[9px] font-light tracking-wider mb-2 ${isActive ? 'text-orange-400' : 'text-white/60'}`}>
        
        {label}
      </span>
      <div className="flex-1 flex items-center justify-center opacity-70 group-hover:opacity-100 transition-opacity">
        {svg}
      </div>
    </div>);

}
// Abstract SVGs for tiles
const BeaconSVG = () =>
<svg viewBox="0 0 40 40" className="w-full h-full max-h-12 text-white/50">
    <circle cx="20" cy="20" r="4" fill="currentColor" />
    <circle
    cx="20"
    cy="20"
    r="10"
    fill="none"
    stroke="currentColor"
    strokeWidth="0.5"
    strokeDasharray="2 2" />
  
    <circle
    cx="20"
    cy="20"
    r="16"
    fill="none"
    stroke="currentColor"
    strokeWidth="0.5"
    opacity="0.5" />
  
  </svg>;

const PredictSVG = () =>
<svg viewBox="0 0 40 40" className="w-full h-full max-h-12 text-white/50">
    <path
    d="M5 35 Q 20 5 35 15"
    fill="none"
    stroke="currentColor"
    strokeWidth="1"
    strokeDasharray="2 2" />
  
    <circle cx="35" cy="15" r="2" fill="currentColor" />
    <circle cx="5" cy="35" r="2" fill="currentColor" opacity="0.5" />
  </svg>;

const RecoverSVG = () =>
<svg
  viewBox="0 0 40 40"
  className="w-full h-full max-h-12 text-orange-500 drop-shadow-[0_0_5px_rgba(249,115,22,0.5)]">
  
    {/* Isometric grid base */}
    <path
    d="M5 25 L20 18 L35 25 L20 32 Z"
    fill="rgba(249,115,22,0.2)"
    stroke="currentColor"
    strokeWidth="0.5" />
  
    {/* Target reticle */}
    <circle
    cx="20"
    cy="25"
    r="6"
    fill="none"
    stroke="currentColor"
    strokeWidth="1" />
  
    <path
    d="M20 17 L20 21 M20 29 L20 33 M12 25 L16 25 M24 25 L28 25"
    stroke="currentColor"
    strokeWidth="1" />
  
    <circle cx="20" cy="25" r="1" fill="currentColor" />
  </svg>;

const TerrainSVG = () =>
<svg viewBox="0 0 40 40" className="w-full h-full max-h-12 text-white/50">
    <path
    d="M2 30 L10 20 L18 25 L28 12 L38 28"
    fill="none"
    stroke="currentColor"
    strokeWidth="0.5" />
  
    <path
    d="M2 32 L12 24 L20 28 L30 16 L38 30"
    fill="none"
    stroke="currentColor"
    strokeWidth="0.5"
    opacity="0.5" />
  
    <circle cx="28" cy="12" r="1.5" fill="currentColor" />
  </svg>;

const TrackSVG = () =>
<svg viewBox="0 0 40 40" className="w-full h-full max-h-12 text-white/50">
    <circle
    cx="20"
    cy="20"
    r="16"
    fill="none"
    stroke="currentColor"
    strokeWidth="0.5" />
  
    <path
    d="M20 20 L32 8"
    stroke="currentColor"
    strokeWidth="1"
    opacity="0.5" />
  
    <path
    d="M20 20 A 16 16 0 0 1 36 20 L 20 20 Z"
    fill="currentColor"
    opacity="0.1" />
  
    <circle cx="28" cy="12" r="1.5" fill="currentColor" />
  </svg>;

const AnalyzeSVG = () =>
<svg viewBox="0 0 40 40" className="w-full h-full max-h-12 text-white/50">
    <path
    d="M5 25 Q 12 15 20 25 T 35 15"
    fill="none"
    stroke="currentColor"
    strokeWidth="0.5" />
  
    <rect
    x="10"
    y="20"
    width="2"
    height="10"
    fill="currentColor"
    opacity="0.3" />
  
    <rect
    x="15"
    y="15"
    width="2"
    height="15"
    fill="currentColor"
    opacity="0.6" />
  
    <rect
    x="20"
    y="22"
    width="2"
    height="8"
    fill="currentColor"
    opacity="0.4" />
  
    <rect
    x="25"
    y="12"
    width="2"
    height="18"
    fill="currentColor"
    opacity="0.8" />
  
  </svg>;

const CutdownSVG = () =>
<svg viewBox="0 0 40 40" className="w-full h-full max-h-12 text-white/50">
    <circle
    cx="20"
    cy="20"
    r="12"
    fill="none"
    stroke="currentColor"
    strokeWidth="0.5" />
  
    <path
    d="M14 20 L26 20 M20 14 L20 26"
    stroke="currentColor"
    strokeWidth="0.5" />
  
    <circle cx="20" cy="20" r="2" fill="currentColor" />
  </svg>;

const TelemetrySVG = () =>
<svg viewBox="0 0 40 40" className="w-full h-full max-h-12 text-white/50">
    <circle
    cx="20"
    cy="20"
    r="14"
    fill="none"
    stroke="currentColor"
    strokeWidth="0.5" />
  
    <circle
    cx="20"
    cy="20"
    r="8"
    fill="none"
    stroke="currentColor"
    strokeWidth="0.5"
    opacity="0.5" />
  
    <circle cx="20" cy="20" r="2" fill="currentColor" />
    <circle cx="20" cy="6" r="1.5" fill="currentColor" />
    <circle cx="34" cy="20" r="1.5" fill="currentColor" />
    <circle cx="20" cy="34" r="1.5" fill="currentColor" />
    <circle cx="6" cy="20" r="1.5" fill="currentColor" />
  </svg>;