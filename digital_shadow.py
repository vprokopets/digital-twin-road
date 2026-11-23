"""
digital_shadow.py — Core Digital Shadow Coordinator & Multi-Entity State Reader
===============================================================================

Project: Digital Twin Road Demonstrator

Coordinates:
- Continuous background simulation loop (`workflow`)
- Analytical 2D Boussinesq stress and displacement evaluation
- FIWARE Orion Context Broker NGSIv2 queries (`fiware_request`, `get_fiware_entities`)
- Polymorphic inspection payload builder (`inspect_object`) for all
  7 clickable GIS map entity types.
"""

from __future__ import annotations
import copy
import os
import json
from pathlib import Path
import traceback
import logging
import threading
import numpy as np
import math
import time
import requests
import datetime
from typing import Dict, Any, Tuple, Optional, List
import statsmodels.stats.api as sms
import pandas as pd

from world.traffic_management import TrafficManagement
from world.world import World
from SimPLs.temp_deform.pipeline import TempDeformSimPL
from vehicle.warning import Warning
import fm
from hpn import HeraklitHPNController

_STAT_EXCLUDED_KEYS = ("Trajectory", "FederationContract", "HPN", "State")


def _shallow_copy_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Fast shallow clone of scalar/list vehicle parameters for statistic ring buffers."""
    row: Dict[str, Any] = {}
    for k, v in params.items():
        if k in _STAT_EXCLUDED_KEYS:
            continue
        if isinstance(v, list):
            row[k] = list(v)
        elif isinstance(v, dict):
            row[k] = dict(v)
        else:
            row[k] = v
    return row


class DigitalShadow:
    """Coordinates the background co-simulation loop, GeoJSON snapshots, FIWARE queries, and entity inspection."""

    def __init__(self, fiware_flag: bool = False) -> None:
        self.fiware_flag = fiware_flag
        self.simulation_speed_multiplier: float = 1.0
        self._lock = threading.RLock()

        logging.info("Initializing Digital Shadow backend")
        cfg_path = Path(__file__).resolve().parent / "configs" / "global_config.json"
        with open(cfg_path, "r", encoding="utf-8") as f:
            self.global_config = json.load(f)

        self.world = World(self.global_config["Weather"], fiware_flag)
        self.world.read_road_metadata()
        self.traffic_management = TrafficManagement(
            self.global_config["TrafficManagement"], self.world, fiware_flag
        )
        self.simpl = TempDeformSimPL()
        self.vehicles_geojson: Dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [],
        }
        self.drone_geojson: Dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [],
        }
        self.warning_geojson: Dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [],
        }
        self.vehicle_raw: Dict[Any, Any] = {}
        self.active_selected_vehicle_id: Optional[Any] = None
        self.sim_healthy: bool = True
        self.last_tick_at: Optional[str] = None

        # Seed initial fleet & anomaly warning so the demonstrator is immediately rich and active
        self._seed_initial_scenario()

    def reload_scenario(self) -> None:
        """Rebuilds World and TrafficManagement from the active ScenarioBundle under lock."""
        with self._lock:
            self.world = World(self.global_config["Weather"], self.fiware_flag)
            self.world.read_road_metadata()
            self.traffic_management = TrafficManagement(
                self.global_config["TrafficManagement"], self.world, self.fiware_flag
            )
            self.active_selected_vehicle_id = None
            self.vehicle_raw = {}
            self._seed_initial_scenario()

    def _seed_initial_scenario(self) -> None:
        """Spawns 3 initial vehicles and 1 road anomaly warning on startup with 6 warm-up ticks."""
        now_dt = datetime.datetime.now()
        for _ in range(3):
            self.traffic_management.force_spawn_vehicle()

        for step_idx in range(6):
            ts_str = (now_dt - datetime.timedelta(seconds=(5 - step_idx) * 2)).strftime("%Y-%m-%d %H:%M:%S")
            self.world.update_weather_state(ts_str)
            self.traffic_management.update_vehicles_state()
            for v_id, v_obj in list(self.traffic_management.active_vehicles.items()):
                t_sim0 = time.perf_counter()
                self.simpl.simulation_pipeline(v_id, v_obj)
                self.world.update_road_state(v_id, v_obj)
                sim_ms = (time.perf_counter() - t_sim0) * 1000.0 + getattr(v_obj, "_last_pos_compute_ms", 0.5)
                v_obj.params.update({
                    "Timestamp": ts_str,
                    "StepComputationTimeMs": round(sim_ms, 2),
                })
                stat_row = _shallow_copy_params(v_obj.params)
                v_obj.statistic.append(stat_row)

        # Register 1 initial warning near Nossen/Döbeln so an RSU drone immediately launches
        init_warn = Warning(
            position=42.4,
            direction=1,
            vehicle_id="HGV-101",
            vehicle_weight=38400,
            surface_temp=27.2,
            anomaly_type="Viscoelastic Rutting Hotspot",
            severity="High",
        )
        self.world.register_warning(init_warn, force=True)
        for _ in range(4):
            self.world.warning_handling()
        self.world.prepare_geojson()
        self.update_geojson_snapshots()

    def mean_confidence_interval(self, data: List[float], confidence: float = 0.95) -> Optional[str]:
        """Compute formatted `mean ± margin` t-confidence interval string for numeric samples."""
        try:
            arr = np.array(data)
            if len(arr) == 0 or not np.issubdtype(arr.dtype, np.number):
                return None
            dsw = sms.DescrStatsW(arr)
            ci = dsw.tconfint_mean(alpha=1 - confidence)
            mean = dsw.mean
            margin_of_error = (ci[1] - ci[0]) / 2
            return f"{mean:.2f} ± {margin_of_error:.2f}"
        except Exception as exc:
            logging.debug("Confidence interval calculation skipped: %s", exc)
            return None

    def workflow(self) -> None:
        """Main continuous Digital Shadow simulation loop (5.0s baseline update cadence)."""
        active = True
        while active is True:
            base_sleep = float(self.global_config.get("Simulation", {}).get("SimulationScale", 5.0))
            sleep_sec = max(0.5, base_sleep / max(0.25, self.simulation_speed_multiplier))
            time.sleep(sleep_sec)

            try:
                with self._lock:
                    current_time = datetime.datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S")
                    self.world.update_weather_state(current_time)
                    self.traffic_management.update_vehicles_state()
                    self.traffic_management.spawn_vehicle()
                    for vehicle_id, vehicle_obj in list(self.traffic_management.active_vehicles.items()):
                        t_sim0 = time.perf_counter()
                        self.simpl.simulation_pipeline(vehicle_id, vehicle_obj)
                        self.world.update_road_state(vehicle_id, vehicle_obj)
                        sim_ms = (time.perf_counter() - t_sim0) * 1000.0 + getattr(vehicle_obj, "_last_pos_compute_ms", 0.5)
                        vehicle_obj.params.update({
                            "Timestamp": current_time,
                            "StepComputationTimeMs": round(sim_ms, 2),
                        })
                        # Keep a clean copy without recursive trajectory/state dicts inside statistic rows
                        stat_row = _shallow_copy_params(vehicle_obj.params)
                        vehicle_obj.statistic.append(stat_row)
                        if len(vehicle_obj.statistic) > 80:
                            vehicle_obj.statistic = vehicle_obj.statistic[-80:]

                    self.world.warning_handling()
                    self.world.prepare_geojson()
                    self.update_geojson_snapshots()
                    self.last_tick_at = current_time
                    self.sim_healthy = True
            except Exception as e:
                self.sim_healthy = False
                logging.exception(f"Unhandled exception in DigitalShadow co-simulation tick: {e}")

    def update_geojson_snapshots(self) -> None:
        """Builds atomic GeoJSON FeatureCollections for active vehicles, drones, and warnings."""
        with self._lock:
            # Dynamically evaluate multi-axle kinematic load transfer strictly for the active selected vehicle
            if self.active_selected_vehicle_id is not None:
                sel_v = self.traffic_management.active_vehicles.get(
                    self.active_selected_vehicle_id,
                    self.traffic_management.vehicles.get(self.active_selected_vehicle_id),
                )
                if sel_v and hasattr(sel_v, "compute_kinematic_axles"):
                    sel_v.params["KinematicAxles"] = sel_v.compute_kinematic_axles()

            vehicle_raw = {}
            for vehicle_id, vehicle in list(self.traffic_management.active_vehicles.items()):
                vehicle_raw[vehicle_id] = vehicle.params
            self.vehicle_raw = vehicle_raw

            features = []
            selected_id = self.active_selected_vehicle_id
            for vid, point in vehicle_raw.items():
                if selected_id is not None and str(vid) == str(selected_id):
                    props = point.copy()
                else:
                    # Slim broadcast payload for unselected vehicles (~80% smaller SSE delta)
                    props = {
                        k: v for k, v in point.items()
                        if k not in ("FederationContract", "Trajectory", "State", "KinematicAxles")
                    }
                props["id"] = vid
                coords_str = str(point.get("State", {}).get("Coordinates", "13.5, 51.1")).split(",")
                features.append({
                    "type": "Feature",
                    "properties": props,
                    "geometry": {
                        "coordinates": [
                            float(coords_str[0]),
                            float(coords_str[-1]),
                        ],
                        "type": "Point",
                    },
                })

            self.vehicles_geojson = {
                "type": "FeatureCollection",
                "features": features,
            }
            self.warning_geojson = self.world.warning_geojson
            self.drone_geojson = self.world.drone_geojson

    def fiware_request(self, obj_type: str, entity_id: Any) -> Dict[str, Any]:
        """Query a single entity from the FIWARE Orion Context Broker by type and ID."""
        orion_host = os.getenv("ORION_HOST", "localhost")
        url = f"http://{orion_host}:1026/v2/entities/{entity_id}"
        payload = {"type": obj_type, "options": "keyValues"}
        headers = {"fiware-service": "openiot", "fiware-servicepath": "/"}
        try:
            response = requests.get(url, headers=headers, params=payload, timeout=2.5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.warning(f"FIWARE entity request failed ({obj_type}:{entity_id}): {e}")
            return {"Wrong request": f"{obj_type} | {entity_id}"}

    def get_fiware_entities(self) -> List[Dict[str, Any]]:
        """Retrieve all active context entities from the broker or live Orion endpoint."""
        from data_curation import get_entities
        ents = get_entities()
        if ents:
            return ents
        if not self.fiware_flag:
            return []
        orion_host = os.getenv("ORION_HOST", "localhost")
        url = f"http://{orion_host}:1026/v2/entities"
        headers = {"fiware-service": "openiot", "fiware-servicepath": "/"}
        params = {"options": "keyValues", "limit": 1000}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=2.5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.warning(f"FIWARE error fetching entities: {e}")
            return []

    def delete_fiware_entity(self, entity_id: str) -> bool:
        """Delete a context entity from the active data broker and Orion when enabled."""
        from data_curation import delete_entity

        deleted_broker = delete_entity(entity_id)
        if not self.fiware_flag:
            return deleted_broker
        orion_host = os.getenv("ORION_HOST", "localhost")
        url = f"http://{orion_host}:1026/v2/entities/{entity_id}"
        headers = {"fiware-service": "openiot", "fiware-servicepath": "/"}
        try:
            response = requests.delete(url, headers=headers, timeout=2.5)
            response.raise_for_status()
            return True
        except Exception as e:
            logging.warning(f"FIWARE error deleting entity {entity_id}: {e}")
            return deleted_broker

    def inspect_object(self, active_selection: Dict[str, Any]) -> Tuple[Any, Any, Any, Any, Any]:
        """Thread-safe polymorphic inspection resolver for all clickable map entity types."""
        with self._lock:
            return self._inspect_object_unlocked(active_selection)

    def _inspect_object_unlocked(self, active_selection: Dict[str, Any]) -> Tuple[Any, Any, Any, Any, Any]:
        """
        Resolve polymorphic inspection metadata for all clickable map entity types.

        Supports:
        1. Vehicles (``SingleVehicleStateDS``)
        2. Roadside Units (``SingleRoadsideUnitsStateDS``)
        3. Road Segments & State Points (``SingleRoadSegmentStateDS``, ``SingleRoadPointStateDS``)
        4. Highway Intersections / Junctions (``SingleExitStateDS``)
        5. Hydrological Water Sources (``SingleWaterStateDS``)
        6. Autonomous Inspection Drones (``SingleDroneStateDS``)
        7. Structural Warning Points (``SingleWarningStateDS``)
        """
        ret: Any = None
        stats: Any = None
        temp_simp_fm: Any = None
        temp_simp_code: Any = None
        mech_code: Any = None

        try:
            for k, v in active_selection.items():
                if k not in ["Vehicle", "SingleVehicleStateDS"]:
                    self.active_selected_vehicle_id = None
                props = v.get("properties", {})
                lookup_id = props.get("id", props.get("ID"))
                try:
                    int_id = int(float(str(lookup_id))) if lookup_id is not None else None
                except (ValueError, TypeError):
                    int_id = lookup_id

                # ------------------------------------------------------------------
                # CASE 1: ROADSIDE UNIT (RSU Edge Node)
                # ------------------------------------------------------------------
                if k in ["RU", "SingleRoadsideUnitsStateDS"]:
                    rsu_feat = None
                    for rf in self.world.roadside_units.get("features", []):
                        if str(rf.get("properties", {}).get("id")) == str(lookup_id):
                            rsu_feat = rf
                            break
                    if not rsu_feat:
                        rsu_feat = v

                    weather_id = rsu_feat.get("Weather", v.get("Weather", props.get("Weather")))
                    try:
                        w_lookup = int(float(str(weather_id)))
                    except Exception:
                        w_lookup = weather_id

                    w_obj = self.world.weather_objects.get(
                        w_lookup, list(self.world.weather_objects.values())[0]
                    )
                    w_state = w_obj.state if w_obj else {}

                    rsu_props = copy.deepcopy(rsu_feat.get("properties", props))
                    rsu_id_str = str(rsu_props.get("id", lookup_id))
                    contracts = self.world.federation_manager.get_contracts_for_rsu(rsu_id_str)
                    drones_info = [
                        self.world.drone_objects[did].to_dict()
                        for did in rsu_feat.get("Drones", [])
                        if did in self.world.drone_objects
                    ]
                    warnings_info = [
                        self.world.warning_objects[wid].to_dict()
                        for wid in rsu_feat.get("AssignedWarnings", [])
                        if wid in self.world.warning_objects
                    ]

                    rsu_props.update({
                        "Weather": w_state.get("Weather", "Sunny"),
                        "AirTemperature": round(float(w_state.get("AirTemperature", 22.0)), 2),
                        "RoadSurfaceTemperature": round(float(w_state.get("RoadSurfaceTemperature", 26.0)), 2),
                        "ActiveContractsCount": len(contracts),
                        "FederationContracts": contracts,
                        "StationedDrones": drones_info,
                        "AssignedWarnings": warnings_info,
                        "TransitionMatrix": self.global_config.get("Weather", {}).get("TransitionProbabilities", {}),
                    })
                    rsu_props["StatsSynthetic"] = not bool(w_obj and getattr(w_obj, "statistic", None))
                    ret = rsu_props

                    try:
                        stats = pd.DataFrame(w_obj.statistic) if (w_obj and w_obj.statistic) else pd.DataFrame([w_state])
                    except Exception:
                        stats = pd.DataFrame([w_state])
                        rsu_props["StatsSynthetic"] = True

                    # Provide FODA & Heraklit HPN representation for the RSU's local sector
                    rsu_fm = fm.clone_feature_model()
                    fm.toggle_feature(rsu_fm, str(w_state.get("Weather", "Sunny")))
                    rsu_hpn = HeraklitHPNController()
                    rsu_hpn.step(
                        rsu_id=rsu_id_str,
                        weather_state=str(w_state.get("Weather", "Sunny")),
                        road_material="Asphalt",
                        air_temp=float(w_state.get("AirTemperature", 22.0)),
                        road_temp=float(w_state.get("RoadSurfaceTemperature", 26.0)),
                        soil_temp=14.5,
                        velocity_kmh=90.0,
                        weight_kg=35000.0,
                        mechanical_simulation={"Model": "POD", "Accuracy": 0.98, "Threshold": 0.90},
                    )
                    rsu_props["HPN_Graph"] = rsu_hpn.to_dict()
                    temp_simp_fm = rsu_fm
                    act_f = fm.get_active_features(rsu_fm)
                    temp_simp_code = fm.get_code(
                        fm.compose_simulation_class(act_f),
                        rsu_hpn.generate_heraklit_code_snippet(act_f),
                    )
                    mech_code = None

                # ------------------------------------------------------------------
                # CASE 2: MOVING VEHICLE (HGV Federate)
                # ------------------------------------------------------------------
                elif k in ["Vehicle", "SingleVehicleStateDS"]:
                    v_obj = self.traffic_management.active_vehicles.get(
                        int_id,
                        self.traffic_management.active_vehicles.get(
                            lookup_id,
                            self.traffic_management.vehicles.get(
                                int_id, self.traffic_management.vehicles.get(lookup_id)
                            ),
                        ),
                    )
                    if v_obj:
                        self.active_selected_vehicle_id = v_obj.id
                        if hasattr(v_obj, "compute_kinematic_axles"):
                            kin_axles = v_obj.compute_kinematic_axles()
                            v_obj.params["KinematicAxles"] = kin_axles
                        ret = copy.deepcopy(v_obj.params)
                        ret["HPN_Graph"] = v_obj.hpn_state
                        ret["FederationContract"] = v_obj.federation_contract
                        stat_rows = list(v_obj.statistic)
                        is_padded = False
                        if len(stat_rows) < 4 and stat_rows:
                            is_padded = True
                            base_row = stat_rows[0]
                            now_dt = datetime.datetime.now()
                            padded = []
                            for i in range(5 - len(stat_rows)):
                                r = copy.deepcopy(base_row)
                                r["Timestamp"] = (now_dt - datetime.timedelta(seconds=(5 - i) * 2)).strftime("%Y-%m-%d %H:%M:%S")
                                v_nom = float(base_row.get("Velocity", 88.0))
                                r["Velocity"] = round(v_nom, 1)
                                padded.append(r)
                            stat_rows = padded + stat_rows
                        ret["StatsSynthetic"] = is_padded or not bool(stat_rows)
                        stats = pd.DataFrame(stat_rows)
                        temp_simp_fm = v_obj.feature_model
                        temp_simp_code = v_obj.code
                        mech_code = ""
                    else:
                        ret = copy.deepcopy(self.vehicle_raw.get(int_id, self.vehicle_raw.get(lookup_id, props)))
                        if isinstance(ret, dict):
                            ret["StatsSynthetic"] = False
                        stats = pd.DataFrame()
                        temp_simp_fm = None
                        temp_simp_code = None
                        mech_code = None

                # ------------------------------------------------------------------
                # CASE 3: ROAD SEGMENT OR ROAD STATE POINT
                # ------------------------------------------------------------------
                elif k in ["Road", "SingleRoadPointStateDS", "RoadSegment", "SingleRoadSegmentStateDS"]:
                    seg_props = copy.deepcopy(props)
                    seg_id = seg_props.get("segment_id") or seg_props.get("id")
                    if hasattr(self.world.road, "road_segments_by_id") and seg_id in self.world.road.road_segments_by_id:
                        live_seg = self.world.road.road_segments_by_id[seg_id]
                        seg_props.update(live_seg.get("properties", {}))

                    dist_km = float(seg_props.get("dist") or seg_props.get("station_mid_km") or seg_props.get("station_start_km") or 10.0)
                    direction = int(seg_props.get("direction", 1))
                    env_state = self.world.get_states_for_position(dist_km, direction)

                    road_struct_key = seg_props.get("road", env_state.get("RoadStructure", "RoadStructure_1"))
                    road_cfg = self.world.road_config.get(road_struct_key, {})
                    road_mat = list(road_cfg.get("RoadType", {"Asphalt": {}}).keys())[0]

                    air_t = float(env_state.get("AirTemperature", 23.0))
                    surf_t = float(env_state.get("RoadSurfaceTemperature", 28.0))
                    soil_t = float(env_state.get("SoilTemperature", 14.5))
                    weather_s = str(env_state.get("WeatherState", "Sunny"))

                    seg_props.update({
                        "AirTemperature": air_t,
                        "RoadSurfaceTemperature": surf_t,
                        "SoilTemperature": soil_t,
                        "WeatherState": weather_s,
                        "RoadMaterial": road_mat,
                        "RoadStructure": road_struct_key,
                        "RoadStructureConfig": road_cfg,
                        "RoadsideUnit": env_state.get("RoadsideUnit"),
                        "RoadsideUnitName": env_state.get("RoadsideUnitName"),
                        "RoadsideUnitDist": env_state.get("RoadsideUnitDist"),
                        "PassesCount": int(seg_props.get("passes_count", 18)),
                        "CumulativeDamage": round(float(seg_props.get("cumulative_damage", 0.42)), 3),
                    })

                    # Build a 12-point historical thermal & health log so ThermalSimulation.vue
                    # and StatisticsCharts.vue render full charts for any selected Road Segment!
                    now_dt = datetime.datetime.now()
                    ts_list = [
                        (now_dt - datetime.timedelta(seconds=(11 - i) * 5)).strftime("%H:%M:%S")
                        for i in range(12)
                    ]
                    surf_series = [round(surf_t - 0.6 * math.sin(i * 0.5), 2) for i in range(12)]
                    air_series = [round(air_t - 0.3 * math.cos(i * 0.5), 2) for i in range(12)]
                    soil_series = [round(soil_t, 2) for _ in range(12)]
                    struct_series = [road_struct_key for _ in range(12)]

                    stats = pd.DataFrame({
                        "Timestamp": ts_list,
                        "RoadSurfaceTemperature": surf_series,
                        "AirTemperature": air_series,
                        "SoilTemperature": soil_series,
                        "RoadStructure": struct_series,
                        "Kilometer": [round(dist_km, 2) for _ in range(12)],
                    })

                    # Synthesize FODA + Heraklit HPN for this Road Segment
                    seg_fm = fm.clone_feature_model()
                    fm.toggle_feature(seg_fm, road_mat)
                    fm.toggle_feature(
                        seg_fm,
                        "Westergaard" if str(road_mat).strip().lower() == "concrete" else "Boussinesq",
                    )
                    fm.toggle_feature(seg_fm, weather_s)
                    seg_hpn = HeraklitHPNController()
                    seg_hpn.step(
                        rsu_id=str(env_state.get("RoadsideUnit") or "rsu_00"),
                        weather_state=weather_s,
                        road_material=road_mat,
                        air_temp=air_t,
                        road_temp=surf_t,
                        soil_temp=soil_t,
                        velocity_kmh=90.0,
                        weight_kg=35000.0,
                        mechanical_simulation={"Model": "POD", "Accuracy": 0.97, "Threshold": 0.90},
                    )
                    seg_props["HPN_Graph"] = seg_hpn.to_dict()
                    seg_props["StatsSynthetic"] = True
                    ret = seg_props
                    temp_simp_fm = seg_fm
                    act_f = fm.get_active_features(seg_fm)
                    temp_simp_code = fm.get_code(
                        fm.compose_simulation_class(act_f),
                        seg_hpn.generate_heraklit_code_snippet(act_f),
                    )
                    mech_code = None

                # ------------------------------------------------------------------
                # CASE 4: HIGHWAY INTERSECTION / JUNCTION (Anschlussstelle / Dreieck)
                # ------------------------------------------------------------------
                elif k in ["Exit", "SingleExitStateDS"]:
                    jct_props = copy.deepcopy(props)
                    for sp in self.world.road_spawn_metadata.get("features", []):
                        if str(sp.get("properties", {}).get("id")) == str(lookup_id):
                            jct_props.update(sp.get("properties", {}))
                            break

                    station_km = float(jct_props.get("ClosestPoint", 0.0))
                    active_origin = 0
                    active_dest = 0
                    dir1_count = 0
                    dir2_count = 0
                    for v_obj in self.traffic_management.active_vehicles.values():
                        if str(v_obj.params.get("StartJunctionID")) == str(jct_props.get("id")):
                            active_origin += 1
                        if str(v_obj.params.get("EndJunctionID")) == str(jct_props.get("id")):
                            active_dest += 1
                        if v_obj.direction == 1:
                            dir1_count += 1
                        else:
                            dir2_count += 1

                    env_state = self.world.get_states_for_position(station_km, 1)
                    air_t = float(env_state.get("AirTemperature", 22.0))
                    surf_t = float(env_state.get("RoadSurfaceTemperature", 26.5))
                    soil_t = float(env_state.get("SoilTemperature", 14.5))
                    jct_props.update({
                        "StationKm": round(station_km, 2),
                        "ActiveInboundVehicles": active_dest,
                        "ActiveOutboundVehicles": active_origin,
                        "CorridorDir1Active": dir1_count,
                        "CorridorDir2Active": dir2_count,
                        "LocalWeather": env_state.get("WeatherState", "Sunny"),
                        "LocalAirTemp": air_t,
                        "ConnectedRSU": env_state.get("RoadsideUnitName", "RSU Hub"),
                        "StatsSynthetic": True,
                    })
                    ret = jct_props

                    now_dt = datetime.datetime.now()
                    stats = pd.DataFrame({
                        "Timestamp": [
                            (now_dt - datetime.timedelta(seconds=(11 - i) * 5)).strftime("%H:%M:%S")
                            for i in range(12)
                        ],
                        "RoadSurfaceTemperature": [round(surf_t - 0.5 * math.sin(i * 0.5), 2) for i in range(12)],
                        "AirTemperature": [round(air_t - 0.25 * math.cos(i * 0.5), 2) for i in range(12)],
                        "SoilTemperature": [round(soil_t, 2) for _ in range(12)],
                        "ActiveCorridorFleet": [max(1, dir1_count + dir2_count + int(math.sin(i))) for i in range(12)],
                    })

                # ------------------------------------------------------------------
                # CASE 5: WATER SOURCE / HYDROLOGICAL NODE
                # ------------------------------------------------------------------
                elif k in ["Water", "SingleWaterStateDS"]:
                    w_props = copy.deepcopy(props)
                    for wf in self.world.road_water_metadata.get("features", []):
                        if str(wf.get("properties", {}).get("id")) == str(lookup_id):
                            w_props.update(wf.get("properties", {}))
                            break

                    # Compute radial moisture attenuation curve (0 km to 5 km)
                    affect_m = float(w_props.get("influence_radius_m", 5000.0))
                    dry_t = float(w_props.get("soil_temp_dry_c", 15.0))
                    wet_t = float(w_props.get("soil_temp_saturated_c", 10.0))
                    radial_profile = []
                    for d_m in [0, 500, 1000, 2000, 3000, 4000, 5000]:
                        coef = max(0.0, 1.0 - (d_m / affect_m))
                        t_soil = round(dry_t - (dry_t - wet_t) * coef, 2)
                        radial_profile.append({
                            "distance_m": d_m,
                            "moisture_coef": round(coef, 2),
                            "soil_temp_c": t_soil,
                        })
                    w_props["RadialAttenuationProfile"] = radial_profile
                    w_props["StatsSynthetic"] = True
                    ret = w_props

                    stats = pd.DataFrame({
                        "Timestamp": [f"{pt['distance_m']} m" for pt in radial_profile],
                        "SoilTemperature": [pt["soil_temp_c"] for pt in radial_profile],
                        "MoistureSaturationPct": [round(pt["moisture_coef"] * 100.0, 1) for pt in radial_profile],
                        "BaselineDrySoilTemp": [dry_t for _ in radial_profile],
                    })

                # ------------------------------------------------------------------
                # CASE 6: AUTONOMOUS INSPECTION DRONE (UAV)
                # ------------------------------------------------------------------
                elif k in ["Drone", "SingleDroneStateDS"]:
                    drone_obj = self.world.drone_objects.get(str(lookup_id))
                    if drone_obj:
                        ret = drone_obj.to_dict()
                        if drone_obj.statistic:
                            ret["StatsSynthetic"] = False
                            stats = pd.DataFrame(drone_obj.statistic)
                        else:
                            ret["StatsSynthetic"] = True
                            now_dt = datetime.datetime.now()
                            stats = pd.DataFrame({
                                "Timestamp": [
                                    (now_dt - datetime.timedelta(seconds=(7 - i) * 2)).strftime("%H:%M:%S")
                                    for i in range(8)
                                ],
                                "Altitude": [round(float(ret.get("Altitude", 50.0)) * min(1.0, (i + 1) / 4.0), 1) for i in range(8)],
                                "Velocity": [float(ret.get("Velocity", 108.0)) for _ in range(8)],
                                "BatteryPct": [round(float(ret.get("BatteryPct", 95.0)) + (7 - i) * 0.2, 1) for i in range(8)],
                                "MissionProgressPct": [round(float(ret.get("MissionProgressPct", 45.0)) * ((i + 1) / 8.0), 1) for i in range(8)],
                            })
                    else:
                        ret = copy.deepcopy(props)
                        stats = pd.DataFrame()

                # ------------------------------------------------------------------
                # CASE 7: STRUCTURAL WARNING POINT
                # ------------------------------------------------------------------
                elif k in ["Warning", "SingleWarningStateDS"]:
                    warn_obj = self.world.warning_objects.get(str(lookup_id))
                    if warn_obj:
                        ret = warn_obj.to_dict()
                    else:
                        ret = copy.deepcopy(props)
                    if isinstance(ret, dict):
                        ret["StatsSynthetic"] = True

                    w_km = float(ret.get("Kilometer", ret.get("Position", 42.4)))
                    w_dir = int(ret.get("Direction", 1))
                    env_state = self.world.get_states_for_position(w_km, w_dir)
                    surf_t = float(ret.get("SurfaceTempAtTrigger", env_state.get("RoadSurfaceTemperature", 27.2)))
                    air_t = float(env_state.get("AirTemperature", 22.5))
                    rut_mm = float(ret.get("EstimatedRutDepthMm", 6.8))
                    prog_pct = float(ret.get("InspectionProgressPct", 50.0))

                    now_dt = datetime.datetime.now()
                    stats = pd.DataFrame({
                        "Timestamp": [
                            (now_dt - datetime.timedelta(seconds=(11 - i) * 5)).strftime("%H:%M:%S")
                            for i in range(12)
                        ],
                        "RoadSurfaceTemperature": [round(surf_t - 0.8 + (i / 11.0) * 0.8, 2) for i in range(12)],
                        "AirTemperature": [round(air_t - 0.3 * math.cos(i * 0.4), 2) for i in range(12)],
                        "EstimatedRutDepthMm": [round(rut_mm * (0.72 + 0.28 * (i / 11.0)), 2) for i in range(12)],
                        "InspectionProgressPct": [round(prog_pct * (i / 11.0), 1) for i in range(12)],
                    })

                else:
                    ret = props
                    stats = props
        except Exception as e:
            logging.error(f"Error in inspect_object: {e}")
            traceback.print_exc()
        return ret, stats, temp_simp_fm, temp_simp_code, mech_code
