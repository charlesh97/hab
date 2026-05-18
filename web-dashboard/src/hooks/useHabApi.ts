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
  const currentRef = useRef(current);
  const lastPacketTimeRef = useRef(Date.now());
  const [packetsReceiving, setPacketsReceiving] = useState(false);

  // Keep currentRef in sync
  useEffect(() => {
    currentRef.current = current;
  });

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
                altitude: 20000 + Math.sin(Date.now() / 5000) * 10000,
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
              lastPacketTimeRef.current = Date.now();
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

  // Spectrum via SSE with HTTP polling fallback
  useEffect(() => {
    let eventSource: EventSource | null = null;
    let pollingInterval: ReturnType<typeof setInterval> | null = null;
    let isDisposed = false;

    function startPolling() {
      pollingInterval = setInterval(async () => {
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
      }, 200);
    }

    function startSSE() {
      if (isDisposed) return;
      try {
        const es = new EventSource(`${API_BASE}/spectrum/live`);

        es.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data && data.power_db) {
              setSpectrum({
                f: data.frequencies || [],
                p: data.power_db || [],
                fc: data.center_freq || 915e6,
                span: data.span_hz || 2e6,
              });
            }
          } catch (e) {
            console.warn('[HAB] SSE parse error:', e);
          }
        };

        es.onerror = () => {
          es.close();
          eventSource = null;
          // Fallback to HTTP polling on SSE failure
          if (!isDisposed) {
            startPolling();
          }
        };

        eventSource = es;
      } catch (e) {
        if (!isDisposed) startPolling();
      }
    }

    startSSE();

    return () => {
      isDisposed = true;
      if (eventSource) eventSource.close();
      if (pollingInterval) clearInterval(pollingInterval);
    };
  }, []);

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

  // Simulated packet generation (1-3 second intervals)
  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout>;
    const types = ['TELEMETRY', 'TELEMETRY', 'TELEMETRY', 'TELEMETRY',
                   'TELEMETRY', 'TELEMETRY', 'TELEMETRY', 'TELEMETRY',
                   'EVENT', 'WARNING'] as const;

    function generatePacket() {
      const c = currentRef.current;
      const type = types[Math.floor(Math.random() * types.length)];
      const sats = c.gpsSats;

      let payload: string;
      if (type === 'TELEMETRY') {
        payload = `[TLM] A:${c.altitude.toFixed(0)}m V:${c.verticalSpeed.toFixed(1)}m/s T:${c.externalTemp.toFixed(1)}°C P:${c.pressure.toFixed(1)}hPa GPS:${sats}`;
      } else if (type === 'EVENT') {
        const events = ['STATUS_UPDATE_NOMINAL', 'GPS_FIX_ACQUIRED',
                        'BEACON_TRANSMITTED', 'PAYLOAD_HEALTHY'];
        payload = `[EVT] ${events[Math.floor(Math.random() * events.length)]} SATS:${sats}`;
      } else {
        const warnings = ['BATTERY_LOW', 'TEMP_HIGH', 'PRESSURE_DROP'];
        const battVal = c.battery.toFixed(1);
        payload = `[WRN] ${warnings[Math.floor(Math.random() * warnings.length)]} ${battVal}%`;
      }

      const id = Array.from({length: 8}, () =>
        Math.floor(Math.random() * 16).toString(16)
      ).join('');

      const pkt: Packet = {
        id,
        timestamp: Date.now(),
        type,
        payload,
      };

      lastPacketTimeRef.current = Date.now();
      setPackets((prev) => {
        const next = [...prev, pkt];
        return next.length > 200 ? next.slice(next.length - 200) : next;
      });

      const delay = 1000 + Math.random() * 2000;
      timeout = setTimeout(generatePacket, delay);
    }

    const initialDelay = 1000 + Math.random() * 2000;
    timeout = setTimeout(generatePacket, initialDelay);

    return () => clearTimeout(timeout);
  }, []);

  // Detect active packet reception
  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = Date.now() - lastPacketTimeRef.current;
      setPacketsReceiving(elapsed < 2500);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  return {
    connected,
    phase,
    missionTime,
    current,
    history,
    packets,
    packetsReceiving,
    linkStatus,
    engineStatus,
    spectrum,
    sendCommand,
  };
}
