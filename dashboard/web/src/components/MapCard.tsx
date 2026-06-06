interface MapCardProps {
  lat: number;
  lon: number;
  alt_m: number;
}

export function MapCard({ lat, lon, alt_m }: MapCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant flex flex-col h-full">
      <div className="p-3 border-b border-outline-variant flex justify-between items-center">
        <span className="data-label text-label-caps text-outline">LIVE MAP</span>
        <span className="text-[10px] font-mono text-outline">v2.4-STABLE</span>
      </div>
      <div className="flex-1 bg-surface-container-lowest relative overflow-hidden">
        <div className="absolute inset-0 opacity-20 pointer-events-none"
          style={{
            backgroundImage: 'linear-gradient(#30363d 1px, transparent 1px), linear-gradient(90deg, #30363d 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        />
        <svg className="w-full h-full p-4" viewBox="0 0 200 120">
          <path d="M 20 100 Q 100 0 180 80" fill="none" stroke="#2F80ED" strokeDasharray="4 2" strokeWidth="2" />
          <circle cx="20" cy="100" fill="#4daa78" r="3" />
          <circle className="animate-pulse" cx="120" cy="35" fill="#abc7ff" r="4" />
          <path d="M 175 75 L 185 85 M 185 75 L 175 85" stroke="#e05344" strokeWidth="2" />
        </svg>
        <div className="absolute bottom-2 left-2 right-2 bg-surface/80 p-2 text-[10px] font-mono card-border border border-outline-variant/50 rounded">
          {lat.toFixed(4)}°N {lon.toFixed(4)}°W | Alt: {alt_m.toFixed(0)}m
        </div>
      </div>
    </div>
  );
}
