<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import {
  RotateCcw,
  Activity,
  Truck,
  Layers,
  ChevronDown,
  ChevronUp
} from 'lucide-vue-next'
import { useDashboardStore } from '../../stores/dashboard'
import {
  type AxleModel,
  type FieldBuffers,
  ASPHALT_LAYERS as asphaltLayers,
  CONCRETE_LAYERS as concreteLayers,
  GRID_NX,
  GRID_NY,
  GRID_NZ,
  X_MIN,
  X_MAX,
  Y_MIN,
  Y_MAX,
  Z_MIN,
  Z_MAX,
  generateCalibratedAxles,
  getAxleLongitudinalPositions,
  computePavementField,
} from '../../physics/pavementMechanics'

export type { AxleModel }

const store = useDashboardStore()

const props = defineProps<{
  drawerWidth?: number
}>()

// ============================================================================
// RESPONSIVE / ADAPTIVE STATE
// ============================================================================
const isCompact = computed(() => {
  return (props.drawerWidth || 460) < 640
})

const isVeryCompact = computed(() => {
  return (props.drawerWidth || 460) < 490
})

// Active selected axle ID (1-based, default Axle 2 = Drive Axle)
const selectedAxleId = ref<number>(2)

// Pavement Type (read-only from road metadata): 'asphalt' (Boussinesq half-space) | 'concrete' (Westergaard rigid plate)
const selectedPavementType = computed<'asphalt' | 'concrete'>(() => {
  const p = store.selectedData?.properties || store.selectedFeature?.properties
  const roadTypeObj = p?.State?.RoadMetadata?.RoadType || p?.RoadStructureConfig?.RoadType
  const roadStructKey = p?.State?.RoadStructure || p?.RoadStructure || p?.road
  const cfgRoadType = roadStructKey ? store.digitalShadowRaw?.map_layers?.road_config?.[roadStructKey]?.RoadType : null
  const mat =
    p?.RoadMaterial ||
    p?.road_material ||
    p?.Material ||
    p?.material ||
    (roadTypeObj ? Object.keys(roadTypeObj)[0] : '') ||
    (cfgRoadType ? Object.keys(cfgRoadType)[0] : '')
  if (mat) {
    const s = String(mat).toLowerCase()
    if (s.includes('concrete') || s.includes('beton')) {
      return 'concrete'
    }
  }
  return 'asphalt'
})
const peakTensileBendingStress = ref<number>(0.0) // Concrete slab bottom tensile bending stress (MPa)
const radiusStiffnessL = ref<number>(0.90) // Concrete radius of relative stiffness ℓ (m)

// View Mode: 'side' (Longitudinal Side View of All Axles with Velocity Lag) | 'cross' (Transverse Dual-Wheel Cross-Section)
const viewMode = ref<'side' | 'cross'>('side')

// Field visualized: 'sigma_z' (Normal Stress, kPa) | 'w_z' (Deflection, mm) | 'tau_max' (Max Shear Stress, kPa)
const activeField = ref<'sigma_z' | 'w_z' | 'tau_max'>('sigma_z')

// Tire inflation pressure slider (User adjustable: 600 - 900 kPa / 6.0 - 9.0 bar)
const contactPressure = ref<number>(750.0)

// Visual toggles
const showIsobars = ref(true)
const showLayers = ref(true)
const showProfiles = ref(true)

// Reactive Kinematics & Multi-Axle extraction from live selected vehicle
const liveKinematicsPayload = computed(() => {
  const p = store.selectedData?.properties || store.selectedData || store.selectedFeature?.properties
  if (p?.KinematicAxles?.axles) {
    return p.KinematicAxles
  }
  // Generate calibrated fallback
  const vehClass = String(p?.VehicleClass || '5-Axle Semi-Trailer (40t)')
  const weight = Number(p?.Weight || 40000)
  const vel = Number(p?.Velocity ?? 86.5)
  const pos = Number(p?.Kilometer || 14.0)
  const slope = pos >= 4.0 && pos <= 24.0 ? 3.5 * Math.sin(((pos - 4.0) / 20.0) * Math.PI) : 0.0
  return generateCalibratedAxles(vehClass, weight, vel, slope, 0.05)
})

const currentAxles = computed<AxleModel[]>(() => {
  return liveKinematicsPayload.value?.axles || []
})

const kinematicsSummary = computed(() => {
  return liveKinematicsPayload.value?.summary || null
})

const selectedAxle = computed<AxleModel | null>(() => {
  return currentAxles.value.find((a) => a.id === selectedAxleId.value) || currentAxles.value[0] || null
})

// Axle load is strictly computed automatically from kinematics
const currentAxleLoadKn = computed<number>(() => {
  return selectedAxle.value?.p_dyn_kn || 100.0
})

// Tire configuration is strictly intrinsic to the selected axle
const currentTireConfig = computed<'dual' | 'single'>(() => {
  return selectedAxle.value?.type || 'dual'
})

const selectAxle = (id: number) => {
  selectedAxleId.value = id
}

const resetDefaults = () => {
  selectedAxleId.value = 2 // Drive axle
  contactPressure.value = 750.0
}

const activeLayers = computed(() => {
  return selectedPavementType.value === 'concrete' ? concreteLayers : asphaltLayers
})

// Characteristic viscoelastic relaxation distance L_lag = v * tau
const relaxationLagMeters = computed<number>(() => {
  const velKmh = kinematicsSummary.value?.velocity_kmh ?? 86.5
  const velMps = Math.max(0.0, velKmh / 3.6)
  const tauRelaxSec = 0.085 // 85 ms typical relaxation time for European asphalt mixes at 20°C
  return Number((velMps * tauRelaxSec).toFixed(2))
})

// ============================================================================
// PREALLOCATED COMPUTATIONAL BUFFERS (Transverse & Longitudinal)
// ============================================================================
let gridSigmaZ = new Float32Array(GRID_NX * GRID_NZ)
let gridWZ = new Float32Array(GRID_NX * GRID_NZ)
let gridTauMax = new Float32Array(GRID_NX * GRID_NZ)

let gridSideSigmaZ = new Float32Array(GRID_NY * GRID_NZ)
let gridSideWZ = new Float32Array(GRID_NY * GRID_NZ)
let gridSideTauMax = new Float32Array(GRID_NY * GRID_NZ)

const maxSurfaceDeflection = ref<number>(0.0)
const subgradeTopStress = ref<number>(0.0)
const peakShearStress = ref<number>(0.0)
const criticalShearDepth = ref<number>(0.07)

const computeActiveBoussinesq = () => {
  const isSide = viewMode.value === 'side'
  const outBuffers: FieldBuffers = isSide
    ? { sigmaZ: gridSideSigmaZ, wZ: gridSideWZ, tauMax: gridSideTauMax }
    : { sigmaZ: gridSigmaZ, wZ: gridWZ, tauMax: gridTauMax }

  const field = computePavementField(
    selectedPavementType.value,
    viewMode.value,
    {
      contactPressureKpa: contactPressure.value,
      axleLoadKn: currentAxleLoadKn.value,
      tireConfig: currentTireConfig.value,
      axles: currentAxles.value,
      relaxationLagM: relaxationLagMeters.value,
      velocityKmh: kinematicsSummary.value?.velocity_kmh ?? 86.5,
    },
    outBuffers
  )

  maxSurfaceDeflection.value = field.metrics.maxSurfaceDeflectionMm
  peakShearStress.value = field.metrics.peakShearStressKpa
  criticalShearDepth.value = field.metrics.criticalShearDepthCm
  subgradeTopStress.value = field.metrics.subgradeTopStressKpa
  if (selectedPavementType.value === 'concrete') {
    peakTensileBendingStress.value = field.metrics.peakTensileBendingStressMpa
    radiusStiffnessL.value = field.metrics.radiusStiffnessM
  }
}

// ============================================================================
// CANVAS RENDERING ENGINE (TURBO / SPECTRAL COLORMAP & CHASSIS PROFILE)
// ============================================================================
const canvasRef = ref<HTMLCanvasElement | null>(null)
const containerRef = ref<HTMLElement | null>(null)

const hoverCanvasPos = ref<{ x: number; y: number } | null>(null)
const hoverData = ref<{
  coordName: string
  coordVal: number
  z: number
  sigmaZ: number
  wZ: number
  tauMax: number
  layerName: string
} | null>(null)

const getColormapRGB = (t: number): [number, number, number] => {
  const clampT = Math.max(0.0, Math.min(1.0, t))
  let r = 0, g = 0, b = 0

  if (clampT < 0.25) {
    const f = clampT / 0.25
    r = Math.round(15 + 20 * f)
    g = Math.round(30 + 170 * f)
    b = Math.round(140 + 115 * f)
  } else if (clampT < 0.5) {
    const f = (clampT - 0.25) / 0.25
    r = Math.round(35 + 45 * f)
    g = Math.round(200 + 40 * f)
    b = Math.round(255 - 195 * f)
  } else if (clampT < 0.75) {
    const f = (clampT - 0.5) / 0.25
    r = Math.round(80 + 165 * f)
    g = Math.round(240 - 50 * f)
    b = Math.round(60 - 50 * f)
  } else {
    const f = (clampT - 0.75) / 0.25
    r = Math.round(245 + 10 * f)
    g = Math.round(190 - 150 * f)
    b = Math.round(10 + 20 * f)
  }
  return [r, g, b]
}

// Cached offscreen buffer for 60 FPS single-blit heatmap rendering
let offscreenCanvas: HTMLCanvasElement | null = null
let offscreenCtx: CanvasRenderingContext2D | null = null
let offscreenImgData: ImageData | null = null
let offscreenBuf32: Uint32Array | null = null
let currentOffscreenW = 0
let currentOffscreenH = 0

const getOffscreenBuffer = (w: number, h: number) => {
  if (typeof document === 'undefined') return { canvas: null, ctx: null, imgData: null, buf32: null }
  if (!offscreenCanvas) {
    offscreenCanvas = document.createElement('canvas')
  }
  if (currentOffscreenW !== w || currentOffscreenH !== h || !offscreenCtx || !offscreenImgData || !offscreenBuf32) {
    currentOffscreenW = w
    currentOffscreenH = h
    offscreenCanvas.width = w
    offscreenCanvas.height = h
    offscreenCtx = offscreenCanvas.getContext('2d')
    if (offscreenCtx) {
      offscreenImgData = offscreenCtx.createImageData(w, h)
      offscreenBuf32 = new Uint32Array(offscreenImgData.data.buffer)
    }
  }
  return { canvas: offscreenCanvas, ctx: offscreenCtx, imgData: offscreenImgData, buf32: offscreenBuf32 }
}

const renderCanvas = () => {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const rect = canvas.getBoundingClientRect()
  const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1
  const width = rect.width
  const height = rect.height

  canvas.width = width * dpr
  canvas.height = height * dpr
  ctx.scale(dpr, dpr)

  const isDark = store.theme === 'dark'
  const isSide = viewMode.value === 'side'
  const compact = isCompact.value

  // Adaptive Coordinate Margins
  const mTop = isSide ? (compact ? 70 : 78) : (compact ? 56 : 60)
  const mBottom = 24
  const mLeft = 34
  const mRight = isSide ? (compact ? 18 : 36) : (compact ? 18 : 36)
  const plotW = width - mLeft - mRight
  const plotH = height - mTop - mBottom

  // Background
  ctx.fillStyle = isDark ? '#0b1329' : '#f8fafc'
  ctx.fillRect(0, 0, width, height)

  const targetBuffer = isSide
    ? (activeField.value === 'w_z' ? gridSideWZ : activeField.value === 'tau_max' ? gridSideTauMax : gridSideSigmaZ)
    : (activeField.value === 'w_z' ? gridWZ : activeField.value === 'tau_max' ? gridTauMax : gridSigmaZ)

  let maxVal = contactPressure.value
  if (activeField.value === 'w_z') {
    maxVal = Math.max(0.01, maxSurfaceDeflection.value * 1.1)
  } else if (activeField.value === 'tau_max') {
    maxVal = Math.max(10.0, peakShearStress.value * 1.15)
  }

  const gridN1 = isSide ? GRID_NY : GRID_NX
  const cellW = plotW / (gridN1 - 1)
  const cellH = plotH / (GRID_NZ - 1)

  // 1. Draw Stress Heatmap Grid via GPU-Accelerated Pixel Buffer (Fast Single Put/Draw)
  const { canvas: offCanvas, ctx: offCtx, imgData, buf32 } = getOffscreenBuffer(gridN1, GRID_NZ)
  if (offCanvas && offCtx && imgData && buf32) {
    for (let iz = 0; iz < GRID_NZ; iz++) {
      const rowOffset = iz * gridN1
      for (let i1 = 0; i1 < gridN1; i1++) {
        const val = targetBuffer[rowOffset + i1]
        const norm = val / maxVal
        const [r, g, b] = getColormapRGB(norm)
        buf32[rowOffset + i1] = (255 << 24) | (b << 16) | (g << 8) | r
      }
    }
    offCtx.putImageData(imgData, 0, 0)
    ctx.imageSmoothingEnabled = true
    ctx.drawImage(offCanvas, 0, 0, gridN1, GRID_NZ, mLeft, mTop, plotW, plotH)
  }

  // 2. Draw Structural Layer Boundary Dashed Lines
  if (showLayers.value) {
    activeLayers.value.forEach((layer) => {
      const yNorm = layer.zBottom / Z_MAX
      if (yNorm <= 1.0) {
        const yPx = mTop + yNorm * plotH
        ctx.strokeStyle = isDark ? 'rgba(255,255,255,0.22)' : 'rgba(0,0,0,0.28)'
        ctx.lineWidth = 1
        ctx.setLineDash([4, 4])
        ctx.beginPath()
        ctx.moveTo(mLeft, yPx)
        ctx.lineTo(mLeft + plotW, yPx)
        ctx.stroke()
        ctx.setLineDash([])
      }
    })
  }

  // 3. Draw Isobar Contour Lines
  if (showIsobars.value) {
    ctx.strokeStyle = isDark ? 'rgba(255,255,255,0.30)' : 'rgba(0,0,0,0.35)'
    ctx.lineWidth = 1
    const levels = [0.15, 0.30, 0.50, 0.75]
    levels.forEach((lvl) => {
      ctx.beginPath()
      let started = false
      for (let i1 = 0; i1 < gridN1; i1++) {
        for (let iz = 0; iz < GRID_NZ - 1; iz++) {
          const v1 = targetBuffer[iz * gridN1 + i1] / maxVal
          const v2 = targetBuffer[(iz + 1) * gridN1 + i1] / maxVal
          if ((v1 >= lvl && v2 <= lvl) || (v1 <= lvl && v2 >= lvl)) {
            const frac = (lvl - v1) / (v2 - v1 || 0.001)
            const isoZ = iz + frac
            const xPx = mLeft + i1 * cellW
            const yPx = mTop + isoZ * cellH
            if (!started) {
              ctx.moveTo(xPx, yPx)
              started = true
            } else {
              ctx.lineTo(xPx, yPx)
            }
            break
          }
        }
      }
      ctx.stroke()
    })
  }

  // 4. Draw Structural Layer Badges (Thermal-Style Pill Badges with Color Dot & Backdrop)
  if (showLayers.value) {
    const badgeH = 15
    const minGap = 2
    const fontStr = 'bold 8.5px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
    ctx.font = fontStr

    // Calculate uniform badge width based on the widest label
    let maxTextW = 0
    activeLayers.value.forEach((l) => {
      const tw = ctx.measureText(l.shortName).width
      if (tw > maxTextW) maxTextW = tw
    })
    const badgeW = Math.ceil(maxTextW + 19) // 6px left pad + 5px dot + 4px gap + text + 4px right pad
    const badgeX = mLeft + plotW - badgeW - 4

    // Compute non-overlapping vertical positions
    const layerPositions = activeLayers.value.map((layer) => {
      const zMid = (layer.zTop + Math.min(layer.zBottom, Z_MAX)) / 2.0
      const idealY = mTop + (zMid / Z_MAX) * plotH
      return {
        layer,
        y: Math.max(mTop + badgeH / 2 + 2, Math.min(mTop + plotH - badgeH / 2 - 2, idealY))
      }
    })

    // Forward pass: resolve collisions downwards
    for (let i = 1; i < layerPositions.length; i++) {
      const prevY = layerPositions[i - 1].y
      if (layerPositions[i].y < prevY + badgeH + minGap) {
        layerPositions[i].y = prevY + badgeH + minGap
      }
    }

    // Backward pass: resolve collisions upwards if pushed beyond plot bottom
    if (layerPositions[layerPositions.length - 1].y > mTop + plotH - badgeH / 2 - 2) {
      layerPositions[layerPositions.length - 1].y = mTop + plotH - badgeH / 2 - 2
      for (let i = layerPositions.length - 2; i >= 0; i--) {
        if (layerPositions[i].y > layerPositions[i + 1].y - (badgeH + minGap)) {
          layerPositions[i].y = layerPositions[i + 1].y - (badgeH + minGap)
        }
      }
    }

    // Render each pill badge on top of heatmap and isobars
    layerPositions.forEach(({ layer, y: badgeCenterY }) => {
      const badgeY = Math.round(badgeCenterY - badgeH / 2)

      ctx.save()
      // Subtle drop shadow for depth
      ctx.shadowColor = 'rgba(0, 0, 0, 0.40)'
      ctx.shadowBlur = 4
      ctx.shadowOffsetX = 0
      ctx.shadowOffsetY = 1

      // Dark translucent pill background (matching ThermalSimulation pill style)
      ctx.fillStyle = isDark ? 'rgba(15, 23, 42, 0.88)' : 'rgba(15, 23, 42, 0.82)'
      ctx.beginPath()
      if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 3.5)
      } else {
        const r = 3.5
        ctx.moveTo(badgeX + r, badgeY)
        ctx.lineTo(badgeX + badgeW - r, badgeY)
        ctx.arcTo(badgeX + badgeW, badgeY, badgeX + badgeW, badgeY + r, r)
        ctx.lineTo(badgeX + badgeW, badgeY + badgeH - r)
        ctx.arcTo(badgeX + badgeW, badgeY + badgeH, badgeX + badgeW - r, badgeY + badgeH, r)
        ctx.lineTo(badgeX + r, badgeY + badgeH)
        ctx.arcTo(badgeX, badgeY + badgeH, badgeX, badgeY + r, r)
        ctx.lineTo(badgeX, badgeY + r)
        ctx.arcTo(badgeX, badgeY, badgeX + r, badgeY, r)
        ctx.closePath()
      }
      ctx.fill()

      // Reset shadow for crisp border and text
      ctx.shadowColor = 'transparent'

      // Subtle light border stroke
      ctx.strokeStyle = isDark ? 'rgba(255, 255, 255, 0.22)' : 'rgba(255, 255, 255, 0.28)'
      ctx.lineWidth = 1
      ctx.stroke()

      // Colored indicator dot matching layer type
      ctx.fillStyle = layer.color
      ctx.beginPath()
      const dotX = badgeX + 6.5
      const dotY = badgeY + badgeH / 2
      ctx.arc(dotX, dotY, 2.5, 0, Math.PI * 2)
      ctx.fill()

      // Crisp label text
      ctx.fillStyle = '#f8fafc'
      ctx.font = fontStr
      ctx.textAlign = 'left'
      ctx.textBaseline = 'middle'
      ctx.fillText(layer.shortName, badgeX + 13, badgeY + badgeH / 2)

      ctx.restore()
    })
  }

  // 4. Draw Geometry Header (Side View Chassis or Transverse Dual Wheels)
  if (isSide) {
    // ------------------------------------------------------------------------
    // LONGITUDINAL SIDE VIEW CHASSIS & WHEELS PROFILE (ADAPTIVE)
    // ------------------------------------------------------------------------
    const axles = currentAxles.value
    const positions = getAxleLongitudinalPositions(axles.length)

    // Road surface pavement top line
    ctx.strokeStyle = isDark ? '#64748b' : '#94a3b8'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(mLeft, mTop)
    ctx.lineTo(mLeft + plotW, mTop)
    ctx.stroke()

    // Draw Truck Silhouette Frame
    const rearAxleId = axles[axles.length - 1]?.id || 5
    const xMinPx = mLeft + ((positions[rearAxleId] - 0.8 - Y_MIN) / (Y_MAX - Y_MIN)) * plotW
    const xMaxPx = mLeft + ((positions[1] + 0.8 - Y_MIN) / (Y_MAX - Y_MIN)) * plotW
    const xDrivePx = mLeft + ((positions[2] - Y_MIN) / (Y_MAX - Y_MIN)) * plotW

    const trailerTop = mTop - (compact ? 36 : 42)
    const trailerH = compact ? 22 : 26
    const cabTop = mTop - (compact ? 40 : 46)
    const cabH = compact ? 26 : 30
    const yAxleNum = mTop - (compact ? 24 : 28)
    const yLoadText = mTop - (compact ? 52 : 58)

    // Trailer Box
    ctx.fillStyle = isDark ? 'rgba(30, 41, 59, 0.75)' : 'rgba(226, 232, 240, 0.85)'
    ctx.strokeStyle = isDark ? '#475569' : '#cbd5e1'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    if (typeof ctx.roundRect === 'function') {
      ctx.roundRect(xMinPx, trailerTop, Math.max(30, xDrivePx - xMinPx - 4), trailerH, [3, 3, 0, 0])
    } else {
      ctx.rect(xMinPx, trailerTop, Math.max(30, xDrivePx - xMinPx - 4), trailerH)
    }
    ctx.fill()
    ctx.stroke()

    // Tractor Cab
    ctx.fillStyle = isDark ? 'rgba(37, 99, 235, 0.25)' : 'rgba(37, 99, 235, 0.15)'
    ctx.strokeStyle = isDark ? '#3b82f6' : '#2563eb'
    ctx.beginPath()
    if (typeof ctx.roundRect === 'function') {
      ctx.roundRect(xDrivePx - 2, cabTop, xMaxPx - (xDrivePx - 2), cabH, [3, 8, 0, 0])
    } else {
      ctx.rect(xDrivePx - 2, cabTop, xMaxPx - (xDrivePx - 2), cabH)
    }
    ctx.fill()
    ctx.stroke()

    // Motion Vector Header Arrow (Right ->)
    const velKmh = kinematicsSummary.value?.velocity_kmh ?? 86.5
    ctx.fillStyle = velKmh > 0.1 ? (isDark ? '#38bdf8' : '#0284c7') : (isDark ? '#94a3b8' : '#64748b')
    ctx.font = 'bold 8.5px monospace'
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.fillText(velKmh > 0.1 ? `MOTION → ${velKmh} km/h` : 'STATIC (0 km/h)', mLeft + plotW, yLoadText)

    // Adaptive Wheel Sizing (Scaled so wheels NEVER collide even on 420px drawer)
    const wheelRadius = compact ? 8.5 : 11

    // Draw Wheels & Axle Loads
    axles.forEach((ax) => {
      const yPos = positions[ax.id] ?? 8.0
      const xPx = mLeft + ((yPos - Y_MIN) / (Y_MAX - Y_MIN)) * plotW
      const isSelected = selectedAxleId.value === ax.id

      // Wheel Tire Silhouette (resting right on road surface at mTop)
      ctx.fillStyle = isSelected ? (isDark ? '#38bdf8' : '#0284c7') : (isDark ? '#1e293b' : '#334155')
      ctx.strokeStyle = isSelected ? '#ef4444' : (isDark ? '#475569' : '#94a3b8')
      ctx.lineWidth = isSelected ? 2 : 1

      ctx.beginPath()
      ctx.arc(xPx, mTop - wheelRadius, wheelRadius, 0, Math.PI * 2)
      ctx.fill()
      ctx.stroke()

      // Rim Center Hub
      ctx.fillStyle = isSelected ? '#ffffff' : '#64748b'
      ctx.beginPath()
      ctx.arc(xPx, mTop - wheelRadius, compact ? 2.5 : 3.5, 0, Math.PI * 2)
      ctx.fill()

      // Axle Number Label (ALL ALIGNED horizontally inside vehicle body)
      ctx.fillStyle = isSelected ? '#ef4444' : (isDark ? '#e2e8f0' : '#1e293b')
      ctx.font = isSelected ? 'bold 9px monospace' : 'bold 8px monospace'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(`#${ax.id}`, xPx, yAxleNum)

      // Axle Load Text (Positioned cleanly ABOVE vehicle contour with zero overlap)
      if (!compact || isSelected) {
        ctx.font = isSelected ? 'bold 8.5px monospace' : '7.5px monospace'
        ctx.fillStyle = isSelected ? '#ef4444' : (isDark ? '#94a3b8' : '#64748b')
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(`${ax.p_dyn_kn} kN`, xPx, yLoadText)
      }

      // Downward load vector arrow
      ctx.strokeStyle = isSelected ? '#ef4444' : (isDark ? 'rgba(56, 189, 248, 0.4)' : 'rgba(2, 132, 199, 0.5)')
      ctx.lineWidth = isSelected ? 2 : 1
      ctx.beginPath()
      ctx.moveTo(xPx, mTop - 2)
      ctx.lineTo(xPx, mTop + 10)
      ctx.lineTo(xPx - 2.5, mTop + 7)
      ctx.moveTo(xPx, mTop + 10)
      ctx.lineTo(xPx + 2.5, mTop + 7)
      ctx.stroke()
    })
  } else {
    // ------------------------------------------------------------------------
    // TRANSVERSE FULL AXLE CROSS-SECTION (LEFT & RIGHT WHEEL ASSEMBLIES)
    // ------------------------------------------------------------------------
    const TRACK_HALF = 1.02
    const isDual = currentTireConfig.value === 'dual'
    const DUAL_HALF = 0.17
    const tireOffsets = isDual
      ? [-TRACK_HALF - DUAL_HALF, -TRACK_HALF + DUAL_HALF, TRACK_HALF - DUAL_HALF, TRACK_HALF + DUAL_HALF]
      : [-TRACK_HALF, TRACK_HALF]

    const xLeftWheelPx = mLeft + ((-TRACK_HALF - X_MIN) / (X_MAX - X_MIN)) * plotW
    const xRightWheelPx = mLeft + ((TRACK_HALF - X_MIN) / (X_MAX - X_MIN)) * plotW
    const xCenterLinePx = mLeft + ((0.0 - X_MIN) / (X_MAX - X_MIN)) * plotW
    const tireH = compact ? 22 : 25
    const wheelLoadKn = (currentAxleLoadKn.value / 2.0).toFixed(1)

    // 1. Axle Connecting Beam bridging Left and Right wheel assemblies
    ctx.fillStyle = isDark ? '#334155' : '#64748b'
    ctx.strokeStyle = isDark ? '#475569' : '#94a3b8'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    const axleBeamH = compact ? 5 : 6
    const axleBeamY = mTop - tireH / 2 - axleBeamH / 2
    if (typeof ctx.roundRect === 'function') {
      ctx.roundRect(xLeftWheelPx, axleBeamY, xRightWheelPx - xLeftWheelPx, axleBeamH, 2)
    } else {
      ctx.rect(xLeftWheelPx, axleBeamY, xRightWheelPx - xLeftWheelPx, axleBeamH)
    }
    ctx.fill()
    ctx.stroke()

    // Differential / Center Axle Housing at Lane Center
    ctx.fillStyle = isDark ? '#1e293b' : '#475569'
    ctx.strokeStyle = isDark ? '#475569' : '#cbd5e1'
    ctx.beginPath()
    ctx.arc(xCenterLinePx, mTop - tireH / 2, compact ? 5.5 : 7, 0, Math.PI * 2)
    ctx.fill()
    ctx.stroke()

    // 2. Draw All Tires (Left & Right Wheels)
    const tHalfW = (isDual ? 0.08 : 0.12) / (X_MAX - X_MIN) * plotW
    tireOffsets.forEach((tOffset) => {
      const tirePx = mLeft + ((tOffset - X_MIN) / (X_MAX - X_MIN)) * plotW

      // Tire Tread Box
      ctx.fillStyle = isDark ? '#1e293b' : '#334155'
      ctx.strokeStyle = '#38bdf8'
      ctx.lineWidth = 1.5
      ctx.beginPath()
      if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(tirePx - tHalfW, mTop - tireH, tHalfW * 2, tireH, [3, 3, 0, 0])
      } else {
        ctx.rect(tirePx - tHalfW, mTop - tireH, tHalfW * 2, tireH)
      }
      ctx.fill()
      ctx.stroke()

      // Tread grooves
      ctx.fillStyle = '#64748b'
      for (let g = -1; g <= 1; g++) {
        ctx.fillRect(tirePx + g * (tHalfW * 0.45) - 1, mTop - tireH + 2, 2, tireH - 4)
      }
    })

    // Wheel Hubs and Downward Load Vectors at Left and Right Wheel Centers
    ;[xLeftWheelPx, xRightWheelPx].forEach((wPx) => {
      // Wheel Hub
      ctx.fillStyle = '#ffffff'
      ctx.beginPath()
      ctx.arc(wPx, mTop - tireH / 2, compact ? 2.5 : 3.5, 0, Math.PI * 2)
      ctx.fill()

      // Downward Wheel Load Vector Arrow
      ctx.strokeStyle = '#ef4444'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(wPx, mTop - tireH - 5)
      ctx.lineTo(wPx, mTop - 2)
      ctx.lineTo(wPx - 3, mTop - 7)
      ctx.moveTo(wPx, mTop - 2)
      ctx.lineTo(wPx + 3, mTop - 7)
      ctx.stroke()

      // Wheel Load Label
      ctx.fillStyle = '#ef4444'
      ctx.font = 'bold 8px monospace'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'bottom'
      ctx.fillText(`${wheelLoadKn} kN`, wPx, mTop - tireH - 7)
    })

    // 3. Lane Centerline Visual Demarcation (Subtle dashed line)
    ctx.strokeStyle = isDark ? 'rgba(56, 189, 248, 0.22)' : 'rgba(2, 132, 199, 0.22)'
    ctx.lineWidth = 1
    ctx.setLineDash([3, 3])
    ctx.beginPath()
    ctx.moveTo(xCenterLinePx, mTop)
    ctx.lineTo(xCenterLinePx, mTop + plotH)
    ctx.stroke()
    ctx.setLineDash([])

    // 4. Axle Title Banner Header
    const bannerText = `${selectedAxle.value?.name || 'Axle'}: ${currentAxleLoadKn.value} kN (Track: 2.04m | 2x Wheel: ${wheelLoadKn} kN)`
    ctx.font = 'bold 9.5px monospace'
    const bannerW = ctx.measureText(bannerText).width + 20
    const bannerH = 20
    const bannerX = mLeft + (plotW - bannerW) / 2
    const bannerY = compact ? 6 : 10

    ctx.save()
    ctx.fillStyle = isDark ? 'rgba(15, 23, 42, 0.85)' : 'rgba(255, 255, 255, 0.90)'
    ctx.strokeStyle = isDark ? 'rgba(255, 255, 255, 0.18)' : 'rgba(0, 0, 0, 0.15)'
    ctx.lineWidth = 1
    ctx.beginPath()
    if (typeof ctx.roundRect === 'function') {
      ctx.roundRect(bannerX, bannerY, bannerW, bannerH, 4)
    } else {
      ctx.rect(bannerX, bannerY, bannerW, bannerH)
    }
    ctx.fill()
    ctx.stroke()

    ctx.fillStyle = isDark ? '#e2e8f0' : '#0f172a'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(bannerText, mLeft + plotW / 2, bannerY + bannerH / 2)
    ctx.restore()
  }

  // 5. Draw Grid Axes & Ticks
  ctx.strokeStyle = isDark ? '#334155' : '#cbd5e1'
  ctx.lineWidth = 1
  ctx.strokeRect(mLeft, mTop, plotW, plotH)

  // Depth (Z) Axis Ticks on Left
  ctx.fillStyle = isDark ? '#94a3b8' : '#64748b'
  ctx.font = '8.5px monospace'
  ctx.textAlign = 'right'
  const zTicks = [0.0, 0.25, 0.50, 0.75, 1.0, 1.25, 1.50]
  zTicks.forEach((zt) => {
    const yPx = mTop + (zt / Z_MAX) * plotH
    ctx.fillText(`${zt.toFixed(2)}m`, mLeft - 3, yPx + 3)
    ctx.beginPath()
    ctx.moveTo(mLeft - 2, yPx)
    ctx.lineTo(mLeft, yPx)
    ctx.stroke()
  })

  // Horizontal Ticks on Bottom
  ctx.textAlign = 'center'
  if (isSide) {
    const yTicks = [0, 2, 4, 6, 8, 10, 12, 14, 16]
    yTicks.forEach((yt) => {
      const xPx = mLeft + ((yt - Y_MIN) / (Y_MAX - Y_MIN)) * plotW
      ctx.fillText(`${yt}m`, xPx, mTop + plotH + 14)
      ctx.beginPath()
      ctx.moveTo(xPx, mTop + plotH)
      ctx.lineTo(xPx, mTop + plotH + 3)
      ctx.stroke()
    })
  } else {
    const xTicks = [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0]
    xTicks.forEach((xt) => {
      const xPx = mLeft + ((xt - X_MIN) / (X_MAX - X_MIN)) * plotW
      ctx.fillText(`${xt > 0 ? '+' : ''}${xt.toFixed(1)}m`, xPx, mTop + plotH + 14)
      ctx.beginPath()
      ctx.moveTo(xPx, mTop + plotH)
      ctx.lineTo(xPx, mTop + plotH + 3)
      ctx.stroke()
    })
  }

  // 6. Draw Hover Probing Crosshairs
  if (hoverCanvasPos.value) {
    const { x: hx, y: hy } = hoverCanvasPos.value
    if (hx >= mLeft && hx <= mLeft + plotW && hy >= mTop && hy <= mTop + plotH) {
      ctx.strokeStyle = isDark ? '#38bdf8' : '#0284c7'
      ctx.lineWidth = 1
      ctx.setLineDash([3, 3])

      ctx.beginPath()
      ctx.moveTo(mLeft, hy)
      ctx.lineTo(mLeft + plotW, hy)
      ctx.stroke()

      ctx.beginPath()
      ctx.moveTo(hx, mTop)
      ctx.lineTo(hx, mTop + plotH)
      ctx.stroke()

      ctx.setLineDash([])

      ctx.fillStyle = '#ef4444'
      ctx.beginPath()
      ctx.arc(hx, hy, 3, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}

const handleCanvasClick = (event: MouseEvent) => {
  if (viewMode.value !== 'side') return
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mouseX = event.clientX - rect.left

  const isSide = viewMode.value === 'side'
  const compact = isCompact.value
  const mLeft = 34
  const mRight = isSide ? (compact ? 18 : 36) : (compact ? 18 : 36)
  const plotW = rect.width - mLeft - mRight
  const positions = getAxleLongitudinalPositions(currentAxles.value.length)

  // Find nearest axle to mouse click
  let closestId = selectedAxleId.value
  let minDistPx = 9999

  currentAxles.value.forEach((ax) => {
    const yPos = positions[ax.id] ?? 8.0
    const xPx = mLeft + ((yPos - Y_MIN) / (Y_MAX - Y_MIN)) * plotW
    const dist = Math.abs(mouseX - xPx)
    if (dist < minDistPx) {
      minDistPx = dist
      closestId = ax.id
    }
  })

  if (minDistPx < 40) {
    selectAxle(closestId)
  }
}

const handleMouseMove = (event: MouseEvent) => {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mouseX = event.clientX - rect.left
  const mouseY = event.clientY - rect.top

  const isSide = viewMode.value === 'side'
  const compact = isCompact.value
  const mTop = isSide ? (compact ? 70 : 78) : (compact ? 56 : 60)
  const mBottom = 24
  const mLeft = 34
  const mRight = isSide ? (compact ? 18 : 36) : (compact ? 18 : 36)
  const plotW = rect.width - mLeft - mRight
  const plotH = rect.height - mTop - mBottom

  if (mouseX >= mLeft && mouseX <= mLeft + plotW && mouseY >= mTop && mouseY <= mTop + plotH) {
    const normH = (mouseX - mLeft) / plotW
    const normZ = (mouseY - mTop) / plotH
    const zVal = Z_MIN + normZ * (Z_MAX - Z_MIN)

    const layer = activeLayers.value.find((l) => zVal >= l.zTop && zVal <= l.zBottom) || activeLayers.value[activeLayers.value.length - 1]

    if (isSide) {
      const yVal = Y_MIN + normH * (Y_MAX - Y_MIN)
      const iy = Math.min(GRID_NY - 1, Math.max(0, Math.round(normH * (GRID_NY - 1))))
      const iz = Math.min(GRID_NZ - 1, Math.max(0, Math.round(normZ * (GRID_NZ - 1))))
      const idx = iz * GRID_NY + iy

      hoverCanvasPos.value = { x: mouseX, y: mouseY }
      hoverData.value = {
        coordName: 'Station Y',
        coordVal: Number(yVal.toFixed(2)),
        z: Number(zVal.toFixed(2)),
        sigmaZ: Number(gridSideSigmaZ[idx].toFixed(1)),
        wZ: Number(gridSideWZ[idx].toFixed(3)),
        tauMax: Number(gridSideTauMax[idx].toFixed(1)),
        layerName: layer.name
      }
    } else {
      const xVal = X_MIN + normH * (X_MAX - X_MIN)
      const ix = Math.min(GRID_NX - 1, Math.max(0, Math.round(normH * (GRID_NX - 1))))
      const iz = Math.min(GRID_NZ - 1, Math.max(0, Math.round(normZ * (GRID_NZ - 1))))
      const idx = iz * GRID_NX + ix

      hoverCanvasPos.value = { x: mouseX, y: mouseY }
      hoverData.value = {
        coordName: 'Offset X',
        coordVal: Number(xVal.toFixed(2)),
        z: Number(zVal.toFixed(2)),
        sigmaZ: Number(gridSigmaZ[idx].toFixed(1)),
        wZ: Number(gridWZ[idx].toFixed(3)),
        tauMax: Number(gridTauMax[idx].toFixed(1)),
        layerName: layer.name
      }
    }
  } else {
    hoverCanvasPos.value = null
    hoverData.value = null
  }
  renderCanvas()
}

const handleMouseLeave = () => {
  hoverCanvasPos.value = null
  hoverData.value = null
  renderCanvas()
}

watch(
  [selectedPavementType, viewMode, activeField, contactPressure, selectedAxleId, showIsobars, showLayers, () => store.theme, () => liveKinematicsPayload.value, () => props.drawerWidth],
  () => {
    computeActiveBoussinesq()
    nextTick(() => {
      renderCanvas()
    })
  },
  { deep: true }
)

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  computeActiveBoussinesq()
  nextTick(() => {
    renderCanvas()
  })

  if (typeof ResizeObserver !== 'undefined' && containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      renderCanvas()
    })
    resizeObserver.observe(containerRef.value)
  }
})

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})
</script>

<template>
  <div ref="containerRef" class="w-full flex flex-col space-y-3">
    
    <!-- Top Section Header (matches DashboardView secondary tabs) -->
    <div class="flex items-center justify-between pb-2 border-b"
         :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
      <div>
        <h4 class="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-100">
          2D Pavement Cross-Section
        </h4>
        <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
          {{ selectedPavementType === 'concrete' ? 'Westergaard (1926) rigid plate on Winkler springs with slab bending tension.' : 'Analytical Boussinesq elastostatic load & stress engine with viscoelastic velocity lag.' }}
        </p>
      </div>
    </div>

    <!-- Solver Model & Reset Utility Bar -->
    <div class="flex items-center justify-between gap-2 p-1.5 rounded-lg border shrink-0 text-xs shadow-xs flex-wrap"
         :class="store.theme === 'dark' ? 'bg-slate-900/60 border-white/10' : 'bg-slate-100/80 border-slate-200/80'">
      <div class="flex items-center gap-2 min-w-0 flex-wrap">
        <span class="text-[10px] font-bold text-slate-400 px-1.5 uppercase tracking-wider shrink-0">Solver Model</span>
        <span class="px-2 py-0.5 rounded-md border text-[10px] font-bold whitespace-nowrap shrink-0"
              :class="selectedPavementType === 'concrete'
                ? (store.theme === 'dark' ? 'bg-slate-950/60 border-sky-400/30 text-sky-300' : 'bg-white border-[#00305E]/25 text-[#00305E]')
                : (store.theme === 'dark' ? 'bg-slate-950/60 border-amber-500/30 text-amber-400' : 'bg-amber-50 border-amber-200 text-amber-700')">
          {{ selectedPavementType === 'concrete' ? 'RStO 12 Concrete — Westergaard' : 'RStO 12 Asphalt — Boussinesq' }}
        </span>
      </div>

      <button @click="resetDefaults"
              class="flex items-center gap-1 px-2.5 py-1 rounded-md text-[10.5px] font-semibold border transition-colors cursor-pointer shrink-0"
              :class="store.theme === 'dark' ? 'bg-slate-800 border-white/10 text-slate-300 hover:bg-slate-700' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'"
              title="Reset parameters to vehicle baseline">
        <RotateCcw :size="11" />
        <span>Reset</span>
      </button>
    </div>

    <!-- 1. INTERACTIVE CHASSIS MULTI-AXLE SELECTOR RIBBON -->
    <div class="flex flex-col gap-2 p-3 rounded-lg border shadow-xs"
         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
      
      <!-- Ribbon Header: Axle Identification & Automatic Kinematics Indicator -->
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <div class="flex items-center gap-2">
          <span class="text-[11px] font-bold uppercase tracking-wider text-slate-400">Axle Selection:</span>
          <span class="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded"
                :class="selectedAxle?.is_drive ? 'bg-amber-500/15 text-amber-500 border border-amber-500/25' : 'bg-slate-500/10 text-slate-400'">
            {{ selectedAxle?.is_drive ? 'Drive Axle (Critical Rutting)' : selectedAxle?.is_steer ? 'Front Steer Axle' : 'Trailer Axle' }}
          </span>
        </div>

        <div class="flex items-center gap-1.5 text-[10px] font-mono text-slate-500 dark:text-slate-400 shrink-0">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
          <span>Automatic Kinematics</span>
        </div>
      </div>

      <!-- Horizontal Axle Cards (ADAPTIVE: Scrollable strip when compact, responsive grid matching axle count when wide) -->
      <div class="flex gap-1.5 pt-0.5 pb-1 overflow-x-auto scrollbar-thin"
           :class="isCompact ? 'flex-nowrap' : (currentAxles.length >= 6 ? 'grid grid-cols-3 sm:grid-cols-6' : currentAxles.length === 4 ? 'grid grid-cols-2 sm:grid-cols-4' : 'grid grid-cols-2 sm:grid-cols-5')">
        <button v-for="axle in currentAxles" :key="axle.id"
                @click="selectAxle(axle.id)"
                class="flex flex-col p-1.5 rounded-md border text-left transition-all cursor-pointer relative shrink-0"
                :class="[
                  isCompact ? 'w-[108px]' : '',
                  selectedAxleId === axle.id
                    ? 'bg-[#00305E]/5 dark:bg-[#00305E]/40 border-[#00305E] dark:border-sky-400 ring-1 ring-[#00305E]/20 text-[#00305E] dark:text-sky-200 shadow-xs'
                    : 'border-slate-200 dark:border-white/5 hover:border-slate-400 dark:hover:border-white/20 text-slate-700 dark:text-slate-300 bg-slate-50/50 dark:bg-slate-950/30'
                ]">
          
          <div class="flex items-center justify-between text-[10px] font-bold">
            <span class="truncate">Axle #{{ axle.id }}</span>
            <span class="text-[9px] font-mono uppercase tracking-tight shrink-0"
                  :class="axle.type === 'dual' ? 'text-[#00305E] dark:text-sky-300 font-semibold' : 'text-slate-400'">
              {{ axle.type === 'dual' ? 'Dual' : 'Single' }}
            </span>
          </div>

          <!-- Mini Axle Shaft & Wheels Silhouette -->
          <div class="my-1.5 flex items-center justify-center gap-1 h-4 bg-slate-200/50 dark:bg-slate-900 rounded px-1">
            <div class="flex gap-0.5">
              <div class="w-1.5 h-3 rounded-xs" :class="selectedAxleId === axle.id ? 'bg-[#00305E] dark:bg-sky-400' : 'bg-slate-400 dark:bg-slate-600'"></div>
              <div v-if="axle.type === 'dual'" class="w-1.5 h-3 rounded-xs" :class="selectedAxleId === axle.id ? 'bg-[#00305E] dark:bg-sky-400' : 'bg-slate-400 dark:bg-slate-600'"></div>
            </div>
            <div class="flex-1 h-0.5 bg-slate-300 dark:bg-slate-700"></div>
            <div class="flex gap-0.5">
              <div v-if="axle.type === 'dual'" class="w-1.5 h-3 rounded-xs" :class="selectedAxleId === axle.id ? 'bg-[#00305E] dark:bg-sky-400' : 'bg-slate-400 dark:bg-slate-600'"></div>
              <div class="w-1.5 h-3 rounded-xs" :class="selectedAxleId === axle.id ? 'bg-[#00305E] dark:bg-sky-400' : 'bg-slate-400 dark:bg-slate-600'"></div>
            </div>
          </div>

          <!-- Dynamic Axle Load Display (Computed automatically) -->
          <div class="flex items-baseline justify-between text-[11px] font-mono font-extrabold">
            <span>{{ axle.p_dyn_kn }} <span class="text-[9px] font-normal text-slate-400">kN</span></span>
            <span v-if="axle.dif !== 1" class="text-[9px]"
                  :class="axle.dif > 1 ? 'text-amber-500' : 'text-emerald-500'">
              {{ axle.dif > 1 ? '+' : '' }}{{ ((axle.dif - 1) * 100).toFixed(1) }}%
            </span>
          </div>

          <div class="text-[9px] text-slate-400 truncate mt-0.5">
            {{ axle.name.split('(')[1]?.replace(')', '') || axle.name }}
          </div>
        </button>
      </div>

      <!-- Live 5s Kinematics Telemetry Ribbon -->
      <div v-if="kinematicsSummary"
           class="flex flex-wrap items-center justify-between gap-2 px-2.5 py-1.5 rounded-md border text-[10px]"
           :class="store.theme === 'dark' ? 'bg-slate-950/50 border-white/5' : 'bg-slate-100/70 border-slate-200'">
        <div class="flex items-center gap-1.5">
          <Activity :size="12" class="text-emerald-500 shrink-0" />
          <span class="font-bold text-slate-700 dark:text-slate-300">5s Loop Kinematics:</span>
          <span class="font-mono text-emerald-600 dark:text-emerald-400 font-bold">{{ kinematicsSummary.velocity_kmh }} km/h</span>
        </div>
        <div class="flex items-center gap-2.5 text-slate-500 dark:text-slate-400 font-mono flex-wrap">
          <span>Accel: <b class="text-slate-700 dark:text-slate-200">{{ kinematicsSummary.accel_mps2 > 0 ? '+' : '' }}{{ kinematicsSummary.accel_mps2 }} m/s²</b></span>
          <span>Grade: <b :class="kinematicsSummary.slope_pct > 0 ? 'text-amber-500' : 'text-slate-600 dark:text-slate-300'">{{ kinematicsSummary.slope_pct > 0 ? '+' : '' }}{{ kinematicsSummary.slope_pct }}%</b></span>
          <span>DLC: <b class="text-[#00305E] dark:text-sky-400">+{{ (kinematicsSummary.dlc * 100).toFixed(1) }}%</b></span>
          <span>Damage: <b class="text-rose-500">{{ selectedAxle?.damage_factor }}x ESAL</b></span>
        </div>
      </div>
    </div>

    <!-- 2. PARAMETER TOOLBAR: RESPONSIVE TWO-ROW LAYOUT (Prevents Any Squeezing) -->
    <div class="p-3 rounded-lg border text-xs flex flex-col gap-2.5 shadow-xs"
         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
      
      <!-- Row 1: Projection View & Visualized Field (2 Columns) -->
      <div class="grid gap-2.5" :class="isVeryCompact ? 'grid-cols-1' : 'grid-cols-2'">
        
        <!-- Control 1: View Mode -->
        <div class="flex flex-col gap-1">
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Projection View</span>
          <div class="flex items-center p-0.5 rounded-md border bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-white/5">
            <button @click="viewMode = 'side'"
                    class="flex-1 py-1 px-1.5 rounded font-semibold transition-all cursor-pointer flex items-center justify-center gap-1 text-[11px] truncate"
                    :class="viewMode === 'side'
                      ? 'bg-[#00305E] text-white shadow-xs'
                      : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
              <Truck :size="12" class="shrink-0" />
              <span class="truncate">Side (All Axles)</span>
            </button>
            <button @click="viewMode = 'cross'"
                    class="flex-1 py-1 px-1.5 rounded font-semibold transition-all cursor-pointer flex items-center justify-center gap-1 text-[11px] truncate"
                    :class="viewMode === 'cross'
                      ? 'bg-[#00305E] text-white shadow-xs'
                      : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
              <Layers :size="12" class="shrink-0" />
              <span class="truncate">Cross-Section</span>
            </button>
          </div>
        </div>

        <!-- Control 2: Field Selector -->
        <div class="flex flex-col gap-1">
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Visualized Field</span>
          <div class="flex items-center p-0.5 rounded-md border bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-white/5">
            <button @click="activeField = 'sigma_z'"
                    class="flex-1 py-1 px-1 rounded font-semibold transition-all cursor-pointer text-center truncate text-[11px]"
                    :class="activeField === 'sigma_z'
                      ? 'bg-white dark:bg-slate-700 text-purple-600 dark:text-purple-400 shadow-sm'
                      : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
              σz (Normal)
            </button>
            <button @click="activeField = 'w_z'"
                    class="flex-1 py-1 px-1 rounded font-semibold transition-all cursor-pointer text-center truncate text-[11px]"
                    :class="activeField === 'w_z'
                      ? 'bg-white dark:bg-slate-700 text-emerald-600 dark:text-emerald-400 shadow-sm'
                      : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
              wz (Deflect)
            </button>
            <button @click="activeField = 'tau_max'"
                    class="flex-1 py-1 px-1 rounded font-semibold transition-all cursor-pointer text-center truncate text-[11px]"
                    :class="activeField === 'tau_max'
                      ? 'bg-white dark:bg-slate-700 text-amber-600 dark:text-amber-400 shadow-sm'
                      : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
              τmax (Shear)
            </button>
          </div>
        </div>
      </div>

      <!-- Row 2: Tire Inflation Pressure Slider (Full Width) -->
      <div class="flex flex-col gap-1 pt-1.5 border-t border-slate-100 dark:border-white/5">
        <div class="flex items-center justify-between text-[11px]">
          <span class="text-slate-500 dark:text-slate-400 font-medium">Tire Inflation Pressure:</span>
          <span class="font-mono font-bold text-slate-800 dark:text-slate-100">{{ contactPressure }} kPa ({{ (contactPressure / 100).toFixed(1) }} bar)</span>
        </div>
        <input type="range" min="600" max="900" step="10" v-model.number="contactPressure"
               class="w-full accent-[#00305E] cursor-pointer h-1.5 bg-slate-200 dark:bg-slate-700 rounded-lg" />
        <div class="flex justify-between text-[9px] font-mono text-slate-400">
          <span>6.0 bar</span>
          <span>Footprint Radius: {{ selectedAxle?.contact_radius_cm || 11.6 }} cm</span>
          <span>9.0 bar</span>
        </div>
      </div>

    </div>

    <!-- 3. VISCOELASTIC VELOCITY MEMORY BANNER (Side View Mode) -->
    <div v-if="viewMode === 'side'"
         class="flex items-center justify-between px-3 py-1.5 rounded-md border text-[10px]"
         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-slate-200' : 'bg-slate-50 border-slate-200 text-slate-800'">
      <div class="flex items-center gap-1.5 flex-wrap">
        <span class="font-bold uppercase tracking-wider text-[9px] text-[#00305E] dark:text-sky-400 shrink-0">Velocity Lag:</span>
        <span class="font-mono font-bold shrink-0">L_lag = {{ relaxationLagMeters }} m</span>
        <span class="text-slate-400 shrink-0">(@ {{ kinematicsSummary?.velocity_kmh ?? 86.5 }} km/h, τ = 85 ms)</span>
      </div>
      <span v-if="!isCompact" class="text-[9px] text-slate-400 shrink-0 hidden md:inline">
        Stress decays gradually behind rolling wheels; tridems superimpose.
      </span>
    </div>

    <!-- 4. MAIN INTERACTIVE CANVAS WRAPPER -->
    <div class="relative w-full rounded-lg border overflow-hidden shadow-sm"
         :class="store.theme === 'dark' ? 'bg-slate-950 border-white/10' : 'bg-slate-50 border-slate-200'">
      
      <!-- HTML5 Hardware-Accelerated 60 FPS Canvas -->
      <canvas ref="canvasRef"
              @mousemove="handleMouseMove"
              @mouseleave="handleMouseLeave"
              @click="handleCanvasClick"
              class="w-full block cursor-crosshair"
              :class="isCompact ? 'h-[350px]' : 'h-[385px]'"></canvas>

      <!-- Colorbar Legend at Bottom (Positioned cleanly inside plot, above X-axis tick labels) -->
      <div class="absolute left-10 bottom-[32px] flex items-center gap-2 bg-black/65 backdrop-blur-xs px-2.5 py-1 rounded-md text-[10px] text-white pointer-events-none shadow-sm">
        <span class="font-mono">0.0</span>
        <div class="w-20 sm:w-24 h-2 rounded-sm bg-gradient-to-r from-blue-600 via-green-400 via-yellow-400 to-red-600 border border-white/20"></div>
        <span class="font-mono">
          {{ activeField === 'sigma_z' ? contactPressure + ' kPa' : activeField === 'w_z' ? maxSurfaceDeflection + ' mm' : peakShearStress + ' kPa' }}
        </span>
      </div>

      <!-- Floating Tooltip on Hover Probing -->
      <div v-if="hoverData"
           class="absolute top-2 left-2 pointer-events-none bg-slate-900/90 text-white p-2 rounded-md border border-white/10 shadow-lg text-[11px] backdrop-blur-xs flex flex-col gap-0.5 z-10">
        <div class="font-bold text-sky-400">{{ hoverData.layerName }}</div>
        <div class="flex items-center gap-3 text-slate-300 font-mono text-[10px]">
          <span>{{ hoverData.coordName }}: {{ hoverData.coordVal > 0 ? '+' : '' }}{{ hoverData.coordVal }}m</span>
          <span>Depth z: {{ hoverData.z }}m</span>
        </div>
        <div class="border-t border-white/10 pt-1 mt-0.5 flex flex-col gap-0.5 text-[10px]">
          <div><span class="text-slate-400">Vertical Stress σz:</span> <span class="font-bold text-purple-300 font-mono">{{ hoverData.sigmaZ }} kPa</span></div>
          <div><span class="text-slate-400">Deflection wz:</span> <span class="font-bold text-emerald-300 font-mono">{{ hoverData.wZ }} mm</span></div>
          <div><span class="text-slate-400">Max Shear τmax:</span> <span class="font-bold text-amber-300 font-mono">{{ hoverData.tauMax }} kPa</span></div>
        </div>
      </div>
    </div>

    <!-- 5. VISUAL CONTROLS & SUBGRADE PROBE SUMMARY -->
    <div class="flex flex-col gap-2.5 pt-1">
      <div class="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 px-1 flex-wrap gap-2">
        <div class="flex items-center gap-3">
          <label class="flex items-center gap-1.5 cursor-pointer select-none">
            <input type="checkbox" v-model="showIsobars" class="accent-[#00305E] rounded" />
            <span class="text-[11px]">Isobars</span>
          </label>
          <label class="flex items-center gap-1.5 cursor-pointer select-none">
            <input type="checkbox" v-model="showLayers" class="accent-[#00305E] rounded" />
            <span class="text-[11px]">Layers</span>
          </label>
        </div>
        <button @click="showProfiles = !showProfiles"
                class="flex items-center gap-1 text-[11px] font-semibold text-[#00305E] dark:text-sky-400 hover:underline cursor-pointer">
          <span>{{ showProfiles ? 'Hide Analytical Summary' : 'Show Analytical Summary' }}</span>
          <ChevronUp v-if="showProfiles" :size="12" />
          <ChevronDown v-else :size="12" />
        </button>
      </div>

      <!-- Critical Structural Peak Badges (Responsive Stack) -->
      <div v-show="showProfiles"
           class="grid gap-2 p-2.5 rounded-lg border text-xs"
           :class="[
             isCompact ? 'grid-cols-1' : 'grid-cols-2',
             store.theme === 'dark' ? 'bg-slate-900/60 border-white/5' : 'bg-slate-50 border-slate-200'
           ]">
        <div class="flex flex-col gap-0.5">
          <div class="flex items-center justify-between">
            <span class="text-[11px] text-slate-400">
              {{ selectedPavementType === 'concrete' ? 'Concrete Slab Deflection w(x)' : 'Surface Deflection Basin w(x)' }}
            </span>
            <span class="font-mono font-bold text-emerald-500">Peak: {{ maxSurfaceDeflection }} mm</span>
          </div>
          <p class="text-[10px] text-slate-500">
            {{ selectedPavementType === 'concrete' ? 'Rigid plate deflection basin on Winkler spring foundation (k=80 MPa/m).' : 'Simulated Falling Weight Deflectometer (FWD) basin at pavement surface.' }}
          </p>
        </div>

        <div class="flex flex-col gap-0.5" :class="isCompact ? 'border-t pt-1.5 border-slate-200 dark:border-white/5' : 'border-l pl-2.5 border-slate-200 dark:border-white/5'">
          <div class="flex items-center justify-between">
            <span class="text-[11px] text-slate-400">
              {{ selectedPavementType === 'concrete' ? 'Slab Bottom Flexural Tension' : 'Vertical Stress at Subgrade' }}
            </span>
            <span class="font-mono font-bold" :class="selectedPavementType === 'concrete' ? 'text-rose-400' : 'text-purple-400'">
              {{ selectedPavementType === 'concrete' ? peakTensileBendingStress + ' MPa' : subgradeTopStress + ' kPa' }}
            </span>
          </div>
          <p class="text-[10px] text-slate-500">
            {{ selectedPavementType === 'concrete' ? 'Westergaard interior bending stress (radius of relative stiffness ℓ = ' + radiusStiffnessL + ' m).' : 'Stress bulb dispersion through depth along axle centerline.' }}
          </p>
        </div>
      </div>
    </div>

  </div>
</template>
