interface AlertsCardProps {
  lastPacketAge: number;
  linkMargin: number;
}

function lastPacketColor(age: number): string {
  if (age < 5) return 'text-secondary';
  if (age < 15) return 'text-tertiary';
  return 'text-reentry-red';
}

export function AlertsCard({ lastPacketAge, linkMargin }: AlertsCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant p-3 flex-1">
      <span className="data-label block mb-3 text-label-caps text-outline">SYSTEM ALERTS</span>
      <div className="flex flex-col gap-2">
        <div className="text-outline text-xs italic">No active alerts...</div>
        <div className="mt-4 pt-4 border-t border-outline-variant space-y-2">
          <div className="flex justify-between text-[11px] font-mono">
            <span className="text-outline">Last packet:</span>
            <span className={lastPacketColor(lastPacketAge)}>{lastPacketAge.toFixed(1)}s ago</span>
          </div>
          <div className="flex justify-between text-[11px] font-mono">
            <span className="text-outline">Link margin:</span>
            <span className={linkMargin > 10 ? 'text-secondary' : linkMargin > 5 ? 'text-tertiary' : 'text-reentry-red'}>
              {linkMargin} dB
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
