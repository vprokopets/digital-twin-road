<script setup lang="ts">
import { ref, watch, nextTick, computed, onMounted, onUnmounted } from 'vue'
import { VueFlow, useVueFlow, Position, Handle } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import {
  Copy,
  Check,
  FileCode,
  Maximize2,
  Minimize2,
  RotateCcw,
  GitBranch,
  Workflow
} from 'lucide-vue-next'
import { useDashboardStore } from '../../stores/dashboard'
import dagre from 'dagre'
import Prism from '../../utils/prism'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

const store = useDashboardStore()
const treeProps = withDefaults(defineProps<{
    drawerWidth?: number
}>(), {
    drawerWidth: 480
})
const isVerticalLayout = computed(() => (treeProps.drawerWidth ?? 480) < 680)
const elements = ref<any[]>([])
const hasData = ref(false)

// Switchable Graph Mode: 'hpn' (Heraklit Hybrid Petri Net) | 'foda' (FODA Feature Tree)
const activeGraphMode = ref<'hpn' | 'foda'>('hpn')

// Active Code View State
const copied = ref(false)
const isExpanded = ref(false)

const sourceLanguage = computed(() =>
    String(store.selectedData?.source_language || 'python').toLowerCase()
)

const activeContexts = computed<string[]>(() =>
    Array.isArray(store.selectedData?.active_contexts) ? store.selectedData.active_contexts : []
)

const codeBadgeLabel = computed(() =>
    sourceLanguage.value === 'julia'
        ? 'External Julia Solver (Multiple Dispatch)'
        : 'Synthesized Python Mixin Class (Heraklit HPN Algebra)'
)

const highlightedCode = computed(() => {
    const rawCode = store.selectedData?.code
    if (!rawCode) return ''
    const grammar = (Prism.languages as Record<string, any>)[sourceLanguage.value] || Prism.languages.python
    return Prism.highlight(rawCode, grammar, sourceLanguage.value in Prism.languages ? sourceLanguage.value : 'python')
})

const copyCurrentCode = async () => {
    const textToCopy = store.selectedData?.code || ''
    if (textToCopy && navigator.clipboard) {
        try {
            await navigator.clipboard.writeText(textToCopy)
            copied.value = true
            setTimeout(() => {
                copied.value = false
            }, 2000)
        } catch (e) {
            console.error('Clipboard copy failed:', e)
        }
    }
}

const { fitView } = useVueFlow()

const resetZoom = () => {
    nextTick(() => {
        fitView({ padding: 0.18 })
    })
}

const hpnMeta = computed(() => store.selectedData?.hpn_graph || null)

// Dagre Layout (Top-to-Bottom in narrow drawers, Left-to-Right when expanded)
const layoutElements = (nodes: any[], edges: any[], isHpn = false) => {
  const vertical = isVerticalLayout.value
  const g = new dagre.graphlib.Graph()
  g.setGraph({
    rankdir: vertical ? 'TB' : 'LR',
    ranksep: isHpn ? (vertical ? 42 : 80) : 45,
    nodesep: isHpn ? (vertical ? 20 : 30) : 18
  })
  g.setDefaultEdgeLabel(() => ({}))

  nodes.forEach((node) => {
    const w = node.data?.width || 140
    const h = node.data?.height || 36
    g.setNode(node.id, { width: w, height: h })
  })

  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target)
  })

  dagre.layout(g)

  return [
    ...nodes.map((node) => {
      const w = node.data?.width || 140
      const h = node.data?.height || 36
      const nodeWithPosition = g.node(node.id)
      return {
        ...node,
        targetPosition: vertical ? Position.Top : Position.Left,
        sourcePosition: vertical ? Position.Bottom : Position.Right,
        position: {
          x: nodeWithPosition.x - w / 2,
          y: nodeWithPosition.y - h / 2,
        },
      }
    }),
    ...edges,
  ]
}

const lastSelectedId = ref<string | null>(null)
const graphContainerRef = ref<HTMLElement | null>(null)

/**
 * Converts Heraklit Hybrid Petri Net JSON (`store.selectedData.hpn_graph`)
 * into styled Vue Flow nodes (Places Pd/Pc, Transitions Td/Tc) and Arcs.
 */
const parseHpnToNodes = (hpn: any) => {
  if (!hpn || !Array.isArray(hpn.nodes)) return { nodes: [], edges: [] }
  const isDark = store.theme === 'dark'

  const nodes = hpn.nodes.map((n: any) => {
    const isPlace = n.node_type === 'place'
    const isCont = n.kind === 'continuous'
    const isFused = n.gate === 'fused'
    const isEnabled = !!n.enabled || (isPlace && n.tokens > 0)

    let bg = isDark ? '#1e293b' : '#ffffff'
    let border = isDark ? '#475569' : '#cbd5e1'
    let text = isDark ? '#f1f5f9' : '#1e293b'
    let boxShadow = 'none'
    let borderRadius = '8px'
    let borderStyle = 'solid'
    let borderWidth = '1.5px'
    let width = isPlace ? (isCont ? 175 : 165) : 160
    let height = 48
    let badgeClass = isDark
      ? 'bg-slate-700/40 text-slate-300 border border-slate-600/40'
      : 'bg-slate-100 text-slate-600 border border-slate-300'

    if (isPlace) {
      borderRadius = isCont ? '14px' : '9999px'
      if (isFused) {
        // Shared Heraklit Interface Gate (beta(M1) ∩ alpha(M2))
        bg = isDark ? '#083344' : '#ecfeff'
        border = '#06b6d4'
        text = isDark ? '#67e8f9' : '#0e7490'
        borderWidth = '2px'
        boxShadow = '0 0 10px rgba(6, 182, 212, 0.35)'
        badgeClass = isDark
          ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/40'
          : 'bg-cyan-100/80 text-cyan-800 border border-cyan-400/50'
      } else if (isCont) {
        // Continuous fluid place Pc
        bg = isDark ? '#1e1b4b' : '#eef2ff'
        border = '#6366f1'
        text = isDark ? '#c7d2fe' : '#3730a3'
        borderStyle = 'double'
        borderWidth = '3px'
        badgeClass = isDark
          ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-400/40'
          : 'bg-indigo-100/80 text-indigo-800 border border-indigo-400/50'
      } else if (n.tokens > 0) {
        // Marked discrete place Pd
        bg = '#10b981'
        border = '#059669'
        text = '#ffffff'
        boxShadow = '0 2px 8px rgba(16, 185, 129, 0.4)'
        badgeClass = 'bg-emerald-800/60 text-white border border-emerald-300/40'
      }
    } else {
      // Transition Td or Tc
      borderRadius = '6px'
      if (isCont) {
        bg = isDark ? '#3b0764' : '#faf5ff'
        border = '#a855f7'
        text = isDark ? '#e9d5ff' : '#6b21a8'
        borderStyle = 'double'
        borderWidth = '3px'
        badgeClass = isDark
          ? 'bg-purple-500/20 text-purple-300 border border-purple-400/40'
          : 'bg-purple-100/80 text-purple-800 border border-purple-400/50'
      } else if (isEnabled) {
        bg = isDark ? '#064e3b' : '#d1fae5'
        border = '#10b981'
        text = isDark ? '#6ee7b7' : '#065f46'
        borderWidth = '2px'
        badgeClass = isDark
          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/40'
          : 'bg-emerald-100 text-emerald-800 border border-emerald-400/50'
      } else {
        bg = isDark ? '#0f172a' : '#f8fafc'
        border = isDark ? '#334155' : '#94a3b8'
        text = isDark ? '#94a3b8' : '#64748b'
        badgeClass = isDark
          ? 'bg-slate-700/30 text-slate-400 border border-slate-600/30'
          : 'bg-slate-100 text-slate-600 border border-slate-300'
      }
    }

    // Format badge text
    let badgeText = ''
    if (isPlace) {
      if (isCont) {
        badgeText = `${Number(n.tokens).toFixed(n.unit === 'mm' ? 4 : 2)}${n.unit ? ' ' + n.unit : ''}`
      } else {
        badgeText = `● ${Math.round(n.tokens)} tok`
      }
    } else {
      badgeText = isCont ? `Tc • r=${n.rate}` : (n.fired ? 'Td • FIRED' : 'Td • Guard')
    }

    const gatePrefix = isFused ? '⊕ ' : n.gate === 'alpha' ? 'α: ' : n.gate === 'beta' ? 'β: ' : ''

    return {
      id: n.id,
      label: `${gatePrefix}${n.label}`,
      type: 'hpn',
      data: {
        width,
        height,
        raw: n,
        gatePrefix,
        cleanLabel: n.label,
        badgeText,
        badgeClass
      },
      style: {
        backgroundColor: bg,
        color: text,
        fontSize: '10px',
        fontWeight: isEnabled || isFused ? '700' : '600',
        padding: '2px 4px',
        borderRadius,
        border: `${borderWidth} ${borderStyle} ${border}`,
        width: `${width}px`,
        height: `${height}px`,
        boxShadow,
      }
    }
  })

  const edges = (hpn.edges || []).map((e: any) => {
    const isTest = e.arc_type === 'test'
    const isInhibitor = e.arc_type === 'inhibitor'
    const isReset = e.arc_type === 'reset'

    let stroke = isDark ? '#64748b' : '#94a3b8'
    if (isTest) stroke = '#06b6d4'
    else if (isInhibitor) stroke = '#ef4444'
    else if (isReset) stroke = '#f59e0b'
    else if (e.animated) stroke = '#10b981'

    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: 'smoothstep',
      pathOptions: { borderRadius: 8 },
      animated: !!e.animated,
      label: isTest ? 'read' : isInhibitor ? 'inhib' : isReset ? 'reset' : '',
      labelStyle: { fontSize: '8px', fill: stroke, fontWeight: 700 },
      style: {
        stroke,
        strokeWidth: e.animated ? 2 : 1.3,
        strokeDasharray: isTest ? '4 3' : isInhibitor ? '2 2' : undefined,
      }
    }
  })

  return { nodes, edges }
}

/**
 * Converts FODA feature dictionary (`store.selectedData.metadata`) into Vue Flow nodes.
 */
const parseDictToNodes = (obj: any) => {
  let nodes: any[] = []
  let edges: any[] = []
  let currentIdCounter = 0

  const traverse = (data: any, parent: string | null = null, keyName: string = 'Root') => {
    if (keyName === 'features' && typeof data === 'object' && data !== null) {
        Object.keys(data).forEach((key) => {
            traverse(data[key], parent, key)
        })
        return
    }

    const nodeId = `node_${currentIdCounter++}`
    let label = keyName
    let isActive = false

    if (typeof data === 'object' && data !== null) {
        if (data.name) label = String(data.name)
        else if (data.Name) label = String(data.Name)
        if ('active' in data) isActive = data.active === true || data.active === 'true'
    } else if (typeof data === 'boolean') {
        isActive = data === true
        label = `${keyName}: ${data}`
    }

    const isDark = store.theme === 'dark'
    let bg = isActive ? '#10b981' : (isDark ? '#1e293b' : '#f1f5f9')
    let text = isActive ? '#ffffff' : (isDark ? '#cbd5e1' : '#475569')
    let border = isActive ? '#059669' : (isDark ? '#334155' : '#cbd5e1')

    nodes.push({
      id: nodeId,
      label: label,
      type: 'default',
      data: { width: 140, height: 34 },
      targetPosition: Position.Left,
      sourcePosition: Position.Right,
      style: { 
        backgroundColor: bg, 
        color: text,
        fontSize: '11px', 
        fontWeight: isActive ? '600' : '500',
        whiteSpace: 'nowrap', 
        overflow: 'hidden', 
        textOverflow: 'ellipsis', 
        padding: '6px 10px', 
        borderRadius: '6px', 
        border: `1px solid ${border}`,
        width: '140px',
        textAlign: 'center',
        boxShadow: isActive ? '0 1px 4px rgba(16, 185, 129, 0.3)' : 'none'
      }
    })

    if (parent) {
      edges.push({
        id: `edge_${parent}_${nodeId}`,
        source: parent,
        target: nodeId,
        animated: isActive,
        style: {
          stroke: isActive ? '#10b981' : (isDark ? '#475569' : '#94a3b8'),
          strokeWidth: isActive ? 2 : 1
        }
      })
    }

    if (typeof data === 'object' && data !== null) {
        Object.keys(data).forEach((key) => {
            if (['active', 'name', 'id', 'ID', 'cardinality'].includes(key)) return
            const val = data[key]
            if (typeof val === 'object' || typeof val === 'boolean') {
                traverse(val, nodeId, key)
            }
        })
    }
  }

  traverse(obj)
  return { nodes, edges }
}

const rebuildGraph = (forceFit = false) => {
    const newData = store.selectedData
    if (!newData) {
        hasData.value = false
        return
    }

    if (activeGraphMode.value === 'hpn' && newData.hpn_graph?.nodes?.length) {
        const { nodes, edges } = parseHpnToNodes(newData.hpn_graph)
        elements.value = layoutElements(nodes, edges, true)
        hasData.value = true
    } else if (newData.metadata) {
        const { nodes, edges } = parseDictToNodes(newData.metadata)
        elements.value = layoutElements(nodes, edges, false)
        hasData.value = nodes.length > 0
    } else {
        hasData.value = false
    }

    const currentId = `${store.selectedFeature?.properties?.id || store.selectedFeature?.properties?.ID}_${activeGraphMode.value}`
    if (forceFit || currentId !== lastSelectedId.value) {
        nextTick(() => {
            setTimeout(() => fitView({ padding: 0.18, duration: 250 }), 100)
        })
        lastSelectedId.value = currentId
    }
}

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
    if (typeof ResizeObserver !== 'undefined' && graphContainerRef.value) {
        resizeObserver = new ResizeObserver(() => {
            if (hasData.value) {
                fitView({ padding: 0.18, duration: 200 })
            }
        })
        resizeObserver.observe(graphContainerRef.value)
    }
})

onUnmounted(() => {
    if (resizeObserver) {
        resizeObserver.disconnect()
        resizeObserver = null
    }
})

watch(() => store.selectedData, () => {
    rebuildGraph(false)
}, { immediate: true })

watch(() => activeGraphMode.value, () => {
    rebuildGraph(true)
})

watch(() => store.theme, () => {
    rebuildGraph(false)
})

watch(isVerticalLayout, () => {
    rebuildGraph(true)
})
</script>

<template>
  <div class="h-full w-full flex flex-col gap-3.5">
    
    <!-- Top Switcher: Heraklit HPN Algebra vs FODA Feature Tree -->
    <div class="p-2.5 rounded-lg border flex flex-col gap-2"
         :class="store.theme === 'dark' ? 'bg-slate-900/90 border-white/10' : 'bg-white border-slate-200'">
      
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <div class="flex items-center p-0.5 rounded-md border bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-white/5 text-[11px] font-semibold">
          <button @click="activeGraphMode = 'hpn'"
                  class="flex items-center gap-1.5 px-2.5 py-1 rounded transition-all cursor-pointer"
                  :class="activeGraphMode === 'hpn'
                    ? 'bg-[#00305E] text-white shadow-xs'
                    : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
            <Workflow :size="12" />
            <span>Heraklit HPN (●)</span>
          </button>
          <button @click="activeGraphMode = 'foda'"
                  class="flex items-center gap-1.5 px-2.5 py-1 rounded transition-all cursor-pointer"
                  :class="activeGraphMode === 'foda'
                    ? 'bg-[#00305E] text-white shadow-xs'
                    : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
            <GitBranch :size="12" />
            <span>FODA Feature Tree</span>
          </button>
        </div>

        <button v-if="hasData"
                @click="resetZoom"
                class="flex items-center gap-1 px-2.5 py-1 rounded-md text-[10.5px] font-semibold border transition-colors cursor-pointer"
                :class="store.theme === 'dark' ? 'bg-slate-800 border-white/10 text-slate-300 hover:bg-slate-700' : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100'"
                title="Reset & Center View">
          <RotateCcw :size="11" />
          <span>Fit Graph</span>
        </button>
      </div>

      <!-- Heraklit Composition Equation Banner (when HPN mode is active) -->
      <div v-if="activeGraphMode === 'hpn' && hpnMeta"
           class="px-2.5 py-1.5 rounded-md border text-[10px] font-mono flex flex-col gap-1"
           :class="store.theme === 'dark' ? 'bg-slate-950/70 border-white/10 text-slate-200' : 'bg-slate-50 border-slate-200 text-slate-800'">
        <div class="flex items-center justify-between gap-2">
          <span class="font-bold uppercase tracking-wider text-[9px] text-[#00305E] dark:text-sky-400">Reisig HERAKLIT Composition</span>
          <span class="px-1.5 py-0.2 rounded bg-slate-200/70 dark:bg-white/10 text-slate-700 dark:text-slate-300 font-bold text-[9px]">
            Solver: {{ hpnMeta.active_solver || 'POD' }}
          </span>
        </div>
        <div class="truncate font-semibold" :title="hpnMeta.algebraic_expression">
          M_Fed = M_RSU_Env ● M_Mat_Thermal ● M_Vehicle_Solver
        </div>
        <div class="flex items-center gap-2 text-[9px] text-slate-500 dark:text-slate-400 flex-wrap">
          <span><b class="text-emerald-600 dark:text-emerald-500">● Pd</b> Discrete Tok</span>
          <span>•</span>
          <span><b class="text-indigo-600 dark:text-indigo-400">◎ Pc</b> Continuous Fluid</span>
          <span>•</span>
          <span><b class="text-cyan-700 dark:text-cyan-400">⊕ β∩α</b> Fused Gate</span>
        </div>
      </div>
    </div>

    <!-- Interactive Graph Canvas (Adaptive TB/LR Layout) -->
    <div ref="graphContainerRef"
         :class="[store.theme === 'dark' ? 'border-white/10 bg-slate-900 shadow-slate-950/50' : 'border-slate-200 bg-slate-50', isVerticalLayout ? 'h-[440px]' : 'h-[360px]', 'rounded-lg border overflow-hidden relative shadow-inner w-full transition-all duration-300']">
      <div v-if="!hasData" class="absolute inset-0 flex items-center justify-center z-10 m-2 border-2 border-dashed rounded-lg"
           :class="store.theme === 'dark' ? 'border-white/5 bg-slate-800/50' : 'border-slate-200 bg-white/50'">
        <p class="text-xs text-center px-6" :class="store.theme === 'dark' ? 'text-slate-500' : 'text-slate-400'">
          Select a vehicle on the map to visualize its Heraklit Hybrid Petri Net &amp; FODA feature graph.
        </p>
      </div>
      <div v-else class="w-full h-full relative"> 
        <VueFlow v-model="elements" :default-zoom="0.85" :min-zoom="0.18" :max-zoom="3" fit-view-on-init>
          <Background :pattern-color="store.theme === 'dark' ? '#334155' : '#cbd5e1'" :gap="16" />
          <Controls />

          <!-- Custom Render for Heraklit HPN Nodes: Clean 2-Row Layout With Gate & Badge -->
          <template #node-hpn="props">
            <div class="h-full w-full flex flex-col items-center justify-center px-2 py-0.5 select-none text-center relative overflow-hidden">
              <Handle type="target" :position="isVerticalLayout ? Position.Top : Position.Left" class="!bg-transparent !border-0 !w-1 !h-1" />

              <div class="w-full flex items-center justify-center gap-1 font-bold text-[10.5px] truncate leading-tight">
                <span v-if="props.data.gatePrefix" class="font-extrabold shrink-0" :class="props.data.raw?.tokens > 0 && props.data.raw?.node_type === 'place' ? 'text-white' : 'text-cyan-700 dark:text-cyan-400'">{{ props.data.gatePrefix }}</span>
                <span class="truncate">{{ props.data.cleanLabel }}</span>
              </div>

              <div class="mt-1 px-1.5 py-0.5 rounded-full text-[9px] font-mono font-bold leading-none shrink-0"
                   :class="props.data.badgeClass">
                {{ props.data.badgeText }}
              </div>

              <Handle type="source" :position="isVerticalLayout ? Position.Bottom : Position.Right" class="!bg-transparent !border-0 !w-1 !h-1" />
            </div>
          </template>
        </VueFlow>
      </div>
    </div>

    <!-- Heraklit Module Interface Gates Summary (only in HPN mode) -->
    <div v-if="activeGraphMode === 'hpn' && hpnMeta?.modules?.length"
         class="grid grid-cols-3 gap-1.5 text-[10px]">
      <div v-for="mod in hpnMeta.modules" :key="mod.name"
           class="p-2 rounded-md border flex flex-col justify-between"
           :class="store.theme === 'dark' ? 'bg-slate-900/70 border-white/10' : 'bg-slate-50 border-slate-200/80'">
        <div class="font-bold text-[#00305E] dark:text-sky-400 truncate" :title="mod.label">{{ mod.name }}</div>
        <div class="text-[9px] text-slate-400 mt-1 truncate">
          α: {{ mod.alpha_gates?.length || 0 }} in • β: {{ mod.beta_gates?.length || 0 }} out
        </div>
      </div>
    </div>

    <!-- Code Snippets Area: Full Width Segmented Viewer -->
    <div v-if="store.selectedData?.code"
         class="rounded-lg border overflow-hidden shadow-sm transition-all"
         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10' : 'bg-white border-slate-200'">
        
        <!-- Header: Code Header Badge & Actions -->
        <div class="p-2.5 border-b flex flex-wrap items-center justify-between gap-2"
             :class="store.theme === 'dark' ? 'border-white/5 bg-slate-950/40' : 'border-slate-100 bg-slate-50/50'">
            
            <!-- Python / HPN or External Solver Code Header Badge -->
            <div class="flex items-center gap-1.5 px-2.5 py-1 rounded border text-[11px] font-semibold bg-[#00305E]/10 text-[#00305E] dark:bg-sky-500/15 dark:text-sky-300 border-[#00305E]/20 dark:border-sky-400/30">
                <FileCode :size="13" />
                <span>{{ codeBadgeLabel }}</span>
            </div>

            <!-- Header Toolbar Actions -->
            <div class="flex items-center gap-1.5">
                <button @click="copyCurrentCode"
                        class="flex items-center gap-1 px-2 py-1 rounded-md border text-[11px] font-medium transition-all cursor-pointer shadow-sm"
                        :class="copied
                          ? 'bg-emerald-500 text-white border-emerald-600'
                          : store.theme === 'dark'
                            ? 'bg-slate-800 border-white/10 text-slate-300 hover:bg-slate-700 hover:text-white'
                            : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'"
                        :title="copied ? 'Copied to clipboard!' : 'Copy snippet'">
                    <Check v-if="copied" :size="12" class="text-white" />
                    <Copy v-else :size="12" />
                    <span>{{ copied ? 'Copied' : 'Copy' }}</span>
                </button>

                <button @click="isExpanded = !isExpanded"
                        class="p-1 rounded-md border text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors cursor-pointer"
                        :class="store.theme === 'dark' ? 'bg-slate-800 border-white/10' : 'bg-white border-slate-200'"
                        :title="isExpanded ? 'Collapse Height' : 'Expand Height'">
                    <Minimize2 v-if="isExpanded" :size="13" />
                    <Maximize2 v-else :size="13" />
                </button>
            </div>
        </div>

        <!-- Code Content Area -->
        <div class="code-wrapper p-3" :class="store.theme">
            <div>
                <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <span class="text-[10px] uppercase font-bold text-slate-400">
                      {{ sourceLanguage === 'julia' ? 'External Solver Active Contexts + Multiple Dispatch' : 'Mosaic Mixin Class + Heraklit HPN Algebra' }}
                    </span>
                    <div v-if="activeContexts.length" class="flex flex-wrap items-center gap-1">
                      <span v-for="ctx in activeContexts" :key="ctx"
                            class="px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-600 dark:text-cyan-300 border border-cyan-500/20 font-mono text-[10px] font-semibold">
                        {{ ctx }}
                      </span>
                    </div>
                </div>
                <pre class="text-[11px] font-mono overflow-auto rounded-lg p-3 leading-relaxed shadow-inner border transition-all duration-200"
                     :class="[
                       store.theme === 'dark' ? 'bg-slate-950/80 border-white/5 text-slate-200' : 'bg-slate-50 border-slate-200 text-slate-800',
                       isExpanded ? 'max-h-[650px]' : 'max-h-[340px]'
                     ]"><code v-html="highlightedCode"></code></pre>
            </div>
        </div>
    </div>
  </div>
</template>

<style scoped>
.code-wrapper.light :deep(pre) {
    background: transparent !important;
    text-shadow: none !important;
}

.code-wrapper.light :deep(.token.comment),
.code-wrapper.light :deep(.token.prolog),
.code-wrapper.light :deep(.token.doctype),
.code-wrapper.light :deep(.token.cdata) {
    color: #94a3b8;
}

.code-wrapper.light :deep(.token.punctuation) {
    color: #475569;
}

.code-wrapper.light :deep(.token.property),
.code-wrapper.light :deep(.token.tag),
.code-wrapper.light :deep(.token.boolean),
.code-wrapper.light :deep(.token.number),
.code-wrapper.light :deep(.token.constant),
.code-wrapper.light :deep(.token.symbol),
.code-wrapper.light :deep(.token.deleted) {
    color: #2563eb;
}

.code-wrapper.light :deep(.token.selector),
.code-wrapper.light :deep(.token.attr-name),
.code-wrapper.light :deep(.token.string),
.code-wrapper.light :deep(.token.char),
.code-wrapper.light :deep(.token.builtin),
.code-wrapper.light :deep(.token.inserted) {
    color: #059669;
}

.code-wrapper.light :deep(.token.operator),
.code-wrapper.light :deep(.token.entity),
.code-wrapper.light :deep(.token.url),
.code-wrapper.light :deep(.language-css .token.string),
.code-wrapper.light :deep(.style .token.string) {
    color: #9333ea;
}

.code-wrapper.light :deep(.token.atrule),
.code-wrapper.light :deep(.token.attr-value),
.code-wrapper.light :deep(.token.keyword) {
    color: #0369a1;
}

.code-wrapper.light :deep(.token.function),
.code-wrapper.light :deep(.token.class-name) {
    color: #ea580c;
}

.code-wrapper.light :deep(.token.regex),
.code-wrapper.light :deep(.token.important),
.code-wrapper.light :deep(.token.variable) {
    color: #eab308;
}

.code-wrapper.light :deep(code) {
    color: #1e293b;
}

.code-wrapper.dark :deep(pre) {
    background: transparent !important;
}
</style>
