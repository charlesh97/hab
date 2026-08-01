import { useRef, useEffect, useState, type MouseEvent as ReactMouseEvent } from 'react';
import { Pause, Trash2, Play } from 'lucide-react';
import { DashboardLogEntry, LogEntry } from '../types';

interface PacketStreamProps {
  entries: LogEntry[];
  logEntries: DashboardLogEntry[];
  packetRate?: number;
  packetSeq?: number;
  uptime?: string;
  systemHealth?: 'NOMINAL' | 'DEGRADED' | 'OFFLINE';
  onHeightChange?: (newHeight: number) => void;
}

const DEFAULT_HEIGHT = 200;
const MIN_HEIGHT = 80;
const MAX_VIEWPORT_RATIO = 0.6;
const LOG_LEVELS = ['INFO', 'WARN', 'ERROR', 'DEBUG'] as const;

type FooterTab = 'packet' | 'log';

interface PausedSnapshot {
  packet: LogEntry[];
  log: DashboardLogEntry[];
}

function getInitialHeight(): number {
  try {
    const saved = window.localStorage.getItem('packetStreamHeight');
    const parsed = saved ? Number.parseInt(saved, 10) : Number.NaN;

    if (Number.isFinite(parsed)) {
      return Math.max(MIN_HEIGHT, Math.min(parsed, window.innerHeight * MAX_VIEWPORT_RATIO));
    }
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }

  return DEFAULT_HEIGHT;
}

const typeColors: Record<string, string> = {
  POS: 'bg-primary/20 text-primary',
  MOT: 'bg-secondary/20 text-secondary',
  ENV: 'bg-tertiary/20 text-tertiary',
  PWR: 'bg-secondary/20 text-secondary',
  SYS: 'bg-reentry-red/20 text-reentry-red',
};

const logLevelColors: Record<string, string> = {
  INFO: 'text-on-surface',
  WARN: 'text-tertiary',
  ERROR: 'text-reentry-red',
  DEBUG: 'text-outline',
};

function healthColor(status: string): string {
  switch (status) {
    case 'NOMINAL': return 'text-secondary';
    case 'DEGRADED': return 'text-tertiary';
    default: return 'text-reentry-red';
  }
}

function healthDot(status: string): string {
  switch (status) {
    case 'NOMINAL': return 'bg-secondary';
    case 'DEGRADED': return 'bg-tertiary';
    default: return 'bg-reentry-red';
  }
}

export function PacketStream({
  entries,
  logEntries,
  packetRate = 2.4,
  packetSeq = 18430,
  uptime = '00:00:00',
  systemHealth = 'NOMINAL',
  onHeightChange,
}: PacketStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const dragCleanupRef = useRef<(() => void) | null>(null);
  const [activeFooterTab, setActiveFooterTab] = useState<FooterTab>('packet');
  const [logLevelFilter, setLogLevelFilter] = useState<Set<string>>(
    () => new Set(LOG_LEVELS),
  );
  const [logSearch, setLogSearch] = useState('');
  const [pausedSnapshot, setPausedSnapshot] = useState<PausedSnapshot | null>(null);
  const [packetClearedThrough, setPacketClearedThrough] = useState<LogEntry | null>(null);
  const [logClearedThrough, setLogClearedThrough] = useState<DashboardLogEntry | null>(null);
  const [height, setHeight] = useState(getInitialHeight);
  const autoScrollRef = useRef(true);
  const paused = pausedSnapshot !== null;

  const packetSource = pausedSnapshot?.packet ?? entries;
  const logSource = pausedSnapshot?.log ?? logEntries;
  const packetClearIndex = packetClearedThrough
    ? packetSource.lastIndexOf(packetClearedThrough)
    : -1;
  const logClearIndex = logClearedThrough
    ? logSource.lastIndexOf(logClearedThrough)
    : -1;
  const visiblePacketEntries = packetSource.slice(packetClearIndex + 1);
  const visibleLogEntries = logSource
    .slice(logClearIndex + 1)
    .filter((entry) => {
      if (!logLevelFilter.has(entry.level.toUpperCase())) return false;
      if (logSearch && !entry.message.toLowerCase().includes(logSearch.toLowerCase())) return false;
      return true;
    });

  useEffect(() => {
    onHeightChange?.(height);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => dragCleanupRef.current?.(), []);

  useEffect(() => {
    if (!paused && autoScrollRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activeFooterTab, visiblePacketEntries.length, visibleLogEntries.length, paused]);

  useEffect(() => {
    autoScrollRef.current = true;
  }, [activeFooterTab]);

  const handleScroll = () => {
    if (!scrollRef.current || paused) return;
    const el = scrollRef.current;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    autoScrollRef.current = isAtBottom;
  };

  const handlePauseToggle = () => {
    if (pausedSnapshot) {
      setPausedSnapshot(null);
      autoScrollRef.current = true;
      return;
    }
    setPausedSnapshot({ packet: entries, log: logEntries });
  };

  const handleClear = () => {
    if (activeFooterTab === 'packet') {
      setPacketClearedThrough(packetSource[packetSource.length - 1] ?? null);
    } else {
      setLogClearedThrough(logSource[logSource.length - 1] ?? null);
    }
  };

  const toggleLogLevel = (level: string) => {
    setLogLevelFilter((current) => {
      const next = new Set(current);
      if (next.has(level)) {
        next.delete(level);
      } else {
        next.add(level);
      }
      return next;
    });
  };

  const toggleAllLogLevels = () => {
    setLogLevelFilter((current) => (
      LOG_LEVELS.every((level) => current.has(level))
        ? new Set<string>()
        : new Set<string>(LOG_LEVELS)
    ));
  };

  const handleDragStart = (e: ReactMouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragCleanupRef.current?.();

    const startY = e.clientY;
    const startHeight = height;
    let finalHeight = startHeight;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;

    function onMove(me: MouseEvent) {
      const maxHeight = window.innerHeight * MAX_VIEWPORT_RATIO;
      finalHeight = Math.round(
        Math.max(MIN_HEIGHT, Math.min(startHeight - (me.clientY - startY), maxHeight)),
      );
      setHeight(finalHeight);
      onHeightChange?.(finalHeight);
    }

    function cleanup() {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      dragCleanupRef.current = null;
    }

    function onUp() {
      try {
        window.localStorage.setItem('packetStreamHeight', String(finalHeight));
      } catch {
        // Resizing should still work when storage is unavailable.
      }
      cleanup();
    }

    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    dragCleanupRef.current = cleanup;
  };

  return (
    <footer
      className="fixed bottom-0 right-0 left-[64px] max-sm:left-0 bg-surface-container-lowest border-t border-outline-variant flex flex-col z-50"
      style={{ height }}
    >
      <div
        className="absolute -top-[3px] left-0 right-0 h-[6px] cursor-ns-resize hover:bg-telemetry-blue/30 z-[60] group"
        onMouseDown={handleDragStart}
        role="separator"
        aria-label="Resize packet stream"
        aria-orientation="horizontal"
        aria-valuenow={height}
        aria-valuemin={MIN_HEIGHT}
        aria-valuemax={Math.round(window.innerHeight * MAX_VIEWPORT_RATIO)}
      >
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-1 rounded-full bg-outline-variant opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>

      {/* Header bar */}
      <div className="h-10 border-b border-outline-variant px-4 flex justify-between items-center bg-surface-container-low shrink-0">
        <div className="flex items-stretch self-stretch" role="tablist" aria-label="Footer views">
          <button
            type="button"
            role="tab"
            aria-selected={activeFooterTab === 'packet'}
            onClick={() => setActiveFooterTab('packet')}
            className={`px-3 text-[10px] font-label-caps border-b-2 transition-colors ${
              activeFooterTab === 'packet'
                ? 'text-on-surface border-telemetry-blue'
                : 'text-outline border-transparent hover:text-on-surface'
            }`}
          >
            PACKET STREAM
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeFooterTab === 'log'}
            onClick={() => setActiveFooterTab('log')}
            className={`px-3 text-[10px] font-label-caps border-b-2 transition-colors ${
              activeFooterTab === 'log'
                ? 'text-on-surface border-telemetry-blue'
                : 'text-outline border-transparent hover:text-on-surface'
            }`}
          >
            LOGGING
          </button>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-[10px] font-mono text-outline">
            RX: {packetRate.toFixed(1)} PKT/S | SEQ: {packetSeq}
          </span>
          <button
            type="button"
            onClick={handlePauseToggle}
            className="text-outline hover:text-on-surface transition-colors flex items-center gap-1"
            title={paused ? 'Resume streaming' : 'Pause streaming'}
          >
            {paused ? <Play size={16} /> : <Pause size={16} />}
            <span className="text-[10px] font-label-caps">{paused ? 'RESUME' : 'PAUSE'}</span>
          </button>
          <button
            type="button"
            onClick={handleClear}
            className="text-outline hover:text-on-surface transition-colors flex items-center gap-1"
            title={activeFooterTab === 'packet' ? 'Clear packet stream' : 'Clear logging stream'}
          >
            <Trash2 size={16} />
            <span className="text-[10px] font-label-caps">CLEAR</span>
          </button>
        </div>
      </div>

      {activeFooterTab === 'packet' ? (
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          role="tabpanel"
          className="flex-1 min-h-0 overflow-y-auto font-mono text-[12px] p-2 leading-relaxed"
        >
          {visiblePacketEntries.length === 0 ? (
            <div className="flex items-center justify-center h-full text-[11px] text-outline-variant">
              Waiting for telemetry packets...
            </div>
          ) : (
            visiblePacketEntries.map((entry, i) => (
              <div
                key={`${entry.timestamp}-${i}`}
                className={`flex gap-3 px-2 py-0.5 rounded ${i % 2 === 0 ? 'bg-surface-container-high/20' : ''}`}
              >
                <span className="text-outline shrink-0">{entry.timestamp}</span>
                <span className={`px-1 rounded text-[10px] font-bold shrink-0 ${typeColors[entry.type] || 'bg-surface-container text-outline'}`}>
                  {entry.type}
                </span>
                <span className="text-on-surface-variant truncate">{entry.payload}</span>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col" role="tabpanel">
          <div className="h-8 px-4 border-b border-outline-variant flex items-center gap-1 shrink-0">
            <span className="text-[9px] font-label-caps text-outline mr-2">LEVEL</span>
            <button
              type="button"
              aria-pressed={LOG_LEVELS.every((level) => logLevelFilter.has(level))}
              onClick={toggleAllLogLevels}
              className={`px-2 py-0.5 rounded text-[9px] font-mono transition-colors ${
                LOG_LEVELS.every((level) => logLevelFilter.has(level))
                  ? 'bg-telemetry-blue/20 text-telemetry-blue'
                  : 'text-outline hover:text-on-surface'
              }`}
            >
              ALL
            </button>
            {LOG_LEVELS.filter((level) => level !== 'DEBUG').map((level) => (
              <button
                key={level}
                type="button"
                aria-pressed={logLevelFilter.has(level)}
                onClick={() => toggleLogLevel(level)}
                className={`px-2 py-0.5 rounded text-[9px] font-mono transition-colors ${
                  logLevelFilter.has(level)
                    ? 'bg-surface-container-high text-on-surface'
                    : 'text-outline-variant hover:text-outline'
                }`}
              >
                {level}
              </button>
            ))}
            <div className="flex-1" />
            <span className="text-[9px] font-label-caps text-outline mr-1">SEARCH</span>
            <input
              type="text"
              value={logSearch}
              onChange={(e) => setLogSearch(e.target.value)}
              placeholder="keyword..."
              className="w-36 bg-surface-container-lowest border border-outline-variant rounded px-2 py-0.5 text-[10px] font-mono text-on-surface placeholder:text-outline-variant focus:border-telemetry-blue outline-none"
            />
            {logSearch && (
              <button
                type="button"
                onClick={() => setLogSearch('')}
                className="text-outline-variant hover:text-on-surface transition-colors text-[14px] leading-none px-1"
                title="Clear search"
              >
                ×
              </button>
            )}
          </div>
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className="flex-1 min-h-0 overflow-y-auto font-mono text-[12px] p-2 leading-relaxed"
          >
            {visibleLogEntries.length === 0 ? (
              <div className="flex items-center justify-center h-full text-[11px] text-outline-variant">
                Waiting for server logs...
              </div>
            ) : (
              visibleLogEntries.map((entry, i) => {
                const level = entry.level.toUpperCase();
                return (
                  <div
                    key={`${entry.timestamp}-${i}`}
                    className={`flex gap-2 px-2 py-0.5 rounded ${i % 2 === 0 ? 'bg-surface-container-high/20' : ''}`}
                  >
                    <span className="text-outline shrink-0">{entry.timestamp}</span>
                    <span className={`font-bold shrink-0 ${logLevelColors[level] || 'text-outline'}`}>
                      [{level}]
                    </span>
                    <span className={`whitespace-pre-wrap break-words ${logLevelColors[level] || 'text-outline'}`}>
                      {entry.message}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Footer status bar */}
      <div className="h-6 bg-surface-container-lowest px-4 border-t border-outline-variant flex justify-between items-center text-[10px] text-outline font-mono shrink-0">
        <span>FLIGHT OPERATIONS SYSTEM v4.2</span>
        <span className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${healthDot(systemHealth)}`} />
          <span className={healthColor(systemHealth)}>SYSTEM HEALTH: {systemHealth}</span>
        </span>
        <span>UPTIME: {uptime}</span>
      </div>
    </footer>
  );
}
