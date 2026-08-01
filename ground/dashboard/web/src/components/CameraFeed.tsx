import { Video, WifiOff } from 'lucide-react';

interface CameraFeedProps {
  bitrate?: number;
  signalQuality?: number;
  rtspUrl?: string;
  isConnected?: boolean;
  locked?: boolean;
  sdrStatus?: any;
}

export function CameraFeed({
  bitrate = 2.4,
  signalQuality = 98,
  rtspUrl = 'rtsp://192.168.1.100/stream1',
  isConnected = false,
  locked = false,
  sdrStatus,
}: CameraFeedProps) {
  const hackrf = sdrStatus?.hackrf;
  const dvbs2 = sdrStatus?.dvbs2;
  const videoUrl = `http://${window.location.hostname}:8001/video`;
  return (
    <div className="card-border bg-surface-container-lowest rounded-[20px] border border-outline-variant flex-1 h-full relative flex flex-col items-center justify-center overflow-hidden group">
      {/* Scanning line animation when no signal */}
      {!isConnected && (
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-primary/5 to-transparent animate-scan" />
          <div className="absolute inset-0 bg-reentry-red/[0.02]" />
        </div>
      )}

      {/* MJPEG stream — shown when pipeline is running */}
      {isConnected && (
        <img
          src={videoUrl}
          alt="Live camera feed"
          className="absolute inset-0 w-full h-full object-cover z-0"
        />
      )}

      {/* Camera empty state */}
      <div className="flex flex-col items-center gap-4 z-10">
        <div className={`transition-all duration-500 ${isConnected ? 'opacity-0 scale-0' : 'opacity-100 scale-100'}`}>
          <Video size={64} className="text-outline-variant" />
          <span className="font-label-caps text-lg tracking-widest text-outline block text-center mt-3">
            NO VIDEO SIGNAL
          </span>
          <span className="text-[10px] text-outline-variant font-mono text-center block mt-1">
            Camera not connected
          </span>
        </div>
      </div>

      {/* SDR Telemetry strip — bottom bar */}
      <div className={`absolute bottom-0 left-0 right-0 z-10 flex items-center justify-between px-4 py-1.5 text-[10px] font-mono border-t transition-colors ${locked ? 'border-secondary/30 bg-secondary/[0.06]' : 'border-outline-variant/30 bg-surface/60'}`}>
        <div className="flex items-center gap-3">
          <span className={`flex items-center gap-1.5 ${locked ? 'text-secondary' : 'text-outline'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${locked ? 'bg-secondary' : 'bg-outline'}`} />
            {locked ? 'LOCKED' : 'UNLOCKED'}
          </span>
          {typeof dvbs2?.snr_db === 'number' && (
            <span className="text-on-surface">{dvbs2.snr_db.toFixed(1)} dB</span>
          )}
        </div>
        <div className="flex items-center gap-3 text-outline">
          {hackrf?.freq_hz != null && <span>{(hackrf.freq_hz / 1e6).toFixed(1)} MHz</span>}
          {hackrf?.sample_rate != null && <span>{(hackrf.sample_rate / 1e6).toFixed(1)} Msps</span>}
        </div>
        <div className="flex items-center gap-2 text-outline">
          {hackrf?.lna != null && <span>LNA {hackrf.lna}</span>}
          {hackrf?.vga != null && <span>VGA {hackrf.vga}</span>}
          {hackrf?.amp && <span className="text-telemetry-blue">AMP</span>}
        </div>
      </div>

      {/* Status badges */}
      <div className="absolute top-4 left-4 flex gap-2 z-10">
        <div className={`px-2 py-0.5 text-[10px] font-bold flex items-center gap-2 card-border border rounded ${
          isConnected
            ? locked
              ? 'bg-secondary/20 text-secondary border-secondary/30 animate-pulse'
              : 'bg-amber-500/20 text-amber-400 border-amber-500/30'
            : 'bg-surface/60 text-outline border-outline-variant/50'
        }`}>
          <span className={`w-2 h-2 rounded-full ${isConnected ? locked ? 'bg-secondary' : 'bg-amber-400' : 'bg-outline'}`} />
          {isConnected ? locked ? 'LOCKED' : 'UNLOCKED' : 'OFFLINE'}
        </div>
        {isConnected && (
          <div className="px-2 py-0.5 bg-surface/60 text-on-surface text-[10px] font-mono card-border border border-outline-variant/50">
            {bitrate.toFixed(1)} Mbps {signalQuality}%
          </div>
        )}
      </div>

      {/* WifiOff icon — top-right, symmetrical to OFFLINE badge */}
      {!isConnected && (
        <div className="absolute top-4 right-4 z-10">
          <WifiOff size={20} className="text-reentry-red" />
        </div>
      )}

      {/* RTSP URL */}
      {isConnected && (
        <div className="absolute top-4 right-4 text-[10px] font-mono text-outline bg-surface/60 px-2 py-0.5 card-border border border-outline-variant/50 rounded z-10 truncate max-w-[160px]">
          {rtspUrl}
        </div>
      )}
    </div>
  );
}
