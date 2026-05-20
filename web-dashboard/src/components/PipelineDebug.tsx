interface PipelineDebugProps { ffmpegOutput: string[]; tspOutput: string[]; onClearFfmpeg: () => void; onClearTsp: () => void; }
export function PipelineDebug(_props: PipelineDebugProps) {
  return (
    <div className="bg-[rgba(18,20,22,0.82)] border border-white/10 rounded-2xl p-6 shadow-lg max-w-2xl">
      <h3 className="text-xs font-bold text-white/50 tracking-wider mb-4 border-b border-white/5 pb-3 uppercase">Debug Output</h3>
      <p className="text-white/40 text-xs">Pipeline debug — full implementation coming in Task 9.</p>
    </div>
  );
}
