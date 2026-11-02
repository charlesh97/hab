export interface PositionPoint {
  seq: number;
  lat: number;
  lon: number;
  alt_m: number;
  fix?: boolean;
  fix_type?: string;
}

const POSITION_EPSILON = 0.0001;

export function hasNonZeroCoordinates(lat: number, lon: number): boolean {
  return Number.isFinite(lat) && Number.isFinite(lon) && (
    Math.abs(lat) > POSITION_EPSILON || Math.abs(lon) > POSITION_EPSILON
  );
}

export function isPlottablePosition(position: PositionPoint): boolean {
  return position.fix === true || hasNonZeroCoordinates(position.lat, position.lon);
}
