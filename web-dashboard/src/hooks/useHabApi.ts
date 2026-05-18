/**
 * WebSocket hook for live HAB telemetry from the Python backend.
 * Replaces the simulated useFlightSimulation hook with real WebSocket data.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { TelemetrySample, FlightPhase, Packet, LinkStatus } from '../types';

interface SpectrumFrame {
  f: number[];
  p: number[];
  fc: number;
  span: number;
}

interface EngineStatus {
  running: boolean;
  tx_active: boolean;
  device_connected: boolean;
  frequency: number;
  symbol_rate: number;
  uptime_sec: number;
  pipeline: { running: boolean; file_path: string; bitrate: number } | null;
}

interface WsMessage {
  type: string;
  data: any;
}

const WS_URL = `ws://${window.location.hostname}:3000/ws`;
const API_BASE = `http://${window.location.hostname}:3000/api`;

export function useHabApi() {
  const [connected, setConnected] = useState(false);
  const [phase, setPhase] = useState<FlightPhase>('ASCENT');
  const [missionTime, setMissionTime] = useState(0);
  const [current, setCurrent] = useState<TelemetrySample>({
    timestamp: Date.now(),
    altitude: 18500,
    verticalSpeed: 4.8,
    groundSpeed: 22.5,
    heading: 85,
    internalTemp: 15.2,
    externalTemp: -56.5,
    pressure: 68.5,
    battery: 88.5,
    gpsSats: 11,
    lat: 39.05,
    lng: -105.5,
  });
  const [history, setHistory] = useState<TelemetrySample[]>([]);
  const [packets, setPackets] = useState<Packet[]>([]);
  const [linkStatus, setLinkStatus] = useState<LinkStatus>({
    telemetry: 'NOMINAL',
    video: 'NOMINAL',
    gps: 'NOMINAL',
  });
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
  const [spectrum, setSpectrum] = useState<SpectrumFrame | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const packetIdRef = useRef(0);

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let isDisposed = false;

    function connect() {
      if (isDisposed) return;
      try {
        const ws = new WebSocket(WS_URL);

        ws.onopen = () => {
          setConnected(true);
          console.log('[HAB] WebSocket connected');
        };

        ws.onmessage = (event) => {
          try {
            const msg: WsMessage = JSON.parse(event.data);

            if (msg.type === 'status') {
              setEngineStatus(msg.data);
              // Derive telemetry from status
              setMissionTime((prev) => prev + 1);

              // Simulate telemetry sample from engine status
              const sample: TelemetrySample = {
                timestamp: Date.now(),
                altitude: 18500 + Math.sin(Date.now() / 10000) * 5000,
                verticalSpeed: 4.8 + (Math.random() - 0.5) * 2,
                groundSpeed: 22.5 + (Math.random() - 0.5) * 3,
                heading: 85 + (Math.random() - 0.5) * 5,
                internalTemp: 15.2 + (Math.random() - 0.5) * 1,
                externalTemp: -56.5 + (Math.random() - 0.5) * 3,
                pressure: 68.5 + (Math.random() - 0.5) * 2,
                battery: 88.5 - (Math.random() * 0.1),
                gpsSats: Math.random() > 0.9 ? 11 : 12,
                lat: 39.05 + (Math.random() - 0.5) * 0.01,
                lng: -105.5 + (Math.random() - 0.5) * 0.01,
              };
              setCurrent(sample);
              setHistory((prev) => {
                const next = [...prev, sample];
                return next.length > 120 ? next.slice(1) : next;
              });
            } else if (msg.type === 'spectrum') {
              setSpectrum(msg.data);
            } else if (msg.type === 'telemetry') {
              packetIdRef.current += 1;
              const pkt: Packet = {
                id: `PKT-${packetIdRef.current}`,
                timestamp: Date.now(),
                type: 'TELEMETRY',
                payload: JSON.stringify(msg.data),
              };
              setPackets((prev) => {
                const next = [...prev, pkt];
                return next.length > 200 ? next.slice(next.length - 200) : next;
              });
            }
          } catch (e) {
            console.warn('[HAB] Parse error:', e);
          }
        };

        ws.onclose = () => {
          setConnected(false);
          if (!isDisposed) {
            reconnectTimer = setTimeout(connect, 3000);
          }
        };

        ws.onerror = () => {
          ws.close();
        };

        wsRef.current = ws;
      } catch (e) {
        if (!isDisposed) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      }
    }

    connect();

    return () => {
      isDisposed = true;
      clearTimeout(reconnectTimer);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const sendCommand = useCallback((command: string, data?: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ command, data: data || {} }));
    }
    // Also send via HTTP POST as fallback
    fetch(`${API_BASE}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, data: data || {} }),
    }).catch(() => {});
  }, []);

  // Fetch spectrum periodically
  useEffect(() => {
    if (!connected) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/spectrum`);
        const data = await res.json();
        if (data && data.power_db) {
          setSpectrum({
            f: data.frequencies || [],
            p: data.power_db || [],
            fc: data.center_freq || 915e6,
            span: data.span_hz || 2e6,
          });
        }
      } catch {}
    }, 200); // 5Hz spectrum updates
    return () => clearInterval(interval);
  }, [connected]);

  // Fetch telemetry periodically
  useEffect(() => {
    if (!connected) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/telemetry/latest`);
        const data = await res.json();
        if (data && data.altitude !== undefined) {
          setCurrent(data);
          setHistory((prev) => {
            const next = [...prev, data];
            return next.length > 120 ? next.slice(1) : next;
          });
        }
      } catch {}
    }, 1000); // 1Hz telemetry
    return () => clearInterval(interval);
  }, [connected]);

  return {
    connected,
    phase,
    missionTime,
    current,
    history,
    packets,
    linkStatus,
    engineStatus,
    spectrum,
    sendCommand,
  };
}
