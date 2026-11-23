# Digital Shadow Coordinator

The `DigitalShadow` class in `digital_shadow.py` acts as the central coordinator binding the physical simulation engines, traffic generators, environmental nodes, and thread-safe API readers.

---

## Class Definition

### `class digital_shadow.DigitalShadow(fiware_flag: bool = False)`

Coordinates continuous multi-rate simulation workflows, thread-safe GeoJSON state management, and polymorphic entity inspection.

* **Parameters:**
  - `fiware_flag` (*bool*): Whether to connect to the external FIWARE Orion Context Broker.

* **Attributes:**
  - `simulation_speed_multiplier` (*float*): Speed scaling multiplier ($0.25\times \text{ to } 10.0\times$) controlling the sleep interval of the continuous simulation loop. Default: `1.0`.
  - `vehicles_geojson` (*Dict[str, Any]*): GeoJSON FeatureCollection representing all active vehicles on the highway. Updated atomically via local list construction and reference swapping.
  - `drone_geojson` (*Dict[str, Any]*): GeoJSON FeatureCollection representing active autonomous inspection UAV drones.
  - `warning_geojson` (*Dict[str, Any]*): GeoJSON FeatureCollection representing registered structural and hydrological road warnings.
  - `active_selected_vehicle_id` (*Optional[Any]*): Tracks the currently inspected vehicle ID. Multi-axle kinematic load transfer is evaluated strictly for this active vehicle in the continuous loop to maintain zero fleet overhead.

---

## Core Methods

### `DigitalShadow.workflow() -> None`

Continuous background simulation thread loop running at a baseline cadence of 5.0 seconds. Acquires `self._lock` (a `threading.RLock`) during the discrete execution step:

1. Advances weather states via multinomial Markov transitions (`world.update_weather_state`).
2. Updates vehicle positions and spawns new corridor traffic (`traffic_management`).
3. Evaluates 1D thermal finite-element diffusion and pavement wear (`simpl.simulation_pipeline`).
4. Applies physical damage to road segments (`world.update_road_state`).
5. Handles structural warnings and dispatches UAV drones (`world.warning_handling`).
6. Rebuilds GeoJSON collections atomically (`update_geojson_snapshots()`).

---

### `DigitalShadow.update_geojson_snapshots() -> None`

Evaluates multi-axle kinematic load transfer for the selected vehicle, snapshots active vehicle parameters, and constructs a new `vehicles_geojson` dictionary in local memory before assigning the reference atomically.

---

### `DigitalShadow.inspect_object(active_selection: Dict[str, Any]) -> Tuple[...]`

Polymorphic entity reader invoked by `POST /dashboard/select_object`. Evaluates the Heraklit Petri Net composition, synthesizes the active Python Mixin class source code, and builds the inspector telemetry dictionary for any clicked map entity.
