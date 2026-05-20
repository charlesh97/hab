interface TxControlsProps { sendCommand: (cmd: string, data?: any) => void; engineStatus: any; }
export function TxControls(_props: TxControlsProps) {
  return (
    <div className="bg-[rgba(18,20,22,0.82)] border border-white/10 rounded-2xl p-6 shadow-lg max-w-2xl">
      <h3 className="text-xs font-bold text-white/50 tracking-wider mb-4 border-b border-white/5 pb-3 uppercase">TX Controls</h3>
      <p className="text-white/40 text-xs">TX controls — full implementation coming in Task 9.</p>
    </div>
  );
}
