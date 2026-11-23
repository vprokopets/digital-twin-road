"""
dashboard_backend.py — FastAPI Entrypoint & Backward-Compatible Router Facade
=============================================================================

Project: Digital Twin Road Demonstrator

Mounts the modular FastAPI routers in `api/` (`simulation`, `inspector`,
`telemetry`, `scenarios`, `physics`, `fiware`), manages the `DigitalShadow`
lifespan thread, and re-exports endpoint handlers and request schemas for
backward compatibility with existing tests and `uvicorn dashboard_backend:app`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import threading
from typing import Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.docs import (
    CustomDocCreateRequest,
    CustomDocUpdateRequest,
    create_custom_documentation,
    delete_custom_documentation,
    get_documentation_article,
    list_documentation_catalog,
    router as docs_router,
    update_custom_documentation,
)
from api.fiware import (
    CleanIdleRequest,
    clean_idle_fiware_entities,
    get_data_broker_status_endpoint,
    get_fiware_entities,
    get_fiware_entity,
    get_fiware_entity_history,
    get_fiware_status,
    router as fiware_router,
)
from api.inspector import (
    SelectionRequest,
    _build_inspector_panel,
    router as inspector_router,
    select_map_object,
)
from api.physics import (
    ThermalRequest,
    compute_thermal_distribution,
    get_boussinesq_stress,
    get_engine_status,
    get_prediction_plot,
    router as physics_router,
)
from api.runtime import get_shadow, set_processing_thread, set_shadow
from api.scenarios import (
    AssetUpdateRequest,
    SaveScenarioRequest,
    SwitchScenarioRequest,
    get_scenario_details,
    list_scenarios,
    router as scenarios_router,
    save_scenario_infrastructure,
    switch_scenario,
    update_asset_parameters,
)
from api.simulation import (
    SimSpeedRequest,
    SpawnVehicleRequest,
    TriggerWarningRequest,
    control_sim_speed,
    control_spawn_vehicle,
    control_trigger_warning,
    get_dashboard_state,
    get_dynamic_delta_state,
    get_road_curves,
    get_road_segments,
    get_static_layers,
    router as simulation_router,
    stream_dashboard_state,
)
from api.telemetry import (
    SensorTelemetryRequest,
    get_sensor_telemetry,
    ingest_sensor_telemetry,
    receive_weather_data_from_pi,
    router as telemetry_router,
)
from data_curation.fiware.service_group import activate_persistance_db, register_service_group
from digital_shadow import DigitalShadow


def _load_local_env() -> None:
    """Loads key=value pairs from `.env` if present without overriding existing environment variables."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            if key:
                os.environ.setdefault(key, val)
    except OSError as exc:
        logging.debug("Skipping .env load: %s", exc)


_load_local_env()

shadow_instance: Optional[DigitalShadow] = None
processing_thread: Optional[threading.Thread] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes optional FIWARE persistence and starts the Digital Shadow worker thread."""
    global shadow_instance, processing_thread
    try:
        try:
            from data_curation.fiware.client import get_default_manager

            requested_backend = os.getenv("DATA_BROKER_BACKEND", "").strip().lower()
            probe_retries = 15 if requested_backend == "fiware" else 1

            mgr = get_default_manager()
            if (
                mgr.check_connection(retries=probe_retries, retry_delay=1.0)
                and mgr.check_iot_agent(retries=probe_retries, retry_delay=1.0)
            ):
                ok_v = register_service_group("vehicle", entity_type="Vehicle")
                ok_rs = register_service_group("rs", entity_type="Roadside_unit")
                ok_db = activate_persistance_db()
                fiware_flag = bool(ok_v and ok_rs and ok_db)
            else:
                fiware_flag = False

            if fiware_flag:
                os.environ["DATA_BROKER_BACKEND"] = "fiware"
                logging.info("FIWARE is enabled. Ready to register sensors.")
            else:
                if requested_backend == "fiware":
                    os.environ["DATA_BROKER_BACKEND"] = "native"
                logging.info("FIWARE is offline or unreachable. Proceeding with local Digital Shadow workflow.")
        except Exception as e:
            fiware_flag = False
            logging.info(f"FIWARE is disabled or offline ({e}). Proceeding with local Digital Shadow workflow.")

        shadow_instance = DigitalShadow(fiware_flag)
        set_shadow(shadow_instance)
        processing_thread = threading.Thread(target=shadow_instance.workflow, args=(), daemon=True)
        set_processing_thread(processing_thread)
        processing_thread.start()
    except Exception as e:
        logging.error(f"Failed to initialize Digital Shadow: {e}")
    yield


app = FastAPI(
    title="Digital Twin Road Demonstrator API",
    description="FastAPI backend for Digital Twin Road — Heraklit HPN, External Solver Bridge, HLA/FOM & 2D Mechanics.",
    version="2.0.0",
    lifespan=lifespan,
)

assets_dir = Path(__file__).resolve().parent / "assets"
app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

cors_origins_env = os.getenv("CORS_ORIGINS")
allowed_origins = (
    [o.strip() for o in cors_origins_env.split(",")]
    if cors_origins_env
    else [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> Dict[str, str]:
    """Liveness health-check endpoint returning service metadata."""
    return {"status": "ok", "service": "Digital Twin Road Backend v2.0"}


@app.get("/health", response_model=None)
async def health():
    """Readiness endpoint verifying active Digital Shadow initialization and loop health."""
    shadow = get_shadow() or shadow_instance
    if shadow is None or not getattr(shadow, "sim_healthy", True):
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy" if shadow is not None else "initializing",
                "service": "Digital Twin Road Backend v2.0",
            },
        )
    return {
        "status": "ok",
        "service": "Digital Twin Road Backend v2.0",
        "last_tick_at": getattr(shadow, "last_tick_at", None),
    }


app.include_router(simulation_router)
app.include_router(inspector_router)
app.include_router(telemetry_router)
app.include_router(scenarios_router)
app.include_router(physics_router)
app.include_router(fiware_router)
app.include_router(docs_router)


__all__ = [
    "AssetUpdateRequest",
    "CleanIdleRequest",
    "CustomDocCreateRequest",
    "CustomDocUpdateRequest",
    "SaveScenarioRequest",
    "SelectionRequest",
    "SensorTelemetryRequest",
    "SimSpeedRequest",
    "SpawnVehicleRequest",
    "SwitchScenarioRequest",
    "ThermalRequest",
    "TriggerWarningRequest",
    "_build_inspector_panel",
    "app",
    "clean_idle_fiware_entities",
    "compute_thermal_distribution",
    "control_sim_speed",
    "control_spawn_vehicle",
    "control_trigger_warning",
    "create_custom_documentation",
    "delete_custom_documentation",
    "get_boussinesq_stress",
    "get_dashboard_state",
    "get_data_broker_status_endpoint",
    "get_documentation_article",
    "get_dynamic_delta_state",
    "get_engine_status",
    "get_fiware_entities",
    "get_fiware_entity",
    "get_fiware_entity_history",
    "get_fiware_status",
    "get_prediction_plot",
    "get_road_curves",
    "get_road_segments",
    "get_scenario_details",
    "get_sensor_telemetry",
    "get_static_layers",
    "ingest_sensor_telemetry",
    "lifespan",
    "list_documentation_catalog",
    "list_scenarios",
    "processing_thread",
    "receive_weather_data_from_pi",
    "root",
    "save_scenario_infrastructure",
    "select_map_object",
    "shadow_instance",
    "stream_dashboard_state",
    "switch_scenario",
    "update_asset_parameters",
    "update_custom_documentation",
]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
