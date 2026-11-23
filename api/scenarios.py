"""
api/scenarios.py — Scenario Bundle Discovery, Switching & Live Asset Editing Router
===================================================================================

Manages scenario bundles (WGS84 highway corridors or `LocalCartesian` test
tracks converted from Lanelet2 / ASAM OpenDRIVE) and runtime asset overrides.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.runtime import get_shadow

router = APIRouter(tags=["Scenarios"])


class SwitchScenarioRequest(BaseModel):
    """Request body specifying the target scenario bundle ID to activate."""

    scenario_id: str


class SaveScenarioRequest(BaseModel):
    """Request payload for persisting Scenario Editor infrastructure changes."""

    scenario_id: Optional[str] = "a14_corridor"
    infrastructure: Dict[str, Any]


class AssetUpdateRequest(BaseModel):
    """Live parameter override payload for RSUs, vehicles, or embedded sensors."""

    asset_type: str  # 'rsu' | 'vehicle' | 'sensor'
    asset_id: str
    properties: Dict[str, Any]


@router.get("/api/scenarios")
def list_scenarios() -> List[Dict[str, Any]]:
    """Lists all discovered scenario bundles in `scenarios/`."""
    from world.scenario_loader import get_scenario_loader

    return get_scenario_loader().list_available_scenarios()


@router.get("/api/scenarios/{scenario_id}")
def get_scenario_details(scenario_id: str) -> Dict[str, Any]:
    """Returns metadata, CRS config, and available pavements for `scenario_id`."""
    from world.scenario_loader import get_scenario_loader

    try:
        bundle = get_scenario_loader().load(scenario_id)
        return {
            "metadata": bundle.summary(),
            "coordinate_system": bundle.coordinate_system,
            "environment": bundle.environment,
            "simulation": bundle.simulation,
            "pavements": list(bundle.pavement_catalog.get("pavements", {}).keys()),
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found: {e}") from e


@router.post("/api/scenarios/switch")
def switch_scenario(req: SwitchScenarioRequest) -> Dict[str, Any]:
    """Activates a different scenario bundle and reloads live world infrastructure."""
    from world.scenario_loader import set_active_scenario

    try:
        bundle = set_active_scenario(req.scenario_id)
        shadow = get_shadow()
        if shadow is not None and hasattr(shadow, "reload_scenario"):
            shadow.reload_scenario()
        return {
            "status": "success",
            "active_scenario": bundle.summary(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to switch scenario: {e}") from e


@router.post("/api/scenarios/save")
def save_scenario_infrastructure(req: SaveScenarioRequest) -> Dict[str, Any]:
    """Sanitizes and persists Scenario Editor infrastructure updates to disk."""
    from world.scenario_loader import get_active_scenario, get_scenario_loader

    active_bundle = get_active_scenario()
    target_id = req.scenario_id or active_bundle.scenario_id
    success = get_scenario_loader().save_infrastructure(target_id, req.infrastructure)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to save infrastructure for scenario '{target_id}'")

    shadow = get_shadow()
    if shadow and hasattr(shadow, "world"):
        with shadow._lock:
            w = shadow.world
            if "roadside_units" in req.infrastructure:
                if hasattr(w, "sync_roadside_units"):
                    w.sync_roadside_units(req.infrastructure["roadside_units"])
                else:
                    w.roadside_units = req.infrastructure["roadside_units"]
            if "spawn_points" in req.infrastructure:
                w.road_spawn_metadata = req.infrastructure["spawn_points"]
            if "water_sources" in req.infrastructure:
                w.road_water_metadata = req.infrastructure["water_sources"]
                if hasattr(w, "_compute_water_hydrological_impacts"):
                    w._compute_water_hydrological_impacts()
            if "embedded_sensors" in req.infrastructure:
                w.embedded_sensors = req.infrastructure["embedded_sensors"]
            if hasattr(shadow, "update_geojson_snapshots"):
                shadow.update_geojson_snapshots()

    return {
        "status": "success",
        "scenario_id": target_id,
        "message": "Infrastructure updated and persisted successfully.",
    }


@router.post("/api/assets/update")
def update_asset_parameters(req: AssetUpdateRequest) -> Dict[str, Any]:
    """
    Override live parameters for RSUs, vehicles, or embedded sensors.

    Supports interactive 'what-if' scenario exploration (altering weather, speed, load, etc.).
    """
    shadow = get_shadow()
    if shadow is None or not hasattr(shadow, "world"):
        raise HTTPException(status_code=503, detail="Digital shadow engine not initialized")

    with shadow._lock:
        w = shadow.world
        updated_props: Dict[str, Any] = {}

        if req.asset_type == "vehicle":
            tm = getattr(shadow, "traffic_management", getattr(w, "traffic_management", None))
            if not tm:
                raise HTTPException(status_code=503, detail="Traffic management not available")
            veh = None
            for vid, vobj in tm.active_vehicles.items():
                if str(vid) == str(req.asset_id):
                    veh = vobj
                    break

            if not veh:
                raise HTTPException(status_code=404, detail=f"Active vehicle '{req.asset_id}' not found")

            for k, val in req.properties.items():
                if k == "Velocity":
                    veh.params["Velocity"] = float(val)
                    veh.cruise_speed = float(val)
                    veh.params["CruiseSpeed"] = float(val)
                elif k == "Weight":
                    veh.params["Weight"] = float(val)
                elif k == "VehicleClass":
                    veh.params["VehicleClass"] = str(val)
                elif k == "Axles":
                    veh.params["Axles"] = int(val)
                elif k == "Direction":
                    veh.direction = int(val)
                    veh.params["Direction"] = int(val)
                else:
                    veh.params[k] = val
                updated_props[k] = val

        elif req.asset_type in ("rsu", "roadside_unit"):
            found_feat = None
            for feat in w.roadside_units.get("features", []):
                fid = feat.get("properties", {}).get("id")
                if str(fid) == str(req.asset_id):
                    found_feat = feat
                    break

            if not found_feat:
                raise HTTPException(status_code=404, detail=f"RSU '{req.asset_id}' not found")

            for k, val in req.properties.items():
                if k == "ResetOverride":
                    continue
                found_feat["properties"][k] = val
                updated_props[k] = val

            w_key = found_feat.get("Weather", found_feat.get("properties", {}).get("Weather"))
            w_obj = getattr(w, "weather_objects", {}).get(w_key)
            if w_obj:
                if req.properties.get("ResetOverride"):
                    w_obj.manual_override = False
                    found_feat["properties"].pop("ResetOverride", None)
                    updated_props["ResetOverride"] = True
                elif any(k in req.properties for k in ("AirTemperature", "RoadSurfaceTemperature", "WeatherState")):
                    w_obj.manual_override = True
                    state_dict = getattr(w_obj, "state", None)
                    if "AirTemperature" in req.properties:
                        val_air = float(req.properties["AirTemperature"])
                        if hasattr(w_obj, "air_temp"):
                            w_obj.air_temp = val_air
                        if hasattr(w_obj, "air_temperature"):
                            w_obj.air_temperature = val_air
                        if isinstance(state_dict, dict):
                            state_dict["AirTemperature"] = val_air
                    if "RoadSurfaceTemperature" in req.properties:
                        val_surf = float(req.properties["RoadSurfaceTemperature"])
                        if hasattr(w_obj, "road_temp"):
                            w_obj.road_temp = val_surf
                        if hasattr(w_obj, "road_surface_temperature"):
                            w_obj.road_surface_temperature = val_surf
                        if isinstance(state_dict, dict):
                            state_dict["RoadSurfaceTemperature"] = val_surf
                    if "WeatherState" in req.properties:
                        val_state = str(req.properties["WeatherState"])
                        if hasattr(w_obj, "current_state"):
                            w_obj.current_state = val_state
                        if hasattr(w_obj, "weather_condition"):
                            w_obj.weather_condition = val_state
                        if isinstance(state_dict, dict):
                            state_dict["Weather"] = val_state

        elif req.asset_type in ("sensor", "embedded_sensor"):
            from world.scenario_loader import get_active_scenario

            active_bundle = get_active_scenario()
            sensors_fc = getattr(w, "embedded_sensors", None)
            if sensors_fc is None:
                sensors_fc = active_bundle.get_embedded_sensors()
                w.embedded_sensors = sensors_fc

            found_sensor = None
            for feat in sensors_fc.get("features", []):
                props = feat.get("properties", {})
                sid = props.get("id") or props.get("station_id")
                if str(sid) == str(req.asset_id):
                    found_sensor = feat
                    break

            if not found_sensor:
                raise HTTPException(status_code=404, detail=f"Embedded sensor '{req.asset_id}' not found")

            for k, val in req.properties.items():
                found_sensor["properties"][k] = val
                updated_props[k] = val

            if isinstance(active_bundle.infrastructure, dict) and "embedded_sensors" in active_bundle.infrastructure:
                for b_feat in active_bundle.infrastructure["embedded_sensors"].get("features", []):
                    b_props = b_feat.get("properties", {})
                    if str(b_props.get("id") or b_props.get("station_id")) == str(req.asset_id):
                        b_props.update(updated_props)
                        break

        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported asset_type '{req.asset_type}'. "
                    "Must be vehicle, rsu, roadside_unit, sensor, or embedded_sensor"
                ),
            )

        return {
            "status": "success",
            "asset_type": req.asset_type,
            "asset_id": req.asset_id,
            "updated_properties": updated_props,
        }
