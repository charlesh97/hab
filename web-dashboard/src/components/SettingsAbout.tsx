export function SettingsAbout() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6 md:col-span-2">
        <h3 className="font-label-caps text-sm text-primary uppercase mb-6">System Status</h3>
        <div className="space-y-4 font-mono text-sm">
          <div className="flex justify-between py-2 border-b border-outline-variant/20"><span className="text-outline">SYSTEM UPTIME</span><span className="text-on-surface">72h 14m 05s</span></div>
          <div className="flex justify-between py-2 border-b border-outline-variant/20"><span className="text-outline">WEBSOCKET STATUS</span><span className="text-tracking-green">CONNECTED</span></div>
          <div className="flex justify-between py-2 border-b border-outline-variant/20"><span className="text-outline">CORE LOAD</span><span className="text-on-surface">12.4%</span></div>
          <div className="flex justify-between py-2 border-b border-outline-variant/20"><span className="text-outline">DISK USAGE (CAPTURE)</span><span className="text-on-surface">244 GB / 1024 GB</span></div>
        </div>
      </div>
      <div className="bg-surface-container-low card-border rounded-[20px] border border-outline-variant p-6 flex flex-col justify-between">
        <div>
          <h3 className="font-label-caps text-sm text-primary uppercase mb-6">Software Build</h3>
          <div className="space-y-2">
            <p className="text-xl font-bold font-mission-name text-on-surface">STRATOS v0.5-dev</p>
            <p className="text-[10px] font-mono text-outline">HASH: 7a8c3d1f_main_stable</p>
            <p className="text-[10px] font-mono text-outline">BUILD: 2026-05-19</p>
          </div>
        </div>
        <button className="mt-8 py-3 border border-outline rounded font-label-caps text-xs hover:bg-surface-container-highest text-outline">CHECK FOR UPDATES</button>
      </div>
    </div>
  );
}
