# Concurrency, Streaming & Multi-Client Safety

A central challenge in real-time cyber-physical digital twins is synchronizing continuous background physics simulation loops with asynchronous multi-client web requests without blocking the event loop, causing race conditions, or starving concurrent browser sessions.

---

## The Multi-Client Starvation Problem

In earlier versions of the backend, dirty road segments were tracked in a single global dictionary:

```python
# Antipattern: Destructive Global Clear
dirty = dict(shadow_instance.world.dirty_segments)
shadow_instance.world.dirty_segments.clear()
```

### The Concurrency Defect
If an engineer opened the dashboard in two browser tabs simultaneously (e.g. on an operator laptop and on an overhead auditorium display), each tab ran an independent `EventSource` connection generator. Whichever client's async generator woke up first read and cleared `dirty_segments`. The second client received an empty dictionary (`{}`) and failed to update road degradation colors on the map.

---

## The Monotonic Version Solution

To resolve this defect, the `World` class introduces monotonic version tracking:

```python
class World:
    def __init__(self, ...):
        self._dirty_segments: Dict[str, Tuple[int, int]] = {}  # id -> (version, state)
        self.dirty_version: int = 0
        self._dirty_lock = threading.Lock()

    def mark_segment_dirty(self, seg_id: str, new_state: int) -> None:
        with self._dirty_lock:
            self.dirty_version += 1
            self._dirty_segments[seg_id] = (self.dirty_version, new_state)

    def get_dirty_segments_since(self, since_version: int = 0) -> Tuple[int, Dict[str, int]]:
        with self._dirty_lock:
            cur_ver = self.dirty_version
            if since_version >= cur_ver:
                return cur_ver, {}
            deltas = {
                seg_id: state
                for seg_id, (ver, state) in self._dirty_segments.items()
                if ver > since_version
            }
            return cur_ver, deltas
```

In the SSE stream handler (`dashboard_backend.py`), each client connection maintains its own independent `client_dirty_version` cursor:

```python
@app.get("/dashboard/stream")
async def stream_dashboard_state(request: Request) -> StreamingResponse:
    async def event_generator():
        client_dirty_version = shadow_instance.world.dirty_version if shadow_instance else 0
        while True:
            if await request.is_disconnected():
                break
            delta_data, client_dirty_version = get_dynamic_delta_state(since_version=client_dirty_version)
            yield f"data: {json.dumps(delta_data)}\n\n"
            mult = shadow_instance.simulation_speed_multiplier if shadow_instance else 1.0
            sleep_time = max(0.5, 5.0 / max(0.25, mult))
            await asyncio.sleep(sleep_time)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### Concurrency Guarantees

* **Zero Starvation:** Any number of concurrent browser clients, projectors, and mobile displays receive all delta updates.
* **Non-Destructive Reads:** Historical entries remain in memory without requiring a destructive clear.
* **Bounded Footprint:** Because highway road segments are fixed in number (1,215 segments), `_dirty_segments` is strictly bounded to the total segment count (~40 kB in RAM).

---

## Thread Safety & Atomic Reference Swapping

In `digital_shadow.py`, the continuous simulation loop runs in a background Python thread:

```python
class DigitalShadow:
    def __init__(self, ...):
        self._lock = threading.RLock()

    def workflow(self) -> None:
        while True:
            time.sleep(sleep_sec)  # Sleep happens outside lock!
            with self._lock:
                # Execute simulation step
                self.world.update_weather_state(...)
                self.traffic_management.update_vehicles_state()
                ...
                self.update_geojson_snapshots()
```

### Atomic Reference Swapping
When constructing GeoJSON layers (`vehicles_geojson`, `drone_geojson`, `warning_geojson`), the lists are built in local memory first and assigned in a single atomic pointer swap:

```python
# Local construction prevents readers from seeing empty or partially populated features
features = []
for vid, point in vehicle_raw.items():
    features.append({...})

self.vehicles_geojson = {
    "type": "FeatureCollection",
    "features": features,
}
```

In CPython, assigning an object attribute (`STORE_ATTR`) is an atomic bytecode operation. Concurrent FastAPI async workers will always observe either the complete previous state or the complete new state—never a half-populated array.
