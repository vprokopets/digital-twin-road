/**
 * Central Pinia state store managing SSE streaming, static GIS layers, entity selection,
 * scenario configuration, and live 2D/3D inspection telemetry.
 */
import { defineStore } from 'pinia'
import { markRaw } from 'vue'
import apiClient from '../api/client'

let activeEventSource: EventSource | null = null

/**
 * Primary Pinia Store for the Digital Twin Road Demonstrator.
 *
 * Performance Architecture:
 * - Static GIS layers (`road_curves`, `road_segments`, `road`, `water`, `spawn`, `ru`)
 *   are fetched once via `/dashboard/static_layers` and wrapped in `markRaw()` so Vue's
 *   reactivity engine never deep-proxies 16,000+ GeoJSON vertices.
 * - Live 5-second SSE ticks (`/dashboard/stream`) deliver lightweight delta payloads
 *   (`vehicles`, `drones`, `warnings`, `rsu_live`, `dirty_segments`, `federation_summary`).
 */
export const useDashboardStore = defineStore('dashboard', {
    state: () => ({
        digitalShadowRaw: null as any,
        staticLayersLoaded: false,
        streamTickCounter: 0,
        lastDirtySegments: {} as Record<string, number>,
        telemetryStats: [],
        droneSimulationResults: null,
        isStreaming: false,
        isConnected: false,
        selectedData: null as any,
        selectedType: null as string | null,
        selectedFeature: null as any,
        // Live real-time frontend icon extrapolation history indexed by vehicle ID
        vehicleExtrapolations: {} as Record<string, Array<{
            timestamp: string;
            km: number;
            standardVelocity: number;
            extrapolatedSpeed: number;
            driftKm: number;
        }>>,
        followVehicle: false,
        simSpeed: 1 as number,
        theme: ((typeof localStorage !== 'undefined' && localStorage.getItem('color-scheme') === 'dark') ? 'dark' : 'light') as 'light' | 'dark',
        isMetadataCollapsed: false,
        isTreeCollapsed: false,
        isVtkCollapsed: false,
        isThermalCollapsed: false,
        currentView: 'digital-shadow' as 'digital-shadow' | 'fiware-status' | 'documentation',
        predictionPlotData: null as any,
        fiwareEnabled: false,
        fiwareConnected: false,
        brokerBackend: 'native' as string,
        brokerDriver: 'In-Memory' as string,
        brokerEndpoints: null as Record<string, string> | null,
        brokerServiceGroups: [] as any[],
        fiwareService: 'openiot' as string,
        fiwareServicePath: '/' as string,
        fiwareEntities: [] as any[],
        mapCenter: [51.2, 13.1] as [number, number],
        mapZoom: 10,
        isEditorMode: false as boolean,
        hasUnsavedEdits: false as boolean,
    }),
    getters: {
        activeVehiclesCount: (state): number => {
            if (state.digitalShadowRaw?.map_layers?.vehicles?.features) {
                return state.digitalShadowRaw.map_layers.vehicles.features.length
            }
            return 0
        },
        activeRuCount: (state): number => {
            if (state.digitalShadowRaw?.map_layers?.ru?.features) {
                return state.digitalShadowRaw.map_layers.ru.features.length
            }
            return 0
        },
        activeDronesCount: (state): number => {
            if (state.digitalShadowRaw?.map_layers?.drones?.features) {
                return state.digitalShadowRaw.map_layers.drones.features.length
            }
            return 0
        },
        activeWarningsCount: (state): number => {
            if (state.digitalShadowRaw?.map_layers?.warnings?.features) {
                return state.digitalShadowRaw.map_layers.warnings.features.length
            }
            return 0
        },
        federationSummary: (state): any => {
            return state.digitalShadowRaw?.federation_summary || {
                active_contracts_count: 0,
                total_Negotiations: 0,
                total_FastSlowSyncs: 0,
                total_Recalibrations: 0,
                total_Handovers: 0,
                recent_interactions: [],
            }
        },
        corridorAvgHealth: (state): number => {
            const features = state.digitalShadowRaw?.map_layers?.road_segments?.features
            if (!Array.isArray(features) || features.length === 0) return 91.5
            let sum = 0
            for (const f of features) {
                sum += Number(f.properties?.state ?? 100)
            }
            return Number((sum / features.length).toFixed(1))
        }
    },
    actions: {
        /**
         * Fetches static GIS layers once and wraps each FeatureCollection in `markRaw`
         * to prevent Vue deep reactivity overhead during map zooming/panning.
         */
        async fetchStaticLayers() {
            if (this.staticLayersLoaded && this.digitalShadowRaw?.map_layers?.road_segments) {
                return
            }
            try {
                const response = await apiClient.get('/dashboard/static_layers')
                const data = response.data
                if (data?.map_layers) {
                    const rawLayers: Record<string, any> = {}
                    for (const [key, val] of Object.entries(data.map_layers)) {
                        rawLayers[key] = val && typeof val === 'object' ? markRaw(val) : val
                    }
                    if (!this.digitalShadowRaw) {
                        this.digitalShadowRaw = {
                            status: 'ok',
                            timestamp: data.timestamp,
                            coordinate_system: data.coordinate_system || { mode: 'WGS84', crs_epsg: 4326 },
                            map_layers: rawLayers,
                            federation_summary: data.federation_summary || {},
                        }
                    } else {
                        this.digitalShadowRaw.coordinate_system = data.coordinate_system || this.digitalShadowRaw.coordinate_system || { mode: 'WGS84', crs_epsg: 4326 }
                        this.digitalShadowRaw.map_layers = {
                            ...rawLayers,
                            ...this.digitalShadowRaw.map_layers,
                        }
                    }
                    this.staticLayersLoaded = true
                }
            } catch (error) {
                console.error('Error fetching static layers:', error)
            }
        },

        /**
         * Fetches full initial state (static + dynamic layers).
         */
        async fetchState() {
            try {
                await this.fetchStaticLayers()
                const response = await apiClient.get('/dashboard/state')
                const data = response.data
                if (data?.map_layers) {
                    const staticKeys = ['road_curves', 'road_segments', 'road', 'water', 'spawn', 'ru']
                    for (const k of staticKeys) {
                        if (data.map_layers[k]) {
                            data.map_layers[k] = markRaw(data.map_layers[k])
                        }
                    }
                    this.staticLayersLoaded = true
                }
                this.digitalShadowRaw = data
                if (data?.sim_speed) {
                    this.simSpeed = data.sim_speed
                }
                this.streamTickCounter++
            } catch (error) {
                console.error('Error fetching dashboard state:', error)
            }
        },

        /**
         * Selects any of the 7 clickable map entity types and fetches its enriched
         * polymorphic inspection payload (`panel`, `stats`, `metadata`, `hpn_graph`, `code`, etc.).
         */
        async selectObject(type: string, feature: any) {
            try {
                const response = await apiClient.post('/dashboard/select_object', {
                    selection_type: type,
                    feature_data: feature
                })
                this.selectedData = response.data
                this.selectedType = type

                // Merge live backend properties if available
                if (response.data.properties && feature?.properties) {
                    feature.properties = { ...feature.properties, ...response.data.properties }
                }
                this.selectedFeature = feature
                if (type !== 'SingleVehicleStateDS') {
                    this.followVehicle = false
                }
                if (type === 'SingleRoadPointStateDS' || type === 'SingleRoadSegmentStateDS') {
                    const health = feature?.properties?.state ?? feature?.properties?.State ?? 85
                    this.fetchPredictionPlot(health)
                }
            } catch (error) {
                console.error('Error fetching object selection:', error)
            }
        },

        /**
         * Clears the active map selection (e.g., when clicking empty map space or pressing Esc/Clear).
         */
        clearSelection() {
            this.selectedData = null
            this.selectedType = null
            this.selectedFeature = null
            this.followVehicle = false
        },

        /**
         * Records a live icon dead-reckoning extrapolation point from the map animation engine.
         */
        recordVehicleExtrapolationPoint(vehicleId: string, record: { timestamp: string; km: number; standardVelocity: number; extrapolatedSpeed: number; driftKm: number }) {
            if (!this.vehicleExtrapolations[vehicleId]) {
                this.vehicleExtrapolations[vehicleId] = []
            }
            const list = this.vehicleExtrapolations[vehicleId]
            list.push(record)
            if (list.length > 80) {
                list.shift()
            }
        },

        /**
         * Connects to the FastAPI SSE stream (`/dashboard/stream`) and applies lightweight
         * 5-second delta updates without recreating static GIS layers.
         */
        startStream() {
            if (activeEventSource) {
                this.stopStream()
            }
            const baseURL = apiClient.defaults.baseURL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '')
            const eventSource = new EventSource(`${baseURL}/dashboard/stream`)
            activeEventSource = eventSource

            eventSource.onopen = () => {
                this.isConnected = true
                this.isStreaming = true
            }

            eventSource.onerror = () => {
                this.isConnected = false
            }

            eventSource.onmessage = async (event) => {
                try {
                    const data = JSON.parse(event.data)
                    if (data.status === 'ok') {
                        if (data.is_delta) {
                            if (!this.staticLayersLoaded || !this.digitalShadowRaw?.map_layers) {
                                return
                            }
                            const existingLayers = this.digitalShadowRaw.map_layers
                            const incomingLayers = data.map_layers || {}

                            // Apply dirty_segments health mutations in-place on cached road_segments & road
                            const dirty: Record<string, number> = incomingLayers.dirty_segments || {}
                            this.lastDirtySegments = dirty
                            if (Object.keys(dirty).length > 0) {
                                const segFeatures = existingLayers.road_segments?.features
                                if (Array.isArray(segFeatures)) {
                                    for (const f of segFeatures) {
                                        const pid = String(f.properties?.point_id ?? f.properties?.id ?? '')
                                        const sid = String(f.properties?.id ?? '')
                                        if (dirty[pid] !== undefined) f.properties.state = dirty[pid]
                                        else if (dirty[sid] !== undefined) f.properties.state = dirty[sid]
                                    }
                                }
                                const roadFeatures = existingLayers.road?.features
                                if (Array.isArray(roadFeatures)) {
                                    for (const f of roadFeatures) {
                                        const id = String(f.properties?.id ?? '')
                                        if (dirty[id] !== undefined) f.properties.state = dirty[id]
                                    }
                                }
                            }

                            this.digitalShadowRaw = {
                                ...this.digitalShadowRaw,
                                timestamp: data.timestamp,
                                sim_speed: data.sim_speed ?? this.simSpeed,
                                federation_summary: data.federation_summary || this.digitalShadowRaw.federation_summary,
                                map_layers: {
                                    ...existingLayers,
                                    vehicles: incomingLayers.vehicles,
                                    drones: incomingLayers.drones,
                                    warnings: incomingLayers.warnings,
                                    rsu_live: incomingLayers.rsu_live,
                                    dirty_segments: dirty,
                                }
                            }
                        } else {
                            this.digitalShadowRaw = data
                        }

                        if (data.sim_speed) {
                            this.simSpeed = data.sim_speed
                        }
                        this.streamTickCounter++

                        // Auto-refresh the currently selected object so its inspector ticks live
                        if (this.selectedType && this.selectedFeature) {
                            let featureToSelect = this.selectedFeature
                            const curId = String(this.selectedFeature.properties?.id ?? this.selectedFeature.properties?.ID ?? '')

                            if (this.selectedType === 'SingleVehicleStateDS' && this.digitalShadowRaw.map_layers?.vehicles?.features) {
                                const latestVehicleFeature = this.digitalShadowRaw.map_layers.vehicles.features.find(
                                    (vf: any) => String(vf.properties?.id ?? vf.properties?.ID) === curId
                                )
                                if (latestVehicleFeature) {
                                    featureToSelect = latestVehicleFeature
                                    this.selectedFeature = latestVehicleFeature
                                }
                            } else if (this.selectedType === 'SingleDroneStateDS' && this.digitalShadowRaw.map_layers?.drones?.features) {
                                const latestDroneFeature = this.digitalShadowRaw.map_layers.drones.features.find(
                                    (df: any) => String(df.properties?.id ?? df.properties?.ID) === curId
                                )
                                if (latestDroneFeature) {
                                    featureToSelect = latestDroneFeature
                                    this.selectedFeature = latestDroneFeature
                                }
                            } else if (this.selectedType === 'SingleWarningStateDS' && this.digitalShadowRaw.map_layers?.warnings?.features) {
                                const latestWarnFeature = this.digitalShadowRaw.map_layers.warnings.features.find(
                                    (wf: any) => String(wf.properties?.id ?? wf.properties?.ID) === curId
                                )
                                if (latestWarnFeature) {
                                    featureToSelect = latestWarnFeature
                                    this.selectedFeature = latestWarnFeature
                                }
                            }

                            await this.selectObject(this.selectedType, featureToSelect)
                        }
                    }
                } catch (e) {
                    console.error('Error parsing SSE data', e)
                }
            }
        },

        stopStream() {
            if (activeEventSource) {
                activeEventSource.close()
                activeEventSource = null
            }
            this.isStreaming = false
            this.isConnected = false
        },

        /**
         * Interactive Demo Controls: Spawn a heavy goods vehicle on demand at the selected intersection.
         */
        async spawnVehicle(junctionId?: string, direction?: number) {
            try {
                const jctId = junctionId || (
                    this.selectedType === 'SingleExitStateDS'
                        ? (this.selectedFeature?.properties?.id ?? this.selectedFeature?.properties?.ID)
                        : undefined
                )
                const resp = await apiClient.post('/dashboard/control/spawn_vehicle', {
                    junction_id: jctId,
                    direction
                })
                return resp.data
            } catch (error) {
                console.error('Error spawning vehicle:', error)
                return null
            }
        },

        /**
         * Interactive Demo Controls: Trigger a synthetic road warning & UAV dispatch.
         * Uses the currently selected vehicle if one is selected; otherwise picks an active fleet vehicle.
         */
        async triggerWarning(kilometer?: number, direction?: number) {
            try {
                const selectedVehId = this.selectedType === 'SingleVehicleStateDS'
                    ? (this.selectedFeature?.properties?.id ?? this.selectedFeature?.properties?.ID)
                    : undefined
                const resp = await apiClient.post('/dashboard/control/trigger_warning', {
                    vehicle_id: selectedVehId,
                    kilometer,
                    direction
                })
                return resp.data
            } catch (error) {
                console.error('Error triggering warning:', error)
                return null
            }
        },

        /**
         * Interactive Demo Controls: Adjust simulation speed multiplier (1x, 2x, 5x).
         */
        async setSimSpeed(multiplier: number) {
            try {
                const resp = await apiClient.post('/dashboard/control/sim_speed', { multiplier })
                if (resp.data?.sim_speed) {
                    this.simSpeed = resp.data.sim_speed
                }
                return resp.data
            } catch (error) {
                console.error('Error setting simulation speed:', error)
                return null
            }
        },

        toggleTheme() {
            this.theme = this.theme === 'light' ? 'dark' : 'light'
            if (typeof window !== 'undefined') {
                localStorage.setItem('color-scheme', this.theme)
                document.documentElement.classList.toggle('dark', this.theme === 'dark')
                const meta = document.querySelector('meta[name="color-scheme"]')
                if (meta) meta.setAttribute('content', this.theme)
            }
        },

        setCurrentView(view: 'digital-shadow' | 'fiware-status' | 'documentation') {
            this.currentView = view
        },

        async fetchPredictionPlot(state: number) {
            try {
                const response = await apiClient.get('/dashboard/prediction_plot', {
                    params: { state }
                })
                this.predictionPlotData = response.data
            } catch (error) {
                console.error('Error fetching prediction plot:', error)
            }
        },

        async checkFiwareStatus() {
            try {
                const response = await apiClient.get('/dashboard/fiware_status')
                this.fiwareEnabled = Boolean(response.data.enabled)
                this.fiwareConnected = Boolean(response.data.fiware_connected ?? response.data.connected)
                this.brokerBackend = String(response.data.backend || 'native')
                this.brokerDriver = String(response.data.driver || 'In-Memory')
                this.brokerEndpoints = response.data.endpoints || null
                this.brokerServiceGroups = Array.isArray(response.data.service_groups)
                    ? response.data.service_groups
                    : []
                this.fiwareService = String(response.data.fiware_service || 'openiot')
                this.fiwareServicePath = String(response.data.fiware_servicepath || '/')
            } catch (error) {
                console.error('Error checking FIWARE status:', error)
                this.fiwareEnabled = false
                this.fiwareConnected = false
            }
        },

        async fetchFiwareEntities() {
            try {
                const response = await apiClient.get('/dashboard/fiware_entities')
                this.fiwareEntities = response.data
            } catch (error) {
                console.error('Error fetching FIWARE entities:', error)
            }
        },

        async cleanIdleEntities() {
            const now = Date.now()
            const idleIds = this.fiwareEntities
                .filter((e: any) => {
                    const tsRaw = e.TimeInstant ?? (e.updated_at ? e.updated_at * 1000 : null)
                    if (!tsRaw) return true
                    try {
                        const tsMs = new Date(tsRaw).getTime()
                        return Number.isNaN(tsMs) || (now - tsMs) >= 60000
                    } catch { return true }
                })
                .map((e: any) => e.id)

            if (idleIds.length === 0) return { deleted: [], failed: [] }

            try {
                const response = await apiClient.post('/dashboard/fiware_entities/clean_idle', {
                    entity_ids: idleIds
                })
                await this.fetchFiwareEntities()
                return response.data
            } catch (error) {
                console.error('Error cleaning idle FIWARE entities:', error)
                return { deleted: [], failed: idleIds }
            }
        },

        setMapState(center: [number, number], zoom: number) {
            this.mapCenter = center
            this.mapZoom = zoom
        },

        toggleEditorMode() {
            this.isEditorMode = !this.isEditorMode
        },

        setEditorMode(mode: boolean) {
            this.isEditorMode = mode
        },

        async saveScenarioInfrastructure(infrastructure: any) {
            try {
                const response = await apiClient.post('/api/scenarios/save', {
                    scenario_id: 'a14_corridor',
                    infrastructure
                })
                if (response.data?.status === 'success') {
                    this.hasUnsavedEdits = false
                }
                return response.data
            } catch (error) {
                console.error('Error saving scenario infrastructure:', error)
                throw error
            }
        },

        async updateAssetParameters(assetType: string, assetId: string, properties: Record<string, any>) {
            try {
                const response = await apiClient.post('/api/assets/update', {
                    asset_type: assetType,
                    asset_id: assetId,
                    properties
                })
                // Mutate local properties immediately
                if (this.selectedFeature?.properties) {
                    this.selectedFeature.properties = {
                        ...this.selectedFeature.properties,
                        ...properties
                    }
                }
                if (this.selectedData?.properties) {
                    this.selectedData.properties = {
                        ...this.selectedData.properties,
                        ...properties
                    }
                }
                return response.data
            } catch (error) {
                console.error('Error updating asset parameters:', error)
                throw error
            }
        }
    },
})
