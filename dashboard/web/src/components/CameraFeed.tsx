import { Video } from 'lucide-react';

interface CameraFeedProps {
  bitrate?: number;
  signalQuality?: number;
  rtspUrl?: string;
}

export function CameraFeed({ bitrate = 2.4, signalQuality = 98, rtspUrl = 'rtsp://192.168.1.100/stream1' }: CameraFeedProps) {
  return (
    <div className="card-border bg-surface-container-lowest rounded-[20px] border border-outline-variant flex-1 relative flex flex-col items-center justify-center">
      <div className="flex flex-col items-center gap-4 opacity-30">
        <Video size={64} />
        <span className="font-label-caps text-xl tracking-widest">NO VIDEO SIGNAL</span>
      </div>

      <div className="absolute top-4 left-4 flex gap-2">
        <div className="px-2 py-0.5 bg-reentry-red/20 text-reentry-red text-[10px] font-bold flex items-center gap-2 card-border border border-outline-variant/50">
          <span className="w-2 h-2 rounded-full bg-reentry-red animate-pulse" /> LIVE
        </div>
        <div className="px-2 py-0.5 bg-surface/60 text-on-surface text-[10px] font-mono card-border border border-outline-variant/50">
          {bitrate.toFixed(1)} Mbps {signalQuality}%
        </div>
      </div>

      <div className="absolute top-4 right-4 text-[10px] font-mono text-outline bg-surface/60 px-2 py-0.5 card-border border border-outline-variant/50 rounded">
        {rtspUrl}
      </div>

      <button className="absolute bottom-6 px-6 py-2 bg-primary text-on-primary font-label-caps rounded-sm hover:opacity-80 transition-opacity">
        RECONNECT
      </button>
    </div>
  );
}
