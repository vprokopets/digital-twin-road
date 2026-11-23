<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { Line } from 'vue-chartjs'
import { useDashboardStore } from '../../stores/dashboard'
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
const hasData = computed(() => !!store.predictionPlotData && store.predictionPlotData.traces?.length > 0)

const refreshPrediction = () => {
  const feat = store.selectedFeature
  const isRoad = store.selectedType === 'SingleRoadPointStateDS' || store.selectedType === 'SingleRoadSegmentStateDS'
  if (isRoad && feat) {
    const health = feat.properties?.state ?? feat.properties?.State ?? 85
    store.fetchPredictionPlot(health)
  } else if (!store.predictionPlotData) {
    store.fetchPredictionPlot(85)
  }
}

onMounted(() => {
  refreshPrediction()
})

watch(() => store.selectedFeature, () => {
  refreshPrediction()
})

const chartData = computed(() => {
    if (!store.predictionPlotData) return { labels: [], datasets: [] }
    
    const isDark = store.theme === 'dark'
    
    return {
        labels: store.predictionPlotData.x.map((v: number) => v.toFixed(2)),
        datasets: store.predictionPlotData.traces.map((trace: any) => ({
            label: trace.name,
            borderColor: isDark && trace.color === '#000000' ? '#ffffff' : trace.color,
            data: trace.y,
            borderDash: trace.dash || [],
            tension: 0.2,
            pointRadius: 0,
            borderWidth: 2,
            fill: false
        }))
    }
})

const chartOptions = computed(() => {
    const isDark = store.theme === 'dark'
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: true,
                position: 'top' as const,
                labels: {
                    color: isDark ? '#94a3b8' : '#64748b',
                    boxWidth: 16,
                    padding: 10,
                    font: { size: 11, weight: 'bold' as const }
                }
            },
            tooltip: {
                mode: 'index' as const,
                intersect: false,
            }
        },
        scales: {
            x: {
                title: {
                    display: true,
                    text: 'Position along cross section [m]',
                    color: isDark ? '#94a3b8' : '#64748b',
                    font: { size: 10, weight: 'bold' as const }
                },
                grid: { color: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)' },
                ticks: { color: isDark ? '#94a3b8' : '#64748b', font: { size: 10 } }
            },
            y: {
                title: {
                    display: true,
                    text: 'Vertical displacement [m]',
                    color: isDark ? '#94a3b8' : '#64748b',
                    font: { size: 10, weight: 'bold' as const }
                },
                grid: { color: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)' },
                ticks: { color: isDark ? '#94a3b8' : '#64748b', font: { size: 10 } }
            }
        }
    }
})

</script>

<template>
  <div class="w-full min-h-[380px] flex flex-col relative p-4 transition-colors rounded-lg border" 
       :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
    
    <div v-if="!hasData" class="flex-1 min-h-[300px] flex items-center justify-center border-2 border-dashed rounded-lg w-full"
         :class="store.theme === 'dark' ? 'border-white/5 bg-slate-800/50' : 'border-slate-100 bg-slate-50/50'">
        <div class="text-center px-4 py-8">
            <p class="text-sm font-semibold mb-1" :class="store.theme === 'dark' ? 'text-slate-300' : 'text-slate-700'">
                Long-term Prediction Model
            </p>
            <p class="text-xs" :class="store.theme === 'dark' ? 'text-slate-500' : 'text-slate-400'">
                Select a road segment or point to view the health &amp; displacement forecast.
            </p>
        </div>
    </div>
    
    <div v-else class="flex-1 flex flex-col min-h-0 relative w-full">
        <div class="flex items-center justify-between mb-3">
            <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Forecast Horizon: 3 – 15 Years
            </span>
            <div class="flex items-center gap-2">
                <div class="px-2 py-0.5 rounded-md text-[10px] font-bold border" 
                     :class="store.predictionPlotData.state > 80 ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25' : store.predictionPlotData.state > 50 ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25'">
                    Current Health: {{ store.predictionPlotData.state }}%
                </div>
            </div>
        </div>
        <div class="h-[320px] w-full min-h-0">
            <Line :data="chartData" :options="chartOptions" />
        </div>
    </div>
  </div>
</template>
