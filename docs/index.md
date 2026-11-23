# Digital Twin Road Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Vue 3](https://img.shields.io/badge/Vue%203-3.5%2B-4FC08D.svg)](https://vuejs.org/)
[![Vite](https://img.shields.io/badge/Vite-8.0%2B-646CFF.svg)](https://vitejs.dev/)

Welcome to the comprehensive technical documentation for the **Digital Twin Road Platform**, an open-source cyber-physical digital twin and digital shadow platform for highway corridor infrastructure, connected freight vehicle kinematics, analytical 2D Boussinesq & Westergaard pavement elastostatics, 1D thermal finite-element diffusion, and edge Roadside Unit (RSU) federation co-simulation.

Authored by **Volodymyr Prokopets** under the permissive **MIT License**.

!!! note "Scientific Context & Research Mandate"
    This research software was developed in connection with scientific investigations conducted within the **DFG Collaborative Research Centre / Transregio TRR 339** (Project Number **453596084**, funded by the Deutsche Forschungsgemeinschaft / German Research Foundation). In adherence to the **DFG Guidelines on the Handling of Research Data** and the **FAIR Data Principles** (*Findable, Accessible, Interoperable, Reusable*), this software is published openly under the MIT License to foster transparent, reproducible cyber-physical infrastructure modeling across the scientific community.

---

## Architectural Highlights

- **2D Pavement Cross-Section Mechanics (`BoussinesqViewer.vue`):** High-performance analytical elastostatics on HTML5 Canvas using typed `Float32Array` grids and direct `Uint32Array` `ImageData` blitting (< 2 ms compute and render). Supports flexible asphalt (Boussinesq half-space with RStO 12 stratification) and rigid concrete (Westergaard plate on Winkler spring foundation).
- **Pure-Python Compositional Hybrid Petri Nets (`hpn.py` & `fm.py`):** In-tree implementation of Wolfgang Reisig's **HERAKLIT composition algebra** ($M_1 \bullet M_2$), fusing boundary interfaces across edge RSUs, weather states, pavement materials, and multi-scale mechanical solvers.
- **Dynamic IEEE 1516 HLA / FOM Federation Contracts (`world/federation.py`):** Fast-scale vehicle federates ($\Delta t = 0.05\text{ s}$) dynamically negotiate and bind SLA contracts with slow-scale Roadside Units (RSUs, $\Delta t = 5.0\text{ s}$) upon entering $10\text{ km}$ communication cells.
- **Hardware-Accelerated 60 FPS GIS Engine (`DashboardMap.vue`):** Centerline rendering of 1,215 road segments and 10,289 vertices via HTML5 Canvas with Flightradar24-inspired corridor tracking, autonomous UAV patrol drones, and interactive scenario asset editing.
- **Pluggable Data Curation Subsystem (`data_curation/`):** Unified broker interface supporting zero-dependency in-memory state (`native`) and European standard FIWARE Orion NGSIv2 / UltraLight 2.0 (`fiware`).

---

## Documentation Navigation

```text
Digital Twin Road Documentation
├── Getting Started
│   ├── Installation & Environment Setup
│   └── Quickstart Guide (Local, Local Dev & Docker)
├── System Architecture & Design
│   ├── C4 Architecture Blueprint (architecture/index.md)
│   ├── System Context & Boundaries
│   ├── Container Topology & Networking
│   └── Concurrency, Thread Safety & SSE Delta Streaming
├── Scientific & Mathematical Foundations
│   ├── Analytical 2D Boussinesq & Westergaard Mechanics
│   ├── 1D Thermal Finite-Element Depth Diffusion
│   ├── Continuum Road Wear & AASHTO 4th Power Law
│   └── Wolfgang Reisig's HERAKLIT Composition Algebra
├── Federated Co-Simulation
│   ├── IEEE 1516 HLA / FOM Standards & Schemas
│   └── Dynamic RSU-Vehicle SLA Contracts & Basis Recalibration
├── API & Module Reference
│   ├── FastAPI Backend & SSE Delta Endpoints
│   ├── Digital Shadow Coordinator (digital_shadow.py)
│   ├── Compositional HPN Runtime (hpn.py)
│   ├── Corridor Environment & Spatial Indexing (world/world.py & road.py)
│   └── Vehicle Kinematics & Axle Dynamics (vehicle/vehicle.py)
├── Frontend Architecture & Performance
│   ├── Vue 3 SPA Layout & Polymorphic Drawer
│   ├── 60 FPS HTML5 Canvas Optimization
│   └── Reactive Pinia State Management
└── DevOps & FAIR Compliance
    ├── Multi-Stage Docker, Docker Compose & Nginx
    └── FAIR Data Principles & DFG Compliance
```
