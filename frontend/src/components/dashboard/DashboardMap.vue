<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet.markercluster'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'
import { useDashboardStore } from '../../stores/dashboard'
import { createMapCoordSystem, type MapCoordSystem } from '../../utils/mapCoordSystem'
import AssetEditorOverlay from './AssetEditorOverlay.vue'

const mapContainer = ref<HTMLElement | null>(null)
let map: L.Map | null = null
let canvasRenderer: L.Canvas | null = null
let activeCoordSystem: MapCoordSystem = createMapCoordSystem('WGS84')

const store = useDashboardStore()

// Vehicle tracking and continuous 60 FPS kinematic dead-reckoning engine
interface TrackedVehicle {
  id: string;
  marker: L.Marker;
  feature: any;
  truthKm: number;
  currentKm: number;
  startKm: number;
  velocity: number; // km/h (reported standard velocity)
  effectiveVelocity: number; // km/h (current real extrapolated speed)
  nominalVelocity: number; // km/h (baseline cruise speed)
  stationRateKmH?: number; // instantaneous signed rate (km/h) along corridor
  direction: number; // 1 or -1
  endRoute?: number;
  driftCorrectionKmH: number; // smooth, phase-decoupled drift relaxation
  targetStationKm: number; // projected ground-truth position
  lastPacketTime: number; // timestamp ms of packet arrival
  lastPacketKm: number;
  instantaneousSpeedKmH: number; // current real-time scalar speed of the icon (km/h)
  lastSampleTime: number; // timestamp ms of last recorded point in store
  currentLatLng: [number, number];
  prevLatLng?: [number, number];
  prevLatLngTime?: number;
  extrapolationHistory: Array<{
    timestamp: string;
    km: number;
    standardVelocity: number;
    extrapolatedSpeed: number;
    driftKm: number;
  }>;
}

// UAV drone tracking and 60 FPS smooth dead reckoning engine
interface TrackedDrone {
  id: string;
  marker: L.Marker;
  feature: any;
  currentLatLng: [number, number];
  targetLatLng: [number, number];
  bearingDeg: number;
  velocityKmh: number;
  altitudeM: number;
  state: string;
  lastPacketTime: number;
}

const trackedVehicles = new Map<string, TrackedVehicle>()
const vehicleMarkersMap = new Map<string, L.Marker>()
const trackedDrones = new Map<string, TrackedDrone>()
const droneMarkersMap = new Map<string, L.Marker>()
const rsuMarkersMap = new Map<string, L.Marker>()

interface LODConfig {
  hz: number;
  label: string;
  active: boolean;
}

const getLODConfig = (zoom: number): LODConfig => {
  if (zoom >= 16) {
    return { hz: 60, label: 'LOD 0 | 60 FPS (Sub-Meter Kinetic)', active: true }
  } else if (zoom >= 14) {
    return { hz: 30, label: 'LOD 1 | 30 FPS (Urban Arterial)', active: true }
  } else if (zoom >= 12) {
    return { hz: 15, label: 'LOD 2 | 15 FPS (Corridor Tracking)', active: true }
  } else {
    return { hz: 5, label: 'LOD 3 | 5s Truth (Regional Macro)', active: false }
  }
}

const dir1Segments: any[] = []
const dir2Segments: any[] = []

// Fast O(1) lookup maps for static layers so we never call .clearLayers() on 1,215 road segments
let staticLayersRendered = false
let isZoomAnimating = false
const roadSegmentsMap = new Map<string, any>()
const roadSegmentLayersById = new Map<string, L.Path>()
const roadPointLayersById = new Map<string, L.CircleMarker>()
const rsuCoveragePolygonsById = new Map<string, [number, number][]>()

const currentZoomLevel = ref(10)
const currentLODState = ref<LODConfig>(getLODConfig(10))
let animationFrameId: number | null = null
let lastTickTimestamp = 0

// Icon definitions
const getVehicleIcon = (isSelected: boolean) => L.icon({ 
    iconUrl: '/images/icon_auto.svg', 
    iconSize: isSelected ? [54, 54] : [26, 26], 
    iconAnchor: isSelected ? [27, 27] : [13, 13],
    className: isSelected ? 'selected-icon-outline' : ''
})
const getDroneIcon = (isSelected: boolean) => L.icon({ 
    iconUrl: '/images/icon_drone.svg', 
    iconSize: isSelected ? [58, 58] : [30, 30], 
    iconAnchor: isSelected ? [29, 29] : [15, 15],
    className: isSelected ? 'selected-icon-outline' : ''
})
const getRuIcon = (isSelected: boolean) => L.icon({ 
    iconUrl: '/images/icon_roadside_unit.svg', 
    iconSize: isSelected ? [58, 58] : [30, 30], 
    iconAnchor: isSelected ? [29, 29] : [15, 15],
    className: isSelected ? 'selected-icon-outline' : ''
})
const getWarningIcon = (isSelected: boolean, feature?: any) => {
    const props = feature?.properties || {}
    const state = props.State || props.status || 'New'

    // Status-adaptive color scheme (#AF2D37 for New, #f59e0b for Under Inspection, #00AA82 for Inspected)
    let mainColor = '#AF2D37'
    let svgIcon = `<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4m0 4h.01" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`

    if (state === 'Under Inspection') {
        mainColor = '#f59e0b'
        svgIcon = `<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" fill="none"/><path d="M12 7v5l3 3" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>`
    } else if (state === 'Inspected') {
        mainColor = '#00AA82' // Verified Emerald Green
        svgIcon = `<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="${mainColor}22" stroke="currentColor" stroke-width="2"/><path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>`
    }

    const size = isSelected ? 38 : 28
    const half = size / 2

    const html = `
      <div class="relative flex items-center justify-center" style="width:${size}px; height:${size}px;">
        ${state === 'New' ? `<span class="absolute inline-flex h-full w-full rounded-full opacity-65 animate-ping" style="background-color:${mainColor};"></span>` : ''}
        ${state === 'Under Inspection' ? `<span class="absolute inline-flex h-full w-full rounded-full opacity-45 border-2 border-dashed animate-spin" style="border-color:${mainColor};"></span>` : ''}
        <div class="relative flex items-center justify-center rounded-xl shadow-lg border-2 ${isSelected ? 'ring-3 ring-[#5096BE] ring-offset-1 scale-110' : ''}"
             style="width:${size - 4}px; height:${size - 4}px; background-color:#001d3a; border-color:${mainColor}; color:${mainColor}; transition: all 0.2s;">
          <svg viewBox="0 0 24 24" width="${Math.round(size * 0.55)}" height="${Math.round(size * 0.55)}">
            ${svgIcon}
          </svg>
        </div>
      </div>
    `

    return L.divIcon({
        html,
        className: 'custom-warning-marker',
        iconSize: [size, size],
        iconAnchor: [half, half]
    })
}
const getWaterIcon = (isSelected: boolean) => L.icon({
    iconUrl: '/images/icon_water.svg',
    iconSize: isSelected ? [44, 44] : [24, 24],
    iconAnchor: isSelected ? [22, 22] : [12, 12],
    className: isSelected ? 'selected-icon-outline' : ''
})

// Color interpolation: 0 (dark red) to 50 (yellow) to 100 (dark green)
const getRoadColor = (health: number) => {
    let r, g, b = 0
    if (health < 50) {
        const p = health / 50
        r = Math.floor(139 + (255 - 139) * p)
        g = Math.floor(0 + (255 - 0) * p)
    } else {
        const p = (health - 50) / 50
        r = Math.floor(255 + (0 - 255) * p)
        g = Math.floor(255 + (100 - 255) * p)
    }
    return `rgb(${r}, ${g}, ${b})`
}

// Layer Groups
const clusterHighlightGroup = L.layerGroup()
let activeClusterPopup: L.Popup | null = null

const roadClusterGroup = L.markerClusterGroup({
  showCoverageOnHover: false,
  maxClusterRadius: 65,
  disableClusteringAtZoom: 13,
  chunkedLoading: true,
  iconCreateFunction: (cluster) => {
    const childMarkers = cluster.getAllChildMarkers()
    const count = childMarkers.length
    let totalHealth = 0
    childMarkers.forEach(m => {
      const feature = (m as any).feature
      totalHealth += feature?.properties?.state ?? 100
    })
    const avgHealth = Math.round(totalHealth / (count || 1))
    const color = getRoadColor(avgHealth)
    const size = count < 25 ? 38 : count < 80 ? 42 : 46

    return L.divIcon({
      html: `
        <div class="cluster-badge" style="background-color: ${color}; width: ${size}px; height: ${size}px;">
          <span class="cluster-health">${avgHealth}%</span>
          <span class="cluster-sub">${count} seg</span>
        </div>
      `,
      className: 'custom-cluster-icon',
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2]
    })
  }
})

const STRUCTURE_PALETTE: Record<string, string> = {
  RoadStructure_0: '#f59e0b', // Amber — Dresden Urban (Asphalt)
  RoadStructure_1: '#2563eb', // Royal Blue — A4 Motorway (Asphalt)
  RoadStructure_2: '#06b6d4', // Cyan — A14 Motorway (Concrete)
  RoadStructure_3: '#8b5cf6', // Violet — A38 Motorway (Asphalt)
  RoadStructure_4: '#ec4899', // Rose — Leipzig Urban (Asphalt)
}

const getRoadStructureColor = (structId: string, material?: string): string => {
  if (structId in STRUCTURE_PALETTE) return STRUCTURE_PALETTE[structId]
  const fallbackColors = ['#0891b2', '#6366f1', '#ea580c', '#10b981', '#eab308']
  if (material && material.toLowerCase() === 'concrete') return '#0891b2'
  let hash = 0
  for (let i = 0; i < structId.length; i++) {
    hash = (hash * 31 + structId.charCodeAt(i)) >>> 0
  }
  return fallbackColors[hash % fallbackColors.length]
}

const summarizeStructureLayers = (structCfg: any): { totalCm: number; breakdown: string; count: number } => {
  if (!structCfg || typeof structCfg !== 'object') {
    return { totalCm: 0, breakdown: 'Default', count: 0 }
  }
  const layerEntries = Object.entries(structCfg)
    .filter(([k, v]) => k.startsWith('Layer_') && v && typeof v === 'object')
    .sort((a, b) => Number(a[0].split('_')[1] ?? 999) - Number(b[0].split('_')[1] ?? 999))
  if (layerEntries.length === 0) {
    return { totalCm: 0, breakdown: 'Standard', count: 0 }
  }
  const cmList = layerEntries.map(([, v]: [string, any]) => Math.max(1, Math.round(Number(v.Length ?? 0.1) * 100)))
  const totalCm = cmList.reduce((acc, c) => acc + c, 0)
  const loadClass = structCfg.LoadClass ? String(structCfg.LoadClass) : ''
  return {
    totalCm,
    breakdown: `${loadClass ? `${loadClass} • ` : `${cmList.length}L • `}${totalCm} cm (${cmList.join('+')})`,
    count: cmList.length,
  }
}

const showStructureLegend = ref(false)
const structureLegendItems = ref<
  Array<{ id: string; label: string; material: string; color: string; layersSummary: string; count: number }>
>([])

const roadCurvesGroup = L.layerGroup()
const lanePolygonsGroup = L.layerGroup()
const roadSegmentsGroup = L.layerGroup()
const roadStructuresGroup = L.layerGroup() // On-demand overlay colored by Asphalt/Concrete pavement structure
const rsuCoverageGroup = L.layerGroup() // Precomputed Voronoi-clipped RSU service cells
const waterGroup = L.layerGroup()
const spawnGroup = L.layerGroup()
const ruGroup = L.layerGroup()
const embeddedSensorsGroup = L.layerGroup()
const trajectoryGroup = L.layerGroup() // Flightradar24 solid past trajectory + influence zones
const vehiclesGroup = L.layerGroup()
const dronesGroup = L.layerGroup()
const warningsGroup = L.layerGroup()
const v2xLinkGroup = L.layerGroup()

const handleFeatureClick = (type: string, feature: any, ev?: any) => {
  if (ev && ev.originalEvent) {
    L.DomEvent.stopPropagation(ev.originalEvent)
  } else if (ev) {
    L.DomEvent.stopPropagation(ev)
  }
  if (feature) {
    store.selectObject(type, feature)
    if (type === 'SingleRoadPointStateDS' || type === 'SingleRoadSegmentStateDS') {
      const health = feature.properties?.state ?? feature.properties?.State ?? 100
      store.fetchPredictionPlot(health)
    }
  }
}

onMounted(async () => {
  if (mapContainer.value) {
    await store.fetchStaticLayers()
    const crsMode = store.digitalShadowRaw?.coordinate_system?.mode || 'WGS84'
    const isCartesian = crsMode === 'LocalCartesian'
    activeCoordSystem = createMapCoordSystem(crsMode)

    // 60 FPS Fix #1: Use HTML5 Canvas renderer (`preferCanvas: true`) instead of 2,400+ SVG DOM nodes
    canvasRenderer = L.canvas({ padding: 0.5 })
    map = L.map(mapContainer.value, {
      preferCanvas: true,
      renderer: canvasRenderer,
      ...(isCartesian ? { crs: L.CRS.Simple, minZoom: -5 } : {}),
      zoomControl: false,
      zoomAnimation: true,
      fadeAnimation: true,
      markerZoomAnimation: true
    }).setView(isCartesian ? [0, 0] : store.mapCenter, isCartesian ? 1 : store.mapZoom)

    if (isCartesian) {
      const bounds = store.digitalShadowRaw?.coordinate_system?.bounds
      if (Array.isArray(bounds) && bounds.length === 2 && Array.isArray(bounds[0]) && Array.isArray(bounds[1])) {
        const [[xMin, yMin], [xMax, yMax]] = bounds
        map.fitBounds([
          [Number(yMin), Number(xMin)],
          [Number(yMax), Number(xMax)]
        ])
      }
    }

    const baseMaps: Record<string, L.TileLayer> = {}
    if (!isCartesian) {
      // 100% Free, Zero-API-Key Tile Layers (No CARTO watermarks)
      const cleanOsm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        className: 'dtr-clean-tiles',
        attribution: '&copy; OpenStreetMap contributors'
      }).addTo(map)

      const esriLightGray = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 16,
        attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ'
      })

      const osmStandard = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors'
      })

      const esriSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics'
      })

      baseMaps["Architectural Clean (OSM)"] = cleanOsm
      baseMaps["Esri Light Gray Canvas"] = esriLightGray
      baseMaps["OpenStreetMap Standard"] = osmStandard
      baseMaps["Esri Aerial Satellite"] = esriSatellite
    }

    lanePolygonsGroup.addTo(map)
    roadCurvesGroup.addTo(map)
    rsuCoverageGroup.addTo(map)
    roadSegmentsGroup.addTo(map)
    clusterHighlightGroup.addTo(map)
    waterGroup.addTo(map)
    spawnGroup.addTo(map)
    ruGroup.addTo(map)
    embeddedSensorsGroup.addTo(map)
    trajectoryGroup.addTo(map)
    v2xLinkGroup.addTo(map)
    vehiclesGroup.addTo(map)
    dronesGroup.addTo(map)
    warningsGroup.addTo(map)

    const overlays = {
        "Road sections (100–250 m)": roadSegmentsGroup,
        "Road structures (Asphalt / Concrete)": roadStructuresGroup,
        "Highway curves": roadCurvesGroup,
        "Lane polygons (Lanelet2 / OpenDRIVE)": lanePolygonsGroup,
        "Road state points (Clusters)": roadClusterGroup,
        "RSU coverage cells (10 km)": rsuCoverageGroup,
        "Embedded pavement sensors": embeddedSensorsGroup,
        "Water sources": waterGroup,
        "Intersections & Junctions": spawnGroup,
        "Roadside units": ruGroup,
        "Vehicle trajectories": trajectoryGroup,
        "Traffic": vehiclesGroup,
        "V2X Edge Links": v2xLinkGroup,
        "Inspection fleet": dronesGroup,
        "Warnings": warningsGroup
    }
    L.control.layers(baseMaps, overlays).addTo(map)
    L.control.zoom({ position: 'bottomright' }).addTo(map)

    map.on('overlayadd', (e: L.LayersControlEvent) => {
      if (e.layer === roadStructuresGroup) {
        showStructureLegend.value = true
      }
    })
    map.on('overlayremove', (e: L.LayersControlEvent) => {
      if (e.layer === roadStructuresGroup) {
        showStructureLegend.value = false
      }
    })

    // Flightradar24 UX: Clicking on empty map space discards active object selection
    map.on('click', () => {
      if (store.selectedType) {
        store.clearSelection()
      }
    })

    // Cluster hover: exact OSM highway geometry glow + detailed inspection card
    roadClusterGroup.on('clustermouseover', (e: any) => {
      if (isZoomAnimating) return
      clusterHighlightGroup.clearLayers()
      const cluster = e.layer
      const childMarkers = cluster.getAllChildMarkers()
      if (!childMarkers || childMarkers.length === 0 || !map) return

      let totalHealth = 0
      let minHealth = 100
      let maxHealth = 0
      let minKm = Infinity
      let maxKm = -Infinity
      let dir1Count = 0
      let dir2Count = 0
      let dir1Health = 0
      let dir2Health = 0

      const renderedSegIds = new Set<string>()

      childMarkers.forEach((marker: any) => {
        const feature = marker.feature
        const props = feature?.properties || {}
        const health = props.state ?? 100
        totalHealth += health
        if (health < minHealth) minHealth = health
        if (health > maxHealth) maxHealth = health

        const startKm = props.station_start_km ?? props.dist ?? 0
        const endKm = props.station_end_km ?? props.dist ?? 0
        if (startKm < minKm) minKm = startKm
        if (endKm > maxKm) maxKm = endKm

        if (props.direction === 1) {
          dir1Count++
          dir1Health += health
        } else if (props.direction === -1 || props.direction === 2) {
          dir2Count++
          dir2Health += health
        }

        const segId = props.segment_id || props.id
        if (segId && !renderedSegIds.has(segId)) {
          renderedSegIds.add(segId)
          const segFeat = roadSegmentsMap.get(segId)
          if (segFeat && segFeat.geometry?.coordinates) {
            const latlngs = segFeat.geometry.coordinates.map((c: [number, number]) => [c[1], c[0]])

            L.polyline(latlngs, {
              renderer: canvasRenderer || undefined,
              color: '#38bdf8',
              weight: 9,
              opacity: 0.75,
              lineCap: 'round',
              lineJoin: 'round',
              interactive: false
            }).addTo(clusterHighlightGroup)

            L.polyline(latlngs, {
              renderer: canvasRenderer || undefined,
              color: getRoadColor(health),
              weight: 4.5,
              opacity: 1.0,
              lineCap: 'round',
              lineJoin: 'round',
              interactive: false
            }).addTo(clusterHighlightGroup)
          }
        }
      })

      const count = childMarkers.length
      const avgHealth = Math.round(totalHealth / (count || 1))
      const color = getRoadColor(avgHealth)
      const spanKm = (maxKm >= minKm && minKm !== Infinity) ? (maxKm - minKm).toFixed(1) : (count * 0.2).toFixed(1)
      const dir1Avg = dir1Count > 0 ? Math.round(dir1Health / dir1Count) : 100
      const dir2Avg = dir2Count > 0 ? Math.round(dir2Health / dir2Count) : 100

      const popupHtml = `
        <div class="p-3 bg-white text-slate-800 text-xs min-w-[230px]">
          <div class="flex items-center justify-between pb-1.5 mb-2 border-b border-slate-100">
            <div class="flex items-center space-x-1.5">
              <span class="w-2.5 h-2.5 rounded-full inline-block shadow-sm" style="background-color: ${color};"></span>
              <span class="font-bold text-slate-900 text-xs tracking-tight">Aggregated Corridor</span>
            </div>
            <span class="px-2 py-0.5 rounded-full text-[10px] font-black text-white shadow-sm" style="background-color: ${color}; text-shadow: 0 1px 1px rgba(0,0,0,0.4);">
              ${avgHealth}% Avg
            </span>
          </div>
          
          <div class="space-y-1.5 text-[11px]">
            <div class="flex items-center justify-between">
              <span class="text-slate-500 font-medium">Corridor Span:</span>
              <span class="font-semibold text-slate-700">km ${minKm !== Infinity ? minKm.toFixed(1) : '0'} – ${maxKm !== -Infinity ? maxKm.toFixed(1) : '0'}</span>
            </div>

            <div class="flex items-center justify-between">
              <span class="text-slate-500 font-medium">Coverage:</span>
              <span class="font-semibold text-slate-700">${count} sections (${spanKm} km)</span>
            </div>

            <div class="flex items-center justify-between">
              <span class="text-slate-500 font-medium">Condition Range:</span>
              <span class="font-semibold ${minHealth < 50 ? 'text-rose-600 font-bold' : minHealth < 75 ? 'text-amber-600 font-bold' : 'text-emerald-700'}">
                ${minHealth}% (worst) – ${maxHealth}% (best)
              </span>
            </div>

            ${dir1Count > 0 && dir2Count > 0 ? `
            <div class="pt-1.5 mt-1 border-t border-slate-100 grid grid-cols-2 gap-1.5 text-[10px]">
              <div class="bg-slate-50 rounded p-1.5 border border-slate-100">
                <div class="text-slate-400 font-medium truncate">Dresden → Lpz</div>
                <div class="font-bold text-slate-700">${dir1Count} seg <span class="text-[9px] font-semibold text-slate-500">(${dir1Avg}%)</span></div>
              </div>
              <div class="bg-slate-50 rounded p-1.5 border border-slate-100">
                <div class="text-slate-400 font-medium truncate">Lpz → Dresden</div>
                <div class="font-bold text-slate-700">${dir2Count} seg <span class="text-[9px] font-semibold text-slate-500">(${dir2Avg}%)</span></div>
              </div>
            </div>
            ` : ''}
          </div>
          <div class="mt-2 text-[9px] text-center text-slate-400 font-medium border-t border-slate-100 pt-1">
            Click cluster to zoom into individual sections
          </div>
        </div>
      `

      if (activeClusterPopup && map) {
        map.closePopup(activeClusterPopup)
      }
      activeClusterPopup = L.popup({
        closeButton: false,
        autoClose: false,
        closeOnEscapeKey: false,
        closeOnClick: false,
        autoPan: false,
        offset: [0, -22],
        className: 'cluster-hover-popup'
      })
      .setLatLng(cluster.getLatLng())
      .setContent(popupHtml)
      .openOn(map)
    })

    const clearClusterHighlight = () => {
      clusterHighlightGroup.clearLayers()
      if (activeClusterPopup && map) {
        map.closePopup(activeClusterPopup)
        activeClusterPopup = null
      }
    }

    roadClusterGroup.on('clustermouseout', clearClusterHighlight)
    roadClusterGroup.on('clusterclick', clearClusterHighlight)

    // 60 FPS Fix #2: Pause rAF marker extrapolation during Leaflet zoom animation
    map.on('zoomstart', () => {
      isZoomAnimating = true
      clearClusterHighlight()
      stopAnimationLoop()
    })

    map.on('movestart', clearClusterHighlight)

    map.on('moveend', () => {
      if (!map) return
      const center = map.getCenter()
      store.setMapState([center.lat, center.lng], map.getZoom())
    })

    map.on('zoom', () => {
      if (!map) return
      const z = Math.round(map.getZoom())
      currentZoomLevel.value = z
      currentLODState.value = getLODConfig(z)
    })

    map.on('zoomend', () => {
      isZoomAnimating = false
      if (!map) return
      const center = map.getCenter()
      store.setMapState([center.lat, center.lng], map.getZoom())
      checkZoomAndToggleExtrapolation()
    })

    if (typeof ResizeObserver !== 'undefined' && mapContainer.value) {
      mapResizeObserver = new ResizeObserver(() => {
        map?.invalidateSize({ debounceMoveend: true })
      })
      mapResizeObserver.observe(mapContainer.value)
    }

    await store.fetchState()
    checkZoomAndToggleExtrapolation()
  }
})

let mapResizeObserver: ResizeObserver | null = null

onUnmounted(() => {
  if (mapResizeObserver) mapResizeObserver.disconnect()
  stopAnimationLoop()
  trackedVehicles.clear()
  vehicleMarkersMap.clear()
  roadSegmentLayersById.clear()
  roadPointLayersById.clear()
  staticLayersRendered = false
  if (map) {
    map.remove()
    map = null
  }
})

// Extrapolates road coordinates [lat, lng] for a given kilometer and direction along high-res OSM segments
const getRoadLatLngForStation = (targetKm: number, direction: number): [number, number] | null => {
  const segs = direction === 1 ? dir1Segments : dir2Segments
  if (!segs || segs.length === 0) return null

  const minKm = segs[0].properties?.station_start_km ?? 0
  const maxKm = segs[segs.length - 1].properties?.station_end_km ?? 137.8
  const clampedKm = Math.max(minKm, Math.min(maxKm, targetKm))

  const estIdx = Math.min(segs.length - 1, Math.max(0, Math.floor(clampedKm / 0.2)))
  let targetSeg = segs[estIdx]

  if (!targetSeg || clampedKm < (targetSeg.properties?.station_start_km ?? 0) || clampedKm > (targetSeg.properties?.station_end_km ?? 137.8)) {
    const start = Math.max(0, estIdx - 4)
    const end = Math.min(segs.length - 1, estIdx + 4)
    for (let i = start; i <= end; i++) {
      if (segs[i].properties?.station_start_km <= clampedKm && clampedKm <= segs[i].properties?.station_end_km) {
        targetSeg = segs[i]
        break
      }
    }
    if (!targetSeg || clampedKm < targetSeg.properties?.station_start_km || clampedKm > targetSeg.properties?.station_end_km) {
      targetSeg = segs.find(s => s.properties?.station_start_km <= clampedKm && clampedKm <= s.properties?.station_end_km)
    }
  }

  if (!targetSeg) return null

  const startKm = targetSeg.properties?.station_start_km ?? clampedKm
  const endKm = targetSeg.properties?.station_end_km ?? (startKm + 0.2)
  const span = Math.max(0.0001, endKm - startKm)
  const frac = Math.max(0, Math.min(1, (clampedKm - startKm) / span))

  const coords = targetSeg.geometry?.coordinates
  if (!coords || coords.length === 0) return null
  if (coords.length === 1) return [coords[0][1], coords[0][0]]

  // Geodesic cumulative arc-length interpolation eliminates vertex-density speed distortion
  const cumDists: number[] | undefined = (targetSeg as any)._cumDists
  const totalM: number = (targetSeg as any)._totalLenM || (targetSeg.properties?.length_m || 200)

  if (cumDists && cumDists.length === coords.length && totalM > 0) {
    const targetDistM = frac * totalM
    let i0 = 0
    let i1 = coords.length - 1
    for (let i = 0; i < coords.length - 1; i++) {
      if (cumDists[i] <= targetDistM && targetDistM <= cumDists[i + 1]) {
        i0 = i
        i1 = i + 1
        break
      }
    }
    const segSpanM = Math.max(0.001, cumDists[i1] - cumDists[i0])
    const subFrac = Math.max(0, Math.min(1, (targetDistM - cumDists[i0]) / segSpanM))
    const c0 = coords[i0]
    const c1 = coords[i1]
    const lat = c0[1] + (c1[1] - c0[1]) * subFrac
    const lng = c0[0] + (c1[0] - c0[0]) * subFrac
    return [lat, lng]
  }

  const floatIdx = frac * (coords.length - 1)
  const i0 = Math.floor(floatIdx)
  const i1 = Math.min(coords.length - 1, i0 + 1)
  const subFrac = floatIdx - i0

  const c0 = coords[i0]
  const c1 = coords[i1]
  const lng = c0[0] + (c1[0] - c0[0]) * subFrac
  const lat = c0[1] + (c1[1] - c0[1]) * subFrac

  return [lat, lng]
}

/**
 * One-time initialization calculation of realistic non-overlapping RSU coverage areas:
 * Computes the bounded Voronoi cell for each RSU within its 10 km service range
 * (all points within 10 km that are closer to this RSU than to any other RSU).
 */
const computeRsuCoverageCellsOnce = (ruFeatures: any[]) => {
  if (!Array.isArray(ruFeatures) || ruFeatures.length === 0) return
  rsuCoveragePolygonsById.clear()
  rsuCoverageGroup.clearLayers()

  const defaultRangeM = activeCoordSystem.mode === 'LocalCartesian' ? 250 : 10000
  const NUM_RAYS = 90 // 4-degree angular resolution for crisp bisector edges

  const rsuList = ruFeatures
    .filter(f => Array.isArray(f.geometry?.coordinates) && f.geometry.coordinates.length >= 2)
    .map(f => ({
      id: String(f.properties?.id ?? ''),
      name: String(f.properties?.name ?? 'RSU'),
      town: String(f.properties?.town ?? ''),
      km: Number(f.properties?.ClosestPoint ?? f.properties?.station_km ?? 0),
      rangeM: f.properties?.coverage_radius_km != null ? Number(f.properties.coverage_radius_km) * 1000 : defaultRangeM,
      lng: Number(f.geometry.coordinates[0]),
      lat: Number(f.geometry.coordinates[1]),
      feature: f
    }))

  for (let i = 0; i < rsuList.length; i++) {
    const cur = rsuList[i]
    const { mPerX, mPerY } = activeCoordSystem.metersPerAxis(cur.lat)
    const maxRangeM = Math.max(50, cur.rangeM)

    // Precompute relative metric vectors (dx, dy) to all neighboring RSUs within 2 * maxRangeM
    const neighbors: { dx: number; dy: number; distSq: number }[] = []
    for (let j = 0; j < rsuList.length; j++) {
      if (i === j) continue
      const other = rsuList[j]
      const dx = (other.lng - cur.lng) * mPerX
      const dy = (other.lat - cur.lat) * mPerY
      const distSq = dx * dx + dy * dy
      if (distSq <= (2 * maxRangeM) * (2 * maxRangeM)) {
        neighbors.push({ dx, dy, distSq })
      }
    }

    const polyLatLngs: [number, number][] = []
    for (let k = 0; k < NUM_RAYS; k++) {
      const theta = (2 * Math.PI * k) / NUM_RAYS
      const ux = Math.cos(theta)
      const uy = Math.sin(theta)
      let r = maxRangeM

      for (const nb of neighbors) {
        const proj = nb.dx * ux + nb.dy * uy
        if (proj > 1e-3) {
          // Distance along ray (ux, uy) to perpendicular bisector between cur and nb
          const rBisect = nb.distSq / (2.0 * proj)
          if (rBisect < r) {
            r = rBisect
          }
        }
      }

      const ptLat = cur.lat + (r * uy) / mPerY
      const ptLng = cur.lng + (r * ux) / mPerX
      polyLatLngs.push([ptLat, ptLng])
    }

    rsuCoveragePolygonsById.set(cur.id, polyLatLngs)

    // Render ambient V2X cellular coverage boundary on the map
    L.polygon(polyLatLngs, {
      renderer: canvasRenderer || undefined,
      color: '#5096BE',
      weight: 1.2,
      dashArray: '4, 6',
      opacity: 0.45,
      fillColor: '#5096BE',
      fillOpacity: 0.035,
      interactive: false
    }).addTo(rsuCoverageGroup)
  }
}

/**
 * Renders the Flightradar24-style solid colored past trajectory trail behind the selected vehicle
 * (strictly skipping any dashed future route, per user specification), or renders contextual
 * radius/flight-path overlays for selected Drones, Water Sources, and RSUs.
 */
const updateSelectionTrajectoryAndContext = () => {
  if (!map) return
  trajectoryGroup.clearLayers()

  const selType = store.selectedType
  const selFeature = store.selectedFeature
  if (!selType || !selFeature) return

  // 1. Selected Vehicle: Solid Colored Past Trajectory Trail along the highway
  if (selType === 'SingleVehicleStateDS') {
    const id = String(selFeature.properties?.id ?? selFeature.properties?.ID ?? '')
    const tracked = trackedVehicles.get(id)
    const props = selFeature.properties || {}
    const dir = tracked?.direction ?? Number(props.Direction ?? 1)
    const curKm = tracked?.currentKm ?? Number(props.Kilometer ?? props.LastPosition ?? 0)
    const startKm = tracked?.startKm ?? Number(props.StartRoute ?? curKm)

    const trailPoints: [number, number][] = []
    const distSpan = Math.abs(curKm - startKm)

    if (distSpan > 0.02 && (dir1Segments.length > 0 || dir2Segments.length > 0)) {
      const stepKm = 0.15
      const steps = Math.min(400, Math.max(2, Math.ceil(distSpan / stepKm)))
      for (let i = 0; i <= steps; i++) {
        const sKm = startKm + ((curKm - startKm) * i) / steps
        const pt = getRoadLatLngForStation(sKm, dir)
        if (pt) trailPoints.push(pt)
      }
    } else if (Array.isArray(props.Trajectory) && props.Trajectory.length > 1) {
      for (const t of props.Trajectory) {
        if (t.lat != null && t.lon != null) {
          trailPoints.push([Number(t.lat), Number(t.lon)])
        }
      }
    }

    if (tracked?.currentLatLng) {
      trailPoints.push(tracked.currentLatLng)
    }

    if (trailPoints.length >= 2) {
      // Dark slate outer casing so the trajectory pops sharply against green road segments
      L.polyline(trailPoints, {
        renderer: canvasRenderer || undefined,
        color: '#0f172a',
        weight: 9,
        opacity: 0.75,
        lineCap: 'round',
        lineJoin: 'round',
        interactive: false
      }).addTo(trajectoryGroup)

      // Solid vivid Flightradar24 past trajectory ribbon (NO dashed future route)
      L.polyline(trailPoints, {
        renderer: canvasRenderer || undefined,
        color: '#06b6d4',
        weight: 5,
        opacity: 1.0,
        lineCap: 'round',
        lineJoin: 'round',
        interactive: false
      }).addTo(trajectoryGroup)

      // High-luminance inner core
      L.polyline(trailPoints, {
        renderer: canvasRenderer || undefined,
        color: '#a5f3fc',
        weight: 2,
        opacity: 0.95,
        lineCap: 'round',
        lineJoin: 'round',
        interactive: false
      }).addTo(trajectoryGroup)

      // Origin marker dot at start of trajectory
      const originPt = trailPoints[0]
      L.circleMarker(originPt, {
        renderer: canvasRenderer || undefined,
        radius: 6,
        fillColor: '#06b6d4',
        color: '#0f172a',
        weight: 2.5,
        fillOpacity: 1,
        interactive: false
      }).addTo(trajectoryGroup)
    }
  }
  // 2. Selected Water Source: 5,000 m Hydrological Subgrade Cooling Zone
  else if (selType === 'SingleWaterStateDS') {
    const coords = selFeature.geometry?.coordinates
    if (Array.isArray(coords) && coords.length >= 2) {
      const latlng: [number, number] = [coords[1], coords[0]]
      const radiusM = Number(selFeature.properties?.influence_radius_m || 5000)
      L.circle(latlng, {
        renderer: canvasRenderer || undefined,
        radius: radiusM,
        color: '#06b6d4',
        weight: 2,
        dashArray: '6, 6',
        fillColor: '#06b6d4',
        fillOpacity: 0.12,
        interactive: false
      }).addTo(trajectoryGroup)
    }
  }
  // 3. Selected RSU: Precomputed 10 km Voronoi-Clipped V2X Cell + Beams to Cell Vehicles
  else if (selType === 'SingleRoadsideUnitsStateDS') {
    const coords = selFeature.geometry?.coordinates
    if (Array.isArray(coords) && coords.length >= 2) {
      const rsuLatLng: [number, number] = [coords[1], coords[0]]
      const rsuId = String(selFeature.properties?.id ?? '')
      const voronoiPoly = rsuCoveragePolygonsById.get(rsuId)

      if (voronoiPoly && voronoiPoly.length >= 3) {
        L.polygon(voronoiPoly, {
          renderer: canvasRenderer || undefined,
          color: '#a855f7',
          weight: 2.2,
          dashArray: '6, 6',
          fillColor: '#a855f7',
          fillOpacity: 0.12,
          interactive: false
        }).addTo(trajectoryGroup)
      } else {
        L.circle(rsuLatLng, {
          renderer: canvasRenderer || undefined,
          radius: 10000,
          color: '#a855f7',
          weight: 2,
          dashArray: '6, 8',
          fillColor: '#a855f7',
          fillOpacity: 0.08,
          interactive: false
        }).addTo(trajectoryGroup)
      }

      // Draw beams to vehicles connected to this RSU
      for (const tv of trackedVehicles.values()) {
        const vRsu = String(tv.feature?.properties?.RoadsideUnit ?? tv.feature?.properties?.State?.RoadsideUnit ?? '')
        if (vRsu === rsuId && tv.currentLatLng) {
          L.polyline([rsuLatLng, tv.currentLatLng], {
            renderer: canvasRenderer || undefined,
            color: '#c084fc',
            weight: 2.5,
            dashArray: '6, 6',
            opacity: 0.85,
            interactive: false
          }).addTo(trajectoryGroup)
        }
      }
    }
  }
  // 4. Selected Drone: Safe side-corridor flight trail in visible dark blue (#00305E) with cyan dashed centerline
  else if (selType === 'SingleDroneStateDS') {
    const props = selFeature.properties || {}
    const trail = props.FlightTrail
    if (Array.isArray(trail) && trail.length >= 2) {
      const latlngs: [number, number][] = trail.map((pt: [number, number]) => [pt[1], pt[0]])
      // Outer high-contrast dark blue casing
      L.polyline(latlngs, {
        renderer: canvasRenderer || undefined,
        color: '#00305E',
        weight: 5,
        opacity: 0.95,
        interactive: false
      }).addTo(trajectoryGroup)
      // Inner cyan dashed guidance core
      L.polyline(latlngs, {
        renderer: canvasRenderer || undefined,
        color: '#5096BE',
        weight: 2,
        dashArray: '6, 6',
        opacity: 0.9,
        interactive: false
      }).addTo(trajectoryGroup)
    }
  }
}

// Continuous 60 FPS kinematic vehicle dead-reckoning engine (scaled with simulation speed multiplier)
const stepVehicleExtrapolations = (_dtSec: number, simDtSec: number, _simMultiplier: number) => {
  if (store.isEditorMode) return
  if (!map || isZoomAnimating || trackedVehicles.size === 0) return

  let selectedVehicleMoved = false
  const selectedId = store.selectedFeature?.properties?.id
  const now = performance.now()
  let cachedNowTs: string | null = null

  for (const [id, v] of trackedVehicles.entries()) {
    const nominalV = v.nominalVelocity != null ? v.nominalVelocity : (v.velocity || 88.0)
    const driftAdj = v.driftCorrectionKmH || 0

    // Vehicle's instantaneous target speed: individual nominal speed + uncoupled gentle drift relaxation
    // Lower bound allows 0.0 km/h (for urban traffic lights and jams)
    const targetSpeedKmH = Math.max(0.0, Math.min(130.0, nominalV + driftAdj))

    // Smooth inertia limiter (heavy lorry inertia: max 5.0 km/h per second of simulation time)
    const curSpeed = v.instantaneousSpeedKmH != null ? v.instantaneousSpeedKmH : nominalV
    const maxSpeedStep = 5.0 * simDtSec
    let newSpeed = curSpeed
    if (targetSpeedKmH > curSpeed) {
      newSpeed = Math.min(targetSpeedKmH, curSpeed + maxSpeedStep)
    } else if (targetSpeedKmH < curSpeed) {
      newSpeed = Math.max(targetSpeedKmH, curSpeed - maxSpeedStep)
    }

    v.instantaneousSpeedKmH = Math.round(newSpeed * 10) / 10
    v.effectiveVelocity = v.instantaneousSpeedKmH

    // 4. Advance station along corridor scaled with simulation speed multiplier (eliminates teleportation jumps)
    const rateKmH = v.direction * newSpeed
    v.stationRateKmH = rateKmH
    const stepKm = (rateKmH / 3600.0) * simDtSec
    v.currentKm += stepKm

    if (v.endRoute != null) {
      if (v.direction === 1 && v.currentKm > v.endRoute) v.currentKm = v.endRoute
      if (v.direction === -1 && v.currentKm < v.endRoute) v.currentKm = v.endRoute
    }

    // 5. Update marker position via arc-length geodesic interpolation
    const newLatLng = getRoadLatLngForStation(v.currentKm, v.direction)
    if (newLatLng) {
      v.prevLatLng = v.currentLatLng
      v.prevLatLngTime = now
      v.currentLatLng = newLatLng
      v.marker.setLatLng(newLatLng)
      if (selectedId && String(selectedId) === id) {
        selectedVehicleMoved = true
        if (store.followVehicle) {
          map.panTo(newLatLng, { animate: false })
        }
      }
    }

    // Sync live extrapolated speed to feature properties
    if (v.feature?.properties) {
      v.feature.properties.ExtrapolatedVelocity = v.instantaneousSpeedKmH
    }

    // 6. High-resolution telemetry sampling (every ~700ms) for real-time FAST vs SLOW visualization
    if (!v.lastSampleTime || (now - v.lastSampleTime) >= 700) {
      v.lastSampleTime = now
      if (!cachedNowTs) {
        cachedNowTs = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      }
      const record = {
        timestamp: cachedNowTs,
        km: Number(v.currentKm.toFixed(3)),
        standardVelocity: Number(nominalV.toFixed(1)),
        extrapolatedSpeed: v.instantaneousSpeedKmH,
        driftKm: Number((v.targetStationKm - v.currentKm).toFixed(3))
      }
      if (!v.extrapolationHistory) v.extrapolationHistory = []
      v.extrapolationHistory.push(record)
      if (v.extrapolationHistory.length > 80) v.extrapolationHistory.shift()
      if (selectedId && String(selectedId) === id) {
        store.recordVehicleExtrapolationPoint(id, record)
      }
    }
  }

  if (selectedVehicleMoved) {
    updateV2XLink()
    updateSelectionTrajectoryAndContext()
  }
}

// 60 FPS smooth dead reckoning extrapolation for active UAV inspection drones
const stepDroneExtrapolations = (_dtSec: number, simDtSec: number) => {
  if (!map || isZoomAnimating || trackedDrones.size === 0) return

  for (const [, d] of trackedDrones.entries()) {
    if (d.state === 'CruisingToward' || d.state === 'CruisingBack') {
      const cur = d.currentLatLng
      const tgt = d.targetLatLng
      const speedMps = Math.max(12.0, (d.velocityKmh * 1000.0) / 3600.0)
      const nextPos = activeCoordSystem.stepToward(cur, tgt, speedMps * simDtSec)
      if (nextPos !== cur) {
        d.currentLatLng = nextPos
        d.marker.setLatLng(d.currentLatLng)

        const selectedId = store.selectedFeature?.properties?.id
        if (selectedId && String(selectedId) === d.id && store.followVehicle) {
          map.panTo(d.currentLatLng, { animate: false })
        }
      }
    }
  }
}

const animationLoop = (timestamp: number) => {
  if (!map || isZoomAnimating) return

  const elapsedMs = timestamp - lastTickTimestamp
  if (elapsedMs >= 14) {
    const dtSec = Math.min(0.12, elapsedMs / 1000)
    lastTickTimestamp = timestamp
    const simMultiplier = Math.max(0.25, Number(store.simSpeed) || 1.0)
    const simDtSec = dtSec * simMultiplier
    stepVehicleExtrapolations(dtSec, simDtSec, simMultiplier)
    stepDroneExtrapolations(dtSec, simDtSec)
  }

  animationFrameId = requestAnimationFrame(animationLoop)
}

const startAnimationLoop = () => {
  if (animationFrameId != null || isZoomAnimating) return
  lastTickTimestamp = performance.now()
  animationFrameId = requestAnimationFrame(animationLoop)
}

const stopAnimationLoop = () => {
  if (animationFrameId != null) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
}

const checkZoomAndToggleExtrapolation = () => {
  if (!map || isZoomAnimating) return
  const zoom = map.getZoom()
  currentZoomLevel.value = zoom
  currentLODState.value = getLODConfig(zoom)

  startAnimationLoop()
  updateV2XLink()
  updateSelectionTrajectoryAndContext()
}

const syncVehicleLayers = (vehiclesGeoJson: any) => {
  if (!vehiclesGeoJson || !Array.isArray(vehiclesGeoJson.features)) {
    for (const marker of vehicleMarkersMap.values()) {
      marker.remove()
    }
    vehicleMarkersMap.clear()
    trackedVehicles.clear()
    return
  }

  const currentIds = new Set<string>()
  const selectedId = store.selectedFeature?.properties?.id
  const now = performance.now()

  for (const feature of vehiclesGeoJson.features) {
    const props = feature.properties || {}
    const id = String(props.id ?? props.ID ?? '')
    if (!id) continue

    currentIds.add(id)
    const isSelected = !!selectedId && id === String(selectedId)

    const rawCoords = feature.geometry?.coordinates
    const rawLatLng: [number, number] = (Array.isArray(rawCoords) && rawCoords.length >= 2)
      ? [rawCoords[1], rawCoords[0]]
      : [0, 0]

    const km = Number(props.Kilometer ?? props.LastPosition ?? props.dist ?? 0)
    const startKm = Number(props.StartRoute ?? km)
    const vel = Number(props.Velocity ?? 90)
    const dir = Number(props.Direction ?? props.State?.Direction ?? 1)
    const endRoute = props.EndRoute != null ? Number(props.EndRoute) : undefined
    const dirLabel = dir === 1 ? 'Dresden → Leipzig' : 'Leipzig → Dresden'
    const originName = props.OriginName || 'Corridor Entry'
    const destName = props.DestinationName || 'Corridor Exit'

    const popupHtml = `
      <div class="p-2 text-xs min-w-[195px]">
        <div class="font-bold text-slate-900 border-b pb-1 mb-1.5 flex items-center justify-between">
          <span>HGV #${id.slice(-4)}</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 font-semibold">${vel.toFixed(0)} km/h</span>
        </div>
        <div class="text-slate-600 space-y-0.5 text-[11px]">
          <div>Route: <span class="font-semibold text-slate-800">${originName} → ${destName}</span></div>
          <div>Direction: <span class="font-medium text-slate-800">${dirLabel}</span></div>
          <div>Station: <span class="font-medium text-slate-800">km ${km.toFixed(2)}</span></div>
        </div>
      </div>
    `

    const truthLatLng = getRoadLatLngForStation(km, dir) || rawLatLng

    if (vehicleMarkersMap.has(id)) {
      const marker = vehicleMarkersMap.get(id)!
      ;(marker as any).feature = feature
      marker.setPopupContent(popupHtml)

      const tracked = trackedVehicles.get(id)
      if (tracked) {
        const simSpeed = Math.max(0.5, Number(store.simSpeed) || 1.0)
        const rawDriftKm = km - tracked.currentKm
        const driftThreshold = 0.35 * Math.max(1.0, simSpeed * 0.8)

        if (Math.abs(rawDriftKm) > driftThreshold || tracked.currentKm <= 0) {
          tracked.currentKm = km
          tracked.nominalVelocity = vel
          tracked.instantaneousSpeedKmH = vel
          tracked.stationRateKmH = dir * vel
          tracked.driftCorrectionKmH = 0
          marker.setLatLng(truthLatLng)
          tracked.currentLatLng = truthLatLng
        } else {
          // Individual relaxation time constant tau_i scaled with simulation speed
          const numId = Math.abs(parseInt(id.replace(/\D/g, '') || '0', 10))
          const tau = (4.0 + (numId % 5) * 0.4) / simSpeed
          const longitudinalDrift = dir * rawDriftKm
          const rateCorr = (longitudinalDrift / Math.max(0.5, tau)) * 3600
          // Bound drift correction proportional to simulation speed
          const maxCorr = 3.0 * simSpeed
          tracked.driftCorrectionKmH = Math.max(-maxCorr, Math.min(maxCorr, rateCorr))
        }

        tracked.truthKm = km
        tracked.lastPacketKm = km
        tracked.lastPacketTime = now
        tracked.targetStationKm = km
        tracked.nominalVelocity = vel
        tracked.velocity = vel
        tracked.direction = dir
        tracked.endRoute = endRoute
        tracked.feature = feature
      }
    } else {
      const marker = L.marker(truthLatLng, {
        icon: getVehicleIcon(isSelected),
        riseOnHover: true
      })
      ;(marker as any).feature = feature
      marker.bindPopup(popupHtml)
      marker.bindTooltip(`<b>HGV #${id.slice(-4)}</b> — ${vel.toFixed(0)} km/h<br/><span class="text-[10px] text-blue-600">${originName} → ${destName}</span>`, { sticky: true })
      marker.on('click', (ev) => handleFeatureClick('SingleVehicleStateDS', (marker as any).feature, ev))
      marker.addTo(vehiclesGroup)

      const initialExtrapSpeed = Math.round(vel * 10) / 10
      const nowTs = new Date()
      const seededHistory: Array<{
        timestamp: string;
        km: number;
        standardVelocity: number;
        extrapolatedSpeed: number;
        driftKm: number;
      }> = []

      // Generate 16 past seconds of telemetry with INDIVIDUAL vehicle phase
      const numId = Math.abs(parseInt(id.replace(/\D/g, '') || '0', 10))
      const vehPhase = (numId * 17.3) % 20
      for (let i = 16; i >= 0; i--) {
        const ptTime = new Date(nowTs.getTime() - i * 1000)
        const ptTs = ptTime.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
        const ptKm = Number((km - (dir * (vel / 3600) * i)).toFixed(3))
        // Independent wave based on this specific vehicle's id phase
        const wave = Math.sin(((i + vehPhase) / 4.0) * Math.PI)
        const extrap = Math.max(50.0, Math.min(125.0, vel + (wave > 0 ? wave * 2.5 : wave * 1.8)))
        seededHistory.push({
          timestamp: ptTs,
          km: ptKm,
          standardVelocity: vel,
          extrapolatedSpeed: Math.round(extrap * 10) / 10,
          driftKm: Number((wave * 0.003).toFixed(3))
        })
      }

      for (const pt of seededHistory) {
        store.recordVehicleExtrapolationPoint(id, pt)
      }

      vehicleMarkersMap.set(id, marker)
      trackedVehicles.set(id, {
        id,
        marker,
        feature,
        truthKm: km,
        currentKm: km,
        startKm,
        velocity: vel,
        nominalVelocity: vel,
        effectiveVelocity: initialExtrapSpeed,
        instantaneousSpeedKmH: initialExtrapSpeed,
        stationRateKmH: dir * vel,
        direction: dir,
        endRoute,
        driftCorrectionKmH: 0,
        targetStationKm: km,
        lastPacketTime: now,
        lastPacketKm: km,
        lastSampleTime: now,
        currentLatLng: truthLatLng,
        extrapolationHistory: seededHistory
      })
    }
  }

  for (const [id, marker] of vehicleMarkersMap.entries()) {
    if (!currentIds.has(id)) {
      marker.remove()
      vehicleMarkersMap.delete(id)
      trackedVehicles.delete(id)
    }
  }

  checkZoomAndToggleExtrapolation()
}

const syncDroneLayers = (dronesGeoJson: any) => {
  if (!dronesGeoJson || !Array.isArray(dronesGeoJson.features)) {
    for (const marker of droneMarkersMap.values()) {
      marker.remove()
    }
    droneMarkersMap.clear()
    trackedDrones.clear()
    return
  }

  const currentIds = new Set<string>()
  const selectedId = store.selectedFeature?.properties?.id
  const now = performance.now()

  for (const feature of dronesGeoJson.features) {
    const props = feature.properties || {}
    const id = String(props.id ?? feature.id ?? '')
    if (!id) continue

    currentIds.add(id)
    const isSelected = !!selectedId && id === String(selectedId)

    const rawCoords = feature.geometry?.coordinates
    const rawLatLng: [number, number] = (Array.isArray(rawCoords) && rawCoords.length >= 2)
      ? [rawCoords[1], rawCoords[0]]
      : [0, 0]

    let targetLatLng: [number, number] = rawLatLng
    if (props.NextWaypoint && Array.isArray(props.NextWaypoint) && props.NextWaypoint.length >= 2) {
      targetLatLng = [props.NextWaypoint[1], props.NextWaypoint[0]]
    } else if (props.State === 'CruisingBack' && props.HomeCoords && Array.isArray(props.HomeCoords) && props.HomeCoords.length >= 2) {
      targetLatLng = [props.HomeCoords[1], props.HomeCoords[0]]
    } else if (props.TargetCoords && Array.isArray(props.TargetCoords) && props.TargetCoords.length >= 2) {
      targetLatLng = [props.TargetCoords[1], props.TargetCoords[0]]
    }

    const tooltipContent =
      `<b>UAV #${props.id}</b> — ${props.State || 'In-Flight'}<br/>` +
      `<span class="text-xs font-semibold text-[#00305E] dark:text-[#8ecae6]">Alt: ${Number(props.Altitude || 0).toFixed(1)}m | Speed: ${Number(props.Velocity || 0).toFixed(0)} km/h | Battery: ${Number(props.BatteryPct || 100).toFixed(0)}%</span>`

    if (droneMarkersMap.has(id)) {
      const marker = droneMarkersMap.get(id)!
      ;(marker as any).feature = feature
      marker.setTooltipContent(tooltipContent)

      const tracked = trackedDrones.get(id)
      if (tracked) {
        tracked.feature = feature
        tracked.state = props.State || 'Idle'
        tracked.velocityKmh = Number(props.Velocity || 0)
        tracked.altitudeM = Number(props.Altitude || 0)
        tracked.bearingDeg = Number(props.BearingDeg || 0)
        tracked.targetLatLng = targetLatLng
        tracked.lastPacketTime = now

        const dLat = Math.abs(rawLatLng[0] - tracked.currentLatLng[0])
        const dLng = Math.abs(rawLatLng[1] - tracked.currentLatLng[1])
        if (!currentLODState.value.active || dLat > 0.0008 || dLng > 0.0008) {
          tracked.currentLatLng = rawLatLng
          marker.setLatLng(rawLatLng)
        }
      }
    } else {
      const marker = L.marker(rawLatLng, {
        icon: getDroneIcon(isSelected),
        riseOnHover: true
      })
      ;(marker as any).feature = feature
      marker.bindTooltip(tooltipContent, { sticky: true })
      marker.on('click', (ev) => handleFeatureClick('SingleDroneStateDS', (marker as any).feature, ev))
      marker.addTo(dronesGroup)

      droneMarkersMap.set(id, marker)
      trackedDrones.set(id, {
        id,
        marker,
        feature,
        currentLatLng: rawLatLng,
        targetLatLng,
        bearingDeg: Number(props.BearingDeg || 0),
        velocityKmh: Number(props.Velocity || 0),
        altitudeM: Number(props.Altitude || 0),
        state: props.State || 'Idle',
        lastPacketTime: now
      })
    }
  }

  for (const [id, marker] of droneMarkersMap.entries()) {
    if (!currentIds.has(id)) {
      marker.remove()
      droneMarkersMap.delete(id)
      trackedDrones.delete(id)
    }
  }
}

/**
 * 60 FPS Fix #3: Render static highway geometry (`road_curves`, `road_segments`,
 * `roadClusterGroup`, `water`, `spawn`, `ru`) ONCE and index by ID for O(1) style updates.
 */
const renderStaticLayersOnce = (layers: any) => {
  if (staticLayersRendered || !layers) return
  const selectedId = store.selectedFeature?.properties?.id

  // 1. Highway Curves
  if (layers.road_curves) {
    roadCurvesGroup.clearLayers()
    L.geoJSON(layers.road_curves, {
      style: (feature) => {
        const isCenterline = feature?.properties?.id === 'corridor_dresden_leipzig'
        const isDir1 = feature?.properties?.direction === 1
        if (isCenterline) {
          return {
            color: '#64748b',
            weight: 2,
            opacity: 0.35,
            dashArray: '5, 5'
          }
        }
        return {
          color: isDir1 ? '#0284c7' : '#0369a1',
          weight: 5,
          opacity: 0.7,
          lineCap: 'round',
          lineJoin: 'round'
        }
      },
      onEachFeature: (feature, layer) => {
        const props = feature.properties || {}
        const dirInfo = props.direction === 1 ? 'Direction 1: Dresden → Leipzig' : props.direction === -1 ? 'Direction 2: Leipzig → Dresden' : 'Centerline'
        layer.bindTooltip(`<b>${props.name || 'Highway'}</b><br/><span class="text-xs text-blue-500 font-semibold">${dirInfo}</span><br/>Length: ${props.length_km ? props.length_km + ' km' : ''}`, { sticky: true })
      }
    }).addTo(roadCurvesGroup)
  }

  // 2. Road Sections (100-250 m)
  if (layers.road_segments) {
    roadSegmentsGroup.clearLayers()
    roadSegmentsMap.clear()
    roadSegmentLayersById.clear()
    dir1Segments.length = 0
    dir2Segments.length = 0

    if (Array.isArray(layers.road_segments.features)) {
      for (const f of layers.road_segments.features) {
        if (f.properties?.id) roadSegmentsMap.set(String(f.properties.id), f)
        if (f.properties?.point_id != null) roadSegmentsMap.set(String(f.properties.point_id), f)
        if (f.properties?.direction === 1) {
          dir1Segments.push(f)
        } else if (f.properties?.direction === -1 || f.properties?.direction === 2) {
          dir2Segments.push(f)
        }

        // Precompute cumulative metric arc-length using active CRS (WGS84 or LocalCartesian)
        const coords = f.geometry?.coordinates
        if (Array.isArray(coords) && coords.length > 1) {
          const { cumDists, totalLenM } = activeCoordSystem.computePolylineCumDists(coords)
          ;(f as any)._cumDists = cumDists
          ;(f as any)._totalLenM = totalLenM > 0 ? totalLenM : (f.properties?.length_m || 200)
        }
      }
      dir1Segments.sort((a, b) => (a.properties?.station_start_km ?? 0) - (b.properties?.station_start_km ?? 0))
      dir2Segments.sort((a, b) => (a.properties?.station_start_km ?? 0) - (b.properties?.station_start_km ?? 0))
    }

    L.geoJSON(layers.road_segments, {
      style: (feature) => {
        const health = feature?.properties?.state ?? 100
        const color = getRoadColor(health)
        const isSelected = !!selectedId && feature?.properties?.id === selectedId
        return {
          color: isSelected ? '#fbbf24' : color,
          weight: isSelected ? 8 : 4.5,
          opacity: isSelected ? 1 : 0.85,
          lineCap: 'round',
          lineJoin: 'round'
        }
      },
      onEachFeature: (feature, layer: any) => {
        const props = feature.properties || {}
        if (props.id != null) roadSegmentLayersById.set(String(props.id), layer)
        if (props.point_id != null) roadSegmentLayersById.set(String(props.point_id), layer)

        const startKm = props.station_start_km != null ? props.station_start_km.toFixed(2) : '?'
        const endKm = props.station_end_km != null ? props.station_end_km.toFixed(2) : '?'
        const dirLabel = props.carriageway || (props.direction === 1 ? 'Dresden → Leipzig' : 'Leipzig → Dresden')
        layer.bindTooltip(
          `<b>${props.name || props.id}</b><br/>` +
          `<span class="text-xs text-blue-600 font-semibold">${dirLabel}</span><br/>` +
          `Station: <b>km ${startKm} – ${endKm}</b> (${props.length_m || 200} m)<br/>` +
          `Health: <b>${props.state}%</b> | Road: ${props.road_name || props.road} (${props.lanes || 2} lanes)`,
          { sticky: true }
        )
        layer.on('click', (ev: any) => {
          handleFeatureClick('SingleRoadSegmentStateDS', feature, ev)
        })
      }
    }).addTo(roadSegmentsGroup)

    // 2b. Road Structures Overlay (colored by Asphalt vs. Concrete RStO 12 stack)
    roadStructuresGroup.clearLayers()
    const roadCfgMap: Record<string, any> = layers.road_config && typeof layers.road_config === 'object' ? layers.road_config : {}
    const legendAcc: Record<
      string,
      { id: string; label: string; material: string; color: string; layersSummary: string; count: number }
    > = {}

    L.geoJSON(layers.road_segments, {
      style: (feature) => {
        const props = feature?.properties || {}
        const structId = String(props.RoadStructure || props.road || 'RoadStructure_1')
        const structCfg = roadCfgMap[structId]
        const mat = String(
          props.RoadMaterial ||
            (structCfg?.RoadType ? Object.keys(structCfg.RoadType)[0] : 'Asphalt')
        )
        const isSelected = !!selectedId && props.id === selectedId
        return {
          color: isSelected ? '#fbbf24' : getRoadStructureColor(structId, mat),
          weight: isSelected ? 9 : 6,
          opacity: isSelected ? 1 : 0.92,
          lineCap: 'round',
          lineJoin: 'round'
        }
      },
      onEachFeature: (feature, layer: any) => {
        const props = feature.properties || {}
        const structId = String(props.RoadStructure || props.road || 'RoadStructure_1')
        const structCfg = roadCfgMap[structId]
        const mat = String(
          props.RoadMaterial ||
            (structCfg?.RoadType ? Object.keys(structCfg.RoadType)[0] : 'Asphalt')
        )
        const layerInfo = summarizeStructureLayers(structCfg)
        ;(feature as any)._structId = structId
        ;(feature as any)._roadMat = mat

        const color = getRoadStructureColor(structId, mat)
        const roadLabel = String(props.road_name || structCfg?.Name || structId)
        if (!legendAcc[structId]) {
          legendAcc[structId] = {
            id: structId,
            label: roadLabel,
            material: mat,
            color,
            layersSummary: layerInfo.breakdown,
            count: 0,
          }
        }
        legendAcc[structId].count += 1

        const matColor = mat.toLowerCase() === 'concrete' ? '#0891b2' : '#475569'
        layer.bindTooltip(
          `<b>${roadLabel}</b> <span class="text-xs font-mono">(${structId})</span><br/>` +
          `<span style="color: ${matColor}; font-weight: 700;">${mat}</span> — ${layerInfo.breakdown}<br/>` +
          `${props.lanes || structCfg?.Lanes || 2} lanes | Section km ${props.station_start_km != null ? Number(props.station_start_km).toFixed(2) : '?'}`,
          { sticky: true }
        )
        layer.on('click', (ev: any) => {
          handleFeatureClick('SingleRoadSegmentStateDS', feature, ev)
        })
      }
    }).addTo(roadStructuresGroup)

    structureLegendItems.value = Object.values(legendAcc).sort((a, b) => a.id.localeCompare(b.id))
  }

  // 3. Road State Points (Clustered)
  if (layers.road) {
    roadClusterGroup.clearLayers()
    roadPointLayersById.clear()
    const geojson = L.geoJSON(layers.road, {
      pointToLayer: (feature, latlng) => {
        const health = feature.properties?.state ?? 100
        const color = getRoadColor(health)
        const isSelected = !!selectedId && feature.properties?.id === selectedId
        const cm = L.circleMarker(latlng, {
          renderer: canvasRenderer || undefined,
          radius: isSelected ? 12 : 6,
          fillColor: color,
          color: isSelected ? '#fbbf24' : '#000',
          weight: isSelected ? 3 : 0.5,
          fillOpacity: 1
        })
        if (feature.properties?.id != null) {
          roadPointLayersById.set(String(feature.properties.id), cm)
        }
        return cm
      },
      onEachFeature: (feature, layer) => {
        const props = feature.properties || {}
        const dirLabel = props.carriageway || (props.direction === 1 ? 'Dresden → Leipzig' : 'Leipzig → Dresden')
        const startKm = props.station_start_km != null ? props.station_start_km.toFixed(2) : (props.dist != null ? props.dist.toFixed(2) : '?')
        const endKm = props.station_end_km != null ? props.station_end_km.toFixed(2) : '?'
        layer.bindTooltip(
          `<b>${props.name || props.id}</b><br/>` +
          `<span class="text-xs text-blue-600 font-semibold">${dirLabel}</span><br/>` +
          `Station: <b>km ${startKm} – ${endKm}</b><br/>` +
          `Health: <b>${props.state}%</b>`,
          { sticky: true }
        )
        layer.on('click', (ev) => handleFeatureClick('SingleRoadPointStateDS', feature, ev))
      }
    })
    roadClusterGroup.addLayer(geojson)
  }

  // 4. Water Sources
  if (layers.water) {
    waterGroup.clearLayers()
    L.geoJSON(layers.water, {
      pointToLayer: (feature, latlng) => {
        const isSelected = !!selectedId && feature.properties?.id === selectedId
        return L.marker(latlng, { icon: getWaterIcon(isSelected) })
      },
      onEachFeature: (feature, layer) => {
        const props = feature.properties || {}
        layer.bindTooltip(
          `<b>${props.name || 'Water Source #' + props.id}</b><br/>` +
          `<span class="text-xs text-cyan-600 font-semibold">${props.water_type || 'Hydrological Basin'}</span><br/>` +
          `Station: <b>km ${Number(props.kilometer || 0).toFixed(1)}</b> • Cooling Zone: 5.0 km`,
          { sticky: true }
        )
        layer.on('click', (ev) => handleFeatureClick('SingleWaterStateDS', feature, ev))
      }
    }).addTo(waterGroup)
  }

  // 5. Highway Intersections & Junctions (formerly "Vehicle spawn")
  if (layers.spawn) {
    spawnGroup.clearLayers()
    L.geoJSON(layers.spawn, {
      pointToLayer: (feature, latlng) => {
        const isSelected = !!selectedId && feature.properties?.id === selectedId
        return L.circleMarker(latlng, {
          renderer: canvasRenderer || undefined,
          radius: isSelected ? 12 : 7,
          fillColor: '#facc15',
          color: isSelected ? '#fbbf24' : '#0f172a',
          weight: isSelected ? 3 : 1.5,
          opacity: 1,
          fillOpacity: 0.9
        })
      },
      onEachFeature: (feature, layer) => {
        const props = feature.properties || {}
        layer.bindTooltip(
          `<b>[${props.code || 'AS'}] ${props.name || 'Highway Junction'}</b><br/>` +
          `<span class="text-xs text-amber-600 font-semibold">${props.type || 'Autobahn Junction'} • ${props.connecting_road || ''}</span><br/>` +
          `Station: <b>km ${Number(props.kilometer || 0).toFixed(1)}</b> • AADT: ${Number(props.daily_traffic_aadt || 42000).toLocaleString()} veh/d`,
          { sticky: true }
        )
        layer.on('click', (ev) => handleFeatureClick('SingleExitStateDS', feature, ev))
      }
    }).addTo(spawnGroup)
  }

  // 6. Roadside Units (RSUs) + One-Time Voronoi-Clipped 10 km Coverage Cells
  if (layers.ru) {
    ruGroup.clearLayers()
    rsuMarkersMap.clear()
    if (Array.isArray(layers.ru.features)) {
      computeRsuCoverageCellsOnce(layers.ru.features)
    }
    L.geoJSON(layers.ru, {
      pointToLayer: (feature, latlng) => {
        const isSelected = !!selectedId && feature.properties?.id === selectedId
        const marker = L.marker(latlng, {
          icon: getRuIcon(isSelected),
          draggable: store.isEditorMode
        })
        ;(marker as any).feature = feature
        rsuMarkersMap.set(String(feature.properties?.id), marker)

        marker.on('dragend', (ev: any) => {
          const newLatLng = ev.target.getLatLng()
          feature.geometry.coordinates = [newLatLng.lng, newLatLng.lat]
          const nearest = findNearestStationToLatLng(newLatLng.lat, newLatLng.lng)
          if (nearest) {
            feature.properties.station_km = Number(nearest.km.toFixed(1))
            feature.properties.ClosestPoint = Number(nearest.km.toFixed(1))
            feature.properties.ClosestPointDist = Number(nearest.distKm.toFixed(3))
          }
          if (Array.isArray(layers.ru?.features)) {
            computeRsuCoverageCellsOnce(layers.ru.features)
          }
          store.hasUnsavedEdits = true
          updateSelectionTrajectoryAndContext()
        })

        return marker
      },
      onEachFeature: (feature, layer) => {
        const props = feature.properties || {}
        layer.bindTooltip(
          `<b>${props.name || 'RSU #' + props.id}</b><br/>` +
          `<span class="text-xs text-purple-600 font-semibold">${props.town || 'Corridor Edge'} • km ${Number(props.kilometer || props.ClosestPoint || 0).toFixed(1)}</span><br/>` +
          `V2X Voronoi Cell: 10.0 km range`,
          { sticky: true }
        )
        layer.on('click', (ev) => handleFeatureClick('SingleRoadsideUnitsStateDS', feature, ev))
      }
    }).addTo(ruGroup)
  }

  // 7. Lane Polygons (Optional Lanelet2 / ASAM OpenDRIVE export)
  if (layers.lane_polygons) {
    lanePolygonsGroup.clearLayers()
    L.geoJSON(layers.lane_polygons, {
      style: () => ({
        color: '#64748b',
        weight: 1,
        fillColor: '#334155',
        fillOpacity: 0.22
      }),
      onEachFeature: (feature, layer) => {
        const props = feature.properties || {}
        const laneId = props.lanelet_id ?? props.lane_id ?? props.id ?? 'Lane'
        layer.bindTooltip(`<b>Lane ${laneId}</b>`, { sticky: true })
      }
    }).addTo(lanePolygonsGroup)
  }

  // 8. Embedded Pavement Sensor Stations (KM-100HAS, KDG-500KPA, PT1000, SMT100, HG-5VHS, 2210-002)
  if (layers.embedded_sensors) {
    embeddedSensorsGroup.clearLayers()
    L.geoJSON(layers.embedded_sensors, {
      pointToLayer: (feature, latlng) => {
        const isSelected = !!selectedId && feature.properties?.id === selectedId
        return L.circleMarker(latlng, {
          renderer: canvasRenderer || undefined,
          radius: isSelected ? 10 : 6,
          fillColor: '#00AA82',
          color: isSelected ? '#fbbf24' : '#ffffff',
          weight: isSelected ? 3 : 1.5,
          opacity: 1,
          fillOpacity: 0.95
        })
      },
      onEachFeature: (feature, layer) => {
        const props = feature.properties || {}
        const model = props.model || props.sensor_model || '6-Sensor DAQ Stack'
        layer.bindTooltip(
          `<b>${props.name || props.id || 'Embedded Sensor'}</b><br/>` +
          `<span class="text-xs text-emerald-600 font-semibold">${model}</span>`,
          { sticky: true }
        )
        layer.on('click', (ev) => handleFeatureClick('SingleEmbeddedSensorStateDS', feature, ev))
      }
    }).addTo(embeddedSensorsGroup)
  }

  if (layers.road_segments && layers.road) {
    staticLayersRendered = true
  }
}

/**
 * Applies incremental dirty segment health updates in O(k) time without touching unchanged layers.
 */
const applyDirtySegmentsToMap = (dirty: Record<string, number>) => {
  if (!dirty || Object.keys(dirty).length === 0) return
  const selectedId = store.selectedFeature?.properties?.id

  for (const [idKey, newHealth] of Object.entries(dirty)) {
    const segLayer = roadSegmentLayersById.get(String(idKey))
    if (segLayer && segLayer.setStyle) {
      const feat = (segLayer as any).feature
      if (feat?.properties) feat.properties.state = newHealth
      const isSelected = !!selectedId && String(feat?.properties?.id) === String(selectedId)
      segLayer.setStyle({
        color: isSelected ? '#fbbf24' : getRoadColor(newHealth),
        weight: isSelected ? 8 : 4.5,
        opacity: isSelected ? 1 : 0.85
      })
    }

    const ptLayer = roadPointLayersById.get(String(idKey))
    if (ptLayer && ptLayer.setStyle) {
      const feat = (ptLayer as any).feature
      if (feat?.properties) feat.properties.state = newHealth
      const isSelected = !!selectedId && String(feat?.properties?.id) === String(selectedId)
      ptLayer.setStyle({
        fillColor: getRoadColor(newHealth),
        radius: isSelected ? 12 : 6,
        color: isSelected ? '#fbbf24' : '#000',
        weight: isSelected ? 3 : 0.5
      })
    }
  }
}

const updateLayerStyles = () => {
    if (!map) return
    const selectedId = store.selectedFeature?.properties?.id

    const applyToGroup = (group: L.LayerGroup | L.FeatureGroup | any, updateFn: (marker: any) => void) => {
        group.eachLayer((layer: any) => {
            if (layer.eachLayer) {
                layer.eachLayer((subLayer: any) => {
                    if (subLayer.eachLayer) subLayer.eachLayer(updateFn)
                    else updateFn(subLayer)
                })
            } else {
                updateFn(layer)
            }
        })
    }

    // 0. Road segments
    applyToGroup(roadSegmentsGroup, (layer: any) => {
        const isSelected = !!selectedId && String(layer.feature?.properties?.id) === String(selectedId)
        if (layer.setStyle) {
            const health = layer.feature?.properties?.state ?? 100
            layer.setStyle({
                color: isSelected ? '#fbbf24' : getRoadColor(health),
                weight: isSelected ? 8 : 4.5,
                opacity: isSelected ? 1 : 0.85
            })
            if (isSelected && layer.bringToFront) layer.bringToFront()
        }
    })

    // 0b. Road structures overlay
    applyToGroup(roadStructuresGroup, (layer: any) => {
        const isSelected = !!selectedId && String(layer.feature?.properties?.id) === String(selectedId)
        if (layer.setStyle) {
            const structId = String(layer.feature?._structId || layer.feature?.properties?.RoadStructure || layer.feature?.properties?.road || 'RoadStructure_1')
            const roadMat = String(layer.feature?._roadMat || layer.feature?.properties?.RoadMaterial || 'Asphalt')
            layer.setStyle({
                color: isSelected ? '#fbbf24' : getRoadStructureColor(structId, roadMat),
                weight: isSelected ? 9 : 6,
                opacity: isSelected ? 1 : 0.92
            })
            if (isSelected && layer.bringToFront) layer.bringToFront()
        }
    })

    // 1. Road points
    applyToGroup(roadClusterGroup, (marker: any) => {
        const isSelected = !!selectedId && String(marker.feature?.properties?.id) === String(selectedId)
        if (marker.setStyle) {
            marker.setStyle({
                radius: isSelected ? 12 : 6,
                color: isSelected ? '#fbbf24' : '#000',
                weight: isSelected ? 3 : 0.5,
            })
        }
    })

    // 2. Intersections / Spawn points
    applyToGroup(spawnGroup, (marker: any) => {
        const isSelected = !!selectedId && String(marker.feature?.properties?.id) === String(selectedId)
        if (marker.setStyle) {
            marker.setStyle({
                radius: isSelected ? 12 : 7,
                color: isSelected ? '#fbbf24' : '#0f172a',
                weight: isSelected ? 3 : 1.5,
            })
        }
    })

    // 3. Icons
    const iconConfigs = [
        { group: waterGroup, getIcon: (sel: boolean, _f?: any) => getWaterIcon(sel) },
        { group: ruGroup, getIcon: (sel: boolean, _f?: any) => getRuIcon(sel) },
        { group: vehiclesGroup, getIcon: (sel: boolean, _f?: any) => getVehicleIcon(sel) },
        { group: dronesGroup, getIcon: (sel: boolean, _f?: any) => getDroneIcon(sel) },
        { group: warningsGroup, getIcon: (sel: boolean, f?: any) => getWarningIcon(sel, f) }
    ]

    iconConfigs.forEach(({ group, getIcon }) => {
        applyToGroup(group, (marker: any) => {
            const isSelected = !!selectedId && String(marker.feature?.properties?.id) === String(selectedId)
            if (marker.setIcon) {
                marker.setIcon(getIcon(isSelected, marker.feature))
            }
        })
    })
}

const updateV2XLink = () => {
    if (!map) return
    v2xLinkGroup.clearLayers()

    const selected = store.selectedFeature
    const isVehicle = store.selectedType === 'SingleVehicleStateDS'
    if (!isVehicle || !selected) return

    const curId = String(selected.properties?.id ?? selected.properties?.ID)
    const liveFeature = store.digitalShadowRaw?.map_layers?.vehicles?.features?.find(
        (vf: any) => String(vf.properties?.id ?? vf.properties?.ID) === curId
    ) || selected

    let vCoords: [number, number] | null = null
    const tracked = trackedVehicles.get(curId)
    if (tracked && tracked.currentLatLng) {
        vCoords = tracked.currentLatLng
    } else if (liveFeature.geometry?.type === 'Point' && Array.isArray(liveFeature.geometry.coordinates)) {
        vCoords = [liveFeature.geometry.coordinates[1], liveFeature.geometry.coordinates[0]]
    }
    if (!vCoords) return

    const stats = store.selectedData?.stats || {}
    const lastFrom = (arr: any) => (Array.isArray(arr) && arr.length > 0 ? arr[arr.length - 1] : null)

    const props = liveFeature.properties || {}
    const state = props.State || props

    const rsuId = lastFrom(stats['RoadsideUnit']) || state.RoadsideUnit
    const rsuName = lastFrom(stats['RoadsideUnitName']) || state.RoadsideUnitName || (state.RoadsideUnitStation != null ? `RSU @ km ${state.RoadsideUnitStation}` : 'RSU Edge Node')

    let rsuCoords: [number, number] | null = null
    let rsuFeatureProps: any = null

    const ruGeo = store.digitalShadowRaw?.map_layers?.ru
    if (ruGeo && Array.isArray(ruGeo.features) && ruGeo.features.length > 0) {
        if (rsuId) {
            const found = ruGeo.features.find((f: any) => String(f.properties?.id) === String(rsuId))
            if (found && found.geometry?.coordinates) {
                rsuCoords = [found.geometry.coordinates[1], found.geometry.coordinates[0]]
                rsuFeatureProps = found.properties
            }
        }
        if (!rsuCoords) {
            let minD = Infinity
            for (const f of ruGeo.features) {
                if (f.geometry?.coordinates) {
                    const c: [number, number] = [f.geometry.coordinates[1], f.geometry.coordinates[0]]
                    const d = map.distance(vCoords, c)
                    if (d < minD) {
                        minD = d
                        rsuCoords = c
                        rsuFeatureProps = f.properties
                    }
                }
            }
        }
    }

    if (!rsuCoords) return

    const resolvedRsuId = String(rsuFeatureProps?.id || rsuId || '')
    const actualDistKm = map.distance(vCoords, rsuCoords) / 1000
    const distText = actualDistKm < 1 ? `${Math.round(actualDistKm * 1000)} m` : `${actualDistKm.toFixed(1)} km`
    const displayName = rsuFeatureProps?.name || rsuName

    // Render the precomputed realistic Voronoi-clipped 10 km coverage cell for the serving RSU
    const voronoiPoly = rsuCoveragePolygonsById.get(resolvedRsuId)
    if (voronoiPoly && voronoiPoly.length >= 3) {
        L.polygon(voronoiPoly, {
            renderer: canvasRenderer || undefined,
            color: '#06b6d4',
            weight: 1.8,
            dashArray: '6, 6',
            fillColor: '#06b6d4',
            fillOpacity: 0.08,
            interactive: false
        }).addTo(v2xLinkGroup)
    } else {
        L.circle(rsuCoords, {
            renderer: canvasRenderer || undefined,
            radius: 10000,
            color: '#06b6d4',
            weight: 1.5,
            dashArray: '6, 8',
            fillColor: '#06b6d4',
            fillOpacity: 0.05,
            interactive: false
        }).addTo(v2xLinkGroup)
    }

    const rsuPulseIcon = L.divIcon({
        className: 'v2x-pulse-container',
        html: '<div class="v2x-pulse-ring"></div>',
        iconSize: [40, 40],
        iconAnchor: [20, 20]
    })
    L.marker(rsuCoords, { icon: rsuPulseIcon, interactive: false }).addTo(v2xLinkGroup)

    L.polyline([vCoords, rsuCoords], {
        renderer: canvasRenderer || undefined,
        color: '#06b6d4',
        weight: 8,
        opacity: 0.25,
        lineCap: 'round',
        interactive: false
    }).addTo(v2xLinkGroup)

    L.polyline([vCoords, rsuCoords], {
        color: '#22d3ee',
        weight: 2.5,
        dashArray: '8, 8',
        className: 'v2x-animated-beam',
        opacity: 0.95,
        interactive: false
    }).addTo(v2xLinkGroup)

    const midLatLng: [number, number] = [
        (vCoords[0] + rsuCoords[0]) / 2,
        (vCoords[1] + rsuCoords[1]) / 2
    ]
    const shortRsuName = String(displayName).split('/')[0].replace(')', '').trim()
    const badgeIcon = L.divIcon({
        className: 'v2x-badge-container',
        html: `
          <div class="v2x-link-pill">
            <span class="v2x-pulse-dot"></span>
            <span class="font-bold text-cyan-400">HLA-V2X</span>
            <span class="text-slate-400">•</span>
            <span class="font-semibold text-white">${shortRsuName}</span>
            <span class="text-slate-400">•</span>
            <span class="text-amber-300 font-bold font-mono">${distText}</span>
          </div>
        `,
        iconSize: [0, 0],
        iconAnchor: [0, 0]
    })
    L.marker(midLatLng, { icon: badgeIcon, interactive: false }).addTo(v2xLinkGroup)
}

let lastSelectedObjectId: string | null = null

// Highlight selected feature & update trajectory overlay
watch(() => store.selectedFeature, (newFeature) => {
    if (!map) return
    const curObjId = newFeature ? `${store.selectedType}_${newFeature.properties?.id ?? newFeature.properties?.ID}` : null

    // Only auto-pan when the user selects a DIFFERENT object, not on background 5s refresh ticks
    if (newFeature && newFeature.geometry && curObjId !== lastSelectedObjectId) {
        if (store.selectedType === 'SingleVehicleStateDS') {
            const vid = String(newFeature.properties?.id ?? newFeature.properties?.ID ?? '')
            const tracked = trackedVehicles.get(vid)
            if (tracked?.extrapolationHistory?.length) {
                store.vehicleExtrapolations[vid] = [...tracked.extrapolationHistory]
            }
        }
        if (newFeature.geometry.type === 'Point') {
            const coords = newFeature.geometry.coordinates
            const latlng = [coords[1], coords[0]] as L.LatLngExpression
            map.panTo(latlng)
        } else if (newFeature.geometry.type === 'LineString') {
            const coords = newFeature.geometry.coordinates
            if (coords.length > 0) {
                const mid = coords[Math.floor(coords.length / 2)]
                map.panTo([mid[1], mid[0]])
            }
        }
    }
    lastSelectedObjectId = curObjId

    updateLayerStyles()
    updateV2XLink()
    updateSelectionTrajectoryAndContext()
})

watch(() => store.digitalShadowRaw, (newState: any) => {
   if (!map || !newState || !newState.map_layers) return

   // 1. Render static layers once (never clear/recreate 1,215 road segments on 5s ticks)
   if (!staticLayersRendered) {
     renderStaticLayersOnce(newState.map_layers)
   } else if (store.lastDirtySegments && Object.keys(store.lastDirtySegments).length > 0) {
     applyDirtySegmentsToMap(store.lastDirtySegments)
   }

   const selectedId = store.selectedFeature?.properties?.id

   // 2. Sync dynamic Vehicles via persistent Flightradar24-style extrapolation engine
   syncVehicleLayers(newState.map_layers.vehicles)

   // 3. Update Drones (smooth dead-reckoning extrapolation engine)
   syncDroneLayers(newState.map_layers.drones)

   // 4. Update Warnings (typically 1-5 markers)
   warningsGroup.clearLayers()
   if (newState.map_layers.warnings) {
      L.geoJSON(newState.map_layers.warnings, {
         pointToLayer: (feature, latlng) => {
             const isSelected = !!selectedId && String(feature.properties?.id) === String(selectedId)
             return L.marker(latlng, { icon: getWarningIcon(isSelected, feature) })
         },
         onEachFeature: (feature, layer) => {
             const props = feature.properties || {}
             const stColor = props.State === 'Inspected' ? '#00AA82' : props.State === 'Under Inspection' ? '#f59e0b' : '#AF2D37'
             layer.bindTooltip(
               `<b>Warning #${props.id}: ${props.AnomalyType || 'Pavement Anomaly'}</b><br/>` +
               `<span class="text-xs font-semibold" style="color:${stColor}">Status: ${props.State || 'New'} • Severity: ${props.Severity || 'MEDIUM'}</span>`,
               { sticky: true }
             )
             layer.on('click', (ev) => handleFeatureClick('SingleWarningStateDS', feature, ev))
         }
      }).addTo(warningsGroup)
   }

   updateV2XLink()
   updateSelectionTrajectoryAndContext()
})

// ============================================================================
// ASSET EDITOR MODE & SCENARIO AUTHORING
// ============================================================================
const isSaving = ref(false)
const saveSuccessToast = ref(false)

const findNearestStationToLatLng = (lat: number, lng: number): { km: number; distKm: number } | null => {
  if (dir1Segments.length === 0) return null
  let bestDist = Infinity
  let bestKm = 0

  for (const seg of dir1Segments) {
    const coords = seg.geometry?.coordinates
    if (Array.isArray(coords)) {
      for (const c of coords) {
        const d = activeCoordSystem.distanceMeters([lng, lat], [c[0], c[1]])
        if (d < bestDist) {
          bestDist = d
          bestKm = Number(seg.properties?.station_start_km ?? 0)
        }
      }
    }
  }
  return { km: bestKm, distKm: bestDist / 1000.0 }
}

watch(
  () => store.isEditorMode,
  (isEdit) => {
    for (const marker of rsuMarkersMap.values()) {
      if (isEdit) {
        marker.dragging?.enable()
      } else {
        marker.dragging?.disable()
      }
    }
    if (!isEdit && !animationFrameId) {
      startAnimationLoop()
    }
  }
)

const addRsuNode = () => {
  if (!map) return
  const center = map.getCenter()
  const rsuCount = rsuMarkersMap.size + 1
  const newId = `rsu_${Date.now().toString().slice(-4)}`
  const nearest = findNearestStationToLatLng(center.lat, center.lng)
  const stationKm = nearest ? Number(nearest.km.toFixed(1)) : 50.0

  const newFeature = {
    type: 'Feature',
    properties: {
      id: newId,
      tag: `RSU-${rsuCount.toString().padStart(2, '0')}`,
      name: `RSU-${rsuCount.toString().padStart(2, '0')} (Interactive Custom Node)`,
      town: `Corridor Edge km ${stationKm}`,
      station_km: stationKm,
      ClosestPoint: stationKm,
      ClosestPointDist: nearest ? Number(nearest.distKm.toFixed(3)) : 0.05,
      coverage_radius_km: 10.0,
      standard: 'ETSI ITS-G5 / IEEE 802.11p',
      AirTemperature: 22.5,
      RoadSurfaceTemperature: 26.0,
      WeatherState: 'Sunny'
    },
    geometry: {
      type: 'Point',
      coordinates: [center.lng, center.lat]
    }
  }

  const ruLayers = store.digitalShadowRaw?.map_layers?.ru
  if (ruLayers && Array.isArray(ruLayers.features)) {
    ruLayers.features.push(newFeature)
    computeRsuCoverageCellsOnce(ruLayers.features)
  }

  const marker = L.marker(center, { icon: getRuIcon(true), draggable: true })
  ;(marker as any).feature = newFeature
  marker.bindTooltip(`<b>${newFeature.properties.name}</b><br/>km ${stationKm} • Coverage: 10.0 km`, { sticky: true })
  marker.on('click', (ev) => handleFeatureClick('SingleRoadsideUnitsStateDS', newFeature, ev))
  marker.on('dragend', (ev: any) => {
    const newLatLng = ev.target.getLatLng()
    newFeature.geometry.coordinates = [newLatLng.lng, newLatLng.lat]
    const n = findNearestStationToLatLng(newLatLng.lat, newLatLng.lng)
    if (n) {
      newFeature.properties.station_km = Number(n.km.toFixed(1))
      newFeature.properties.ClosestPoint = Number(n.km.toFixed(1))
      newFeature.properties.ClosestPointDist = Number(n.distKm.toFixed(3))
    }
    if (ruLayers?.features) computeRsuCoverageCellsOnce(ruLayers.features)
    store.hasUnsavedEdits = true
    updateSelectionTrajectoryAndContext()
  })
  marker.addTo(ruGroup)
  rsuMarkersMap.set(newId, marker)

  store.hasUnsavedEdits = true
  handleFeatureClick('SingleRoadsideUnitsStateDS', newFeature)
}

const deleteSelectedRsu = () => {
  const selFeature = store.selectedFeature
  const selId = selFeature?.properties?.id
  if (!selId) return

  const marker = rsuMarkersMap.get(String(selId))
  if (marker) {
    ruGroup.removeLayer(marker)
    rsuMarkersMap.delete(String(selId))
  }

  const ruLayers = store.digitalShadowRaw?.map_layers?.ru
  if (ruLayers && Array.isArray(ruLayers.features)) {
    const idx = ruLayers.features.findIndex((f: any) => String(f.properties?.id) === String(selId))
    if (idx !== -1) {
      ruLayers.features.splice(idx, 1)
      computeRsuCoverageCellsOnce(ruLayers.features)
    }
  }
  store.clearSelection()
  store.hasUnsavedEdits = true
  updateSelectionTrajectoryAndContext()
}

const applyInspectorChanges = async (updatedProps: Record<string, any>) => {
  const feat = store.selectedFeature
  if (!feat?.properties) return
  const type = store.selectedType
  const id = feat.properties.id || feat.properties.ID

  if (type === 'SingleRoadsideUnitsStateDS') {
    Object.assign(feat.properties, updatedProps)
    store.hasUnsavedEdits = true
    try {
      await store.updateAssetParameters('rsu', String(id), updatedProps)
    } catch (err) {
      console.warn('RSU parameter update deferred until scenario save:', err)
    }
    const marker = rsuMarkersMap.get(String(id))
    if (marker) {
      marker.setTooltipContent(`<b>${feat.properties.name}</b><br/>km ${Number(feat.properties.station_km || 0).toFixed(1)} • Coverage: ${feat.properties.coverage_radius_km || 10} km`)
    }
    const ruLayers = store.digitalShadowRaw?.map_layers?.ru
    if (ruLayers?.features) computeRsuCoverageCellsOnce(ruLayers.features)
  } else if (type === 'SingleVehicleStateDS') {
    Object.assign(feat.properties, updatedProps)
    try {
      await store.updateAssetParameters('vehicle', String(id), updatedProps)
    } catch (err) {
      console.warn('Vehicle parameter update failed:', err)
    }
  }
}

const saveScenarioEdits = async () => {
  try {
    isSaving.value = true
    const ruLayers = store.digitalShadowRaw?.map_layers?.ru || { type: 'FeatureCollection', features: [] }
    const spawnLayers = store.digitalShadowRaw?.map_layers?.spawn || { type: 'FeatureCollection', features: [] }
    const waterLayers = store.digitalShadowRaw?.map_layers?.water || { type: 'FeatureCollection', features: [] }

    const infrastructurePayload = {
      manifest_version: '2.0.0',
      corridor_id: 'a14_corridor',
      roadside_units: ruLayers,
      spawn_points: spawnLayers,
      water_sources: waterLayers,
      ...(store.digitalShadowRaw?.map_layers?.embedded_sensors
        ? { embedded_sensors: store.digitalShadowRaw.map_layers.embedded_sensors }
        : {}),
    }

    await store.saveScenarioInfrastructure(infrastructurePayload)
    saveSuccessToast.value = true
    setTimeout(() => {
      saveSuccessToast.value = false
    }, 3000)
  } catch (e) {
    console.error('Failed to save scenario:', e)
  } finally {
    isSaving.value = false
  }
}

const discardScenarioEdits = async () => {
  store.hasUnsavedEdits = false
  staticLayersRendered = false
  await store.fetchState()
}
</script>

<template>
  <div class="relative w-full h-full rounded-2xl z-0 overflow-hidden">
    <div ref="mapContainer" class="w-full h-full"></div>

    <AssetEditorOverlay
      :is-saving="isSaving"
      :save-success-toast="saveSuccessToast"
      @add-rsu="addRsuNode"
      @save-scenario="saveScenarioEdits"
      @discard-edits="discardScenarioEdits"
      @apply-changes="applyInspectorChanges"
      @delete-rsu="deleteSelectedRsu"
    />

    <!-- Road Structures Legend Card (visible when Road structures overlay is toggled on) -->
    <div v-if="showStructureLegend && structureLegendItems.length > 0"
         class="absolute bottom-12 left-3 z-[400] max-w-sm bg-[#00305E]/92 backdrop-blur-md border border-[#5096BE]/60 rounded-xl p-2.5 shadow-xl text-[11px] text-slate-100 pointer-events-none select-none space-y-1.5">
      <div class="flex items-center justify-between gap-2 pb-1 border-b border-white/10">
        <span class="font-bold tracking-wider uppercase text-[10px] text-[#8ecae6]">Road Structures</span>
        <span class="font-mono text-[9px] text-slate-300">{{ structureLegendItems.length }} types</span>
      </div>
      <div v-for="item in structureLegendItems" :key="item.id" class="flex items-center justify-between gap-2 text-[10px]">
        <div class="flex items-center gap-1.5 min-w-0">
          <span class="w-3 h-1.5 rounded-full shrink-0" :style="{ backgroundColor: item.color }"></span>
          <span class="font-semibold text-white truncate">{{ item.label }}</span>
        </div>
        <div class="flex items-center gap-1 shrink-0 font-mono text-[9px]">
          <span class="px-1 py-0.5 rounded border"
                :class="item.material.toLowerCase() === 'concrete'
                  ? 'bg-cyan-500/20 text-cyan-300 border-cyan-400/40'
                  : 'bg-slate-800/80 text-slate-200 border-white/15'">
            {{ item.material }}
          </span>
          <span class="text-slate-300">{{ item.layersSummary }}</span>
        </div>
      </div>
    </div>

    <!-- Multi-LOD Flight Radar Telemetry Pill -->
    <div class="absolute bottom-3 left-3 z-[400] flex items-center space-x-2 bg-[#00305E]/92 backdrop-blur-md border border-[#5096BE]/60 rounded-full px-3.5 py-1 shadow-lg text-[11px] text-slate-200 pointer-events-none select-none">
      <span class="w-2 h-2 rounded-full transition-all duration-300" :class="currentLODState.active ? 'bg-[#BECD32] shadow-[0_0_8px_#BECD32]' : 'bg-[#5096BE]'"></span>
      <span class="font-bold tracking-tight text-white">Canvas Renderer •</span>
      <span class="font-semibold" :class="currentLODState.active ? 'text-[#BECD32]' : 'text-[#8ecae6]'">{{ currentLODState.label }}</span>
      <span class="text-white/30">•</span>
      <span class="text-slate-300 font-mono text-[10px]">Zoom {{ currentZoomLevel }}</span>
    </div>
  </div>
</template>

<style>
/* Architectural color grading for standard OSM tiles (100% Free, Zero API Key) */
.dtr-clean-tiles {
  filter: saturate(0.32) contrast(0.95) brightness(1.04);
  transition: filter 0.3s ease;
}

html.dark .dtr-clean-tiles {
  filter: invert(100%) hue-rotate(180deg) saturate(0.55) brightness(0.92) contrast(0.95);
}

.selected-icon-outline {
  filter: drop-shadow(0 0 5px #fbbf24) drop-shadow(0 0 2px #fbbf24);
  z-index: 1000 !important;
}

.custom-cluster-icon {
    background: none !important;
    border: none !important;
}

.cluster-badge {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 2.5px solid rgba(255, 255, 255, 0.95);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35), inset 0 1px 2px rgba(255, 255, 255, 0.25);
  color: #ffffff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.65);
  transition: transform 0.15s ease-out, box-shadow 0.15s ease-out;
  cursor: pointer;
  user-select: none;
}

.cluster-badge:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.45);
}

.cluster-health {
  font-size: 13px;
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: -0.02em;
}

.cluster-sub {
  font-size: 9px;
  font-weight: 600;
  opacity: 0.92;
  line-height: 1;
  margin-top: 1px;
}

.cluster-hover-popup {
  pointer-events: none;
}

.cluster-hover-popup .leaflet-popup-content-wrapper {
  padding: 0;
  border-radius: 12px;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.25), 0 8px 10px -6px rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(226, 232, 240, 0.85);
  overflow: hidden;
}

.cluster-hover-popup .leaflet-popup-content {
  margin: 0;
  line-height: 1.4;
}

@keyframes v2x-dash {
  to {
    stroke-dashoffset: -32;
  }
}

.v2x-animated-beam {
  animation: v2x-dash 1.2s linear infinite;
  pointer-events: none;
}

.v2x-badge-container {
  overflow: visible !important;
}

.v2x-link-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: max-content;
  transform: translate(-50%, -140%);
  background: rgba(0, 48, 94, 0.95);
  border: 1.5px solid #5096BE;
  box-shadow: 0 4px 14px rgba(0, 48, 94, 0.45), 0 2px 8px rgba(0, 0, 0, 0.5);
  border-radius: 9999px;
  padding: 3px 11px;
  font-size: 11px;
  color: #ffffff;
  white-space: nowrap;
  pointer-events: none;
  backdrop-filter: blur(4px);
  user-select: none;
}

.v2x-pulse-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #BECD32;
  box-shadow: 0 0 8px #BECD32;
  animation: v2x-dot-pulse 1s infinite alternate;
}

@keyframes v2x-dot-pulse {
  from { opacity: 0.35; transform: scale(0.8); }
  to { opacity: 1; transform: scale(1.3); }
}

.v2x-pulse-container {
  background: none !important;
  border: none !important;
}

.v2x-pulse-ring {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 2.5px solid #06b6d4;
  background: rgba(6, 182, 212, 0.18);
  box-sizing: border-box;
  transform-origin: center center;
  animation: v2x-ring-expand 2s infinite ease-out;
  pointer-events: none;
}

@keyframes v2x-ring-expand {
  0% { transform: scale(0.35); opacity: 1; }
  100% { transform: scale(2.2); opacity: 0; }
}
</style>
