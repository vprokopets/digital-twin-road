# World & Highway Corridor (`world/`)

The `world/` package orchestrates the highway corridor geography, Roadside Unit telemetry, probabilistic weather Markov chains, and vehicle traffic generation.

---

## Module Overview

| File | Description |
| :--- | :--- |
| `world/world.py` | Central environment container, 1,215 road points, monotonic dirty segment versioning, UAV drone FSM. |
| `world/road.py` | OpenStreetMap highway geometry interpolation, centerline spline projection, $O(\log M)$ binary search range queries. |
| `world/weather.py` | Markov chain probabilistic micro-climate station with multinomial state sampling. |
| `world/weather_sources.py` | Real-time Raspberry Pi weather station listener (temperature, humidity, lux, barometric pressure). |
| `world/traffic_management.py` | Autonomous vehicle flow orchestration with 50-vehicle LRU eviction and junction route spawning. |
| `world/federation.py` | IEEE 1516 HLA / FOM dynamic simulation contract manager (RTI). |
| `world/geo_utils.py` | Cross-platform geographic bearing, haversine distance, and coordinate interpolation utilities. |

---

## The World Container

### `class world.world.World(params: Dict[str, Any], fiware_flag: bool)`

Manages the highway corridor physical infrastructure, environmental sensor objects, and structural deterioration tracking.

* **`dirty_version` (*int*):**  
  Monotonic sequence counter incremented on every road segment damage mutation.

* **`mark_segment_dirty(seg_id: str, new_state: int) -> None`:**  
  Thread-safe registration of a road segment or point state mutation. Increments `self.dirty_version`.

* **`get_dirty_segments_since(since_version: int = 0) -> Tuple[int, Dict[str, int]]`:**  
  Thread-safe delta query for SSE clients. Returns `(current_version, {id: new_state})` containing only segments mutated after `since_version`.

* **`update_road_state(vehicle_id: Any, vehicle_obj: Any) -> None`:**  
  Progressively evaluates road degradation in the moving traversal window between `vehicle_obj.prev_position` and `vehicle_obj.position`. Adapts wear to local material (Asphalt vs. Concrete) and marks traversed segments dirty.

* **`update_weather_state(timestamp: str) -> None`:**  
  Advances all RSU weather Markov stations and syncs air/surface temperatures onto RSU GeoJSON properties for instant UI access.

* **`prepare_geojson() -> None`:**  
  Builds GeoJSON FeatureCollections for active UAV drones and structural warnings in local memory before atomic reference assignment.
