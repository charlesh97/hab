import { useState } from 'react';

interface SettingsRfProps {
  sendCommand: (command: string, data?: any) => void;
  sdrStatus: any;
  selectedSerial: string;
}

const MODCODS = [
  'QPSK1/4',
  'QPSK1/3',
  'QPSK2/5',
  'QPSK1/2',
  'QPSK3/5',
  'QPSK2/3',
  'QPSK3/4',
  'QPSK4/5',
  'QPSK5/6',
  'QPSK8/9',
  '8PSK3/5',
  '8PSK2/3',
  '8PSK3/4',
  '8PSK5/6',
  '8PSK8/9',
];

function loadFromStorage<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(`sdr_config_${key}`);
    return raw !== null ? JSON.parse(raw) : fallback;
  } catch { return fallback; }
}

function saveToStorage(key: string, value: unknown) {
  try { localStorage.setItem(`sdr_config_${key}`, JSON.stringify(value)); } catch { /* noop */ }
}

const BITRATE_LOOKUP: Record<string, number> = {
  'QPSK1/4': 479, 'QPSK1/3': 641, 'QPSK2/5': 771, 'QPSK1/2': 965,
  'QPSK3/5': 1159, 'QPSK2/3': 1288, 'QPSK3/4': 1449, 'QPSK4/5': 1546,
  'QPSK5/6': 1611, 'QPSK8/9': 1718,
  '8PSK3/5': 1739, '8PSK2/3': 1933, '8PSK3/4': 2174, '8PSK5/6': 2319,
  '8PSK8/9': 2578,
};

export function SettingsRf({ sendCommand, sdrStatus, selectedSerial }: SettingsRfProps) {
  const [freqMHz, setFreqMHz] = useState(() => loadFromStorage('freqMHz', 915));
  const [sampleRateMsps, setSampleRateMsps] = useState(() => loadFromStorage('sampleRateMsps', 4));
  const [lna, setLna] = useState(() => loadFromStorage('lna', 24));
  const [vga, setVga] = useState(() => loadFromStorage('vga', 32));
  const [amp, setAmp] = useState(() => loadFromStorage('amp', true));
  const [rfApplied, setRfApplied] = useState(false);
  const [modcod, setModcod] = useState(() => loadFromStorage('modcod', 'QPSK1/2'));
  const [offsetMHz, setOffsetMHz] = useState(() => loadFromStorage('offsetMHz', 0));
  const [symRateMsps, setSymRateMsps] = useState(() => loadFromStorage('symRateMsps', 1));
  const [dvbs2Applied, setDvbs2Applied] = useState(false);
  const [saved, setSaved] = useState(false);
  const dvbs2 = sdrStatus?.dvbs2;

  const saveConfig = () => {
    saveToStorage('freqMHz', freqMHz);
    saveToStorage('sampleRateMsps', sampleRateMsps);
    saveToStorage('lna', lna);
    saveToStorage('vga', vga);
    saveToStorage('amp', amp);
    saveToStorage('modcod', modcod);
    saveToStorage('offsetMHz', offsetMHz);
    saveToStorage('symRateMsps', symRateMsps);
    applyRf();
    applyDvbs2();
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  };

  const applyRf = () => {
    sendCommand('sdr_configure', {
      freq_hz: freqMHz * 1e6,
      sample_rate: sampleRateMsps * 1e6,
      lna,
      vga,
      amp,
      serial: selectedSerial,
    });
    setRfApplied(true);
    window.setTimeout(() => setRfApplied(false), 2000);
  };

  const applyDvbs2 = () => {
    sendCommand('sdr_configure', {
      modcod,
      dvbs2_offset_hz: offsetMHz * 1e6,
      symbol_rate: Math.round(symRateMsps * 1e6),
      serial: selectedSerial,
    });
    setDvbs2Applied(true);
    window.setTimeout(() => setDvbs2Applied(false), 2000);
  };

  const txFrequencyHz = Math.round((freqMHz + offsetMHz) * 1e6);
  const tsBitrate = Math.round((BITRATE_LOOKUP[modcod] || 965) * symRateMsps);
  const txCommand = `python3 dev/dvbs2/dvbs2/tx.py --freq ${txFrequencyHz} --modcod ${modcod} --sym-rate ${Math.round(symRateMsps * 1e6)} --rolloff 0.2 --amp --hackrf-vga 47 --pilots`;

  return (
    <div className="space-y-6">
      <section className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-4 flex items-center justify-between">
        <span className="text-[10px] font-label-caps text-outline">RF CONFIG — save defaults + apply to server</span>
        <button
          onClick={saveConfig}
          className={`px-6 py-2 rounded text-[10px] font-label-caps transition-colors ${saved ? 'bg-tracking-green text-white' : 'border border-outline-variant text-outline hover:text-on-surface hover:border-on-surface-variant'}`}
        >
          {saved ? 'SAVED ✓' : 'SAVE CONFIG'}
        </button>
      </section>

      <section className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-8">
        <h3 className="font-label-caps text-sm text-primary uppercase mb-6">Core RF</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <div>
            <label className="block text-[10px] font-label-caps text-outline mb-2">FREQUENCY (MHz)</label>
            <input
              className="w-full bg-surface-container-lowest border border-outline-variant rounded p-3 font-mono text-on-surface focus:border-telemetry-blue outline-none"
              type="number"
              step="0.001"
              value={freqMHz}
              onChange={(event) => setFreqMHz(Number(event.target.value))}
            />
          </div>
          <div>
            <label className="block text-[10px] font-label-caps text-outline mb-2">SAMPLE RATE (Msps)</label>
            <input
              className="w-full bg-surface-container-lowest border border-outline-variant rounded p-3 font-mono text-on-surface focus:border-telemetry-blue outline-none"
              type="number"
              step="0.001"
              value={sampleRateMsps}
              onChange={(event) => setSampleRateMsps(Number(event.target.value))}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
          <div>
            <div className="flex justify-between mb-2">
              <label className="text-[10px] font-label-caps text-outline">LNA GAIN (0-40 dB)</label>
              <span className="font-mono text-telemetry-blue">{lna} dB</span>
            </div>
            <input
              className="w-full h-1 bg-surface-container-highest rounded-lg appearance-none cursor-pointer accent-telemetry-blue"
              type="range"
              min="0"
              max="40"
              step="8"
              value={lna}
              onChange={(event) => setLna(Number(event.target.value))}
            />
          </div>
          <div>
            <div className="flex justify-between mb-2">
              <label className="text-[10px] font-label-caps text-outline">VGA GAIN (0-62 dB)</label>
              <span className="font-mono text-telemetry-blue">{vga} dB</span>
            </div>
            <input
              className="w-full h-1 bg-surface-container-highest rounded-lg appearance-none cursor-pointer accent-telemetry-blue"
              type="range"
              min="0"
              max="62"
              step="2"
              value={vga}
              onChange={(event) => setVga(Number(event.target.value))}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-4 pt-6 border-t border-outline-variant/30">
          <div className="flex items-center gap-4">
            <span className="text-[10px] font-label-caps text-outline">AMP ENABLE</span>
            <div className="flex p-1 bg-surface-container-lowest rounded-lg border border-outline-variant">
              <button
                onClick={() => setAmp(false)}
                className={`px-4 py-1 text-[10px] font-label-caps rounded transition-colors ${!amp ? 'bg-surface-container-highest text-on-surface' : 'text-outline hover:text-on-surface'}`}
              >
                DISABLED
              </button>
              <button
                onClick={() => setAmp(true)}
                className={`px-4 py-1 text-[10px] font-label-caps rounded transition-colors ${amp ? 'bg-surface-container-highest text-on-surface' : 'text-outline hover:text-on-surface'}`}
              >
                ENABLED
              </button>
            </div>
          </div>
          <button
            onClick={applyRf}
            className={`px-6 py-2 rounded text-[10px] font-label-caps transition-colors ${rfApplied ? 'bg-tracking-green text-white' : 'bg-telemetry-blue text-white hover:bg-blue-600'}`}
          >
            {rfApplied ? 'APPLIED ✓' : 'APPLY RF'}
          </button>
        </div>
      </section>

      <section className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-8">
        <div className="pt-1 border-t border-outline-variant/30">
          <h3 className="font-label-caps text-sm text-primary uppercase mt-6 mb-6">DVB-S2</h3>

          <div className="rounded-xl border border-outline-variant/30 bg-surface p-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
              <div>
                <label className="block text-[10px] font-label-caps text-outline mb-2">MODCOD</label>
                <select
                  value={modcod}
                  onChange={(event) => setModcod(event.target.value)}
                  className="w-full bg-surface-container-lowest border border-outline-variant rounded p-3 font-mono text-xs text-on-surface"
                >
                  {MODCODS.map((value) => <option key={value}>{value}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-label-caps text-outline mb-2">DVB-S2 OFFSET (MHz)</label>
                <input
                  value={offsetMHz}
                  onChange={(event) => setOffsetMHz(Number(event.target.value))}
                  className="w-full bg-surface-container-lowest border border-outline-variant rounded p-3 font-mono text-xs text-on-surface focus:border-telemetry-blue outline-none"
                  type="number"
                  step="0.001"
                />
              </div>
              <div>
                <label className="block text-[10px] font-label-caps text-outline mb-2">SYMBOL RATE (Msps)</label>
                <input
                  value={symRateMsps}
                  onChange={(event) => setSymRateMsps(Number(event.target.value))}
                  className="w-full bg-surface-container-lowest border border-outline-variant rounded p-3 font-mono text-xs text-on-surface focus:border-telemetry-blue outline-none"
                  type="number"
                  step="0.001"
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-4 pt-5 border-t border-outline-variant/20">
              <div className="flex flex-wrap items-center gap-3">
                <span className={`rounded-full border px-3 py-1 font-label-caps text-[10px] ${dvbs2?.locked ? 'border-tracking-green/50 bg-tracking-green/10 text-tracking-green' : 'border-reentry-red/50 bg-reentry-red/10 text-reentry-red'}`}>
                  {dvbs2?.locked ? 'LOCKED' : 'UNLOCKED'}
                </span>
                <span className="font-mono text-xs text-on-surface">
                  SNR: {typeof dvbs2?.snr_db === 'number' ? `${dvbs2.snr_db.toFixed(2)} dB` : '--'}
                </span>
              </div>
              <button
                onClick={applyDvbs2}
                className={`px-6 py-2 rounded text-[10px] font-label-caps transition-colors ${dvbs2Applied ? 'bg-tracking-green text-white' : 'bg-telemetry-blue text-white hover:bg-blue-600'}`}
              >
                {dvbs2Applied ? 'APPLIED ✓' : 'APPLY DVB-S2'}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6">
        <h3 className="font-label-caps text-sm text-primary uppercase mb-4">Packet Telemetry</h3>
        <div className="rounded-xl border border-outline-variant/30 bg-surface p-4">
          <p className="font-mono text-sm text-on-surface">Packet Offset: +2.000 MHz | Symbol Rate: 0.100 Msps</p>
          <p className="mt-2 text-[10px] font-label-caps text-outline">Read-only — packet RX not yet integrated</p>
        </div>
      </section>

      <section className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6">
        <h3 className="font-label-caps text-sm text-primary uppercase mb-4">TX Command Reference</h3>
        <div className="rounded-xl border border-outline-variant/30 bg-surface p-4">
          <p className="text-[10px] font-label-caps text-outline mb-2">Matching TX command</p>
          <code className="block overflow-x-auto whitespace-nowrap font-mono text-xs text-tracking-green">
            {txCommand}
          </code>
          <p className="mt-2 text-[10px] font-mono text-outline">
            TS muxrate ≤ ~{tsBitrate} kbps ({modcod} + pilots)
          </p>
        </div>
      </section>
    </div>
  );
}
