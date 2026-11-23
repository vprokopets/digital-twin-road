# Architecture & Workflow Specification: Digital Twin Road Platform

This document details the architectural topology, container boundaries, component interactions, and operational sequences of the **Digital Twin Road Demonstrator** using the **C4 Model** and **UML Sequence Diagrams**.

---

## 1. C4 Level 1: System Context Diagram

The System Context diagram illustrates how the **Digital Twin Road Platform** sits at the nexus between highway physical assets, edge computing nodes, autonomous inspection fleets, and transport infrastructure operators.

```mermaid
flowchart TD
    subgraph Users["Human Actors & Operators"]
        OP["Highway Traffic Operator<br/>(Traffic Control Center)"]
        CE["Chief Civil Engineer<br/>(Maintenance Planning)"]
    end

    subgraph System["Digital Twin Road Platform (Core System)"]
        DTR["<b>Digital Twin Road Platform</b><br/>• 60 FPS GIS & Telemetry Dashboard<br/>• Analytical 2D Boussinesq/Westergaard Engine<br/>• Heraklit Compositional Hybrid Petri Nets<br/>• IEEE 1516 HLA / FOM Edge Federation<br/>• Multi-Client Versioned SSE Delta Stream"]
    end

    subgraph Physical["Physical Highway Corridor Assets"]
        HGV["Connected Freight Fleet<br/>(Multi-Axle HGVs, Vans, Cars)"]
        RSU_PHYS["Roadside Units (RSUs)<br/>(Every 5–10 km with SWIS Weather Sensors)"]
        PAVE["Pavement Structure<br/>(1,215 Segments along A4/A14/A38 Highway)"]
        DRONE_PHYS["Autonomous Inspection Fleet<br/>(UAV Drones at Depots)"]
    end

    subgraph External["External Ecosystems (Optional)"]
        FIWARE["FIWARE Smart City Ecosystem<br/>(Orion Context Broker & MongoDB)"]
        OPEN_DATA["Federal Mobility Data<br/>(Mobilithek / Autobahn GmbH WIM Logs)"]
    end

    HGV -->|"V2X Telemetry (Speed, Weight, GPS)"| DTR
    RSU_PHYS -->|"Micro-Climate & Surface Temp (SWIS)"| DTR
    PAVE -.->|"Physical Strain & Rutting State"| DTR
    DTR -->|"Autonomous Dispatch Flight Plan"| DRONE_PHYS
    DRONE_PHYS -->|"Optical / Thermal Telemetry"| DTR

    DTR -->|"Live 60 FPS Visual Twin & Alerts"| OP
    DTR -->|"Long-Term Pavement Degradation Prognosis"| CE

    DTR <-->|"NGSIv2 Entity Mirroring (Optional)"| FIWARE
    OPEN_DATA -.->|"Historical WIM & Weather Feeds"| DTR
```

---

## 2. C4 Level 2: Container Diagram

The Container diagram illustrates the runtime deployment topology: the **Vue 3 SPA**, the **FastAPI Backend**, and the optional **FIWARE IoT stack**.

```mermaid
flowchart TD
    subgraph Browser["Client Browser (Desktop / Mobile / Kiosk)"]
        SPA["Vue 3 + Vite Single Page Application (:5173)<br/>• Leaflet HTML5 Canvas Engine (preferCanvas: true)<br/>• Offscreen ImageData Uint32Array Blit Viewer<br/>• Vue Flow Heraklit HPN & FODA Visualizer<br/>• Pinia Reactive State Store"]
    end

    subgraph BackendHost["Backend Server Container (:8000)"]
        API["FastAPI Application (dashboard_backend.py)<br/>• Lifespan Context Manager<br/>• REST Layer Endpoints<br/>• Multi-Client SSE Streamer (/dashboard/stream)"]

        COORDINATOR["Digital Shadow Coordinator (digital_shadow.py)<br/>• Continuous 5s Co-Simulation Workflow<br/>• Thread-Safe Mutex (threading.RLock)<br/>• Atomic Reference GeoJSON Swapper"]

        ENGINES["In-Tree Numerical & Formal Engines<br/>• Analytical 2D Boussinesq Elastostatics<br/>• 1D Thermal Finite-Element Heat Equation<br/>• Heraklit Hybrid Petri Net Algebra (hpn.py)<br/>• FODA Feature Model Synthesizer (fm.py)<br/>• Experimental External Solver Bridge (SimPLs/engine_contract.py)"]

        FED["Corridor Federation Manager (world/federation.py)<br/>• IEEE 1516 HLA / FOM Contract Manager<br/>• Dynamic SLA Accuracy Tracking<br/>• RSU Cell Handover Coordinator"]

        WORLD["Corridor World & Traffic (world/)<br/>• 1,215 Road Segments & Versioned Dirty Set<br/>• Multi-Axle Kinematic Load Transfer<br/>• Multinomial Markov Weather Chains<br/>• UAV Drone Mission State Machine"]
    end

    subgraph IoT["Optional FIWARE IoT Stack (Docker)"]
        ORION["FIWARE Orion Context Broker (:1026)"]
        MONGO[("MongoDB Container (:27017)")]
    end

    SPA -->|"HTTP GET /dashboard/static_layers (One-Time Startup)"| API
    SPA -->|"HTTP GET /dashboard/stream (EventSource SSE Delta)"| API
    SPA -->|"HTTP POST /dashboard/select_object (Polymorphic Telemetry)"| API
    SPA -->|"HTTP POST /dashboard/control/* (Interactive Triggers)"| API

    API <--> COORDINATOR
    COORDINATOR <--> ENGINES
    COORDINATOR <--> FED
    COORDINATOR <--> WORLD

    API -.->|"NGSIv2 Sensor Updates"| ORION
    ORION <--> MONGO
```

---

## 3. C4 Level 3: Component Diagram (Backend Core)

Focuses on the internal class design and threading synchronization between the background co-simulation loop and concurrent FastAPI request handlers:

```mermaid
flowchart LR
    subgraph RequestHandlers["FastAPI Async Handlers (AsyncIO Worker Pool)"]
        REQ_STATIC["get_static_layers()"]
        REQ_STREAM["stream_dashboard_state()<br/>(Per-Client Generator)"]
        REQ_SELECT["select_map_object()"]
        REQ_BOUSS["get_boussinesq_stress()"]
    end

    subgraph CoreLock["Thread Synchronization Barrier"]
        LOCK["threading.RLock()"]
    end

    subgraph SimulationLoop["Background Simulation Thread (Daemon)"]
        LOOP["DigitalShadow.workflow()<br/>(5.0 s Loop Cadence)"]
        TRAFFIC["TrafficManagement<br/>• Max-50 Inactive Eviction<br/>• Axle Kinematics"]
        WORLD_COMP["World<br/>• 1,215 Road Points<br/>• Dirty Version Monotonic Counter<br/>• UAV Mission FSM"]
        HPN_COMP["HeraklitHPNController<br/>• M_RSU @ M_Mat @ M_Veh<br/>• Dynamic Mixin Synthesis"]
        FED_COMP["CorridorFederationManager<br/>• DynamicFederationContract<br/>• Handover & Sync"]
    end

    REQ_STATIC -->|"Read GIS Geometry"| WORLD_COMP
    REQ_STREAM -->|"get_dirty_segments_since(client_ver)"| WORLD_COMP
    REQ_STREAM -->|"Atomic Snapshot"| LOCK
    REQ_SELECT -->|"Inspect Entity"| LOCK
    REQ_BOUSS -->|"Analytical Half-Space Calc"| ENGINES

    LOOP -->|"Acquires Lock during step"| LOCK
    LOOP --> TRAFFIC
    LOOP --> WORLD_COMP
    LOOP --> HPN_COMP
    LOOP --> FED_COMP
```

---

## 4. Workflow 1: Multi-Rate Co-Simulation & Multi-Client SSE Stream

Illustrates the execution timing, thread synchronization, atomic reference updates, and multi-client non-destructive SSE streaming:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '13.5px', 'fontFamily': 'Inter, sans-serif'}, 'sequence': {'actorFontSize': 14, 'messageFontSize': 13, 'noteFontSize': 12, 'useMaxWidth': false}}}%%
sequenceDiagram
    autonumber
    participant ClientA as "Browser Tab A (Operator)"
    participant ClientB as "Browser Tab B (Projector)"
    participant SSE as "FastAPI SSE Handler"
    participant World as "World (world.py)"
    participant Sim as "DigitalShadow.workflow (Daemon)"

    Note over ClientA,ClientB: Both clients connected to GET /dashboard/stream
    ClientA->>SSE: Connect (client_a_ver = 10)
    ClientB->>SSE: Connect (client_b_ver = 10)

    loop Every 5.0 Seconds (Co-Simulation Step)
        Sim->>Sim: Update weather & vehicle kinematics
        Sim->>World: Detect heavy truck pass over Segment #42
        Sim->>World: mark_segment_dirty("seg_42", new_state=78)
        Note over World: dirty_version incremented (10 -> 11)<br/>_dirty_segments["seg_42"] = (11, 78)
        Sim->>Sim: Build new GeoJSON feature lists locally
        Sim->>Sim: Atomic reference swap: self.vehicles_geojson = new_dict
    end

    par Client A Stream Poll
        SSE->>World: get_dirty_segments_since(since_version=10)
        World-->>SSE: returns (cur_version=11, { "seg_42": 78 })
        SSE-->>ClientA: data: { is_delta: true, dirty_segments: { "seg_42": 78 } }
        Note over ClientA: Mutates cached road_segments in-place<br/>Color shifts Green -> Orange
        Note over SSE: client_a_ver updated to 11
    and Client B Stream Poll (No Starvation!)
        SSE->>World: get_dirty_segments_since(since_version=10)
        World-->>SSE: returns (cur_version=11, { "seg_42": 78 })
        SSE-->>ClientB: data: { is_delta: true, dirty_segments: { "seg_42": 78 } }
        Note over ClientB: Receives same delta! Both screens stay synced.
        Note over SSE: client_b_ver updated to 11
    end

    Note over ClientA,ClientB: Between 5s SSE ticks, browser runs 60 FPS requestAnimationFrame dead-reckoning
```

---

## 5. Workflow 2: IEEE 1516 HLA / FOM Federation Contract Lifecycle

Illustrates how an in-transit vehicle negotiates, maintains, and hands over simulation contracts with Roadside Units along the corridor:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '13.5px', 'fontFamily': 'Inter, sans-serif'}, 'sequence': {'actorFontSize': 14, 'messageFontSize': 13, 'noteFontSize': 12, 'useMaxWidth': false}}}%%
sequenceDiagram
    autonumber
    participant Veh as "Vehicle Federate (Δt = 0.05 s)"
    participant CFM as "CorridorFederationManager"
    participant RSU1 as "RSU-01 Edge Node (km 10.0)"
    participant RSU2 as "RSU-02 Edge Node (km 20.0)"

    Note over Veh: Vehicle #101 approaches km 8.5 (dist = 1.5 km, RSSI = -68 dBm)
    Veh->>CFM: sync_vehicle_contract(veh_101)
    CFM->>RSU1: Negotiate Contract (IEEE 1516 Interaction: ContractNegotiation)
    RSU1-->>CFM: Contract Established: HLA-RSU_01-V0101 (SLA Threshold = 0.90)
    CFM-->>Veh: Contract Active: ACTIVE_FAST_SLOW_SYNC

    loop Every 5s Co-Simulation Tick
        RSU1->>Veh: FastSlowBoundarySync (Pushes WeatherState, AirTemp, SurfaceTemp)
        Veh->>Veh: Evaluate Multi-Axle Kinematic Load Transfer
        Veh->>Veh: Boussinesq Surface Stress & Strain Calculation
        Veh->>RSU1: Publish Kinematic Telemetry (Speed, Weight, DamageIncrement)
    end

    alt Surrogate Accuracy Drops (Acc < 0.90)
        Veh->>CFM: Accuracy = 0.88 (< 0.90 SLA Limit)
        CFM->>RSU1: Trigger Interaction: FOMBasisRecalibration
        Note over Veh,RSU1: Executes full-order FEM fallback step & resets POD basis
        CFM-->>Veh: Accuracy restored to 0.99
    end

    Note over Veh: Vehicle crosses km 15.0 boundary into RSU-02 coverage
    Veh->>CFM: sync_vehicle_contract (Nearest RSU is now RSU-02)
    CFM->>RSU1: Terminate Cell Session (Log Handover Interaction)
    CFM->>RSU2: Establish Downstream Contract (HLA-RSU_02-V0101)
    CFM-->>Veh: State: CELL_HANDOVER -> ACTIVE_FAST_SLOW_SYNC
```

---

## 6. Workflow 3: Automated Pavement Anomaly Detection & UAV Drone Dispatch

Illustrates the physical-to-digital trigger pipeline: from excessive axle load on high-temperature asphalt to autonomous drone verification:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '13.5px', 'fontFamily': 'Inter, sans-serif'}, 'sequence': {'actorFontSize': 14, 'messageFontSize': 13, 'noteFontSize': 12, 'useMaxWidth': false}}}%%
sequenceDiagram
    autonumber
    participant HGV as "Heavy Freight Truck (40 t)"
    participant World as "World Simulator"
    participant Warning as "Warning FSM"
    participant Drone as "AerialDrone FSM"
    participant Map as "Frontend Canvas Map"

    HGV->>World: Rolls over Segment #24 (Asphalt Surface Temp = 49.5°C)
    World->>World: Calculate Cumulative Rutting Stress (DamageIncrement = 0.42)
    World->>Warning: Threshold Exceeded (Cumulative rutting depth > 15 mm)

    Warning->>Warning: Register Anomaly: Warning #07<br/>("Viscoelastic Rutting Hotspot" @ km 42.4, Severity: HIGH)
    World->>Drone: Request Aerial Inspection Dispatch(km 42.4)

    Drone->>Drone: Transition: IDLE -> EN_ROUTE
    Note over Drone: UAV departs maintenance depot @ 15 m/s

    World->>Map: SSE Delta: Drone position & Warning marker updated
    Note over Map: Pulsing red anomaly badge rendered on map, drone flight path visualized

    Drone->>Drone: Arrives at km 42.4 (Transition: EN_ROUTE -> INSPECTING)
    loop Hover & Photogrammetry Scan (4 Ticks)
        Drone->>Drone: Optical & Thermal Sensor Scan (Progress: 25% -> 50% -> 100%)
    end

    Drone->>Warning: Inspection Complete (Ground truth confirmed: 16.2 mm rutting)
    Warning->>Warning: State: NEW -> INSPECTED
    Drone->>Drone: Transition: INSPECTING -> RETURNING
    Drone->>Drone: Lands at depot (State: IDLE)

    World->>Map: SSE Delta: Warning #07 color shifts Red -> Green (Inspected)
```

---

## 7. Architectural Quality Attributes & Guarantees

| Quality Attribute | Architectural Mechanism | Concrete Metric / Benchmark |
| :--- | :--- | :--- |
| **Interactive Responsiveness** | HTML5 Canvas rendering (`preferCanvas: true`) + Offscreen `ImageData` buffer | **60 FPS** map interpolation and **< 2 ms** canvas redraws (11,200–12,800 cells) |
| **Bandwidth Efficiency** | Dynamic delta SSE stream (`/dashboard/stream`) separated from static GIS layers | **~22.9 KB** default 10-vehicle delta vs. **~2.0 MB** static GeoJSON (`road_segments` + `road_curves`) |
| **Multi-Client Concurrency** | Monotonic versioned queries (`get_dirty_segments_since`) + atomic reference swaps | Lock-isolated delta delivery across concurrent browser sessions |
| **Memory Stability** | Bounded vehicle cache (`maxlen=50`) + sliding window weather statistics (`maxlen=100`) | Bounded in-memory buffers across continuous simulation loops |
| **Bundle Performance** | Async component code-splitting (`defineAsyncComponent`) on drawer views | **~383 kB** entry chunk (`~109 kB` gzip) with lazy chunks for 2D/3D viewers, charts, and docs |
| **Multi-Scale Simulation** | Decoupled IEEE 1516 HLA / FOM contracts | **100:1 multi-rate ratio** (5.0 s environment ⇄ 0.05 s vehicle) |
| **Formal Soundness** | Pure-Python Wolfgang Reisig Heraklit module algebra ($M_1 \bullet M_2$) | Associative interface gate fusion with zero external C++ dependencies |
