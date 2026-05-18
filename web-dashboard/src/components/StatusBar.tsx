import React from 'react';

interface StatusBarProps {
  connected: boolean;
  engineStatus: any;
  packetCount: number;
  sendCommand: (cmd: string, data?: any) => void;
}

export function StatusBar({ connected, engineStatus, packetCount, sendCommand }: StatusBarProps) {
  const uptime = engineStatus?.uptime_sec || 0;
  const mins = Math.floor(uptime / 60);
  const secs = Math.floor(uptime % 60);

  return (
    <div className="flex items-center justify-between px-5 py-2 bg-[rgba(18,20,22,0.82)] border-t border-white/5 text-[10px] font-mono text-white/40">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-rose-400'}`} />
          {connected ? 'CONNECTED' : 'DISCONNECTED'}
        </div>
        <div>PKT: {packetCount}</div>
        <div>UPTIME: {mins}m {secs}s</div>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-white/30">HAB-1 STRATOS</span>
        <span className="text-white/20">v0.3</span>
      </div>
    </div>
  );
}
