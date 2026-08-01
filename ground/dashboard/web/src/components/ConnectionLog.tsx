import { useRef, useEffect, useState } from 'react';
import { Terminal, Trash2 } from 'lucide-react';

interface ConnectionLogEntry {
  timestamp: number;
  message: string;
  type: 'info' | 'error' | 'warning';
}

interface ConnectionLogProps {
  log: ConnectionLogEntry[];
  onClear: () => void;
}

export type { ConnectionLogEntry };

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function typeColor(type: ConnectionLogEntry['type']): string {
  switch (type) {
    case 'info':
      return 'text-emerald-400';
    case 'error':
      return 'text-rose-400';
    case 'warning':
      return 'text-yellow-400';
  }
}

function typeDotColor(type: ConnectionLogEntry['type']): string {
  switch (type) {
    case 'info':
      return 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]';
    case 'error':
      return 'bg-rose-400 shadow-[0_0_6px_rgba(244,63,94,0.5)]';
    case 'warning':
      return 'bg-yellow-400 shadow-[0_0_6px_rgba(250,204,21,0.5)]';
  }
}

export function ConnectionLog({ log, onClear }: ConnectionLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevLengthRef = useRef(log.length);
  const [filter, setFilter] = useState<'all' | 'info' | 'error'>('all');

  // Auto-scroll to latest entry
  useEffect(() => {
    if (scrollRef.current && log.length > prevLengthRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
    prevLengthRef.current = log.length;
  }, [log.length]);

  const filteredLog = filter === 'all'
    ? log
    : filter === 'error'
      ? log.filter(e => e.type === 'error' || e.type === 'warning')
      : log.filter(e => e.type === 'info');

  return (
    <div className="p-4 bg-[rgba(18,20,22,0.82)] border border-white/10 rounded-2xl shadow-lg flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 pb-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-sky-400" />
          <h3 className="text-xs font-bold text-white/50 tracking-wider uppercase">Connection Log</h3>
          <span className="text-[10px] text-white/20 font-mono ml-1">({log.length})</span>
        </div>
        <button
          onClick={onClear}
          disabled={log.length === 0}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold text-white/40 hover:text-white/70 hover:bg-white/5 transition-colors disabled:opacity-20 disabled:cursor-not-allowed"
        >
          <Trash2 className="w-3 h-3" />
          Clear
        </button>
      </div>

      {/* Filter toggles */}
      <div className="flex items-center gap-1 mb-2">
        {(['all', 'info', 'error'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-2 py-0.5 text-[10px] font-mono rounded transition-colors ${
              filter === f
                ? f === 'all'
                  ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30'
                  : f === 'info'
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                    : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                : 'bg-transparent text-slate-500 border border-transparent hover:text-slate-300'
            }`}
          >
            {f === 'all' ? 'All' : f === 'info' ? 'Info' : 'Errors'}
          </button>
        ))}
      </div>

      {/* Log Entries */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto min-h-[120px] max-h-[320px] space-y-0.5 scrollbar-thin"
      >
        {filteredLog.length === 0 ? (
          <div className="flex items-center justify-center h-full text-white/20 text-xs font-mono italic">
            No connection events yet...
          </div>
        ) : (
          filteredLog.map((entry, i) => (
            <div
              key={`${entry.timestamp}-${i}`}
              className="flex items-start gap-2 px-2 py-1 rounded hover:bg-white/[0.02] transition-colors"
            >
              <span
                className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${typeDotColor(entry.type)}`}
              />
              <span className="text-[10px] font-mono text-white/30 flex-shrink-0 tabular-nums w-16">
                {formatTime(entry.timestamp)}
              </span>
              <span className={`text-xs font-mono leading-relaxed break-all ${typeColor(entry.type)}`}>
                {entry.message}
              </span>
            </div>
          ))
        )}
      </div>

      {/* Footer entry count */}
      {log.length > 0 && (
        <div className="pt-2 mt-2 border-t border-white/5 text-[9px] text-white/20 font-mono text-right">
          {filteredLog.length} / {log.length} event{log.length !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  );
}
