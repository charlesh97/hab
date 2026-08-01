import { useCallback, useEffect, useState } from 'react';
import { MemoryStick, Play, Square } from 'lucide-react';

interface SdrDevice {
  serial: string;
  label: string;
  driver: string;
}

interface SettingsDeviceProps {
  connected: boolean;
  sdrStatus: any;
  engineStatus: any;
  selectedSerial: string;
  onSerialChange: (serial: string) => void;
  sendCommand: (command: string, data?: any) => void;
}

export function SettingsDevice({
  connected,
  sdrStatus,
  engineStatus,
  selectedSerial,
  onSerialChange,
  sendCommand,
}: SettingsDeviceProps) {
  const [devices, setDevices] = useState<SdrDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadDevices = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/devices');
      if (!response.ok) throw new Error(`Device scan failed (${response.status})`);
      const data = await response.json();
      if (!Array.isArray(data)) throw new Error('Invalid device response');
      setDevices(data as SdrDevice[]);
    } catch (err) {
      setDevices([]);
      setError(err instanceof Error ? err.message : 'Device scan failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDevices();
  }, [loadDevices]);

  const jsonActive = engineStatus?.json_active === true;
  const jsonReady = engineStatus?.json_ready === true;
  const pipelineRunning = jsonActive || engineStatus?.pipeline?.running === true;
  const hackrf = pipelineRunning ? sdrStatus?.hackrf : null;

  return (
    <div className="space-y-6">
      <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6">
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-label-caps text-sm text-primary uppercase">Device Discovery</h3>
          <button onClick={() => void loadDevices()} className="text-xs font-label-caps text-telemetry-blue hover:underline">RESCAN</button>
        </div>
        <div className="space-y-4">
          {loading && <p className="font-mono text-xs text-outline">Scanning for SDR devices...</p>}
          {!loading && error && <p className="font-mono text-xs text-reentry-red">{error}</p>}
          {!loading && !error && devices.length === 0 && (
            <p className="font-mono text-xs text-outline">No SDR devices found.</p>
          )}
          {devices.map((device) => (
            <div key={device.serial} className="flex items-center justify-between p-4 bg-surface rounded-xl border border-outline-variant/30">
              <div className="flex items-center gap-4 min-w-0">
                <div className="w-10 h-10 shrink-0 rounded-lg bg-surface-container-highest flex items-center justify-center text-tracking-green">
                  <MemoryStick size={20} />
                </div>
                <div className="min-w-0">
                  <p className="font-mono text-sm text-on-surface truncate">{device.label}</p>
                  <p className="text-[10px] font-label-caps text-outline truncate">{device.driver} · Serial: {device.serial}</p>
                </div>
              </div>
              <button
                onClick={() => { onSerialChange(device.serial); sendCommand('sdr_configure', { serial: device.serial }); }}
                className={`ml-4 px-4 py-2 rounded-lg font-label-caps text-[10px] hover:opacity-90 ${
                  selectedSerial === device.serial
                    ? 'border border-tracking-green text-tracking-green'
                    : 'bg-telemetry-blue text-white'
                }`}
              >
                {selectedSerial === device.serial ? 'SELECTED' : 'CONNECT'}
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="font-label-caps text-sm text-primary uppercase">Pipeline</h3>
            <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-[10px]">
              <span className={pipelineRunning ? 'text-tracking-green' : 'text-outline'}>
                {pipelineRunning ? 'RUNNING' : 'STOPPED'}
              </span>
              <span className={jsonReady ? 'text-tracking-green' : 'text-outline'}>
                JSON {jsonReady ? 'READY' : 'WAITING'}
              </span>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => sendCommand('sdr_start')}
              disabled={!connected || pipelineRunning}
              className="px-6 py-2 bg-tracking-green text-white rounded font-label-caps flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Play size={16} /> START PIPELINE
            </button>
            <button
              onClick={() => sendCommand('sdr_stop')}
              disabled={!connected || !pipelineRunning}
              className="px-6 py-2 bg-reentry-red/20 text-reentry-red border border-reentry-red/50 rounded font-label-caps flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Square size={16} /> STOP PIPELINE
            </button>
          </div>
        </div>

        {!connected && (
          <p className="mt-4 font-mono text-xs text-reentry-red">
            Receiver server disconnected. Pipeline controls are unavailable.
          </p>
        )}
      </div>

      <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6 flex flex-col">
        <h3 className="font-label-caps text-sm text-primary uppercase mb-6">Connected Device</h3>
        {hackrf ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 flex-1">
            <StatusValue label="SERIAL" value={hackrf.serial ?? 'unknown'} />
            <StatusValue label="CENTER FREQUENCY" value={formatRate(hackrf.freq_hz, 'MHz')} />
            <StatusValue label="SAMPLE RATE" value={formatRate(hackrf.sample_rate, 'Msps')} />
            <StatusValue label="LNA GAIN" value={formatGain(hackrf.lna)} />
            <StatusValue label="VGA GAIN" value={formatGain(hackrf.vga)} />
            <StatusValue label="AMP" value={hackrf.amp ? 'ENABLED' : 'DISABLED'} />
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center rounded border border-outline-variant/30 bg-surface p-6">
            <p className="font-mono text-xs text-outline">
              {pipelineRunning ? 'Waiting for live SDR status...' : 'No active pipeline'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function formatRate(value: unknown, unit: string) {
  return typeof value === 'number' ? `${(value / 1e6).toFixed(3)} ${unit}` : '--';
}

function formatGain(value: unknown) {
  return typeof value === 'number' ? `${value} dB` : '--';
}

function StatusValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-3 bg-surface rounded border border-outline-variant/30">
      <p className="text-[10px] font-label-caps text-outline mb-1">{label}</p>
      <p className="font-mono text-sm text-on-surface break-all">{value}</p>
    </div>
  );
}
