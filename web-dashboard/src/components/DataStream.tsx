import React, { useEffect, useState, useRef } from 'react';
import { Packet } from '../types';
import { PauseIcon, PlayIcon, Trash2Icon } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
interface DataStreamProps {
  packets: Packet[];
}
export function DataStream({ packets }: DataStreamProps) {
  const [isPaused, setIsPaused] = useState(false);
  const [displayPackets, setDisplayPackets] = useState<Packet[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!isPaused) {
      setDisplayPackets(packets);
    }
  }, [packets, isPaused]);
  useEffect(() => {
    if (!isPaused && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [displayPackets, isPaused]);
  return (
    <div className="h-full flex flex-col bg-[#1e293b]">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-800 border-b border-slate-700 shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-mono text-slate-300">
            RX RATE: 1.0 pkt/s
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsPaused(!isPaused)}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors"
            title={isPaused ? 'Resume' : 'Pause'}>
            
            {isPaused ?
            <PlayIcon className="w-4 h-4" /> :

            <PauseIcon className="w-4 h-4" />
            }
          </button>
          <button
            onClick={() => setDisplayPackets([])}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors"
            title="Clear Log">
            
            <Trash2Icon className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Log Area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed">
        
        <AnimatePresence initial={false}>
          {displayPackets.map((pkt) =>
          <motion.div
            key={`${pkt.id}-${pkt.timestamp}`}
            initial={{
              opacity: 0,
              x: -10
            }}
            animate={{
              opacity: 1,
              x: 0
            }}
            className="flex gap-3 mb-1 hover:bg-slate-800/50 px-1 rounded">
            
              <span className="text-slate-500 shrink-0">
                {new Date(pkt.timestamp).toISOString().substring(11, 23)}
              </span>
              <span
              className={`shrink-0 w-16 ${pkt.type === 'TELEMETRY' ? 'text-sky-400' : pkt.type === 'EVENT' ? 'text-emerald-400' : pkt.type === 'WARNING' ? 'text-amber-400' : 'text-rose-400'}`}>
              
                [{pkt.type.substring(0, 3)}]
              </span>
              <span className="text-slate-300 break-all">{pkt.payload}</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>);

}