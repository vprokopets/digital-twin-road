/**
 * Frontend Coordinate Reference System (CRS) utilities supporting WGS84 geodesic
 * corridors and LocalCartesian test tracks without changing downstream map rendering.
 */
export type MapCrsMode = 'WGS84' | 'LocalCartesian'

export interface MapCoordSystem {
  readonly mode: MapCrsMode
  /** Computes planar or spherical distance in meters between GeoJSON `[xOrLon, yOrLat]` coordinates. */
  distanceMeters(c0: [number, number], c1: [number, number]): number
  /** Returns approximate meters per coordinate unit along X (lon/x) and Y (lat/y). */
  metersPerAxis(latOrY: number): { mPerX: number; mPerY: number }
  /** Advances a Leaflet `[yOrLat, xOrLon]` point toward target by `stepMeters`. */
  stepToward(curLatLng: [number, number], tgtLatLng: [number, number], stepMeters: number): [number, number]
  /** Precomputes cumulative metric arc-lengths along a GeoJSON coordinate polyline. */
  computePolylineCumDists(coords: number[][]): { cumDists: number[]; totalLenM: number }
}

const R_EARTH_METERS = 6371000.0

function haversineMeters(c0: [number, number], c1: [number, number]): number {
  const lat1 = (c0[1] * Math.PI) / 180.0
  const lat2 = (c1[1] * Math.PI) / 180.0
  const dLat = ((c1[1] - c0[1]) * Math.PI) / 180.0
  const dLon = ((c1[0] - c0[0]) * Math.PI) / 180.0
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) * Math.sin(dLon / 2)
  return 2.0 * R_EARTH_METERS * Math.asin(Math.sqrt(Math.max(0.0, Math.min(1.0, a))))
}

function buildCoordSystem(mode: MapCrsMode): MapCoordSystem {
  const isCartesian = mode === 'LocalCartesian'

  const distanceMeters = (c0: [number, number], c1: [number, number]): number => {
    if (isCartesian) {
      return Math.hypot(c1[0] - c0[0], c1[1] - c0[1])
    }
    return haversineMeters(c0, c1)
  }

  const metersPerAxis = (latOrY: number): { mPerX: number; mPerY: number } => {
    if (isCartesian) {
      return { mPerX: 1.0, mPerY: 1.0 }
    }
    return {
      mPerX: 111320.0 * Math.cos((latOrY * Math.PI) / 180.0),
      mPerY: 111132.0,
    }
  }

  const stepToward = (
    curLatLng: [number, number],
    tgtLatLng: [number, number],
    stepMeters: number
  ): [number, number] => {
    const distM = distanceMeters([curLatLng[1], curLatLng[0]], [tgtLatLng[1], tgtLatLng[0]])
    if (distM <= 0.5) {
      return curLatLng
    }
    const frac = Math.min(1.0, stepMeters / distM)
    return [
      curLatLng[0] + (tgtLatLng[0] - curLatLng[0]) * frac,
      curLatLng[1] + (tgtLatLng[1] - curLatLng[1]) * frac,
    ]
  }

  const computePolylineCumDists = (coords: number[][]): { cumDists: number[]; totalLenM: number } => {
    const cumDists: number[] = [0]
    let totalLenM = 0
    for (let i = 0; i < coords.length - 1; i++) {
      const c0 = coords[i]
      const c1 = coords[i + 1]
      const segLen = distanceMeters([c0[0], c0[1]], [c1[0], c1[1]])
      totalLenM += segLen
      cumDists.push(totalLenM)
    }
    return { cumDists, totalLenM }
  }

  return {
    mode,
    distanceMeters,
    metersPerAxis,
    stepToward,
    computePolylineCumDists,
  }
}

/** Instantiate a coordinate helper matching `'WGS84'` (default) or `'LocalCartesian'`. */
export function createMapCoordSystem(mode?: string): MapCoordSystem {
  const normalized: MapCrsMode = mode === 'LocalCartesian' ? 'LocalCartesian' : 'WGS84'
  return buildCoordSystem(normalized)
}
