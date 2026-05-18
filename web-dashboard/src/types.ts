export type FlightPhase =
'PRE-LAUNCH' |
'ASCENT' |
'FLOAT' |
'DESCENT' |
'RECOVERED';

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
  type: 'TELEMETRY' | 'EVENT' | 'COMMAND' | 'WARNING';
  payload: string;
}

export interface RfConfigData {
  callsign: string;
  beaconFreq: number;
  tone: number;
  beaconInterval: number;
  downlinkFreq: number;
  modulation: 'AFSK' | 'FSK' | 'LoRa';
  txPower: number;
  path: string;
}

export interface LinkStatus {
  telemetry: 'NOMINAL' | 'DEGRADED' | 'OFFLINE';
  video: 'NOMINAL' | 'DEGRADED' | 'OFFLINE';
  gps: 'NOMINAL' | 'DEGRADED' | 'OFFLINE';
}