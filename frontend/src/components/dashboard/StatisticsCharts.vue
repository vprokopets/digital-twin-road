<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { Line } from 'vue-chartjs'
import { useDashboardStore } from '../../stores/dashboard'
import { Clock, Navigation, Activity } from 'lucide-vue-next'
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
const hasData = ref(false)

// Telemetry Metric Selection (Filtered strictly to physical/temperature metrics)
const currentYAxis = ref<string>('ALL_TEMPS')

// X-Axis Mode: 'timestamp' vs 'kilometer'
const xAxisMode = ref<'timestamp' | 'kilometer'>('timestamp')

const chartData = ref({
  labels: [] as string[],
  datasets: [] as any[]
})

const chartOptions = ref<any>({
  responsive: true,
  maintainAspectRatio: false,
  scales: {
    y: {
      beginAtZero: false,
      grace: '10%'
    }
  },
  plugins: {
    legend: {
      display: false
    }
  }
})

interface MetricOption {
  id: string
  label: string
  unit: string
}

// Helper to retrieve metric values whether at top-level of stats or inside stats.State array
const getMetricArray = (key: string): number[] => {
  const stats = store.selectedData?.stats
  if (!stats) return []

  const checkKeys = key === 'Velocity' 
    ? ['Velocity', 'velocity', 'Speed', 'speed'] 
    : key === 'ExtrapolatedVelocity'
    ? ['ExtrapolatedVelocity', 'extrapolated_velocity', 'ExtrapolatedSpeed', 'effectiveVelocity', 'StationRateKmH']
    : [key]

  for (const k of checkKeys) {
    if (Array.isArray(stats[k]) && stats[k].length > 0) {
      return stats[k].map(Number)
    }
  }

  if (Array.isArray(stats.State) && stats.State.length > 0) {
    const first = stats.State[0]
    if (first && typeof first === 'object') {
      for (const k of checkKeys) {
        if (k in first) {
          return stats.State.map((s: any) => Number(s?.[k])).filter((v: number) => !isNaN(v))
        }
      }
    }
  }
  return []
}

// Available Y-axis metrics: supports Vehicle, RSU, Road Segment, Drone, Warning, Junction, and Water Source telemetry
const availableMetrics = computed<MetricOption[]>(() => {
  const stats = store.selectedData?.stats
  if (!stats) return []

  const opts: MetricOption[] = []
  const isDrone = store.selectedType === 'SingleDroneStateDS'
  
  const hasVelocity = getMetricArray('Velocity').length > 0
  const hasAltitude = getMetricArray('Altitude').length > 0
  const hasBattery = getMetricArray('BatteryPct').length > 0
  const hasMissionProg = getMetricArray('MissionProgressPct').length > 0
  const hasInspProg = getMetricArray('InspectionProgressPct').length > 0
  const hasRutDepth = getMetricArray('EstimatedRutDepthMm').length > 0
  const hasSurface = getMetricArray('RoadSurfaceTemperature').length > 0
  const hasAir = getMetricArray('AirTemperature').length > 0
  const hasSoil = getMetricArray('SoilTemperature').length > 0
  const hasMoisture = getMetricArray('MoistureSaturationPct').length > 0
  const hasDamage = getMetricArray('Damage').length > 0

  if (hasSurface && hasAir) {
    opts.push({ id: 'ALL_TEMPS', label: 'All Temperatures (Overlay)', unit: '°C' })
  }
  if (hasAltitude) {
    opts.push({ id: 'Altitude', label: 'UAV Altitude (AGL)', unit: 'm' })
  }
  if (hasVelocity) {
    opts.push({ 
      id: 'Velocity', 
      label: isDrone ? 'UAV Airspeed' : 'Velocity (Standard vs Extrapolated)', 
      unit: 'km/h' 
    })
  }
  if (hasBattery) {
    opts.push({ id: 'BatteryPct', label: 'UAV Battery State of Charge', unit: '%' })
  }
  if (hasMissionProg) {
    opts.push({ id: 'MissionProgressPct', label: 'UAV Mission Progress', unit: '%' })
  } else if (hasInspProg) {
    opts.push({ id: 'InspectionProgressPct', label: 'UAV Inspection Progress', unit: '%' })
  }
  if (hasRutDepth) {
    opts.push({ id: 'EstimatedRutDepthMm', label: 'Estimated Rut Depth', unit: 'mm' })
  }
  if (hasSurface) {
    opts.push({ id: 'RoadSurfaceTemperature', label: 'Road Surface Temperature', unit: '°C' })
  }
  if (hasAir) {
    opts.push({ id: 'AirTemperature', label: 'Air Temperature', unit: '°C' })
  }
  if (hasSoil) {
    opts.push({ id: 'SoilTemperature', label: 'Subgrade Soil Temperature', unit: '°C' })
  }
  if (hasMoisture) {
    opts.push({ id: 'MoistureSaturationPct', label: 'Subgrade Moisture Saturation', unit: '%' })
  }
  if (hasDamage) {
    opts.push({ id: 'Damage', label: 'Deformation Damage', unit: '' })
  }

  // Fallback if none of the explicit keys matched
  if (opts.length === 0) {
    const cols = Object.keys(stats).filter(k => 
      k.toLowerCase().includes('temp') || 
      k.toLowerCase().includes('vel') || 
      k.toLowerCase().includes('speed')
    )
    cols.forEach(c => {
      const unit = c.toLowerCase().includes('temp') ? '°C' : (c.toLowerCase().includes('vel') || c.toLowerCase().includes('speed')) ? 'km/h' : ''
      opts.push({ id: c, label: c, unit })
    })
  }

  return opts
})

// Robustly find the best kilometer array (prioritizing arrays that actually update/vary)
const getKilometerArray = (stats: any): number[] | null => {
  if (!stats) return null
  const candidates = ['Kilometer', 'IntervalBegin', 'IntervalEnd', 'LastPosition']

  // 1. First priority: find a candidate whose values vary over time
  for (const key of candidates) {
    const arr = stats[key]
    if (Array.isArray(arr) && arr.length > 0) {
      const numArr = arr.map(Number)
      const validNums = numArr.filter(v => typeof v === 'number' && !isNaN(v))
      if (validNums.length > 1) {
        const min = Math.min(...validNums)
        const max = Math.max(...validNums)
        if (max !== min) {
          return numArr
        }
      }
    }
  }

  // 2. Fallback: return the first existing candidate array
  for (const key of candidates) {
    const arr = stats[key]
    if (Array.isArray(arr) && arr.length > 0) {
      return arr.map(Number)
    }
  }

  return null
}

// Radial distance profile detection (Water Source 0 m .. 5000 m attenuation)
const isRadialDistanceProfile = computed(() => {
  if (store.selectedType === 'SingleWaterStateDS') return true
  const ts = store.selectedData?.stats?.Timestamp
  if (Array.isArray(ts) && ts.length > 0) {
    return ts.every((v: any) => /^\d+(?:\.\d+)?\s*m$/i.test(String(v).trim()))
  }
  return false
})

// Show Time | Kilometer switcher only when corridor chainage actually varies (moving vehicles)
const hasVaryingKilometerData = computed(() => {
  if (isRadialDistanceProfile.value) return false
  if (store.selectedType === 'SingleVehicleStateDS') return true
  const arr = getKilometerArray(store.selectedData?.stats)
  if (!arr || arr.length < 2) return false
  const valid = arr.filter((v) => typeof v === 'number' && !isNaN(v))
  if (valid.length < 2) return false
  return Math.max(...valid) !== Math.min(...valid)
})

watch(hasVaryingKilometerData, (varying) => {
  if (!varying && xAxisMode.value === 'kilometer') {
    xAxisMode.value = 'timestamp'
  }
})

const getXValues = (stats: any): { labels: string[], fullLabels: string[] } => {
  if (!stats) return { labels: [], fullLabels: [] }

  if (xAxisMode.value === 'kilometer' && hasVaryingKilometerData.value) {
    const kmArray = getKilometerArray(stats)
    if (kmArray && kmArray.length > 0) {
      const validNums = kmArray.filter(v => typeof v === 'number' && !isNaN(v))
      const min = validNums.length ? Math.min(...validNums) : 0
      const max = validNums.length ? Math.max(...validNums) : 0
      const span = Math.abs(max - min)

      // Choose precision dynamically so ticks are distinct and meaningful
      const decimals = span === 0 ? 1 : span < 0.2 ? 3 : span < 5 ? 2 : 1

      const labels = kmArray.map((v: any) => {
        const n = Number(v)
        return isNaN(n) ? String(v) : `${n.toFixed(decimals)} km`
      })
      const fullLabels = kmArray.map((v: any) => {
        const n = Number(v)
        return isNaN(n) ? String(v) : `Corridor Chainage: ${n.toFixed(3)} km`
      })
      return { labels, fullLabels }
    }
  }

  // Default to Timestamp or Radial Distance labels
  const tsArray = stats.Timestamp || []
  if (Array.isArray(tsArray) && tsArray.length > 0) {
    const labels = tsArray.map((ts: any) => {
      const str = String(ts)
      const dtMatch = str.match(/^\d{4}-\d{2}-\d{2}[ T](\d{2}:\d{2}:\d{2})/)
      if (dtMatch) {
        return dtMatch[1] // HH:mm:ss
      }
      return str
    })
    const fullLabels = tsArray.map((ts: any) => String(ts))
    return { labels, fullLabels }
  }

  // Fallback if Timestamp is not directly an array
  const metricLen = getMetricArray(currentYAxis.value).length
  if (metricLen > 0) {
    const labels = Array.from({ length: metricLen }, (_, i) => `T+${i * 5}s`)
    return { labels, fullLabels: labels }
  }

  return { labels: [], fullLabels: [] }
}

const getYAxisTitle = (metricId: string): string => {
  if (metricId === 'Velocity') return 'Velocity [km/h]'
  if (metricId === 'Damage') return 'Damage Index []'
  if (metricId === 'ALL_TEMPS' || metricId.toLowerCase().includes('temp')) return 'Temperature [°C]'
  const m = availableMetrics.value.find(item => item.id === metricId)
  return m ? (m.unit ? `${m.label} [${m.unit}]` : m.label) : metricId
}

const updateChart = () => {
    const newData = store.selectedData
    const isDark = store.theme === 'dark'
    
    if (newData && newData.stats && availableMetrics.value.length > 0) {
        const stats = newData.stats
        
        // Ensure current selection is valid
        if (!availableMetrics.value.some(m => m.id === currentYAxis.value)) {
            currentYAxis.value = availableMetrics.value[0].id
        }

        let { labels, fullLabels } = getXValues(stats)

        let datasets: any[] = []

        if (currentYAxis.value === 'ALL_TEMPS') {
            // Multi-series overlay of all temperatures
            datasets = [
                {
                    label: 'Road Surface [°C]',
                    backgroundColor: 'rgba(245, 158, 11, 0.08)',
                    borderColor: isDark ? '#fbbf24' : '#d97706',
                    data: getMetricArray('RoadSurfaceTemperature'),
                    tension: 0.2,
                    pointRadius: 1.5,
                    borderWidth: 2
                },
                {
                    label: 'Air [°C]',
                    backgroundColor: 'rgba(56, 189, 248, 0.08)',
                    borderColor: isDark ? '#38bdf8' : '#0284c7',
                    data: getMetricArray('AirTemperature'),
                    tension: 0.2,
                    pointRadius: 1.5,
                    borderWidth: 2
                }
            ]
            const soilData = getMetricArray('SoilTemperature')
            if (soilData.length > 0) {
                datasets.push({
                    label: 'Soil [°C]',
                    backgroundColor: 'rgba(16, 185, 129, 0.08)',
                    borderColor: isDark ? '#34d399' : '#059669',
                    data: soilData,
                    tension: 0.2,
                    pointRadius: 1.5,
                    borderWidth: 2
                })
            }
        } else if (currentYAxis.value === 'Velocity' && store.selectedType === 'SingleVehicleStateDS') {
            // Dual comparison: Standard Reported Velocity vs REAL Map Icon Extrapolated Movement Speed
            const selId = String(store.selectedFeature?.properties?.id ?? '')
            const realExtrapList = (store.vehicleExtrapolations && store.vehicleExtrapolations[selId]) ? store.vehicleExtrapolations[selId] : []

            if (realExtrapList.length >= 2) {
                const liveLabels: string[] = []
                const liveFullLabels: string[] = []
                const stdVelSeries: number[] = []
                const extrapVelSeries: number[] = []

                for (const pt of realExtrapList) {
                    if (xAxisMode.value === 'kilometer') {
                        liveLabels.push(`${pt.km.toFixed(2)} km`)
                        liveFullLabels.push(`Corridor Chainage: ${pt.km.toFixed(3)} km | Drift: ${(pt.driftKm * 1000).toFixed(0)} m`)
                    } else {
                        liveLabels.push(pt.timestamp)
                        liveFullLabels.push(`Time: ${pt.timestamp} | Station: km ${pt.km.toFixed(2)}`)
                    }
                    stdVelSeries.push(pt.standardVelocity)
                    extrapVelSeries.push(pt.extrapolatedSpeed)
                }

                labels = liveLabels
                fullLabels = liveFullLabels

                datasets = [
                    {
                        label: 'Standard Velocity [km/h]',
                        backgroundColor: isDark ? 'rgba(129, 140, 248, 0.12)' : 'rgba(79, 70, 229, 0.08)',
                        borderColor: isDark ? '#818cf8' : '#4f46e5',
                        data: stdVelSeries,
                        tension: 0.15,
                        fill: false,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        borderWidth: 2.5
                    },
                    {
                        label: 'Extrapolated Speed [km/h] (Icon)',
                        backgroundColor: isDark ? 'rgba(56, 189, 248, 0.12)' : 'rgba(2, 132, 199, 0.08)',
                        borderColor: isDark ? '#38bdf8' : '#0284c7',
                        borderDash: [6, 4],
                        data: extrapVelSeries,
                        tension: 0.25,
                        fill: false,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        borderWidth: 2.2
                    }
                ]
            } else {
                // Fallback to static stats if live buffer has not accumulated points yet
                const stdVelData = getMetricArray('Velocity')
                datasets = [
                    {
                        label: 'Standard Velocity [km/h]',
                        backgroundColor: isDark ? 'rgba(129, 140, 248, 0.12)' : 'rgba(79, 70, 229, 0.08)',
                        borderColor: isDark ? '#818cf8' : '#4f46e5',
                        data: stdVelData,
                        tension: 0.15,
                        fill: false,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        borderWidth: 2.5
                    },
                    {
                        label: 'Extrapolated Speed [km/h] (Icon)',
                        backgroundColor: isDark ? 'rgba(56, 189, 248, 0.12)' : 'rgba(2, 132, 199, 0.08)',
                        borderColor: isDark ? '#38bdf8' : '#0284c7',
                        borderDash: [6, 4],
                        data: stdVelData,
                        tension: 0.25,
                        fill: false,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        borderWidth: 2.2
                    }
                ]
            }
        } else {
            // Single Metric View
            const metric = availableMetrics.value.find(m => m.id === currentYAxis.value)
            const label = metric ? (metric.unit ? `${metric.label} [${metric.unit}]` : metric.label) : currentYAxis.value
            
            let color = '#3b82f6'
            let bgColor = 'rgba(59, 130, 246, 0.15)'

            if (currentYAxis.value === 'Velocity') {
                color = isDark ? '#818cf8' : '#4f46e5'
                bgColor = isDark ? 'rgba(129, 140, 248, 0.15)' : 'rgba(79, 70, 229, 0.15)'
            } else if (currentYAxis.value.includes('Surface')) {
                color = isDark ? '#fbbf24' : '#d97706'
                bgColor = 'rgba(245, 158, 11, 0.15)'
            } else if (currentYAxis.value.includes('Air')) {
                color = isDark ? '#38bdf8' : '#0284c7'
                bgColor = 'rgba(56, 189, 248, 0.15)'
            } else if (currentYAxis.value.includes('Soil')) {
                color = isDark ? '#34d399' : '#059669'
                bgColor = 'rgba(16, 185, 129, 0.15)'
            } else if (currentYAxis.value.includes('Damage')) {
                color = isDark ? '#f43f5e' : '#e11d48'
                bgColor = 'rgba(244, 63, 94, 0.15)'
            }

            datasets = [
                {
                    label: label,
                    backgroundColor: bgColor,
                    borderColor: color,
                    data: getMetricArray(currentYAxis.value),
                    tension: 0.2,
                    fill: true,
                    pointRadius: 2,
                    borderWidth: 2
                }
            ]
        }

        chartData.value = {
            labels: labels,
            datasets: datasets
        }

        const isAllTemps = currentYAxis.value === 'ALL_TEMPS'
        const isKm = xAxisMode.value === 'kilometer' && hasVaryingKilometerData.value
        const xAxisTitle = isRadialDistanceProfile.value
            ? 'Radial Distance from Basin [m]'
            : isKm
                ? 'Corridor Chainage [km]'
                : 'Simulation Time [HH:mm:ss]'

        chartOptions.value = {
            responsive: true,
            maintainAspectRatio: false,
            animation: (currentYAxis.value === 'Velocity' && store.selectedType === 'SingleVehicleStateDS') ? { duration: 150 } : undefined,
            layout: {
                padding: {
                    bottom: 12,
                    top: 6,
                    left: 4,
                    right: 8
                }
            },
            scales: {
                x: {
                    grid: { color: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)' },
                    ticks: {
                        color: isDark ? '#94a3b8' : '#64748b',
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 6,
                        font: { size: 10 }
                    },
                    title: {
                        display: true,
                        text: xAxisTitle,
                        color: isDark ? '#94a3b8' : '#64748b',
                        font: { size: 10, weight: 'bold' },
                        padding: { top: 8 }
                    }
                },
                y: {
                    beginAtZero: false,
                    grace: '10%',
                    grid: { color: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)' },
                    ticks: {
                        color: isDark ? '#94a3b8' : '#64748b',
                        font: { size: 10 }
                    },
                    title: {
                        display: true,
                        text: getYAxisTitle(currentYAxis.value),
                        color: isDark ? '#94a3b8' : '#64748b',
                        font: { size: 10, weight: 'bold' }
                    }
                }
            },
            plugins: {
                legend: {
                    display: isAllTemps || datasets.length > 1,
                    position: 'top',
                    labels: {
                        color: isDark ? '#cbd5e1' : '#475569',
                        boxWidth: 12,
                        font: { size: 10, weight: '600' },
                        padding: 10
                    }
                },
                tooltip: {
                    callbacks: {
                        title: (tooltipItems: any[]) => {
                            if (!tooltipItems.length) return ''
                            const idx = tooltipItems[0].dataIndex
                            return fullLabels[idx] || tooltipItems[0].label
                        },
                        label: (context: any) => {
                            const val = typeof context.parsed.y === 'number' ? context.parsed.y.toFixed(1) : context.parsed.y
                            const unit = currentYAxis.value === 'Velocity' ? ' km/h' : ''
                            return `${context.dataset.label}: ${val}${unit}`
                        }
                    }
                }
            }
        }
        hasData.value = labels.length > 0 && datasets.some(d => Array.isArray(d.data) && d.data.length > 0)
    } else {
        hasData.value = false
    }
}

watch([() => store.selectedData, () => store.theme, currentYAxis, xAxisMode], () => {
    updateChart()
}, { deep: true, immediate: true })

watch(() => {
    const selId = String(store.selectedFeature?.properties?.id ?? '')
    const list = store.vehicleExtrapolations?.[selId]
    return list ? list.length : 0
}, () => {
    if (currentYAxis.value === 'Velocity' && store.selectedType === 'SingleVehicleStateDS') {
        updateChart()
    }
})

</script>

<template>
  <div class="w-full h-full flex flex-col relative transition-colors"
       :class="store.theme === 'dark' ? 'bg-transparent' : 'bg-transparent'">
    
    <!-- Empty State -->
    <div v-if="!hasData" class="flex-1 flex flex-col items-center justify-center border-2 border-dashed rounded-lg w-full h-full p-6 text-center"
         :class="store.theme === 'dark' ? 'border-white/5 bg-slate-800/30' : 'border-slate-100 bg-slate-50/50'">
        <Activity :size="28" class="text-slate-400 mb-2 opacity-40 animate-pulse" />
        <p class="text-xs font-medium" :class="store.theme === 'dark' ? 'text-slate-400' : 'text-slate-600'">
          Select an active vehicle or roadside unit on the map to stream live telemetry & trend analytics.
        </p>
        <span class="text-[10px] text-slate-500 mt-1">Collecting route observations & dynamic telemetry...</span>
    </div>

    <!-- Active Chart View -->
    <div v-else class="flex-1 flex flex-col min-h-0 relative w-full h-full gap-2.5">
      
      <!-- Top Control Toolbar: X-Axis Selector & Y-Axis Metric Dropdown -->
      <div class="flex flex-wrap items-center justify-between gap-2 px-0.5 shrink-0">
        
        <!-- Left: X-Axis Mode Switcher (only shown for moving vehicles with varying chainage) -->
        <div v-if="hasVaryingKilometerData && !isRadialDistanceProfile" class="flex items-center gap-1.5">
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">X-Axis:</span>
          <div class="flex items-center p-0.5 rounded-md border bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-white/5 text-[10px] font-semibold">
            <button @click="xAxisMode = 'timestamp'"
                    class="flex items-center gap-1 px-2 py-0.5 rounded transition-all cursor-pointer"
                    :class="xAxisMode === 'timestamp'
                      ? 'bg-white dark:bg-slate-700 text-[#00305E] dark:text-sky-400 shadow-sm'
                      : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
              <Clock :size="11" />
              <span>Time</span>
            </button>

            <button @click="xAxisMode = 'kilometer'"
                    class="flex items-center gap-1 px-2 py-0.5 rounded transition-all cursor-pointer"
                    :class="xAxisMode === 'kilometer'
                      ? 'bg-white dark:bg-slate-700 text-[#00305E] dark:text-sky-400 shadow-sm'
                      : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'"
                    title="Plot against highway chainage in km">
              <Navigation :size="11" />
              <span>Kilometer</span>
            </button>
          </div>
        </div>

        <!-- Right: Y-Axis Temperature / Metric Selector -->
        <div class="flex items-center gap-1.5 ml-auto">
          <span v-if="store.selectedData?.stats_synthetic"
                class="px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                title="Analytical baseline profile synthesized from current boundary conditions">
            Synthetic Profile
          </span>
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Metric:</span>
          <select v-model="currentYAxis"
                  class="text-[11px] font-semibold border rounded-md shadow-sm px-2.5 py-1 outline-none transition-colors cursor-pointer"
                  :class="store.theme === 'dark' ? 'bg-slate-800 border-white/10 text-slate-200 focus:border-sky-400' : 'bg-white border-slate-200 text-slate-700 focus:border-[#00305E]'">
            <option v-for="opt in availableMetrics" :key="opt.id" :value="opt.id">
              {{ opt.label }} {{ opt.unit ? `[${opt.unit}]` : '' }}
            </option>
          </select>
        </div>

      </div>

      <!-- Chart Rendering Area -->
      <div class="flex-1 min-h-[280px] md:min-h-[340px] xl:min-h-[380px] 2k:min-h-[480px] 4k:min-h-[580px] relative border rounded-lg p-3 pb-3 transition-colors"
           :class="store.theme === 'dark' ? 'border-white/5 bg-slate-950/40' : 'border-slate-100 bg-slate-50/40'">
        <Line :data="chartData" :options="chartOptions" class="w-full h-full" />
      </div>

    </div>
  </div>
</template>
