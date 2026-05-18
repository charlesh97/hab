import React from 'react';
import { ArrowUpRightIcon } from 'lucide-react';
interface TrajectoryCardProps {
  className?: string;
}
export function TrajectoryCard({ className = '' }: TrajectoryCardProps) {
  return (
    <div
      className={`bg-white/[0.02] border border-white/10 rounded-3xl p-5 flex flex-col ${className}`}>
      
      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-white text-sm font-normal tracking-wide">
            Trajectory Map
          </h3>
          <p className="text-white/40 text-[10px] font-light tracking-wider mt-0.5">
            3 Waypoints
          </p>
        </div>
        <button className="w-6 h-6 rounded-full bg-white/5 flex items-center justify-center text-white/50 hover:text-white hover:bg-white/10 transition-colors">
          <ArrowUpRightIcon className="w-3 h-3" />
        </button>
      </div>

      {/* Stylized Map Area */}
      <div className="flex-1 relative mb-4">
        <svg viewBox="0 0 200 100" className="w-full h-full opacity-80">
          {/* Decorative Mountains/Terrain */}
          <path
            d="M0 90 L40 60 L80 80 L130 40 L170 70 L200 50 L200 100 L0 100 Z"
            fill="rgba(255,255,255,0.02)"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth="1" />
          
          <path
            d="M0 100 L60 70 L100 85 L150 55 L200 80 L200 100 Z"
            fill="rgba(255,255,255,0.03)"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth="1" />
          

          {/* Trajectory Line */}
          <path
            d="M30 70 Q 100 10 170 60"
            fill="none"
            stroke="rgba(255,255,255,0.2)"
            strokeWidth="1"
            strokeDasharray="3 3" />
          

          {/* Waypoints */}
          {/* Point 1 */}
          <g transform="translate(30, 70)">
            <circle cx="0" cy="0" r="12" fill="rgba(255,255,255,0.05)" />
            <circle cx="0" cy="0" r="3" fill="#fff" />
            <text
              x="0"
              y="20"
              fill="rgba(255,255,255,0.6)"
              fontSize="8"
              fontFamily="monospace"
              textAnchor="middle">
              
              14:10
            </text>
          </g>

          {/* Point 2 (Apex) */}
          <g transform="translate(100, 25)">
            <circle cx="0" cy="0" r="16" fill="rgba(255,255,255,0.05)" />
            <circle cx="0" cy="0" r="3" fill="#fff" />
            <text
              x="0"
              y="22"
              fill="rgba(255,255,255,0.6)"
              fontSize="8"
              fontFamily="monospace"
              textAnchor="middle">
              
              14:35
            </text>
          </g>

          {/* Point 3 */}
          <g transform="translate(170, 60)">
            <circle cx="0" cy="0" r="12" fill="rgba(255,255,255,0.05)" />
            <circle cx="0" cy="0" r="3" fill="#fff" />
            <text
              x="0"
              y="20"
              fill="rgba(255,255,255,0.6)"
              fontSize="8"
              fontFamily="monospace"
              textAnchor="middle">
              
              14:47
            </text>
          </g>
        </svg>
      </div>

      {/* Timeline */}
      <div className="flex justify-between items-end gap-2 mt-auto">
        <TimelineSegment label="Launch" time="14:10" isActive={false} />
        <TimelineSegment label="Float" time="14:35" isActive={true} />
        <TimelineSegment label="Recovery" time="14:47" isActive={false} />
      </div>
    </div>);

}
function TimelineSegment({
  label,
  time,
  isActive




}: {label: string;time: string;isActive: boolean;}) {
  return (
    <div className="flex-1 flex flex-col">
      <div className="flex gap-1 mb-1.5">
        {[...Array(6)].map((_, i) =>
        <div
          key={i}
          className={`h-1 flex-1 rounded-full ${isActive ? 'bg-orange-500' : 'bg-white/10'}`} />

        )}
      </div>
      <div className="flex justify-between items-center">
        <span
          className={`text-[9px] font-light tracking-wide ${isActive ? 'text-orange-400' : 'text-white/40'}`}>
          
          {label}
        </span>
        <span className="text-[9px] font-mono text-white/30">{time}</span>
      </div>
    </div>);

}