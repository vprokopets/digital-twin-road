# Container Architecture & C4 Level 2

The Container Architecture defines the technical execution boundaries of the system: the browser Single Page Application, the asynchronous FastAPI backend service, the in-tree simulation engines, and the pluggable data curation brokers.

---

## Container Topology

```text
+-----------------------------------------------------------------------------------+
|                    BROWSER SINGLE PAGE APPLICATION (SPA)                          |
|                                                                                   |
|   • Vue 3.5+ (Composition API with <script setup>)                                |
|   • TypeScript 5.0+ strict typing                                                 |
|   • Leaflet 1.9+ with HTML5 Canvas Renderer (`preferCanvas: true`)                |
|   • 60 FPS Dead-Reckoning Animation Loop (`requestAnimationFrame`)                |
|   • Offscreen ImageData Uint32Array Blit Viewer (Boussinesq Cross-Section)        |
|   • Vue Flow Interactive Graph Renderer (Heraklit Petri Nets & FODA Trees)        |
|   • Pinia State Management with Monotonic Delta Replay                            |
+---------------------------------^-------------------------------------------------+
                                  |
            HTTP GET /dashboard/static_layers (Heavy GIS loaded once)
            HTTP GET /dashboard/stream (EventSource 5s Delta Stream)
            HTTP POST /dashboard/select_object (Polymorphic Telemetry)
                                  |
+---------------------------------v-------------------------------------------------+
|                     FASTAPI BACKEND SERVICE (:8000)                               |
|                                                                                   |
|   • Uvicorn ASGI Server with modern `lifespan` Context Manager                    |
|   • Thread-Safe Mutex (`threading.RLock`) synchronizing API & Simulation          |
|   • Monotonic Versioned Delta Reader (`get_dirty_segments_since`)                 |
|   • Atomic GeoJSON Reference Swapping (`self.vehicles_geojson = new_dict`)        |
+---------------------------------^-------------------------------------------------+
                                  |
                                  | Direct In-Memory Python Calls (<0.1 ms)
                                  v
+-----------------------------------------------------------------------------------+
|                    IN-TREE SIMULATION & NUMERICAL RUNTIME                         |
|                                                                                   |
|   • DigitalShadow.workflow (Continuous 5.0 s Background Daemon Thread)            |
|   • Analytical 2D Boussinesq & Westergaard Elastostatic Solver                    |
|   • 1D Thermal Finite-Element Heat Conduction (fem_solver.py / temp.py)           |
|   • Wolfgang Reisig's Heraklit Compositional Hybrid Petri Net Engine (hpn.py)     |
|   • FODA Feature Model & Dynamic Mixin Synthesizer (fm.py)                        |
|   • IEEE 1516 HLA / FOM Corridor Federation Manager (world/federation.py)         |
|   • Vehicle Multi-Axle Kinematic Load Transfer Engine (vehicle/vehicle.py)        |
+---------------------------------^-------------------------------------------------+
                                  | (Optional)
                                  | NGSIv2 REST & UltraLight 2.0
                                  v
+-----------------------------------------------------------------------------------+
|                     OPTIONAL FIWARE IOT CLUSTER (DOCKER)                          |
|                                                                                   |
|   • FIWARE Orion Context Broker (:1026)                                           |
|   • MongoDB Document Database (:27017)                                            |
|   • FIWARE IoT Agent for UltraLight 2.0 (:4041 / :7896)                           |
+-----------------------------------------------------------------------------------+
```

---

## Network Interfaces & Protocol Separation

1. **Static GIS Layer Endpoint (`GET /dashboard/static_layers`):**  
   Transfers static geospatial geometry (1,215 road segments, 10,289 road curve vertices, water bodies, junctions, RSU footprints) once at application startup. This avoids re-transmitting 850+ kB of unchanged GIS coordinates on every simulation step.

2. **Lightweight Delta SSE Stream (`GET /dashboard/stream`):**  
   Pushes dynamic state every 5 seconds (~18–25 kB delta payload, cutting bandwidth and main-thread parsing by >90%): active vehicle coordinates, UAV inspection drone locations, RSU micro-climate readings, corridor federation contract summaries, and newly modified road segment health IDs.

3. **Polymorphic Entity Inspector (`POST /dashboard/select_object`):**  
   When an operator selects any corridor entity (road segment, vehicle, RSU, drone, junction, water body, or warning badge), this endpoint returns an inspection payload containing telemetry curves, the Heraklit Petri Net graph, the FODA variability tree, and HLA federation contract terms.
