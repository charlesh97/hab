import { useRef, useEffect } from 'react';
import { Pause, Trash2 } from 'lucide-react';
import { LogEntry } from '../types';

interface PacketStreamProps {
  entries: LogEntry[];
}

const typeColors: Record<string, string> = {
  POS: 'bg-primary/20 text-primary',
  MOT: 'bg-secondary/20 text-secondary',
  ENV: 'bg-tertiary/20 text-tertiary',
  PWR: 'bg-secondary/20 text-secondary',
  SYS: 'bg-reentry-red/20 text-reentry-red',
};

export function PacketStream({ entries }: PacketStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries.length]);

  return (
    <footer className="fixed bottom-0 right-0 left-[64px] h-[200px] bg-surface-container-lowest border-t border-outline-variant flex flex-col z-50">
      <div className="h-10 border-b border-outline-variant px-4 flex justify-between items-center bg-surface-container-low">
        <div className="flex items-center gap-4">
          <span className="data-label text-label-caps text-outline">PACKET STREAM</span>
          <span className="text-[10px] font-mono text-outline">RX: 2.4 PKT/S | SEQ: 18430</span>
        </div>
        <div className="flex gap-4">
          <button className="text-outline hover:text-on-surface transition-colors flex items-center gap-1">
            <Pause size={16} />
            <span className="text-[10px] font-label-caps">PAUSE</span>
          </button>
          <button className="text-outline hover:text-on-surface transition-colors flex items-center gap-1">
            <Trash2 size={16} />
            <span className="text-[10px] font-label-caps">CLEAR</span>
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto font-mono text-[12px] p-2 leading-relaxed">
        {entries.map((entry, i) => (
          <div
            key={`${entry.timestamp}-${i}`}
            className={`flex gap-3 px-2 py-0.5 rounded ${i % 2 === 0 ? 'bg-surface-container-high/20' : ''}`}
          >
            <span className="text-outline">{entry.timestamp}</span>
            <span className={`px-1 rounded text-[10px] font-bold ${typeColors[entry.type] || 'bg-surface-container text-outline'}`}>
              {entry.type}
            </span>
            <span className="text-on-surface-variant">{entry.payload}</span>
          </div>
        ))}
      </div>

      <div className="h-6 bg-surface-container-lowest px-4 border-t border-outline-variant flex justify-between items-center text-[10px] text-outline font-mono">
        <span>FLIGHT OPERATIONS SYSTEM v4.2</span>
        <span>SYSTEM HEALTH: NOMINAL</span>
        <span>UPTIME: 03:14:22</span>
      </div>
    </footer>
  );
}
