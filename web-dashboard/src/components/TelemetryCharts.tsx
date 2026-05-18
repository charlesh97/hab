import React from 'react';
import { TelemetrySample } from '../types';
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer } from
'recharts';
interface TelemetryChartsProps {
  history: TelemetrySample[];
}
export function TelemetryCharts({ history }: TelemetryChartsProps) {
  // Format data for charts
  const data = history.map((h) => ({
    time: new Date(h.timestamp).toLocaleTimeString([], {
      minute: '2-digit',
      second: '2-digit'
    }),
    alt: Math.round(h.altitude),
    extTemp: Number(h.externalTemp.toFixed(1)),
    intTemp: Number(h.internalTemp.toFixed(1))
  }));
  return (
    <div className="flex flex-col gap-4 p-4 bg-[rgba(18,20,22,0.6)] shrink-0 h-64">
      <div className="flex-1 flex gap-4">
        {/* Altitude Chart */}
        <div className="flex-1 border border-white/5 rounded-lg p-2 bg-[rgba(18,20,22,0.3)]">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2 pl-2">
            Altitude Profile
          </div>
          <div className="h-[calc(100%-24px)] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={data}
                margin={{
                  top: 5,
                  right: 5,
                  left: -20,
                  bottom: 0
                }}>
                
                <defs>
                  <linearGradient id="colorAlt" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0284c7" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#0284c7" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="rgba(255,255,255,0.05)" />
                
                <XAxis
                  dataKey="time"
                  tick={{
                    fontSize: 10,
                    fontFamily: 'JetBrains Mono'
                  }}
                  stroke="#64748b"
                  minTickGap={30} />
                
                <YAxis
                  tick={{
                    fontSize: 10,
                    fontFamily: 'JetBrains Mono'
                  }}
                  stroke="#64748b" />
                
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    borderRadius: '8px',
                    border: '1px solid rgba(255,255,255,0.1)',
                    fontSize: '12px',
                    fontFamily: 'JetBrains Mono'
                  }}
                  labelStyle={{
                    color: '#94a3b8',
                    marginBottom: '4px'
                  }} />
                
                <Area
                  type="monotone"
                  dataKey="alt"
                  stroke="#0284c7"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorAlt)"
                  isAnimationActive={false} />
                
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Temperature Chart */}
        <div className="flex-1 border border-white/5 rounded-lg p-2 bg-[rgba(18,20,22,0.3)]">
          <div className="flex justify-between items-center mb-2 pl-2 pr-2">
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
              Thermal
            </div>
            <div className="flex gap-3 text-[9px] font-bold uppercase">
              <span className="text-emerald-500">Internal</span>
              <span className="text-indigo-500">External</span>
            </div>
          </div>
          <div className="h-[calc(100%-24px)] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={data}
                margin={{
                  top: 5,
                  right: 5,
                  left: -20,
                  bottom: 0
                }}>
                
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="rgba(255,255,255,0.05)" />
                
                <XAxis
                  dataKey="time"
                  tick={{
                    fontSize: 10,
                    fontFamily: 'JetBrains Mono'
                  }}
                  stroke="#64748b"
                  minTickGap={30} />
                
                <YAxis
                  tick={{
                    fontSize: 10,
                    fontFamily: 'JetBrains Mono'
                  }}
                  stroke="#64748b" />
                
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    borderRadius: '8px',
                    border: '1px solid rgba(255,255,255,0.1)',
                    fontSize: '12px',
                    fontFamily: 'JetBrains Mono',
                    color: '#e2e8f0'
                  }} />
                
                <Line
                  type="monotone"
                  dataKey="intTemp"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false} />
                
                <Line
                  type="monotone"
                  dataKey="extTemp"
                  stroke="#6366f1"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false} />
                
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>);

}
