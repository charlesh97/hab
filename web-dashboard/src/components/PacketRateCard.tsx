interface PacketRateCardProps {
  rate: number;
  sequence: number;
}

export function PacketRateCard({ rate, sequence }: PacketRateCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant p-3">
      <div className="flex justify-between items-start mb-2">
        <div>
          <span className="data-label block text-label-caps text-outline">PACKET RATE</span>
          <div className="font-mono text-2xl text-on-surface">
            {rate.toFixed(1)} <span className="text-xs opacity-50">pkt/s</span>
          </div>
        </div>
        <div className="text-right">
          <span className="data-label block text-label-caps text-outline">SEQUENCE</span>
          <div className="font-mono text-lg text-primary">#{sequence}</div>
        </div>
      </div>
      <div className="h-12 w-full mt-2">
        <svg className="w-full h-full" viewBox="0 0 300 40">
          <path
            d="M 0 30 L 20 25 L 40 35 L 60 15 L 80 20 L 100 10 L 120 28 L 140 12 L 160 30 L 180 15 L 200 22 L 220 5 L 240 18 L 260 32 L 280 25 L 300 20"
            fill="none"
            stroke="#abc7ff"
            strokeWidth="1.5"
          />
        </svg>
      </div>
    </div>
  );
}
