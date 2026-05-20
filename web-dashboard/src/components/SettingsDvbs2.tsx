export function SettingsDvbs2() {
  return (
    <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-8">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-6 mb-8">
        <div><label className="block text-[10px] font-label-caps text-outline mb-2">MODCOD</label><select className="w-full bg-surface-container-lowest border border-outline-variant rounded p-2 font-mono text-xs text-on-surface"><option>QPSK 1/2</option><option>QPSK 3/4</option><option>8PSK 2/3</option></select></div>
        <div><label className="block text-[10px] font-label-caps text-outline mb-2">PILOTS</label><select className="w-full bg-surface-container-lowest border border-outline-variant rounded p-2 font-mono text-xs text-on-surface"><option>OFF</option><option>ON</option></select></div>
        <div><label className="block text-[10px] font-label-caps text-outline mb-2">ROLLOFF</label><select className="w-full bg-surface-container-lowest border border-outline-variant rounded p-2 font-mono text-xs text-on-surface"><option>0.35</option><option>0.25</option><option>0.20</option></select></div>
        <div><label className="block text-[10px] font-label-caps text-outline mb-2">FEC FRAME</label><select className="w-full bg-surface-container-lowest border border-outline-variant rounded p-2 font-mono text-xs text-on-surface"><option>NORMAL</option><option>SHORT</option></select></div>
        <div><label className="block text-[10px] font-label-caps text-outline mb-2">SPS</label><input className="w-full bg-surface-container-lowest border border-outline-variant rounded p-2 font-mono text-xs text-on-surface focus:border-telemetry-blue outline-none" type="number" defaultValue="2" /></div>
      </div>

      <div className="space-y-6">
        <div>
          <label className="block text-[10px] font-label-caps text-outline mb-2">DEVICE ARGUMENTS (ADVANCED)</label>
          <input className="w-full bg-surface-container-lowest border border-outline-variant rounded p-4 font-mono text-xs text-tracking-green focus:border-telemetry-blue outline-none" type="text" defaultValue="hackrf=0,bias=0,pack_stream=1,buffer_size=1048576" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="flex items-center justify-between p-4 bg-surface-container-lowest rounded border border-outline-variant/30">
            <span className="text-xs font-label-caps text-outline">RRC DELAY</span>
            <span className="font-mono text-xs text-on-surface">10 taps</span>
          </div>
          <div className="flex items-center justify-between p-4 bg-surface-container-lowest rounded border border-outline-variant/30">
            <span className="text-xs font-label-caps text-outline">SINK TYPE</span>
            <span className="font-mono text-xs text-on-surface">TCP SERVER :5000</span>
          </div>
        </div>
      </div>
    </div>
  );
}
