import React from 'react';
import { TelemetrySample } from '../types';
import { StatTile } from './Shared';
import {
  ArrowUpIcon,
  ArrowDownIcon,
  CompassIcon,
  ThermometerIcon,
  GaugeIcon,
  BatteryIcon,
  SatelliteIcon,
  WindIcon } from
'lucide-react';
interface TelemetryGridProps {
  current: TelemetrySample;
}
export function TelemetryGrid({ current }: TelemetryGridProps) {
  return (
    <div className="grid grid-cols-3 gap-3 p-4 bg-slate-50 border-b border-slate-200 shrink-0">
      <StatTile
        label="Altitude"
        value={current.altitude.toFixed(0)}
        unit="m"
        icon={<ArrowUpIcon className="w-4 h-4" />} />
      
      <StatTile
        label="Vert Speed"
        value={current.verticalSpeed.toFixed(1)}
        unit="m/s"
        icon={
        current.verticalSpeed >= 0 ?
        <ArrowUpIcon className="w-4 h-4 text-emerald-500" /> :

        <ArrowDownIcon className="w-4 h-4 text-amber-500" />

        } />
      
      <StatTile
        label="Gnd Speed"
        value={current.groundSpeed.toFixed(1)}
        unit="m/s"
        icon={<WindIcon className="w-4 h-4" />} />
      

      <StatTile
        label="Heading"
        value={current.heading.toFixed(0)}
        unit="°"
        icon={<CompassIcon className="w-4 h-4" />} />
      
      <StatTile
        label="Ext Temp"
        value={current.externalTemp.toFixed(1)}
        unit="°C"
        icon={<ThermometerIcon className="w-4 h-4" />} />
      
      <StatTile
        label="Int Temp"
        value={current.internalTemp.toFixed(1)}
        unit="°C"
        icon={<ThermometerIcon className="w-4 h-4" />} />
      

      <StatTile
        label="Pressure"
        value={current.pressure.toFixed(1)}
        unit="hPa"
        icon={<GaugeIcon className="w-4 h-4" />} />
      
      <StatTile
        label="Battery"
        value={current.battery.toFixed(1)}
        unit="%"
        icon={<BatteryIcon className="w-4 h-4" />} />
      
      <StatTile
        label="GPS Sats"
        value={current.gpsSats}
        unit=""
        icon={<SatelliteIcon className="w-4 h-4" />} />
      
    </div>);

}