# Digital Twin Road — Frontend SPA (`Vue 3 + TypeScript + Vite`)

Interactive 60 FPS cyber-physical visualization client for the **Digital Twin Road Platform**.

## Key Subsystems

- **`src/components/dashboard/DashboardMap.vue`**: 60 FPS HTML5 Canvas GIS corridor renderer, Flightradar24-inspired dead-reckoning vehicle & UAV extrapolation, Voronoi V2X cell visualization, and interactive Scenario Asset Editor.
- **`src/components/dashboard/BoussinesqViewer.vue`**: Real-time analytical 2D Boussinesq (asphalt half-space) and Westergaard (concrete slab on Winkler foundation) cross-section stress & deflection engine (`Uint32Array` direct `ImageData` canvas blitting).
- **`src/components/dashboard/ObjectInspector.vue`**: Polymorphic 8-entity domain inspector (Vehicles, Roadside Units, Road Segments, Highway Junctions, Water Sources, Inspection Drones, Warnings, Embedded Pavement Sensors).
- **`src/components/dashboard/TreeRenderer.vue`**: Interactive Wolfgang Reisig Heraklit Hybrid Petri Net (`M1 • M2`) & FODA Feature Model visualizer powered by Vue Flow and Dagre.
- **`src/components/dashboard/ThermalSimulation.vue`**: Interactive 1D pavement depth thermal conduction profile.
- **`src/components/dashboard/PredictionPlot.vue`**: 15-year multi-horizon pavement rutting and damage forecast.
- **`src/components/dashboard/FiwareInsights.vue`**: Full-bleed Context Broker entity browser with SQL-like filter queries and history links.
- **`src/components/dashboard/DocumentationViewer.vue`**: Two-pane built-in Markdown/KaTeX reference handbook and custom notes editor.
- **`src/stores/dashboard.ts`**: Pinia reactive state store with static GIS layer caching (`markRaw`) and versioned delta SSE stream consumer (`/dashboard/stream`).

## Development Commands

```bash
# Install dependencies
npm ci --legacy-peer-deps

# Start hot-reloading development server (:5173)
npm run dev

# Run TypeScript compiler verification (vue-tsc) and production bundle build
npm run build
```
