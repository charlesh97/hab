import React, { useState, useEffect } from 'react';

interface RfConfigProps {
  sendCommand: (cmd: string, data?: any) => void;
  engineStatus?: any;
}

export function RfConfig({ sendCommand, engineStatus }: RfConfigProps) {
  const [freq, setFreq] = useState('915.000');
  const [vga, setVga] = useState('16');
  const [amp, setAmp] = useState(false);
  const [symbolRate, setSymbolRate] = useState('1.000');

  const applyConfig = () => {
    const freqHz = parseFloat(freq) * 1e6;
    sendCommand('set_frequency', { frequency: freqHz });
    sendCommand('set_gain', { vga: parseFloat(vga), amp });
  };

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="bg-[rgba(18,20,22,0.82)] border border-white/10 rounded-2xl p-6 shadow-lg max-w-2xl">
        <h3 className="text-xs font-bold text-white/50 tracking-wider mb-6 border-b border-white/5 pb-3 uppercase">
          RF Configuration
        </h3>

        <div className="grid grid-cols-2 gap-5 mb-6">
          <FormGroup label="Frequency (MHz)">
            <input
              type="text"
              value={freq}
              onChange={(e) => setFreq(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white font-mono focus:outline-none focus:border-sky-500"
            />
          </FormGroup>
          <FormGroup label="Symbol Rate (Msps)">
            <input
              type="text"
              value={symbolRate}
              onChange={(e) => setSymbolRate(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white font-mono focus:outline-none focus:border-sky-500"
            />
          </FormGroup>
          <FormGroup label="VGA Gain (dB)">
            <div className="flex items-center gap-3">
              <input
                type="range"
                min="0"
                max="47"
                value={vga}
                onChange={(e) => setVga(e.target.value)}
                className="flex-1 accent-orange-500"
              />
              <span className="text-sm font-mono text-white/60 w-8">{vga}</span>
            </div>
          </FormGroup>
          <FormGroup label="AMP (14dB)">
            <button
              onClick={() => setAmp(!amp)}
              className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
                amp
                  ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                  : 'bg-white/5 text-white/40 border border-white/10'
              }`}
            >
              {amp ? 'ENABLED' : 'DISABLED'}
            </button>
          </FormGroup>
        </div>

        <div className="flex gap-3 pt-4 border-t border-white/5">
          <button
            onClick={applyConfig}
            className="px-5 py-2.5 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold rounded-xl transition-colors"
          >
            Apply Config
          </button>
          <button className="px-5 py-2.5 bg-white/5 hover:bg-white/10 text-white/60 text-sm font-semibold rounded-xl transition-colors">
            Reset
          </button>
        </div>

        {engineStatus && (
          <div className="mt-6 pt-4 border-t border-white/5">
            <div className="text-[10px] font-bold text-white/30 tracking-wider mb-3 uppercase">Device Status</div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="text-white/50">Connected:</div>
              <div className={`font-mono ${engineStatus.device_connected ? 'text-emerald-400' : 'text-rose-400'}`}>
                {engineStatus.device_connected ? 'YES' : 'NO'}
              </div>
              <div className="text-white/50">TX Active:</div>
              <div className={`font-mono ${engineStatus.tx_active ? 'text-orange-400' : 'text-white/40'}`}>
                {engineStatus.tx_active ? 'TRANSMITTING' : 'INACTIVE'}
              </div>
              <div className="text-white/50">Frequency:</div>
              <div className="font-mono text-white/60">{(engineStatus.frequency / 1e6).toFixed(3)} MHz</div>
              <div className="text-white/50">Symbol Rate:</div>
              <div className="font-mono text-white/60">{(engineStatus.symbol_rate / 1e6).toFixed(2)} Msps</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FormGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-[10px] font-bold text-white/40 uppercase tracking-wider">{label}</label>
      {children}
    </div>
  );
}
