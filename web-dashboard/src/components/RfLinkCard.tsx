import { LinkStatus } from '../types';

interface RfLinkCardProps {
  linkStatus: LinkStatus;
  frequency?: number;
  snr?: number;
}

function statusColor(status: string): string {
  switch (status) {
    case 'NOMINAL': return 'bg-secondary-container text-on-secondary-container';
    case 'DEGRADED': return 'bg-tertiary-container/30 text-tertiary';
    default: return 'bg-reentry-red/20 text-reentry-red';
  }
}

export function RfLinkCard({ linkStatus, frequency = 915, snr = 12.3 }: RfLinkCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant p-3">
      <span className="data-label block mb-3 text-label-caps text-outline">RF LINK STATUS</span>
      <div className="flex gap-2 mb-4">
        <div className={`px-2 py-1 text-[10px] font-bold rounded-sm ${statusColor(linkStatus.telemetry)}`}>TLM</div>
        <div className={`px-2 py-1 text-[10px] font-bold rounded-sm ${statusColor(linkStatus.packet)}`}>PKT</div>
        <div className={`px-2 py-1 text-[10px] font-bold rounded-sm ${statusColor(linkStatus.video)}`}>VID</div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-[10px] text-outline font-label-caps">FREQ</div>
          <div className="font-mono text-xl text-on-surface">
            {frequency} <span className="text-xs opacity-50">MHz</span>
          </div>
        </div>
        <div>
          <div className="text-[10px] text-outline font-label-caps">SNR</div>
          <div className={`font-mono text-xl ${snr > 10 ? 'text-secondary' : snr > 5 ? 'text-tertiary' : 'text-reentry-red'}`}>
            {snr.toFixed(1)} <span className="text-xs">dB</span>
          </div>
        </div>
      </div>
    </div>
  );
}
