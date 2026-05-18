import React from 'react';
export function RfConfig() {
  return (
    <div className="p-4 h-full overflow-y-auto bg-slate-50">
      <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
        <h3 className="text-xs font-bold text-slate-800 tracking-wider mb-4 border-b border-slate-100 pb-2">
          APRS & TELEMETRY BEACON
        </h3>

        <div className="grid grid-cols-2 gap-4 mb-6">
          <FormGroup label="Callsign">
            <input type="text" defaultValue="W1AW-11" className="w-full bg-slate-50 border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500" />
          </FormGroup>
          <FormGroup label="Path">
            <input type="text" defaultValue="WIDE1-1,WIDE2-1" className="w-full bg-slate-50 border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500" />
          </FormGroup>
          <FormGroup label="Beacon Freq (MHz)">
            <input type="number" defaultValue="144.390" step="0.005" className="w-full bg-slate-50 border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 font-mono focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500" />
          </FormGroup>
          <FormGroup label="Interval (s)">
            <input type="number" defaultValue="60" className="w-full bg-slate-50 border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 font-mono focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500" />
          </FormGroup>
        </div>

        <h3 className="text-xs font-bold text-slate-800 tracking-wider mb-4 border-b border-slate-100 pb-2">DOWNLINK SETTINGS</h3>
        
        <div className="grid grid-cols-2 gap-4 mb-6">
          <FormGroup label="Downlink Freq (MHz)">
            <input type="number" defaultValue="433.050" step="0.005" className="w-full bg-slate-50 border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 font-mono focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500" />
          </FormGroup>
          <FormGroup label="Modulation">
            <select className="w-full bg-slate-50 border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500" defaultValue="LoRa">
              <option>AFSK</option>
              <option>FSK</option>
              <option>LoRa</option>
            </select>
          </FormGroup>
          <FormGroup label="TX Power (dBm)">
            <div className="flex items-center gap-3">
              <input
                type="range"
                min="10"
                max="30"
                defaultValue="22"
                className="flex-1 accent-sky-600" />
              
              <span className="font-mono text-xs text-slate-600 w-8">22</span>
            </div>
          </FormGroup>
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t border-slate-100">
          <button className="px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100 rounded-md transition-colors">
            Reset
          </button>
          <button className="px-4 py-2 text-sm font-semibold text-white bg-sky-600 hover:bg-sky-700 rounded-md shadow-sm transition-colors">
            Apply Config
          </button>
        </div>
      </div>
    </div>);

}
function FormGroup({
  label,
  children



}: {label: string;children: React.ReactNode;}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
        {label}
      </label>
      {children}
    </div>);

}