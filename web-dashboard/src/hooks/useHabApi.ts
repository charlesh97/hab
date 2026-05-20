/**
 * WebSocket hook for live HAB telemetry from the Python backend.
 * Replaces the simulated useFlightSimulation hook with real WebSocket data.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  TelemetrySample, FlightPhase, Packet, LinkStatus,
  PositionData, MotionData, EnvironmentData, PowerData,
  LogEntry, TelemetryMessage,
} from '../types';

export interface ConnectionLogEntry {
  timestamp: number;
  message: string;
  type: 'info' | 'error' | 'warning';
}

interface SpectrumFrame {
  f: number[];
  p: number[];
  fc: number;
  span: number;
  ts?: number;
}

interface EngineStatus {
  running: boolean;
  tx_active: boolean;
  device_connected: boolean;
  device_serial?: string;
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

function _derivePhase(altitude: number, verticalSpeed: number): FlightPhase {
  if (altitude < 100 && Math.abs(verticalSpeed) < 1) return 'RECOVERED';
  if (verticalSpeed < -1 && altitude > 100) return 'DESCENT';
  if (Math.abs(verticalSpeed) < 1 && altitude > 1000) return 'FLOAT';
  if (verticalSpeed > 0 && altitude > 100) return 'ASCENT';
  return 'PRE-LAUNCH';
}

const MAX_LOG_ENTRIES = 500;

export function useHabApi() {
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(true);
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
  const [newLinkStatus, setNewLinkStatus] = useState<LinkStatus>({
    telemetry: 'NOMINAL', packet: 'NOMINAL', video: 'NOMINAL',
  });
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
  const [spectrum, setSpectrum] = useState<SpectrumFrame | null>(null);
  const [connectionLog, setConnectionLog] = useState<ConnectionLogEntry[]>([]);
  const [position, setPosition] = useState<PositionData>({
    lat: 39.3187, lon: -120.3289, alt_m: 18342.7, agl_m: 17210.3,
    fix: true, fix_type: '3d', sats: 14, hdop: 0.82, vdop: 1.34,
  });
  const [motion, setMotion] = useState<MotionData>({
    gs_mps: 13.8, vs_mps: 5.4, heading_deg: 72.6, cog_deg: 74.1,
    accel: { x: 0.03, y: -0.08, z: 9.71 },
    gyro_dps: { r: 0.4, p: -0.2, y: 1.1 },
    att_deg: { roll: 2.8, pitch: -4.1, yaw: 71.9 },
  });
  const [environment, setEnvironment] = useState<EnvironmentData>({
    temp_ext_c: -42.6, temp_int_c: 12.4, pressure_hpa: 72.8,
    humidity_pct: 4.2, baro_alt_m: 18190.5,
  });
  const [power, setPower] = useState<PowerData>({
    bat_v: 7.62, bat_a: 0.84, bat_w: 6.4, bat_pct: 68,
    bat_temp_c: 8.1, rails_v: { v5: 5.03, v3v3: 3.31, v1v8: 1.79 },
  });
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [packetRate, _setPacketRate] = useState(2.4);
  const [packetRateHistory, _setPacketRateHistory] = useState<number[]>([]);
  void packetRateHistory;
  const [lastPacketAge, _setLastPacketAge] = useState(1.2);
  const [packetSeq, setPacketSeq] = useState(18430);

  const addLogEntry = useCallback((timestamp: string, type: LogEntry['type'], payload: string) => {
    setLogEntries((prev) => {
      const next = [...prev, { timestamp, type, payload }];
      return next.length > 500 ? next.slice(next.length - 500) : next;
    });
  }, []);

  const wsRef = useRef<WebSocket | null>(null);
  const currentRef = useRef(current);
  const prevEngineStatusRef = useRef<EngineStatus | null>(null);
  const addLogEntryRef = useRef<(message: string, type: ConnectionLogEntry['type']) => void>(() => {});

  // Keep addLogEntryRef pointing to a stable setter so WebSocket callbacks don't cause re-renders
  addLogEntryRef.current = useCallback((message: string, type: ConnectionLogEntry['type']) => {
    setConnectionLog((prev) => {
      const entry: ConnectionLogEntry = { timestamp: Date.now(), message, type };
      const next = [...prev, entry];
      return next.length > MAX_LOG_ENTRIES ? next.slice(next.length - MAX_LOG_ENTRIES) : next;
    });
  }, []);

  // Keep currentRef in sync
  useEffect(() => {
    currentRef.current = current;
  });

  // Derive flight phase from current telemetry
  useEffect(() => {
    setPhase(_derivePhase(current.altitude, current.verticalSpeed));
  }, [current.altitude, current.verticalSpeed]);

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let isDisposed = false;

    function connect() {
      if (isDisposed) return;
      setConnecting(true);
      try {
        const ws = new WebSocket(WS_URL);

        ws.onopen = () => {
          setConnected(true);
          setConnecting(false);
          addLogEntryRef.current('WebSocket connected', 'info');
        };

        ws.onmessage = (event) => {
          try {
            const msg: WsMessage = JSON.parse(event.data);

            if (msg.type === 'status') {
              setEngineStatus(msg.data);
              setMissionTime((prev) => prev + 1);
            } else if (msg.type === 'spectrum') { 
              setSpectrum(msg.data);
            } else if (msg.type === 'telemetry') {
              const data: TelemetryMessage = msg.data;
              setPacketSeq(data.seq);

              const time = data.t.split('T')[1]?.substring(0, 8) || new Date().toISOString().substring(11, 19);

              if (data.type === 'position') {
                setPosition(data);
                addLogEntry(time, 'POS', `lat:${data.lat.toFixed(5)} lon:${data.lon.toFixed(5)} alt:${data.alt_m.toFixed(0)}m sats:${data.sats} fix:${data.fix_type}`);
              } else if (data.type === 'motion') {
                setMotion(data);
                addLogEntry(time, 'MOT', `gs:${data.gs_mps.toFixed(1)} vs:${data.vs_mps.toFixed(1)} hdg:${data.heading_deg.toFixed(1)}`);
              } else if (data.type === 'environment') {
                setEnvironment(data);
                addLogEntry(time, 'ENV', `ext:${data.temp_ext_c.toFixed(1)}°C int:${data.temp_int_c.toFixed(1)}°C pres:${data.pressure_hpa.toFixed(1)}hPa hum:${data.humidity_pct.toFixed(1)}%`);
              } else if (data.type === 'power') {
                setPower(data);
                addLogEntry(time, 'PWR', `v:${data.bat_v.toFixed(2)}V a:${data.bat_a.toFixed(2)}A w:${data.bat_w.toFixed(1)}W ${data.bat_pct.toFixed(0)}%`);
              }

              const now = Date.now();
              setPackets((prev) => {
                const next = [...prev, { id: `PKT-${data.seq}`, timestamp: now, type: 'TELEMETRY', payload: JSON.stringify(data) }];
                return next.length > 200 ? next.slice(next.length - 200) : next;
              });
            }
          } catch (e) {
            // Don't log parse errors to the connection log — they're debug-only
          }
        };

        ws.onclose = (event) => {
          setConnected(false);
          setConnecting(false);
          const reason = event.reason || `code ${event.code}`;
          addLogEntryRef.current(`WebSocket disconnected: ${reason}`, 'error');
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

  // Track engineStatus changes for connection log events
  useEffect(() => {
    if (!engineStatus) {
      prevEngineStatusRef.current = null;
      return;
    }

    const prev = prevEngineStatusRef.current;
    const add = addLogEntryRef.current;

    // Device connect/disconnect
    if (prev && !prev.device_connected && engineStatus.device_connected) {
      const serial = engineStatus.device_serial || 'unknown';
      add(`HackRF connected: ${serial}`, 'info');
    } else if (prev && prev.device_connected && !engineStatus.device_connected) {
      add('Device disconnected', 'error');
    }

    // Serial change (new device or serial populated)
    if (engineStatus.device_serial && prev?.device_serial !== engineStatus.device_serial) {
      add(`HackRF connected: ${engineStatus.device_serial}`, 'info');
    }

    // TX start/stop
    if (prev && !prev.tx_active && engineStatus.tx_active) {
      add('TX started', 'info');
    } else if (prev && prev.tx_active && !engineStatus.tx_active) {
      add('TX stopped', 'info');
    }

    // Pipeline start/stop
    if (engineStatus.pipeline && prev?.pipeline) {
      if (!prev.pipeline.running && engineStatus.pipeline.running) {
        add('Pipeline started', 'info');
      } else if (prev.pipeline.running && !engineStatus.pipeline.running) {
        add('Pipeline stopped', 'info');
      }
    }

    prevEngineStatusRef.current = engineStatus;
  }, [engineStatus]);

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

  const clearLog = useCallback(() => {
    setConnectionLog([]);
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
              ts: data.timestamp || data.ts || undefined,
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
                ts: data.timestamp || data.ts || undefined,
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

  // Compute packetsReceiving from actual packet recency
  const packetsReceiving = useMemo(() => {
    if (packets.length === 0) return false;
    return (Date.now() - packets[packets.length - 1].timestamp) < 5000;
  }, [packets]);

  // Fetch telemetry periodically + update link status
  useEffect(() => {
    if (!connected) {
      setNewLinkStatus((prev) => ({ ...prev, telemetry: 'OFFLINE', packet: 'OFFLINE' }));
      return;
    }
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/telemetry/latest`);
        const data = await res.json();
        if (data && data.altitude !== undefined) {
          setCurrent(data);
          setHistory((prev) => {
            const next = [...prev, data];
            return next.length > 300 ? next.slice(next.length - 300) : next;
          });
          // Create a packet from telemetry sample
          const pk: Packet = {
            id: `TLM-${Date.now()}`,
            timestamp: Date.now(),
            type: 'TELEMETRY',
            payload: `A:${data.altitude.toFixed(0)}m V:${data.verticalSpeed.toFixed(1)}m/s T:${data.externalTemp.toFixed(1)}°C GPS:${data.gpsSats}`,
          };
          setPackets((prev) => {
            const next = [...prev, pk];
            return next.length > 200 ? next.slice(-200) : next;
          });
          setNewLinkStatus((prev) => ({
            ...prev,
            telemetry: packetsReceiving ? 'NOMINAL' : 'DEGRADED',
            packet: data.gpsSats > 0 ? 'NOMINAL' : 'OFFLINE',
          }));
        }
      } catch {}
    }, 1000); // 1Hz telemetry
    return () => clearInterval(interval);
  }, [connected, packetsReceiving]);

  // Update video link status based on engine pipeline
  useEffect(() => {
    setNewLinkStatus((prev) => ({
      ...prev,
      video: engineStatus?.pipeline?.running ? 'NOMINAL' : 'OFFLINE',
    }));
  }, [engineStatus?.pipeline?.running]);

  // Pipeline debug output — fetch from server at 2 Hz
  const [ffmpegOutput, setFfmpegOutput] = useState<string[]>([]);
  const [tspOutput, setTspOutput] = useState<string[]>([]);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/pipeline/logs`);
        const data = await res.json();
        if (data.ffmpeg) setFfmpegOutput(data.ffmpeg);
        if (data.tsp) setTspOutput(data.tsp);
      } catch {}
    }, 500);
    return () => clearInterval(interval);
  }, []);

  const clearFfmpegOutput = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/pipeline/logs/clear`, { method: 'POST' });
      setFfmpegOutput([]);
    } catch {}
  }, []);

  const clearTspOutput = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/pipeline/logs/clear`, { method: 'POST' });
      setTspOutput([]);
    } catch {}
  }, []);

  return {
    connected,
    connecting,
    phase,
    missionTime,
    current,
    history,
    packets,
    packetsReceiving,
    newLinkStatus,
    engineStatus,
    spectrum,
    sendCommand,
    connectionLog,
    clearLog,
    ffmpegOutput,
    tspOutput,
    clearFfmpegOutput,
    clearTspOutput,
    position,
    motion,
    environment,
    power,
    logEntries,
    packetRate,
    lastPacketAge,
    packetSeq,
  };
}
