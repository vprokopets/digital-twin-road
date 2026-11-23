"""
world/world.py — Digital Twin Corridor Environment, Infrastructure & Federation World
=====================================================================================

Project: Digital Twin Road Demonstrator

Manages:
- Corridor GIS infrastructure (`Road`, `RoadsideUnits`, `Intersections/Spawn`, `WaterSources`)
- Micro-climate weather stations (`RealTimePiWeather` on RSU-00, `Weather` Markov chains on RSU-01..10)
- Autonomous UAV inspection drones (`AerialDrone`) and structural warnings (`Warning`)
- Dynamic HLA/FOM + Heraklit federation contracts (`CorridorFederationManager`)
"""

from __future__ import annotations
import bisect
import copy
import datetime
import json
from pathlib import Path
import threading
from typing import Dict, Any, List, Tuple, Optional

from world.road import Road
from world.weather import Weather
from world.weather_sources import RealTimePiWeather
from world.federation import CorridorFederationManager
from vehicle.aerial_drone import AerialDrone
from data_curation import get_broker_status, register_device, send_telemetry
from world.scenario_loader import get_active_scenario


class World:
    """Manages corridor road infrastructure, weather stations, UAV patrol fleet, warnings, and HLA contracts."""

    def __init__(self, params: Dict[str, Any], fiware_flag: bool) -> None:
        self.fiware_flag = fiware_flag
        self.parameters = params
        self.federation_manager = CorridorFederationManager()
        self.warnings: List[Any] = []
        self._dirty_segments: Dict[str, Tuple[int, int]] = {}
        self.dirty_version: int = 0
        self._dirty_lock = threading.Lock()
        self.drone_geojson: Dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [],
        }
        self.warning_geojson: Dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [],
        }

    @property
    def dirty_segments(self) -> Dict[str, int]:
        """Backwards compatibility property returning the latest known state map."""
        with self._dirty_lock:
            return {k: v[1] for k, v in self._dirty_segments.items()}

    def mark_segment_dirty(self, seg_id: str, new_state: int) -> None:
        """Thread-safe registration of a road segment or point state update."""
        with self._dirty_lock:
            self.dirty_version += 1
            self._dirty_segments[seg_id] = (self.dirty_version, new_state)

    def get_dirty_segments_since(self, since_version: int = 0) -> Tuple[int, Dict[str, int]]:
        """
        Return thread-safe segment state deltas for SSE clients.

        Returns ``(current_version, {id: new_state})`` containing only segments
        mutated after ``since_version``.
        """
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

    def _should_publish_broker(self) -> bool:
        """Returns True when Orion FIWARE or the local Native data broker should receive updates."""
        if self.fiware_flag is True:
            return True
        return get_broker_status().get("backend") == "native"

    def _recompute_rsu_road_associations(self) -> None:
        """Recomputes RSU ClosestPoint distances and per-road-point ClosestRoadsideUnitId lookups."""
        road_pts = getattr(getattr(self, "road", None), "road_structure_metadata_processed", {}).get("features", [])
        if not road_pts:
            return
        coord_sys = self.road.coord_system
        rsu_features = self.roadside_units.get("features", [])
        for ru_pt in rsu_features:
            coords = ru_pt.get("geometry", {}).get("coordinates", [])
            if len(coords) < 2:
                continue
            best_dist = 1e6
            best_pos = 0.0
            for pt in road_pts:
                pt_coords = pt["geometry"]["coordinates"]
                d_km = coord_sys.distance_km(pt_coords[0], pt_coords[1], coords[0], coords[1])
                if d_km < best_dist:
                    best_dist = d_km
                    best_pos = float(pt["properties"].get("dist", 0.0))
            ru_pt["properties"].update({
                "ClosestPoint": best_pos,
                "ClosestPointDist": best_dist,
            })

        for pt in road_pts:
            pt_dist = float(pt["properties"].get("dist", 0.0))
            min_ru_diff = 1e6
            closest_ru = None
            for ru_pt in rsu_features:
                ru_pos = float(ru_pt.get("properties", {}).get("ClosestPoint", 0.0))
                diff = abs(pt_dist - ru_pos)
                if diff < min_ru_diff:
                    min_ru_diff = diff
                    closest_ru = ru_pt
            pt["properties"]["ClosestRU"] = min_ru_diff
            pt["properties"]["ClosestRoadsideUnitId"] = (
                closest_ru["properties"].get("id") if closest_ru else None
            )

    def sync_roadside_units(self, new_rsu_fc: Dict[str, Any]) -> None:
        """
        Reconcile runtime weather stations, UAV fleets, and spatial RSU associations.

        Called after Scenario Editor saves or RSU mutations.
        """
        synced_fc = copy.deepcopy(new_rsu_fc) if new_rsu_fc else {"type": "FeatureCollection", "features": []}
        old_by_id = {
            str(f.get("properties", {}).get("id")): f
            for f in self.roadside_units.get("features", [])
            if f.get("properties", {}).get("id") is not None
        }
        now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sim_scale = float(self.parameters.get("Simulation", {}).get("SimulationScale", 5.0))
        kept_weather_keys = set()
        kept_drone_ids = set()

        for index, feat in enumerate(synced_fc.get("features", [])):
            props = feat.setdefault("properties", {})
            rs_id = str(props.get("id") or f"rsu_{index:02d}")
            props["id"] = rs_id
            rs_name = str(props.get("name") or f"RSU-{index:02d}")
            old_feat = old_by_id.get(rs_id)

            w_key = old_feat.get("Weather") if old_feat else None
            if w_key is None or w_key not in self.weather_objects:
                weather_obj = Weather(self.parameters)
                weather_obj.update_state(now_ts)
                w_key = id(weather_obj)
                self.weather_objects[w_key] = weather_obj
                props.setdefault("sensor_source", "Markov Chain Micro-Climate Simulator")
            else:
                old_props = old_feat.get("properties", {})
                if "sensor_source" in old_props and "sensor_source" not in props:
                    props["sensor_source"] = old_props["sensor_source"]
                weather_obj = self.weather_objects[w_key]

            kept_weather_keys.add(w_key)
            feat["Weather"] = w_key
            cur_w_state = getattr(weather_obj, "state", {})
            props.setdefault("WeatherState", cur_w_state.get("Weather", "Sunny"))
            props.setdefault("AirTemperature", round(float(cur_w_state.get("AirTemperature", 22.0)), 2))
            props.setdefault("RoadSurfaceTemperature", round(float(cur_w_state.get("RoadSurfaceTemperature", 26.0)), 2))
            props.setdefault("LastUpdated", cur_w_state.get("Timestamp", now_ts))

            existing_drones = [
                did for did in (old_feat.get("Drones", []) if old_feat else [])
                if did in self.drone_objects
            ]
            if not existing_drones:
                coords = feat.get("geometry", {}).get("coordinates", [13.5, 51.1])
                aerial_drone = AerialDrone(
                    position_lon_lat=coords,
                    simulation_interval=sim_scale,
                    rsu_id=rs_id,
                    rsu_name=rs_name,
                    drone_index=1,
                )
                self.drone_objects[aerial_drone.id] = aerial_drone
                existing_drones = [aerial_drone.id]
            else:
                coords = feat.get("geometry", {}).get("coordinates", [])
                if len(coords) >= 2:
                    for did in existing_drones:
                        d_obj = self.drone_objects.get(did)
                        if d_obj and d_obj.state == "Idle":
                            d_obj.home_position = [float(coords[0]), float(coords[1])]
                            d_obj.current_position = [float(coords[0]), float(coords[1])]

            kept_drone_ids.update(existing_drones)
            feat["Drones"] = existing_drones
            props["drone_id"] = existing_drones[0]
            feat["AssignedWarnings"] = list(old_feat.get("AssignedWarnings", [])) if old_feat else []

            if old_feat is None and self._should_publish_broker():
                register_device(device_id=rs_id, entity_type="Roadside_unit", api_key="rs", geo_data=feat)

        for orphan_w_key in list(self.weather_objects.keys()):
            if orphan_w_key not in kept_weather_keys:
                self.weather_objects.pop(orphan_w_key, None)

        for orphan_d_id in list(self.drone_objects.keys()):
            if orphan_d_id not in kept_drone_ids and self.drone_objects[orphan_d_id].state == "Idle":
                self.drone_objects.pop(orphan_d_id, None)

        self.roadside_units = synced_fc
        self._recompute_rsu_road_associations()
        self.prepare_geojson()

    def read_road_metadata(self) -> None:
        """Loads scenario infrastructure, initializes weather stations/drones, and builds Road spatial indices."""
        scenario = get_active_scenario()
        self.road_spawn_metadata = scenario.get_spawn_points()
        for idx, point in enumerate(self.road_spawn_metadata.get("features", [])):
            sp_id = point["properties"].get("id", f"jct_{idx:02d}")
            point["properties"].update({
                "id": sp_id,
                "ClosestPoint": 0.0,
                "ClosestPointDist": 1e6,
                "vehicles_spawned": point["properties"].get("vehicles_spawned", 0),
                "vehicles_destined": point["properties"].get("vehicles_destined", 0),
            })

        self.road_water_metadata = scenario.get_water_sources()
        for idx, point in enumerate(self.road_water_metadata.get("features", [])):
            w_id = point["properties"].get("id", f"water_{idx:02d}")
            point["properties"].update({
                "id": w_id,
                "ClosestPoint": 0.0,
                "ClosestPointDist": 1e6,
            })

        self.roadside_units = scenario.get_roadside_units()
        self.embedded_sensors = scenario.get_embedded_sensors()
        for point in self.roadside_units.get("features", []):
            rs_id = point["properties"].get("id", f"rsu_{id(point)}")
            point["properties"]["id"] = rs_id
            if self._should_publish_broker():
                register_device(device_id=rs_id, entity_type="Roadside_unit", api_key="rs", geo_data=point)
            point["properties"].update({
                "ClosestPoint": point["properties"].get("ClosestPoint", 0.0),
                "ClosestPointDist": 1e6,
            })

        self.weather_objects: Dict[Any, Any] = {}
        self.drone_objects: Dict[str, AerialDrone] = {}
        self.warning_objects: Dict[str, Any] = {}

        for index, roadside_unit in enumerate(self.roadside_units["features"]):
            rs_props = roadside_unit.get("properties", {})
            rs_id = rs_props.get("id", f"rsu_{index:02d}")
            rs_name = rs_props.get("name", f"RSU-{index:02d}")

            if index == 0:
                weather_obj = RealTimePiWeather(self.parameters)
                rs_props["sensor_source"] = "RealTime Raspberry Pi Weather Station"
            else:
                weather_obj = Weather(self.parameters)
                rs_props["sensor_source"] = "Markov Chain Micro-Climate Simulator"

            w_key = id(weather_obj)
            self.weather_objects[w_key] = weather_obj
            roadside_unit.update({
                "Weather": w_key,
                "Drones": [],
                "AssignedWarnings": [],
            })

            aerial_drone = AerialDrone(
                position_lon_lat=roadside_unit["geometry"]["coordinates"],
                simulation_interval=float(self.parameters.get("Simulation", {}).get("SimulationScale", 5.0)),
                rsu_id=rs_id,
                rsu_name=rs_name,
                drone_index=1,
            )
            self.drone_objects[aerial_drone.id] = aerial_drone
            roadside_unit["Drones"].append(aerial_drone.id)
            rs_props["drone_id"] = aerial_drone.id

        configs_dir = Path(__file__).resolve().parent.parent / "configs"
        with open(configs_dir / "road_config.json", "r", encoding="utf-8") as f:
            self.road_config = json.load(f)

        with open(configs_dir / "road_structure.json", "r", encoding="utf-8") as f:
            self.road_structure = json.load(f)
        for point in self.road_structure["features"]:
            point["properties"].update({"ClosestPoint": 0.0, "ClosestPointDist": 1e6})

        with open(configs_dir / "road_geometry.json", "r", encoding="utf-8") as f:
            road_geometry = json.load(f)

        self.road = Road(
            self.road_config,
            road_geometry,
            self.road_structure,
            self.road_spawn_metadata,
            self.road_water_metadata,
            self.roadside_units,
        )

        num_spawns = max(1, len(self.road_spawn_metadata["features"]))
        for spawn_point in self.road_spawn_metadata["features"]:
            spawn_point["properties"].update({
                "TargetFrom": round(1.0 / num_spawns, 4),
                "TargetTo": round(1.0 / num_spawns, 4),
            })

        # Enrich water sources with affected road segment counts & thermal depression metrics
        self._compute_water_hydrological_impacts()
        self.prepare_geojson()

    def _compute_water_hydrological_impacts(self) -> None:
        """Precomputes hydrological impact metrics for each water source along the corridor."""
        affect_dist_km = float(
            self.parameters.get("WaterAffectDistance", self.parameters.get("WatterAffectDistance", 5000.0))
        ) / 1000.0
        dry_temp = float(self.parameters["StandardTemp"]["Soil"]["Dry"])
        wet_temp = float(self.parameters["StandardTemp"]["Soil"]["Wet"])

        for w_pt in self.road_water_metadata["features"]:
            w_props = w_pt["properties"]
            w_station = float(w_props.get("ClosestPoint", 0.0))
            w_min_dist_km = float(w_props.get("ClosestPointDist", 0.2))
            affected_segs: List[str] = []
            for pt in self.road.road_structure_metadata_processed["features"]:
                pt_dist = float(pt["properties"].get("dist", 0.0))
                if abs(pt_dist - w_station) <= affect_dist_km:
                    affected_segs.append(pt["properties"].get("segment_id", pt["properties"].get("id", "")))

            max_coef = max(0.0, 1.0 - (w_min_dist_km / max(0.1, affect_dist_km)))
            min_soil_temp = round(dry_temp - (dry_temp - wet_temp) * max_coef, 2)
            w_props.update({
                "station_km": round(w_station, 2),
                "distance_to_highway_m": round(w_min_dist_km * 1000.0, 1),
                "affected_segments_count": len(affected_segs),
                "affected_corridor_span_km": round(max(0.0, w_station - affect_dist_km), 1),
                "affected_corridor_end_km": round(w_station + affect_dist_km, 1),
                "max_moisture_coef": round(max_coef, 3),
                "soil_temp_dry_c": dry_temp,
                "soil_temp_saturated_c": wet_temp,
                "local_soil_temp_c": min_soil_temp,
                "thermal_depression_c": round(dry_temp - min_soil_temp, 2),
            })

    def _get_rsu_by_id(self, rsu_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Resolves an RSU GeoJSON feature by its properties.id."""
        if not rsu_id:
            return None
        target = str(rsu_id)
        for rf in self.roadside_units.get("features", []):
            if str(rf.get("properties", {}).get("id")) == target:
                return rf
        return None

    def register_warning(self, warning: Any, force: bool = False) -> Any:
        """
        Register a road anomaly warning and assign it to the nearest RSU and UAV.

        Includes spatial deduplication and active warning caps so background traffic
        never floods the corridor map with stale warning icons.
        """
        if not force:
            # Cap spontaneous background warnings so the map stays clean & legible
            if len(self.warning_objects) >= 6:
                return None
            # Deduplicate warnings within ±4.0 km of an existing warning
            for existing in self.warning_objects.values():
                if abs(float(getattr(existing, "position", 0.0)) - float(warning.position)) < 4.0:
                    return None
        else:
            # If manually triggered via '+ Warning' and over capacity, evict the oldest Inspected warning
            if len(self.warning_objects) >= 8:
                inspected_ids = [w.id for w in self.warning_objects.values() if w.state == "Inspected"]
                victim_id = inspected_ids[0] if inspected_ids else next(iter(self.warning_objects.keys()))
                self._remove_warning(victim_id)

        direction = getattr(warning, "direction", 1)
        ref_pt, _, _ = self.find_closest_point(warning.position, direction)
        warning.coordinates = list(ref_pt["geometry"]["coordinates"])

        pt_props = ref_pt.get("properties", {})
        warning.segment_id = pt_props.get("segment_id", pt_props.get("id", ""))
        warning.segment_name = pt_props.get("name", warning.segment_id)
        warning.segment_health = int(pt_props.get("state", 80))
        warning.road_structure = pt_props.get("road", "RoadStructure_1")

        roadside_unit = (
            self._get_rsu_by_id(pt_props.get("ClosestRoadsideUnitId"))
            or pt_props.get("ClosestRoadsideUnit")
        )
        if not roadside_unit and self.roadside_units["features"]:
            roadside_unit = self.roadside_units["features"][0]

        if roadside_unit:
            ru_props = roadside_unit.get("properties", {})
            warning.assigned_rsu_id = ru_props.get("id", "rsu_00")
            warning.assigned_rsu_name = ru_props.get("name", "RSU Hub")
            warning.assigned_rsu_dist_km = float(pt_props.get("ClosestRU", 1.5))
            roadside_unit["AssignedWarnings"].append(warning.id)

        self.warning_objects[warning.id] = warning
        return warning

    def _remove_warning(self, warn_id: str) -> None:
        """Removes an archived warning from `warning_objects` and RSU assignment lists."""
        self.warning_objects.pop(warn_id, None)
        for roadside_unit in self.roadside_units.get("features", []):
            assigned = roadside_unit.get("AssignedWarnings", [])
            if warn_id in assigned:
                assigned.remove(warn_id)

    def warning_handling(self) -> None:
        """Steps all autonomous UAVs, dispatches idle drones, and syncs/archives warnings."""
        # 1. Step every drone once per simulation tick
        for drone_obj in self.drone_objects.values():
            drone_obj.action_loop()

        # 2. Match Idle drones to New warnings at each RSU
        for roadside_unit in self.roadside_units["features"]:
            for warn_id in list(roadside_unit.get("AssignedWarnings", [])):
                warning_obj = self.warning_objects.get(warn_id)
                if not warning_obj or warning_obj.state != "New":
                    continue
                for drone_id in roadside_unit.get("Drones", []):
                    drone_obj = self.drone_objects.get(drone_id)
                    if drone_obj and drone_obj.state == "Idle":
                        drone_obj.establish_inspection_task(warning_obj)
                        warning_obj.update_state("Under Inspection")
                        break

        # 3. Synchronize live drone progress & auto-archive old Inspected warnings
        to_archive: List[str] = []
        for warn_id, warning_obj in list(self.warning_objects.items()):
            if warning_obj.state == "Inspected":
                warning_obj.drone_flight_state = "Mission Complete"
                warning_obj.inspection_progress_pct = 100.0
                warning_obj.inspected_ticks = getattr(warning_obj, "inspected_ticks", 0) + 1
                # Archive inspected warnings after ~45s if other warnings exist on the corridor
                if warning_obj.inspected_ticks > 45 and len(self.warning_objects) > 2:
                    to_archive.append(warn_id)
            elif warning_obj.state == "Under Inspection" and warning_obj.assigned_drone_id:
                d_obj = self.drone_objects.get(warning_obj.assigned_drone_id)
                if d_obj:
                    warning_obj.drone_flight_state = d_obj.state
                    warning_obj.inspection_progress_pct = d_obj.get_mission_progress_pct()
            else:
                warning_obj.drone_flight_state = "Queued for Dispatch"
                warning_obj.inspection_progress_pct = 0.0

        for wid in to_archive:
            self._remove_warning(wid)

    def prepare_geojson(self) -> None:
        """Builds GeoJSON FeatureCollections for active UAV drones and warning points."""
        drone_features = []
        for drone in list(self.drone_objects.values()):
            if drone.state != "Idle":
                drone_features.append({
                    "type": "Feature",
                    "properties": drone.to_dict(),
                    "geometry": {
                        "coordinates": [
                            float(drone.current_position[0]),
                            float(drone.current_position[1]),
                        ],
                        "type": "Point",
                    },
                })

        warning_features = []
        for warning in list(self.warning_objects.values()):
            if warning.coordinates:
                warning_features.append({
                    "type": "Feature",
                    "properties": warning.to_dict(),
                    "geometry": {
                        "coordinates": [
                            float(warning.coordinates[0]),
                            float(warning.coordinates[1]),
                        ],
                        "type": "Point",
                    },
                })

        self.drone_geojson = {
            "type": "FeatureCollection",
            "features": drone_features,
        }
        self.warning_geojson = {
            "type": "FeatureCollection",
            "features": warning_features,
        }

    def get_states_for_position(self, position: float, direction: int) -> Dict[str, Any]:
        """Interpolates continuous road coordinates and resolves local weather, soil temp, and nearest RSU."""
        ref_pt, _, _ = self.find_closest_point(position, direction)

        # High-resolution continuous road coordinate interpolation along OpenStreetMap centerline
        cur_lon: Optional[float] = None
        cur_lat: Optional[float] = None
        seg_list = getattr(self.road, "road_segments_dir1" if direction == 1 else "road_segments_dir2", None)
        seg_starts = getattr(self.road, "road_seg_starts_dir1" if direction == 1 else "road_seg_starts_dir2", None)
        if seg_list:
            if seg_starts:
                idx = bisect.bisect_right(seg_starts, position) - 1
                chosen_seg = seg_list[max(0, min(len(seg_list) - 1, idx))]
            else:
                est_idx = max(0, min(len(seg_list) - 1, int(position / 0.2)))
                chosen_seg = seg_list[est_idx]
                if not (chosen_seg["properties"]["station_start_km"] <= position <= chosen_seg["properties"]["station_end_km"]):
                    for s in seg_list:
                        if s["properties"]["station_start_km"] <= position <= s["properties"]["station_end_km"]:
                            chosen_seg = s
                            break
            st = chosen_seg["properties"]["station_start_km"]
            en = chosen_seg["properties"]["station_end_km"]
            coords = chosen_seg["geometry"]["coordinates"]
            span = max(1e-4, en - st)
            frac = max(0.0, min(1.0, (position - st) / span))
            fidx = frac * (len(coords) - 1)
            i0 = int(fidx)
            i1 = min(len(coords) - 1, i0 + 1)
            sub = fidx - i0
            c0 = coords[i0]
            c1 = coords[i1]
            cur_lon = c0[0] + (c1[0] - c0[0]) * sub
            cur_lat = c0[1] + (c1[1] - c0[1]) * sub

        if cur_lon is None or cur_lat is None:
            p0 = ref_pt["geometry"]["coordinates"]
            cur_lon = p0[0]
            cur_lat = p0[1]

        coord = f"{cur_lon:.6f}, {cur_lat:.6f}"

        closest_water = ref_pt["properties"].get("ClosestWater", 0.0)
        ru_metadata = (
            self._get_rsu_by_id(ref_pt["properties"].get("ClosestRoadsideUnitId"))
            or ref_pt["properties"].get("ClosestRoadsideUnit")
        )

        if not ru_metadata or "Weather" not in ru_metadata or ru_metadata["Weather"] not in self.weather_objects:
            best_ru = None
            min_ru_d = 1e6
            for ru in self.roadside_units["features"]:
                ru_st = ru["properties"].get("ClosestPoint", 0.0)
                d = abs(position - ru_st)
                if d < min_ru_d:
                    min_ru_d = d
                    best_ru = ru
            if best_ru:
                ru_metadata = best_ru
                ref_pt["properties"]["ClosestRoadsideUnitId"] = best_ru.get("properties", {}).get("id")
                ref_pt["properties"]["ClosestRU"] = min_ru_d

        weather_id = ru_metadata.get("Weather") if ru_metadata else list(self.weather_objects.keys())[0]
        closest_weather_point = self.weather_objects.get(weather_id, list(self.weather_objects.values())[0])

        water_affect_m = float(
            self.parameters.get("WaterAffectDistance", self.parameters.get("WatterAffectDistance", 5000.0))
        )
        water_coef = 1.0 - (abs(closest_water - position) * 1000.0 / water_affect_m)
        if water_coef >= 0:
            soil_temp = self.parameters["StandardTemp"]["Soil"]["Dry"] - (
                (self.parameters["StandardTemp"]["Soil"]["Dry"] - self.parameters["StandardTemp"]["Soil"]["Wet"]) * water_coef
            )
        else:
            soil_temp = self.parameters["StandardTemp"]["Soil"]["Dry"]

        ru_props = ru_metadata.get("properties", {}) if ru_metadata else {}
        ru_id = ru_props.get("id")
        ru_name = ru_props.get("name", f"RSU @ km {ru_props.get('ClosestPoint', 0.0)}")
        ru_town = ru_props.get("town", "A14 Corridor")
        ru_station = ru_props.get("ClosestPoint")
        ru_dist = round(ref_pt["properties"].get("ClosestRU", 0.0), 3) if ref_pt else None

        return {
            "Coordinates": coord,
            "AirTemperature": round(float(closest_weather_point.air_temp), 2),
            "RoadSurfaceTemperature": round(float(closest_weather_point.road_temp), 2),
            "SoilTemperature": round(float(soil_temp), 2),
            "RoadMetadata": self.road_config[ref_pt["properties"]["road"]],
            "WeatherState": closest_weather_point.current_state,
            "RoadStructure": ref_pt["properties"]["road"],
            "RoadsideUnit": ru_id,
            "RoadsideUnitName": ru_name,
            "RoadsideUnitTown": ru_town,
            "RoadsideUnitStation": ru_station,
            "RoadsideUnitDist": ru_dist,
        }

    def find_closest_point(self, position: float, direction: int = 1) -> Tuple[Dict[str, Any], int, float]:
        """Finds the nearest road health point to `position` (km) for `direction` in O(log M) via binary search."""
        pts_by_dir = getattr(self.road, "road_points_by_dir", None)
        dists_by_dir = getattr(self.road, "road_dists_by_dir", None)
        if pts_by_dir and dists_by_dir and direction in pts_by_dir and pts_by_dir[direction]:
            pts = pts_by_dir[direction]
            dists = dists_by_dir[direction]
            idx = bisect.bisect_left(dists, position)
            if idx == 0:
                best_idx = 0
            elif idx >= len(dists):
                best_idx = len(dists) - 1
            else:
                if abs(position - dists[idx - 1]) <= abs(dists[idx] - position):
                    best_idx = idx - 1
                else:
                    best_idx = idx
            return pts[best_idx], best_idx, abs(position - dists[best_idx])

        closest_point_index = 0
        dist = 1e6
        closest_point = None
        for index, point in enumerate(self.road.road_structure_metadata_processed["features"]):
            if point["properties"].get("direction", 1) != direction:
                continue
            if (new_dist := abs(position - point["properties"]["dist"])) < dist:
                dist = new_dist
                closest_point_index = index
                closest_point = point
            elif closest_point is not None and new_dist > dist:
                break
        if closest_point is None:
            closest_point = self.road.road_structure_metadata_processed["features"][0]
        return closest_point, closest_point_index, dist

    def update_weather_state(self, timestamp: str) -> None:
        """Advances each RSU weather station by one step and synchronizes RSU GeoJSON properties."""
        for index, roadside_unit in enumerate(self.roadside_units["features"]):
            w_key = roadside_unit.get("Weather")
            w_obj = self.weather_objects.get(w_key) if w_key is not None else None
            if w_obj is None:
                w_obj = Weather(self.parameters)
                w_key = id(w_obj)
                self.weather_objects[w_key] = w_obj
                roadside_unit["Weather"] = w_key
                roadside_unit.setdefault("Drones", [])
                roadside_unit.setdefault("AssignedWarnings", [])
                roadside_unit.setdefault("properties", {}).setdefault(
                    "sensor_source",
                    f"Markov Chain Micro-Climate Simulator ({index})",
                )
            w_obj.update_state(timestamp)

            # Sync latest weather readings onto RSU GeoJSON properties for instant UI access
            current_state = w_obj.state
            roadside_unit["properties"].update({
                "WeatherState": current_state.get("Weather", "Sunny"),
                "AirTemperature": round(float(current_state.get("AirTemperature", 22.0)), 2),
                "RoadSurfaceTemperature": round(float(current_state.get("RoadSurfaceTemperature", 26.0)), 2),
                "LastUpdated": timestamp,
            })

            if self._should_publish_broker():
                roadside_unit_sensor_data = {
                    "Weather": current_state["Weather"],
                    "AirTemperature": current_state["AirTemperature"],
                    "RoadSurfaceTemperature": current_state["RoadSurfaceTemperature"],
                }
                send_telemetry(
                    device_id=roadside_unit["properties"]["id"],
                    entity_type="Roadside_unit",
                    sensor_dict=roadside_unit_sensor_data,
                    api_key="rs",
                )

    def update_road_state(self, vehicle_id: Any, vehicle_obj: Any) -> None:
        """Applies vehicle pass wear to traversed road segments and registers dirty segment deltas."""
        v_dir = vehicle_obj.direction
        p_min = min(vehicle_obj.prev_position, vehicle_obj.position)
        p_max = max(vehicle_obj.prev_position, vehicle_obj.position)
        if hasattr(self.road, "get_points_in_range"):
            candidate_points = self.road.get_points_in_range(v_dir, p_min, p_max)
        else:
            candidate_points = [
                rp for rp in self.road.road_structure_metadata_processed["features"]
                if rp["properties"].get("direction", 1) == v_dir and p_min <= rp["properties"]["dist"] <= p_max
            ]
        for road_point in candidate_points:
            point_metadata = road_point.get("simulation", {})
            road_material_coef = 1.5 if "Asphalt" in point_metadata.get("Type", "Asphalt") else 1.0
            damage_adapted = float(vehicle_obj.params.get("Damage", 0.1)) * road_material_coef

            old_state = road_point["properties"]["state"]
            new_state = max(5, min(100, round(old_state - damage_adapted)))
            road_point["properties"]["state"] = new_state
            road_point["properties"]["passes_count"] = int(road_point["properties"].get("passes_count", 12)) + 1
            road_point["properties"]["cumulative_damage"] = round(
                float(road_point["properties"].get("cumulative_damage", 0.25)) + damage_adapted, 4
            )
            road_point["properties"]["last_vehicle_id"] = str(vehicle_id)

            seg_id = road_point["properties"].get("segment_id")
            pt_id = road_point["properties"].get("id")
            if pt_id:
                self.mark_segment_dirty(pt_id, new_state)
            if hasattr(self.road, "road_segments_by_id") and seg_id:
                self.mark_segment_dirty(seg_id, new_state)
                seg = self.road.road_segments_by_id.get(seg_id)
                if seg:
                    seg["properties"]["state"] = new_state
                    seg["properties"]["passes_count"] = road_point["properties"]["passes_count"]
                    seg["properties"]["cumulative_damage"] = road_point["properties"]["cumulative_damage"]
                    seg["properties"]["last_vehicle_id"] = str(vehicle_id)
