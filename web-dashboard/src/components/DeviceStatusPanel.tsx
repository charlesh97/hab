import React from 'react';
import { Radio, GitBranch, Wifi, Globe } from 'lucide-react';

interface DeviceStatusItem {
  icon: React.ReactNode;
  label: string;
  status: string;
  active: boolean;
}

interface DeviceStatusPanelProps {
  deviceConnected: boolean;
  pipelineRunning: boolean;
  txActive: boolean;
  wsConnected: boolean;
}

function StatusIndicator({ label, status, active, icon }: DeviceStatusItem) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-xl bg-white/[0.02] border border-white/5 hover:bg-white/[0.04] transition-colors">
      <div className={`p-2 rounded-lg ${active ? 'bg-emerald-500/10' : 'bg-white/5'}`}>
        <div className={`w-4 h-4 ${active ? 'text-emerald-400' : 'text-white/30'}`}>
          {icon}
        </div>
      </div>
      <div className="flex flex-col min-w-0">
        <span className="text-white/40 text-[10px] font-light tracking-wide uppercase">
          {label}
        </span>
        <div className="flex items-center gap-1.5">
          <span
            className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
              active
                ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]'
                : 'bg-rose-400/60'
            }`}
          />
          <span
            className={`text-xs font-mono ${
              active ? 'text-emerald-300' : 'text-rose-300/60'
            }`}
          >
            {status}
          </span>
        </div>
      </div>
    </div>
  );
}

export function DeviceStatusPanel({
  deviceConnected,
  pipelineRunning,
  txActive,
  wsConnected,
}: DeviceStatusPanelProps) {
  const items: DeviceStatusItem[] = [
    {
      icon: <Radio />,
      label: 'HackRF',
      status: deviceConnected ? 'Connected' : 'Disconnected',
      active: deviceConnected,
    },
    {
      icon: <GitBranch />,
      label: 'Pipeline',
      status: pipelineRunning ? 'Running' : 'Stopped',
      active: pipelineRunning,
    },
    {
      icon: <Wifi />,
      label: 'TX',
      status: txActive ? 'Active' : 'Inactive',
      active: txActive,
    },
    {
      icon: <Globe />,
      label: 'WebSocket',
      status: wsConnected ? 'Connected' : 'Disconnected',
      active: wsConnected,
    },
  ];

  return (
    <div className="px-6 relative z-10">
      <div className="bg-[rgba(18,20,22,0.5)] border border-white/5 rounded-xl p-3 backdrop-blur-sm">
        <div className="grid grid-cols-4 gap-2">
          {items.map((item) => (
            <StatusIndicator key={item.label} {...item} />
          ))}
        </div>
      </div>
    </div>
  );
}
