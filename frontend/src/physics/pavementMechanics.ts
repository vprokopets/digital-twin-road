/**
 * Analytical 2D pavement elastostatics solvers for real-time Boussinesq (asphalt half-space)
 * and Westergaard (concrete slab on Winkler foundation) stress, deflection, and shear fields.
 */
export interface AxleModel {
  id: number
  name: string
  group: string
  type: 'single' | 'dual'
  tire: string
  is_drive: boolean
  is_steer: boolean
  p_stat_kn: number
  p_dyn_kn: number
  wheel_load_kn: number
  tire_load_kn: number
  dif: number
  pressure_kpa: number
  contact_radius_cm: number
  damage_factor: number
}

export interface PavementLayer {
  name: string
  shortName: string
  zTop: number
  zBottom: number
  E_MPa: number
  nu: number
  color: string
}

export interface FieldBuffers {
  sigmaZ: Float32Array
  wZ: Float32Array
  tauMax: Float32Array
}

export interface StressFieldMetrics {
  maxSurfaceDeflectionMm: number
  peakShearStressKpa: number
  criticalShearDepthCm: number
  subgradeTopStressKpa: number
  peakTensileBendingStressMpa: number
  radiusStiffnessM: number
}

export interface StressField2D {
  n1: number
  nz: number
  axisMin: number
  axisMax: number
  zMin: number
  zMax: number
  sigmaZ: Float32Array
  wZ: Float32Array
  tauMax: Float32Array
  metrics: StressFieldMetrics
  solverLabel: string
  activeContexts?: string[]
}

export interface PavementFieldParams {
  contactPressureKpa: number
  axleLoadKn: number
  tireConfig: 'dual' | 'single'
  axles: AxleModel[]
  relaxationLagM: number
  velocityKmh: number
}

export const GRID_NX = 140
export const GRID_NY = 160
export const GRID_NZ = 80
export const X_MIN = -2.0
export const X_MAX = 2.0
export const Y_MIN = -0.8
export const Y_MAX = 18.2
export const Z_MIN = 0.001
export const Z_MAX = 1.50

export const ASPHALT_LAYERS: PavementLayer[] = [
  { name: 'Asphalt Surface Course (SMA 11 S)', shortName: 'SMA 11 S', zTop: 0.0, zBottom: 0.04, E_MPa: 6500, nu: 0.35, color: '#f97316' },
  { name: 'Asphalt Binder Course (AC 16 B S)', shortName: 'AC 16 B S', zTop: 0.04, zBottom: 0.12, E_MPa: 8000, nu: 0.35, color: '#eab308' },
  { name: 'Asphalt Base Course (AC 22 T S)', shortName: 'AC 22 T S', zTop: 0.12, zBottom: 0.34, E_MPa: 7500, nu: 0.35, color: '#d97706' },
  { name: 'Frost Protection Layer (FSS - Unbound Gravel)', shortName: 'Gravel FSS', zTop: 0.34, zBottom: 0.70, E_MPa: 150, nu: 0.40, color: '#ca8a04' },
  { name: 'Subgrade Soil (Untergrund / Planum)', shortName: 'Subgrade', zTop: 0.70, zBottom: 1.50, E_MPa: 45, nu: 0.45, color: '#14b8a6' },
]

export const CONCRETE_LAYERS: PavementLayer[] = [
  { name: 'Concrete Slab (JPCP C30/37, d=27cm)', shortName: 'Slab C30/37', zTop: 0.0, zBottom: 0.27, E_MPa: 34000, nu: 0.20, color: '#94a3b8' },
  { name: 'Hydraulically Bound Base (HGT, d=15cm)', shortName: 'HGT Base', zTop: 0.27, zBottom: 0.42, E_MPa: 12000, nu: 0.25, color: '#64748b' },
  { name: 'Frost Protection Layer (FSS - Gravel, d=28cm)', shortName: 'Gravel FSS', zTop: 0.42, zBottom: 0.70, E_MPa: 150, nu: 0.40, color: '#ca8a04' },
  { name: 'Subgrade Soil (Untergrund / Planum)', shortName: 'Subgrade', zTop: 0.70, zBottom: 1.50, E_MPa: 45, nu: 0.45, color: '#14b8a6' },
]

/**
 * Fallback calibrated multi-axle generator for the 3 active HGV classes.
 * Evaluates when live backend KinematicAxles is initializing or in standalone mode.
 */
export const generateCalibratedAxles = (
  vehClass: string,
  grossWeightKg: number,
  velKmh = 86.5,
  slopePct = 0.0,
  accel = 0.0
): { axles: AxleModel[]; summary: any } => {
  const totalKn = (grossWeightKg * 9.81) / 1000.0
  const aLong = accel + 9.81 * (slopePct / 100.0)
  const pitchKn = ((totalKn * aLong) / 9.81) * (1.8 / 6.5) * 0.45
  const dlc = 0.05 * Math.pow(velKmh / 80.0, 1.3)

  let baseAxles: any[] = []
  if (vehClass.includes('4-Axle')) {
    baseAxles = [
      { id: 1, name: 'Axle 1 (Front Steer)', group: 'Steer', type: 'single', tire: '385/65R22.5', pct: 0.208, is_drive: false, is_steer: true, pressure: 750.0 },
      { id: 2, name: 'Axle 2 (2nd Steer)', group: 'Steer', type: 'single', tire: '385/65R22.5', pct: 0.208, is_drive: false, is_steer: true, pressure: 750.0 },
      { id: 3, name: 'Axle 3 (Drive Tandem 1)', group: 'Tandem', type: 'dual', tire: '315/80R22.5', pct: 0.292, is_drive: true, is_steer: false, pressure: 800.0 },
      { id: 4, name: 'Axle 4 (Drive Tandem 2)', group: 'Tandem', type: 'dual', tire: '315/80R22.5', pct: 0.292, is_drive: true, is_steer: false, pressure: 800.0 },
    ]
  } else if (vehClass.includes('6-Axle')) {
    baseAxles = [
      { id: 1, name: 'Axle 1 (Front Steer)', group: 'Steer', type: 'single', tire: '385/65R22.5', pct: 0.160, is_drive: false, is_steer: true, pressure: 750.0 },
      { id: 2, name: 'Axle 2 (Pusher Axle)', group: 'Pusher', type: 'single', tire: '385/65R22.5', pct: 0.160, is_drive: false, is_steer: false, pressure: 750.0 },
      { id: 3, name: 'Axle 3 (Drive Axle)', group: 'Drive', type: 'dual', tire: '315/80R22.5', pct: 0.260, is_drive: true, is_steer: false, pressure: 800.0 },
      { id: 4, name: 'Axle 4 (Trailer Tridem 1)', group: 'Tridem', type: 'dual', tire: '245/70R17.5', pct: 0.140, is_drive: false, is_steer: false, pressure: 750.0 },
      { id: 5, name: 'Axle 5 (Trailer Tridem 2)', group: 'Tridem', type: 'dual', tire: '245/70R17.5', pct: 0.140, is_drive: false, is_steer: false, pressure: 750.0 },
      { id: 6, name: 'Axle 6 (Trailer Tridem 3)', group: 'Tridem', type: 'dual', tire: '245/70R17.5', pct: 0.140, is_drive: false, is_steer: false, pressure: 750.0 },
    ]
  } else {
    // 5-Axle Semi-Trailer (EU Standard 40t)
    baseAxles = [
      { id: 1, name: 'Axle 1 (Front Steer)', group: 'Tractor Steer', type: 'single', tire: '385/65R22.5', pct: 0.175, is_drive: false, is_steer: true, pressure: 750.0 },
      { id: 2, name: 'Axle 2 (Drive Axle)', group: 'Tractor Drive', type: 'dual', tire: '315/80R22.5', pct: 0.2875, is_drive: true, is_steer: false, pressure: 800.0 },
      { id: 3, name: 'Axle 3 (Trailer Tridem 1)', group: 'Semitrailer', type: 'single', tire: '385/65R22.5', pct: 0.179, is_drive: false, is_steer: false, pressure: 750.0 },
      { id: 4, name: 'Axle 4 (Trailer Tridem 2)', group: 'Semitrailer', type: 'single', tire: '385/65R22.5', pct: 0.179, is_drive: false, is_steer: false, pressure: 750.0 },
      { id: 5, name: 'Axle 5 (Trailer Tridem 3)', group: 'Semitrailer', type: 'single', tire: '385/65R22.5', pct: 0.179, is_drive: false, is_steer: false, pressure: 750.0 },
    ]
  }

  const axleResults: AxleModel[] = baseAxles.map((a) => {
    const pStat = totalKn * a.pct
    const deltaP = a.is_steer
      ? -pitchKn * 0.5
      : a.is_drive
        ? pitchKn * 0.6
        : pitchKn * (0.4 / Math.max(1, baseAxles.length - 2))
    const pDyn = Math.max(30.0, (pStat + deltaP) * (1.0 + dlc))
    const dif = pDyn / Math.max(1.0, pStat)
    const tiresCount = a.type === 'dual' ? 4 : 2
    const pTireN = (pDyn * 1000.0) / tiresCount
    const radiusM = Math.sqrt(pTireN / (Math.PI * (a.pressure * 1000.0)))
    const damageFactor = Math.pow(pDyn / 100.0, 4.0)

    return {
      id: a.id,
      name: a.name,
      group: a.group,
      type: a.type,
      tire: a.tire,
      is_drive: a.is_drive,
      is_steer: a.is_steer,
      p_stat_kn: Number(pStat.toFixed(1)),
      p_dyn_kn: Number(pDyn.toFixed(1)),
      wheel_load_kn: Number((pDyn / 2.0).toFixed(1)),
      tire_load_kn: Number((pTireN / 1000.0).toFixed(1)),
      dif: Number(dif.toFixed(3)),
      pressure_kpa: a.pressure,
      contact_radius_cm: Number((radiusM * 100.0).toFixed(1)),
      damage_factor: Number(damageFactor.toFixed(2)),
    }
  })

  return {
    axles: axleResults,
    summary: {
      velocity_kmh: Number(velKmh.toFixed(1)),
      accel_mps2: Number(accel.toFixed(2)),
      slope_pct: Number(slopePct.toFixed(2)),
      dlc: Number(dlc.toFixed(3)),
      total_static_kn: Number(totalKn.toFixed(1)),
      total_dynamic_kn: Number(axleResults.reduce((sum, a) => sum + a.p_dyn_kn, 0).toFixed(1)),
    },
  }
}

/** Return longitudinal chassis coordinates (meters) indexed by 1-based axle number. */
export const getAxleLongitudinalPositions = (count: number): { [id: number]: number } => {
  if (count === 4) {
    return { 1: 10.8, 2: 9.1, 3: 3.8, 4: 2.4 }
  }
  if (count === 6) {
    return { 1: 13.8, 2: 12.0, 3: 9.4, 4: 4.2, 5: 2.9, 6: 1.6 }
  }
  return { 1: 13.2, 2: 9.6, 3: 4.2, 4: 2.9, 5: 1.6 }
}

function allocBuffers(n1: number, nz: number, out?: FieldBuffers): FieldBuffers {
  const len = n1 * nz
  if (out && out.sigmaZ.length >= len && out.wZ.length >= len && out.tauMax.length >= len) {
    return out
  }
  return {
    sigmaZ: new Float32Array(len),
    wZ: new Float32Array(len),
    tauMax: new Float32Array(len),
  }
}

/** Evaluate transverse Boussinesq normal stress, deflection, and max shear grid across the wheel track. */
export function computeTransverseBoussinesq(
  params: PavementFieldParams,
  outBuffers?: FieldBuffers
): StressField2D {
  const bufs = allocBuffers(GRID_NX, GRID_NZ, outBuffers)
  const p0 = params.contactPressureKpa
  const pAxleN = params.axleLoadKn * 1000.0
  const pWheelN = pAxleN / 2.0
  const isDual = params.tireConfig === 'dual'
  const pTireN = isDual ? pWheelN / 2.0 : pWheelN

  const TRACK_HALF = 1.02
  const DUAL_HALF = 0.17
  const tireOffsets = isDual
    ? [-TRACK_HALF - DUAL_HALF, -TRACK_HALF + DUAL_HALF, TRACK_HALF - DUAL_HALF, TRACK_HALF + DUAL_HALF]
    : [-TRACK_HALF, TRACK_HALF]

  const contactRadius = Math.sqrt(pTireN / (Math.PI * (p0 * 1000.0)))
  const a = Math.max(0.05, contactRadius)

  const E_equiv = 350.0 * 1e6
  const nu_equiv = 0.35

  let maxW = 0.0
  let maxTau = 0.0
  let maxTauZ = 0.07
  let subgradeSigma = 0.0

  const dx = (X_MAX - X_MIN) / (GRID_NX - 1)
  const dz = (Z_MAX - Z_MIN) / (GRID_NZ - 1)

  for (let iz = 0; iz < GRID_NZ; iz++) {
    const z = Z_MIN + iz * dz
    const z_eff = Math.max(z, 0.005)
    const centerline = 1.0 - Math.pow(z_eff, 3) / Math.pow(a * a + z_eff * z_eff, 1.5)
    const spread = Math.sqrt(a * a + 0.45 * z_eff * z_eff)

    for (let ix = 0; ix < GRID_NX; ix++) {
      const x = X_MIN + ix * dx
      const idx = iz * GRID_NX + ix

      let sigZ = 0.0
      let wZ = 0.0
      let sigX = 0.0

      for (let it = 0; it < tireOffsets.length; it++) {
        const r = Math.abs(x - tireOffsets[it])
        const lateral = Math.pow(1.0 + Math.pow(r / spread, 2), -2.5)
        const tireSigZ = p0 * centerline * lateral
        sigZ += tireSigZ

        const radFactor = z_eff / Math.sqrt(r * r + z_eff * z_eff)
        const tireSigX = tireSigZ * (1.0 - 0.7 * radFactor)
        sigX += tireSigX

        const wCenter =
          ((2.0 * (p0 * 1000.0) * (1.0 - nu_equiv * nu_equiv) * a) / E_equiv) *
          (Math.sqrt(1.0 + Math.pow(z_eff / a, 2)) - z_eff / a) *
          1000.0
        const wLateral = Math.pow(1.0 + Math.pow(r / (a + 0.75 * z_eff), 2), -0.75)
        wZ += wCenter * wLateral
      }

      const tau = Math.max(0.0, (sigZ - sigX) * 0.5)

      bufs.sigmaZ[idx] = sigZ
      bufs.wZ[idx] = wZ
      bufs.tauMax[idx] = tau

      if (wZ > maxW) maxW = wZ
      if (tau > maxTau) {
        maxTau = tau
        maxTauZ = z
      }
      if (Math.abs(z - 0.70) < dz * 0.6 && Math.abs(x - TRACK_HALF) < dx * 1.5) {
        subgradeSigma = sigZ
      }
    }
  }

  return {
    n1: GRID_NX,
    nz: GRID_NZ,
    axisMin: X_MIN,
    axisMax: X_MAX,
    zMin: Z_MIN,
    zMax: Z_MAX,
    sigmaZ: bufs.sigmaZ,
    wZ: bufs.wZ,
    tauMax: bufs.tauMax,
    metrics: {
      maxSurfaceDeflectionMm: Number(maxW.toFixed(2)),
      peakShearStressKpa: Number(maxTau.toFixed(1)),
      criticalShearDepthCm: Number((maxTauZ * 100.0).toFixed(1)),
      subgradeTopStressKpa: Number(subgradeSigma.toFixed(1)),
      peakTensileBendingStressMpa: 0.0,
      radiusStiffnessM: 0.9,
    },
    solverLabel: 'Boussinesq Transverse Cross-Section',
  }
}

/** Evaluate longitudinal multi-axle Boussinesq stress field with viscoelastic rolling velocity lag. */
export function computeSideBoussinesq(
  params: PavementFieldParams,
  outBuffers?: FieldBuffers
): StressField2D {
  const bufs = allocBuffers(GRID_NY, GRID_NZ, outBuffers)
  const p0 = params.contactPressureKpa
  const axles = params.axles
  if (!axles.length) {
    return {
      n1: GRID_NY,
      nz: GRID_NZ,
      axisMin: Y_MIN,
      axisMax: Y_MAX,
      zMin: Z_MIN,
      zMax: Z_MAX,
      sigmaZ: bufs.sigmaZ,
      wZ: bufs.wZ,
      tauMax: bufs.tauMax,
      metrics: {
        maxSurfaceDeflectionMm: 0.0,
        peakShearStressKpa: 0.0,
        criticalShearDepthCm: 7.0,
        subgradeTopStressKpa: 0.0,
        peakTensileBendingStressMpa: 0.0,
        radiusStiffnessM: 0.9,
      },
      solverLabel: 'Boussinesq Side View (Viscoelastic Lag)',
    }
  }

  const positions = getAxleLongitudinalPositions(axles.length)
  const L_lag = params.relaxationLagM
  const velKmh = params.velocityKmh ?? 86.5
  const velMps = Math.max(0.0, velKmh / 3.6)

  const E_equiv = 350.0 * 1e6
  const nu_equiv = 0.35

  let maxW = 0.0
  let maxTau = 0.0
  let maxTauZ = 0.07
  let subgradeSigma = 0.0

  const dy = (Y_MAX - Y_MIN) / (GRID_NY - 1)
  const dz = (Z_MAX - Z_MIN) / (GRID_NZ - 1)

  for (let iz = 0; iz < GRID_NZ; iz++) {
    const z = Z_MIN + iz * dz
    const z_eff = Math.max(z, 0.005)

    for (let iy = 0; iy < GRID_NY; iy++) {
      const y = Y_MIN + iy * dy
      const idx = iz * GRID_NY + iy

      let totalSigZ = 0.0
      let totalWZ = 0.0
      let totalSigY = 0.0

      for (let ia = 0; ia < axles.length; ia++) {
        const ax = axles[ia]
        const yPos = positions[ax.id] ?? 8.0
        const pWheel = (ax.p_dyn_kn * 1000.0) / 2.0
        const nTires = ax.type === 'dual' ? 2 : 1
        const pTire = pWheel / nTires
        const a = Math.max(0.05, Math.sqrt(pTire / (Math.PI * (p0 * 1000.0))))

        const centerline = 1.0 - Math.pow(z_eff, 3) / Math.pow(a * a + z_eff * z_eff, 1.5)
        const spread = Math.sqrt(a * a + 0.45 * z_eff * z_eff)

        const dist = y - yPos
        const absDist = Math.abs(dist)

        const longShape = Math.pow(1.0 + Math.pow(absDist / spread, 2), -2.5)
        let sigZ_ax = p0 * centerline * longShape

        if (dist < 0) {
          const behindDist = -dist
          const lagFactor = Math.exp(-behindDist / Math.max(0.15, L_lag))
          const depthCoupling = Math.exp(-z_eff / 0.45)
          const speedScaling = Math.min(1.0, velMps / 15.0)
          sigZ_ax += p0 * centerline * 0.70 * lagFactor * depthCoupling * speedScaling
        }

        const radFactor = z_eff / Math.sqrt(absDist * absDist + z_eff * z_eff)
        const sigY_ax = sigZ_ax * (1.0 - 0.65 * radFactor)

        const wCenter =
          ((2.0 * (p0 * 1000.0) * (1.0 - nu_equiv * nu_equiv) * a) / E_equiv) *
          (Math.sqrt(1.0 + Math.pow(z_eff / a, 2)) - z_eff / a) *
          1000.0
        const wShape = Math.pow(1.0 + Math.pow(absDist / (a + 0.75 * z_eff), 2), -0.75)
        const wZ_ax = wCenter * wShape

        totalSigZ += sigZ_ax
        totalSigY += sigY_ax
        totalWZ += wZ_ax
      }

      const tau = Math.max(0.0, (totalSigZ - totalSigY) * 0.5)

      bufs.sigmaZ[idx] = totalSigZ
      bufs.wZ[idx] = totalWZ
      bufs.tauMax[idx] = tau

      if (totalWZ > maxW) maxW = totalWZ
      if (tau > maxTau) {
        maxTau = tau
        maxTauZ = z
      }
      if (Math.abs(z - 0.70) < dz * 0.6 && Math.abs(y - 9.6) < 0.2) {
        subgradeSigma = totalSigZ
      }
    }
  }

  return {
    n1: GRID_NY,
    nz: GRID_NZ,
    axisMin: Y_MIN,
    axisMax: Y_MAX,
    zMin: Z_MIN,
    zMax: Z_MAX,
    sigmaZ: bufs.sigmaZ,
    wZ: bufs.wZ,
    tauMax: bufs.tauMax,
    metrics: {
      maxSurfaceDeflectionMm: Number(maxW.toFixed(2)),
      peakShearStressKpa: Number(maxTau.toFixed(1)),
      criticalShearDepthCm: Number((maxTauZ * 100.0).toFixed(1)),
      subgradeTopStressKpa: Number(subgradeSigma.toFixed(1)),
      peakTensileBendingStressMpa: 0.0,
      radiusStiffnessM: 0.9,
    },
    solverLabel: 'Boussinesq Side View (Viscoelastic Lag)',
  }
}

/** Evaluate transverse Westergaard rigid slab deflection and bending stress field on Winkler springs. */
export function computeTransverseWestergaard(
  params: PavementFieldParams,
  outBuffers?: FieldBuffers
): StressField2D {
  const bufs = allocBuffers(GRID_NX, GRID_NZ, outBuffers)
  const p0 = params.contactPressureKpa
  const pAxleN = params.axleLoadKn * 1000.0
  const pWheelN = pAxleN / 2.0
  const isDual = params.tireConfig === 'dual'
  const pTireN = isDual ? pWheelN / 2.0 : pWheelN

  const TRACK_HALF = 1.02
  const DUAL_HALF = 0.17
  const tireOffsets = isDual
    ? [-TRACK_HALF - DUAL_HALF, -TRACK_HALF + DUAL_HALF, TRACK_HALF - DUAL_HALF, TRACK_HALF + DUAL_HALF]
    : [-TRACK_HALF, TRACK_HALF]

  const contactRadius = Math.sqrt(pTireN / (Math.PI * (p0 * 1000.0)))
  const a = Math.max(0.05, contactRadius)

  const h_slab = 0.27
  const E_slab = 34000.0 * 1e6
  const nu_slab = 0.20
  const k_subgrade = 80.0 * 1e6
  const D_rigidity = (E_slab * Math.pow(h_slab, 3)) / (12.0 * (1.0 - nu_slab * nu_slab))
  const ell = Math.pow(D_rigidity / k_subgrade, 0.25)

  const b = a < 1.724 * h_slab ? Math.sqrt(1.6 * a * a + h_slab * h_slab) - 0.675 * h_slab : a
  const sigmaBendPrefactor = (3.0 * pTireN * (1.0 + nu_slab)) / (2.0 * Math.PI * (h_slab * h_slab))
  const peakSigmaBendPa = sigmaBendPrefactor * (Math.log(ell / b) + 0.6159)
  const peakSigmaBendKpa = peakSigmaBendPa / 1000.0

  let maxW = 0.0
  let maxTau = 0.0
  let maxTauZ = h_slab
  let subgradeSigma = 0.0

  const dx = (X_MAX - X_MIN) / (GRID_NX - 1)
  const dz = (Z_MAX - Z_MIN) / (GRID_NZ - 1)

  for (let iz = 0; iz < GRID_NZ; iz++) {
    const z = Z_MIN + iz * dz
    const inSlab = z <= h_slab

    for (let ix = 0; ix < GRID_NX; ix++) {
      const x = X_MIN + ix * dx
      const idx = iz * GRID_NX + ix

      let wZ = 0.0
      let sigZ = 0.0
      let sigX = 0.0

      for (let it = 0; it < tireOffsets.length; it++) {
        const r = Math.abs(x - tireOffsets[it])
        const rNorm = r / ell

        const w0_tire = (pTireN / (8.0 * k_subgrade * (ell * ell))) * 1000.0
        const wave = Math.exp(-rNorm) * (Math.cos(rNorm) + Math.sin(rNorm))
        wZ += w0_tire * wave

        const bendDecay = Math.exp(-rNorm * 1.2) * Math.cos(rNorm * 0.8)
        const localBendKpa = peakSigmaBendKpa * bendDecay

        if (inSlab) {
          const zRel = (z - h_slab / 2.0) / (h_slab / 2.0)
          sigX += localBendKpa * zRel

          const tireFootprint = Math.exp(-Math.pow(r / Math.max(0.08, a * 1.2), 2))
          const verticalContact = p0 * tireFootprint * (1.0 - z / h_slab)
          const baseReaction = (k_subgrade / 1000.0) * (w0_tire / 1000.0) * wave * (z / h_slab)
          sigZ += verticalContact + baseReaction
        } else {
          const depthBelowSlab = z - h_slab
          const subgradeAtten = 1.0 / (1.0 + 1.2 * Math.pow(depthBelowSlab / 0.5, 2))
          const foundationPressure = (k_subgrade / 1000.0) * (w0_tire / 1000.0) * Math.max(0, wave)
          sigZ += foundationPressure * subgradeAtten
          sigX += foundationPressure * subgradeAtten * 0.35
        }
      }

      const tau = Math.max(0.0, Math.abs(sigZ - sigX) * 0.5)

      bufs.sigmaZ[idx] = Math.max(0.0, sigZ)
      bufs.wZ[idx] = Math.max(0.0, wZ)
      bufs.tauMax[idx] = tau

      if (wZ > maxW) maxW = wZ
      if (tau > maxTau) {
        maxTau = tau
        maxTauZ = z
      }
      if (Math.abs(z - 0.70) < dz * 0.6 && Math.abs(x - TRACK_HALF) < dx * 1.5) {
        subgradeSigma = sigZ
      }
    }
  }

  return {
    n1: GRID_NX,
    nz: GRID_NZ,
    axisMin: X_MIN,
    axisMax: X_MAX,
    zMin: Z_MIN,
    zMax: Z_MAX,
    sigmaZ: bufs.sigmaZ,
    wZ: bufs.wZ,
    tauMax: bufs.tauMax,
    metrics: {
      maxSurfaceDeflectionMm: Number(maxW.toFixed(2)),
      peakShearStressKpa: Number(maxTau.toFixed(1)),
      criticalShearDepthCm: Number((maxTauZ * 100.0).toFixed(1)),
      subgradeTopStressKpa: Number(subgradeSigma.toFixed(1)),
      peakTensileBendingStressMpa: Number((peakSigmaBendKpa / 1000.0).toFixed(2)),
      radiusStiffnessM: Number(ell.toFixed(2)),
    },
    solverLabel: 'Westergaard Slab Transverse Cross-Section',
  }
}

/** Evaluate longitudinal multi-axle Westergaard slab stress, deflection, and subgrade pressure field. */
export function computeSideWestergaard(
  params: PavementFieldParams,
  outBuffers?: FieldBuffers
): StressField2D {
  const bufs = allocBuffers(GRID_NY, GRID_NZ, outBuffers)
  const p0 = params.contactPressureKpa
  const axles = params.axles
  const h_slab = 0.27
  const E_slab = 34000.0 * 1e6
  const nu_slab = 0.20
  const k_subgrade = 80.0 * 1e6
  const D_rigidity = (E_slab * Math.pow(h_slab, 3)) / (12.0 * (1.0 - nu_slab * nu_slab))
  const ell = Math.pow(D_rigidity / k_subgrade, 0.25)

  if (!axles.length) {
    return {
      n1: GRID_NY,
      nz: GRID_NZ,
      axisMin: Y_MIN,
      axisMax: Y_MAX,
      zMin: Z_MIN,
      zMax: Z_MAX,
      sigmaZ: bufs.sigmaZ,
      wZ: bufs.wZ,
      tauMax: bufs.tauMax,
      metrics: {
        maxSurfaceDeflectionMm: 0.0,
        peakShearStressKpa: 0.0,
        criticalShearDepthCm: 26.0,
        subgradeTopStressKpa: 0.0,
        peakTensileBendingStressMpa: 0.0,
        radiusStiffnessM: Number(ell.toFixed(2)),
      },
      solverLabel: 'Westergaard Multi-Axle Slab Side View',
    }
  }

  const positions = getAxleLongitudinalPositions(axles.length)
  let maxW = 0.0
  let maxTau = 0.0
  let maxTauZ = h_slab
  let subgradeSigma = 0.0
  let maxTensileBend = 0.0

  const dy = (Y_MAX - Y_MIN) / (GRID_NY - 1)
  const dz = (Z_MAX - Z_MIN) / (GRID_NZ - 1)

  for (let iz = 0; iz < GRID_NZ; iz++) {
    const z = Z_MIN + iz * dz
    const inSlab = z <= h_slab

    for (let iy = 0; iy < GRID_NY; iy++) {
      const y = Y_MIN + iy * dy
      const idx = iz * GRID_NY + iy

      let totalSigZ = 0.0
      let totalWZ = 0.0
      let totalSigY = 0.0

      for (let ia = 0; ia < axles.length; ia++) {
        const ax = axles[ia]
        const yPos = positions[ax.id] ?? 8.0
        const pWheel = (ax.p_dyn_kn * 1000.0) / 2.0
        const nTires = ax.type === 'dual' ? 2 : 1
        const pTire = pWheel / nTires
        const a = Math.max(0.05, Math.sqrt(pTire / (Math.PI * (p0 * 1000.0))))
        const b = a < 1.724 * h_slab ? Math.sqrt(1.6 * a * a + h_slab * h_slab) - 0.675 * h_slab : a

        const dist = Math.abs(y - yPos)
        const rNorm = dist / ell

        const w0_ax = (pWheel / (8.0 * k_subgrade * (ell * ell))) * 1000.0
        const wave = Math.exp(-rNorm) * (Math.cos(rNorm) + Math.sin(rNorm))
        totalWZ += w0_ax * wave

        const sigmaBendPrefactor = (3.0 * pWheel * (1.0 + nu_slab)) / (2.0 * Math.PI * (h_slab * h_slab))
        const peakBendKpa = (sigmaBendPrefactor * (Math.log(ell / b) + 0.6159)) / 1000.0
        const bendDecay = Math.exp(-rNorm * 1.2) * Math.cos(rNorm * 0.8)
        const localBendKpa = peakBendKpa * bendDecay

        if (inSlab) {
          const zRel = (z - h_slab / 2.0) / (h_slab / 2.0)
          totalSigY += localBendKpa * zRel

          const tireFootprint = Math.exp(-Math.pow(dist / Math.max(0.12, a * 1.5), 2))
          const verticalContact = p0 * tireFootprint * (1.0 - z / h_slab)
          const baseReaction = (k_subgrade / 1000.0) * (w0_ax / 1000.0) * wave * (z / h_slab)
          totalSigZ += verticalContact + baseReaction
        } else {
          const depthBelowSlab = z - h_slab
          const subgradeAtten = 1.0 / (1.0 + 1.2 * Math.pow(depthBelowSlab / 0.5, 2))
          const foundationPressure = (k_subgrade / 1000.0) * (w0_ax / 1000.0) * Math.max(0, wave)
          totalSigZ += foundationPressure * subgradeAtten
          totalSigY += foundationPressure * subgradeAtten * 0.35
        }

        if (inSlab && localBendKpa > maxTensileBend) {
          maxTensileBend = localBendKpa
        }
      }

      const tau = Math.max(0.0, Math.abs(totalSigZ - totalSigY) * 0.5)

      bufs.sigmaZ[idx] = Math.max(0.0, totalSigZ)
      bufs.wZ[idx] = Math.max(0.0, totalWZ)
      bufs.tauMax[idx] = tau

      if (totalWZ > maxW) maxW = totalWZ
      if (tau > maxTau) {
        maxTau = tau
        maxTauZ = z
      }
      if (Math.abs(z - 0.70) < dz * 0.6 && Math.abs(y - 9.6) < 0.2) {
        subgradeSigma = totalSigZ
      }
    }
  }

  return {
    n1: GRID_NY,
    nz: GRID_NZ,
    axisMin: Y_MIN,
    axisMax: Y_MAX,
    zMin: Z_MIN,
    zMax: Z_MAX,
    sigmaZ: bufs.sigmaZ,
    wZ: bufs.wZ,
    tauMax: bufs.tauMax,
    metrics: {
      maxSurfaceDeflectionMm: Number(maxW.toFixed(2)),
      peakShearStressKpa: Number(maxTau.toFixed(1)),
      criticalShearDepthCm: Number((maxTauZ * 100.0).toFixed(1)),
      subgradeTopStressKpa: Number(subgradeSigma.toFixed(1)),
      peakTensileBendingStressMpa: Number((maxTensileBend / 1000.0).toFixed(2)),
      radiusStiffnessM: Number(ell.toFixed(2)),
    },
    solverLabel: 'Westergaard Multi-Axle Slab Side View',
  }
}

/** Dispatch the 2D analytical stress field computation matching `pavementType` and `viewMode`. */
export function computePavementField(
  pavementType: 'asphalt' | 'concrete',
  viewMode: 'side' | 'cross',
  params: PavementFieldParams,
  outBuffers?: FieldBuffers
): StressField2D {
  if (pavementType === 'concrete') {
    return viewMode === 'side'
      ? computeSideWestergaard(params, outBuffers)
      : computeTransverseWestergaard(params, outBuffers)
  }
  return viewMode === 'side'
    ? computeSideBoussinesq(params, outBuffers)
    : computeTransverseBoussinesq(params, outBuffers)
}

/**
 * Converts a 2D JSON grid payload from `/dashboard/boussinesq_stress` or an external
 * Julia solver into the flattened Float32Array `StressField2D` buffer contract.
 */
export function fromBackendStressPayload(payload: any): StressField2D {
  const xCoords: number[] = Array.isArray(payload?.x_coords) ? payload.x_coords : []
  const zCoords: number[] = Array.isArray(payload?.z_coords) ? payload.z_coords : []
  const sigRows: number[][] = Array.isArray(payload?.sigma_z) ? payload.sigma_z : []
  const wRows: number[][] = Array.isArray(payload?.w_z) ? payload.w_z : []
  const tauRows: number[][] = Array.isArray(payload?.tau_max) ? payload.tau_max : []

  const nz = sigRows.length || zCoords.length
  const n1 = sigRows[0]?.length || xCoords.length
  const len = n1 * nz
  const sigmaZ = new Float32Array(len)
  const wZ = new Float32Array(len)
  const tauMax = new Float32Array(len)

  let maxW = 0.0
  let maxTau = 0.0
  let maxTauZ = 0.07

  for (let iz = 0; iz < nz; iz++) {
    const sRow = sigRows[iz] || []
    const wRow = wRows[iz] || []
    const tRow = tauRows[iz] || []
    const zVal = zCoords[iz] ?? 0
    for (let i1 = 0; i1 < n1; i1++) {
      const idx = iz * n1 + i1
      const wVal = Number(wRow[i1] ?? 0)
      const tVal = Number(tRow[i1] ?? 0)
      sigmaZ[idx] = Number(sRow[i1] ?? 0)
      wZ[idx] = wVal
      tauMax[idx] = tVal
      if (wVal > maxW) maxW = wVal
      if (tVal > maxTau) {
        maxTau = tVal
        maxTauZ = zVal
      }
    }
  }

  return {
    n1,
    nz,
    axisMin: xCoords.length ? Number(xCoords[0]) : X_MIN,
    axisMax: xCoords.length ? Number(xCoords[xCoords.length - 1]) : X_MAX,
    zMin: zCoords.length ? Number(zCoords[0]) : Z_MIN,
    zMax: zCoords.length ? Number(zCoords[zCoords.length - 1]) : Z_MAX,
    sigmaZ,
    wZ,
    tauMax,
    metrics: {
      maxSurfaceDeflectionMm: Number(maxW.toFixed(2)),
      peakShearStressKpa: Number(maxTau.toFixed(1)),
      criticalShearDepthCm: Number((maxTauZ * 100.0).toFixed(1)),
      subgradeTopStressKpa: 0.0,
      peakTensileBendingStressMpa: 0.0,
      radiusStiffnessM: 0.9,
    },
    solverLabel: String(payload?.solver_label || 'Backend / External 2D Stress Solver'),
    activeContexts: Array.isArray(payload?.active_contexts) ? payload.active_contexts : undefined,
  }
}
