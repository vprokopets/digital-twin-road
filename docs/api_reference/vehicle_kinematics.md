# Vehicle Kinematics & Drone Inspection (`vehicle/`)

The `vehicle/` package models multi-axle freight chassis kinematics, dynamic pitch load transfers, structural warning classification, and autonomous UAV drone inspection missions.

---

## Vehicle Kinematic Chassis

### `class vehicle.vehicle.Vehicle(...)`

Represents a moving vehicle on the highway corridor.

#### `Vehicle.compute_kinematic_axles() -> Dict[str, Any]`

Evaluates dynamic vertical load distributions across multi-axle chassis configurations (`HGV_CLASSES` in `vehicle/vehicle.py`):

* **5-Axle Semi-Trailer (EU 40t standard):**
  EU Class N3 (`2+3 Axle`): Steer Axle + Drive Axle + Tridem Semitrailer.

* **4-Axle Heavy Dumper (36t):**
  EU Class N3 (`2+2 Axle`): Steer Tandem + Drive Tandem.

* **6-Axle Low-Loader HGV (44t):**
  EU Class N3 (`3+3 Axle`): Tri-Axle Tractor + Trailer Tridem.

#### Dynamic Pitch Weight Transfer
Under acceleration $a$ or road slope $\theta$, longitudinal inertia and gravity shift vertical load between front and rear axle groups:

$$\Delta P_{\text{pitch}} = M \cdot (a + g \sin\theta) \cdot \frac{h_{\text{CG}}}{L_{\text{wb}}}$$

where:

* $\Delta P_{\text{pitch}}$: Longitudinal pitch weight transfer force shifted between front and rear axle groups ($\text{kN}$ when converted via $W_{\text{total}} = M g / 1000$).
* $M$: Gross vehicle mass ($\text{kg}$).
* $a$: Instantaneous longitudinal acceleration ($\text{m/s}^2$), computed from consecutive velocity samples as $(v_t - v_{t-\Delta t}) / (3.6\,\Delta t)$ over the $\Delta t = 5\,\text{s}$ co-simulation step.
* $g = 9.81\,\text{m/s}^2$: Standard gravitational acceleration.
* $\theta$: Local longitudinal road grade angle ($\sin\theta \approx \text{slope\_pct}/100$).
* $h_{\text{CG}}$: Assumed freight center-of-gravity height above the road surface ($1.8\,\text{m}$ reference).
* $L_{\text{wb}}$: Effective chassis wheelbase length ($6.5\,\text{m}$ reference).

In `vehicle/vehicle.py` (`compute_kinematic_axles`), this rigid-body transfer is scaled by a $0.45$ suspension-damping factor and distributed across axle groups as front unloading ($\Delta P_{\text{steer}} = -0.5\,\Delta P_{\text{pitch}}$) and rear loading ($\Delta P_{\text{drive}} = +0.6\,\Delta P_{\text{pitch}}$, with $+0.4\,\Delta P_{\text{pitch}}$ shared across trailing axles).

#### Velocity Dynamic Load Coefficient (DLC)
Models speed-induced vertical tire-force amplification excited by ISO 8608 highway surface roughness:

$$\text{DLC} = 0.05 \cdot \left(\frac{v}{80\,\text{km/h}}\right)^{1.3}$$

where:

* $\text{DLC}$: Dimensionless Dynamic Load Coefficient giving the fractional speed-dependent surcharge above static/pitched load.
* $v$: Instantaneous cruising velocity ($\text{km/h}$).
* $0.05$: Baseline $5\%$ dynamic amplification at the $80\,\text{km/h}$ heavy-freight reference speed.
* $1.3$: Empirical roughness velocity sensitivity exponent.

#### Resulting Dynamic Axle Load & ESAL Factor
Combining pitch weight transfer with the velocity dynamic load factor yields each axle's effective dynamic load $P_{\text{dyn}, i}$, Dynamic Impact Factor $\text{DIF}_i$, and pavement fatigue equivalence $\text{ESAL}_i$:

$$P_{\text{dyn}, i} = \max\!\Big(30\,\text{kN},\; (P_{\text{stat}, i} + \Delta P_i) \cdot (1 + \text{DLC})\Big), \qquad \text{DIF}_i = \frac{P_{\text{dyn}, i}}{P_{\text{stat}, i}}, \qquad \text{ESAL}_i = \left(\frac{P_{\text{dyn}, i}}{100\,\text{kN}}\right)^{4}$$

where:

* $P_{\text{stat}, i}$: Static load share on axle $i$ derived from gross vehicle weight and the chassis configuration in `HGV_CLASSES` ($\text{kN}$).
* $\Delta P_i$: Group-specific longitudinal pitch weight transfer assigned to axle $i$ ($\text{kN}$).
* $P_{\text{dyn}, i}$: Resulting dynamic axle load ($\text{kN}$), clamped below at a $30\,\text{kN}$ minimum contact floor.
* $\text{DIF}_i$: Dynamic Impact Factor measuring the instantaneous ratio of dynamic to static axle load.
* $\text{ESAL}_i$: Equivalent Single Axle Load damage factor from the AASHTO Fourth Power Law relative to a $100\,\text{kN}$ standard axle.

---

## Autonomous UAV Inspection Drone

### `class vehicle.aerial_drone.AerialDrone(position_lon_lat: List[float], simulation_interval: float = 5.0, rsu_id: str = "rsu_00", rsu_name: str = "RSU Hub", drone_index: int = 1)`

Autonomous UAV quadcopter state machine performing photogrammetry over structural highway anomalies.

* **`state` (*str*):**
  Operational state: `"Idle"` | `"Liftoff"` | `"CruisingToward"` | `"DescendToInspect"` | `"Inspecting"` | `"AscendToCruise"` | `"CruisingBack"` | `"Landing"`.

* **`establish_inspection_task(warning_obj: Warning) -> None`:**
  Assigns an inspection target coordinate and `warning_obj`, transitioning state from `"Idle"` to `"Liftoff"`.

* **`action_loop() -> None`:**
  Advances multi-altitude drone flight physics: vertical climb to $50\,\text{m}$ transit altitude, verge cruise to the anomaly, descent to $18\,\text{m}$ inspection altitude, hovering LiDAR/photogrammetry scan, and return/landing at the home RSU pad.

---

## Structural Road Warnings

### `class vehicle.warning.Warning(...)`

Represents a detected highway defect or environmental hazard.

* **`state` (*str*):**  
  Progress state: `"New"` (Red pulse on map) $\to$ `"Under Inspection"` (Amber) $\to$ `"Inspected"` (Green).
