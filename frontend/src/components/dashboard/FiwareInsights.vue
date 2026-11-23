<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref, watch } from 'vue'
import {
    Database,
    RefreshCcw,
    ExternalLink,
    Search,
    SortAsc,
    SortDesc,
    Activity,
    Trash2,
    Truck,
    Radio,
    Box,
    Copy,
    Check,
    Link2,
    ChevronDown,
    History,
    X,
    ChevronLeft,
    ChevronRight,
} from 'lucide-vue-next'
import { useDashboardStore } from '../../stores/dashboard'
import apiClient from '../../api/client'

type FilterOp = '=' | '!=' | '>' | '>=' | '<' | '<=' | '~'
type FilterTerm =
    | { kind: 'predicate'; field: string; op: FilterOp; value: string }
    | { kind: 'text'; value: string }

interface NormalizedEntity {
    id: string
    type: string
    _isActive: boolean
    _raw: any
    _fieldMap: Record<string, any>
    _propPairs: Array<[string, string]>
    _searchBlob: string
    TimeInstant?: any
    updated_at?: any
}

const store = useDashboardStore()
const isFiwareActive = computed(() => store.fiwareConnected)
const isNativeActive = computed(() => !store.fiwareConnected)
const apiBase = apiClient.defaults.baseURL ?? ''
const rawEntitiesUrl = `${apiBase}/dashboard/fiware_entities`
let pollInterval: any = null

const searchQuery = ref('')
const selectedTypeFilter = ref<string>('ALL')
const sortKey = ref('TimeInstant')
const sortOrder = ref<'asc' | 'desc'>('desc')
const filterActiveOnly = ref(false)
const pageSize = ref<25 | 50 | 'all'>(25)
const currentPage = ref<number>(1)
const isCleaning = ref(false)
const copiedKey = ref<string | null>(null)

const refreshBroker = async () => {
    await Promise.all([store.checkFiwareStatus(), store.fetchFiwareEntities()])
}

const copyText = async (key: string, text?: string) => {
    if (!text) return
    try {
        if (typeof navigator !== 'undefined' && navigator.clipboard) {
            await navigator.clipboard.writeText(text)
        }
        copiedKey.value = key
        setTimeout(() => {
            if (copiedKey.value === key) copiedKey.value = null
        }, 1500)
    } catch {
        // Ignore clipboard errors in headless/restricted contexts
    }
}

const resolveBackendUrl = (path: string) => `${apiBase}${path}`

const getEntityRawUrl = (entityId: string) => `${rawEntitiesUrl}/${encodeURIComponent(entityId)}`

const getEntityHistoryUrl = (entityId: string) => `${rawEntitiesUrl}/${encodeURIComponent(entityId)}/history`

const unwrapPropValue = (val: any): any => {
    let current = val
    let depth = 0
    while (
        current !== null &&
        typeof current === 'object' &&
        !Array.isArray(current) &&
        'value' in current &&
        depth < 4
    ) {
        current = current.value
        depth++
    }
    return current
}

const formatPropValue = (key: string, val: any): string => {
    const unwrapped = unwrapPropValue(val)
    if (key.toLowerCase() === 'coordinates' && Array.isArray(unwrapped) && unwrapped.length >= 2) {
        return `${Number(unwrapped[0]).toFixed(4)}, ${Number(unwrapped[1]).toFixed(4)}`
    }
    if (typeof unwrapped === 'number') {
        return Number.isInteger(unwrapped) ? String(unwrapped) : unwrapped.toFixed(2)
    }
    if (typeof unwrapped === 'object' && unwrapped !== null) {
        return JSON.stringify(unwrapped)
    }
    return String(unwrapped)
}

const IGNORED_META_KEYS = new Set([
    'id',
    'type',
    'entity_type',
    'device_id',
    'entity_name',
    'created_at',
    'updated_at',
    'TimeInstant',
    'telemetry',
    'static_attributes',
    '_isActive',
])

const formatEntityProperties = (entity: any): Array<[string, string]> => {
    const pairs: Array<[string, string]> = []
    const seen = new Set<string>()
    const addProp = (key: string, val: any) => {
        if (val === undefined || val === null || seen.has(key)) return
        seen.add(key)
        pairs.push([key, formatPropValue(key, val)])
    }
    if (entity?.telemetry && typeof entity.telemetry === 'object') {
        for (const [k, v] of Object.entries(entity.telemetry)) {
            addProp(k, v)
        }
    }
    if (entity?.static_attributes && typeof entity.static_attributes === 'object' && !Array.isArray(entity.static_attributes)) {
        for (const [k, v] of Object.entries(entity.static_attributes)) {
            if (k !== 'ID') {
                addProp(k, v)
            }
        }
    }
    for (const [k, v] of Object.entries(entity || {})) {
        if (IGNORED_META_KEYS.has(k) || k.startsWith('_')) continue
        addProp(k, v)
    }
    return pairs
}

const buildEntityFieldMap = (
    entity: any,
    entityId: string,
    entityType: string,
    isEntityActive: boolean
): Record<string, any> => {
    const fieldMap: Record<string, any> = {}
    const put = (key: string, val: any) => {
        if (val === undefined || val === null) return
        fieldMap[key.toLowerCase()] = unwrapPropValue(val)
    }

    if (entity?.static_attributes && typeof entity.static_attributes === 'object' && !Array.isArray(entity.static_attributes)) {
        for (const [k, v] of Object.entries(entity.static_attributes)) {
            if (k !== 'ID') put(k, v)
        }
    }

    for (const [k, v] of Object.entries(entity || {})) {
        if (IGNORED_META_KEYS.has(k) || k.startsWith('_')) continue
        put(k, v)
    }

    if (entity?.telemetry && typeof entity.telemetry === 'object') {
        for (const [k, v] of Object.entries(entity.telemetry)) {
            put(k, v)
        }
    }

    fieldMap['id'] = entityId
    fieldMap['type'] = entityType
    fieldMap['status'] = isEntityActive ? 'active' : 'idle'
    fieldMap['active'] = isEntityActive
    return fieldMap
}

const tokenizeFilterQuery = (raw: string): Array<{ type: 'word' | 'op'; value: string; quoted?: boolean }> => {
    const tokens: Array<{ type: 'word' | 'op'; value: string; quoted?: boolean }> = []
    let i = 0
    const n = raw.length
    while (i < n) {
        const ch = raw[i]
        if (/\s/.test(ch)) {
            i++
            continue
        }
        const two = raw.slice(i, i + 2)
        if (two === '>=' || two === '<=' || two === '!=') {
            tokens.push({ type: 'op', value: two })
            i += 2
            continue
        }
        if (ch === '=' || ch === '>' || ch === '<' || ch === '~') {
            tokens.push({ type: 'op', value: ch })
            i += 1
            continue
        }
        if (ch === '"' || ch === "'") {
            const quote = ch
            i++
            let val = ''
            while (i < n && raw[i] !== quote) {
                if (raw[i] === '\\' && i + 1 < n) {
                    i++
                }
                val += raw[i]
                i++
            }
            if (i < n && raw[i] === quote) i++
            if (val.length > 0) {
                tokens.push({ type: 'word', value: val, quoted: true })
            }
            continue
        }
        let val = ''
        while (i < n) {
            const c = raw[i]
            if (/\s/.test(c) || c === '=' || c === '>' || c === '<' || c === '~' || c === '"' || c === "'") {
                break
            }
            if (c === '!' && raw[i + 1] === '=') {
                break
            }
            val += c
            i++
        }
        if (val.length > 0) {
            tokens.push({ type: 'word', value: val, quoted: false })
        }
    }
    return tokens
}

const parseFilterQuery = (raw: string): FilterTerm[][] => {
    const trimmed = raw.trim()
    if (!trimmed) return []
    const tokens = tokenizeFilterQuery(trimmed)
    const clauses: FilterTerm[][] = []
    let currentClause: FilterTerm[] = []

    const isAndToken = (tok: { type: 'word' | 'op'; value: string; quoted?: boolean }) =>
        tok.type === 'word' && !tok.quoted && (tok.value.toUpperCase() === 'AND' || tok.value === '&&')
    const isOrToken = (tok: { type: 'word' | 'op'; value: string; quoted?: boolean }) =>
        tok.type === 'word' && !tok.quoted && (tok.value.toUpperCase() === 'OR' || tok.value === '||')

    let i = 0
    while (i < tokens.length) {
        const tok = tokens[i]
        if (tok.type === 'op') {
            i++
            continue
        }
        if (isOrToken(tok)) {
            if (currentClause.length > 0) {
                clauses.push(currentClause)
                currentClause = []
            }
            i++
            continue
        }
        if (isAndToken(tok)) {
            i++
            continue
        }
        const next = tokens[i + 1]
        const rhs = tokens[i + 2]
        if (next && next.type === 'op' && rhs && rhs.type === 'word') {
            currentClause.push({
                kind: 'predicate',
                field: tok.value,
                op: next.value as FilterOp,
                value: rhs.value,
            })
            i += 3
            continue
        }
        if (next && next.type === 'op' && !rhs) {
            // Incomplete predicate mid-typing (e.g. "Velocity>"): keep field as loose text match
            currentClause.push({ kind: 'text', value: tok.value })
            i += 2
            continue
        }
        currentClause.push({ kind: 'text', value: tok.value })
        i++
    }

    if (currentClause.length > 0) {
        clauses.push(currentClause)
    }
    return clauses
}

const toFiniteNumber = (v: any): number | null => {
    if (typeof v === 'number') return Number.isFinite(v) ? v : null
    if (typeof v === 'boolean') return null
    const s = String(v).trim()
    if (!s) return null
    const n = Number(s)
    return Number.isFinite(n) ? n : null
}

const matchesTerm = (entity: NormalizedEntity, term: FilterTerm): boolean => {
    if (term.kind === 'text') {
        const needle = term.value.toLowerCase()
        return (
            entity.id.toLowerCase().includes(needle) ||
            entity.type.toLowerCase().includes(needle) ||
            entity._searchBlob.includes(needle)
        )
    }

    const rawVal = entity._fieldMap[term.field.toLowerCase()]
    if (rawVal === undefined || rawVal === null) return false

    if (term.op === '~') {
        return String(rawVal).toLowerCase().includes(term.value.toLowerCase())
    }

    if (term.op === '>' || term.op === '>=' || term.op === '<' || term.op === '<=') {
        const left = toFiniteNumber(rawVal)
        const right = toFiniteNumber(term.value)
        if (left === null || right === null) return false
        if (term.op === '>') return left > right
        if (term.op === '>=') return left >= right
        if (term.op === '<') return left < right
        return left <= right
    }

    const leftNum = toFiniteNumber(rawVal)
    const rightNum = toFiniteNumber(term.value)
    const isEqual =
        leftNum !== null && rightNum !== null
            ? leftNum === rightNum
            : String(rawVal).toLowerCase() === term.value.toLowerCase()

    return term.op === '=' ? isEqual : !isEqual
}

const matchesEntityQuery = (entity: NormalizedEntity, clauses: FilterTerm[][]): boolean => {
    if (clauses.length === 0) return true
    return clauses.some((clause) => clause.every((term) => matchesTerm(entity, term)))
}

const cleanIdle = async () => {
    isCleaning.value = true
    try {
        await store.cleanIdleEntities()
    } finally {
        isCleaning.value = false
    }
}

onMounted(async () => {
    await Promise.all([store.checkFiwareStatus(), store.fetchFiwareEntities()])
    // Poll every 5 seconds for freshness
    pollInterval = setInterval(() => {
        store.checkFiwareStatus()
        store.fetchFiwareEntities()
    }, 5000)
})

onUnmounted(() => {
    if (pollInterval) clearInterval(pollInterval)
})

const getEntityTimestampMs = (entity: any): number => {
    const raw = entity?.TimeInstant ?? (entity?.updated_at ? entity.updated_at * 1000 : null)
    if (!raw) return 0
    const ms = new Date(raw).getTime()
    return Number.isNaN(ms) ? 0 : ms
}

const isActive = (entity: any) => {
    const lastUpdate = getEntityTimestampMs(entity)
    if (!lastUpdate) return false
    return Date.now() - lastUpdate < 60000 // 60 seconds
}

const toggleSort = (key: string) => {
    if (sortKey.value === key) {
        sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
    } else {
        sortKey.value = key
        sortOrder.value = 'desc'
    }
}

const normalizedEntities = computed<NormalizedEntity[]>(() => {
    return store.fiwareEntities.map((e) => {
        const id = String(e.id ?? e.device_id ?? '')
        const type = String(e.type ?? e.entity_type ?? 'Entity')
        const activeFlag = isActive(e)
        const propPairs = formatEntityProperties(e)
        const fieldMap = buildEntityFieldMap(e, id, type, activeFlag)
        const searchBlob = propPairs.map(([k, v]) => `${k}=${v} ${k}:${v}`).join(' ').toLowerCase()
        return {
            id,
            type,
            _isActive: activeFlag,
            _raw: e,
            _fieldMap: fieldMap,
            _propPairs: propPairs,
            _searchBlob: searchBlob,
            TimeInstant: e.TimeInstant,
            updated_at: e.updated_at,
        }
    })
})

const entityTypeChips = computed(() => {
    const base = filterActiveOnly.value
        ? normalizedEntities.value.filter((e) => e._isActive)
        : normalizedEntities.value
    const counts = new Map<string, number>()
    for (const ent of base) {
        counts.set(ent.type, (counts.get(ent.type) ?? 0) + 1)
    }
    const typeEntries = Array.from(counts.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([type, count]) => ({ type, label: type, count }))

    return [{ type: 'ALL', label: 'All', count: base.length }, ...typeEntries]
})

const parsedFilterClauses = computed(() => parseFilterQuery(searchQuery.value))

const filteredAndSortedEntities = computed(() => {
    let result = normalizedEntities.value

    if (filterActiveOnly.value) {
        result = result.filter((e) => e._isActive)
    }

    if (selectedTypeFilter.value !== 'ALL') {
        result = result.filter((e) => e.type === selectedTypeFilter.value)
    }

    if (parsedFilterClauses.value.length > 0) {
        const clauses = parsedFilterClauses.value
        result = result.filter((e) => matchesEntityQuery(e, clauses))
    }

    const sorted = [...result]
    sorted.sort((a, b) => {
        let valA: any = 0
        let valB: any = 0

        if (sortKey.value === 'id') {
            valA = a.id
            valB = b.id
        } else if (sortKey.value === 'type') {
            valA = a.type
            valB = b.type
        } else if (sortKey.value === 'TimeInstant') {
            valA = getEntityTimestampMs(a)
            valB = getEntityTimestampMs(b)
        } else if (sortKey.value === 'active') {
            valA = a._isActive ? 1 : 0
            valB = b._isActive ? 1 : 0
        }

        if (valA < valB) return sortOrder.value === 'asc' ? -1 : 1
        if (valA > valB) return sortOrder.value === 'asc' ? 1 : -1
        return 0
    })

    return sorted
})

const totalPages = computed(() => {
    if (pageSize.value === 'all') return 1
    return Math.max(1, Math.ceil(filteredAndSortedEntities.value.length / pageSize.value))
})

const safeCurrentPage = computed(() => Math.min(Math.max(1, currentPage.value), totalPages.value))

const paginatedEntities = computed(() => {
    const items = filteredAndSortedEntities.value
    if (pageSize.value === 'all') return items
    const start = (safeCurrentPage.value - 1) * pageSize.value
    return items.slice(start, start + pageSize.value)
})

const pageRangeStart = computed(() => {
    if (filteredAndSortedEntities.value.length === 0) return 0
    if (pageSize.value === 'all') return 1
    return (safeCurrentPage.value - 1) * pageSize.value + 1
})

const pageRangeEnd = computed(() => {
    const total = filteredAndSortedEntities.value.length
    if (total === 0) return 0
    if (pageSize.value === 'all') return total
    return Math.min(total, safeCurrentPage.value * pageSize.value)
})

watch([searchQuery, selectedTypeFilter, filterActiveOnly, pageSize], () => {
    currentPage.value = 1
})

watch(totalPages, (tp) => {
    if (currentPage.value > tp) currentPage.value = tp
})

const getEntityIcon = (type: string) => {
    if (type.toLowerCase().includes('vehicle')) return Truck
    if (type.toLowerCase().includes('roadside')) return Radio
    return Box
}

const formatDate = (entity: any) => {
    const ms = getEntityTimestampMs(entity)
    if (!ms) return 'N/A'
    return new Date(ms).toLocaleTimeString()
}
</script>

<template>
  <div class="h-full w-full flex flex-col overflow-hidden"
       :class="store.theme === 'dark' ? 'bg-slate-900 text-slate-100' : 'bg-white text-slate-800'">

    <!-- Portal Broker Mode & Actions into Global Header -->
    <Teleport defer to="#view-header-actions">
      <div class="flex items-center gap-2 shrink-0">
        <span class="px-2 py-1 rounded-md text-[10px] font-mono font-bold uppercase border whitespace-nowrap"
              :class="store.fiwareConnected
                ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/25'
                : 'bg-[#00305E]/10 text-[#00305E] border-[#00305E]/20 dark:bg-sky-500/15 dark:text-sky-300 dark:border-sky-400/25'">
          {{ store.fiwareConnected ? 'FIWARE ORION' : 'NATIVE IN-MEMORY' }}
        </span>
        <button @click="cleanIdle"
                :disabled="isCleaning"
                class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md transition-colors border text-[10px] font-bold uppercase tracking-wider cursor-pointer"
                :class="[
                    isCleaning ? 'opacity-50 cursor-not-allowed' : '',
                    store.theme === 'dark'
                        ? 'bg-red-500/10 border-red-500/25 text-red-400 hover:bg-red-500/20'
                        : 'bg-red-50 border-red-200 text-red-600 hover:bg-red-100'
                ]">
          <Trash2 :size="13" :class="isCleaning ? 'animate-pulse' : ''" />
          <span>{{ isCleaning ? 'Cleaning...' : 'Clean Idle' }}</span>
        </button>
        <button @click="refreshBroker"
                class="p-1.5 rounded-md transition-colors border group cursor-pointer"
                :class="store.theme === 'dark' ? 'bg-slate-800 border-white/10 text-slate-400 hover:text-white' : 'bg-slate-50 border-slate-200 text-slate-500 hover:text-[#00305E]'"
                title="Refresh Broker Status & Entities">
          <RefreshCcw :size="15" class="group-active:rotate-180 transition-transform duration-500" />
        </button>
      </div>
    </Teleport>

    <!-- Flush Broker Metrics Ribbon -->
    <div class="px-5 py-2.5 border-b shrink-0"
         :class="store.theme === 'dark' ? 'bg-slate-950/50 border-white/10' : 'bg-slate-50/70 border-slate-200'">
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
        <div class="flex items-center justify-between px-3 py-2 rounded-md border"
             :class="store.theme === 'dark' ? 'bg-white/5 border-white/5' : 'bg-white border-slate-200/80'">
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Entities</span>
          <span class="text-lg font-mono font-bold" :class="store.theme === 'dark' ? 'text-sky-400' : 'text-[#00305E]'">{{ store.fiwareEntities.length }}</span>
        </div>
        <div class="flex flex-col justify-center px-3 py-2 rounded-md border min-w-0"
             :class="store.theme === 'dark' ? 'bg-white/5 border-white/5 text-slate-300' : 'bg-white border-slate-200/80 text-slate-700'">
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Active Driver</span>
          <span class="font-mono text-xs truncate" :title="store.brokerDriver">{{ store.brokerDriver }}</span>
        </div>
        <div class="flex flex-col justify-center px-3 py-2 rounded-md border min-w-0"
             :class="store.theme === 'dark' ? 'bg-white/5 border-white/5 text-slate-300' : 'bg-white border-slate-200/80 text-slate-700'">
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Service Scope</span>
          <span class="font-mono text-xs truncate">{{ store.fiwareService }} {{ store.fiwareServicePath }}</span>
        </div>
        <div class="flex flex-col justify-center px-3 py-2 rounded-md border"
             :class="store.theme === 'dark' ? 'bg-white/5 border-white/5' : 'bg-white border-slate-200/80'">
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Status</span>
          <div class="flex items-center gap-1.5 font-mono font-bold text-xs"
               :class="store.fiwareEnabled ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-500'">
            <span class="w-1.5 h-1.5 rounded-full"
                  :class="store.fiwareEnabled ? 'bg-emerald-500' : 'bg-amber-500'"></span>
            {{ store.fiwareEnabled ? (store.fiwareConnected ? 'FIWARE LIVE' : 'NATIVE ACTIVE') : 'OFFLINE' }}
          </div>
        </div>
      </div>
    </div>

    <!-- Collapsible Roadside & FIWARE Service-Group Endpoints Strip (Closed by Default) -->
    <details class="border-b shrink-0 group"
             :class="store.theme === 'dark' ? 'bg-slate-900 border-white/10 text-slate-200' : 'bg-white border-slate-200 text-slate-800'">
        <summary class="px-5 py-2.5 flex items-center justify-between cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden">
            <div class="flex items-center gap-2.5">
                <Link2 :size="15" class="text-[#00305E] dark:text-sky-400" />
                <span class="font-bold text-xs uppercase tracking-wider text-slate-600 dark:text-slate-300">
                    Roadside &amp; FIWARE Connection Endpoints (Service Groups)
                </span>
                <span class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border"
                      :class="store.fiwareConnected
                        ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-700 dark:text-emerald-400'
                        : 'bg-slate-500/10 border-slate-300/70 dark:border-white/10 text-slate-500 dark:text-slate-400'">
                    {{ store.brokerServiceGroups.length }} Service Groups
                </span>
            </div>
            <ChevronDown :size="15" class="text-slate-400 transition-transform group-open:rotate-180" />
        </summary>

        <div class="px-5 pb-4 pt-3 max-h-[38vh] overflow-y-auto custom-scrollbar grid grid-cols-1 lg:grid-cols-2 gap-3 border-t"
             :class="store.theme === 'dark' ? 'border-white/5' : 'border-slate-100'">
            <!-- Left: Roadside & Backend Ingest -->
            <div class="p-3.5 rounded-md border space-y-2 transition-all"
                 :class="[
                    store.theme === 'dark' ? 'bg-slate-950/60' : 'bg-slate-50/80',
                    isNativeActive
                        ? 'border-emerald-500/35 ring-1 ring-emerald-500/15'
                        : (store.theme === 'dark' ? 'border-white/10 border-dashed opacity-55 grayscale-[35%] hover:opacity-80' : 'border-slate-300/70 border-dashed opacity-55 grayscale-[35%] hover:opacity-80')
                 ]">
                <div class="flex items-center justify-between">
                    <span class="text-[11px] font-bold uppercase tracking-wider"
                          :class="isNativeActive ? 'text-purple-600 dark:text-purple-400' : 'text-slate-400 dark:text-slate-500'">
                        Roadside &amp; Backend Ingest (FastAPI)
                    </span>
                    <span class="text-[10px] font-mono px-1.5 py-0.5 rounded font-bold"
                          :class="isNativeActive
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                            : 'bg-slate-500/10 text-slate-500 dark:text-slate-400'">
                        {{ isNativeActive ? 'ACTIVE' : 'INACTIVE' }}
                    </span>
                </div>
                <div class="space-y-1.5 text-xs">
                    <div class="flex items-center justify-between gap-2 p-2 rounded-md border"
                         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
                        <div class="min-w-0">
                            <div class="text-[10px] font-semibold text-slate-500 dark:text-slate-400">RSU-00 Pi Weather Push</div>
                            <code class="text-[11px] font-mono truncate block"
                                  :class="isNativeActive ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400 dark:text-slate-500'">POST {{ store.brokerEndpoints?.roadside_weather_ingest || '/dashboard/weather_data' }}</code>
                        </div>
                        <button @click="copyText('wx', resolveBackendUrl(store.brokerEndpoints?.roadside_weather_ingest || '/dashboard/weather_data'))"
                                class="p-1.5 rounded border text-slate-400 hover:text-[#00305E] dark:hover:text-sky-400 transition-colors shrink-0 cursor-pointer"
                                :class="store.theme === 'dark' ? 'border-white/10 hover:bg-white/5' : 'border-slate-200 hover:bg-slate-50'"
                                title="Copy endpoint URL">
                            <Check v-if="copiedKey === 'wx'" :size="13" class="text-emerald-500" />
                            <Copy v-else :size="13" />
                        </button>
                    </div>

                    <div class="flex items-center justify-between gap-2 p-2 rounded-md border"
                         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
                        <div class="min-w-0">
                            <div class="text-[10px] font-semibold text-slate-500 dark:text-slate-400">6-Channel Embedded Pavement DAQ</div>
                            <code class="text-[11px] font-mono truncate block"
                                  :class="isNativeActive ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400 dark:text-slate-500'">POST {{ store.brokerEndpoints?.embedded_sensor_ingest || '/api/telemetry/sensors/{station_id}' }}</code>
                        </div>
                        <button @click="copyText('daq', resolveBackendUrl(store.brokerEndpoints?.embedded_sensor_ingest || '/api/telemetry/sensors/{station_id}'))"
                                class="p-1.5 rounded border text-slate-400 hover:text-[#00305E] dark:hover:text-sky-400 transition-colors shrink-0 cursor-pointer"
                                :class="store.theme === 'dark' ? 'border-white/10 hover:bg-white/5' : 'border-slate-200 hover:bg-slate-50'"
                                title="Copy endpoint URL">
                            <Check v-if="copiedKey === 'daq'" :size="13" class="text-emerald-500" />
                            <Copy v-else :size="13" />
                        </button>
                    </div>

                    <div class="flex items-center justify-between gap-2 p-2 rounded-md border"
                         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
                        <div class="min-w-0">
                            <div class="text-[10px] font-semibold text-slate-500 dark:text-slate-400">Unified Context Entity Registry</div>
                            <a :href="rawEntitiesUrl" target="_blank"
                               class="text-[11px] font-mono hover:underline truncate block"
                               :class="isNativeActive ? 'text-[#00305E] dark:text-sky-400' : 'text-slate-400 dark:text-slate-500'">
                                GET {{ store.brokerEndpoints?.broker_entities || '/dashboard/fiware_entities' }}
                            </a>
                        </div>
                        <button @click="copyText('ents', rawEntitiesUrl)"
                                class="p-1.5 rounded border text-slate-400 hover:text-[#00305E] dark:hover:text-sky-400 transition-colors shrink-0 cursor-pointer"
                                :class="store.theme === 'dark' ? 'border-white/10 hover:bg-white/5' : 'border-slate-200 hover:bg-slate-50'"
                                title="Copy endpoint URL">
                            <Check v-if="copiedKey === 'ents'" :size="13" class="text-emerald-500" />
                            <Copy v-else :size="13" />
                        </button>
                    </div>

                    <div class="flex items-center justify-between gap-2 p-2 rounded-md border"
                         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
                        <div class="min-w-0">
                            <div class="text-[10px] font-semibold text-slate-500 dark:text-slate-400">Single Entity Context API</div>
                            <code class="text-[11px] font-mono truncate block"
                                  :class="isNativeActive ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400 dark:text-slate-500'">GET {{ store.brokerEndpoints?.broker_entity_template || '/dashboard/fiware_entities/{entity_id}' }}</code>
                        </div>
                        <button @click="copyText('ent', resolveBackendUrl(store.brokerEndpoints?.broker_entity_template || '/dashboard/fiware_entities/{entity_id}'))"
                                class="p-1.5 rounded border text-slate-400 hover:text-[#00305E] dark:hover:text-sky-400 transition-colors shrink-0 cursor-pointer"
                                :class="store.theme === 'dark' ? 'border-white/10 hover:bg-white/5' : 'border-slate-200 hover:bg-slate-50'"
                                title="Copy endpoint URL">
                            <Check v-if="copiedKey === 'ent'" :size="13" class="text-emerald-500" />
                            <Copy v-else :size="13" />
                        </button>
                    </div>

                    <div class="flex items-center justify-between gap-2 p-2 rounded-md border"
                         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
                        <div class="min-w-0">
                            <div class="text-[10px] font-semibold text-slate-500 dark:text-slate-400">Entity History API</div>
                            <code class="text-[11px] font-mono truncate block"
                                  :class="isNativeActive ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400 dark:text-slate-500'">GET {{ store.brokerEndpoints?.broker_entity_history_template || '/dashboard/fiware_entities/{entity_id}/history' }}</code>
                        </div>
                        <button @click="copyText('hist', resolveBackendUrl(store.brokerEndpoints?.broker_entity_history_template || '/dashboard/fiware_entities/{entity_id}/history'))"
                                class="p-1.5 rounded border text-slate-400 hover:text-[#00305E] dark:hover:text-sky-400 transition-colors shrink-0 cursor-pointer"
                                :class="store.theme === 'dark' ? 'border-white/10 hover:bg-white/5' : 'border-slate-200 hover:bg-slate-50'"
                                title="Copy history endpoint URL">
                            <Check v-if="copiedKey === 'hist'" :size="13" class="text-emerald-500" />
                            <Copy v-else :size="13" />
                        </button>
                    </div>
                </div>
            </div>

            <!-- Right: FIWARE Orion & Service Groups -->
            <div class="p-3.5 rounded-md border space-y-2 transition-all"
                 :class="[
                    store.theme === 'dark' ? 'bg-slate-950/60' : 'bg-slate-50/80',
                    isFiwareActive
                        ? 'border-emerald-500/35 ring-1 ring-emerald-500/15'
                        : (store.theme === 'dark' ? 'border-white/10 border-dashed opacity-55 grayscale-[35%] hover:opacity-80' : 'border-slate-300/70 border-dashed opacity-55 grayscale-[35%] hover:opacity-80')
                 ]">
                <div class="flex items-center justify-between">
                    <span class="text-[11px] font-bold uppercase tracking-wider"
                          :class="isFiwareActive ? 'text-cyan-600 dark:text-cyan-400' : 'text-slate-400 dark:text-slate-500'">
                        FIWARE Orion &amp; Service Groups (NGSIv2 / UltraLight 2.0)
                    </span>
                    <span class="text-[10px] font-mono px-1.5 py-0.5 rounded font-bold"
                          :class="isFiwareActive
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                            : 'bg-slate-500/10 text-slate-500 dark:text-slate-400'">
                        {{ isFiwareActive ? 'ORION LIVE' : 'INACTIVE' }}
                    </span>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-3 gap-1.5 text-[10.5px]">
                    <div class="flex items-center justify-between gap-1.5 p-2 rounded-md border"
                         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
                        <div class="min-w-0">
                            <div class="text-[9.5px] font-bold text-slate-400">Orion NGSIv2</div>
                            <div class="font-mono truncate" :class="isFiwareActive ? '' : 'text-slate-400 dark:text-slate-500'" :title="store.brokerEndpoints?.orion_entities">{{ store.brokerEndpoints?.orion_entities || 'http://localhost:1026/v2/entities' }}</div>
                        </div>
                        <button @click="copyText('orion', store.brokerEndpoints?.orion_entities || 'http://localhost:1026/v2/entities')"
                                class="p-1 rounded text-slate-400 hover:text-[#00305E] dark:hover:text-sky-400 shrink-0 cursor-pointer"
                                title="Copy Orion URL">
                            <Check v-if="copiedKey === 'orion'" :size="12" class="text-emerald-500" />
                            <Copy v-else :size="12" />
                        </button>
                    </div>
                    <div class="flex items-center justify-between gap-1.5 p-2 rounded-md border"
                         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
                        <div class="min-w-0">
                            <div class="text-[9.5px] font-bold text-slate-400">IoT Agent North</div>
                            <div class="font-mono truncate" :class="isFiwareActive ? '' : 'text-slate-400 dark:text-slate-500'" :title="store.brokerEndpoints?.iota_services">{{ store.brokerEndpoints?.iota_services || 'http://localhost:4041/iot/services' }}</div>
                        </div>
                        <button @click="copyText('iota_n', store.brokerEndpoints?.iota_services || 'http://localhost:4041/iot/services')"
                                class="p-1 rounded text-slate-400 hover:text-[#00305E] dark:hover:text-sky-400 shrink-0 cursor-pointer"
                                title="Copy IoT Agent North URL">
                            <Check v-if="copiedKey === 'iota_n'" :size="12" class="text-emerald-500" />
                            <Copy v-else :size="12" />
                        </button>
                    </div>
                    <div class="flex items-center justify-between gap-1.5 p-2 rounded-md border"
                         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
                        <div class="min-w-0">
                            <div class="text-[9.5px] font-bold text-slate-400">IoT Agent South</div>
                            <div class="font-mono truncate" :class="isFiwareActive ? '' : 'text-slate-400 dark:text-slate-500'" :title="store.brokerEndpoints?.iota_ultralight">{{ store.brokerEndpoints?.iota_ultralight || 'http://localhost:7896/iot/d' }}</div>
                        </div>
                        <button @click="copyText('iota_s', store.brokerEndpoints?.iota_ultralight || 'http://localhost:7896/iot/d')"
                                class="p-1 rounded text-slate-400 hover:text-[#00305E] dark:hover:text-sky-400 shrink-0 cursor-pointer"
                                title="Copy IoT Agent South URL">
                            <Check v-if="copiedKey === 'iota_s'" :size="12" class="text-emerald-500" />
                            <Copy v-else :size="12" />
                        </button>
                    </div>
                </div>

                <!-- Schema Service Groups -->
                <div class="space-y-1.5">
                    <div v-for="sg in store.brokerServiceGroups" :key="sg.id || sg.entity_type"
                         class="flex items-center justify-between gap-2 p-2 rounded-md border text-xs"
                         :class="store.theme === 'dark' ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200/80'">
                        <div class="min-w-0">
                            <div class="flex items-center gap-1.5">
                                <span class="font-bold text-[10.5px]"
                                      :class="isFiwareActive ? 'text-cyan-600 dark:text-cyan-400' : 'text-slate-500 dark:text-slate-400'">{{ sg.entity_type }}</span>
                                <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-500 dark:text-slate-400">{{ sg.id }}</span>
                                <span class="text-[10px] font-mono"
                                      :class="isFiwareActive ? 'text-purple-600 dark:text-purple-400' : 'text-slate-400 dark:text-slate-500'">k={{ sg.runtime_apikey || sg.apikey }}</span>
                            </div>
                            <code class="text-[10.5px] font-mono truncate block"
                                  :class="isFiwareActive ? 'text-slate-600 dark:text-slate-300' : 'text-slate-400 dark:text-slate-500'">{{ sg.ultralight_endpoint }}</code>
                        </div>
                        <button @click="copyText(`sg_${sg.id || sg.entity_type}`, sg.ultralight_endpoint)"
                                class="p-1.5 rounded border text-slate-400 hover:text-[#00305E] dark:hover:text-sky-400 transition-colors shrink-0 cursor-pointer"
                                :class="store.theme === 'dark' ? 'border-white/10 hover:bg-white/5' : 'border-slate-200 hover:bg-slate-50'"
                                title="Copy UltraLight 2.0 endpoint">
                            <Check v-if="copiedKey === `sg_${sg.id || sg.entity_type}`" :size="13" class="text-emerald-500" />
                            <Copy v-else :size="13" />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </details>

    <!-- Flush Context Entities Table Region -->
    <div class="flex-1 min-h-0 flex flex-col overflow-hidden"
         :class="store.theme === 'dark' ? 'bg-slate-900' : 'bg-white'">

        <div class="px-5 py-3 border-b space-y-2.5 shrink-0" :class="store.theme === 'dark' ? 'border-white/5' : 'border-slate-100'">
            <!-- Row 1: Title, SQL-like Filter Bar, Active Toggle, Auto-refresh Label -->
            <div class="flex flex-wrap items-center justify-between gap-2.5">
                <div class="flex flex-wrap items-center gap-2.5 flex-1 min-w-0">
                    <div class="flex items-center gap-2 shrink-0">
                        <h3 class="font-bold text-xs uppercase tracking-wider text-slate-500 dark:text-slate-300">Context Entities</h3>
                        <span class="px-1.5 py-0.5 rounded font-mono text-[10px] font-semibold border"
                              :class="store.theme === 'dark' ? 'bg-white/5 border-white/10 text-slate-300' : 'bg-slate-100 border-slate-200 text-slate-600'">
                            {{ filteredAndSortedEntities.length }}
                        </span>
                    </div>

                    <!-- Universal SQL-like Filter Input -->
                    <div class="relative flex-1 min-w-[240px] max-w-xl">
                        <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" :size="13" />
                        <input v-model="searchQuery"
                               type="text"
                               placeholder="Filter: ID, type, or SQL-like e.g. Velocity>85 Weight>=35000 Weather=Sunny"
                               class="w-full bg-transparent border rounded-md py-1.5 pl-8 pr-8 text-xs font-mono focus:ring-2 focus:ring-[#00305E]/20 transition-all outline-none"
                               :class="store.theme === 'dark' ? 'border-white/10 text-white placeholder:text-slate-500' : 'border-slate-200 text-slate-800 placeholder:text-slate-400'">
                        <button v-if="searchQuery"
                                @click="searchQuery = ''"
                                type="button"
                                class="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
                                title="Clear filter">
                            <X :size="13" />
                        </button>
                    </div>

                    <!-- Active Filter Toggle -->
                    <button @click="filterActiveOnly = !filterActiveOnly"
                            class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-[11px] font-semibold transition-colors cursor-pointer shrink-0"
                            :class="[
                                filterActiveOnly
                                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
                                    : (store.theme === 'dark' ? 'bg-transparent border-white/10 text-slate-400 hover:text-slate-200' : 'bg-transparent border-slate-200 text-slate-600 hover:border-slate-300')
                            ]">
                        <Activity :size="12" />
                        ACTIVE ONLY
                    </button>
                </div>

                <span class="text-[11px] font-mono text-slate-400 shrink-0">
                    Auto-refresh 5s
                </span>
            </div>

            <!-- Row 2: Entity Type Filter Chips & Query Operator Hint -->
            <div class="flex flex-wrap items-center justify-between gap-2">
                <div class="flex flex-wrap items-center gap-1.5">
                    <button v-for="chip in entityTypeChips"
                            :key="chip.type"
                            @click="selectedTypeFilter = chip.type"
                            type="button"
                            class="px-2 py-0.5 rounded border text-[11px] font-medium transition-colors cursor-pointer"
                            :class="selectedTypeFilter === chip.type
                                ? 'bg-[#00305E] text-white border-[#00305E] dark:bg-sky-500/20 dark:text-sky-300 dark:border-sky-400/40'
                                : (store.theme === 'dark' ? 'bg-slate-800/70 border-white/10 text-slate-400 hover:text-slate-200' : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100')">
                        <span>{{ chip.label }}</span>
                        <span class="ml-1 font-mono opacity-75">({{ chip.count }})</span>
                    </button>
                </div>
                <span class="text-[10px] font-mono text-slate-400">
                    Ops: = != &gt; &gt;= &lt; &lt;= ~ AND OR
                </span>
            </div>
        </div>

        <div class="flex-1 overflow-auto custom-scrollbar">
            <table class="w-full text-left border-collapse">
                <thead class="sticky top-0 z-10 border-b"
                       :class="store.theme === 'dark' ? 'bg-slate-950/90 border-white/10 backdrop-blur-md' : 'bg-slate-50/95 border-slate-200/80 backdrop-blur-md'">
                    <tr>
                        <th @click="toggleSort('id')" class="px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-400 cursor-pointer hover:text-[#00305E] dark:hover:text-sky-400 transition-colors whitespace-nowrap">
                            <div class="flex items-center gap-1">
                                ID / Type
                                <SortAsc v-if="sortKey === 'id' && sortOrder === 'asc'" :size="12" />
                                <SortDesc v-if="sortKey === 'id' && sortOrder === 'desc'" :size="12" />
                            </div>
                        </th>
                        <th class="px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-400 w-full">Properties (Key-Values)</th>
                        <th @click="toggleSort('active')" class="px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-400 cursor-pointer hover:text-[#00305E] dark:hover:text-sky-400 transition-colors whitespace-nowrap">
                            <div class="flex items-center gap-1">
                                Status
                                <SortAsc v-if="sortKey === 'active' && sortOrder === 'asc'" :size="12" />
                                <SortDesc v-if="sortKey === 'active' && sortOrder === 'desc'" :size="12" />
                            </div>
                        </th>
                        <th @click="toggleSort('TimeInstant')" class="px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-400 cursor-pointer hover:text-[#00305E] dark:hover:text-sky-400 transition-colors whitespace-nowrap">
                            <div class="flex items-center gap-1">
                                Last Seen
                                <SortAsc v-if="sortKey === 'TimeInstant' && sortOrder === 'asc'" :size="12" />
                                <SortDesc v-if="sortKey === 'TimeInstant' && sortOrder === 'desc'" :size="12" />
                            </div>
                        </th>
                        <th class="px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-400 whitespace-nowrap">Action</th>
                    </tr>
                </thead>
                <tbody class="divide-y" :class="store.theme === 'dark' ? 'divide-white/5' : 'divide-slate-100'">
                    <tr v-for="entity in paginatedEntities" :key="entity.id"
                        class="group transition-colors"
                        :class="store.theme === 'dark' ? 'hover:bg-white/5' : 'hover:bg-slate-50/80'">
                        <td class="px-4 py-2.5 whitespace-nowrap">
                            <div class="flex items-center gap-2.5">
                                <component :is="getEntityIcon(entity.type)" :size="16" class="text-[#00305E] dark:text-sky-400 opacity-85 shrink-0" />
                                <div class="flex flex-col">
                                    <span class="text-xs font-mono font-bold" :class="store.theme === 'dark' ? 'text-slate-100' : 'text-slate-800'">{{ entity.id }}</span>
                                    <span class="text-[10px] uppercase font-bold tracking-wider" :class="store.theme === 'dark' ? 'text-sky-400' : 'text-[#00305E]'">{{ entity.type }}</span>
                                </div>
                            </div>
                        </td>
                        <td class="px-4 py-2.5">
                            <div class="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] font-mono leading-snug">
                                <span v-for="[propKey, propVal] in entity._propPairs"
                                      :key="propKey"
                                      class="inline-flex items-baseline whitespace-nowrap"
                                      :title="`${propKey}=${propVal}`">
                                    <span class="font-semibold"
                                          :class="store.theme === 'dark' ? 'text-sky-400' : 'text-[#00305E]'">{{ propKey }}</span><span class="text-slate-400 mx-0.5">=</span><span class="truncate max-w-[160px]"
                                          :class="store.theme === 'dark' ? 'text-slate-200' : 'text-slate-700'">{{ propVal }}</span>
                                </span>
                            </div>
                        </td>
                        <td class="px-4 py-2.5 whitespace-nowrap">
                            <div class="flex items-center gap-1.5">
                                <span class="w-1.5 h-1.5 rounded-full"
                                      :class="entity._isActive ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-700'"></span>
                                <span class="text-[10px] font-mono font-bold uppercase"
                                      :class="entity._isActive ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400'">
                                    {{ entity._isActive ? 'Active' : 'Idle' }}
                                </span>
                            </div>
                        </td>
                        <td class="px-4 py-2.5 whitespace-nowrap">
                            <span class="text-xs font-mono" :class="store.theme === 'dark' ? 'text-slate-400' : 'text-slate-500'">
                                {{ formatDate(entity) }}
                            </span>
                        </td>
                        <td class="px-4 py-2.5 whitespace-nowrap">
                            <div class="flex items-center gap-3 text-xs font-semibold">
                                <a :href="getEntityRawUrl(entity.id)" target="_blank"
                                   class="inline-flex items-center gap-1 transition-colors no-underline hover:underline"
                                   :class="store.theme === 'dark' ? 'text-sky-400 hover:text-sky-300' : 'text-[#00305E] hover:text-blue-700'">
                                    Raw <ExternalLink :size="11" />
                                </a>
                                <a :href="getEntityHistoryUrl(entity.id)" target="_blank"
                                   class="inline-flex items-center gap-1 transition-colors no-underline hover:underline"
                                   :class="store.theme === 'dark' ? 'text-slate-300 hover:text-sky-300' : 'text-slate-600 hover:text-[#00305E]'">
                                    History <History :size="11" />
                                </a>
                            </div>
                        </td>
                    </tr>
                    <tr v-if="paginatedEntities.length === 0">
                        <td colspan="5" class="px-6 py-16 text-center">
                            <div class="flex flex-col items-center gap-2 opacity-40">
                                <Database :size="40" />
                                <span class="text-xs font-medium">No entities match your filters.</span>
                            </div>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- Pagination Footer -->
        <div class="px-5 py-2 border-t flex flex-wrap items-center justify-between gap-2 text-[11px] shrink-0"
             :class="store.theme === 'dark' ? 'bg-slate-950/60 border-white/10 text-slate-300' : 'bg-slate-50 border-slate-200/80 text-slate-600'">
            <div>
                Showing <span class="font-mono font-semibold">{{ pageRangeStart }}–{{ pageRangeEnd }}</span>
                of <span class="font-mono font-semibold">{{ filteredAndSortedEntities.length }}</span>
                <span v-if="filteredAndSortedEntities.length !== store.fiwareEntities.length" class="text-slate-400 ml-1">
                    (filtered from {{ store.fiwareEntities.length }})
                </span>
            </div>

            <div class="flex items-center gap-3">
                <div class="flex items-center gap-1">
                    <span class="text-slate-400 mr-1">Per page:</span>
                    <button v-for="opt in ([25, 50, 'all'] as const)"
                            :key="String(opt)"
                            @click="pageSize = opt"
                            type="button"
                            class="px-2 py-0.5 rounded border font-mono text-[10px] font-semibold transition-colors cursor-pointer"
                            :class="pageSize === opt
                                ? 'bg-[#00305E] text-white border-[#00305E] dark:bg-sky-500/20 dark:text-sky-300 dark:border-sky-400/40'
                                : (store.theme === 'dark' ? 'border-white/10 text-slate-400 hover:text-white' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-100')">
                        {{ opt === 'all' ? 'All' : opt }}
                    </button>
                </div>

                <div class="flex items-center gap-1">
                    <button @click="currentPage = Math.max(1, safeCurrentPage - 1)"
                            :disabled="safeCurrentPage <= 1 || pageSize === 'all'"
                            type="button"
                            class="inline-flex items-center gap-0.5 px-2 py-0.5 rounded border text-[11px] font-medium transition-colors"
                            :class="[
                                (safeCurrentPage <= 1 || pageSize === 'all') ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer',
                                store.theme === 'dark' ? 'border-white/10 text-slate-300 hover:bg-white/5' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-100'
                            ]">
                        <ChevronLeft :size="12" />
                        Prev
                    </button>
                    <span class="px-2 font-mono text-[11px]">
                        Page {{ safeCurrentPage }} / {{ totalPages }}
                    </span>
                    <button @click="currentPage = Math.min(totalPages, safeCurrentPage + 1)"
                            :disabled="safeCurrentPage >= totalPages || pageSize === 'all'"
                            type="button"
                            class="inline-flex items-center gap-0.5 px-2 py-0.5 rounded border text-[11px] font-medium transition-colors"
                            :class="[
                                (safeCurrentPage >= totalPages || pageSize === 'all') ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer',
                                store.theme === 'dark' ? 'border-white/10 text-slate-300 hover:bg-white/5' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-100'
                            ]">
                        Next
                        <ChevronRight :size="12" />
                    </button>
                </div>
            </div>
        </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.2);
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.4);
}
</style>
