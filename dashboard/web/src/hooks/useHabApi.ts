/**
 * WebSocket hook for live HAB telemetry from the HAB Receiver Server.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  TelemetrySample, FlightPhase, Packet, LinkStatus,
  PositionData, MotionData, EnvironmentData, PowerData,
  LogEntry, TelemetryMessage, MetricPoint, ConnectionLogEntry,
} from '../types';
import { EngineStatus } from '../types';

interface WsMessage {
  type: string;
  data: any;
}

const WS_URL = `ws://${window.location.hostname}:8000/ws`;

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
  const [spectrum, setSpectrum] = useState<any>(null);
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
    bat_temp_c: 8.1,
  });
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [packetRate, _setPacketRate] = useState(2.4);
  const [packetRateHistory, _setPacketRateHistory] = useState<number[]>([]);
  void packetRateHistory;
  const [lastPacketAge, _setLastPacketAge] = useState(1.2);
  const [packetSeq, setPacketSeq] = useState(18430);

  const metricHistoryRef = useRef<{
    altitude: MetricPoint[];
    verticalSpeed: MetricPoint[];
    externalTemp: MetricPoint[];
    internalTemp: MetricPoint[];
    pressure: MetricPoint[];
    humidity: MetricPoint[];
    roll: MetricPoint[];
    pitch: MetricPoint[];
    yaw: MetricPoint[];
  }>({
    altitude: [],
    verticalSpeed: [],
    externalTemp: [],
    internalTemp: [],
    pressure: [],
    humidity: [],
    roll: [],
    pitch: [],
    yaw: [],
  });

  const [metricHistory, setMetricHistory] = useState<typeof metricHistoryRef.current>(metricHistoryRef.current);

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

  addLogEntryRef.current = useCallback((message: string, type: ConnectionLogEntry['type']) => {
    setConnectionLog((prev) => {
      const entry: ConnectionLogEntry = { timestamp: Date.now(), message, type };
      const next = [...prev, entry];
      return next.length > MAX_LOG_ENTRIES ? next.slice(next.length - MAX_LOG_ENTRIES) : next;
    });
  }, []);

  useEffect(() => {
    currentRef.current = current;
  });

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
                pushMetric('altitude', data.alt_m);
                addLogEntry(time, 'POS', `lat:${data.lat.toFixed(5)} lon:${data.lon.toFixed(5)} alt:${data.alt_m.toFixed(0)}m sats:${data.sats} fix:${data.fix_type}`);
              } else if (data.type === 'motion') {
                setMotion(data);
                pushMetric('verticalSpeed', data.vs_mps);
                pushMetric('roll', data.att_deg.roll);
                pushMetric('pitch', data.att_deg.pitch);
                pushMetric('yaw', data.att_deg.yaw);
                addLogEntry(time, 'MOT', `gs:${data.gs_mps.toFixed(1)} vs:${data.vs_mps.toFixed(1)} hdg:${data.heading_deg.toFixed(1)}`);
              } else if (data.type === 'environment') {
                setEnvironment(data);
                pushMetric('externalTemp', data.temp_ext_c);
                pushMetric('internalTemp', data.temp_int_c);
                pushMetric('pressure', data.pressure_hpa);
                pushMetric('humidity', data.humidity_pct);
                addLogEntry(time, 'ENV', `ext:${data.temp_ext_c.toFixed(1)}°C int:${data.temp_int_c.toFixed(1)}°C pres:${data.pressure_hpa.toFixed(1)}hPa hum:${data.humidity_pct.toFixed(1)}%`);
              } else if (data.type === 'power') {
                setPower(data);
                addLogEntry(time, 'PWR', `v:${data.bat_v.toFixed(2)}V a:${data.bat_a.toFixed(2)}A w:${data.bat_w.toFixed(1)}W ${data.bat_pct.toFixed(0)}%`);
              }

              // Update TelemetrySample from incoming telemetry
              if (data.type === 'position') {
                setCurrent((prev) => ({
                  ...prev,
                  timestamp: Date.now(),
                  lat: data.lat,
                  lng: data.lon,
                  altitude: data.alt_m,
                  gpsSats: data.sats,
                }));
                setHistory((prev) => {
                  const sample: TelemetrySample = {
                    timestamp: Date.now(),
                    altitude: data.alt_m,
                    verticalSpeed: 0,
                    groundSpeed: 0,
                    heading: 0,
                    internalTemp: 0,
                    externalTemp: 0,
                    pressure: 0,
                    battery: 0,
                    gpsSats: data.sats,
                    lat: data.lat,
                    lng: data.lon,
                  };
                  const next = [...prev, sample];
                  return next.length > 300 ? next.slice(next.length - 300) : next;
                });
              }
              if (data.type === 'environment') {
                setCurrent((prev) => ({
                  ...prev,
                  externalTemp: data.temp_ext_c,
                  internalTemp: data.temp_int_c,
                  pressure: data.pressure_hpa,
                }));
              }
              if (data.type === 'motion') {
                setCurrent((prev) => ({
                  ...prev,
                  verticalSpeed: data.vs_mps,
                  groundSpeed: data.gs_mps,
                  heading: data.heading_deg,
                }));
              }
              if (data.type === 'power') {
                setCurrent((prev) => ({ ...prev, battery: data.bat_pct }));
              }

              const now = Date.now();
              setPackets((prev) => {
                const next = [...prev, { id: `PKT-${data.seq}`, timestamp: now, type: 'TELEMETRY', payload: JSON.stringify(data) }];
                return next.length > 200 ? next.slice(next.length - 200) : next;
              });

              flushMetricHistory();
            }
          } catch (e) {
            // Parse errors are debug-only
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

    if (prev && !prev.device_connected && engineStatus.device_connected) {
      const serial = engineStatus.device_serial || 'unknown';
      add(`HackRF connected: ${serial}`, 'info');
    } else if (prev && prev.device_connected && !engineStatus.device_connected) {
      add('Device disconnected', 'error');
    }

    if (engineStatus.device_serial && prev?.device_serial !== engineStatus.device_serial) {
      add(`HackRF connected: ${engineStatus.device_serial}`, 'info');
    }

    if (prev && !prev.tx_active && engineStatus.tx_active) {
      add('TX started', 'info');
    } else if (prev && prev.tx_active && !engineStatus.tx_active) {
      add('TX stopped', 'info');
    }

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
    // Map command names to receiver-server message types
    const typeMap: Record<string, string> = {
      'start': 'cmd:start',
      'stop': 'cmd:stop',
      'configure': 'cmd:configure',
      'set_frequency': 'cmd:configure',
      'set_gain': 'cmd:configure',
    };
    const msgType = typeMap[command] || command;
    const payload = { type: msgType, data: data || {} };
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const clearLog = useCallback(() => {
    setConnectionLog([]);
  }, []);

  // Compute packetsReceiving from actual packet recency
  const packetsReceiving = useMemo(() => {
    if (packets.length === 0) return false;
    return (Date.now() - packets[packets.length - 1].timestamp) < 10000;
  }, [packets]);

  // Periodically update link status based on connection and packet recency
  useEffect(() => {
    if (!connected) {
      setNewLinkStatus((prev) => ({ ...prev, telemetry: 'OFFLINE', packet: 'OFFLINE' }));
      return;
    }
    const interval = setInterval(() => {
      setNewLinkStatus((prev) => ({
        ...prev,
        telemetry: packetsReceiving ? 'NOMINAL' : 'DEGRADED',
        packet: packetSeq > 0 ? 'NOMINAL' : 'OFFLINE',
      }));
    }, 2000);
    return () => clearInterval(interval);
  }, [connected, packetsReceiving, packetSeq]);

  // Update video link status based on engine pipeline
  useEffect(() => {
    setNewLinkStatus((prev) => ({
      ...prev,
      video: engineStatus?.pipeline?.running ? 'NOMINAL' : 'OFFLINE',
    }));
  }, [engineStatus?.pipeline?.running]);

  const ROLLING_WINDOW_MS = 60_000;

  function pushMetric(key: keyof typeof metricHistoryRef.current, value: number) {
    const now = Date.now();
    const buf = metricHistoryRef.current;
    const arr = [...buf[key], { timestamp: now, value }];
    const cutoff = now - ROLLING_WINDOW_MS;
    buf[key] = arr.filter((p) => p.timestamp >= cutoff);
  }

  function flushMetricHistory() {
    setMetricHistory({ ...metricHistoryRef.current });
  }

  const loadPositions = useCallback(async (since: number = 0): Promise<Array<{seq: number; lat: number; lon: number; alt_m: number}>> => {
    try {
      const host = window.location.hostname;
      const res = await fetch(`http://${host}:8000/api/positions?since=${since}&limit=5000`);
      if (!res.ok) return [];
      return await res.json();
    } catch {
      return [];
    }
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
    position,
    motion,
    environment,
    power,
    logEntries,
    packetRate,
    lastPacketAge,
    packetSeq,
    metricHistory,
    loadPositions,
  };
}
