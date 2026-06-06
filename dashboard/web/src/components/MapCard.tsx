import { useEffect, useRef, useState, useMemo } from 'react';
import { MapContainer, TileLayer, Polyline, CircleMarker, Popup } from 'react-leaflet';
import type { LatLngTuple } from 'leaflet';
import L from 'leaflet';

interface PositionPoint {
  seq: number;
  lat: number;
  lon: number;
  alt_m: number;
}

interface MapCardProps {
  lat: number;
  lon: number;
  alt_m: number;
  loadPositions: (since: number) => Promise<PositionPoint[]>;
}

const DARK_TILE_URL = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
const DARK_TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>';

const TRAIL_COLOR = { color: '#abc7ff', weight: 2, opacity: 0.8 };

function formatLatLng(lat: number, lon: number): string {
  const latDir = lat >= 0 ? 'N' : 'S';
  const lonDir = lon >= 0 ? 'E' : 'W';
  return `${Math.abs(lat).toFixed(4)}°${latDir} ${Math.abs(lon).toFixed(4)}°${lonDir}`;
}

export function MapCard({ lat, lon, alt_m, loadPositions }: MapCardProps) {
  const [trail, setTrail] = useState<LatLngTuple[]>([]);
  const [lastLoadedSeq, setLastLoadedSeq] = useState(0);
  const mapRef = useRef<L.Map | null>(null);
  const prevPositionRef = useRef<LatLngTuple | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadPositions(0).then((positions) => {
      if (cancelled) return;
      if (positions.length > 0) {
        const points: LatLngTuple[] = positions.map((p) => [p.lat, p.lon]);
        setTrail(points);
        setLastLoadedSeq(positions[positions.length - 1].seq);
      }
    });
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const pos: LatLngTuple = [lat, lon];
    if (
      prevPositionRef.current &&
      prevPositionRef.current[0] === pos[0] &&
      prevPositionRef.current[1] === pos[1]
    ) {
      return;
    }
    prevPositionRef.current = pos;
    setTrail((prev) => [...prev, pos]);
  }, [lat, lon]);

  useEffect(() => {
    const interval = setInterval(() => {
      loadPositions(lastLoadedSeq).then((positions) => {
        if (positions.length > 0) {
          setTrail((prev) => {
            const newPoints: LatLngTuple[] = positions.map((p) => [p.lat, p.lon]);
            return [...prev, ...newPoints];
          });
          setLastLoadedSeq(positions[positions.length - 1].seq);
        }
      });
    }, 10000);
    return () => clearInterval(interval);
  }, [lastLoadedSeq, loadPositions]);

  useEffect(() => {
    if (mapRef.current) {
      mapRef.current.panTo([lat, lon], { animate: true, duration: 1 });
    }
  }, [lat, lon]);

  const center: LatLngTuple = useMemo(() => {
    if (trail.length > 0) return trail[trail.length - 1];
    return [lat || 39.0, lon || -98.0] as LatLngTuple;
  }, [trail, lat, lon]);

  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant flex flex-col h-[35%] min-h-[200px]">
      <div className="p-3 border-b border-outline-variant flex justify-between items-center">
        <span className="data-label text-label-caps text-outline">LIVE MAP</span>
        <span className="text-[10px] font-mono text-outline">
          {trail.length > 0 ? `${trail.length} pts` : 'NO DATA'}
        </span>
      </div>
      <div className="flex-1 relative overflow-hidden">
        <MapContainer
          center={center}
          zoom={5}
          className="h-full w-full"
          zoomControl={false}
          ref={mapRef}
          style={{ background: '#1a1a2e' }}
        >
          <TileLayer url={DARK_TILE_URL} attribution={DARK_TILE_ATTR} />
          {trail.length >= 2 && (
            <Polyline positions={trail} pathOptions={TRAIL_COLOR} />
          )}
          <CircleMarker
            center={[lat, lon]}
            radius={5}
            pathOptions={{ color: '#abc7ff', fillColor: '#abc7ff', fillOpacity: 0.8, weight: 2 }}
          >
            <Popup>
              <div className="text-xs font-mono">
                <div>{formatLatLng(lat, lon)}</div>
                <div>Altitude: {alt_m.toFixed(0)} m</div>
              </div>
            </Popup>
          </CircleMarker>
        </MapContainer>
        <div className="absolute bottom-2 left-2 right-2 bg-surface/80 p-2 text-[10px] font-mono card-border border border-outline-variant/50 rounded z-[1000] pointer-events-none">
          {formatLatLng(lat, lon)} | Alt: {alt_m.toFixed(0)}m
        </div>
      </div>
    </div>
  );
}
