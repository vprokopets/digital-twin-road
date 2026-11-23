# Backend API & Endpoints

The FastAPI application in `dashboard_backend.py` provides the central REST interface and Server-Sent Events (SSE) stream for the digital twin platform.

---

## Application Configuration & Lifespan

The application uses Starlette / FastAPI's modern `lifespan` async context manager, managing the background simulation thread lifecycle cleanly on server startup and shutdown:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Probe FIWARE connectivity; fallback to Native Broker if offline
    # 2. Instantiate DigitalShadow coordinator
    # 3. Start background simulation daemon thread
    yield
    # Graceful teardown on shutdown
```

---

## CORS Security Configuration

In compliance with W3C specifications, explicit allowed origins and localhost regex matching are enforced without wildcard credential conflicts:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Core Endpoints

### `GET /` & `GET /health`

Liveness (`GET /`) and readiness (`GET /health`) endpoints returning service metadata (`HTTP 200` when the background simulation loop is healthy, `HTTP 503` when uninitialized or unhealthy).

---

### `GET /dashboard/static_layers`

Returns the heavy static GIS geospatial layers once at application startup.

* **Response Headers:** `Content-Type: application/json`
* **Response JSON Object:**
  - `status` (*string*): `"ok"`
  - `coordinate_system` (*object*): Active coordinate reference metadata (`WGS84` or `LocalCartesian`).
  - `federation_summary` (*object*): Active contracts count and sync counters.
  - `map_layers` (*object*): FeatureCollections for `road`, `road_curves`, `road_segments`, `lane_polygons`, `road_config`, `water`, `spawn`, `ru`, and `embedded_sensors`.

---

### `GET /dashboard/stream`

Server-Sent Events (SSE) delta stream delivering 5-second dynamic corridor updates.

* **Response Headers:** `Content-Type: text/event-stream`, `Cache-Control: no-cache`
* **Stream Payload Schema:**

```json
{
  "status": "ok",
  "is_delta": true,
  "sim_speed": 1.0,
  "federation_summary": { ... },
  "dirty_segments": { "seg_42": 78, "seg_43": 92 },
  "rsu_live": {
    "rsu_01": {
      "WeatherState": "Sunny",
      "AirTemperature": 22.4,
      "RoadSurfaceTemperature": 26.8,
      "ActiveContracts": 2
    }
  },
  "map_layers": {
    "vehicles": { "type": "FeatureCollection", "features": [ ... ] },
    "drones": { "type": "FeatureCollection", "features": [ ... ] },
    "warnings": { "type": "FeatureCollection", "features": [ ... ] }
  }
}
```

---

### `GET /dashboard/boussinesq_stress`

Calculates analytical 2D Boussinesq elastostatic stress tensors and surface deflection basins.

* **Query Parameters:**
  - `axle_load_kn` (*float*): Gross axle load in kilonewtons (default: `115.0`).
  - `tire_config` (*string*): `"single"` or `"dual"` (default: `"dual"`).
  - `contact_pressure_kpa` (*float*): Tire contact pressure in kilopascals (default: `750.0`).
* **Response JSON Object:**
  - `status` (*string*): `"success"`
  - `contact_radius_m` (*float*): Derived circular tire footprint radius ($a$).
  - `x_coords` (*list[float]*): Lateral cross-section coordinates ($-1.5\,\text{m to } +1.5\,\text{m}$).
  - `z_coords` (*list[float]*): Subsurface depth coordinates ($0.005\,\text{m to } 1.50\,\text{m}$).
  - `sigma_z` (*list[list[float]]*): 2D vertical stress matrix ($40 \times 60$).
  - `w_z` (*list[list[float]]*): 2D displacement matrix ($40 \times 60$).
  - `tau_max` (*list[list[float]]*): 2D maximum shear stress matrix ($40 \times 60$).

---

### `POST /dashboard/select_object`

Polymorphic entity inspection endpoint returning tailored telemetry for all 8 GIS map entity types (including `EmbeddedSensor` / `SingleEmbeddedSensorStateDS`).

* **Request Body JSON:**

```json
{
  "selection_type": "SingleVehicleStateDS",
  "feature_data": { "id": "HGV-101", ... }
}
```

* **Response JSON Object:**
  - `panel` (*object*): Structured domain inspector payload (`panel_type`).
  - `metadata` (*object*): Active FODA feature tree / entity metadata.
  - `properties` (*object*): Entity telemetry attributes.
  - `stats` (*object*): Time-series historical records.
  - `columns` (*list[string]*): Time-series column headers.
  - `hpn_graph` (*object*): Composed Heraklit Petri Net nodes and edges for Vue Flow.
  - `code` & `mech_code` (*string*): Synthesized Python Mixin class source code.
  - `federation_contract` (*object*): Bilateral HLA contract terms, RSSI, and SLA status.

---

### `GET /api/engine/status` *(Experimental Extension Seam)*

Exposes the pluggable model-engine contract (`SimPLs/engine_contract.py`), allowing the Python simulation pipeline to delegate batch thermal/mechanical step requests to an external HTTP solver sidecar (with automatic local fallback).

---

### `POST /dashboard/thermal_distribution`

Computes steady-state 1D depth temperature profiles and layer heat flux across a stratified RStO 12 pavement column.

* **Request Body JSON:**
  - `surface_temp` (*float*): Top wearing-course temperature (°C).
  - `soil_temp` (*float*): Deep subgrade boundary temperature at $z = 1.5\,\text{m}$ (°C).
  - `road_structure` (*object*): Ordered `Layer_0..Layer_N` definitions with layer thickness `Length` ($\text{m}$) and `ThermalConductivity` ($\text{W}/(\text{m}\cdot\text{K})$).
* **Response JSON Object:** Per-layer boundary temperatures, conductive heat flux ($\text{W/m}^2$), and thermal properties table for `ThermalSimulation.vue`.

---

### Data Broker & FIWARE Context API

* `GET /dashboard/fiware_status`: Returns active context broker driver (`native` vs. `fiware`), health flag, `openiot` service scope, and configured Orion / IoT Agent / FastAPI ingest endpoints.
* `GET /dashboard/fiware_entities`: Lists all curated entity snapshots (`Vehicle`, `Roadside_unit`, and registered sensors) from the active broker.
* `GET /dashboard/fiware_entities/{entity_id}`: Resolves a single entity by ID from the active broker (with Orion NGSIv2 fallback and `404` when absent).
* `GET /dashboard/fiware_entities/{entity_id}/history`: Returns bounded recent telemetry snapshots (`limit` clamped to `1..500`) for time-series inspection.

---

### Documentation Catalog & Notes API (`api/docs.py`)

* `GET /api/docs`: Lists locked built-in Markdown sections from `zensical.toml` alongside editable custom Markdown notes in `docs/custom/`.
* `GET /api/docs/article?id=...`: Fetches raw Markdown content and metadata (`locked: true` for reference docs, `locked: false` for `custom/<slug>`).
* `POST /api/docs/custom`, `PUT /api/docs/custom/{slug}`, `DELETE /api/docs/custom/{slug}`: File-backed CRUD endpoints for creating, editing, and removing custom Markdown notes.
