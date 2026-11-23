"""
api/inspector.py — Polymorphic 8-Entity Inspector & Context Metadata Router
===========================================================================

Resolves telemetry, structural properties, Heraklit HPN / external solver
activation metadata, and 6-sensor embedded station frames on map click.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
import numpy as np
import pandas as pd
from pydantic import BaseModel

from api.runtime import get_shadow
from world.sensor_sources import SENSOR_MODELS, get_sensor_stream

router = APIRouter(tags=["Inspector"])


class SelectionRequest(BaseModel):
    """Payload identifying a map entity clicked by the user for inspection."""

    selection_type: str
    feature_data: Dict[Any, Any]


def _build_pavement_layers(road_mat: str, road_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Builds the RStO 12 layer stack from a segment's `RoadMaterial` and `RoadStructureConfig`."""
    is_concrete = road_mat.strip().lower() == "concrete"
    layer_items = []
    for k, v in road_cfg.items():
        if k.startswith("Layer_") and isinstance(v, dict):
            try:
                idx = int(k.split("_", 1)[1])
            except (IndexError, ValueError):
                idx = 999
            layer_items.append((idx, v))
    layer_items.sort(key=lambda item: item[0])

    if is_concrete:
        templates = [
            ("Concrete Slab (JPCP C30/37)", 34000, "Concrete"),
            ("Hydraulically Bound Base (HGT)", 12000, "Concrete"),
            ("Frost Protection Layer (FSS)", 150, "Unbound"),
        ]
        if not layer_items:
            return [
                {"layer": templates[0][0], "thickness_cm": 27, "modulus_mpa": 34000, "material": "Concrete"},
                {"layer": templates[1][0], "thickness_cm": 15, "modulus_mpa": 12000, "material": "Concrete"},
                {"layer": templates[2][0], "thickness_cm": 28, "modulus_mpa": 150, "material": "Unbound"},
            ]
        layers: List[Dict[str, Any]] = []
        for idx, (_, lcfg) in enumerate(layer_items):
            tmpl_name, tmpl_mod, tmpl_mat = (
                templates[idx] if idx < len(templates) else ("Frost Protection Layer (FSS)", 150, "Unbound")
            )
            name = str(lcfg.get("Name") or tmpl_name)
            raw_mod = lcfg.get("ModulusMPa")
            mod = int(round(float(raw_mod))) if raw_mod is not None else tmpl_mod
            mat = "Unbound" if "fss" in name.lower() or tmpl_mat == "Unbound" else "Concrete"
            thickness_cm = max(1, round(float(lcfg.get("Length", 0.2)) * 100))
            layers.append({"layer": name, "thickness_cm": thickness_cm, "modulus_mpa": mod, "material": mat})
        return layers

    templates = [
        ("Surface Course (SMA 11 S)", 6500, "Asphalt"),
        ("Binder Course (AC 16 B S)", 8000, "Asphalt"),
        ("Asphalt Base Course (AC 22 T S)", 7500, "Asphalt"),
        ("Frost Protection Layer (FSS)", 150, "Unbound"),
    ]
    if not layer_items:
        return [
            {"layer": templates[0][0], "thickness_cm": 4, "modulus_mpa": 6500, "material": "Asphalt"},
            {"layer": templates[1][0], "thickness_cm": 8, "modulus_mpa": 8000, "material": "Asphalt"},
            {"layer": templates[2][0], "thickness_cm": 22, "modulus_mpa": 7500, "material": "Asphalt"},
            {"layer": templates[3][0], "thickness_cm": 36, "modulus_mpa": 150, "material": "Unbound"},
        ]
    layers = []
    for idx, (_, lcfg) in enumerate(layer_items):
        tmpl_name, tmpl_mod, tmpl_mat = (
            templates[idx] if idx < len(templates) else ("Frost Protection Layer (FSS)", 150, "Unbound")
        )
        name = str(lcfg.get("Name") or tmpl_name)
        raw_mod = lcfg.get("ModulusMPa")
        mod = int(round(float(raw_mod))) if raw_mod is not None else tmpl_mod
        mat = "Unbound" if "fss" in name.lower() or tmpl_mat == "Unbound" else "Asphalt"
        thickness_cm = max(1, round(float(lcfg.get("Length", 0.1)) * 100))
        layers.append({"layer": name, "thickness_cm": thickness_cm, "modulus_mpa": mod, "material": mat})
    return layers


def _build_broker_context_link(
    entity_id: Any,
    entity_type: str,
    service_group_key: str,
) -> Dict[str, Any]:
    """Builds universal Native/FIWARE broker link metadata for an inspected entity."""
    from data_curation import get_broker_status

    st = get_broker_status()
    shadow = get_shadow()
    fiware_connected = bool(getattr(shadow, "fiware_flag", False)) if shadow is not None else False
    orion_host = os.getenv("ORION_HOST", "localhost")
    iota_south_host = os.getenv("IOT_AGENT_SOUTH_HOST", "localhost")
    eid = str(entity_id)

    return {
        "backend": "fiware" if fiware_connected else st.get("backend", "native"),
        "fiware_connected": fiware_connected,
        "entity_id": eid,
        "entity_type": entity_type,
        "service": "openiot",
        "servicepath": "/",
        "service_group": service_group_key,
        "entity_api_url": f"/dashboard/fiware_entities/{eid}",
        "orion_url": f"http://{orion_host}:1026/v2/entities/{eid}?type={entity_type}&options=keyValues",
        "ultralight_url": f"http://{iota_south_host}:7896/iot/d?k={service_group_key}&i={eid}",
    }


def _build_inspector_panel(selection_type: str, md: Any, obj_id: Any) -> Optional[Dict[str, Any]]:
    """Construct a normalized `panel` dict for `ObjectInspector.vue` across all 8 entity types."""
    if not isinstance(md, dict):
        return None

    # 1. Vehicle Inspector
    if selection_type in ("Vehicle", "SingleVehicleStateDS"):
        state = md.get("State", {}) if isinstance(md.get("State"), dict) else {}
        mech = md.get("MechanicalSimulation", {}) if isinstance(md.get("MechanicalSimulation"), dict) else {}
        dir_val = int(md.get("Direction", state.get("Direction", 1)))
        start_km = float(md.get("StartRoute", 0.0))
        end_km = float(md.get("EndRoute", 120.0))
        cur_km = float(md.get("Kilometer", md.get("LastPosition", start_km)))
        span = max(0.1, abs(end_km - start_km))
        prog_pct = min(100.0, max(0.0, (abs(cur_km - start_km) / span) * 100.0))
        return {
            "panel_type": "vehicle",
            "vehicle_id": md.get("id", obj_id),
            "carriageway": "Dresden → Leipzig" if dir_val == 1 else "Leipzig → Dresden",
            "origin_name": md.get("StartJunctionName") or md.get("OriginName") or "AS 78 Dresden-Altstadt",
            "destination_name": md.get("EndJunctionName") or md.get("DestinationName") or "AS 25 Leipzig-Ost",
            "start_km": start_km,
            "end_km": end_km,
            "kilometer": cur_km,
            "route_progress_pct": md.get("RouteProgressPct", round(prog_pct, 1)),
            "velocity_kmh": float(md.get("Velocity", 88.0)),
            "extrapolated_velocity_kmh": float(md.get("ExtrapolatedVelocity", md.get("Velocity", 88.0))),
            "weight_kg": float(md.get("Weight", 36000.0)),
            "surface_temp_c": float(state.get("RoadSurfaceTemperature", md.get("RoadSurfaceTemperature", 26.5))),
            "active_solver": mech.get("Model", "POD"),
            "step_computation_time_ms": float(md.get("StepComputationTimeMs", 1.45)),
            "federation_contract": md.get("FederationContract"),
            "kinematic_axles": md.get("KinematicAxles"),
            "broker_link": _build_broker_context_link(
                md.get("id", obj_id), "Vehicle", "vehicle"
            ),
        }

    # 2. Road Segment / State Point Inspector
    if selection_type in ("Road", "SingleRoadPointStateDS", "RoadSegment", "SingleRoadSegmentStateDS"):
        health = float(md.get("state", 94.0))
        cond = "Good / Serviceable" if health >= 75 else ("Moderate Wear" if health >= 50 else "Critical")
        dir_val = int(md.get("direction", 1))
        start_km = float(md.get("station_start_km", md.get("dist", 0.0)))
        end_km = float(md.get("station_end_km", start_km + 0.2))
        soil_t = float(md.get("SoilTemperature", 14.5))
        road_cfg = md.get("RoadStructureConfig") if isinstance(md.get("RoadStructureConfig"), dict) else {}
        road_type_dict = road_cfg.get("RoadType") if isinstance(road_cfg.get("RoadType"), dict) else {"Asphalt": {}}
        road_mat = str(md.get("RoadMaterial") or next(iter(road_type_dict.keys()), "Asphalt"))
        road_struct_id = str(md.get("RoadStructure") or md.get("road") or "RoadStructure_1")
        closest_water = md.get("ClosestWaterDist", md.get("ClosestWater"))
        water_dist_km = round(float(closest_water), 1) if closest_water is not None else 8.0
        return {
            "panel_type": "road_segment",
            "name": md.get("name") or f"Section #{obj_id}",
            "road_name": md.get("road_name") or md.get("road") or "A4 / A14",
            "carriageway": md.get("carriageway") or ("Dresden → Leipzig" if dir_val == 1 else "Leipzig → Dresden"),
            "station_start_km": start_km,
            "station_end_km": end_km,
            "health_pct": health,
            "condition_status": cond,
            "length_m": int(md.get("length_m", 200)),
            "lanes": int(md.get("lanes", 3)),
            "total_passes": int(md.get("PassesCount", md.get("passes_count", 18))),
            "cumulative_damage_mm": float(md.get("CumulativeDamage", md.get("cumulative_damage", 0.42))),
            "road_material": road_mat,
            "road_structure_id": road_struct_id,
            "load_class": road_cfg.get("LoadClass"),
            "standard": road_cfg.get("Standard"),
            "pavement_layers": _build_pavement_layers(road_mat, road_cfg),
            "nearest_rsu": {
                "name": md.get("RoadsideUnitName") or f"RSU ({md.get('RoadsideUnit', 'rsu_00')})",
                "distance_km": round(float(md.get("RoadsideUnitDist") or 2.4), 1),
                "weather": md.get("WeatherState", "Sunny"),
                "road_temperature": float(md.get("RoadSurfaceTemperature", 26.5)),
                "air_temperature": float(md.get("AirTemperature", 22.0)),
            },
            "nearest_water": {
                "name": "Corridor Hydrological Basin",
                "distance_km": water_dist_km,
                "in_influence_zone": water_dist_km <= 5.0,
                "cooling_effect_c": round(soil_t - 15.0, 1),
            },
        }

    # 3. Highway Intersection / Junction Inspector
    if selection_type in ("Exit", "SingleExitStateDS"):
        hgv_raw = float(md.get("heavy_goods_share", md.get("heavy_goods_share_pct", 0.18)))
        hgv_pct = round(hgv_raw * 100, 1) if hgv_raw <= 1.0 else round(hgv_raw, 1)
        sp_raw = float(md.get("SpawnProbability", 0.08))
        ex_raw = float(md.get("DestroyProbability", 0.08))
        return {
            "panel_type": "intersection",
            "id": md.get("id", obj_id),
            "code": md.get("code", "AS"),
            "name": md.get("name", f"Junction #{obj_id}"),
            "junction_type": md.get("type", "Anschlussstelle (Interchange)"),
            "kilometer": float(md.get("StationKm", md.get("ClosestPoint", md.get("kilometer", 0.0)))),
            "connecting_road": md.get("connecting_road", "B 175 / A 14"),
            "daily_traffic_aadt": int(md.get("daily_traffic_aadt", md.get("aadt_vehicles_per_day", 48500))),
            "heavy_goods_share_pct": hgv_pct,
            "spawn_probability_pct": round(sp_raw * 100, 1) if sp_raw <= 1.0 else round(sp_raw, 1),
            "exit_probability_pct": round(ex_raw * 100, 1) if ex_raw <= 1.0 else round(ex_raw, 1),
            "active_spawned_vehicles": int(md.get("ActiveOutboundVehicles", 0)),
            "active_inbound_vehicles": int(md.get("ActiveInboundVehicles", 0)),
        }

    # 4. Water Source Inspector
    if selection_type in ("Water", "SingleWaterStateDS"):
        raw_profile = md.get("RadialAttenuationProfile", [])
        radial_att = [
            {
                "distance_m": pt.get("distance_m", 0),
                "moisture_factor_pct": round(float(pt.get("moisture_coef", 0.5)) * 100),
                "soil_temp_c": pt.get("soil_temp_c", 12.5),
            }
            for pt in raw_profile
        ]
        return {
            "panel_type": "water_source",
            "name": md.get("name", f"Water Basin #{obj_id}"),
            "water_type": md.get("water_type", md.get("type", "River Floodplain")),
            "kilometer": float(md.get("kilometer", md.get("station_km", 25.0))),
            "cooled_soil_temp_c": float(md.get("soil_temp_saturated_c", 10.0)),
            "baseline_soil_temp_c": float(md.get("soil_temp_dry_c", 15.0)),
            "soil_moisture_saturation": float(md.get("soil_moisture_saturation", md.get("saturation_index", 0.85))),
            "frost_susceptibility": md.get("frost_susceptibility", md.get("frost_susceptibility_class", "F2 (Moderate)")),
            "affected_road_segments_count": int(
                md.get("affected_segments_count", md.get("affected_road_segments_count", 25))
            ),
            "radial_attenuation": radial_att,
        }

    # 5. Roadside Unit (RSU) Inspector
    if selection_type in ("RU", "SingleRoadsideUnitsStateDS"):
        is_real = str(md.get("id", obj_id)) in ("0", "rsu_00")
        raw_matrix = md.get("TransitionMatrix") or {}
        norm_matrix: Dict[str, Dict[str, float]] = {}
        states_order = ["Sunny", "Cloudy", "Rainy"]
        for s_from in states_order:
            row_raw = raw_matrix.get(s_from, {})
            if isinstance(row_raw, dict) and "TransitionTo" in row_raw and isinstance(row_raw["TransitionTo"], dict):
                trans_to = row_raw["TransitionTo"]
            elif isinstance(row_raw, dict):
                trans_to = row_raw
            else:
                trans_to = {}
            row_probs: Dict[str, float] = {}
            other_sum = 0.0
            for s_to in states_order:
                if s_to != s_from:
                    p = float(trans_to.get(s_to, 0.0))
                    row_probs[s_to] = round(p, 4)
                    other_sum += p
            row_probs[s_from] = round(max(0.0, 1.0 - other_sum), 4)
            norm_matrix[s_from] = {k: row_probs[k] for k in states_order}

        return {
            "panel_type": "rsu",
            "name": md.get("name", f"RSU #{obj_id}"),
            "town": md.get("town", "A14 Corridor"),
            "kilometer": float(md.get("kilometer", md.get("station_km", 0.0))),
            "is_real_sensor": is_real,
            "sensor_source": "RealTime Edge Pi" if is_real else "Markov Weather Sim",
            "weather": md.get("Weather", "Sunny"),
            "air_temperature_c": float(md.get("AirTemperature", 22.0)),
            "road_temperature_c": float(md.get("RoadSurfaceTemperature", 26.5)),
            "coverage_radius_km": 10.0,
            "markov_matrix": norm_matrix,
            "active_contracts_count": int(md.get("ActiveContractsCount", 0)),
            "active_contracts": md.get("FederationContracts", []),
            "broker_link": _build_broker_context_link(
                md.get("id", obj_id), "Roadside_unit", "rs"
            ),
        }

    # 6. Autonomous Inspection Drone (UAV) Inspector
    if selection_type in ("Drone", "SingleDroneStateDS"):
        return {
            "panel_type": "drone",
            "drone_id": md.get("id", obj_id),
            "home_rsu_name": md.get("HomeRSUName", f"RSU ({md.get('RoadsideUnit', 'rsu_01')})"),
            "payload_sensor": md.get("Payload", "Zenmuse P1 Photogrammetry + LiDAR"),
            "flight_state": md.get("State", "CruisingToward"),
            "target_warning_id": md.get("TargetWarningID", md.get("WarningID", "warn_01")),
            "target_warning_km": float(md.get("TargetWarningKm", md.get("TargetStationKm", md.get("TargetPositionKm", 42.4)))),
            "mission_progress_pct": float(md.get("MissionProgressPct", md.get("InspectionProgressPct", 50.0))),
            "altitude_m": float(md.get("Altitude", 50.0)),
            "velocity_kmh": float(md.get("Velocity", md.get("CruiseSpeedKmh", 108.0))),
            "bearing_deg": float(md.get("BearingDeg", 112.0)),
            "battery_pct": float(md.get("BatteryPct", 88.0)),
        }

    # 7. Structural Warning Point Inspector
    if selection_type in ("Warning", "SingleWarningStateDS"):
        dir_val = int(md.get("Direction", 1))
        warn_status = md.get("State", "Under Inspection")
        default_drone_state = "Mission Complete" if warn_status == "Inspected" else ("Queued for Dispatch" if warn_status == "New" else "CruisingToward")
        default_prog_pct = 100.0 if warn_status == "Inspected" else (0.0 if warn_status == "New" else 50.0)
        return {
            "panel_type": "warning",
            "warning_id": md.get("id", obj_id),
            "carriageway": "Dresden → Leipzig" if dir_val == 1 else "Leipzig → Dresden",
            "anomaly_type": md.get("AnomalyType", "Viscoelastic Rutting Hotspot"),
            "severity": md.get("Severity", "HIGH"),
            "anomaly_description": md.get(
                "Description",
                "Localized viscoelastic surface depression and micro-cracking detected via vehicle-road interaction.",
            ),
            "status": warn_status,
            "kilometer": float(md.get("Position", md.get("Kilometer", 42.4))),
            "estimated_rut_depth_mm": float(md.get("EstimatedRutDepthMm", 6.8)),
            "confidence_score": float(md.get("ConfidenceScore", 0.94)),
            "triggered_by_vehicle_id": md.get("TriggerVehicleID", md.get("TriggeredByVehicle", md.get("VehicleID", "HGV-101"))),
            "trigger_velocity_kmh": float(md.get("TriggerVelocityKmh", 88.0)),
            "trigger_weight_kg": float(md.get("TriggerVehicleWeight", md.get("TriggerWeightKg", md.get("VehicleWeight", 38400.0)))),
            "assigned_rsu_name": md.get("AssignedRSUName", f"RSU ({md.get('AssignedRSU', 'rsu_03')})"),
            "assigned_drone_id": md.get("AssignedDroneID", md.get("AssignedDrone")),
            "drone_flight_state": md.get("DroneFlightState", default_drone_state),
            "drone_mission_progress_pct": float(md.get("InspectionProgressPct", md.get("DroneMissionProgressPct", default_prog_pct))),
        }

    # 8. Embedded Pavement Instrumentation Station Inspector
    if selection_type in ("EmbeddedSensor", "SingleEmbeddedSensorStateDS"):
        station_id = str(md.get("station_id") or md.get("id") or obj_id or "rsu_00")
        latest = get_sensor_stream().get_latest(station_id)
        return {
            "panel_type": "embedded_sensor",
            "station_id": station_id,
            "name": md.get("name") or f"Sensor Station ({station_id})",
            "model": md.get("model") or md.get("sensor_model") or "6-Sensor DAQ Stack",
            "kilometer": float(md.get("kilometer", md.get("station_km", 0.0))),
            "latest_frame": latest.to_dict() if latest else None,
            "hardware_catalog": SENSOR_MODELS,
        }

    return None


@router.post("/dashboard/select_object")
def select_map_object(req: SelectionRequest) -> Dict[str, Any]:
    """Resolves polymorphic telemetry, HPN/FODA or external solver state, and HLA contracts for a clicked entity."""
    shadow = get_shadow()
    if shadow is None:
        raise HTTPException(status_code=500, detail="Shadow not initialized")

    try:
        active_selection = {req.selection_type: req.feature_data}
        md, selection_data, fm_tree, code, mech_code = shadow.inspect_object(active_selection)

        tree_data = fm_tree if fm_tree else md
        stats_payload = None
        columns: List[str] = []

        if isinstance(selection_data, pd.DataFrame):
            selection_data = selection_data.replace({pd.NA: None, np.nan: None})
            stats_payload = selection_data.to_dict(orient="list")
            columns = list(selection_data.columns)
            if "State" in stats_payload and isinstance(stats_payload["State"], list):
                state_list = stats_payload["State"]
                if state_list and isinstance(state_list[0], dict):
                    for subkey in ["AirTemperature", "RoadSurfaceTemperature", "SoilTemperature"]:
                        if subkey not in stats_payload:
                            sub_vals = [s.get(subkey) for s in state_list if isinstance(s, dict)]
                            if any(v is not None for v in sub_vals):
                                stats_payload[subkey] = sub_vals
                                if subkey not in columns:
                                    columns.append(subkey)
        elif isinstance(selection_data, dict):
            stats_payload = {
                k: v if isinstance(v, list) else [v]
                for k, v in selection_data.items()
                if not isinstance(v, (dict, list)) or k in ("Timestamp", "RoadSurfaceTemperature", "AirTemperature", "SoilTemperature")
            }
            columns = list(stats_payload.keys())

        hpn_graph = md.get("HPN_Graph") if isinstance(md, dict) else None
        federation_contract = md.get("FederationContract") if isinstance(md, dict) else None

        obj_id = req.feature_data.get("properties", {}).get("id", req.feature_data.get("properties", {}).get("ID"))
        panel = _build_inspector_panel(req.selection_type, md, obj_id)

        return {
            "status": "success",
            "selection_type": req.selection_type,
            "id": obj_id,
            "ID": obj_id,
            "panel": panel,
            "metadata": tree_data,
            "hpn_graph": hpn_graph,
            "federation_contract": federation_contract,
            "properties": md,
            "stats": stats_payload,
            "columns": columns,
            "code": code,
            "mech_code": mech_code,
            "stats_synthetic": bool(md.get("StatsSynthetic", False)) if isinstance(md, dict) else False,
            "engine": md.get("Engine", "python-hpn") if isinstance(md, dict) else "python-hpn",
            "source_language": md.get("SourceLanguage", "python") if isinstance(md, dict) else "python",
            "active_contexts": md.get("ActiveContexts", []) if isinstance(md, dict) else [],
        }
    except Exception as e:
        logging.error(f"Error in selection: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
