import { MemoryStick } from 'lucide-react';

export function SettingsDevice() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6">
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-label-caps text-sm text-primary uppercase">Device Discovery</h3>
          <button className="text-xs font-label-caps text-telemetry-blue hover:underline">RESCAN</button>
        </div>
        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 bg-surface rounded-xl border border-outline-variant/30">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-surface-container-highest flex items-center justify-center text-tracking-green">
                <MemoryStick size={20} />
              </div>
              <div>
                <p className="font-mono text-sm text-on-surface">HackRF One</p>
                <p className="text-[10px] font-label-caps text-outline">Serial: ...60661</p>
              </div>
            </div>
            <button className="px-4 py-2 bg-telemetry-blue text-white rounded-lg font-label-caps text-[10px] hover:opacity-90">CONNECT</button>
          </div>
          <div className="flex items-center justify-between p-4 bg-surface rounded-xl border border-outline-variant/30 opacity-50">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-surface-container-highest flex items-center justify-center text-outline">
                <MemoryStick size={20} />
              </div>
              <div>
                <p className="font-mono text-sm text-on-surface">HackRF One</p>
                <p className="text-[10px] font-label-caps text-outline">Serial: ...67464</p>
              </div>
            </div>
            <button className="px-4 py-2 border border-outline rounded-lg font-label-caps text-[10px] cursor-not-allowed text-outline">BUSY</button>
          </div>
        </div>
      </div>

      <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6 flex flex-col">
        <h3 className="font-label-caps text-sm text-primary uppercase mb-6">Connected Device</h3>
        <div className="grid grid-cols-2 gap-4 flex-1">
          <div className="p-3 bg-surface rounded border border-outline-variant/30">
            <p className="text-[10px] font-label-caps text-outline mb-1">CENTER FREQUENCY</p>
            <p className="font-telemetry-lg text-2xl text-on-surface">915.000 <span className="text-xs text-outline">MHz</span></p>
          </div>
          <div className="p-3 bg-surface rounded border border-outline-variant/30">
            <p className="text-[10px] font-label-caps text-outline mb-1">SAMPLE RATE</p>
            <p className="font-telemetry-lg text-2xl text-on-surface">2.000 <span className="text-xs text-outline">Msps</span></p>
          </div>
          <div className="p-3 bg-surface rounded border border-outline-variant/30">
            <p className="text-[10px] font-label-caps text-outline mb-1">LNA GAIN</p>
            <p className="font-telemetry-lg text-2xl text-on-surface">16 <span className="text-xs text-outline">dB</span></p>
          </div>
          <div className="p-3 bg-surface rounded border border-outline-variant/30">
            <p className="text-[10px] font-label-caps text-outline mb-1">VGA GAIN</p>
            <p className="font-telemetry-lg text-2xl text-on-surface">24 <span className="text-xs text-outline">dB</span></p>
          </div>
        </div>
        <button className="mt-6 w-full py-3 bg-reentry-red/20 text-reentry-red border border-reentry-red/50 rounded-lg font-label-caps hover:bg-reentry-red hover:text-white transition-all">DISCONNECT DEVICE</button>
      </div>
    </div>
  );
}
