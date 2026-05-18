import React from 'react';
import { SignalIcon, VideoIcon } from 'lucide-react';
export function VideoFeeds() {
  return (
    <div className="p-4 overflow-y-auto space-y-4 bg-[rgba(18,20,22,0.6)]">
      <VideoPlayer title="ONBOARD CAM" bitrate="2.4 Mbps" signal="98%" />
      <VideoPlayer title="CHASE VEHICLE" bitrate="1.8 Mbps" signal="85%" />
    </div>);

}
function VideoPlayer({
  title,
  bitrate,
  signal




}: {title: string;bitrate: string;signal: string;}) {
  return (
    <div className="bg-[rgba(18,20,22,0.8)] border border-white/5 rounded-lg overflow-hidden">
      {/* Video Placeholder */}
      <div className="aspect-video bg-slate-900 relative flex items-center justify-center">
        <VideoIcon className="w-12 h-12 text-slate-700" />

        {/* Overlays */}
        <div className="absolute top-3 left-3 flex items-center gap-2">
          <div className="bg-rose-600 text-white text-[10px] font-bold px-2 py-0.5 rounded animate-pulse tracking-widest">
            LIVE
          </div>
          <div className="bg-black/50 backdrop-blur text-white text-[10px] font-mono px-2 py-0.5 rounded">
            {title}
          </div>
        </div>

        <div className="absolute bottom-3 right-3 flex items-center gap-3 bg-black/50 backdrop-blur text-white text-[10px] font-mono px-2 py-1 rounded">
          <div className="flex items-center gap-1">
            <SignalIcon className="w-3 h-3 text-emerald-400" />
            {signal}
          </div>
          <div>{bitrate}</div>
        </div>
      </div>

      {/* Controls */}
      <div className="p-3 border-t border-white/5 flex gap-2">
        <input
          type="text"
          defaultValue="rtsp://hab-1.local/stream1"
          className="flex-1 bg-[rgba(18,20,22,0.6)] border border-white/5 rounded text-xs font-mono px-2 py-1.5 text-slate-300 focus:outline-none focus:border-sky-500 placeholder:text-slate-600" />
        
        <button className="bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold px-3 py-1.5 rounded transition-colors">
          Reconnect
        </button>
      </div>
    </div>);

}