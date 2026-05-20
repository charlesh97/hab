import { Play, Square } from 'lucide-react';

export function SettingsPipeline() {
  return (
    <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-8">
      <div className="flex gap-4 mb-8">
        <div className="flex-1 bg-surface-container-lowest border border-outline-variant rounded px-4 py-3 flex items-center justify-between text-outline">
          <span className="font-mono text-xs">/opt/stratos/capture/telemetry_915mhz.ts</span>
          <button className="px-3 py-1 bg-surface-container-high rounded text-[10px] font-label-caps hover:text-on-surface">BROWSE</button>
        </div>
        <button className="px-6 py-2 bg-tracking-green text-white rounded font-label-caps flex items-center gap-2"><Play size={16} /> START PIPELINE</button>
        <button className="px-6 py-2 bg-reentry-red/20 text-reentry-red border border-reentry-red/50 rounded font-label-caps opacity-50"><Square size={16} /> STOP</button>
      </div>

      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-surface p-4 rounded border border-outline-variant/30"><p className="text-[10px] font-label-caps text-outline mb-1">BITRATE</p><p className="font-mono text-lg text-tracking-green">965,326 <span className="text-xs opacity-50">bps</span></p></div>
        <div className="bg-surface p-4 rounded border border-outline-variant/30"><p className="text-[10px] font-label-caps text-outline mb-1">DURATION</p><p className="font-mono text-lg text-on-surface">00:47:32</p></div>
        <div className="bg-surface p-4 rounded border border-outline-variant/30"><p className="text-[10px] font-label-caps text-outline mb-1">DROP RATIO</p><p className="font-mono text-lg text-reentry-red">0.02%</p></div>
        <div className="bg-surface p-4 rounded border border-outline-variant/30"><p className="text-[10px] font-label-caps text-outline mb-1">SINK HEALTH</p><p className="font-mono text-lg text-tracking-green">ACTIVE</p></div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 h-[250px]">
        <div className="bg-black rounded-lg p-4 flex flex-col">
          <div className="flex justify-between items-center mb-2 border-b border-white/10 pb-1">
            <span className="text-[10px] font-mono text-outline">FFMPEG_STREAM_OUT</span>
            <span className="w-2 h-2 rounded-full bg-tracking-green animate-pulse" />
          </div>
          <div className="flex-1 overflow-y-auto font-mono text-[11px] text-green-500 leading-relaxed" style={{ scrollbarWidth: 'thin' }}>
            <div>[h264 @ 0x559e86c] frame=1240 fps=30 q=28.0 size=450kB</div>
            <div>[h264 @ 0x559e86c] frame=1270 fps=30 q=28.0 size=482kB</div>
            <div>[h264 @ 0x559e86c] frame=1300 fps=30 q=29.0 size=512kB</div>
          </div>
        </div>
        <div className="bg-black rounded-lg p-4 flex flex-col">
          <div className="flex justify-between items-center mb-2 border-b border-white/10 pb-1">
            <span className="text-[10px] font-mono text-outline">TSP_PACKET_PROCESSOR</span>
            <span className="w-2 h-2 rounded-full bg-tracking-green animate-pulse" />
          </div>
          <div className="flex-1 overflow-y-auto font-mono text-[11px] text-blue-400 leading-relaxed" style={{ scrollbarWidth: 'thin' }}>
            <div>* tsp: PID 0x0100 (SDT) pkt: 4,502, rate: 1,200 b/s</div>
            <div>* tsp: PID 0x1FFF (Null) pkt: 1,204,502, rate: 45,600 b/s</div>
            <div>* tsp: PID 0x0010 (NIT) pkt: 890, rate: 200 b/s</div>
          </div>
        </div>
      </div>
    </div>
  );
}
