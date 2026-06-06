export type FlightPhase = 'PRE-LAUNCH' | 'ASCENT' | 'FLOAT' | 'DESCENT' | 'RECOVERED';

export interface PositionData {
  lat: number;
  lon: number;
  alt_m: number;
  agl_m: number;
  fix: boolean;
  fix_type: string;
  sats: number;
  hdop: number;
  vdop: number;
}

export interface MotionData {
  gs_mps: number;
  vs_mps: number;
  heading_deg: number;
  cog_deg: number;
  accel: { x: number; y: number; z: number };
  gyro_dps: { r: number; p: number; y: number };
  att_deg: { roll: number; pitch: number; yaw: number };
}

export interface EnvironmentData {
  temp_ext_c: number;
  temp_int_c: number;
  pressure_hpa: number;
  humidity_pct: number;
  baro_alt_m: number;
}

export interface PowerData {
  bat_v: number;
  bat_a: number;
  bat_w: number;
  bat_pct: number;
  bat_temp_c: number;
}

export interface TelemetryPacket {
  v: number;
  id: string;
  mid: string;
  seq: number;
  t: string;
  type: 'position' | 'motion' | 'environment' | 'power';
}

export interface PositionPacket extends TelemetryPacket, PositionData { type: 'position'; }
export interface MotionPacket extends TelemetryPacket, MotionData { type: 'motion'; }
export interface EnvironmentPacket extends TelemetryPacket, EnvironmentData { type: 'environment'; }
export interface PowerPacket extends TelemetryPacket, PowerData { type: 'power'; }

export type TelemetryMessage = PositionPacket | MotionPacket | EnvironmentPacket | PowerPacket;

export interface LogEntry {
  timestamp: string;
  type: 'POS' | 'MOT' | 'ENV' | 'PWR' | 'SYS';
  payload: string;
}

export interface EngineStatus {
  running: boolean;
  tx_active: boolean;
  device_connected: boolean;
  device_serial?: string;
  frequency: number;
  symbol_rate: number;
  uptime_sec: number;
  pipeline: { running: boolean; file_path: string; bitrate: number } | null;
  error_count?: number;
  last_error?: string;
  rx_active?: boolean;
}

export interface TelemetrySample {
  timestamp: number;
  altitude: number;
  verticalSpeed: number;
  groundSpeed: number;
  heading: number;
  internalTemp: number;
  externalTemp: number;
  pressure: number;
  battery: number;
  gpsSats: number;
  lat: number;
  lng: number;
}

export interface Packet {
  id: string;
  timestamp: number;
  type: string;
  payload: string;
}

export interface LinkStatus {
  telemetry: 'NOMINAL' | 'DEGRADED' | 'OFFLINE';
  packet: 'NOMINAL' | 'DEGRADED' | 'OFFLINE';
  video: 'NOMINAL' | 'DEGRADED' | 'OFFLINE';
}

export interface RfConfig {
  frequency: number;
  symbol_rate: number;
  lo_ppm: number;
  lna_gain: number;
  vga_gain: number;
  amp_enabled: boolean;
}

export interface Dvbs2Config {
  modcod: string;
  pilots: boolean;
  rolloff: number;
  fec_frame: 'NORMAL' | 'SHORT';
  symbol_rate: number;
  sps: number;
  rrc_delay: number;
  gold_code: number;
  fullscale: number;
  sink_type: string;
  device_args: string;
}

export interface PipelineConfig {
  file_path: string;
  running: boolean;
  bitrate: number;
  duration: string;
  errors: number;
}

export interface ConnectionLogEntry {
  timestamp: number;
  message: string;
  type: 'info' | 'error' | 'warning';
}

export interface MetricPoint {
  timestamp: number;
  value: number;
}
