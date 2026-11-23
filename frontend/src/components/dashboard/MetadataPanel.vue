<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useDashboardStore } from '../../stores/dashboard'
import {
  ChevronLeft,
  ChevronRight,
  Info,
  Search,
  Cpu,
  Navigation,
  Thermometer,
  Tag,
  Activity
} from 'lucide-vue-next'

const store = useDashboardStore()
const selectedDetailKey = ref<string | null>(null)
const searchQuery = ref('')

const stats = computed(() => store.selectedData?.stats || {})
const rawProps = computed(() => store.selectedData?.properties || store.selectedFeature?.properties || {})

watch(() => store.selectedFeature?.properties?.id, () => {
  selectedDetailKey.value = null
})

interface NormalizedParam {
  key: string
  label: string
  value: any
  formatted: string
  unit: string
  category: 'identity' | 'kinematics' | 'environment' | 'simulation'
  badgeType?: 'boolean-true' | 'boolean-false' | 'weather' | 'solver' | 'array-temps' | 'direction'
  history: any[]
}

const HUMAN_LABELS: Record<string, string> = {
  ID: 'Entity ID',
  id: 'Entity ID',
  Callsign: 'Fleet Callsign',
  Active: 'Operational Status',
  VehicleClass: 'Vehicle Configuration',
  AxleConfig: 'EU Axle Class',
  Axles: 'Number of Axles',
  Weight: 'Gross Vehicle Weight',
  Velocity: 'Cruising Speed',
  ExtrapolatedVelocity: 'Extrapolated Speed',
  Length: 'Vehicle Length',
  Width: 'Vehicle Width',
  Damage: 'Instantaneous Damage Incr.',
  CumulativeDamage: 'Cumulative Rut Depth',
  PassesCount: 'Total HGV Passes',
  Kilometer: 'Corridor Station',
  LastPosition: 'Last Recorded Station',
  Direction: 'Carriageway Direction',
  RouteProgressPct: 'Route Completion',
  RemainingKm: 'Remaining Distance',
  StartRoute: 'Origin Station',
  EndRoute: 'Destination Station',
  StartJunctionCode: 'Origin Junction Code',
  StartJunctionName: 'Origin Junction',
  EndJunctionCode: 'Destination Code',
  EndJunctionName: 'Destination Junction',
  AirTemperature: 'Ambient Air Temp',
  RoadSurfaceTemperature: 'Pavement Surface Temp',
  SoilTemperature: 'Subgrade Soil Temp',
  WeatherState: 'Micro-Climate State',
  TemperatureDisplacement: '1D FEM Nodal Temps (Air→Soil)',
  StepComputationTimeMs: 'Sim Loop Compute Time',
  SolverModel: 'Active Mechanical Solver',
  SolverAccuracy: 'POD Surrogate Confidence',
  SolverThreshold: 'SLA Confidence Threshold',
  Coordinates: 'WGS84 Coordinates (Lon, Lat)',
  RoadStructure: 'RStO 12 Structure Class',
  RoadsideUnit: 'Connected RSU ID',
  RoadsideUnitName: 'Connected Edge RSU',
  RoadsideUnitTown: 'RSU Municipality',
  RoadsideUnitStation: 'RSU Corridor Station',
  RoadsideUnitDist: 'V2X Link Distance',
  SpawnProbability: 'Corridor Spawn Rate',
  VehicleLimit: 'Fleet Capacity Limit',
  UpdatePeriod: 'Fast-Scale Step Δt',
  Timestamp: 'Last Telemetry Sync',
  Altitude: 'Flight Altitude (AGL)',
  BearingDeg: 'Heading Bearing',
  BatteryPct: 'Onboard LiPo Battery',
  MissionProgressPct: 'UAV Mission Progress',
  FlightState: 'UAV Flight Stage',
  PayloadSensor: 'Inspection Payload',
  AnomalyType: 'Structural Anomaly Class',
  Severity: 'Severity Classification',
  ConfidenceScore: 'Detection Confidence',
  EstimatedRutDepthMm: 'Estimated Rut Depth'
}

const IGNORED_KEYS = new Set([
  'State',
  'MechanicalSimulation',
  'StartJunctionID',
  'StartJunctionShort',
  'EndJunctionID',
  'EndJunctionShort',
  'IntervalBegin',
  'IntervalEnd',
  'HPN',
  'HPN_Graph',
  'FederationContract',
  'Trajectory',
  'FlightTrail',
  'RoadMetadata',
  'LastPosition',
  'StatsSynthetic',
  'KinematicAxles'
])

const formatHumanLabel = (rawKey: string): string => {
  if (HUMAN_LABELS[rawKey]) return HUMAN_LABELS[rawKey]
  return rawKey
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, c => c.toUpperCase())
}

const getUnit = (key: string): string => {
  const k = key.toLowerCase()
  if (k === 'stepcomputationtimems') return 'ms'
  if (k.includes('temperature') && !k.includes('displacement')) return '°C'
  if (k === 'weight' || k === 'triggerweightkg') return 'kg'
  if (k === 'velocity' || k === 'extrapolatedvelocity' || k === 'speed' || k === 'triggervelocitykmh') return 'km/h'
  if (k === 'length' || k === 'width' || k === 'altitude' || k === 'length_m') return 'm'
  if (k.includes('pct') || k === 'solveraccuracy' || k === 'solverthreshold' || k === 'state') return '%'
  if (k === 'kilometer' || k === 'lastposition' || k === 'startroute' || k === 'endroute' || k === 'remainingkm' || k === 'roadsideunitdist' || k === 'roadsideunitstation' || k === 'dist') return 'km'
  if (k === 'updateperiod') return 's'
  if (k === 'bearingdeg') return '°'
  if (k.includes('damage') || k.includes('rutdepth')) return 'mm'
  return ''
}

const getCategory = (key: string): 'identity' | 'kinematics' | 'environment' | 'simulation' => {
  const k = key.toLowerCase()
  if (
    k === 'id' || k === 'callsign' || k === 'active' || k.includes('class') ||
    k.includes('axle') || k === 'name' || k === 'code' || k === 'town' ||
    k.includes('anomaly') || k === 'severity' || k === 'payloadsensor'
  ) {
    return 'identity'
  }
  if (
    k.includes('velocity') || k.includes('weight') || k === 'length' || k === 'width' ||
    k.includes('kilometer') || k.includes('position') || k.includes('route') ||
    k.includes('junction') || k === 'direction' || k === 'remainingkm' ||
    k === 'coordinates' || k === 'altitude' || k === 'bearingdeg' || k.includes('progress')
  ) {
    return 'kinematics'
  }
  if (
    k.includes('temp') || k.includes('weather') || k.includes('water') ||
    k.includes('soil') || k.includes('frost') || k === 'roadstructure'
  ) {
    return 'environment'
  }
  return 'simulation'
}

const formatParamValue = (key: string, val: any): string => {
  if (val === null || val === undefined || val === '') return '—'
  if (typeof val === 'boolean') return val ? 'Active' : 'Inactive'
  if (key === 'Direction') {
    return Number(val) === 1 ? 'Dresden → Leipzig (+1)' : 'Leipzig → Dresden (-1)'
  }
  if (key === 'SolverAccuracy' || key === 'SolverThreshold' || key === 'ConfidenceScore') {
    const num = Number(val)
    if (!isNaN(num)) return (num <= 1.0 ? num * 100 : num).toFixed(1)
  }
  if (typeof val === 'number') {
    if (Number.isInteger(val) && !key.toLowerCase().includes('temp')) return String(val)
    const k = key.toLowerCase()
    if (k.includes('damage')) return val.toFixed(4)
    if (k === 'stepcomputationtimems') return val.toFixed(2)
    if (k.includes('temp')) return val.toFixed(1)
    if (k.includes('velocity') || k.includes('pct')) return val.toFixed(1)
    return Math.abs(val) < 0.001 && val !== 0 ? val.toExponential(2) : val.toFixed(2)
  }
  if (Array.isArray(val)) {
    if (val.every(item => typeof item === 'number')) {
      return val.map(n => `${Number(n).toFixed(1)}°C`).join(' → ')
    }
    return val.join(', ')
  }
  if (typeof val === 'object') {
    return Object.entries(val)
      .filter(([_, v]) => typeof v !== 'object')
      .map(([k, v]) => `${k}: ${v}`)
      .join(' • ')
  }
  return String(val)
}

const normalizedParams = computed<NormalizedParam[]>(() => {
  const resultMap = new Map<string, NormalizedParam>()

  const addEntry = (key: string, rawVal: any, histArray?: any[]) => {
    if (IGNORED_KEYS.has(key) || rawVal === undefined || rawVal === null) return
    if (typeof rawVal === 'object' && !Array.isArray(rawVal)) return

    let badgeType: NormalizedParam['badgeType'] = undefined
    if (typeof rawVal === 'boolean') {
      badgeType = rawVal ? 'boolean-true' : 'boolean-false'
    } else if (key === 'WeatherState') {
      badgeType = 'weather'
    } else if (key === 'SolverModel') {
      badgeType = 'solver'
    } else if (key === 'TemperatureDisplacement' && Array.isArray(rawVal)) {
      badgeType = 'array-temps'
    } else if (key === 'Direction') {
      badgeType = 'direction'
    }

    resultMap.set(key, {
      key,
      label: formatHumanLabel(key),
      value: rawVal,
      formatted: formatParamValue(key, rawVal),
      unit: getUnit(key),
      category: getCategory(key),
      badgeType,
      history: histArray && histArray.length ? histArray : [rawVal]
    })
  }

  // 1. Extract from time-series stats
  for (const [k, arr] of Object.entries(stats.value)) {
    const latest = Array.isArray(arr) ? arr[arr.length - 1] : arr
    if (k === 'MechanicalSimulation' && typeof latest === 'object' && latest) {
      addEntry('SolverModel', latest.Model || 'POD')
      if (latest.Accuracy != null) addEntry('SolverAccuracy', Number(latest.Accuracy))
      if (latest.Threshold != null) addEntry('SolverThreshold', Number(latest.Threshold))
      continue
    }
    if (k === 'State' && typeof latest === 'object' && latest) {
      if (latest.Coordinates) addEntry('Coordinates', latest.Coordinates)
      if (latest.RoadStructure) addEntry('RoadStructure', latest.RoadStructure)
      if (latest.RoadsideUnitName) addEntry('RoadsideUnitName', latest.RoadsideUnitName)
      if (latest.RoadsideUnitDist != null) addEntry('RoadsideUnitDist', Number(latest.RoadsideUnitDist))
      continue
    }
    addEntry(k, latest, Array.isArray(arr) ? arr : [arr])
  }

  // 2. Supplement with direct properties (such as StepComputationTimeMs or nested State/MechanicalSimulation)
  for (const [k, val] of Object.entries(rawProps.value)) {
    if (resultMap.has(k)) continue
    if (k === 'MechanicalSimulation' && typeof val === 'object' && val) {
      if (!resultMap.has('SolverModel')) addEntry('SolverModel', (val as any).Model || 'POD')
      if (!resultMap.has('SolverAccuracy') && (val as any).Accuracy != null) addEntry('SolverAccuracy', Number((val as any).Accuracy))
      continue
    }
    if (k === 'State' && typeof val === 'object' && val) {
      if (!resultMap.has('Coordinates') && (val as any).Coordinates) addEntry('Coordinates', (val as any).Coordinates)
      if (!resultMap.has('RoadsideUnitName') && (val as any).RoadsideUnitName) addEntry('RoadsideUnitName', (val as any).RoadsideUnitName)
      if (!resultMap.has('RoadsideUnitDist') && (val as any).RoadsideUnitDist != null) addEntry('RoadsideUnitDist', Number((val as any).RoadsideUnitDist))
      continue
    }
    addEntry(k, val)
  }

  const query = searchQuery.value.trim().toLowerCase()
  const all = Array.from(resultMap.values())
  if (!query) return all
  return all.filter(
    p => p.label.toLowerCase().includes(query) ||
         p.key.toLowerCase().includes(query) ||
         p.formatted.toLowerCase().includes(query)
  )
})

const sections = computed(() => {
  const groups = [
    {
      id: 'identity',
      title: 'Identity & Classification',
      icon: Tag,
      accentColor: '#00305E',
      items: normalizedParams.value.filter(p => p.category === 'identity')
    },
    {
      id: 'kinematics',
      title: 'Kinematics, Route & Geometry',
      icon: Navigation,
      accentColor: '#5096BE',
      items: normalizedParams.value.filter(p => p.category === 'kinematics')
    },
    {
      id: 'environment',
      title: 'Environmental & Thermal Boundary',
      icon: Thermometer,
      accentColor: '#00AA82',
      items: normalizedParams.value.filter(p => p.category === 'environment')
    },
    {
      id: 'simulation',
      title: 'Mechanics, V2X & Compute Runtime',
      icon: Cpu,
      accentColor: '#BECD32',
      items: normalizedParams.value.filter(p => p.category === 'simulation')
    }
  ]
  return groups.filter(g => g.items.length > 0)
})

const selectedParam = computed(() => {
  if (!selectedDetailKey.value) return null
  return normalizedParams.value.find(p => p.key === selectedDetailKey.value) || null
})
</script>

<template>
  <div class="w-full flex flex-col space-y-3 text-xs">

    <!-- ================================================================== -->
    <!-- TIER 2: PARAMETER DRILL-DOWN DETAIL VIEW                           -->
    <!-- ================================================================== -->
    <div v-if="selectedParam" class="space-y-3">
      <div class="flex items-center justify-between">
        <button @click="selectedDetailKey = null"
                class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-[#00305E] text-white hover:bg-[#004982] transition-colors cursor-pointer shadow-2xs">
          <ChevronLeft :size="14" />
          <span>Back to Parameters</span>
        </button>
        <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#5096BE]/15 text-[#00305E] dark:text-[#8ecae6] border border-[#5096BE]/30">
          Key: {{ selectedParam.key }}
        </span>
      </div>

      <div class="p-4 rounded-lg border shadow-xs space-y-3"
           :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/10' : 'bg-white border-slate-200'">
        <div class="border-b pb-2.5" :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-100'">
          <div class="text-[10px] font-bold uppercase tracking-wider text-[#5096BE]">{{ selectedParam.category }} Parameter</div>
          <h4 class="text-sm font-extrabold text-[#00305E] dark:text-white mt-0.5">{{ selectedParam.label }}</h4>
        </div>

        <div class="p-3.5 rounded-md border"
             :class="store.theme === 'dark' ? 'bg-slate-950/70 border-white/5' : 'bg-[#F2F2F2]/70 border-slate-200/80'">
          <div class="text-[10px] font-bold uppercase text-slate-400 mb-1">Current Live Value</div>
          <div class="text-lg font-mono font-black text-[#00305E] dark:text-[#5096BE] break-words">
            {{ selectedParam.formatted }}
            <span v-if="selectedParam.unit" class="text-xs font-bold text-slate-500 ml-1">{{ selectedParam.unit }}</span>
          </div>
        </div>

        <!-- Recent History Table -->
        <div v-if="selectedParam.history.length > 1" class="space-y-1.5">
          <div class="flex items-center justify-between text-[10px] font-bold uppercase text-slate-400">
            <span class="flex items-center gap-1"><Activity :size="12" class="text-[#5096BE]" /> Recent Telemetry Buffer</span>
            <span class="font-mono">{{ Math.min(8, selectedParam.history.length) }} samples</span>
          </div>
          <div class="grid grid-cols-2 gap-1.5">
            <div v-for="(hVal, idx) in selectedParam.history.slice(-8).reverse()" :key="idx"
                 class="p-2 rounded-lg border flex items-center justify-between font-mono text-[11px]"
                 :class="store.theme === 'dark' ? 'bg-slate-950/50 border-white/5' : 'bg-slate-50 border-slate-200/60'">
              <span class="text-[10px] font-bold text-slate-400">T-{{ idx }}</span>
              <span class="font-bold text-slate-800 dark:text-slate-200 truncate ml-2">
                {{ formatParamValue(selectedParam.key, hVal) }} {{ selectedParam.unit }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ================================================================== -->
    <!-- TIER 1: STRUCTURED DOMAIN PARAMETER CARDS                          -->
    <!-- ================================================================== -->
    <template v-else>
      <!-- Search & Parameter Count Bar -->
      <div class="flex items-center gap-2">
        <div class="relative flex-1">
          <Search :size="13" class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          <input v-model="searchQuery"
                 type="text"
                 placeholder="Filter entity parameters..."
                 class="w-full pl-8 pr-3 py-1.5 rounded-md border text-xs outline-none transition-colors"
                 :class="store.theme === 'dark'
                   ? 'bg-slate-900 border-white/10 text-white placeholder-slate-500 focus:border-[#5096BE]'
                   : 'bg-white border-slate-200/90 text-[#00305E] placeholder-slate-400 focus:border-[#00305E]'" />
        </div>
        <span class="px-2.5 py-1.5 rounded-md font-mono font-bold text-[10px] border shrink-0"
              :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-[#8ecae6]' : 'bg-white border-slate-200 text-[#00305E]'">
          {{ normalizedParams.length }} params
        </span>
      </div>

      <div v-if="!sections.length" class="py-10 text-center text-slate-400 space-y-2">
        <Info :size="28" class="mx-auto opacity-30" />
        <p class="text-xs">No matching parameters found.</p>
      </div>

      <!-- Domain Categorized Cards -->
      <div v-for="section in sections" :key="section.id"
           class="rounded-lg border overflow-hidden shadow-2xs"
           :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/10' : 'bg-white border-slate-200/90'">
        
        <!-- Section Header -->
        <div class="px-3.5 py-2 border-b flex items-center justify-between"
             :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-[#F2F2F2]/80 border-slate-200/70'">
          <div class="flex items-center gap-2">
            <span class="w-1.5 h-3.5 rounded-full" :style="{ backgroundColor: section.accentColor }"></span>
            <component :is="section.icon" :size="13" class="text-[#00305E] dark:text-[#5096BE]" />
            <span class="font-extrabold text-[11px] uppercase tracking-wider text-[#00305E] dark:text-slate-200">
              {{ section.title }}
            </span>
          </div>
          <span class="text-[10px] font-mono font-semibold text-slate-400">{{ section.items.length }}</span>
        </div>

        <!-- Clean Key-Value Rows -->
        <div class="divide-y" :class="store.theme === 'dark' ? 'divide-white/5' : 'divide-slate-100'">
          <div v-for="item in section.items" :key="item.key"
               @click="selectedDetailKey = item.key"
               class="px-3.5 py-2 flex items-center justify-between gap-3 cursor-pointer transition-colors group"
               :class="store.theme === 'dark' ? 'hover:bg-slate-800/70' : 'hover:bg-[#F2F2F2]/60'">
            
            <div class="min-w-0 flex-1">
              <div class="font-semibold text-[11px] text-slate-600 dark:text-slate-300 group-hover:text-[#00305E] dark:group-hover:text-white transition-colors truncate">
                {{ item.label }}
              </div>
            </div>

            <div class="flex items-center gap-1.5 shrink-0 max-w-[62%]">
              <!-- Boolean Active/Inactive Pill -->
              <span v-if="item.badgeType === 'boolean-true'"
                    class="px-2 py-0.5 rounded text-[10px] font-black uppercase bg-[#00AA82]/15 text-[#00AA82] border border-[#00AA82]/30">
                Active
              </span>
              <span v-else-if="item.badgeType === 'boolean-false'"
                    class="px-2 py-0.5 rounded text-[10px] font-black uppercase bg-slate-500/15 text-slate-500 border border-slate-500/30">
                Completed
              </span>

              <!-- Weather State Pill -->
              <span v-else-if="item.badgeType === 'weather'"
                    class="px-2 py-0.5 rounded text-[10px] font-bold border"
                    :class="item.value === 'Sunny'
                      ? 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30'
                      : item.value === 'Rainy'
                        ? 'bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30'
                        : 'bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-500/30'">
                {{ item.formatted }}
              </span>

              <!-- Solver Pill -->
              <span v-else-if="item.badgeType === 'solver'"
                    class="px-2 py-0.5 rounded text-[10px] font-black font-mono bg-[#00305E] text-[#BECD32]">
                {{ String(item.value).replace('FOM', 'FEM') }}
              </span>

              <!-- 1D Nodal Temperature Array -->
              <span v-else-if="item.badgeType === 'array-temps'"
                    class="px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/25 font-mono font-bold text-[10px] text-amber-700 dark:text-amber-300 truncate"
                    :title="item.formatted">
                {{ item.formatted }}
              </span>

              <!-- Standard Formatted Value -->
              <span v-else
                    class="font-mono font-bold text-[11px] text-[#00305E] dark:text-slate-100 truncate"
                    :title="item.formatted">
                {{ item.formatted }}<span v-if="item.unit" class="text-[10px] font-normal text-slate-500 dark:text-slate-400 ml-0.5">{{ item.unit }}</span>
              </span>

              <ChevronRight :size="12" class="text-slate-300 dark:text-slate-600 group-hover:text-[#5096BE] transition-colors shrink-0" />
            </div>

          </div>
        </div>
      </div>
    </template>

  </div>
</template>
