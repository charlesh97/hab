export function SettingsRf() {
  return (
    <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">FREQUENCY (MHz)</label>
          <input className="w-full bg-surface-container-lowest border border-outline-variant rounded p-3 font-mono text-on-surface focus:border-telemetry-blue outline-none" type="text" defaultValue="915.000" />
        </div>
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">SYMBOL RATE (Msps)</label>
          <input className="w-full bg-surface-container-lowest border border-outline-variant rounded p-3 font-mono text-on-surface focus:border-telemetry-blue outline-none" type="text" defaultValue="1.000" />
        </div>
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">LO OFFSET (PPM)</label>
          <input className="w-full bg-surface-container-lowest border border-outline-variant rounded p-3 font-mono text-on-surface focus:border-telemetry-blue outline-none" type="number" defaultValue="0" />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-12 mb-8">
        <div>
          <div className="flex justify-between mb-2">
            <label className="text-[10px] font-label-caps text-outline">LNA GAIN (0-40 dB)</label>
            <span className="font-mono text-telemetry-blue">16 dB</span>
          </div>
          <input className="w-full h-1 bg-surface-container-highest rounded-lg appearance-none cursor-pointer accent-telemetry-blue" type="range" min="0" max="40" defaultValue="16" />
        </div>
        <div>
          <div className="flex justify-between mb-2">
            <label className="text-[10px] font-label-caps text-outline">VGA GAIN (0-62 dB)</label>
            <span className="font-mono text-telemetry-blue">24 dB</span>
          </div>
          <input className="w-full h-1 bg-surface-container-highest rounded-lg appearance-none cursor-pointer accent-telemetry-blue" type="range" min="0" max="62" defaultValue="24" />
        </div>
      </div>

      <div className="flex items-center justify-between pt-6 border-t border-outline-variant/30">
        <div className="flex items-center gap-4">
          <span className="text-[10px] font-label-caps text-outline">AMP ENABLE</span>
          <div className="flex p-1 bg-surface-container-lowest rounded-lg border border-outline-variant">
            <button className="px-4 py-1 text-[10px] font-label-caps rounded transition-colors bg-surface-container-highest text-on-surface">DISABLED</button>
            <button className="px-4 py-1 text-[10px] font-label-caps rounded transition-colors text-outline hover:text-on-surface">ENABLED</button>
          </div>
        </div>
        <div className="flex gap-3">
          <button className="px-6 py-2 border border-outline-variant rounded text-[10px] font-label-caps hover:bg-surface-container-highest text-outline">RESET</button>
          <button className="px-6 py-2 bg-telemetry-blue text-white rounded text-[10px] font-label-caps hover:bg-blue-600">APPLY PARAMETERS</button>
        </div>
      </div>
    </div>
  );
}
