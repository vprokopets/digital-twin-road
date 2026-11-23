<script setup lang="ts">
import { computed } from 'vue'
import {
  Droplets,
  Radio,
  Plane,
  Truck,
  Layers,
  AlertTriangle,
  ArrowRight,
  ShieldCheck,
  Plus,
  Crosshair,
  Activity,
  Database,
  ExternalLink
} from 'lucide-vue-next'
import { useDashboardStore } from '../../stores/dashboard'
import apiClient from '../../api/client'

const store = useDashboardStore()
const resolveEntityApiUrl = (path?: string) => `${apiClient.defaults.baseURL ?? ''}${path || ''}`

const panel = computed(() => store.selectedData?.panel || null)
const panelType = computed(() => panel.value?.panel_type || null)
const fedContract = computed(() => store.selectedData?.federation_contract || panel.value?.federation_contract || null)
const isRecalibrating = computed(() =>
  fedContract.value?.state === 'FOM_BASIS_RECALIBRATION' ||
  String(fedContract.value?.active_solver || '').toUpperCase().includes('FEM') ||
  String(fedContract.value?.active_solver || '').toUpperCase().includes('FOM')
)

const getHealthColorClass = (h: number) => {
  if (h >= 75) return 'text-emerald-700 dark:text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
  if (h >= 50) return 'text-amber-700 dark:text-amber-400 border-amber-500/30 bg-amber-500/10'
  return 'text-rose-700 dark:text-rose-400 border-rose-500/30 bg-rose-500/10'
}

const getHealthBarColor = (h: number) => {
  if (h >= 75) return 'bg-emerald-500'
  if (h >= 50) return 'bg-amber-500'
  return 'bg-rose-500'
}

const formatContractState = (rawState?: string) => {
  if (!rawState) return 'Fast–Slow Sync'
  if (rawState === 'ACTIVE_FAST_SLOW_SYNC') return 'Fast–Slow Sync'
  if (rawState === 'FOM_BASIS_RECALIBRATION') return 'FEM Recalibration'
  if (rawState === 'HANDOVER_NEGOTIATION' || rawState === 'CELL_HANDOVER') return 'RSU Handover'
  return rawState.replace(/_/g, ' ')
}

const getContractStateBadgeClass = (rawState?: string) => {
  if (rawState === 'FOM_BASIS_RECALIBRATION') {
    return 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30'
  }
  if (rawState === 'HANDOVER_NEGOTIATION' || rawState === 'CELL_HANDOVER') {
    return 'bg-purple-500/15 text-purple-700 dark:text-purple-300 border-purple-500/30'
  }
  return 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
}

const formatVehicleId = (rawId: any) => {
  if (rawId == null) return 'HGV-101'
  const s = String(rawId).trim()
  if (s.startsWith('HGV') || s.startsWith('Corridor') || s.startsWith('Fleet')) return s
  return `HGV #${s.slice(-4)}`
}

const formatJunctionSignName = (code?: string, name?: string) => {
  const cleanName = String(name || '').trim()
  const cleanCode = String(code || '').trim()
  if (cleanCode && cleanName.toLowerCase().startsWith(cleanCode.toLowerCase())) {
    const stripped = cleanName.slice(cleanCode.length).trim()
    return stripped || cleanName
  }
  return cleanName || cleanCode
}

const formatProbPct = (val: any) => {
  const num = Number(val)
  if (isNaN(num)) return '0%'
  return `${(num * 100).toFixed(0)}%`
}

const currentIconSpeed = (fallback: number) => {
  const selId = String(store.selectedFeature?.properties?.id ?? '')
  const list = store.vehicleExtrapolations?.[selId]
  if (list && list.length > 0) {
    return Number(list[list.length - 1].extrapolatedSpeed).toFixed(1)
  }
  return Number(store.selectedFeature?.properties?.ExtrapolatedVelocity ?? fallback).toFixed(1)
}

const iconKinematicState = computed(() => {
  const selId = String(store.selectedFeature?.properties?.id ?? '')
  const list = store.vehicleExtrapolations?.[selId]
  const stdVel = Number(panel.value?.velocity_kmh ?? 88.0)
  let currentSpeed = stdVel
  if (list && list.length > 0) {
    currentSpeed = Number(list[list.length - 1].extrapolatedSpeed)
  } else if (store.selectedFeature?.properties?.ExtrapolatedVelocity != null) {
    currentSpeed = Number(store.selectedFeature.properties.ExtrapolatedVelocity)
  }

  const diff = currentSpeed - stdVel
  if (diff > 1.8) {
    return {
      label: `FAST (+${diff.toFixed(1)})`,
      badgeClass: 'text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
    }
  } else if (diff < -1.8) {
    return {
      label: `SLOW (${diff.toFixed(1)})`,
      badgeClass: 'text-amber-700 dark:text-amber-400 bg-amber-500/10 border-amber-500/20'
    }
  } else {
    return {
      label: 'CRUISE',
      badgeClass: 'text-slate-500 dark:text-slate-400 bg-slate-500/10 border-slate-500/20'
    }
  }
})

const v2xRssiInfo = computed(() => {
  const distKm = Number(fedContract.value?.distance_km ?? fedContract.value?.distance_to_rsu_km ?? 2.4)
  const rawRssi = Number(fedContract.value?.rssi_dbm)
  const rssi = Number.isFinite(rawRssi) ? Math.round(rawRssi) : Math.round(-55 - distKm * 2.8)
  const quality = rssi > -68 ? 'High' : rssi > -80 ? 'Good' : 'Fair'
  return {
    distKm: distKm.toFixed(1),
    rssi,
    label: `${rssi} dBm (${quality})`
  }
})

const droneStages = [
  { id: 'Liftoff', label: '1. Liftoff (50m)' },
  { id: 'CruisingToward', label: '2. En Route (50m)' },
  { id: 'Inspecting', label: '3. LiDAR (18m)' },
  { id: 'CruisingBack', label: '4. Return (50m)' },
  { id: 'Landing', label: '5. Landing' }
]

const isDroneStageActive = (stageId: string, currentFlightState: string) => {
  if (stageId === 'Liftoff') return currentFlightState === 'Liftoff'
  if (stageId === 'CruisingToward') return currentFlightState === 'CruisingToward' || currentFlightState === 'DescendToInspect'
  if (stageId === 'Inspecting') return currentFlightState === 'Inspecting'
  if (stageId === 'CruisingBack') return currentFlightState === 'CruisingBack' || currentFlightState === 'AscendToCruise'
  if (stageId === 'Landing') return currentFlightState === 'Landing'
  return false
}

const formatDroneState = (state: string) => {
  if (state === 'DescendToInspect') return 'Descend to 18m'
  if (state === 'AscendToCruise') return 'Climb to 50m'
  if (state === 'CruisingToward') return 'En Route (50m)'
  if (state === 'CruisingBack') return 'Return (50m)'
  if (state === 'Inspecting') return 'LiDAR Scan (18m)'
  if (state === 'Liftoff') return 'Liftoff (50m)'
  if (state === 'Landing') return 'Landing'
  if (state === 'Idle') return 'Docked'
  return state || 'In-Flight'
}
const warningStages = ['New', 'Under Inspection', 'Inspected']

const warningColorConfig = computed(() => {
  const p = panel.value
  if (!p || panelType.value !== 'warning') {
    return {
      borderClass: 'border-[#AF2D37]/35 dark:border-[#AF2D37]/50',
      iconBoxClass: 'bg-[#AF2D37]/15 text-[#AF2D37] dark:text-[#f87171] border-[#AF2D37]/30',
      titleTagClass: 'text-[#AF2D37] dark:text-[#f87171]',
      severityBadgeClass: 'bg-[#AF2D37] text-white border-[#8e222a]'
    }
  }

  const st = p.status || 'New'
  const sev = String(p.severity || 'MEDIUM').toUpperCase()

  let borderClass = 'border-[#AF2D37]/40 dark:border-[#AF2D37]/60'
  let iconBoxClass = 'bg-[#AF2D37]/15 text-[#AF2D37] dark:text-[#f87171] border-[#AF2D37]/30'
  let titleTagClass = 'text-[#AF2D37] dark:text-[#f87171]'

  if (st === 'Under Inspection') {
    borderClass = 'border-amber-500/40 dark:border-amber-500/60'
    iconBoxClass = 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30'
    titleTagClass = 'text-amber-600 dark:text-amber-400'
  } else if (st === 'Inspected') {
    borderClass = 'border-[#00AA82]/40 dark:border-[#00AA82]/60'
    iconBoxClass = 'bg-[#00AA82]/15 text-[#00AA82] border-[#00AA82]/30'
    titleTagClass = 'text-[#00AA82]'
  }

  let severityBadgeClass = 'bg-amber-500 text-slate-950 border-amber-600'
  if (sev === 'CRITICAL') {
    severityBadgeClass = 'bg-[#AF2D37] text-white border-[#8e222a] animate-pulse'
  } else if (sev === 'HIGH') {
    severityBadgeClass = 'bg-orange-600 text-white border-orange-700'
  } else if (sev === 'MEDIUM') {
    severityBadgeClass = 'bg-amber-500 text-slate-950 border-amber-600'
  } else if (sev === 'LOW') {
    severityBadgeClass = 'bg-[#5096BE] text-white border-[#3c789a]'
  }

  return { borderClass, iconBoxClass, titleTagClass, severityBadgeClass }
})
</script>

<template>
  <div v-if="panel" class="space-y-3.5 text-xs">

    <!-- ================================================================== -->
    <!-- 1. VEHICLE INSPECTOR (Flightradar24 Route + HLA Dynamic Contract)  -->
    <!-- ================================================================== -->
    <template v-if="panelType === 'vehicle'">
      <!-- Flightradar24-style Origin -> Destination Route Progress Card -->
      <div class="p-3.5 rounded-lg border shadow-xs transition-all"
           :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/10' : 'bg-white border-slate-200'">
        <div class="flex items-center justify-between gap-2.5 pb-2.5 mb-2.5 border-b flex-wrap min-w-0"
             :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="h-8 w-8 rounded-md bg-[#00305E]/10 text-[#00305E] dark:bg-sky-500/15 dark:text-sky-300 border border-[#00305E]/25 dark:border-sky-400/30 flex items-center justify-center shrink-0">
              <Truck :size="16" />
            </div>
            <div class="min-w-0">
              <div class="text-[10px] font-bold uppercase tracking-wider text-[#00305E] dark:text-sky-400 truncate">{{ panel.carriageway }}</div>
              <h4 class="font-bold text-sm truncate" :class="store.theme === 'dark' ? 'text-white' : 'text-slate-900'">
                HGV #{{ String(panel.vehicle_id).slice(-4) }}
              </h4>
            </div>
          </div>

          <!-- Contextual Vehicle Actions -->
          <div class="flex items-center gap-1.5 flex-wrap shrink-0">
            <button @click="store.triggerWarning()"
                    class="flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-bold border transition-all cursor-pointer bg-[#AF2D37]/12 hover:bg-[#AF2D37] text-[#AF2D37] dark:text-rose-300 hover:text-white border-[#AF2D37]/30"
                    :title="`Trigger structural anomaly warning next to HGV #${String(panel.vehicle_id).slice(-4)} & dispatch UAV`">
              <AlertTriangle :size="11" />
              <span>Anomaly</span>
            </button>

            <button @click="store.followVehicle = !store.followVehicle"
                    class="flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-bold border transition-all cursor-pointer"
                    :class="store.followVehicle
                      ? 'bg-[#BECD32] text-[#00305E] border-[#a8b824] shadow-sm'
                      : (store.theme === 'dark' ? 'bg-slate-800 border-white/10 text-slate-300 hover:bg-slate-700' : 'bg-slate-100 border-slate-200 text-[#00305E] hover:bg-slate-200')"
                    title="Lock map camera onto this vehicle">
              <Crosshair :size="11" />
              <span>{{ store.followVehicle ? 'Following' : 'Follow Cam' }}</span>
            </button>
          </div>
        </div>

        <!-- Origin -> Destination Banner -->
        <div class="grid grid-cols-11 items-center gap-2 p-2.5 rounded-md border mb-2.5"
             :class="store.theme === 'dark' ? 'bg-slate-950/70 border-white/5' : 'bg-slate-50 border-slate-200/70'">
          <div class="col-span-5 min-w-0">
            <div class="text-[9px] uppercase font-bold text-slate-500 dark:text-slate-400">Origin Junction</div>
            <div class="font-bold text-xs truncate text-[#00305E] dark:text-[#5096BE]" :title="panel.origin_name">{{ panel.origin_name }}</div>
            <div class="text-[10px] text-slate-500 dark:text-slate-400 font-mono">km {{ Number(panel.start_km).toFixed(1) }}</div>
          </div>
          <div class="col-span-1 flex justify-center">
            <ArrowRight :size="14" class="text-slate-400" />
          </div>
          <div class="col-span-5 min-w-0 text-right">
            <div class="text-[9px] uppercase font-bold text-slate-500 dark:text-slate-400">Destination</div>
            <div class="font-bold text-xs truncate text-emerald-600 dark:text-[#BECD32]" :title="panel.destination_name">{{ panel.destination_name }}</div>
            <div class="text-[10px] text-slate-500 dark:text-slate-400 font-mono">km {{ Number(panel.end_km).toFixed(1) }}</div>
          </div>
        </div>

        <!-- Route Progress Bar -->
        <div class="space-y-1 mb-3">
          <div class="flex justify-between text-[10px] font-semibold">
            <span class="text-slate-500 dark:text-slate-400">Station: <b class="text-slate-800 dark:text-slate-200 font-mono">km {{ Number(panel.kilometer).toFixed(2) }}</b></span>
            <span class="text-[#00305E] dark:text-[#5096BE] font-bold font-mono">{{ Number(panel.route_progress_pct).toFixed(1) }}% Complete</span>
          </div>
          <div class="w-full h-2 rounded-full overflow-hidden bg-slate-200 dark:bg-slate-800">
            <div class="h-full bg-gradient-to-r from-[#00305E] via-[#5096BE] to-[#BECD32] rounded-full transition-all duration-300"
                 :style="{ width: `${Math.min(100, Math.max(2, Number(panel.route_progress_pct || 0)))}%` }"></div>
          </div>
        </div>

        <!-- Kinematics & Axle Load KPIs -->
        <div class="grid grid-cols-3 gap-2 text-center">
          <div class="p-2 rounded-md border flex flex-col justify-between" :class="store.theme === 'dark' ? 'bg-slate-950/50 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="flex items-center justify-between">
              <span class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Speed / Extrap</span>
              <span class="text-[8px] font-bold px-1 py-0.2 rounded border font-mono" :class="iconKinematicState.badgeClass">
                {{ iconKinematicState.label }}
              </span>
            </div>
            <div class="text-sm font-black text-[#00305E] dark:text-sky-400 font-mono flex items-baseline justify-center gap-1 mt-0.5">
              <span>{{ Number(panel.velocity_kmh).toFixed(1) }}</span>
              <span class="text-[10px] text-slate-500 dark:text-slate-400 font-semibold" title="Real icon movement speed on map">/ {{ currentIconSpeed(panel.velocity_kmh) }}</span>
              <span class="text-[9px] font-normal text-slate-400">km/h</span>
            </div>
          </div>
          <div class="p-2 rounded-md border" :class="store.theme === 'dark' ? 'bg-slate-950/50 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Gross Mass</div>
            <div class="text-sm font-black font-mono text-slate-800 dark:text-slate-100">{{ (Number(panel.weight_kg) / 1000).toFixed(2) }} <span class="text-[9px] font-normal">t</span></div>
          </div>
          <div class="p-2 rounded-md border" :class="store.theme === 'dark' ? 'bg-slate-950/50 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Road Surf T</div>
            <div class="text-sm font-black text-amber-600 dark:text-amber-400 font-mono">{{ Number(panel.surface_temp_c).toFixed(1) }} <span class="text-[9px] font-normal">°C</span></div>
          </div>
        </div>
      </div>

      <!-- Unified IEEE 1516 HLA / Heraklit Dynamic Federation Contract + V2X Link Card -->
      <div v-if="fedContract"
           class="p-3.5 rounded-lg border shadow-xs space-y-2.5"
           :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/10' : 'bg-white border-slate-200'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-1.5 min-w-0">
            <ShieldCheck :size="15" class="text-[#00305E] dark:text-sky-400 shrink-0" />
            <span class="font-bold text-xs text-slate-900 dark:text-slate-100 truncate">HLA / Heraklit Federation Contract</span>
          </div>
          <span class="px-2 py-0.5 rounded text-[9px] font-black uppercase border shrink-0"
                :class="getContractStateBadgeClass(fedContract.state)">
            {{ formatContractState(fedContract.state) }}
          </span>
        </div>

        <!-- Consolidated V2X Edge Link Banner -->
        <div class="p-2 rounded-md border flex items-center justify-between gap-2 text-[10px]"
             :class="store.theme === 'dark' ? 'bg-slate-950/70 border-white/5' : 'bg-slate-50 border-slate-200/80'">
          <div class="flex items-center gap-1.5 min-w-0">
            <Radio :size="13" class="text-[#00305E] dark:text-sky-400 shrink-0" />
            <div class="truncate">
              <span class="font-bold text-slate-800 dark:text-slate-100">{{ fedContract.rsu_name }}</span>
              <span class="text-slate-500 dark:text-slate-400 font-mono ml-1">⇄ Veh #{{ String(fedContract.vehicle_id).slice(-4) }}</span>
            </div>
          </div>
          <div class="flex items-center gap-1.5 shrink-0 font-mono">
            <span class="text-amber-600 dark:text-amber-400 font-bold">{{ v2xRssiInfo.distKm }} km</span>
            <span class="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-300 border border-slate-200/80 dark:border-white/10 font-semibold text-[9px]">
              {{ v2xRssiInfo.label }}
            </span>
          </div>
        </div>

        <!-- Fast-Slow Multi-Scale Coupling Badges -->
        <div class="grid grid-cols-2 gap-2">
          <div class="p-2 rounded-lg border text-[10px]"
               :class="store.theme === 'dark' ? 'bg-slate-900/80 border-white/5' : 'bg-white border-slate-200/80'">
            <div class="font-bold text-purple-700 dark:text-purple-400 uppercase text-[9px]">Slow Scale (RSU Env)</div>
            <div class="font-mono font-bold mt-0.5 text-slate-800 dark:text-slate-100">Δt = {{ fedContract.slow_step_sec ?? 5.0 }} s</div>
            <div class="text-[9px] text-slate-500 dark:text-slate-400 mt-0.5 truncate">Pub: AirT, SurfT, Weather</div>
          </div>
          <div class="p-2 rounded-lg border text-[10px]"
               :class="store.theme === 'dark' ? 'bg-slate-900/80 border-white/5' : 'bg-white border-slate-200/80'">
            <div class="font-bold text-cyan-700 dark:text-cyan-400 uppercase text-[9px]">Fast Scale (Veh Mech)</div>
            <div class="font-mono font-bold mt-0.5 text-slate-800 dark:text-slate-100">Δt = {{ fedContract.fast_step_sec ?? 0.05 }} s</div>
            <div class="text-[9px] text-slate-500 dark:text-slate-400 mt-0.5 truncate">Pub: Load, Damage, POD_Conf</div>
          </div>
        </div>

        <!-- POD Reduced-Order Basis SLA Bar -->
        <div class="p-2.5 rounded-lg border space-y-1.5"
             :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/5' : 'bg-white border-slate-200/80'">
          <div class="flex items-center justify-between text-[10px]">
            <span class="font-semibold text-slate-500 dark:text-slate-400">
              {{ isRecalibrating ? 'FEM Reference Fidelity (Recalibrating POD):' : 'POD Surrogate Basis Confidence:' }}
            </span>
            <span class="font-mono font-bold"
                  :class="isRecalibrating
                    ? 'text-amber-600 dark:text-amber-400'
                    : Number(fedContract.pod_confidence) >= Number(fedContract.sla_min_pod_confidence || 0.9)
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-amber-600 dark:text-amber-400'">
              {{ (Number(fedContract.pod_confidence || 0.94) * 100).toFixed(1) }}% {{ isRecalibrating ? '• Rebuilding Basis' : '(SLA ≥ 90%)' }}
            </span>
          </div>
          <div class="w-full h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
            <div class="h-full rounded-full transition-all"
                 :class="isRecalibrating ? 'bg-amber-500' : (Number(fedContract.pod_confidence) >= 0.9 ? 'bg-emerald-500' : 'bg-amber-500')"
                 :style="{ width: `${Math.min(100, Number(fedContract.pod_confidence || 0.94) * 100)}%` }"></div>
          </div>
          <div class="flex items-center justify-between text-[9px] text-slate-500 dark:text-slate-400 pt-0.5">
            <span>Active Solver: <b class="text-cyan-700 dark:text-cyan-300 font-mono">{{ (fedContract.active_solver || panel.active_solver || 'POD').replace('FOM', 'FEM') }}</b></span>
            <span>Syncs: <b class="text-slate-700 dark:text-slate-200 font-mono">{{ fedContract.sync_ticks || 1 }}</b> • Recalib: <b class="text-slate-700 dark:text-slate-200 font-mono">{{ fedContract.recalibrations_triggered || 0 }}</b></span>
          </div>
        </div>

        <!-- Live HLA FOM Interaction Ticker -->
        <div v-if="(fedContract.recent_interactions || fedContract.latest_interactions)?.length"
             class="p-2 rounded-lg border space-y-1"
             :class="store.theme === 'dark' ? 'bg-slate-950/70 border-white/5' : 'bg-white/90 border-slate-200/80'">
          <div class="flex items-center justify-between text-[9px] font-bold uppercase text-slate-500 dark:text-slate-400">
            <span class="flex items-center gap-1"><Activity :size="10" class="text-cyan-500" /> HLA RTI Message Bus</span>
            <span class="font-mono">{{ fedContract.contract_id }}</span>
          </div>
          <div v-for="(msg, mIdx) in (fedContract.recent_interactions || fedContract.latest_interactions).slice(0, 3)" :key="mIdx"
               class="flex items-center justify-between gap-2 text-[9.5px] font-mono py-0.5 border-t first:border-t-0"
               :class="store.theme === 'dark' ? 'border-white/5' : 'border-slate-100'">
            <span class="font-bold truncate"
                  :class="msg.interaction === 'FOMBasisRecalibration' || msg.interaction === 'SolverRecalibrationDirective'
                    ? 'text-amber-600 dark:text-amber-400'
                    : (String(msg.sender || '').toLowerCase().startsWith('rsu') ? 'text-purple-700 dark:text-purple-300' : 'text-cyan-700 dark:text-cyan-300')">
              {{ String(msg.sender || '').toLowerCase().startsWith('rsu') ? 'RSU→Veh' : 'Veh→RSU' }}: {{ msg.interaction }}
            </span>
            <span class="text-slate-500 dark:text-slate-400 shrink-0">{{ msg.timestamp }}</span>
          </div>
        </div>

        <!-- Active Context Broker / FIWARE Instance Link -->
        <div v-if="panel.broker_link"
             class="p-2 rounded-md border flex items-center justify-between gap-2 flex-wrap"
             :class="store.theme === 'dark' ? 'bg-slate-950/70 border-white/5' : 'bg-slate-50/90 border-slate-200/80'">
          <div class="flex items-center gap-1.5 min-w-0">
            <Database :size="12" :class="panel.broker_link.fiware_connected ? 'text-emerald-500 shrink-0' : 'text-[#00305E] dark:text-sky-400 shrink-0'" />
            <span class="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase border shrink-0"
                  :class="panel.broker_link.fiware_connected
                    ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/25'
                    : 'bg-[#00305E]/10 text-[#00305E] border-[#00305E]/20 dark:bg-sky-500/15 dark:text-sky-300 dark:border-sky-400/30'">
              {{ panel.broker_link.fiware_connected ? 'FIWARE Live' : 'Native Broker' }}
            </span>
            <span class="font-mono text-[10px] text-slate-600 dark:text-slate-300 truncate">
              {{ panel.broker_link.entity_type }}:{{ panel.broker_link.entity_id }} · sg={{ panel.broker_link.service_group }}
            </span>
          </div>
          <div class="flex items-center gap-1.5 shrink-0 text-[10px] font-bold">
            <a :href="resolveEntityApiUrl(panel.broker_link.entity_api_url)" target="_blank"
               class="flex items-center gap-1 px-2 py-0.5 rounded border text-[#00305E] dark:text-sky-400 hover:bg-[#00305E]/10 dark:hover:bg-sky-500/10 no-underline"
               :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200'">
              <span>{{ panel.broker_link.fiware_connected ? 'FIWARE JSON' : 'Entity JSON' }}</span>
              <ExternalLink :size="10" />
            </a>
            <a v-if="panel.broker_link.fiware_connected"
               :href="panel.broker_link.orion_url" target="_blank"
               class="flex items-center gap-1 px-2 py-0.5 rounded border text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/10 no-underline"
               :class="store.theme === 'dark' ? 'border-emerald-500/30' : 'border-emerald-300'">
              <span>Orion :1026</span>
              <ExternalLink :size="10" />
            </a>
            <button @click="store.setCurrentView('fiware-status')"
                    class="px-2 py-0.5 rounded border text-slate-600 dark:text-slate-300 hover:bg-slate-500/10 cursor-pointer"
                    :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200'">
              Broker Tab
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- ================================================================== -->
    <!-- 2. ROAD SEGMENT / POINT INSPECTOR (RStO 12 Stack + Context)        -->
    <!-- ================================================================== -->
    <template v-else-if="panelType === 'road_segment'">
      <div class="p-3.5 rounded-lg border shadow-xs space-y-3"
           :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/10' : 'bg-white border-slate-200'">
        <div class="flex items-center justify-between gap-2.5 pb-2.5 border-b flex-wrap min-w-0"
             :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="h-8 w-8 rounded-md bg-[#00305E]/10 text-[#00305E] dark:bg-sky-500/15 dark:text-sky-300 border border-[#00305E]/25 dark:border-sky-400/30 flex items-center justify-center shrink-0">
              <Layers :size="16" />
            </div>
            <div class="min-w-0">
              <div class="text-[10px] font-bold uppercase tracking-wider text-[#00305E] dark:text-sky-400 truncate">{{ panel.road_name }} • {{ panel.carriageway }}</div>
              <h4 class="font-bold text-sm truncate" :class="store.theme === 'dark' ? 'text-white' : 'text-slate-900'">
                km {{ Number(panel.station_start_km).toFixed(2) }} – {{ Number(panel.station_end_km).toFixed(2) }}
              </h4>
            </div>
          </div>
          <div class="px-2.5 py-1 rounded-md border text-right shrink-0" :class="getHealthColorClass(Number(panel.health_pct))">
            <div class="text-xs font-black font-mono leading-tight">{{ Number(panel.health_pct).toFixed(1) }}%</div>
            <div class="text-[9px] font-bold uppercase tracking-wider leading-tight">{{ panel.condition_status }}</div>
          </div>
        </div>

        <!-- Health Progress Bar -->
        <div class="w-full h-2 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
          <div class="h-full rounded-full transition-all duration-300"
               :class="getHealthBarColor(Number(panel.health_pct))"
               :style="{ width: `${Math.min(100, Math.max(5, Number(panel.health_pct)))}%` }"></div>
        </div>

        <!-- Traffic Load & Rutting KPIs -->
        <div class="grid grid-cols-3 gap-2 text-center">
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Length / Lanes</div>
            <div class="text-xs font-bold font-mono">{{ panel.length_m }} m • {{ panel.lanes }}L</div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">HGV Passes</div>
            <div class="text-xs font-bold font-mono text-[#00305E] dark:text-sky-400">{{ panel.total_passes }}</div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">
              {{ String(panel.road_material || '').toLowerCase() === 'concrete' ? 'Cumulative Wear' : 'Rut Depth' }}
            </div>
            <div class="text-xs font-bold font-mono text-amber-600 dark:text-amber-400">{{ Number(panel.cumulative_damage_mm).toFixed(3) }} mm</div>
          </div>
        </div>

        <!-- RStO 12 Pavement Layer Cross-Section -->
        <div class="space-y-1.5">
          <div class="flex items-center justify-between gap-2">
            <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">RStO 12 Structural Layer Stack</span>
            <span v-if="panel.road_material"
                  class="px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide border"
                  :class="String(panel.road_material).toLowerCase() === 'concrete'
                    ? 'bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 border-cyan-500/30'
                    : 'bg-slate-700/15 text-slate-700 dark:text-slate-300 border-slate-500/30'">
              {{ panel.road_material }}<template v-if="panel.load_class"> • {{ panel.load_class }}</template><template v-if="panel.road_structure_id"> • {{ panel.road_structure_id }}</template>
            </span>
          </div>
          <div class="space-y-1">
            <div v-for="(layer, idx) in panel.pavement_layers" :key="idx"
                 class="p-2 rounded-lg border flex items-center justify-between text-[11px]"
                 :class="(String(layer.material || '').toLowerCase() === 'unbound' || String(layer.layer || '').includes('FSS'))
                   ? 'bg-amber-900/90 text-amber-100 border-amber-700'
                   : (String(panel.road_material || layer.material || '').toLowerCase() === 'concrete'
                       ? (idx === 0
                           ? 'bg-slate-200 dark:bg-slate-700 text-slate-900 dark:text-white border-slate-300 dark:border-slate-500'
                           : 'bg-cyan-900/90 text-cyan-50 border-cyan-700')
                       : (idx === 0
                           ? 'bg-slate-900 text-white border-slate-700'
                           : idx === 1
                             ? 'bg-slate-800 text-slate-100 border-slate-600'
                             : 'bg-slate-700 text-slate-100 border-slate-500'))">
              <div>
                <div class="font-bold">{{ layer.layer }}</div>
                <div class="text-[9px] opacity-80">E-Modulus: {{ layer.modulus_mpa }} MPa</div>
              </div>
              <span class="px-2 py-0.5 rounded font-mono font-bold text-[10px]"
                    :class="String(panel.road_material || layer.material || '').toLowerCase() === 'concrete' && idx === 0
                      ? 'bg-slate-900/15 dark:bg-black/30'
                      : 'bg-black/30'">
                {{ layer.thickness_cm }} cm
              </span>
            </div>
          </div>
        </div>

        <!-- Environmental Context: Nearest RSU & Water Basin -->
        <div class="grid grid-cols-2 gap-2 pt-1">
          <div v-if="panel.nearest_rsu" class="p-2.5 rounded-lg border"
               :class="store.theme === 'dark' ? 'bg-slate-950/50 border-white/5' : 'bg-slate-50 border-slate-200/70'">
            <div class="text-[9px] font-bold uppercase text-purple-700 dark:text-purple-400 flex items-center gap-1">
              <Radio :size="11" /> Nearest RSU ({{ panel.nearest_rsu.distance_km }} km)
            </div>
            <div class="font-bold text-[11px] truncate mt-0.5">{{ panel.nearest_rsu.name }}</div>
            <div class="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
              {{ panel.nearest_rsu.weather }} • Surf {{ Number(panel.nearest_rsu.road_temperature).toFixed(1) }}°C
            </div>
          </div>

          <div v-if="panel.nearest_water" class="p-2.5 rounded-lg border"
               :class="store.theme === 'dark' ? 'bg-slate-950/50 border-white/5' : 'bg-slate-50 border-slate-200/70'">
            <div class="text-[9px] font-bold uppercase text-cyan-700 dark:text-cyan-400 flex items-center gap-1">
              <Droplets :size="11" /> Hydrology ({{ panel.nearest_water.distance_km }} km)
            </div>
            <div class="font-bold text-[11px] truncate mt-0.5">{{ panel.nearest_water.name }}</div>
            <div class="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
              {{ panel.nearest_water.in_influence_zone ? `Cooling ${panel.nearest_water.cooling_effect_c}°C` : 'Outside 5km zone' }}
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ================================================================== -->
    <!-- 3. INTERSECTION / JUNCTION INSPECTOR (Autobahn AS / AD Sign)       -->
    <!-- ================================================================== -->
    <template v-else-if="panelType === 'intersection'">
      <div class="p-3.5 rounded-lg border shadow-xs space-y-3"
           :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/10' : 'bg-white border-slate-200'">
        <div class="flex items-center justify-between gap-2.5 pb-2.5 border-b flex-wrap min-w-0"
             :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="h-8 px-2 rounded-md bg-[#003399] text-white border border-white/25 font-black text-xs flex items-center justify-center shrink-0 shadow-2xs">
              {{ panel.code }}
            </div>
            <div class="min-w-0">
              <div class="text-[10px] font-bold uppercase tracking-wider text-[#003399] dark:text-blue-400 truncate">{{ panel.junction_type }}</div>
              <h4 class="font-bold text-sm truncate" :class="store.theme === 'dark' ? 'text-white' : 'text-slate-900'">
                {{ formatJunctionSignName(panel.code, panel.name) }}
              </h4>
            </div>
          </div>
          <div class="px-2 py-1 rounded-md border text-right font-mono shrink-0"
               :class="store.theme === 'dark' ? 'bg-blue-500/10 text-blue-300 border-blue-500/30' : 'bg-[#003399]/10 text-[#003399] border-[#003399]/25'">
            <div class="text-[11px] font-bold leading-tight">km {{ Number(panel.kilometer).toFixed(1) }}</div>
            <div class="text-[9px] font-semibold uppercase leading-tight opacity-85">{{ panel.connecting_road }}</div>
          </div>
        </div>

        <!-- Traffic Volume & Probabilities -->
        <div class="grid grid-cols-2 gap-2">
          <div class="p-2.5 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Daily Traffic (AADT)</div>
            <div class="text-sm font-black font-mono text-blue-600 dark:text-blue-400">{{ Number(panel.daily_traffic_aadt).toLocaleString() }} <span class="text-[9px] font-normal">veh/d</span></div>
            <div class="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">HGV Share: <b class="text-slate-700 dark:text-slate-200">{{ panel.heavy_goods_share_pct }}%</b></div>
          </div>
          <div class="p-2.5 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">O/D Matrix Weights</div>
            <div class="text-xs font-bold font-mono text-emerald-600 dark:text-emerald-400">Spawn: {{ panel.spawn_probability_pct }}%</div>
            <div class="text-xs font-bold font-mono text-amber-600 dark:text-amber-400">Exit: {{ panel.exit_probability_pct }}%</div>
          </div>
        </div>

        <!-- Live Corridor O/D Activity & Quick Spawn Button -->
        <div class="p-2.5 rounded-lg border flex items-center justify-between"
             :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/70'">
          <div class="text-[11px]">
            <span class="text-slate-500 dark:text-slate-400">Active Fleet From/To Junction:</span>
            <div class="font-bold mt-0.5">
              <span class="text-blue-600 dark:text-blue-400">{{ panel.active_spawned_vehicles }} Departed</span> •
              <span class="text-emerald-600 dark:text-emerald-400">{{ panel.active_inbound_vehicles }} Inbound</span>
            </div>
          </div>
          <button @click="store.spawnVehicle(panel.id)"
                  class="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#00305E] hover:bg-[#5096BE] text-white text-[10px] font-bold shadow-xs cursor-pointer transition-colors"
                  :title="`Spawn HGV at ${panel.name || 'Junction'} (starts at 30 km/h and accelerates to cruise speed)`">
            <Plus :size="12" />
            <span>Spawn HGV</span>
          </button>
        </div>
      </div>
    </template>

    <!-- ================================================================== -->
    <!-- 4. WATER SOURCE INSPECTOR (Hydrological Basin & Soil Cooling)      -->
    <!-- ================================================================== -->
    <template v-else-if="panelType === 'water_source'">
      <div class="p-3.5 rounded-lg border shadow-xs space-y-3"
           :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/10' : 'bg-white border-slate-200'">
        <div class="flex items-center justify-between gap-2.5 pb-2.5 border-b flex-wrap min-w-0"
             :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="h-8 w-8 rounded-md bg-cyan-500/15 text-cyan-600 dark:text-cyan-400 border border-cyan-500/30 flex items-center justify-center shrink-0">
              <Droplets :size="16" />
            </div>
            <div class="min-w-0">
              <div class="text-[10px] font-bold uppercase tracking-wider text-cyan-700 dark:text-cyan-400 truncate">{{ panel.water_type }}</div>
              <h4 class="font-bold text-sm truncate" :class="store.theme === 'dark' ? 'text-white' : 'text-slate-900'">{{ panel.name }}</h4>
            </div>
          </div>
          <span class="px-2 py-1 rounded-md bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 border border-cyan-500/30 font-mono font-bold text-[10px] shrink-0">
            km {{ Number(panel.kilometer).toFixed(1) }}
          </span>
        </div>

        <!-- Subgrade Thermal & Moisture KPIs -->
        <div class="grid grid-cols-3 gap-2 text-center">
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Subgrade T</div>
            <div class="text-xs font-black text-cyan-700 dark:text-cyan-400 font-mono">
              {{ panel.cooled_soil_temp_c }}°C <span class="text-[9px] text-slate-400 line-through">{{ panel.baseline_soil_temp_c }}°C</span>
            </div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Saturation</div>
            <div class="text-xs font-black text-blue-600 dark:text-blue-400 font-mono">{{ Number(panel.soil_moisture_saturation * 100).toFixed(0) }}%</div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Frost Class</div>
            <div class="text-xs font-black text-amber-600 dark:text-amber-400">{{ panel.frost_susceptibility }}</div>
          </div>
        </div>

        <!-- Radial Moisture Attenuation Profile (0 - 5000 m) -->
        <div class="space-y-1.5">
          <div class="flex items-center justify-between text-[10px]">
            <span class="font-bold uppercase text-slate-500 dark:text-slate-400">Radial Moisture &amp; Cooling Attenuation (5 km Zone)</span>
            <span class="text-cyan-700 dark:text-cyan-400 font-bold">{{ panel.affected_road_segments_count }} road segs</span>
          </div>
          <div class="space-y-1">
            <div v-for="pt in panel.radial_attenuation" :key="pt.distance_m"
                 class="flex items-center gap-2 text-[10px] font-mono">
              <span class="w-14 text-right text-slate-500 dark:text-slate-400">{{ pt.distance_m }} m</span>
              <div class="flex-1 h-2 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                <div class="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full"
                     :style="{ width: `${pt.moisture_factor_pct}%` }"></div>
              </div>
              <span class="w-14 font-bold text-cyan-700 dark:text-cyan-300">{{ pt.soil_temp_c }}°C</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ================================================================== -->
    <!-- 5. ROADSIDE UNIT (RSU) INSPECTOR (Weather Matrix + HLA Contracts)  -->
    <!-- ================================================================== -->
    <template v-else-if="panelType === 'rsu'">
      <div class="p-3.5 rounded-lg border shadow-xs space-y-3"
           :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/10' : 'bg-white border-slate-200'">
        <div class="flex items-center justify-between gap-2.5 pb-2.5 border-b flex-wrap min-w-0"
             :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="h-8 w-8 rounded-md bg-purple-500/15 text-purple-700 dark:text-purple-400 border border-purple-500/30 flex items-center justify-center shrink-0">
              <Radio :size="16" />
            </div>
            <div class="min-w-0">
              <div class="text-[10px] font-bold uppercase tracking-wider text-purple-700 dark:text-purple-400 truncate">km {{ Number(panel.kilometer).toFixed(1) }} • {{ panel.town }}</div>
              <h4 class="font-bold text-sm truncate" :class="store.theme === 'dark' ? 'text-white' : 'text-slate-900'">{{ panel.name }}</h4>
            </div>
          </div>
          <span class="px-2 py-1 rounded-md text-[10px] font-bold border shrink-0"
                :class="panel.is_real_sensor
                  ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
                  : 'bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-white/10'">
            {{ panel.sensor_source }}
          </span>
        </div>

        <!-- Micro-climate KPIs -->
        <div class="grid grid-cols-3 gap-2 text-center">
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Weather</div>
            <div class="text-xs font-black text-amber-600 dark:text-amber-400">{{ panel.weather }}</div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Air Temp</div>
            <div class="text-xs font-black font-mono text-sky-600 dark:text-sky-400">{{ Number(panel.air_temperature_c).toFixed(1) }}°C</div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Road Surf T</div>
            <div class="text-xs font-black font-mono text-orange-600 dark:text-orange-400">{{ Number(panel.road_temperature_c).toFixed(1) }}°C</div>
          </div>
        </div>

        <!-- Markov Weather Transition Matrix -->
        <div v-if="panel.markov_matrix" class="space-y-1">
          <div class="text-[9px] font-bold uppercase text-slate-500 dark:text-slate-400">Markov Weather Transition Matrix P(S_t+1 | S_t)</div>
          <div class="grid grid-cols-4 gap-1 text-[10px] font-mono text-center p-2.5 rounded-lg border"
               :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/80'">
            <div class="text-slate-500 dark:text-slate-400 font-sans font-bold text-left">From \ To</div>
            <div class="font-bold text-amber-600 dark:text-amber-400">Sunny</div>
            <div class="font-bold text-slate-600 dark:text-slate-300">Cloudy</div>
            <div class="font-bold text-blue-600 dark:text-blue-400">Rainy</div>
            <template v-for="(probs, stateName) in panel.markov_matrix" :key="stateName">
              <div class="text-left font-sans font-bold"
                   :class="panel.weather === stateName ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-500 dark:text-slate-400'">
                {{ stateName }}
              </div>
              <div :class="panel.weather === stateName ? 'font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 rounded' : 'text-slate-700 dark:text-slate-300'">
                {{ formatProbPct(probs?.Sunny) }}
              </div>
              <div :class="panel.weather === stateName ? 'font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 rounded' : 'text-slate-700 dark:text-slate-300'">
                {{ formatProbPct(probs?.Cloudy) }}
              </div>
              <div :class="panel.weather === stateName ? 'font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 rounded' : 'text-slate-700 dark:text-slate-300'">
                {{ formatProbPct(probs?.Rainy) }}
              </div>
            </template>
          </div>
        </div>

        <!-- Active HLA Federation Contracts & UAV Hangar -->
        <div class="p-2.5 rounded-md border space-y-1.5"
             :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/80'">
          <div class="flex items-center justify-between text-[10px]">
            <span class="font-bold text-[#00305E] dark:text-sky-400">Active HLA Contracts in Cell ({{ panel.coverage_radius_km }} km)</span>
            <span class="font-mono font-bold text-slate-800 dark:text-slate-200">{{ panel.active_contracts_count }} Linked</span>
          </div>
          <div v-if="panel.active_contracts?.length" class="space-y-1">
            <div v-for="c in panel.active_contracts" :key="c.contract_id"
                 class="flex items-center justify-between text-[10px] font-mono px-2.5 py-1.5 rounded-md border"
                 :class="store.theme === 'dark' ? 'bg-slate-900/80 border-white/10 text-slate-200' : 'bg-white border-slate-200 text-slate-800'">
              <span class="font-bold">Veh #{{ String(c.vehicle_id).slice(-4) }}</span>
              <span class="font-semibold text-[#00305E] dark:text-sky-300">Solver: {{ (c.active_solver || 'POD').replace('FOM', 'FEM') }}</span>
              <span class="font-bold text-emerald-700 dark:text-emerald-400">POD {{ (Number(c.pod_confidence) * 100).toFixed(0) }}%</span>
            </div>
          </div>
          <div v-else class="text-[10px] text-slate-500 dark:text-slate-400 italic">No vehicles currently inside this RSU cell.</div>
        </div>

        <!-- Active Context Broker / FIWARE Instance Link -->
        <div v-if="panel.broker_link"
             class="p-2 rounded-md border flex items-center justify-between gap-2 flex-wrap"
             :class="store.theme === 'dark' ? 'bg-slate-950/70 border-white/5' : 'bg-slate-50/90 border-slate-200/80'">
          <div class="flex items-center gap-1.5 min-w-0">
            <Database :size="12" :class="panel.broker_link.fiware_connected ? 'text-emerald-500 shrink-0' : 'text-[#00305E] dark:text-sky-400 shrink-0'" />
            <span class="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase border shrink-0"
                  :class="panel.broker_link.fiware_connected
                    ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/25'
                    : 'bg-[#00305E]/10 text-[#00305E] border-[#00305E]/20 dark:bg-sky-500/15 dark:text-sky-300 dark:border-sky-400/30'">
              {{ panel.broker_link.fiware_connected ? 'FIWARE Live' : 'Native Broker' }}
            </span>
            <span class="font-mono text-[10px] text-slate-600 dark:text-slate-300 truncate">
              {{ panel.broker_link.entity_type }}:{{ panel.broker_link.entity_id }} · sg={{ panel.broker_link.service_group }}
            </span>
          </div>
          <div class="flex items-center gap-1.5 shrink-0 text-[10px] font-bold">
            <a :href="resolveEntityApiUrl(panel.broker_link.entity_api_url)" target="_blank"
               class="flex items-center gap-1 px-2 py-0.5 rounded border text-[#00305E] dark:text-sky-400 hover:bg-[#00305E]/10 dark:hover:bg-sky-500/10 no-underline"
               :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200'">
              <span>{{ panel.broker_link.fiware_connected ? 'FIWARE JSON' : 'Entity JSON' }}</span>
              <ExternalLink :size="10" />
            </a>
            <a v-if="panel.broker_link.fiware_connected"
               :href="panel.broker_link.orion_url" target="_blank"
               class="flex items-center gap-1 px-2 py-0.5 rounded border text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/10 no-underline"
               :class="store.theme === 'dark' ? 'border-emerald-500/30' : 'border-emerald-300'">
              <span>Orion :1026</span>
              <ExternalLink :size="10" />
            </a>
            <button @click="store.setCurrentView('fiware-status')"
                    class="px-2 py-0.5 rounded border text-slate-600 dark:text-slate-300 hover:bg-slate-500/10 cursor-pointer"
                    :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200'">
              Broker Tab
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- ================================================================== -->
    <!-- 6. AUTONOMOUS DRONE INSPECTOR (5-Stage Mission + Energetics)       -->
    <!-- ================================================================== -->
    <template v-else-if="panelType === 'drone'">
      <div class="p-3.5 rounded-lg border shadow-xs space-y-3"
           :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/10' : 'bg-white border-slate-200'">
        <div class="flex items-center justify-between gap-2.5 pb-2.5 border-b flex-wrap min-w-0"
             :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="h-8 w-8 rounded-md bg-[#00305E]/15 text-[#00305E] dark:text-[#8ecae6] border border-[#00305E]/30 flex items-center justify-center shrink-0">
              <Plane :size="16" />
            </div>
            <div class="min-w-0">
              <div class="text-[10px] font-bold uppercase tracking-wider text-[#00305E] dark:text-[#8ecae6] truncate">{{ panel.payload_sensor }}</div>
              <h4 class="font-bold text-sm truncate" :class="store.theme === 'dark' ? 'text-white' : 'text-slate-900'">UAV #{{ panel.drone_id }} ({{ panel.home_rsu_name }})</h4>
            </div>
          </div>
          <span class="px-2 py-1 rounded-md text-[10px] font-bold bg-[#00305E]/15 text-[#00305E] dark:text-[#8ecae6] border border-[#00305E]/30 shrink-0">
            {{ formatDroneState(panel.flight_state) }}
          </span>
        </div>

        <!-- 5-Stage Flight Mission Stepper -->
        <div class="grid grid-cols-5 gap-1 pt-0.5">
          <div v-for="stage in droneStages" :key="stage.id"
               class="text-center py-1 px-1 rounded-md border text-[9.5px] font-bold truncate transition-all"
               :class="isDroneStageActive(stage.id, panel.flight_state)
                 ? 'bg-[#00305E] text-white border-[#00305E] shadow-xs'
                 : 'bg-slate-100 dark:bg-slate-800/80 text-slate-600 dark:text-slate-400 border-slate-200/70 dark:border-white/5'">
            {{ stage.label }}
          </div>
        </div>

        <!-- Mission Progress Bar -->
        <div class="space-y-1">
          <div class="flex justify-between text-[10px] font-semibold">
            <span class="text-slate-500 dark:text-slate-400">Target Warning: <b class="text-amber-600 dark:text-amber-400 font-mono">#{{ panel.target_warning_id }} (km {{ Number(panel.target_warning_km || 0).toFixed(1) }})</b></span>
            <span class="text-[#00305E] dark:text-[#8ecae6] font-bold font-mono">{{ Number(panel.mission_progress_pct).toFixed(0) }}%</span>
          </div>
          <div class="w-full h-2 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
            <div class="h-full bg-gradient-to-r from-[#00305E] via-[#5096BE] to-[#BECD32] rounded-full transition-all duration-300"
                 :style="{ width: `${Math.min(100, Math.max(4, Number(panel.mission_progress_pct || 0)))}%` }"></div>
          </div>
        </div>

        <!-- Altitude, Speed, Battery & Bearing KPIs -->
        <div class="grid grid-cols-4 gap-1.5 text-center">
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Altitude</div>
            <div class="text-xs font-black font-mono text-[#00305E] dark:text-[#8ecae6]">{{ Number(panel.altitude_m).toFixed(1) }} m</div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Airspeed</div>
            <div class="text-xs font-black font-mono text-slate-800 dark:text-slate-100">{{ Number(panel.velocity_kmh).toFixed(1) }} km/h</div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Bearing</div>
            <div class="text-xs font-black font-mono text-cyan-700 dark:text-cyan-400">{{ Number(panel.bearing_deg).toFixed(0) }}°</div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Battery</div>
            <div class="text-xs font-black font-mono text-emerald-700 dark:text-emerald-400">{{ Number(panel.battery_pct).toFixed(0) }}%</div>
          </div>
        </div>
      </div>
    </template>

    <!-- ================================================================== -->
    <!-- 7. WARNING POINT INSPECTOR (Anomaly Classification & UAV Dispatch) -->
    <!-- ================================================================== -->
    <template v-else-if="panelType === 'warning'">
      <div class="p-3.5 rounded-lg border shadow-xs space-y-3"
           :class="[
             store.theme === 'dark' ? 'bg-slate-900/90' : 'bg-white',
             warningColorConfig.borderClass
           ]">
        <div class="flex items-center justify-between gap-2.5 pb-2.5 border-b flex-wrap min-w-0"
             :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="h-8 w-8 rounded-md flex items-center justify-center shrink-0 border"
                 :class="warningColorConfig.iconBoxClass">
              <AlertTriangle :size="16" />
            </div>
            <div class="min-w-0">
              <div class="text-[10px] font-bold uppercase tracking-wider truncate" :class="warningColorConfig.titleTagClass">
                Warning #{{ panel.warning_id }} • {{ panel.carriageway }}
              </div>
              <h4 class="font-bold text-sm truncate" :class="store.theme === 'dark' ? 'text-white' : 'text-slate-900'" :title="panel.anomaly_type">{{ panel.anomaly_type }}</h4>
            </div>
          </div>
          <span class="px-2 py-1 rounded-md text-[10px] font-black uppercase border shrink-0"
                :class="warningColorConfig.severityBadgeClass">
            {{ panel.severity }}
          </span>
        </div>

        <p class="text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed">{{ panel.anomaly_description }}</p>

        <!-- 3-Stage Lifecycle Stepper -->
        <div class="grid grid-cols-3 gap-1.5">
          <div v-for="st in warningStages" :key="st"
               class="text-center py-1 px-2 rounded-lg border text-[10px] font-bold transition-all"
               :class="panel.status === st
                 ? (st === 'Inspected'
                   ? 'bg-[#00AA82] text-white border-[#00916e] shadow-xs'
                   : st === 'Under Inspection'
                     ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-xs'
                     : 'bg-[#AF2D37] text-white border-[#8e222a] shadow-xs')
                 : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border-slate-200/70 dark:border-transparent'">
            {{ st }}
          </div>
        </div>

        <!-- Structural Metrics & Trigger Snapshot -->
        <div class="grid grid-cols-3 gap-2 text-center">
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Location</div>
            <div class="text-xs font-black font-mono">km {{ Number(panel.kilometer).toFixed(2) }}</div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Est. Rutting</div>
            <div class="text-xs font-black font-mono text-rose-600 dark:text-rose-400">{{ Number(panel.estimated_rut_depth_mm).toFixed(1) }} mm</div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Confidence</div>
            <div class="text-xs font-black font-mono text-emerald-600 dark:text-emerald-400">{{ (Number(panel.confidence_score) * 100).toFixed(0) }}%</div>
          </div>
        </div>

        <!-- Triggering Vehicle & Assigned UAV Dispatch -->
        <div class="p-2.5 rounded-lg border space-y-1.5 text-[10px]"
             :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/80'">
          <div class="flex justify-between">
            <span class="text-slate-500 dark:text-slate-400">Triggered By:</span>
            <span class="font-bold font-mono text-slate-800 dark:text-slate-100">{{ formatVehicleId(panel.triggered_by_vehicle_id) }} ({{ Number(panel.trigger_velocity_kmh).toFixed(0) }} km/h, {{ (Number(panel.trigger_weight_kg) / 1000).toFixed(1) }} t)</span>
          </div>
          <div class="flex justify-between">
            <span class="text-slate-500 dark:text-slate-400">Assigned Edge RSU:</span>
            <span class="font-bold text-purple-700 dark:text-purple-400">{{ panel.assigned_rsu_name }}</span>
          </div>
          <div v-if="panel.assigned_drone_id" class="pt-1.5 border-t border-slate-200 dark:border-white/10">
            <div class="flex justify-between mb-1">
              <span class="font-bold"
                    :class="panel.status === 'Inspected' ? 'text-emerald-700 dark:text-emerald-400' : 'text-indigo-700 dark:text-indigo-400'">
                Dispatched UAV #{{ panel.assigned_drone_id }} ({{ panel.status === 'Inspected' ? 'Mission Complete' : panel.drone_flight_state }})
              </span>
              <span class="font-mono font-bold">{{ Number(panel.status === 'Inspected' ? 100 : panel.drone_mission_progress_pct).toFixed(0) }}%</span>
            </div>
            <div class="w-full h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
              <div class="h-full rounded-full transition-all duration-300"
                   :class="panel.status === 'Inspected' ? 'bg-emerald-500' : 'bg-indigo-500'"
                   :style="{ width: `${Math.min(100, Number(panel.status === 'Inspected' ? 100 : (panel.drone_mission_progress_pct || 0)))}%` }"></div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ================================================================== -->
    <!-- 8. EMBEDDED PAVEMENT INSTRUMENTATION STATION INSPECTOR             -->
    <!-- ================================================================== -->
    <template v-else-if="panelType === 'embedded_sensor'">
      <div class="p-3.5 rounded-lg border shadow-xs space-y-3"
           :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/10' : 'bg-white border-slate-200'">
        <div class="flex items-center justify-between gap-2.5 pb-2.5 border-b flex-wrap min-w-0"
             :class="store.theme === 'dark' ? 'border-white/10' : 'border-slate-200/80'">
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="h-8 w-8 rounded-md bg-teal-500/15 text-teal-600 dark:text-teal-400 border border-teal-500/30 flex items-center justify-center shrink-0">
              <Activity :size="16" />
            </div>
            <div class="min-w-0">
              <div class="text-[10px] font-bold uppercase tracking-wider text-teal-600 dark:text-teal-400 truncate">
                km {{ Number(panel.kilometer || 0).toFixed(1) }} • Station {{ panel.station_id }}
              </div>
              <h4 class="font-bold text-sm truncate" :class="store.theme === 'dark' ? 'text-white' : 'text-slate-900'">
                {{ panel.name }}
              </h4>
            </div>
          </div>
          <span class="px-2 py-1 rounded-md text-[10px] font-bold border shrink-0"
                :class="panel.latest_frame ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30' : 'bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/20'">
            {{ panel.latest_frame ? 'LIVE DAQ' : 'STANDBY' }}
          </span>
        </div>

        <div v-if="panel.latest_frame" class="grid grid-cols-3 gap-2 text-center">
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Microstrain</div>
            <div class="text-xs font-black font-mono text-teal-600 dark:text-teal-400">
              {{ panel.latest_frame.strain_ue != null ? `${Number(panel.latest_frame.strain_ue).toFixed(1)} µε` : '—' }}
            </div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Pressure</div>
            <div class="text-xs font-black font-mono text-cyan-600 dark:text-cyan-400">
              {{ panel.latest_frame.pressure_kpa != null ? `${Number(panel.latest_frame.pressure_kpa).toFixed(0)} kPa` : '—' }}
            </div>
          </div>
          <div class="p-2 rounded-lg border" :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/60'">
            <div class="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">Layer Temp</div>
            <div class="text-xs font-black font-mono text-amber-600 dark:text-amber-400">
              {{ panel.latest_frame.temperature_c != null ? `${Number(panel.latest_frame.temperature_c).toFixed(1)} °C` : '—' }}
            </div>
          </div>
        </div>

        <div v-else class="p-2.5 rounded-lg border text-[10.5px]"
             :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5 text-slate-400' : 'bg-slate-50 border-slate-200/70 text-slate-600'">
          Awaiting physical DAQ frame on <code class="font-mono">POST /api/telemetry/sensors/{{ panel.station_id }}</code>. Displaying configured sensor channels below.
        </div>

        <div v-if="panel.hardware_catalog" class="p-2.5 rounded-lg border space-y-1 text-[10px]"
             :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/5' : 'bg-slate-50 border-slate-200/80'">
          <div class="flex items-center justify-between gap-2 mb-1">
            <span class="text-[9px] font-bold uppercase text-slate-500 dark:text-slate-400 shrink-0">Instrumented Channel Stack</span>
            <span class="text-[9px] font-mono text-slate-500 dark:text-slate-400 truncate">{{ panel.model }}</span>
          </div>
          <div v-for="(spec, chan) in panel.hardware_catalog" :key="chan"
               class="flex items-center justify-between gap-2 py-0.5 border-t first:border-t-0"
               :class="store.theme === 'dark' ? 'border-white/5' : 'border-slate-200/60'">
            <span class="font-semibold text-slate-700 dark:text-slate-200">{{ chan }}</span>
            <span class="font-mono text-slate-500 dark:text-slate-400 truncate max-w-[170px]">{{ spec.model || spec.unit || 'Active' }}</span>
          </div>
        </div>
      </div>
    </template>

  </div>
</template>
