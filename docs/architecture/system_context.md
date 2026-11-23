# System Context & C4 Level 1

The **System Context** defines the operational boundaries of the Digital Twin Road Platform, demonstrating how physical highway infrastructure, connected freight fleets, edge Roadside Units (RSUs), and human operators interact with the core digital shadow.

---

## Conceptual Context Model

```text
+---------------------------------------------------------------------------------+
|                           HIGHWAY OPERATIONS ACTORS                             |
|                                                                                 |
|   [ Highway Traffic Operator ]                  [ Chief Civil Maintenance Eng. ]|
|   • Real-time corridor telemetry                • 15-year pavement degradation  |
|   • V2X Edge link monitoring                    • Rutting & structural warnings |
+-----------------------+---------------------------------+-----------------------+
                        |                                 |
                        | Visual Dashboard & Web UI       | Degradation Prognosis
                        v                                 v
+---------------------------------------------------------------------------------+
|                 DIGITAL TWIN ROAD PLATFORM (CORE SYSTEM)                        |
|                                                                                 |
|   • 60 FPS Canvas GIS & Trajectory Dead-Reckoning Engine                        |
|   • Analytical 2D Boussinesq & Westergaard Elastostatic Stress & Deflection     |
|   • 1D Thermal Finite-Element Subsurface Heat Conduction                        |
|   • Wolfgang Reisig's Heraklit Compositional Hybrid Petri Net Engine            |
|   • IEEE 1516 HLA / FOM Dynamic Federation SLA Contracts                        |
|   • Monotonic Versioned Non-Destructive SSE Delta Broadcast                     |
+-------^-----------------------^-------------------------^-----------------------+
        |                       |                         |
        | Telemetry Stream      | SWIS Micro-Climate Logs | Dispatch Commands & Ground-Truth
        |                       |                         |
+-------+-----------+   +-------+-----------+     +-------+-----------+
| CONNECTED FLEET   |   | ROADSIDE UNITS    |     | AUTONOMOUS FLEET  |
| • Multi-Axle HGVs |   | • 10 km RSU Cells |     | • UAV Drones      |
| • Dynamic Pitch & |   | • Air & Surface   |     | • Optical/Thermal |
|   Axle Transfers  |   |   Pyrometers      |     |   Photogrammetry  |
| • WIM Piezo Weight|   | • Edge Computing  |     | • Automated Depot |
+-------------------+   +-------------------+     +-------------------+
```

---

## Primary External Actors & Interfaces

1. **Connected Freight Fleet (HGVs, Semi-Trailers, Vans):**  
   Vehicles traversing the corridor broadcast dynamic kinematic telemetry (speed, GPS coordinates, gross vehicle weight, axle configurations) over simulated V2X wireless links. Dynamic pitch transfers under braking and acceleration shift vertical wheel loads onto the pavement structure.

2. **Roadside Units (RSUs) & Meteorological Edge Nodes:**  
   Positioned along the highway corridor at 5–10 km intervals, RSUs host local SWIS (*Straßenwetter-Informationssystem*) stations measuring ambient air temperature, surface temperature, and subgrade moisture. Each RSU acts as an independent edge simulation federate.

3. **Pavement Infrastructure (1,215 Segments):**  
   The highway is divided into discrete 100–250 m segments. Each segment maintains dynamic structural health indicators, cumulative equivalent single-axle loads (ESAL), and plastic rutting depth forecasts.

4. **Autonomous UAV Inspection Fleet:**  
   High-severity structural alerts (such as excessive viscoelastic deformation under elevated surface temperatures) trigger autonomous UAV drones from regional maintenance depots to conduct low-altitude optical and thermal photogrammetry missions.
