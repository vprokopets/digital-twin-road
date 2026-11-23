"""
api/simulation.py — GIS Static Layers, SSE Stream & Interactive Controls Router
===============================================================================

Serves static GIS GeoJSON bundles (`road_curves`, `road_segments`, optional
`lane_polygons`, `embedded_sensors`), lightweight delta SSE updates, and manual
simulation controls (`spawn_vehicle`, `sim_speed`, `trigger_warning`).
"""

from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path
import random
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.runtime import get_shadow
from SimPLs.engine_contract import sanitize_json_payload
from vehicle.warning import Warning
from world.scenario_loader import get_active_scenario

router = APIRouter(tags=["Simulation & GIS"])


@router.get("/dashboard/static_layers")
def get_static_layers() -> Dict[str, Any]:
    """
    Serve static GIS layers once alongside `coordinate_system` metadata.

    Includes `road_curves`, `road_segments`, `road`, `road_config`, `water`,
    `spawn`, `ru`, optional `lane_polygons`, and `embedded_sensors` so the
    frontend can configure WGS84 vs. LocalCartesian projection on initial load.
    """
    shadow = get_shadow()
    if shadow is None:
        return {"status": "initializing"}
    scenario = get_active_scenario()
    return {
        "status": "ok",
        "coordinate_system": scenario.coordinate_system,
        "federation_summary": shadow.world.federation_manager.get_federation_summary(),
        "map_layers": {
            "road": shadow.world.road.road_structure_metadata_processed,
            "road_curves": getattr(shadow.world.road, "road_curves", None),
            "road_segments": getattr(shadow.world.road, "road_segments", None),
            "lane_polygons": scenario.lane_polygons or None,
            "road_config": shadow.world.road_config,
            "water": shadow.world.road_water_metadata,
            "spawn": shadow.world.road_spawn_metadata,
            "ru": shadow.world.roadside_units,
            "embedded_sensors": getattr(shadow.world, "embedded_sensors", None) or scenario.get_embedded_sensors(),
        },
    }


@router.get("/dashboard/state")
def get_dashboard_state() -> Dict[str, Any]:
    """Full dashboard state snapshot (initial load + backwards compatibility)."""
    shadow = get_shadow()
    if shadow is None:
        return {"status": "initializing"}

    try:
        scenario = get_active_scenario()
        return {
            "status": "ok",
            "sim_healthy": getattr(shadow, "sim_healthy", True),
            "last_tick_at": getattr(shadow, "last_tick_at", None),
            "sim_speed": shadow.simulation_speed_multiplier,
            "coordinate_system": scenario.coordinate_system,
            "federation_summary": shadow.world.federation_manager.get_federation_summary(),
            "map_layers": {
                "road": shadow.world.road.road_structure_metadata_processed,
                "road_curves": getattr(shadow.world.road, "road_curves", None),
                "road_segments": getattr(shadow.world.road, "road_segments", None),
                "lane_polygons": scenario.lane_polygons or None,
                "road_config": shadow.world.road_config,
                "water": shadow.world.road_water_metadata,
                "spawn": shadow.world.road_spawn_metadata,
                "ru": shadow.world.roadside_units,
                "embedded_sensors": getattr(shadow.world, "embedded_sensors", None) or scenario.get_embedded_sensors(),
                "vehicles": shadow.vehicles_geojson,
                "drones": shadow.drone_geojson,
                "warnings": shadow.warning_geojson,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def get_dynamic_delta_state(since_version: int = 0) -> Tuple[Dict[str, Any], int]:
    """
    Build lightweight delta payload for the SSE stream.

    Includes only moving entities (`vehicles`, `drones`, `warnings`), RSU live
    weather summaries, and road segment IDs mutated since `since_version`.
    """
    shadow = get_shadow()
    if shadow is None:
        return {"status": "initializing"}, 0

    cur_version, dirty = shadow.world.get_dirty_segments_since(since_version)

    with shadow._lock:
        rsu_features = list(shadow.world.roadside_units.get("features", []))
        vehicles = shadow.vehicles_geojson
        drones = shadow.drone_geojson
        warnings = shadow.warning_geojson
        sim_speed = shadow.simulation_speed_multiplier
        fed_summary = shadow.world.federation_manager.get_federation_summary()

        rsu_live = {}
        for rf in rsu_features:
            rp = rf.get("properties", {})
            rid = rp.get("id")
            if rid:
                rsu_live[rid] = {
                    "WeatherState": rp.get("WeatherState", "Sunny"),
                    "AirTemperature": rp.get("AirTemperature", 22.0),
                    "RoadSurfaceTemperature": rp.get("RoadSurfaceTemperature", 26.0),
                    "ActiveContracts": len(shadow.world.federation_manager.get_contracts_for_rsu(rid)),
                }

    return {
        "status": "ok",
        "is_delta": True,
        "sim_speed": sim_speed,
        "federation_summary": fed_summary,
        "dirty_segments": dirty,
        "rsu_live": rsu_live,
        "map_layers": {
            "vehicles": vehicles,
            "drones": drones,
            "warnings": warnings,
            "dirty_segments": dirty,
            "rsu_live": rsu_live,
        },
    }, cur_version


@router.get("/dashboard/layers/road_curves")
def get_road_curves() -> Any:
    """Returns highway centerline curves GeoJSON from memory (or disk during early boot)."""
    shadow = get_shadow()
    if shadow is not None and getattr(shadow.world.road, "road_curves", None):
        return shadow.world.road.road_curves
    configs_dir = Path(__file__).resolve().parent.parent / "configs"
    fpath = configs_dir / "road_curves.geojson"
    if fpath.exists():
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Road curves layer not found")


@router.get("/dashboard/layers/road_segments")
def get_road_segments() -> Any:
    """Returns discretized road segment GeoJSON from memory (or disk during early boot)."""
    shadow = get_shadow()
    if shadow is not None and getattr(shadow.world.road, "road_segments", None):
        return shadow.world.road.road_segments
    configs_dir = Path(__file__).resolve().parent.parent / "configs"
    fpath = configs_dir / "road_segments.geojson"
    if fpath.exists():
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Road segments layer not found")


@router.get("/dashboard/stream")
async def stream_dashboard_state(request: Request) -> StreamingResponse:
    """Streams lightweight per-client SSE state deltas on the active simulation cadence."""
    async def event_generator():
        shadow = get_shadow()
        client_dirty_version = shadow.world.dirty_version if shadow else 0
        while True:
            if await request.is_disconnected():
                break
            delta_data, client_dirty_version = get_dynamic_delta_state(since_version=client_dirty_version)
            safe_payload = sanitize_json_payload(delta_data)
            yield f"data: {json.dumps(safe_payload)}\n\n"
            shadow_now = get_shadow()
            mult = shadow_now.simulation_speed_multiplier if shadow_now else 1.0
            sleep_time = max(0.5, 5.0 / max(0.25, mult))
            await asyncio.sleep(sleep_time)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class SpawnVehicleRequest(BaseModel):
    """Optional overrides when manually spawning a Heavy Goods Vehicle."""

    direction: Optional[int] = None
    junction_id: Optional[str] = None


@router.post("/dashboard/control/spawn_vehicle")
def control_spawn_vehicle(req: Optional[SpawnVehicleRequest] = None) -> Dict[str, Any]:
    """Spawns a new Heavy Goods Vehicle immediately on demand at the selected intersection."""
    shadow = get_shadow()
    if shadow is None:
        raise HTTPException(status_code=500, detail="Shadow not initialized")
    jct_id = req.junction_id if req else None
    direction = req.direction if req else None
    with shadow._lock:
        v_obj = shadow.traffic_management.force_spawn_vehicle(junction_id=jct_id, direction=direction)
        if v_obj is None:
            return {"status": "limit_reached", "active_vehicles": len(shadow.traffic_management.active_vehicles)}

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        shadow.simpl.simulation_pipeline(v_obj.id, v_obj)
        v_obj.params.update({"Timestamp": now_str})
        v_obj.statistic.append({k: v for k, v in v_obj.params.items() if k not in ("Trajectory", "FederationContract", "HPN")})
        shadow.update_geojson_snapshots()
        active_count = len(shadow.traffic_management.active_vehicles)
    return {
        "status": "success",
        "vehicle_id": v_obj.id,
        "callsign": v_obj.params.get("Callsign"),
        "origin": v_obj.params.get("StartJunctionName"),
        "destination": v_obj.params.get("EndJunctionName"),
        "velocity_kmh": v_obj.params.get("Velocity"),
        "active_vehicles": active_count,
    }


class SimSpeedRequest(BaseModel):
    """Requested co-simulation speed multiplier (clamped to [0.25, 10.0])."""

    multiplier: float


@router.post("/dashboard/control/sim_speed")
def control_sim_speed(req: SimSpeedRequest) -> Dict[str, Any]:
    """Adjusts the background simulation speed multiplier (e.g. 1.0x, 2.0x, 5.0x)."""
    shadow = get_shadow()
    if shadow is None:
        raise HTTPException(status_code=500, detail="Shadow not initialized")
    shadow.simulation_speed_multiplier = max(0.25, min(10.0, float(req.multiplier)))
    return {"status": "success", "sim_speed": shadow.simulation_speed_multiplier}


class TriggerWarningRequest(BaseModel):
    """Optional target vehicle ID for placing a road anomaly warning."""

    vehicle_id: Optional[Any] = None


@router.post("/dashboard/control/trigger_warning")
def control_trigger_warning(req: Optional[TriggerWarningRequest] = None) -> Dict[str, Any]:
    """
    Trigger a road anomaly warning next to the selected vehicle and dispatch a UAV.

    Finds the nearest serving RSU and deploys its autonomous inspection drone.
    """
    shadow = get_shadow()
    if shadow is None:
        raise HTTPException(status_code=500, detail="Shadow not initialized")

    with shadow._lock:
        target_veh = None
        if req and req.vehicle_id is not None:
            req_id_str = str(req.vehicle_id)
            for vid_key, v_obj in shadow.traffic_management.active_vehicles.items():
                if str(vid_key) == req_id_str or str(v_obj.params.get("Callsign")) == req_id_str:
                    target_veh = v_obj
                    break

        # Fallback to a random vehicle only if no explicit ID was requested
        if target_veh is None and not (req and req.vehicle_id is not None):
            active_vehs = list(shadow.traffic_management.active_vehicles.values())
            if active_vehs:
                target_veh = random.choice(active_vehs)

        if target_veh is None:
            return {"status": "error", "message": "No vehicle selected or active"}

        # Place warning 50 meters ahead of vehicle in its direction of travel
        pos = round(target_veh.position + target_veh.direction * 0.05, 3)
        direction = target_veh.direction
        vid = target_veh.params.get("Callsign", f"HGV-{target_veh.id}")
        weight = target_veh.params.get("Weight", 36000)
        surf_t = target_veh.params.get("State", {}).get("RoadSurfaceTemperature", 27.0)

        warn = Warning(
            position=pos,
            direction=direction,
            vehicle_id=vid,
            vehicle_weight=weight,
            surface_temp=surf_t,
        )
        shadow.world.register_warning(warn, force=True)
        shadow.world.warning_handling()
        shadow.world.prepare_geojson()
        shadow.update_geojson_snapshots()
        active_warnings_count = len(shadow.world.warnings)
        warning_dict = warn.to_dict()
        target_veh_id = target_veh.id
    return {
        "status": "success",
        "warning_id": warn.id,
        "vehicle_id": target_veh_id,
        "vehicle_callsign": vid,
        "position_km": pos,
        "direction": direction,
        "active_warnings": active_warnings_count,
        "warning": warning_dict,
    }
