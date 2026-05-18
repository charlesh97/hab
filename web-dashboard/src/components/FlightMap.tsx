import React, { useEffect } from 'react';
import {
  MapContainer,
  TileLayer,
  Polyline,
  Marker,
  useMap } from
'react-leaflet';
import L from 'leaflet';
import { TelemetrySample } from '../types';
import { NavigationIcon } from 'lucide-react';
// Fix Leaflet default icon issue by creating custom DivIcons
const balloonIcon = L.divIcon({
  className: 'bg-transparent',
  html: `<div class="w-4 h-4 bg-sky-500 rounded-full border-2 border-white shadow-md relative">
           <div class="absolute inset-0 bg-sky-500 rounded-full animate-ping opacity-75"></div>
         </div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8]
});
const launchIcon = L.divIcon({
  className: 'bg-transparent',
  html: `<div class="w-3 h-3 bg-slate-800 rounded-full border-2 border-white shadow-sm"></div>`,
  iconSize: [12, 12],
  iconAnchor: [6, 6]
});
interface FlightMapProps {
  current: TelemetrySample;
  history: TelemetrySample[];
}
// Component to auto-center map on balloon — only pans when lat/lng actually changes
function MapUpdater({ center }: {center: [number, number];}) {
  const map = useMap();
  useEffect(() => {
    map.panTo(center, {
      animate: true,
      duration: 1
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [center[0], center[1], map]);
  return null;
}
export function FlightMap({ current, history }: FlightMapProps) {
  const path: [number, number][] = history.map((h) => [h.lat, h.lng]);
  const currentPos: [number, number] = [current.lat, current.lng];
  const launchPos: [number, number] = [39.05, -105.5]; // Hardcoded launch site
  // Predicted trajectory (dummy data extending from current heading)
  const predictedPath: [number, number][] = [currentPos];
  for (let i = 1; i <= 10; i++) {
    predictedPath.push([
    currentPos[0] + Math.cos(current.heading * Math.PI / 180) * i * 0.05,
    currentPos[1] + Math.sin(current.heading * Math.PI / 180) * i * 0.05]
    );
  }
  return (
    <div className="relative h-full w-full bg-[rgba(18,20,22,0.6)] rounded-b-xl">
      <MapContainer
        center={currentPos}
        zoom={11}
        className="h-full w-full z-0"
        zoomControl={false}>
        
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>' />
        

        <MapUpdater center={currentPos} />

        {/* Launch Site */}
        <Marker position={launchPos} icon={launchIcon} />

        {/* Actual Path */}
        <Polyline positions={path} color="#0284c7" weight={3} opacity={0.8} />

        {/* Predicted Path */}
        <Polyline
          positions={predictedPath}
          color="#94a3b8"
          weight={2}
          dashArray="5, 10"
          opacity={0.6} />
        

        {/* Current Position */}
        <Marker position={currentPos} icon={balloonIcon} />
      </MapContainer>

      {/* Floating Telemetry Card — dark glassmorphism */}
      <div className="absolute top-4 left-4 z-[1000] bg-[rgba(18,20,22,0.85)] backdrop-blur-sm border border-white/10 rounded-lg shadow-lg p-3 w-64">
        <div className="flex items-center gap-2 mb-3 pb-2 border-b border-white/10">
          <NavigationIcon className="w-4 h-4 text-sky-400" />
          <span className="text-xs font-bold text-white/80 tracking-wider">
            POSITION DATA
          </span>
        </div>
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-[10px] font-bold text-white/40 uppercase">
              LAT
            </span>
            <span className="font-mono text-sm text-white/80">
              {current.lat.toFixed(6)}°
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[10px] font-bold text-white/40 uppercase">
              LON
            </span>
            <span className="font-mono text-sm text-white/80">
              {current.lng.toFixed(6)}°
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[10px] font-bold text-white/40 uppercase">
              ALT
            </span>
            <span className="font-mono text-sm text-sky-400 font-bold">
              {current.altitude.toFixed(0)} m
            </span>
          </div>
        </div>
      </div>
    </div>);

}