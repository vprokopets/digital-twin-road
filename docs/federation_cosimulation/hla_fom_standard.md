# IEEE 1516 High-Level Architecture (HLA) & FOM

The **High-Level Architecture (HLA)** is an international IEEE standard (IEEE 1516-2010) for distributed, heterogeneous simulation modeling. In this platform, HLA provides the formal semantic model and object dictionary for multi-rate co-simulation between roadside edge infrastructure and moving freight fleets.

---

## Federation Object Model (FOM) Specification

The federation schema is formally defined in `configs/fom_schema.json`:

```json
{
  "federation_name": "A14_Corridor_Road_Federation",
  "hla_standard": "IEEE 1516-2010 + Heraklit Module Composition",
  "time_management": {
    "coupling_scheme": "Multi-Rate Fast-Slow Co-Simulation",
    "slow_scale": {
      "owner": "RSU_Environment_Federate",
      "step_sec": 5.0
    },
    "fast_scale": {
      "owner": "Vehicle_Mechanical_Federate",
      "step_sec": 0.05
    }
  }
}
```

---

## HLA Object Classes

The FOM defines two primary continuous object classes exchanged between federates:

### 1. `EnvironmentBoundaryState`

* **Publisher:** `RSU_Environment_Federate` (Roadside Units).
* **Subscriber:** `Vehicle_Mechanical_Federate` (Freight Vehicles).
* **Heraklit Gate:** $\beta(M_{\text{RSU}}) \equiv \alpha(M_{\text{Vehicle}})$.
* **Attributes:**
  - `WeatherState`: Discrete categorical state (`Sunny`, `Cloudy`, `Rainy`, `Snowy`).
  - `AirTemperature`: Continuous fluid level (°C).
  - `RoadSurfaceTemperature`: Continuous fluid level (°C).
  - `SoilTemperature`: Continuous fluid level (°C).
  - `RoadStructure`: Categorical configuration token (`RoadStructure_0..4`).

### 2. `VehicleKinematicTelemetry`

* **Publisher:** `Vehicle_Mechanical_Federate`.
* **Subscriber:** `RSU_Environment_Federate`.
* **Heraklit Gate:** $\beta(M_{\text{Vehicle}}) \equiv \alpha(M_{\text{RSU}})$.
* **Attributes:**
  - `Kilometer`: Current station chainage along corridor (km).
  - `Velocity`: Instantaneous velocity (km/h).
  - `Weight`: Dynamic gross vehicle mass (kg).
  - `SolverMode`: Active solver feature (`POD` vs. `FEM`).
  - `PODAccuracy`: Current projection confidence ratio ($0.0 \text{ to } 1.0$).
  - `DamageIncrement`: Pavement strain damage index imparted to the current segment.

---

## HLA Interaction Classes

Interactions represent discrete, asynchronous protocol events between federates:

| Interaction Class | Trigger Precondition | Functional Responsibility |
| :--- | :--- | :--- |
| `ContractNegotiation` | $\text{dist} \le 10\,\text{km} \land \text{RSSI} \ge -85\,\text{dBm}$ | Initial bilateral handshake when a vehicle joins an RSU's V2X wireless coverage cell. |
| `FastSlowBoundarySync` | Periodic ($5.0\,\text{s}$ tick) | Pushes slow-scale RSU thermal and moisture states into the vehicle's fast-scale mechanical solver. |
| `FOMBasisRecalibration` | $\text{Accuracy} \le 0.90$ | Triggered when surrogate error exceeds 10%; executes a full-order calibration step and resets the surrogate basis. |
| `CellHandover` | $\text{dist}(\text{RSU}_{\text{down}}) < \text{dist}(\text{RSU}_{\text{curr}})$ | Seamless session migration from current RSU to downstream RSU across highway cell boundaries. |
