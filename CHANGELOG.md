# Changelog

All notable changes to the **Digital Twin Road** platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-11-23

### Added

- **Dual 2D Pavement Mechanics Engine (`BoussinesqViewer.vue`):** Interactive HTML5 Canvas cross-section stress solver (< 2 ms compute & render) supporting Boussinesq elastic half-space (asphalt) and Westergaard plate on Winkler foundation (concrete), with single wide-base and dual tire footprint modeling.
- **Pure-Python HERAKLIT Hybrid Petri Net Engine (`hpn.py`, `fm.py`):** Compositional algebra (`M1 @ M2` / `M1 • M2`) with discrete places, continuous fluid places, guard conditions, and automatic shared interface boundary fusion, paired with interactive Vue Flow visualization (`TreeRenderer.vue`).
- **Dynamic IEEE 1516 HLA / FOM Federation Contracts (`world/federation.py`):** Multi-rate RSU–vehicle SLA negotiation upon entering Voronoi-clipped communication cells, with fallback and basis recalibration events.
- **Pluggable Data Curation & Full-Bleed Broker Workbench (`data_curation/`, `FiwareInsights.vue`):** Unified `BaseDataBroker` interface supporting `native` (in-memory) and `fiware` (Orion NGSIv2 / UltraLight 2.0), plus a full-bleed entity browser with SQL-like predicate filtering, single-entity lookup, and bounded time-series history (`/dashboard/fiware_entities/{entity_id}/history`).
- **In-App Two-Pane Documentation & KaTeX Renderer (`api/docs.py`, `DocumentationViewer.vue`, `markdownRenderer.ts`):** Built-in Zensical reference catalog (locked read-only) paired with file-backed custom Markdown notes (`docs/custom/*.md`) and offline bundled KaTeX + Prism rendering.
- **RStO 12 Layered Thermal Conduction Inspector (`ThermalSimulation.vue`, `api/physics.py`):** Per-layer pavement thermal conductivity ($k$), thickness, and temperature interval inspection (`POST /dashboard/thermal_distribution`) for vehicles and road segments.
- **Interactive Scenario Asset Editor & Bundle Format (`scenarios/a14_corridor/`, `world/scenario_loader.py`):** Self-contained corridor scenario manifests with draggable RSUs, live parameter overrides (`/api/assets/update`), and sanitized infrastructure persistence.
- **3-Mode Lifecycle Orchestration (`manage.sh`):** Explicit `./manage.sh up-local` (local dev processes), `./manage.sh up` (lightweight 2-container Native Docker stack), and `./manage.sh up-fiware` (full Docker stack with FIWARE Orion, IoT Agent UltraLight, and MongoDB).
- **Selective 5s Multi-Axle Kinematic Load Transfer (`vehicle/vehicle.py`):** Longitudinal dynamic pitch weight transfer, velocity-dependent Dynamic Load Coefficient, and AASHTO 4th-power ESAL calculation evaluated for the selected active vehicle.
- **Delta SSE Streaming (`/dashboard/stream`):** Per-client versioned delta updates (`dirty_segments`, moving vehicles, drones, warnings, RSU states) and one-time static GeoJSON layer loading (`/dashboard/static_layers`).
- **Comprehensive Documentation & Automated Test Suite:** C4 architecture specs (`docs/architecture/index.md`), Zensical documentation, scalability benchmarks (`scripts/benchmark_fleet.py`), and `pytest` + GitHub Actions CI (`70` passing tests).

### Changed

- Migrated frontend dashboard to **Vue 3.5**, **Vite 8**, **TypeScript 5**, **Pinia**, **Tailwind CSS v4**, and **Leaflet**.
- Consolidated Docker Compose orchestration with optional FIWARE profiles and Nginx reverse-proxied SPA + SSE delivery.
- Standardized repository packaging and tool configuration in `pyproject.toml`.

### Removed

- Legacy v1 static file layouts, deprecated v1 method aliases (`workwlow`, `test`, `test_read`), and unused weather simulator prototypes.

## [1.1.0] - 2025-12-01

### Added

- Initial corridor Digital Twin & Digital Shadow demonstrator for the Dresden–Leipzig A14 freight corridor.
- Coupled 1D thermal conduction and empirical pavement deformation pipeline (`SimPLs/temp_deform/`).
- Autonomous UAV inspection mission state machine and Markov chain weather micro-climate simulation.
