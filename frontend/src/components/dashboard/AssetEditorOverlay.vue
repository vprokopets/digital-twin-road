<script setup lang="ts">
import { ref, watch } from 'vue'
import { Edit3, PlusCircle, Save, RotateCcw, Check, Sliders, X, Trash2 } from 'lucide-vue-next'
import { useDashboardStore } from '../../stores/dashboard'

defineProps<{
  isSaving: boolean
  saveSuccessToast: boolean
}>()

const emit = defineEmits<{
  'add-rsu': []
  'save-scenario': []
  'discard-edits': []
  'delete-rsu': []
  'apply-changes': [buffer: Record<string, any>]
}>()

const store = useDashboardStore()
const inspectorEditBuffer = ref<Record<string, any>>({})

watch(
  () => [store.selectedType, store.selectedFeature?.properties?.id ?? store.selectedFeature?.properties?.ID],
  () => {
    const feat = store.selectedFeature
    if (feat?.properties) {
      inspectorEditBuffer.value = { ...feat.properties }
    } else {
      inspectorEditBuffer.value = {}
    }
  },
  { immediate: true }
)

const onVehicleClassChange = () => {
  const cls = String(inspectorEditBuffer.value.VehicleClass || '')
  if (cls.includes('4-Axle')) {
    inspectorEditBuffer.value.Axles = 4
    inspectorEditBuffer.value.Weight = 36000
  } else if (cls.includes('6-Axle')) {
    inspectorEditBuffer.value.Axles = 6
    inspectorEditBuffer.value.Weight = 44000
  } else {
    inspectorEditBuffer.value.Axles = 5
    inspectorEditBuffer.value.Weight = 40000
  }
}

const submitChanges = () => {
  if (store.selectedType === 'SingleVehicleStateDS') {
    const vehiclePayload: Record<string, any> = {}
    for (const key of ['VehicleClass', 'Axles', 'Weight', 'Velocity'] as const) {
      if (inspectorEditBuffer.value[key] !== undefined) {
        vehiclePayload[key] = inspectorEditBuffer.value[key]
      }
    }
    emit('apply-changes', vehiclePayload)
    return
  }
  emit('apply-changes', { ...inspectorEditBuffer.value })
}
</script>

<template>
  <!-- Floating Mode Switcher & Asset Editor Action Bar -->
  <div class="absolute top-3 left-3 z-[400] flex items-center gap-2 flex-wrap">
    <!-- Mode Toggle Pill -->
    <div class="flex items-center p-1 rounded-full bg-[#00305E]/92 backdrop-blur-md border border-[#5096BE]/50 shadow-lg text-xs">
      <button @click="store.setEditorMode(false)"
              :class="!store.isEditorMode ? 'bg-[#5096BE] text-white font-bold shadow-sm' : 'text-slate-300 hover:text-white'"
              class="flex items-center gap-1.5 px-3 py-1 rounded-full transition-all cursor-pointer">
        <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
        <span>Live Digital Shadow</span>
      </button>
      <button @click="store.setEditorMode(true)"
              :class="store.isEditorMode ? 'bg-amber-600 text-white font-bold shadow-sm' : 'text-slate-300 hover:text-white'"
              class="flex items-center gap-1.5 px-3 py-1 rounded-full transition-all cursor-pointer">
        <Edit3 :size="12" />
        <span>Asset Editor Mode</span>
      </button>
    </div>

    <!-- Editor Action Bar (Visible when in Editor Mode) -->
    <div v-if="store.isEditorMode"
         class="flex items-center gap-1.5 p-1 rounded-full bg-[#00305E]/92 backdrop-blur-md border border-amber-500/40 shadow-lg text-xs text-white">
      <button @click="emit('add-rsu')"
              class="flex items-center gap-1 px-2.5 py-1 rounded-full bg-purple-600/80 hover:bg-purple-600 text-white text-[11px] font-semibold transition-all cursor-pointer"
              title="Place a new V2X Roadside Unit at map center">
        <PlusCircle :size="12" />
        <span>Add RSU</span>
      </button>

      <button @click="emit('save-scenario')"
              :disabled="isSaving || !store.hasUnsavedEdits"
              :class="store.hasUnsavedEdits ? 'bg-emerald-600 hover:bg-emerald-500 text-white' : 'bg-slate-800 text-slate-400 cursor-not-allowed'"
              class="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all cursor-pointer">
        <Save :size="12" />
        <span>{{ isSaving ? 'Saving...' : 'Save Scenario' }}</span>
        <span v-if="store.hasUnsavedEdits" class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
      </button>

      <button @click="emit('discard-edits')"
              class="flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-medium transition-all cursor-pointer"
              title="Discard unsaved changes">
        <RotateCcw :size="12" />
        <span>Discard</span>
      </button>
    </div>

    <!-- Success Save Toast Notification -->
    <div v-if="saveSuccessToast"
         class="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-600 text-white text-xs font-bold shadow-lg animate-bounce">
      <Check :size="13" />
      <span>Scenario Saved!</span>
    </div>
  </div>

  <!-- Asset Parameter Inspector Panel (Offset below Leaflet Layers Control to avoid overlap) -->
  <div v-if="store.isEditorMode && store.selectedFeature"
       class="absolute top-16 right-3 z-[450] w-72 max-h-[calc(100%-84px)] overflow-y-auto bg-slate-900/95 backdrop-blur-md border border-amber-500/30 rounded-2xl p-3 text-white shadow-2xl flex flex-col gap-2.5 text-xs">

    <!-- Panel Header -->
    <div class="flex items-center justify-between pb-1.5 border-b border-white/10">
      <div class="flex items-center gap-1.5">
        <Sliders :size="13" class="text-amber-400" />
        <span class="font-bold text-white uppercase tracking-wider text-[11px]">Asset Inspector</span>
      </div>
      <button @click="store.clearSelection" class="text-slate-400 hover:text-white p-0.5 rounded cursor-pointer">
        <X :size="13" />
      </button>
    </div>

    <!-- 1. Roadside Unit Inspector -->
    <div v-if="store.selectedType === 'SingleRoadsideUnitsStateDS'" class="flex flex-col gap-2">
      <div class="flex items-center justify-between">
        <span class="text-purple-400 font-bold font-mono">{{ inspectorEditBuffer.tag || inspectorEditBuffer.id }}</span>
        <span class="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">V2X RSU</span>
      </div>

      <div class="flex flex-col gap-1">
        <label class="text-[10px] text-slate-400 font-medium">RSU Display Name</label>
        <input v-model="inspectorEditBuffer.name"
               class="px-2 py-1 bg-slate-800 border border-white/10 rounded text-xs text-white focus:outline-none focus:border-amber-400" />
      </div>

      <div class="grid grid-cols-2 gap-2">
        <div class="flex flex-col gap-1">
          <label class="text-[10px] text-slate-400 font-medium">Station (km)</label>
          <input type="number" step="0.1" v-model.number="inspectorEditBuffer.station_km"
                 class="px-2 py-1 bg-slate-800 border border-white/10 rounded text-xs text-white font-mono" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-[10px] text-slate-400 font-medium">Range (km)</label>
          <input type="number" step="1" min="2" max="25" v-model.number="inspectorEditBuffer.coverage_radius_km"
                 class="px-2 py-1 bg-slate-800 border border-white/10 rounded text-xs text-white font-mono" />
        </div>
      </div>

      <!-- Environmental Overrides for What-If Scenarios -->
      <div class="pt-1.5 border-t border-white/10 flex flex-col gap-1.5">
        <span class="text-[10px] font-bold text-amber-400 uppercase tracking-wider">Environmental What-If</span>

        <div class="grid grid-cols-2 gap-2">
          <div class="flex flex-col gap-0.5">
            <label class="text-[9px] text-slate-400">Air Temp (°C)</label>
            <input type="number" step="0.5" v-model.number="inspectorEditBuffer.AirTemperature"
                   class="px-2 py-1 bg-slate-800 border border-white/10 rounded text-xs text-white font-mono" />
          </div>
          <div class="flex flex-col gap-0.5">
            <label class="text-[9px] text-slate-400">Surface Temp (°C)</label>
            <input type="number" step="0.5" v-model.number="inspectorEditBuffer.RoadSurfaceTemperature"
                   class="px-2 py-1 bg-slate-800 border border-white/10 rounded text-xs text-white font-mono" />
          </div>
        </div>

        <div class="flex flex-col gap-0.5">
          <label class="text-[9px] text-slate-400">Weather Condition</label>
          <select v-model="inspectorEditBuffer.WeatherState"
                  class="px-2 py-1 bg-slate-800 border border-white/10 rounded text-xs text-white">
            <option value="Sunny">Sunny (High Solar Irradiance)</option>
            <option value="Cloudy">Cloudy (Overcast Diffuse)</option>
            <option value="Rainy">Rainy (Wet Pavement Cooling)</option>
            <option value="Snowy">Snowy (Freezing Precipitation)</option>
          </select>
        </div>
      </div>

      <!-- Inspector Actions -->
      <div class="flex items-center gap-2 pt-2 border-t border-white/10">
        <button @click="submitChanges"
                class="flex-1 py-1 rounded bg-amber-600 hover:bg-amber-500 font-bold text-xs text-white transition-all cursor-pointer text-center">
          Apply Changes
        </button>
        <button @click="emit('delete-rsu')"
                class="p-1 rounded bg-rose-600/20 hover:bg-rose-600 text-rose-300 hover:text-white border border-rose-500/30 transition-all cursor-pointer"
                title="Delete this RSU">
          <Trash2 :size="13" />
        </button>
      </div>
    </div>

    <!-- 2. Vehicle Inspector -->
    <div v-else-if="store.selectedType === 'SingleVehicleStateDS'" class="flex flex-col gap-2">
      <div class="flex items-center justify-between">
        <span class="text-blue-400 font-bold font-mono">HGV #{{ inspectorEditBuffer.id }}</span>
        <span class="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">Active Vehicle</span>
      </div>

      <div class="flex flex-col gap-1">
        <label class="text-[10px] text-slate-400 font-medium">Vehicle Class &amp; Axle Preset</label>
        <select v-model="inspectorEditBuffer.VehicleClass"
                @change="onVehicleClassChange"
                class="px-2 py-1 bg-slate-800 border border-white/10 rounded text-xs text-white">
          <option value="5-Axle Semi-Trailer (40t)">5-Axle Semi-Trailer (40t) — EU Standard N3</option>
          <option value="4-Axle Heavy Dumper (36t)">4-Axle Heavy Dumper (36t) — Tandem Steer</option>
          <option value="6-Axle Low-Loader HGV (44t)">6-Axle Low-Loader (44t) — Heavy Transport</option>
        </select>
      </div>

      <div class="flex flex-col gap-1">
        <div class="flex justify-between text-[10px]">
          <span class="text-slate-400">Total Gross Weight:</span>
          <span class="font-mono font-bold text-amber-300">{{ (inspectorEditBuffer.Weight / 1000).toFixed(1) }} t</span>
        </div>
        <input type="range" min="15000" max="48000" step="500" v-model.number="inspectorEditBuffer.Weight"
               class="w-full accent-amber-500 cursor-pointer h-1.5 bg-slate-700 rounded-lg" />
      </div>

      <div class="flex flex-col gap-1">
        <div class="flex justify-between text-[10px]">
          <span class="text-slate-400">Cruise Velocity:</span>
          <span class="font-mono font-bold text-emerald-300">{{ Number(inspectorEditBuffer.Velocity || 85).toFixed(0) }} km/h</span>
        </div>
        <input type="range" min="30" max="110" step="1" v-model.number="inspectorEditBuffer.Velocity"
               class="w-full accent-emerald-500 cursor-pointer h-1.5 bg-slate-700 rounded-lg" />
      </div>

      <button @click="submitChanges"
              class="mt-1 py-1 rounded bg-blue-600 hover:bg-blue-500 font-bold text-xs text-white transition-all cursor-pointer text-center">
        Apply Vehicle Parameters
      </button>
    </div>
  </div>
</template>
