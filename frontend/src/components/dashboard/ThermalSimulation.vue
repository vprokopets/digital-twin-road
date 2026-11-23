<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { useDashboardStore } from '../../stores/dashboard'
import {
  Thermometer,
  Layers,
  Activity,
  Flame,
  Sun,
  Eye,
  BarChart2
} from 'lucide-vue-next'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js'
import { Line } from 'vue-chartjs'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

const store = useDashboardStore()

const props = withDefaults(defineProps<{
  drawerWidth?: number
}>(), {
  drawerWidth: 460
})

// View mode: 'profile' (2D Heatmap), 'chart' (1D Time Series), 'dual' (both)
const viewMode = ref<'profile' | 'chart' | 'dual'>('profile')

// Chart states
const chartData = ref({
  labels: [] as any[],
  datasets: [] as any[]
})
const chartOptions = ref<any>({})

// 2D Pavement Cross-Section States
interface PavementLayer {
  id: string
  name: string
  subname: string
  thicknessM: number
  thicknessCm: number
  depthTopCm: number
  depthBottomCm: number
  conductivity: number     // W/(m·K)
  rValue: number           // m²·K/W
  femConductance: number   // k/h [W/(m²·K)]
  heatCapacity: number     // c_p [J/(kg·K)]
  density: number          // ρ [kg/m³]
  diffusivityMm2s: number  // α = k / (ρ·c_p) × 10^6 [mm²/s]
  isSubgrade?: boolean
  tempTop: number          // °C
  tempBottom: number       // °C
  colorTop: string
  colorBottom: string
  patternType: 'dense' | 'medium' | 'coarse' | 'gravel' | 'soil'
  visualHeightPct: number
  visualTopPct: number
  visualBottomPct: number
}

const surfaceTemp = ref(32.5)
const airTemp = ref(25.0)
const subgradeSoilTemp = ref(14.5)
const heatFlux = ref(34.2) // W/m²
const totalResistance = ref(0.53) // m²·K/W
const pavementOnlyResistance = ref(0.21) // m²·K/W
const totalPavementDepthCm = ref(100)
const isConcretePavement = ref(false)
const pavementLayers = ref<PavementLayer[]>([])
const activeStructureId = ref('')
const activeStandard = ref('')
const activeLoadClass = ref('')
const activeWeatherState = ref('Cloudy')
const femNodalTemps = ref<number[]>([])
const solarFluxWm2 = computed(() => (activeWeatherState.value.toLowerCase() === 'sunny' ? 10.0 : 0.0))

// Interactive Depth Cursor Probe
const hoveredLayerId = ref<string | null>(null)
const activeProbe = ref<{
  depthCm: number
  yPct: number
  temp: number
  layer: PavementLayer | null
  heatFlux: number
} | null>(null)

// Temperature to Color interpolation
const getTemperatureColor = (t: number) => {
  if (t >= 32) return '#ef4444' // Crimson Red
  if (t >= 28) return '#f97316' // Warm Orange
  if (t >= 24) return '#eab308' // Amber Gold
  if (t >= 20) return '#10b981' // Emerald Green
  if (t >= 17) return '#06b6d4' // Cyan Teal
  return '#3b82f6'             // Deep Cool Blue
}

const updateThermalSimulation = async () => {
  if (!store.selectedData) return

  const stats = store.selectedData.stats || {}
  const panel = store.selectedData.panel || {}
  let timestamps = Array.isArray(stats['Timestamp']) ? stats['Timestamp'] : []

  let roadSurfaceTempLog = Array.isArray(stats['RoadSurfaceTemperature'])
    ? stats['RoadSurfaceTemperature']
    : (Array.isArray(stats['AirTemperature']) ? stats['AirTemperature'] : [])
  let airTempLog = Array.isArray(stats['AirTemperature']) ? stats['AirTemperature'] : []
  let soilTempLog = Array.isArray(stats['SoilTemperature']) ? stats['SoilTemperature'] : []
  const roadStructureLog = Array.isArray(stats['RoadStructure']) ? stats['RoadStructure'] : []

  // Fallback for Road Segment selection: derive boundary temperatures from nearest RSU & Hydrology
  if (!timestamps.length && panel.panel_type === 'road_segment') {
    const rsuSurfT = Number(panel.nearest_rsu?.road_temperature ?? 24.5)
    const rsuAirT = Number(panel.nearest_rsu?.air_temperature ?? 20.0)
    const waterCool = Number(panel.nearest_water?.cooling_effect_c ?? 0.0)
    const baseSoilT = 15.0 + waterCool
    timestamps = ['T-20s', 'T-15s', 'T-10s', 'T-5s', 'Now']
    roadSurfaceTempLog = [rsuSurfT - 0.3, rsuSurfT - 0.2, rsuSurfT - 0.1, rsuSurfT, rsuSurfT]
    airTempLog = [rsuAirT, rsuAirT, rsuAirT, rsuAirT, rsuAirT]
    soilTempLog = [baseSoilT, baseSoilT, baseSoilT, baseSoilT, baseSoilT]
  }

  if (!timestamps.length) return

  // Extract latest boundary temperatures
  const sT = Number(roadSurfaceTempLog[roadSurfaceTempLog.length - 1] ?? 32.5)
  const aT = Number(airTempLog[airTempLog.length - 1] ?? 25.0)
  const bT = Number(soilTempLog[soilTempLog.length - 1] ?? 14.5)

  surfaceTemp.value = sT
  airTemp.value = aT
  subgradeSoilTemp.value = bT

  // Get active road structure configuration from digital shadow
  const props = store.selectedData?.properties || store.selectedFeature?.properties || {}
  const roadStructureName =
    (roadStructureLog.length ? roadStructureLog[roadStructureLog.length - 1] : null) ||
    props?.State?.RoadStructure ||
    props?.RoadStructure ||
    props?.road ||
    null
  let roadStructure: any = {}
  if (roadStructureName && store.digitalShadowRaw?.map_layers?.road_config) {
    roadStructure = store.digitalShadowRaw.map_layers.road_config[roadStructureName] || {}
  }
  if (!roadStructure || Object.keys(roadStructure).length === 0) {
    roadStructure = props?.State?.RoadMetadata || props?.RoadStructureConfig || {}
  }

  const roadTypeObj = roadStructure?.RoadType || props?.State?.RoadMetadata?.RoadType || props?.RoadStructureConfig?.RoadType
  const roadTypeKeys = roadTypeObj ? Object.keys(roadTypeObj) : []
  const matHint = String(roadTypeKeys[0] || props?.RoadMaterial || '').toLowerCase()
  const isConcrete = matHint.includes('concrete') || matHint.includes('beton')
  isConcretePavement.value = isConcrete

  activeStructureId.value = String(roadStructureName || panel.road_structure_id || (isConcrete ? 'Concrete JPCP' : 'Asphalt'))
  activeStandard.value = String(roadStructure?.Standard || 'RStO 12')
  activeLoadClass.value = String(roadStructure?.LoadClass || panel.load_class || '')

  const weatherLog = Array.isArray(stats['WeatherState']) ? stats['WeatherState'] : []
  const latestWeather = weatherLog.length ? weatherLog[weatherLog.length - 1] : null
  activeWeatherState.value = String(
    latestWeather || props?.State?.WeatherState || props?.WeatherState || panel.nearest_rsu?.weather || 'Cloudy'
  )

  const femLog = Array.isArray(stats['TemperatureDisplacement']) ? stats['TemperatureDisplacement'] : []
  const latestFem = femLog.length
    ? femLog[femLog.length - 1]
    : (props?.TemperatureDisplacement || props?.State?.TemperatureDisplacement)
  femNodalTemps.value = Array.isArray(latestFem)
    ? latestFem.map(Number).filter((v: number) => Number.isFinite(v))
    : []

  // Build physical layers (RStO 12 highway specification aligned with digital shadow)
  const rawLayers: any[] = []
  const layerKeys = Object.keys(roadStructure)
    .filter(k => k.startsWith("Layer_"))
    .sort((a, b) => Number(a.split('_')[1] ?? 999) - Number(b.split('_')[1] ?? 999))
  for (const k of layerKeys) rawLayers.push(roadStructure[k])

  interface LayerDef {
    name: string
    subname: string
    len: number
    k: number
    stiff?: any
    cp: number
    rho: number
    isSubgrade?: boolean
    pat: 'dense' | 'medium' | 'coarse' | 'gravel' | 'soil'
    visPct: number
  }

  const layerDefs: LayerDef[] = isConcrete
    ? [
        {
          name: 'Concrete Slab',
          subname: rawLayers[0]?.Name || 'JPCP C30/37 (Betondecke)',
          len: rawLayers[0]?.Length ? Number(rawLayers[0].Length) : 0.27,
          k: rawLayers[0]?.ThermalConductivity ? Number(rawLayers[0].ThermalConductivity) : 2.10,
          stiff: rawLayers[0]?.CorrespondingStiffness,
          cp: rawLayers[0]?.HeatCapacity ? Number(rawLayers[0].HeatCapacity) : 1000,
          rho: rawLayers[0]?.Density ? Number(rawLayers[0].Density) : 2400,
          pat: 'dense',
          visPct: 26,
        },
        {
          name: 'Hydraulically Bound Base',
          subname: rawLayers[1]?.Name || 'HGT (Tragschicht)',
          len: rawLayers[1]?.Length ? Number(rawLayers[1].Length) : 0.15,
          k: rawLayers[1]?.ThermalConductivity ? Number(rawLayers[1].ThermalConductivity) : 1.80,
          stiff: rawLayers[1]?.CorrespondingStiffness,
          cp: rawLayers[1]?.HeatCapacity ? Number(rawLayers[1].HeatCapacity) : 950,
          rho: rawLayers[1]?.Density ? Number(rawLayers[1].Density) : 2250,
          pat: 'coarse',
          visPct: 22,
        },
        {
          name: 'Frost Protection',
          subname: rawLayers[2]?.Name || 'FSS (Frostschutzschicht)',
          len: rawLayers[2]?.Length ? Number(rawLayers[2].Length) : 0.28,
          k: rawLayers[2]?.ThermalConductivity ? Number(rawLayers[2].ThermalConductivity) : 2.00,
          stiff: rawLayers[2]?.CorrespondingStiffness,
          cp: rawLayers[2]?.HeatCapacity ? Number(rawLayers[2].HeatCapacity) : 850,
          rho: rawLayers[2]?.Density ? Number(rawLayers[2].Density) : 2100,
          pat: 'gravel',
          visPct: 24,
        },
        {
          name: 'Subgrade Soil',
          subname: 'Untergrund / Erdplanum',
          len: 0.40,
          k: 1.25,
          cp: 1050,
          rho: 1900,
          isSubgrade: true,
          pat: 'soil',
          visPct: 28,
        },
      ]
    : [
        {
          name: 'Surface Course',
          subname: rawLayers[0]?.Name || 'SMA 11 S (Deckschicht)',
          len: rawLayers[0]?.Length ? Number(rawLayers[0].Length) : 0.04,
          k: rawLayers[0]?.ThermalConductivity ? Number(rawLayers[0].ThermalConductivity) : 1.50,
          stiff: rawLayers[0]?.CorrespondingStiffness,
          cp: rawLayers[0]?.HeatCapacity ? Number(rawLayers[0].HeatCapacity) : 920,
          rho: rawLayers[0]?.Density ? Number(rawLayers[0].Density) : 2350,
          pat: 'dense',
          visPct: 16,
        },
        {
          name: 'Binder Course',
          subname: rawLayers[1]?.Name || 'AC 16 B S (Binderschicht)',
          len: rawLayers[1]?.Length ? Number(rawLayers[1].Length) : 0.08,
          k: rawLayers[1]?.ThermalConductivity ? Number(rawLayers[1].ThermalConductivity) : 1.60,
          stiff: rawLayers[1]?.CorrespondingStiffness,
          cp: rawLayers[1]?.HeatCapacity ? Number(rawLayers[1].HeatCapacity) : 920,
          rho: rawLayers[1]?.Density ? Number(rawLayers[1].Density) : 2400,
          pat: 'medium',
          visPct: 17,
        },
        {
          name: 'Asphalt Base',
          subname: rawLayers[2]?.Name || 'AC 22 T S (Tragschicht)',
          len: rawLayers[2]?.Length ? Number(rawLayers[2].Length) : 0.22,
          k: rawLayers[2]?.ThermalConductivity ? Number(rawLayers[2].ThermalConductivity) : 1.45,
          stiff: rawLayers[2]?.CorrespondingStiffness,
          cp: rawLayers[2]?.HeatCapacity ? Number(rawLayers[2].HeatCapacity) : 920,
          rho: rawLayers[2]?.Density ? Number(rawLayers[2].Density) : 2380,
          pat: 'coarse',
          visPct: 19,
        },
        {
          name: 'Frost Protection',
          subname: rawLayers[3]?.Name || 'FSS (Frostschutzschicht)',
          len: rawLayers[3]?.Length ? Number(rawLayers[3].Length) : 0.36,
          k: rawLayers[3]?.ThermalConductivity ? Number(rawLayers[3].ThermalConductivity) : 2.00,
          stiff: rawLayers[3]?.CorrespondingStiffness,
          cp: rawLayers[3]?.HeatCapacity ? Number(rawLayers[3].HeatCapacity) : 850,
          rho: rawLayers[3]?.Density ? Number(rawLayers[3].Density) : 2100,
          pat: 'gravel',
          visPct: 23,
        },
        {
          name: 'Subgrade Soil',
          subname: 'Untergrund / Erdplanum',
          len: 0.40,
          k: 1.25,
          cp: 1050,
          rho: 1900,
          isSubgrade: true,
          pat: 'soil',
          visPct: 25,
        },
      ]

  const totalR = layerDefs.reduce((acc, l) => acc + (l.len / l.k), 0)
  totalResistance.value = totalR

  const deltaT = sT - bT
  const q = deltaT / (totalR || 1) // W/m²
  heatFlux.value = q

  let accumDepthM = 0
  let accumVisPct = 0
  let currentTopTemp = sT
  const computedLayers: PavementLayer[] = []

  for (let i = 0; i < layerDefs.length; i++) {
    const def = layerDefs[i]
    const safeLen = Math.max(1e-4, def.len)
    const rVal = safeLen / def.k
    const femConductance = def.stiff != null && Number(def.stiff) > 0 ? Number(def.stiff) : def.k / safeLen
    const heatCapacity = Number(def.cp) > 0 ? Number(def.cp) : 920
    const density = Number(def.rho) > 0 ? Number(def.rho) : 2300
    const diffusivityMm2s = (def.k / (density * heatCapacity)) * 1e6
    const tempDrop = q * rVal
    const tempBottom = currentTopTemp - tempDrop

    const depthTopCm = accumDepthM * 100
    accumDepthM += def.len
    const depthBottomCm = accumDepthM * 100

    const visTop = accumVisPct
    accumVisPct += def.visPct
    const visBottom = accumVisPct

    computedLayers.push({
      id: `layer_${i}`,
      name: def.name,
      subname: def.subname,
      thicknessM: def.len,
      thicknessCm: Math.round(def.len * 100),
      depthTopCm: Math.round(depthTopCm),
      depthBottomCm: Math.round(depthBottomCm),
      conductivity: def.k,
      rValue: rVal,
      femConductance,
      heatCapacity,
      density,
      diffusivityMm2s,
      isSubgrade: def.isSubgrade,
      tempTop: currentTopTemp,
      tempBottom: tempBottom,
      colorTop: getTemperatureColor(currentTopTemp),
      colorBottom: getTemperatureColor(tempBottom),
      patternType: def.pat,
      visualHeightPct: def.visPct,
      visualTopPct: visTop,
      visualBottomPct: visBottom
    })

    currentTopTemp = tempBottom
  }

  pavementLayers.value = computedLayers
  pavementOnlyResistance.value = computedLayers
    .filter(l => !l.isSubgrade)
    .reduce((acc, l) => acc + l.rValue, 0)
  totalPavementDepthCm.value = Math.round(accumDepthM * 100)

  // 1D Line Chart Time-Series Calculations
  const monitorDepths: { name: string; depth: number; rToDepth: number }[] = [
    { name: 'Surface (0 cm)', depth: 0.0, rToDepth: 0 },
  ]
  let rAcc = 0
  for (const layer of computedLayers) {
    rAcc += layer.rValue
    monitorDepths.push({
      name: `${layer.name} (${layer.depthBottomCm} cm)`,
      depth: layer.depthBottomCm / 100,
      rToDepth: rAcc,
    })
  }

  const chartColors = ['#ef4444', '#f97316', '#eab308', '#10b981', '#06b6d4', '#3b82f6']
  const datasets = monitorDepths.map((md, idx) => {
    const color = chartColors[idx % chartColors.length]
    const data = timestamps.map((_: any, tIdx: number) => {
      const curSTemp = roadSurfaceTempLog[tIdx] ?? sT
      const curBTemp = soilTempLog[tIdx] ?? bT
      const curQ = (curSTemp - curBTemp) / (totalR || 1)
      return Number((curSTemp - curQ * md.rToDepth).toFixed(2))
    })

    return {
      label: md.name,
      data: data,
      borderColor: color,
      backgroundColor: color + '20',
      borderWidth: 2,
      fill: false,
      tension: 0.1,
      pointRadius: 0
    }
  })

  const isDark = store.theme === 'dark'
  const textColor = isDark ? '#94a3b8' : '#64748b'
  const gridColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)'

  chartData.value = {
    labels: timestamps,
    datasets: datasets
  }

  chartOptions.value = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: {
        title: { display: true, text: 'Simulation Timestamp', color: textColor, font: { size: 10 } },
        grid: { color: gridColor },
        ticks: { color: textColor, font: { size: 10 }, maxRotation: 45, minRotation: 45 }
      },
      y: {
        title: { display: true, text: 'Temperature [°C]', color: textColor, font: { size: 10 } },
        grid: { color: gridColor },
        ticks: { color: textColor, font: { size: 10 } }
      }
    },
    plugins: {
      legend: {
        display: true,
        position: 'top',
        labels: { color: textColor, boxWidth: 10, font: { size: 9 } }
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        callbacks: {
          label: (context: any) => `${context.dataset.label}: ${context.parsed.y.toFixed(2)}°C`
        }
      }
    }
  }
}

// Mouse interactive depth probe (piecewise-linearly mapped to each layer's visual height)
const onCrossSectionMouseMove = (e: MouseEvent) => {
  const container = e.currentTarget as HTMLElement
  if (!container) return

  const rect = container.getBoundingClientRect()
  const y = Math.max(0, Math.min(rect.height, e.clientY - rect.top))
  const yVisPct = (y / rect.height) * 100

  // Find layer by visual vertical span
  const layer = pavementLayers.value.find(
    l => yVisPct >= l.visualTopPct && yVisPct <= l.visualBottomPct
  ) || pavementLayers.value[pavementLayers.value.length - 1]

  let currentDepthCm = (yVisPct / 100) * totalPavementDepthCm.value
  let localTemp = surfaceTemp.value

  if (layer) {
    const visSpan = Math.max(1, layer.visualBottomPct - layer.visualTopPct)
    const fracInLayer = Math.max(0, Math.min(1, (yVisPct - layer.visualTopPct) / visSpan))
    currentDepthCm = layer.depthTopCm + fracInLayer * (layer.depthBottomCm - layer.depthTopCm)
    localTemp = layer.tempTop - fracInLayer * (layer.tempTop - layer.tempBottom)
  }

  activeProbe.value = {
    depthCm: Number(currentDepthCm.toFixed(1)),
    yPct: yVisPct,
    temp: Number(localTemp.toFixed(2)),
    layer: layer || null,
    heatFlux: Number(heatFlux.value.toFixed(1))
  }
}

const onCrossSectionMouseLeave = () => {
  activeProbe.value = null
}

onMounted(() => {
  updateThermalSimulation()
})

watch(() => store.selectedData, () => {
  updateThermalSimulation()
}, { deep: true })

watch(() => store.theme, () => {
  updateThermalSimulation()
})
</script>

<template>
  <div class="w-full h-full flex flex-col space-y-3.5">
    
    <!-- Top Mode Switcher Bar -->
    <div class="flex items-center justify-between gap-2 p-1.5 rounded-lg border shrink-0 text-xs shadow-xs"
         :class="store.theme === 'dark' ? 'bg-slate-900/60 border-white/10' : 'bg-slate-100/80 border-slate-200/80'">
      
      <span class="text-[10px] font-bold text-slate-400 px-1.5 uppercase tracking-wider">View Mode</span>

      <div class="flex items-center gap-1 bg-white/80 dark:bg-slate-950/60 p-0.5 rounded-md border border-slate-200/70 dark:border-white/10">
        <button @click="viewMode = 'profile'"
                class="px-2.5 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer flex items-center gap-1.5"
                :class="viewMode === 'profile'
                  ? 'bg-[#00305E] text-white shadow-xs'
                  : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'">
          <Layers :size="12" />
          <span>2D Cross-Section</span>
        </button>
        <button @click="viewMode = 'chart'"
                class="px-2.5 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer flex items-center gap-1.5"
                :class="viewMode === 'chart'
                  ? 'bg-[#00305E] text-white shadow-xs'
                  : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'">
          <BarChart2 :size="12" />
          <span>Depth Trends</span>
        </button>
        <button @click="viewMode = 'dual'"
                class="px-2.5 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer flex items-center gap-1.5"
                :class="viewMode === 'dual'
                  ? 'bg-[#00305E] text-white shadow-xs'
                  : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'">
          <Eye :size="12" />
          <span>Dual</span>
        </button>
      </div>

    </div>

    <!-- Boundary Environmental KPI Cards (Responsive 2x2 grid on standard drawer width, 1x4 on wide view) -->
    <div :class="[drawerWidth >= 620 ? 'grid-cols-4' : 'grid-cols-2', 'grid gap-2 text-xs shrink-0']">
      
      <!-- Card 1: Surface Temperature -->
      <div class="relative group p-2.5 rounded-lg border shadow-xs flex flex-col justify-between cursor-pointer transition-all hover:border-amber-400"
           :class="store.theme === 'dark' ? 'bg-slate-950/40 border-white/5' : 'bg-slate-50 border-slate-200/60'">
        <div class="h-6 flex items-center justify-between text-[10px] text-slate-400 font-bold uppercase tracking-wider">
          <span class="truncate">Surface Temp</span>
          <Sun :size="12" class="text-amber-500 shrink-0 ml-1" />
        </div>
        <div class="text-base font-black text-amber-500 tracking-tight leading-none my-1.5">{{ surfaceTemp.toFixed(1) }}°C</div>
        <div class="text-[10px] text-slate-400 truncate leading-tight">Pavement top (z = 0 cm)</div>

        <!-- On-Hover Rich Floating Info Block -->
        <div class="opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-all duration-150 absolute z-50 left-0 right-0 top-full mt-1.5 p-2.5 rounded-lg border shadow-2xl backdrop-blur-md"
             :class="store.theme === 'dark' ? 'bg-slate-900/95 border-amber-500/40 text-slate-200' : 'bg-white/95 border-amber-400 text-slate-800'">
          <div class="flex items-center justify-between font-bold text-xs text-amber-500 pb-1 border-b" :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-100'">
            <span>Surface Temperature (θ_surf)</span>
            <span class="font-mono text-sm font-black">{{ surfaceTemp.toFixed(1) }}°C</span>
          </div>
          <div class="mt-1 text-[10px] text-slate-400 font-medium">Sensor: Virtual Pyrometer / Thermal Boundary</div>
          <div class="mt-1 text-[10.5px] text-slate-600 dark:text-slate-300 leading-snug">
            Direct solar irradiance absorption and convective air contact on the top wearing course skin (z = 0 cm). Determines tire contact thermal boundary conditions.
          </div>
        </div>
      </div>

      <!-- Card 2: Ambient Air Temperature -->
      <div class="relative group p-2.5 rounded-lg border shadow-xs flex flex-col justify-between cursor-pointer transition-all hover:border-orange-400"
           :class="store.theme === 'dark' ? 'bg-slate-950/40 border-white/5' : 'bg-slate-50 border-slate-200/60'">
        <div class="h-6 flex items-center justify-between text-[10px] text-slate-400 font-bold uppercase tracking-wider">
          <span class="truncate">Ambient Air</span>
          <Thermometer :size="12" class="text-orange-400 shrink-0 ml-1" />
        </div>
        <div class="text-base font-black tracking-tight leading-none my-1.5" :class="store.theme === 'dark' ? 'text-slate-200' : 'text-slate-700'">
          {{ airTemp.toFixed(1) }}°C
        </div>
        <div class="text-[10px] text-slate-400 truncate leading-tight">RSU Weather Sensor</div>

        <!-- On-Hover Rich Floating Info Block -->
        <div class="opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-all duration-150 absolute z-50 left-0 right-0 top-full mt-1.5 p-2.5 rounded-lg border shadow-2xl backdrop-blur-md"
             :class="store.theme === 'dark' ? 'bg-slate-900/95 border-orange-500/40 text-slate-200' : 'bg-white/95 border-orange-400 text-slate-800'">
          <div class="flex items-center justify-between font-bold text-xs text-orange-500 pb-1 border-b" :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-100'">
            <span>Ambient Air Temperature (T_air)</span>
            <span class="font-mono text-sm font-black">{{ airTemp.toFixed(1) }}°C</span>
          </div>
          <div class="mt-1 text-[10px] text-slate-400 font-medium">Sensor: RSU Weather Station Mast (2m AGL)</div>
          <div class="mt-1 text-[10.5px] text-slate-600 dark:text-slate-300 leading-snug">
            Convective environmental boundary driving Newton heat exchange between atmospheric air and the asphalt surface.
          </div>
        </div>
      </div>

      <!-- Card 3: Subgrade Bedding Soil Temperature -->
      <div class="relative group p-2.5 rounded-lg border shadow-xs flex flex-col justify-between cursor-pointer transition-all hover:border-blue-400"
           :class="store.theme === 'dark' ? 'bg-slate-950/40 border-white/5' : 'bg-slate-50 border-slate-200/60'">
        <div class="h-6 flex items-center justify-between text-[10px] text-slate-400 font-bold uppercase tracking-wider">
          <span class="truncate">Subgrade Soil</span>
          <Layers :size="12" class="text-blue-500 shrink-0 ml-1" />
        </div>
        <div class="text-base font-black text-blue-500 tracking-tight leading-none my-1.5">{{ subgradeSoilTemp.toFixed(1) }}°C</div>
        <div class="text-[10px] text-slate-400 truncate leading-tight">Deep Earth (z = {{ (totalPavementDepthCm / 100).toFixed(2) }} m)</div>

        <!-- On-Hover Rich Floating Info Block -->
        <div class="opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-all duration-150 absolute z-50 left-0 right-0 top-full mt-1.5 p-2.5 rounded-lg border shadow-2xl backdrop-blur-md"
             :class="store.theme === 'dark' ? 'bg-slate-900/95 border-blue-500/40 text-slate-200' : 'bg-white/95 border-blue-400 text-slate-800'">
          <div class="flex items-center justify-between font-bold text-xs text-blue-500 pb-1 border-b" :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-100'">
            <span>Subgrade Soil Temperature (T_soil)</span>
            <span class="font-mono text-sm font-black">{{ subgradeSoilTemp.toFixed(1) }}°C</span>
          </div>
          <div class="mt-1 text-[10px] text-slate-400 font-medium">Sensor: Subsurface Hydro-Thermal Sensor (z = {{ (totalPavementDepthCm / 100).toFixed(2) }} m)</div>
          <div class="mt-1 text-[10.5px] text-slate-600 dark:text-slate-300 leading-snug">
            Geothermal deep earth boundary condition acting as a constant conductive heat sink beneath granular subbase layers.
          </div>
        </div>
      </div>

      <!-- Card 4: Heat Flux -->
      <div class="relative group p-2.5 rounded-lg border shadow-xs flex flex-col justify-between cursor-pointer transition-all hover:border-rose-400"
           :class="store.theme === 'dark' ? 'bg-slate-950/40 border-white/5' : 'bg-slate-50 border-slate-200/60'">
        <div class="h-6 flex items-center justify-between text-[10px] text-slate-400 font-bold uppercase tracking-wider">
          <span class="truncate">Heat Flux (q)</span>
          <Flame :size="12" class="text-rose-500 shrink-0 ml-1" />
        </div>
        <div class="text-base font-black text-rose-500 tracking-tight leading-none my-1.5 flex items-baseline gap-1">
          <span>{{ heatFlux.toFixed(1) }}</span>
          <span class="text-xs font-semibold">W/m²</span>
        </div>
        <div class="text-[10px] text-slate-400 truncate leading-tight">Downward diffusion</div>

        <!-- On-Hover Rich Floating Info Block -->
        <div class="opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-all duration-150 absolute z-50 left-0 right-0 top-full mt-1.5 p-2.5 rounded-lg border shadow-2xl backdrop-blur-md"
             :class="store.theme === 'dark' ? 'bg-slate-900/95 border-rose-500/40 text-slate-200' : 'bg-white/95 border-rose-400 text-slate-800'">
          <div class="flex items-center justify-between font-bold text-xs text-rose-500 pb-1 border-b" :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-100'">
            <span>Conductive Heat Flux (q)</span>
            <span class="font-mono text-sm font-black">{{ heatFlux.toFixed(1) }} W/m²</span>
          </div>
          <div class="mt-1 text-[10px] text-slate-400 font-medium">Fourier 1D Conduction Rate (q = ΔT / Σ(h_i / k_i))</div>
          <div class="mt-1 text-[10.5px] text-slate-600 dark:text-slate-300 leading-snug">
            Vertical heat transfer rate flowing downward through asphalt, binder, base, and granular frost protection into subgrade earth.
          </div>
        </div>
      </div>

    </div>

    <!-- MAIN SECTION: 2D Pavement Cross-Section Heatmap -->
    <div v-show="viewMode === 'profile' || viewMode === 'dual'"
         class="rounded-lg border p-4 shadow-sm flex flex-col space-y-3 relative overflow-hidden"
         :class="store.theme === 'dark' ? 'bg-slate-950/40 border-white/10' : 'bg-slate-50/70 border-slate-200'">

      <div class="flex items-center justify-between gap-2">
        <div>
          <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Layers :size="14" class="text-amber-500" />
            <span>Pavement Structural Cross-Section & Thermal Gradient</span>
          </h4>
          <p class="text-[11px] text-slate-500">Move mouse vertically across the layered pavement profile to probe local temperature & conductive flux.</p>
        </div>
        <span class="text-[10px] font-bold px-2 py-0.5 rounded border whitespace-nowrap shrink-0"
              :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-amber-400' : 'bg-amber-50 border-amber-200 text-amber-700'">
          {{ isConcretePavement ? 'RStO 12 Concrete (JPCP)' : 'RStO 12 Asphalt' }}
        </span>
      </div>

      <!-- Cross-Section Container (Height increased to 285px to prevent bottom cropping) -->
      <div class="relative w-full h-[285px] rounded-lg border overflow-hidden flex select-none cursor-crosshair group shadow-inner"
           :class="store.theme === 'dark' ? 'border-white/10 bg-slate-900' : 'border-slate-300 bg-white'"
           @mousemove="onCrossSectionMouseMove"
           @mouseleave="onCrossSectionMouseLeave">

        <!-- Integrated Depth Axis (Left) -->
        <div class="w-12 h-full shrink-0 border-r relative text-[9px] font-mono select-none"
             :class="store.theme === 'dark' ? 'border-white/10 bg-slate-950/70 text-slate-400' : 'border-slate-200 bg-slate-100/80 text-slate-600'">
          <span class="absolute right-1.5 top-1 font-bold text-[#00305E] dark:text-[#8ecae6]">0 cm</span>
          <span v-for="(layer, idx) in pavementLayers" :key="`axis_${layer.id}`"
                class="absolute right-1.5 font-bold"
                :class="idx === pavementLayers.length - 1 ? 'bottom-1 text-blue-600 dark:text-blue-400' : '-translate-y-1/2 text-slate-500 dark:text-slate-400'"
                :style="idx === pavementLayers.length - 1 ? {} : { top: `${layer.visualBottomPct}%` }">
            {{ layer.depthBottomCm }} cm
          </span>
        </div>

        <!-- Layer Blocks Canvas (Center) -->
        <div class="flex-1 h-full relative flex flex-col">

          <div v-for="layer in pavementLayers" :key="layer.id"
               class="relative w-full border-b transition-all flex items-center justify-between px-3 py-1 text-xs"
               :class="[
                 store.theme === 'dark' ? 'border-white/15' : 'border-slate-300/80',
                 hoveredLayerId === layer.id ? 'ring-2 ring-amber-400 ring-inset z-10' : ''
               ]"
               :style="{
                 height: `${layer.visualHeightPct}%`,
                 background: `linear-gradient(to bottom, ${layer.colorTop}45, ${layer.colorBottom}45)`
               }"
               @mouseenter="hoveredLayerId = layer.id"
               @mouseleave="hoveredLayerId = null">

            <!-- Texture Pattern Overlay -->
            <div class="absolute inset-0 pointer-events-none opacity-15"
                 :class="{
                   'bg-[radial-gradient(#000_1px,transparent_1px)] dark:bg-[radial-gradient(#fff_1px,transparent_1px)] [background-size:6px_6px]': layer.patternType === 'dense',
                   'bg-[radial-gradient(#000_1.5px,transparent_1.5px)] dark:bg-[radial-gradient(#fff_1.5px,transparent_1.5px)] [background-size:10px_10px]': layer.patternType === 'medium',
                   'bg-[radial-gradient(#000_2px,transparent_2px)] dark:bg-[radial-gradient(#fff_2px,transparent_2px)] [background-size:14px_14px]': layer.patternType === 'coarse',
                   'bg-[repeating-linear-gradient(45deg,#000_0,#000_1px,transparent_0,transparent_8px)] dark:bg-[repeating-linear-gradient(45deg,#fff_0,#fff_1px,transparent_0,transparent_8px)]': layer.patternType === 'gravel',
                   'bg-[repeating-linear-gradient(-45deg,#000_0,#000_1px,transparent_0,transparent_6px)] dark:bg-[repeating-linear-gradient(-45deg,#fff_0,#fff_1px,transparent_0,transparent_6px)]': layer.patternType === 'soil'
                 }">
            </div>

            <!-- Layer Name & Thickness Tag -->
            <div class="relative z-10 min-w-0 pr-2 select-none flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full shrink-0 shadow-xs" :style="{ backgroundColor: layer.colorTop }"></span>
              <span class="font-extrabold text-[11px] truncate leading-tight" :class="store.theme === 'dark' ? 'text-white' : 'text-[#00305E]'">
                {{ layer.name }}
              </span>
              <span class="text-[9.5px] px-1 py-0.2 rounded font-mono font-semibold bg-black/10 dark:bg-white/10 shrink-0">
                h={{ layer.thicknessCm }}cm
              </span>
            </div>

            <!-- In-Layer Temperature Gradient Badge -->
            <div class="relative z-10 shrink-0 select-none">
              <span class="text-[10px] font-mono font-bold px-2 py-0.5 rounded-md bg-black/35 dark:bg-black/55 text-white backdrop-blur-xs border border-white/10 shadow-xs">
                {{ layer.tempTop.toFixed(1) }}° → {{ layer.tempBottom.toFixed(1) }}°C
              </span>
            </div>

          </div>

          <!-- Dynamic Interactive Laser Depth Probe Guide Line -->
          <div v-if="activeProbe"
               class="absolute left-0 right-0 border-t-2 border-dashed border-amber-400 pointer-events-none z-30 transition-all duration-75 flex items-center justify-end pr-3"
               :style="{ top: `${activeProbe.yPct}%` }">
            <div class="bg-amber-500 text-slate-950 font-black text-[10px] px-2.5 py-0.5 rounded shadow-lg -translate-y-1/2">
              z = {{ activeProbe.depthCm }} cm • {{ activeProbe.temp }}°C
            </div>
          </div>

        </div>

        <!-- Integrated Vertical Thermal Scale (Right) -->
        <div class="w-9 h-full shrink-0 border-l relative flex flex-col justify-between py-1.5 px-1 text-[9px] font-mono select-none"
             :class="store.theme === 'dark' ? 'border-white/10 bg-slate-950/70' : 'border-slate-200 bg-slate-100/80'">
          <div class="absolute inset-y-2 left-1.5 w-1 rounded-full opacity-70"
               style="background: linear-gradient(to bottom, #ef4444, #f97316, #eab308, #10b981, #06b6d4, #3b82f6);"></div>
          <span class="text-right text-rose-500 font-bold z-10 top-1 absolute right-1">{{ Math.round(surfaceTemp) }}°</span>
          <span class="text-right text-amber-500 font-bold z-10 top-1/2 -translate-y-1/2 absolute right-1">{{ Math.round((surfaceTemp + subgradeSoilTemp) / 2) }}°</span>
          <span class="text-right text-blue-500 font-bold z-10 bottom-1 absolute right-1">{{ Math.round(subgradeSoilTemp) }}°</span>
        </div>

      </div>

      <!-- Dedicated Layer Thermal & 1D FEM Material Properties Table -->
      <div class="rounded-lg border overflow-hidden text-xs shadow-xs"
           :class="store.theme === 'dark' ? 'border-white/10 bg-slate-900/80' : 'border-slate-200 bg-white'">
        
        <div class="px-3 py-2 border-b flex items-center justify-between gap-2 flex-wrap"
             :class="store.theme === 'dark' ? 'bg-slate-950/70 border-white/10' : 'bg-slate-100/80 border-slate-200'">
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
            Layer Thermal &amp; 1D FEM Properties
          </span>
          <span class="text-[10px] font-mono font-semibold text-[#00305E] dark:text-sky-300">
            {{ activeStructureId }}<template v-if="activeLoadClass"> · {{ activeLoadClass }}</template><template v-if="activeStandard"> · {{ activeStandard }}</template>
          </span>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse min-w-[660px]">
            <thead>
              <tr class="text-[9.5px] font-bold uppercase tracking-wider border-b"
                  :class="store.theme === 'dark' ? 'bg-slate-950/50 border-white/5 text-slate-400' : 'bg-slate-50 border-slate-200 text-slate-500'">
                <th class="px-3 py-2">Layer / Material</th>
                <th class="px-2 py-2 text-right font-mono normal-case whitespace-nowrap">h [cm]</th>
                <th class="px-2 py-2 text-right font-mono normal-case whitespace-nowrap">k [W/(m·K)]</th>
                <th class="px-2 py-2 text-right font-mono normal-case whitespace-nowrap">R=h/k [m²·K/W]</th>
                <th class="px-2 py-2 text-right font-mono normal-case whitespace-nowrap">k/h [W/(m²·K)]</th>
                <th class="px-2 py-2 text-right font-mono normal-case whitespace-nowrap">c_p [J/(kg·K)]</th>
                <th class="px-2 py-2 text-right font-mono normal-case whitespace-nowrap">ρ [kg/m³]</th>
                <th class="px-2 py-2 text-right font-mono normal-case whitespace-nowrap">α [mm²/s]</th>
                <th class="px-3 py-2 text-right whitespace-nowrap">Temp Interval</th>
              </tr>
            </thead>
            <tbody class="divide-y" :class="store.theme === 'dark' ? 'divide-white/5' : 'divide-slate-100'">
              <tr v-for="layer in pavementLayers"
                  :key="`row_${layer.id}`"
                  class="transition-colors cursor-pointer"
                  :class="hoveredLayerId === layer.id
                    ? (store.theme === 'dark' ? 'bg-white/10' : 'bg-amber-50/80')
                    : (store.theme === 'dark' ? 'hover:bg-white/5' : 'hover:bg-slate-50')"
                  @mouseenter="hoveredLayerId = layer.id"
                  @mouseleave="hoveredLayerId = null">
                <td class="px-3 py-2">
                  <div class="flex items-center gap-2 min-w-[155px]">
                    <span class="w-2.5 h-2.5 rounded-full shrink-0 border border-black/20 shadow-xs" :style="{ backgroundColor: layer.colorTop }"></span>
                    <div class="min-w-0">
                      <div class="flex items-center gap-1.5">
                        <span class="font-bold text-[11px] truncate leading-tight" :class="store.theme === 'dark' ? 'text-slate-200' : 'text-[#00305E]'">
                          {{ layer.name }}
                        </span>
                        <span v-if="layer.isSubgrade"
                              class="px-1 py-0.2 rounded text-[8.5px] font-mono font-semibold border border-slate-300 dark:border-white/10 text-slate-500 dark:text-slate-400">
                          BC
                        </span>
                      </div>
                      <div class="text-[9px] text-slate-500 truncate leading-tight mt-0.5">
                        {{ layer.subname }}
                      </div>
                    </div>
                  </div>
                </td>
                <td class="px-2 py-2 text-right font-mono text-[10.5px] tabular-nums whitespace-nowrap">
                  <div class="font-semibold" :class="store.theme === 'dark' ? 'text-slate-200' : 'text-slate-800'">{{ layer.thicknessCm }}</div>
                  <div class="text-[9px] text-slate-400">{{ layer.depthTopCm }}–{{ layer.depthBottomCm }}</div>
                </td>
                <td class="px-2 py-2 text-right font-mono text-[10.5px] font-bold tabular-nums whitespace-nowrap"
                    :class="store.theme === 'dark' ? 'text-slate-200' : 'text-[#00305E]'">
                  {{ layer.conductivity.toFixed(2) }}
                </td>
                <td class="px-2 py-2 text-right font-mono text-[10.5px] tabular-nums text-slate-600 dark:text-slate-300 whitespace-nowrap">
                  {{ layer.rValue.toFixed(3) }}
                </td>
                <td class="px-2 py-2 text-right font-mono text-[10.5px] tabular-nums text-slate-600 dark:text-slate-300 whitespace-nowrap">
                  {{ layer.femConductance.toFixed(2) }}
                </td>
                <td class="px-2 py-2 text-right font-mono text-[10.5px] tabular-nums text-slate-600 dark:text-slate-300 whitespace-nowrap">
                  {{ Math.round(layer.heatCapacity) }}
                </td>
                <td class="px-2 py-2 text-right font-mono text-[10.5px] tabular-nums text-slate-600 dark:text-slate-300 whitespace-nowrap">
                  {{ Math.round(layer.density) }}
                </td>
                <td class="px-2 py-2 text-right font-mono text-[10.5px] tabular-nums text-slate-600 dark:text-slate-300 whitespace-nowrap">
                  {{ layer.diffusivityMm2s.toFixed(2) }}
                </td>
                <td class="px-3 py-2 text-right font-mono text-[11px] font-bold tabular-nums whitespace-nowrap">
                  <span class="text-amber-500">{{ layer.tempTop.toFixed(1) }}°</span>
                  <span class="text-slate-400 mx-0.5 font-normal">→</span>
                  <span :style="{ color: layer.colorBottom }">{{ layer.tempBottom.toFixed(1) }}°C</span>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="border-t text-[10px] font-mono"
                  :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/10 text-slate-300' : 'bg-slate-50 border-slate-200 text-slate-700'">
                <td class="px-3 py-1.5 font-sans font-bold uppercase tracking-wider text-slate-500">Total Column</td>
                <td class="px-2 py-1.5 text-right font-bold whitespace-nowrap">{{ totalPavementDepthCm }} cm</td>
                <td class="px-2 py-1.5 text-right text-slate-400">—</td>
                <td class="px-2 py-1.5 text-right font-bold whitespace-nowrap" :title="`Pavement layers only: ${pavementOnlyResistance.toFixed(3)} m²·K/W`">
                  {{ totalResistance.toFixed(3) }}
                </td>
                <td colspan="4" class="px-2 py-1.5 text-right text-slate-500 whitespace-nowrap">
                  Pavement R: {{ pavementOnlyResistance.toFixed(3) }} m²·K/W
                </td>
                <td class="px-3 py-1.5 text-right font-bold text-rose-500 whitespace-nowrap">
                  q = {{ heatFlux.toFixed(1) }} W/m²
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      <!-- 1D FEM Boundary Conditions & Nodal Solver Vector -->
      <div class="p-2.5 rounded-lg border text-[10.5px] space-y-2"
           :class="store.theme === 'dark' ? 'bg-slate-950/50 border-white/10 text-slate-300' : 'bg-slate-50 border-slate-200 text-slate-700'">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono">
          <div class="px-2 py-1.5 rounded border"
               :class="store.theme === 'dark' ? 'bg-slate-900/70 border-white/5' : 'bg-white border-slate-200/80'">
            <div class="font-sans text-[9px] font-bold uppercase tracking-wider text-slate-400">Convective Film</div>
            <div class="font-bold mt-0.5">R_conv = 0.04 m²·K/W</div>
          </div>
          <div class="px-2 py-1.5 rounded border"
               :class="store.theme === 'dark' ? 'bg-slate-900/70 border-white/5' : 'bg-white border-slate-200/80'">
            <div class="font-sans text-[9px] font-bold uppercase tracking-wider text-slate-400">Solar Flux (f₁)</div>
            <div class="font-bold mt-0.5 text-amber-600 dark:text-amber-400">{{ solarFluxWm2.toFixed(1) }} W/m² ({{ activeWeatherState }})</div>
          </div>
          <div class="px-2 py-1.5 rounded border"
               :class="store.theme === 'dark' ? 'bg-slate-900/70 border-white/5' : 'bg-white border-slate-200/80'">
            <div class="font-sans text-[9px] font-bold uppercase tracking-wider text-slate-400">Dirichlet BCs</div>
            <div class="font-bold mt-0.5">{{ airTemp.toFixed(1) }}° → {{ subgradeSoilTemp.toFixed(1) }}°C</div>
          </div>
          <div class="px-2 py-1.5 rounded border"
               :class="store.theme === 'dark' ? 'bg-slate-900/70 border-white/5' : 'bg-white border-slate-200/80'">
            <div class="font-sans text-[9px] font-bold uppercase tracking-wider text-slate-400">Total ΣR</div>
            <div class="font-bold mt-0.5 text-[#00305E] dark:text-sky-300">{{ totalResistance.toFixed(3) }} m²·K/W</div>
          </div>
        </div>

        <div v-if="femNodalTemps.length > 0"
             class="flex flex-wrap items-center gap-2 pt-1 border-t font-mono text-[10px]"
             :class="store.theme === 'dark' ? 'border-white/5' : 'border-slate-200/80'">
          <span class="font-sans font-bold uppercase tracking-wider text-[9px] text-slate-400 shrink-0">
            1D FEM Nodal Temps (Air → Layers → Soil):
          </span>
          <span class="font-semibold text-amber-600 dark:text-amber-300">
            {{ femNodalTemps.map(t => `${t.toFixed(1)}°C`).join(' → ') }}
          </span>
        </div>
      </div>

      <!-- Live Probe HUD (Hover Card) -->
      <div v-if="activeProbe"
           class="p-2.5 rounded-lg border text-xs flex items-center justify-between gap-3 shadow-md animate-in fade-in duration-150"
           :class="store.theme === 'dark' ? 'bg-slate-900 border-amber-500/30' : 'bg-amber-50/90 border-amber-300'">
        <div class="flex items-center gap-2 min-w-0">
          <div class="h-7 w-7 rounded-md bg-amber-500/20 text-amber-500 flex items-center justify-center shrink-0 font-bold">
            <Thermometer :size="15" />
          </div>
          <div class="min-w-0">
            <div class="font-bold text-slate-900 dark:text-white flex items-center gap-1.5 truncate">
              <span>Depth: {{ activeProbe.depthCm }} cm</span>
              <span class="text-[10px] font-normal text-slate-400 truncate">({{ activeProbe.layer?.name }})</span>
            </div>
            <div class="text-[10px] font-mono text-slate-500 truncate">
              k={{ activeProbe.layer?.conductivity.toFixed(2) }} W/(m·K) · R={{ activeProbe.layer?.rValue.toFixed(3) }} · k/h={{ activeProbe.layer?.femConductance.toFixed(2) }} · c_p={{ activeProbe.layer?.heatCapacity }} · ρ={{ activeProbe.layer?.density }}
            </div>
          </div>
        </div>
        <div class="text-right shrink-0">
          <div class="text-base font-black text-amber-500 tracking-tight leading-none">{{ activeProbe.temp }}°C</div>
          <div class="text-[9px] text-slate-400 mt-0.5">Probe Temp</div>
        </div>
      </div>

    </div>

    <!-- 1D Time Series Line Chart -->
    <div v-show="viewMode === 'chart' || viewMode === 'dual'"
         class="rounded-lg border p-4 shadow-sm flex flex-col space-y-2"
         :class="store.theme === 'dark' ? 'bg-slate-950/40 border-white/5' : 'bg-slate-50/70 border-slate-200/60'">
      
      <div class="flex items-center justify-between mb-1">
        <div>
          <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Activity :size="14" class="text-blue-500" />
            <span>Multi-Depth Transient Heat Conduction</span>
          </h4>
          <p class="text-[11px] text-slate-500">Simulated thermal progression across depth intervals from surface (0 cm) to deep subgrade ({{ totalPavementDepthCm }} cm).</p>
        </div>
      </div>

      <div v-if="chartData.datasets.length" class="w-full h-[280px]">
        <Line :data="chartData" :options="chartOptions" />
      </div>
      <div v-else class="text-xs font-medium italic py-10 text-center text-slate-400">
        No transient thermal log points recorded yet.
      </div>

    </div>

  </div>
</template>