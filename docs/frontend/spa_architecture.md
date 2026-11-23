# Frontend SPA Architecture & Code-Splitting

The frontend is built with **Vue 3.5+**, **TypeScript 5**, **Vite 8**, and **Tailwind CSS v4**, designed to operate as an interactive single-page application (SPA).

---

## Component Organization

```text
frontend/src/
├── api/
│   └── client.ts                   # Axios client with configurable baseURL
├── components/dashboard/
│   ├── AssetEditorOverlay.vue      # Interactive Scenario Asset Editor mode & parameter panel
│   ├── BoussinesqViewer.vue        # 2D Analytical Stress Engine (Offscreen ImageData Blit)
│   ├── DashboardMap.vue            # 60 FPS HTML5 Canvas GIS Map & Dead-Reckoning
│   ├── DocumentationViewer.vue     # Two-pane Markdown catalog, KaTeX reader & custom notes editor
│   ├── FiwareInsights.vue          # Full-bleed Data Broker browser with SQL-like filter & history
│   ├── MetadataPanel.vue           # Searchable cyber-physical entity property inspector
│   ├── ObjectInspector.vue         # Polymorphic 8-entity inspector & telemetry charts
│   ├── PredictionPlot.vue          # 15-year pavement lifecycle deterioration forecast
│   ├── StatisticsCharts.vue        # Time-series vehicle velocity & load charts
│   ├── ThermalSimulation.vue       # 1D thermal FEM depth profile & RStO 12 layer probe
│   └── TreeRenderer.vue            # Heraklit HPN & FODA graph viewer (Vue Flow)
├── physics/
│   └── pavementMechanics.ts        # Decoupled 2D Boussinesq & Westergaard solvers
├── stores/
│   └── dashboard.ts                # Pinia store managing SSE stream and GIS layers
├── utils/
│   ├── mapCoordSystem.ts           # Shared WGS84 & LocalCartesian GIS math utilities
│   └── markdownRenderer.ts         # Offline KaTeX + Prism Markdown renderer
└── views/
    └── DashboardView.vue           # Main application shell with Polymorphic Drawer
```

---

## Async Component Code-Splitting

To maximize performance, non-essential drawer components are lazy-loaded on-demand using Vue's `defineAsyncComponent`:

```typescript
import { defineAsyncComponent } from 'vue'

const DocumentationViewer = defineAsyncComponent(() => import('../components/dashboard/DocumentationViewer.vue'))
const FiwareInsights = defineAsyncComponent(() => import('../components/dashboard/FiwareInsights.vue'))
const TreeRenderer = defineAsyncComponent(() => import('../components/dashboard/TreeRenderer.vue'))
const BoussinesqViewer = defineAsyncComponent(() => import('../components/dashboard/BoussinesqViewer.vue'))
const ThermalSimulation = defineAsyncComponent(() => import('../components/dashboard/ThermalSimulation.vue'))
const StatisticsCharts = defineAsyncComponent(() => import('../components/dashboard/StatisticsCharts.vue'))
const PredictionPlot = defineAsyncComponent(() => import('../components/dashboard/PredictionPlot.vue'))
```

### Performance Impact

* Initial entry bundle decreased by **65% to ~360 kB**.
* The core Leaflet map loads and renders almost instantaneously.
* Heavy visualization libraries (Vue Flow, Dagre, Prism.js, Chart.js) load in parallel chunks strictly when the user opens their respective drawer tab.
