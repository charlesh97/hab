import React from 'react';
import { FlightPhase } from '../types';
import { ActivityIcon, AlertCircleIcon, CheckCircle2Icon } from 'lucide-react';
export function PhaseBadge({ phase }: {phase: FlightPhase;}) {
  const colors = {
    'PRE-LAUNCH': 'bg-slate-100 text-slate-600 border-slate-200',
    ASCENT: 'bg-sky-100 text-sky-700 border-sky-200',
    FLOAT: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    DESCENT: 'bg-amber-100 text-amber-700 border-amber-200',
    RECOVERED: 'bg-indigo-100 text-indigo-700 border-indigo-200'
  };
  return (
    <div
      className={`px-2.5 py-1 rounded-md border text-xs font-bold tracking-wider ${colors[phase]}`}>
      
      {phase}
    </div>);

}
export function StatusPill({
  label,
  status



}: {label: string;status: 'NOMINAL' | 'DEGRADED' | 'OFFLINE';}) {
  const colors = {
    NOMINAL: 'text-emerald-600 bg-emerald-50 border-emerald-200',
    DEGRADED: 'text-amber-600 bg-amber-50 border-amber-200',
    OFFLINE: 'text-rose-600 bg-rose-50 border-rose-200'
  };
  const Icon =
  status === 'NOMINAL' ?
  CheckCircle2Icon :
  status === 'DEGRADED' ?
  ActivityIcon :
  AlertCircleIcon;
  return (
    <div
      className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs font-semibold ${colors[status]}`}>
      
      <Icon className="w-3.5 h-3.5" />
      <span className="tracking-wide">{label}</span>
    </div>);

}
interface StatTileProps {
  label: string;
  value: string | number;
  unit: string;
  trend?: 'up' | 'down' | 'flat';
  icon?: React.ReactNode;
}
export function StatTile({ label, value, unit, trend, icon }: StatTileProps) {
  return (
    <div className="bg-[rgba(18,20,22,0.6)] border border-white/5 rounded-lg p-3 flex flex-col justify-between">
      <div className="flex items-center justify-between text-slate-400 mb-1">
        <span className="text-[10px] font-bold uppercase tracking-widest">
          {label}
        </span>
        {icon && <div className="text-slate-500">{icon}</div>}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-mono font-bold text-white">
          {value}
        </span>
        <span className="text-xs font-mono text-slate-400">{unit}</span>
      </div>
    </div>);

}