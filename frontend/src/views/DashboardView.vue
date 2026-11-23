<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed, defineAsyncComponent } from 'vue'
import {
  Map,
  Activity,
  Database,
  BookOpen,
  Sun,
  Moon,
  Lock,
  PanelLeftClose,
  PanelLeftOpen,
  BarChart3,
  Layers,
  GitBranch,
  Thermometer,
  TrendingDown,
  Car,
  X,
  Info,
  Radio,
  Signpost,
  Droplets,
  Plane,
  AlertTriangle,
  ShieldCheck
} from 'lucide-vue-next'
import DashboardMap from '../components/dashboard/DashboardMap.vue'
import MetadataPanel from '../components/dashboard/MetadataPanel.vue'
import ObjectInspector from '../components/dashboard/ObjectInspector.vue'

// Lazy-loaded drawer views and tools (Code-splitting for sub-second startup)
const BoussinesqViewer = defineAsyncComponent(() => import('../components/dashboard/BoussinesqViewer.vue'))
const StatisticsCharts = defineAsyncComponent(() => import('../components/dashboard/StatisticsCharts.vue'))
const TreeRenderer = defineAsyncComponent(() => import('../components/dashboard/TreeRenderer.vue'))
const PredictionPlot = defineAsyncComponent(() => import('../components/dashboard/PredictionPlot.vue'))
const ThermalSimulation = defineAsyncComponent(() => import('../components/dashboard/ThermalSimulation.vue'))
const FiwareInsights = defineAsyncComponent(() => import('../components/dashboard/FiwareInsights.vue'))
const DocumentationViewer = defineAsyncComponent(() => import('../components/dashboard/DocumentationViewer.vue'))
import { useDashboardStore } from '../stores/dashboard'

const store = useDashboardStore()

// Navigation & Drawer State
const isDrawerOpen = ref(true)
const activeDrawerTab = ref<'telemetry' | 'metadata' | 'foda' | 'thermal' | 'boussinesq' | 'prediction'>('telemetry')

// Main canvas reference & responsive width tracking
const mainRef = ref<HTMLElement | null>(null)
const windowWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1600)
const mainWidth = ref(1000)
let mainResizeObserver: ResizeObserver | null = null

// Resizable Drawer Width (Bounded to min 420px so tabs, tables & cross-sections never cramp)
const getInitialDrawerWidth = () => {
  if (typeof window === 'undefined') return 460
  const w = window.innerWidth
  const maxW = w < 2000 ? Math.floor(w * 0.48) : Math.min(1100, Math.floor(w * 0.45))
  const saved = localStorage.getItem('road_drawer_width')
  if (saved) {
    const num = Number(saved)
    if (!isNaN(num) && num >= 420) {
      return Math.min(maxW, num)
    }
  }
  if (w >= 3000) return 680
  if (w >= 2200) return 560
  if (w >= 1600) return 480
  return Math.min(460, Math.max(420, Math.floor(w * 0.32)))
}

const drawerWidth = ref(getInitialDrawerWidth())
const isDragging = ref(false)

const startResize = (e: MouseEvent) => {
  e.preventDefault()
  isDragging.value = true

  const startX = e.clientX
  const startWidth = drawerWidth.value

  const onMouseMove = (moveEvent: MouseEvent) => {
    if (!isDragging.value) return
    const deltaX = moveEvent.clientX - startX
    const w = window.innerWidth
    const minW = Math.max(420, Math.min(460, Math.floor(w * 0.28)))
    const maxW = w < 2000 ? Math.floor(w * 0.48) : Math.min(1100, Math.floor(w * 0.45))
    drawerWidth.value = Math.max(minW, Math.min(maxW, startWidth + deltaX))
    mainWidth.value = Math.max(200, w - 64 - drawerWidth.value)
  }

  const onMouseUp = () => {
    if (isDragging.value) {
      isDragging.value = false
      localStorage.setItem('road_drawer_width', String(drawerWidth.value))
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }

  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

const togglePresetWidth = () => {
  const w = typeof window !== 'undefined' ? window.innerWidth : 1600
  const maxW = w < 2000 ? Math.floor(w * 0.48) : Math.min(1100, Math.floor(w * 0.45))
  const stdW = w >= 2200 ? 560 : 460
  const wideW = Math.min(maxW, w >= 2200 ? 840 : Math.floor(w * 0.46))

  if (drawerWidth.value > (stdW + wideW) / 2) {
    drawerWidth.value = stdW
  } else {
    drawerWidth.value = wideW
  }
  mainWidth.value = Math.max(200, w - 64 - drawerWidth.value)
  localStorage.setItem('road_drawer_width', String(drawerWidth.value))
}

const headerLOD = computed<'full' | 'compact' | 'minimal' | 'micro'>(() => {
  const w = mainWidth.value
  if (w >= 1150) return 'full'
  if (w >= 820) return 'compact'
  if (w >= 520) return 'minimal'
  return 'micro'
})

const warningDotColorClass = computed(() => {
  const warnings = store.digitalShadowRaw?.map_layers?.warnings?.features || []
  if (!warnings.length) return 'bg-[#00AA82]'
  const hasNew = warnings.some((w: any) => (w.properties?.State || w.properties?.status) === 'New')
  if (hasNew) return 'bg-[#AF2D37] animate-pulse'
  const hasUnderInspection = warnings.some((w: any) => (w.properties?.State || w.properties?.status) === 'Under Inspection')
  if (hasUnderInspection) return 'bg-amber-500 animate-pulse'
  return 'bg-[#00AA82]'
})

const handleNavigate = (viewId: 'digital-shadow' | 'fiware-status' | 'documentation', disabled?: boolean) => {
  if (disabled) return
  if (store.currentView === viewId) return
  store.setCurrentView(viewId)
}

const drawerTabs = computed(() => {
  const t = store.selectedType
  const isVeh = t === 'SingleVehicleStateDS'
  const isRoad = t === 'SingleRoadSegmentStateDS' || t === 'SingleRoadPointStateDS'
  
  if (!t) {
    return [
      { id: 'telemetry', label: drawerWidth.value < 400 ? 'Overview' : 'Corridor Overview', title: 'Corridor Overview', icon: BarChart3 },
    ]
  }

  // Calculate actual per-tab width (24px horizontal padding)
  const tabCount = isVeh ? 5 : isRoad ? 4 : 2
  const tabW = (drawerWidth.value - 24) / tabCount

  let tabLabels = {
    telemetry: 'Inspector',
    params: 'Parameters',
    foda: 'HPN & FODA',
    thermal: '1D Thermal',
    boussinesq: '2D Load',
    prediction: 'Prediction'
  }

  if (tabW < 58) {
    tabLabels = {
      telemetry: '',
      params: '',
      foda: '',
      thermal: '',
      boussinesq: '',
      prediction: ''
    }
  } else if (tabW < 74) {
    tabLabels = {
      telemetry: 'Status',
      params: 'Param',
      foda: 'HPN',
      thermal: 'Heat',
      boussinesq: 'Load',
      prediction: 'Pred'
    }
  } else if (tabW < 90) {
    tabLabels = {
      telemetry: 'Status',
      params: 'Params',
      foda: 'HPN',
      thermal: 'Thermal',
      boussinesq: '2D Load',
      prediction: 'Predict'
    }
  } else if (tabW < 115) {
    tabLabels = {
      telemetry: 'Inspector',
      params: 'Params',
      foda: 'HPN',
      thermal: 'Thermal',
      boussinesq: '2D Load',
      prediction: 'Prediction'
    }
  }

  const tabs: { id: string; label: string; title: string; icon: any }[] = [
    {
      id: 'telemetry',
      label: tabLabels.telemetry,
      title: 'Vehicle Status & Telemetry Inspector',
      icon: BarChart3
    },
    {
      id: 'metadata',
      label: tabLabels.params,
      title: 'Kinematic & Physical Parameters',
      icon: Layers
    }
  ]

  // HPN & FODA is exclusively for Vehicle selection
  if (isVeh) {
    tabs.push({
      id: 'foda',
      label: tabLabels.foda,
      title: 'Heraklit Hybrid Petri Net & FODA Feature Tree',
      icon: GitBranch
    })
  }

  // 1D Thermal is for Vehicle and Road Segment / Point selection
  if (isVeh || isRoad) {
    tabs.push({
      id: 'thermal',
      label: tabLabels.thermal,
      title: '1D Pavement Structural Thermal Cross-Section',
      icon: Thermometer
    })
  }

  // State Over Time Prediction is for Road Segment / Point selection
  if (isRoad) {
    tabs.push({
      id: 'prediction',
      label: tabLabels.prediction,
      title: 'State Over Time Rutting & Displacement Prediction',
      icon: Activity
    })
  }

  // 2D Pavement Cross-Section (Boussinesq Analytical Load) is for Vehicle selection
  if (isVeh) {
    tabs.push({
      id: 'boussinesq',
      label: tabLabels.boussinesq,
      title: '2D Pavement Cross-Section Load & Stress Distribution (Boussinesq)',
      icon: TrendingDown
    })
  }

  return tabs
})

// Flightradar24 UX: Open drawer when an object is clicked; collapse drawer when selection is cleared
watch(() => store.selectedType, (newVal, oldVal) => {
  if (newVal) {
    isDrawerOpen.value = true
    const validIds = drawerTabs.value.map(tab => tab.id)
    if (!validIds.includes(activeDrawerTab.value)) {
      activeDrawerTab.value = 'telemetry'
    }
  } else if (oldVal && !newVal) {
    isDrawerOpen.value = false
    activeDrawerTab.value = 'telemetry'
  }
})

const navItems = computed(() => [
  { id: 'digital-shadow' as const, label: 'Digital Shadow', icon: Map },
  { id: 'fiware-status' as const, label: 'Data Broker', icon: Database, disabled: !store.fiwareEnabled },
  { id: 'documentation' as const, label: 'Documentation', icon: BookOpen },
])

const vehicleLabel = computed(() => {
  const f = store.selectedFeature
  const rawId = f?.properties?.id ?? f?.properties?.ID ?? store.selectedData?.id ?? store.selectedData?.ID
  if (rawId == null) return 'Selected'
  const strId = String(rawId)
  return strId.length > 8 ? strId.slice(-4) : strId
})

// Polymorphic Header Metadata for all 7 Clickable Object Types
const inspectorHeader = computed(() => {
  const t = store.selectedType
  const p = store.selectedData?.panel
  const props = store.selectedFeature?.properties || {}

  if (t === 'SingleVehicleStateDS') {
    return {
      icon: Car,
      badgeClass: 'bg-blue-600 text-white',
      title: `HGV #${vehicleLabel.value}`,
      subtitle: p ? `${p.origin_name} → ${p.destination_name}` : 'Live Federation & Telemetry',
      labels: ['Vehicle', 'Kinematics', 'Boussinesq']
    }
  }
  if (t === 'SingleRoadSegmentStateDS' || t === 'SingleRoadPointStateDS') {
    const rawTitle = String(p?.name || props.name || `Road Section #${props.id || ''}`)
    const cleanTitle = rawTitle.replace(/\s*\[[^\]]+\]\s*$/, '').trim()
    return {
      icon: Layers,
      badgeClass: 'bg-emerald-600 text-white',
      title: cleanTitle,
      subtitle: `${p?.carriageway || props.carriageway || 'Carriageway'} • Health ${p?.health_pct ?? props.state ?? 100}%`,
      labels: ['Road Twin', 'Structural Health']
    }
  }
  if (t === 'SingleExitStateDS') {
    const rawName = String(p?.name || props.name || '').trim()
    const code = String(p?.code || '').trim()
    const cleanTitle =
      code && rawName && !rawName.toLowerCase().startsWith(code.toLowerCase())
        ? `${code} ${rawName}`
        : rawName || code || 'Highway Junction'
    return {
      icon: Signpost,
      badgeClass: 'bg-[#003399] text-white',
      title: cleanTitle,
      subtitle: p ? `${p.junction_type} • km ${Number(p.kilometer).toFixed(1)}` : 'Autobahn O/D Junction',
      labels: ['Junction', 'Network Graph']
    }
  }
  if (t === 'SingleWaterStateDS') {
    return {
      icon: Droplets,
      badgeClass: 'bg-cyan-600 text-white',
      title: p?.name || props.name || 'Water Source',
      subtitle: p ? `${p.water_type} • 5 km Subgrade Cooling Zone` : 'Hydrological Subgrade Node',
      labels: ['Hydrology', 'Environment']
    }
  }
  if (t === 'SingleRoadsideUnitsStateDS') {
    return {
      icon: Radio,
      badgeClass: 'bg-purple-600 text-white',
      title: p?.name || props.name || 'Roadside Unit',
      subtitle: p ? `${p.town} • ${p.sensor_source}` : 'V2X Edge & Weather Station',
      labels: ['RSU Node', 'V2X Edge', 'IoT']
    }
  }
  if (t === 'SingleDroneStateDS') {
    return {
      icon: Plane,
      badgeClass: 'bg-indigo-600 text-white',
      title: `Inspection UAV #${p?.drone_id ?? props.id ?? ''}`,
      subtitle: p ? `${p.flight_state} • Target Warning #${p.target_warning_id}` : 'Autonomous Aerial Drone',
      labels: ['Drone UAV', 'Autonomous Flight']
    }
  }
  if (t === 'SingleWarningStateDS') {
    return {
      icon: AlertTriangle,
      badgeClass: 'bg-rose-600 text-white',
      title: p?.anomaly_type || `Warning #${props.id ?? ''}`,
      subtitle: p ? `Status: ${p.status} • km ${Number(p.kilometer).toFixed(2)}` : 'Structural Road Anomaly',
      labels: ['Structural Wear', 'Anomaly Alert']
    }
  }
  if (t === 'SingleEmbeddedSensorStateDS' || t === 'EmbeddedSensor') {
    return {
      icon: Activity,
      badgeClass: 'bg-teal-600 text-white',
      title: p?.name || props.name || 'Embedded Sensor Station',
      subtitle: p ? `Station ${p.station_id} • km ${Number(p.kilometer || 0).toFixed(1)}` : '6-Channel Pavement DAQ',
      labels: ['DAQ', 'Sensors']
    }
  }
  return {
    icon: Layers,
    badgeClass: 'bg-slate-100 dark:bg-slate-800 text-slate-500',
    title: 'Corridor Inspector',
    subtitle: 'Click any of the 8 map entity types to inspect',
    labels: []
  }
})

const inspectorFooterLabel = computed(() => {
  switch (store.selectedType) {
    case 'SingleVehicleStateDS': return 'Vehicle Inspector'
    case 'SingleRoadSegmentStateDS':
    case 'SingleRoadPointStateDS': return 'Road Section Inspector'
    case 'SingleRoadsideUnitsStateDS': return 'RSU Edge Inspector'
    case 'SingleExitStateDS': return 'Junction Inspector'
    case 'SingleWaterStateDS': return 'Hydrology Inspector'
    case 'SingleDroneStateDS': return 'UAV Mission Inspector'
    case 'SingleWarningStateDS': return 'Anomaly Inspector'
    case 'SingleEmbeddedSensorStateDS':
    case 'EmbeddedSensor': return 'Sensor Station Inspector'
    default: return 'Corridor Inspector'
  }
})

const vehicleV2XInfo = computed(() => {
  if (store.selectedType !== 'SingleVehicleStateDS' || !store.selectedFeature) return null

  const stats = store.selectedData?.stats || {}
  const lastFrom = (arr: any) => (Array.isArray(arr) && arr.length > 0 ? arr[arr.length - 1] : null)

  const statsRsuName = lastFrom(stats['RoadsideUnitName'])
  const statsRsuTown = lastFrom(stats['RoadsideUnitTown'])
  const statsRsuDist = lastFrom(stats['RoadsideUnitDist'])
  const statsRsuStation = lastFrom(stats['RoadsideUnitStation'])

  const props = store.selectedFeature.properties || {}
  const state = props.State || props

  const rsuName = statsRsuName || state.RoadsideUnitName || (state.RoadsideUnitStation != null ? `RSU @ km ${state.RoadsideUnitStation}` : 'RSU Edge Node')
  const rsuTown = statsRsuTown || state.RoadsideUnitTown || 'A14 Corridor'
  const distVal = statsRsuDist != null ? Number(statsRsuDist) : (state.RoadsideUnitDist != null ? Number(state.RoadsideUnitDist) : null)
  const distLabel = distVal != null ? `${distVal.toFixed(1)} km` : 'In coverage'
  const stationVal = statsRsuStation != null ? statsRsuStation : state.RoadsideUnitStation
  const stationLabel = stationVal != null ? `km ${Number(stationVal).toFixed(1)}` : ''

  const dVal = distVal != null ? distVal : 3.0
  const rssi = Math.round(-55 - (dVal * 2.8))
  const signalLabel = rssi > -68 ? `${rssi} dBm (High)` : rssi > -80 ? `${rssi} dBm (Good)` : `${rssi} dBm (Fair)`

  return {
    name: rsuName,
    town: rsuTown,
    station: stationLabel,
    dist: distLabel,
    rssi,
    signal: signalLabel,
    standard: 'ETSI ITS-G5 / IEEE 1516 HLA'
  }
})

const updateDimensions = () => {
  if (typeof window !== 'undefined') {
    windowWidth.value = window.innerWidth
  }
  if (mainRef.value) {
    mainWidth.value = mainRef.value.clientWidth
  } else {
    mainWidth.value = Math.max(200, windowWidth.value - 64 - (isDrawerOpen.value ? drawerWidth.value : 0))
  }
}

onMounted(() => {
  if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('dark', store.theme === 'dark')
  }
  store.startStream()
  store.checkFiwareStatus()

  updateDimensions()
  window.addEventListener('resize', updateDimensions)

  if (typeof ResizeObserver !== 'undefined' && mainRef.value) {
    mainResizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        mainWidth.value = entry.contentRect.width
      }
    })
    mainResizeObserver.observe(mainRef.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', updateDimensions)
  if (mainResizeObserver) mainResizeObserver.disconnect()
})
</script>

<template>
  <div :class="[store.theme === 'dark' ? 'dark bg-slate-950 text-slate-100' : 'bg-[#F2F2F2] text-[#3C3C3B]']"
       class="flex flex-col h-screen w-screen overflow-hidden font-sans">
    
    <div class="flex flex-1 min-h-0 overflow-hidden">
      
      <!-- ======================================================== -->
      <!-- TIER 1: SLIM ICON NAVIGATION RAIL (64px)                 -->
      <!-- ======================================================== -->
      <nav class="w-16 flex-shrink-0 z-30 flex flex-col items-center justify-between py-4 border-r transition-colors duration-300"
           :class="store.theme === 'dark' ? 'bg-[#001d3a] border-white/10' : 'bg-white border-slate-200/90'">
        
        <div class="flex flex-col items-center gap-4">
          <div class="h-10 w-10 rounded-xl flex items-center justify-center p-1 border shadow-sm transition-transform hover:scale-105 cursor-pointer bg-white border-[#00305E]/20"
               @click="handleNavigate('digital-shadow')"
               title="Digital Twin Road — Cyber-Physical Highway Platform">
            <Layers :size="20" class="text-[#00305E]" />
          </div>

          <div class="w-8 h-0.5 dtr-accent-bar rounded-full my-0.5"></div>

          <div class="flex flex-col items-center gap-2">
            <div v-for="item in navItems" :key="item.id" class="relative group">
              <button @click="handleNavigate(item.id, item.disabled)"
                      :disabled="item.disabled"
                      class="relative h-11 w-11 rounded-xl flex items-center justify-center transition-all outline-none"
                      :class="[
                        store.currentView === item.id
                          ? 'bg-[#00305E] text-white shadow-lg shadow-[#00305E]/30 ring-2 ring-[#5096BE]/40'
                          : 'text-[#706F6F] dark:text-slate-400 hover:text-[#00305E] dark:hover:text-white hover:bg-[#F2F2F2] dark:hover:bg-white/10',
                        item.disabled ? 'opacity-30 cursor-not-allowed hover:bg-transparent' : 'cursor-pointer'
                      ]">
                <component :is="item.icon" :size="20" />
                <Lock v-if="item.disabled" :size="10" class="absolute top-1.5 right-1.5 opacity-60" />
                
                <span v-if="store.currentView === item.id"
                      class="absolute -left-2.5 top-1/2 -translate-y-1/2 w-1.5 h-6 bg-[#BECD32] rounded-r-full"></span>
              </button>

              <div class="absolute left-full ml-3 top-1/2 -translate-y-1/2 px-2.5 py-1.5 bg-[#00305E] text-white text-xs font-semibold rounded-lg shadow-xl whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 border border-[#5096BE]/40">
                {{ item.label }}
                <span v-if="item.disabled" class="text-[10px] text-[#BECD32] block font-normal">(Offline)</span>
              </div>
            </div>
          </div>
        </div>

        <div class="flex flex-col items-center gap-3">
          <div class="relative group cursor-pointer" :title="store.isConnected ? 'SSE Live Connected' : 'Connecting to Stream...'">
            <div class="h-8 w-8 rounded-lg flex items-center justify-center border"
                 :class="store.theme === 'dark' ? 'bg-slate-800/80 border-white/10' : 'bg-[#F2F2F2] border-slate-200'">
              <span class="relative flex h-2.5 w-2.5">
                <span class="relative inline-flex rounded-full h-2.5 w-2.5"
                      :class="store.isConnected ? 'bg-[#849218] dark:bg-[#BECD32]' : 'bg-amber-500'"></span>
              </span>
            </div>
            <div class="absolute left-full ml-3 top-1/2 -translate-y-1/2 px-2.5 py-1 bg-[#00305E] text-white text-xs rounded-lg shadow-xl whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 border border-[#5096BE]/40">
              {{ store.isConnected ? 'Live Connected' : 'Connecting...' }}
            </div>
          </div>

          <button @click="store.toggleTheme"
                  class="h-10 w-10 rounded-xl flex items-center justify-center transition-colors text-[#706F6F] dark:text-slate-300 hover:text-[#00305E] dark:hover:text-white hover:bg-[#F2F2F2] dark:hover:bg-white/10 border border-transparent hover:border-slate-200 dark:hover:border-white/10 cursor-pointer"
                  :title="`Switch to ${store.theme === 'light' ? 'dark' : 'light'} mode`">
            <Sun v-if="store.theme === 'dark'" :size="18" />
            <Moon v-else :size="18" />
          </button>
        </div>
      </nav>

      <!-- ======================================================== -->
      <!-- TIER 2: POLYMORPHIC SLIDE-OUT CONTEXT DRAWER             -->
      <!-- ======================================================== -->
      <aside v-if="store.currentView === 'digital-shadow'"
             class="flex-shrink-0 z-20 flex flex-col border-r overflow-hidden relative"
             :style="{ width: isDrawerOpen ? `${drawerWidth}px` : '0px' }"
             :class="[
               store.theme === 'dark' ? 'bg-slate-900/95 border-white/10' : 'bg-white border-slate-200/90',
               isDragging ? 'select-none transition-none' : 'transition-[width] duration-300',
               isDrawerOpen ? '' : 'border-r-0'
             ]">
        
        <div class="h-full flex flex-col min-h-0" :style="{ width: `${drawerWidth}px` }">
          
          <!-- Polymorphic Drawer Header — "FUTURE ROAD SYSTEM" Hero Banner Style -->
          <div class="h-[68px] px-4 md:px-5 shrink-0 flex items-center justify-between gap-2 dtr-hero-gradient text-white relative overflow-hidden">
            <!-- Decorative geometric network mesh watermark -->
            <svg class="absolute right-0 top-0 h-full w-36 opacity-20 pointer-events-none" viewBox="0 0 140 70" fill="none">
              <line x1="20" y1="10" x2="75" y2="25" stroke="#5096BE" stroke-width="1" />
              <line x1="75" y1="25" x2="125" y2="12" stroke="#ffffff" stroke-width="1" />
              <line x1="75" y1="25" x2="95" y2="58" stroke="#BECD32" stroke-width="1" />
              <line x1="125" y1="12" x2="95" y2="58" stroke="#5096BE" stroke-width="1" />
              <line x1="20" y1="10" x2="45" y2="55" stroke="#ffffff" stroke-width="0.8" />
              <line x1="45" y1="55" x2="95" y2="58" stroke="#5096BE" stroke-width="1" />
              <circle cx="20" cy="10" r="2.5" fill="#5096BE" />
              <circle cx="75" cy="25" r="3" fill="#BECD32" />
              <circle cx="125" cy="12" r="2.5" fill="#ffffff" />
              <circle cx="95" cy="58" r="2.5" fill="#5096BE" />
              <circle cx="45" cy="55" r="2" fill="#ffffff" />
            </svg>

            <div class="flex items-center gap-2.5 min-w-0 flex-1 relative z-10">
              <div class="h-9 w-9 rounded-lg flex items-center justify-center shrink-0 shadow-sm border border-white/25 bg-white/15 text-white backdrop-blur-xs">
                <component :is="inspectorHeader.icon" :size="17" />
              </div>
              <div class="min-w-0 flex-1">
                <h3 class="font-bold text-sm truncate text-white leading-snug">
                  {{ inspectorHeader.title }}
                </h3>
                <p class="text-[11px] text-blue-100/85 truncate leading-tight">
                  {{ inspectorHeader.subtitle }}
                </p>
              </div>
            </div>

            <!-- Drawer Controls -->
            <div class="flex items-center gap-1 shrink-0 relative z-10">
              <button @click="togglePresetWidth"
                      class="px-2 py-1 rounded-md text-[10px] font-bold border border-white/25 bg-white/10 text-white hover:bg-white/20 transition-colors cursor-pointer shrink-0"
                      :title="drawerWidth > 500 ? 'Snap to Compact Width' : 'Snap to Expanded View'">
                {{ drawerWidth > 500 ? 'Compact' : 'Expand' }}
              </button>
              <button @click="isDrawerOpen = false"
                      class="p-1.5 rounded-md text-white/80 hover:text-white hover:bg-white/15 transition-colors cursor-pointer shrink-0"
                      title="Collapse Drawer">
                <PanelLeftClose :size="18" />
              </button>
            </div>

            <!-- Signature 3-Area Accent Strip -->
            <div class="absolute bottom-0 left-0 right-0 h-[3px] dtr-accent-bar"></div>
          </div>

          <!-- Drawer Tab Strip -->
          <div class="px-2 md:px-3 py-1.5 border-b shrink-0 flex items-center gap-1 bg-[#F2F2F2]/70 dark:bg-slate-950/40"
               :class="store.theme === 'dark' ? 'border-white/5' : 'border-slate-200/80'">
            <button v-for="tab in drawerTabs" :key="tab.id"
                    @click="activeDrawerTab = tab.id as any"
                    class="flex-1 flex items-center justify-center gap-1 py-1.5 px-1 rounded-md font-semibold transition-all cursor-pointer whitespace-nowrap min-w-0"
                    :class="[
                      activeDrawerTab === tab.id
                        ? 'bg-[#00305E] text-white shadow-sm shadow-[#00305E]/25 ring-1 ring-[#5096BE]/40'
                        : 'text-[#706F6F] dark:text-slate-400 hover:text-[#00305E] dark:hover:text-white hover:bg-white dark:hover:bg-slate-800',
                      drawerTabs.length >= 5 ? 'text-[11px]' : 'text-xs px-2'
                    ]"
                    :title="tab.title || tab.label">
              <component :is="tab.icon" :size="drawerTabs.length >= 5 ? 12 : 13" class="shrink-0" :class="activeDrawerTab === tab.id ? 'text-[#BECD32]' : ''" />
              <span v-if="tab.label" class="truncate">{{ tab.label }}</span>
            </button>
          </div>

          <!-- Drawer Content Body (Scrollable) -->
          <div class="flex-1 overflow-y-auto p-4 min-h-0">
            
            <!-- Fallback V2X Edge Connection Card (only if federation_contract is not yet populated) -->
            <div v-if="store.selectedType === 'SingleVehicleStateDS' && vehicleV2XInfo && !store.selectedData?.federation_contract && !store.selectedData?.panel?.federation_contract"
                 class="p-3 mb-4 rounded-xl border flex items-center justify-between gap-3 shadow-xs transition-all"
                 :class="store.theme === 'dark' ? 'bg-cyan-950/25 border-cyan-500/25 text-slate-200' : 'bg-cyan-50/80 border-cyan-200 text-slate-800'">
              <div class="flex items-center gap-2.5 min-w-0">
                <div class="h-8 w-8 rounded-lg bg-cyan-500/15 text-cyan-600 dark:text-cyan-400 border border-cyan-500/30 flex items-center justify-center shrink-0">
                  <Radio :size="16" class="animate-pulse" />
                </div>
                <div class="min-w-0">
                  <div class="flex items-center gap-1.5 text-[10px] font-bold text-cyan-600 dark:text-cyan-400 uppercase tracking-wider">
                    <span>Active V2X Edge Node</span>
                    <span class="inline-block w-1.5 h-1.5 rounded-full bg-cyan-500"></span>
                  </div>
                  <p class="text-xs font-bold truncate">{{ vehicleV2XInfo.name }}</p>
                  <p class="text-[10px] text-slate-500 dark:text-slate-400 truncate">Station {{ vehicleV2XInfo.station }} • Distance: <span class="font-semibold text-amber-600 dark:text-amber-400">{{ vehicleV2XInfo.dist }}</span></p>
                </div>
              </div>
              <div class="text-right shrink-0">
                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 border border-cyan-500/30">
                  {{ vehicleV2XInfo.signal }}
                </span>
                <p class="text-[9px] text-slate-500 dark:text-slate-400 mt-0.5">{{ vehicleV2XInfo.standard }}</p>
              </div>
            </div>

            <!-- Tab 1: Polymorphic Entity Inspector + Fleet Trend Charts -->
            <div v-show="activeDrawerTab === 'telemetry'" class="flex flex-col space-y-4">
              
              <!-- Polymorphic Inspector Card for all 8 Entity Types -->
              <ObjectInspector v-if="store.selectedType && store.selectedData?.panel" />

              <!-- Fleet / Entity Trend Analytics -->
              <div v-if="store.selectedType !== 'SingleExitStateDS'"
                   class="rounded-lg border p-4 shadow-sm"
                   :class="store.theme === 'dark' ? 'bg-slate-950/40 border-white/5' : 'bg-slate-50/60 border-slate-200/60'">
                <div class="flex items-center justify-between mb-3">
                  <h4 class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-2">
                    <BarChart3 :size="14" class="text-[#00305E] dark:text-sky-400" />
                    <span>{{ store.selectedType === 'SingleVehicleStateDS' ? 'Vehicle Time-Series Telemetry' : 'Corridor & Entity Analytics' }}</span>
                  </h4>
                </div>
                <div class="h-[340px] md:h-[380px] xl:h-[420px] w-full">
                  <StatisticsCharts />
                </div>
              </div>
            </div>

            <!-- Tab 2: Selection Parameters -->
            <div v-show="activeDrawerTab === 'metadata'">
              <div v-if="store.selectedType" class="space-y-3">
                <div class="flex items-center justify-between pb-2 border-b"
                     :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
                  <div>
                    <h4 class="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-100">Entity Parameters</h4>
                    <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">Searchable physical configuration and state attributes for the selected asset.</p>
                  </div>
                </div>
                <MetadataPanel />
              </div>
              <div v-else class="text-center py-12 px-4 text-slate-400">
                <Layers :size="32" class="mx-auto mb-2 opacity-30" />
                <p class="text-xs">Click on any road segment, junction, water source, vehicle, RSU, drone, or warning on the map to inspect its parameters.</p>
              </div>
            </div>

            <!-- Tab 3: Heraklit Hybrid Petri Net & FODA Feature Model -->
            <div v-show="activeDrawerTab === 'foda'">
              <div v-if="store.selectedData?.hpn_graph || store.selectedType === 'SingleVehicleStateDS'" class="space-y-3">
                <div class="flex items-center justify-between pb-2 border-b"
                     :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
                  <div>
                    <h4 class="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-100">Heraklit HPN &amp; Synthesized Code</h4>
                    <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">Compositional Hybrid Petri Net graph, FODA variability model, and generated runtime.</p>
                  </div>
                </div>
                <TreeRenderer :drawer-width="drawerWidth" />
              </div>
              <div v-else class="text-center py-12 px-4 text-slate-400">
                <GitBranch :size="32" class="mx-auto mb-2 opacity-30" />
                <p class="text-xs">Select a moving vehicle, Roadside Unit (RSU), or road segment to inspect its Compositional Hybrid Petri Net (Heraklit algebra), FODA feature tree, and synthesized Python code.</p>
              </div>
            </div>

            <!-- Tab 4: 1D Thermal Simulation (Vehicle & Road Segment) -->
            <div v-show="activeDrawerTab === 'thermal'">
              <div v-if="store.selectedType === 'SingleVehicleStateDS' || store.selectedType === 'SingleRoadSegmentStateDS' || store.selectedType === 'SingleRoadPointStateDS'" class="space-y-3">
                <div class="flex items-center justify-between pb-2 border-b"
                     :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
                  <div>
                    <h4 class="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-100">1D Thermal Conduction Profile</h4>
                    <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">Multi-layer Fourier depth thermal distribution calibrated to RStO 12 material conductivities.</p>
                  </div>
                </div>
                <ThermalSimulation :drawer-width="drawerWidth" />
              </div>
              <div v-else class="text-center py-12 px-4 text-slate-400">
                <Thermometer :size="32" class="mx-auto mb-2 opacity-30" />
                <p class="text-xs">Select a vehicle or road section to view the 1D thermal finite element depth profile.</p>
              </div>
            </div>

            <!-- Tab 5: 2D Pavement Cross-Section (Boussinesq Real-Time Load) -->
            <div v-show="activeDrawerTab === 'boussinesq' && store.selectedType === 'SingleVehicleStateDS'" class="space-y-3">
              <BoussinesqViewer :drawer-width="drawerWidth" />
            </div>

            <!-- Tab 6: State Over Time Prediction (Road Segment / Point) -->
            <div v-show="activeDrawerTab === 'prediction'">
              <div v-if="store.selectedType === 'SingleRoadSegmentStateDS' || store.selectedType === 'SingleRoadPointStateDS'" class="space-y-3">
                <div class="flex items-center justify-between pb-2 border-b"
                     :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
                  <div>
                    <h4 class="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-100">Long-Term Pavement Prediction</h4>
                    <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">15-year lifecycle pavement deformation forecast across cross-section.</p>
                  </div>
                </div>
                <PredictionPlot />
              </div>
              <div v-else class="text-center py-12 px-4 text-slate-400">
                <Activity :size="32" class="mx-auto mb-2 opacity-30" />
                <p class="text-xs">Select a road section or point on the map to inspect its long-term lifecycle health and rutting prediction.</p>
              </div>
            </div>

          </div>

          <!-- Drawer Footer -->
          <div class="p-3 border-t shrink-0 flex items-center justify-between gap-2 text-xs text-slate-400"
               :class="store.theme === 'dark' ? 'border-white/5 bg-slate-950/40' : 'border-slate-100 bg-slate-50/50'">
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-[11px] text-slate-400 font-medium">{{ inspectorFooterLabel }}</span>
            </div>
            <button v-if="store.selectedType"
                    @click="store.clearSelection()"
                    class="text-[11px] font-semibold text-rose-500 hover:underline flex items-center gap-1 cursor-pointer shrink-0">
              <X :size="12" /> Clear Selection
            </button>
          </div>

        </div>

        <!-- Draggable Resizer Gutter -->
        <div v-if="isDrawerOpen"
             @mousedown="startResize"
             @dblclick="togglePresetWidth"
             class="absolute top-0 right-0 w-2.5 h-full cursor-col-resize z-30 group flex items-center justify-center hover:bg-blue-500/20 active:bg-blue-500/40 transition-colors select-none"
             title="Drag to resize drawer (Double-click to toggle width)">
          <div class="w-1 h-10 rounded-full bg-slate-300 dark:bg-slate-700 group-hover:bg-blue-500 group-active:bg-blue-600 transition-colors shadow-sm"></div>
        </div>
      </aside>

      <!-- Invisible mouse capture shield while dragging -->
      <div v-if="isDragging"
           class="fixed inset-0 z-50 cursor-col-resize select-none pointer-events-auto"></div>

      <!-- ======================================================== -->
      <!-- TIER 3: MAIN VIEWPORT CANVAS (Full-Screen Visualizer)   -->
      <!-- ======================================================== -->
      <main ref="mainRef" class="flex-1 flex flex-col relative min-w-0 overflow-hidden"
            :class="store.theme === 'dark' ? 'bg-slate-950' : 'bg-[#F2F2F2]'">
        
        <!-- Adaptive Level of Detail (LOD) Top Header Bar -->
        <header class="h-[68px] px-3 sm:px-4 md:px-6 flex items-center [align-items:safe_center] justify-between shrink-0 border-b backdrop-blur-md z-10 gap-2 md:gap-3 min-w-0 relative"
                :class="store.theme === 'dark' ? 'bg-slate-900/85 border-white/10' : 'bg-white/95 border-slate-200'">
          
          <!-- Left: Drawer Toggle Button & View Title -->
          <div class="flex items-center gap-2 md:gap-3 shrink-0 min-w-0">
            <button v-if="store.currentView === 'digital-shadow' && !isDrawerOpen"
                    @click="isDrawerOpen = true"
                    class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border text-xs font-bold shadow-xs transition-all cursor-pointer shrink-0"
                    :class="store.theme === 'dark' ? 'bg-[#00305E] border-[#5096BE]/40 text-white hover:bg-[#004982]' : 'bg-[#00305E] border-[#00305E] text-white hover:bg-[#004982]'"
                    title="Open Inspector Drawer">
              <PanelLeftOpen :size="15" class="text-[#BECD32]" />
              <span v-if="headerLOD !== 'micro'">Inspector</span>
            </button>

            <div class="flex flex-col min-w-0">
              <span v-if="headerLOD === 'full' || headerLOD === 'compact'"
                    class="text-[9px] font-extrabold uppercase tracking-[0.18em] text-[#5096BE] leading-none mb-0.5">
                Digital Twin Road • Future Road System
              </span>
              <div class="flex items-center gap-2 shrink-0">
                <h2 class="font-extrabold tracking-tight whitespace-nowrap shrink-0"
                    :class="[
                      store.theme === 'dark' ? 'text-white' : 'text-[#00305E]',
                      headerLOD === 'full' ? 'text-base' : 'text-sm'
                    ]">
                  {{
                    store.currentView === 'digital-shadow' ? 'Digital Shadow' :
                    store.currentView === 'fiware-status' ? (headerLOD === 'minimal' || headerLOD === 'micro' ? 'Broker' : 'Data Broker & Context') :
                    'Documentation'
                  }}
                </h2>
              </div>
            </div>
          </div>

          <!-- Right: Compact Simulation Speed & Merged Fleet Telemetry Counters -->
          <div v-if="store.currentView === 'digital-shadow'"
               class="flex items-center gap-2 shrink-0 ms-auto">
            <!-- Speed Multipliers (1x / 2x / 5x) -->
            <div v-if="headerLOD !== 'micro'"
                 class="flex items-center gap-0.5 p-1 rounded-xl border bg-[#F2F2F2] dark:bg-slate-900/80 border-slate-200/80 dark:border-white/10 shrink-0 shadow-xs text-[11px] font-semibold">
              <button v-for="spd in [1, 2, 5]" :key="spd"
                      @click="store.setSimSpeed(spd)"
                      class="px-2 py-0.5 rounded-lg text-[10px] font-black cursor-pointer transition-colors"
                      :class="store.simSpeed === spd
                        ? 'bg-[#BECD32] text-[#00305E] shadow-2xs'
                        : 'text-[#706F6F] dark:text-slate-400 hover:text-[#00305E] dark:hover:text-white'"
                      :title="`Simulation Speed ${spd}x`">
                {{ spd }}x
              </button>
            </div>

            <!-- Merged Fleet & UAV/Warning Telemetry Pill -->
            <div class="flex items-center gap-2 px-2.5 py-1.5 rounded-xl border shadow-xs shrink-0 text-xs font-semibold"
                 :class="store.theme === 'dark' ? 'bg-slate-800/80 border-white/10 text-slate-200' : 'bg-[#F2F2F2] border-slate-200 text-[#00305E]'"
                 :title="`${store.activeVehiclesCount} Active HGVs, ${store.activeDronesCount} UAVs, ${store.activeWarningsCount} Warnings`">
              <div class="flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full bg-[#5096BE] shrink-0"></span>
                <span v-if="headerLOD === 'full' || headerLOD === 'compact'">{{ store.activeVehiclesCount }} {{ store.activeVehiclesCount === 1 ? 'HGV' : 'HGVs' }}</span>
                <span v-else>{{ store.activeVehiclesCount }}</span>
              </div>
              <span class="w-px h-3.5 bg-slate-300 dark:bg-white/15 shrink-0"></span>
              <div class="flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full shrink-0" :class="warningDotColorClass"></span>
                <span v-if="headerLOD === 'full' || headerLOD === 'compact'">{{ store.activeDronesCount }} {{ store.activeDronesCount === 1 ? 'UAV' : 'UAVs' }} / {{ store.activeWarningsCount }} {{ store.activeWarningsCount === 1 ? 'Warn' : 'Warns' }}</span>
                <span v-else>{{ store.activeDronesCount }}/{{ store.activeWarningsCount }}</span>
              </div>
            </div>
          </div>

          <!-- Right: View-Specific Header Actions (Teleport target for Broker & Documentation) -->
          <div v-else
               id="view-header-actions"
               class="flex items-center gap-2 shrink-0 ms-auto min-w-0">
          </div>
        </header>

        <!-- Main Viewport Content Area -->
        <div class="flex-1 overflow-hidden relative">
          
          <!-- VIEW 1: DIGITAL SHADOW -->
          <div v-if="store.currentView === 'digital-shadow'" class="w-full h-full relative">
            <div class="w-full h-full relative">
              <DashboardMap />

              <!-- Flightradar24-Inspired Floating Corridor & HLA Federation Overview Card (when no object is selected) -->
              <div v-if="!store.selectedType"
                   class="absolute bottom-12 left-3 z-[400] max-w-xs p-3 rounded-2xl backdrop-blur-md shadow-xl border text-xs space-y-2 pointer-events-none"
                   :class="store.theme === 'dark' ? 'bg-slate-900/88 border-white/10 text-slate-200' : 'bg-white/90 border-slate-200 text-slate-800'">
                <div class="flex items-center justify-between gap-3 border-b pb-1.5"
                     :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200'">
                  <div class="flex items-center gap-1.5 font-bold text-[#00305E] dark:text-[#5096BE]">
                    <ShieldCheck :size="14" />
                    <span>A4/A14 Corridor Federation</span>
                  </div>
                  <span class="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-[#00AA82]/15 text-[#00AA82]">
                    Avg {{ store.corridorAvgHealth }}%
                  </span>
                </div>
                <div class="grid grid-cols-3 gap-1.5 text-center text-[10px]">
                  <div class="p-1.5 rounded-lg bg-slate-500/10">
                    <div class="text-slate-500 dark:text-slate-400">HLA Contracts</div>
                    <div class="font-bold font-mono text-[#00305E] dark:text-[#5096BE]">{{ store.federationSummary.active_contracts_count || store.activeVehiclesCount }}</div>
                  </div>
                  <div class="p-1.5 rounded-lg bg-slate-500/10">
                    <div class="text-slate-500 dark:text-slate-400">Fast-Slow Syncs</div>
                    <div class="font-bold font-mono text-purple-700 dark:text-purple-400">{{ store.federationSummary.total_FastSlowSyncs || 0 }}</div>
                  </div>
                  <div class="p-1.5 rounded-lg bg-slate-500/10">
                    <div class="text-slate-500 dark:text-slate-400">Handovers</div>
                    <div class="font-bold font-mono text-amber-600 dark:text-amber-400">{{ store.federationSummary.total_Handovers || 0 }}</div>
                  </div>
                </div>
                <div class="flex items-center gap-1.5 text-[10px] text-slate-500 dark:text-slate-400 pt-0.5">
                  <Info :size="12" class="text-[#5096BE] shrink-0" />
                  <span>Click any road segment, junction, water source, vehicle, RSU, drone, or warning to inspect.</span>
                </div>
              </div>
            </div>
          </div>

          <!-- VIEW 2: FIWARE STATUS -->
          <div v-else-if="store.currentView === 'fiware-status'" class="w-full h-full overflow-hidden">
            <FiwareInsights />
          </div>

          <!-- VIEW 4: WEB DOCUMENTATION -->
          <div v-else-if="store.currentView === 'documentation'" class="w-full h-full overflow-hidden">
            <DocumentationViewer />
          </div>

        </div>

      </main>

    </div>

    <!-- ======================================================== -->
    <!-- GLOBAL FOOTER (48px)                                     -->
    <!-- ======================================================== -->
    <footer class="h-12 border-t flex items-center justify-between px-6 shrink-0 z-30 transition-colors"
            :class="store.theme === 'dark' ? 'bg-[#001d3a] border-white/10' : 'bg-white border-slate-200'">
      
      <!-- Left spacer for balanced footer alignment -->
      <div class="hidden sm:flex items-center gap-2 w-32"></div>

      <div class="text-[11px] font-semibold text-[#00305E] dark:text-slate-300 text-center hidden md:flex items-center gap-2">
        <span>Digital Twin Road System</span>
        <span class="text-blue-500">•</span>
        <span>Volodymyr Prokopets</span>
        <span class="text-blue-500">•</span>
        <span class="text-[#706F6F] dark:text-slate-400">Open Source Permissive License (MIT)</span>
      </div>

      <div class="flex items-center gap-4">
        <a href="https://github.com/vprokopets/digital-twin-road" target="_blank"
           class="flex items-center gap-2 opacity-85 hover:opacity-100 transition-opacity no-underline">
          <div class="h-5 w-5 bg-white rounded flex items-center justify-center p-0.5 shadow-xs border border-[#00305E]/20">
            <Layers :size="13" class="text-[#00305E]" />
          </div>
          <span class="text-[10px] font-extrabold tracking-widest uppercase text-[#00305E] dark:text-white">
            FUTURE ROAD SYSTEM
          </span>
        </a>
      </div>
    </footer>

  </div>
</template>

<style scoped>
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.2);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.4);
}
</style>
