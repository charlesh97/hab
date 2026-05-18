import { useState, useEffect, useRef } from 'react';
import { TelemetrySample, FlightPhase, Packet, LinkStatus } from '../types';

const START_LAT = 39.05;
const START_LNG = -105.5;
const MAX_HISTORY = 120; // Keep 120 seconds of history for charts

export function useFlightSimulation() {
  const [phase, setPhase] = useState<FlightPhase>('ASCENT');
  const [missionTime, setMissionTime] = useState(3600); // Start at T+ 1 hour for demo
  const [history, setHistory] = useState<TelemetrySample[]>([]);
  const [packets, setPackets] = useState<Packet[]>([]);
  const [linkStatus, setLinkStatus] = useState<LinkStatus>({
    telemetry: 'NOMINAL',
    video: 'NOMINAL',
    gps: 'NOMINAL'
  });

  // Initial state representing a balloon already in flight
  const currentRef = useRef<TelemetrySample>({
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
    lat: START_LAT + 0.15,
    lng: START_LNG + 0.25
  });

  useEffect(() => {
    // Generate some initial history
    const initialHistory: TelemetrySample[] = [];
    let tempState = { ...currentRef.current };
    for (let i = MAX_HISTORY; i > 0; i--) {
      tempState = {
        ...tempState,
        timestamp: Date.now() - i * 1000,
        altitude: Math.max(0, tempState.altitude - 4.8),
        lat: tempState.lat - 0.0001,
        lng: tempState.lng - 0.0002
      };
      initialHistory.push({ ...tempState });
    }
    setHistory(initialHistory);

    const interval = setInterval(() => {
      setMissionTime((prev) => prev + 1);

      const prev = currentRef.current;
      let newPhase = phase;
      let newVsi = prev.verticalSpeed;

      // Phase logic
      if (prev.altitude > 30000 && phase === 'ASCENT') {
        newPhase = 'FLOAT';
        newVsi = 0.1; // Float drift
      } else if (missionTime > 7200 && phase === 'FLOAT') {
        newPhase = 'DESCENT';
        newVsi = -8.5; // Fast descent initially
      } else if (prev.altitude <= 0 && phase === 'DESCENT') {
        newPhase = 'RECOVERED';
        newVsi = 0;
      }

      setPhase(newPhase);

      // Add some noise
      const noise = (val: number, variance: number) =>
      val + (Math.random() - 0.5) * variance;

      // Calculate new values
      const newAltitude = Math.max(0, prev.altitude + newVsi);

      // Standard atmosphere temp approx
      let newExtTemp = 15.0;
      if (newAltitude < 11000) newExtTemp = 15.0 - newAltitude / 1000 * 6.5;else
      if (newAltitude < 20000) newExtTemp = -56.5;else
      newExtTemp = -56.5 + (newAltitude - 20000) / 1000 * 1.0;

      // Barometric formula approx
      const newPressure =
      1013.25 * Math.pow(1 - 2.25577e-5 * newAltitude, 5.25588);

      const nextSample: TelemetrySample = {
        timestamp: Date.now(),
        altitude: newAltitude,
        verticalSpeed: noise(newVsi, 0.5),
        groundSpeed: noise(prev.groundSpeed, 1.0),
        heading: noise(prev.heading, 2.0) % 360,
        internalTemp: noise(prev.internalTemp - 0.001, 0.1), // slowly cooling
        externalTemp: noise(newExtTemp, 0.5),
        pressure: Math.max(0, noise(newPressure, 0.5)),
        battery: Math.max(0, prev.battery - 0.005), // slow drain
        gpsSats:
        Math.random() > 0.95 ? prev.gpsSats === 12 ? 11 : 12 : prev.gpsSats,
        lat:
        prev.lat +
        prev.groundSpeed * Math.cos(prev.heading * Math.PI / 180) /
        111000,
        lng:
        prev.lng +
        prev.groundSpeed * Math.sin(prev.heading * Math.PI / 180) / (
        111000 * Math.cos(prev.lat * Math.PI / 180))
      };

      currentRef.current = nextSample;

      setHistory((prevHist) => {
        const next = [...prevHist, nextSample];
        if (next.length > MAX_HISTORY) return next.slice(1);
        return next;
      });

      // Generate packet log
      const packetType = Math.random() > 0.9 ? 'EVENT' : 'TELEMETRY';
      const newPacket: Packet = {
        id: Math.random().toString(36).substring(7).toUpperCase(),
        timestamp: Date.now(),
        type: packetType,
        payload:
        packetType === 'TELEMETRY' ?
        `[TLM] A:${nextSample.altitude.toFixed(0)}m V:${nextSample.verticalSpeed.toFixed(1)}m/s T:${nextSample.externalTemp.toFixed(1)}C P:${nextSample.pressure.toFixed(1)}hPa` :
        `[EVT] STATUS_UPDATE_NOMINAL SATS:${nextSample.gpsSats}`
      };

      setPackets((prevPackets) => {
        const next = [...prevPackets, newPacket];
        if (next.length > 200) return next.slice(next.length - 200);
        return next;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [phase, missionTime]);

  return {
    phase,
    missionTime,
    current: currentRef.current,
    history,
    packets,
    linkStatus
  };
}