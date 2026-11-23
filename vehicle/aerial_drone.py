"""
vehicle/aerial_drone.py — Autonomous RSU Inspection UAV State Machine
=====================================================================

Project: Digital Twin Road Demonstrator

Models an autonomous quadcopter stationed at a Roadside Unit (RSU) drone hangar.
Compliant with German UAV airspace regulations (LuftVO § 21h / EASA Open & Specific Category)
and the multi-altitude mission profile:
1. Liftoff: Ascends vertically at home RSU from 0m up to 50m safety transit altitude.
2. CruisingToward: Cruises along the outer road verge / embankment (offset ~22m from road)
   at 50m transit altitude at 65–70 km/h.
3. DescendToInspect: Arrives beside the target anomaly on the embankment and descends
   from 50m down to 15–20m (nominal 18m).
4. Inspecting: Conducts high-resolution LiDAR and photogrammetric distress scan from the
   side at 15–20m altitude with subtle hover drift.
5. AscendToCruise: Ascends vertically from 18m back up to 50m transit altitude.
6. CruisingBack: Cruises along the outer road verge at 50m altitude back toward home RSU.
7. Landing: Descends vertically at home RSU pad from 50m down to 0m and docks (Idle).
"""

from __future__ import annotations
import datetime
import json
import logging
import math
import os
import random
from typing import Optional, Tuple, List, Dict, Any

from world.geo_utils import get_coord_system
from world.scenario_loader import get_active_scenario


class AerialDrone:
    """
    Geo-aware autonomous inspection drone stationed at an RSU hub.

    Note:
        ``initial_position`` and ``current_position`` are stored as ``(lon, lat)``
        to match GeoJSON coordinate ordering ``[lon, lat]``.
    """

    _CACHED_ROAD_SEGMENTS: Optional[List[Dict[str, Any]]] = None
    _CACHED_FLAT_ROAD_PTS: Optional[List[Tuple[float, float, float]]] = None  # (station_km, lon, lat)

    def __init__(
        self,
        position_lon_lat: List[float],
        simulation_interval: float = 5.0,
        rsu_id: str = "rsu_00",
        rsu_name: str = "RSU Hub",
        drone_index: int = 1,
    ) -> None:
        self.id: str = f"uav_{rsu_id}_{drone_index}"
        self.home_rsu_id: str = rsu_id
        self.home_rsu_name: str = rsu_name
        self.simulation_interval: float = float(simulation_interval or 5.0)

        self.state: str = "Idle"
        self.initial_position: Tuple[float, float] = (float(position_lon_lat[0]), float(position_lon_lat[1]))
        self.current_position: Tuple[float, float] = self.initial_position
        self.altitude: float = 0.0
        self.target_cruise_altitude: float = 50.0   # Transit / cruise altitude AGL (meters)
        self.target_inspect_altitude: float = 18.0  # Local inspection altitude AGL (meters, 15-20m)
        self.liftoff_speed: float = 5.0            # Vertical climb/descent speed (m/s)

        # Base cruising airspeed (68 km/h ≈ 18.89 m/s realistic survey UAV)
        self.cruise_speed_kmh: float = 68.0
        self.cruise_speed_mps: float = self.cruise_speed_kmh * 1000.0 / 3600.0

        self.current_inspection_obj: Optional[Any] = None
        self.inspection_target: Optional[Tuple[float, float]] = None  # (lon, lat)
        self.target_warning_id: str = "Standby"
        self.target_warning_km: float = 42.4
        self.target_anomaly_type: str = "Corridor Scan"
        self.initial_target_distance_m: float = 1000.0

        # Corridor waypoints along the road verge (LuftVO § 21h compliant)
        self.corridor_waypoints: List[List[float]] = []
        self.corridor_waypoint_idx: int = 0
        self.return_waypoints: List[List[float]] = []
        self.return_waypoint_idx: int = 0

        self.inspection_time: float = 18.0 + (random.random() * 6.0)
        self.time_spent_for_inspection: float = 0.0
        self.flight_time_sec: float = 0.0

        # Energetics & Telemetry
        self.battery_pct: float = 100.0
        self.cruise_drain_coef: float = 1.2
        self.inspect_drain_coef: float = 1.5
        self.bearing_deg: float = 0.0
        self.distance_to_target_m: float = 0.0
        self.missions_completed: int = 0
        self.flight_trail: List[List[float]] = []  # List of [lon, lat] breadcrumbs
        self.statistic: List[Dict[str, Any]] = []  # Multi-point flight telemetry history for charts

        # Active coordinate system strategy (WGS84 or LocalCartesian)
        self.coord_system = get_coord_system(get_active_scenario().coordinate_system)

        # Ensure road network geometry cache is loaded
        AerialDrone._ensure_road_segments_loaded()

    @classmethod
    def _ensure_road_segments_loaded(cls) -> None:
        """Loads and caches road network segments from config file once for all drones."""
        if cls._CACHED_ROAD_SEGMENTS is not None and cls._CACHED_FLAT_ROAD_PTS is not None:
            return

        possible_paths = [
            os.path.join("configs", "road_segments.geojson"),
            os.path.join(os.path.dirname(__file__), "..", "configs", "road_segments.geojson"),
            os.path.join(os.path.dirname(__file__), "..", "..", "configs", "road_segments.geojson"),
        ]

        for p in possible_paths:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    features = data.get("features", [])
                    dir1 = [s for s in features if s.get("properties", {}).get("direction", 1) == 1]
                    dir1.sort(key=lambda s: s.get("properties", {}).get("station_start_km", 0.0))
                    cls._CACHED_ROAD_SEGMENTS = dir1 if dir1 else features

                    # Precompute strictly monotonic (station_km, lon, lat) road centerline vertices
                    flat_pts: List[Tuple[float, float, float]] = []
                    for seg in cls._CACHED_ROAD_SEGMENTS:
                        s_start = float(seg.get("properties", {}).get("station_start_km", 0.0))
                        s_end = float(seg.get("properties", {}).get("station_end_km", 0.0))
                        coords = seg.get("geometry", {}).get("coordinates", [])
                        n_coords = len(coords)
                        for j, c in enumerate(coords):
                            frac = j / max(1, n_coords - 1)
                            st_km = s_start + frac * (s_end - s_start)
                            flat_pts.append((st_km, float(c[0]), float(c[1])))
                    cls._CACHED_FLAT_ROAD_PTS = flat_pts
                    return
                except Exception as exc:
                    logging.debug("Skipped road segments candidate %s: %s", p, exc)

        cls._CACHED_ROAD_SEGMENTS = []
        cls._CACHED_FLAT_ROAD_PTS = []

    def _haversine_distance(self, lon1_deg: float, lat1_deg: float, lon2_deg: float, lat2_deg: float) -> float:
        """Calculates metric distance between two `(x, y)` / `(lon, lat)` points in meters."""
        return self.coord_system.distance_m(lon1_deg, lat1_deg, lon2_deg, lat2_deg)

    def _calculate_bearing(self, lon1_deg: float, lat1_deg: float, lon2_deg: float, lat2_deg: float) -> float:
        """Calculates compass bearing from `(x1, y1)` to `(x2, y2)` in degrees [0, 360)."""
        return self.coord_system.bearing_deg(lon1_deg, lat1_deg, lon2_deg, lat2_deg)

    def _destination_point(self, lon1_deg: float, lat1_deg: float, bearing_deg: float, distance_m: float) -> Tuple[float, float]:
        """Calculates projected `(x, y)` / `(lon, lat)` given start, bearing, and distance in meters."""
        return self.coord_system.destination_point(lon1_deg, lat1_deg, bearing_deg, distance_m)

    def _find_nearest_station(self, pt_lon_lat: Tuple[float, float]) -> float:
        """Finds the kilometer station of the road centerline point closest to `pt_lon_lat`."""
        pts = AerialDrone._CACHED_FLAT_ROAD_PTS
        if not pts:
            return 40.0

        min_d = 1e9
        best_station = 40.0
        for st_km, c_lon, c_lat in pts:
            d = self._haversine_distance(pt_lon_lat[0], pt_lon_lat[1], c_lon, c_lat)
            if d < min_d:
                min_d = d
                best_station = st_km
        return best_station

    def _build_safe_side_corridor(
        self,
        home_coords: Tuple[float, float],
        target_coords: Tuple[float, float],
        target_station_km: float,
    ) -> List[List[float]]:
        """
        Build a safe, regulation-compliant flight corridor along the road verge (LuftVO § 21h).

        1. Follows the road geometry strictly between Home RSU and the Warning station.
        2. Strictly enforces forward progress towards target_station_km (never flying backward
           to an arbitrary segment boundary or closest vertex).
        3. Applies a continuous ~22m lateral offset onto the outer embankment on the RSU's side.
        4. Precludes flying over moving traffic or diagonally slicing across carriageway lanes.
        """
        home_station_km = self._find_nearest_station(home_coords)
        flat_pts = AerialDrone._CACHED_FLAT_ROAD_PTS or []

        if not flat_pts:
            b = self._calculate_bearing(home_coords[0], home_coords[1], target_coords[0], target_coords[1])
            off_target = self._destination_point(target_coords[0], target_coords[1], b + 90, 22.0)
            return [[home_coords[0], home_coords[1]], [off_target[0], off_target[1]]]

        # Select vertices strictly progressing between home_station_km and target_station_km
        if home_station_km <= target_station_km:
            corridor_pts = [p for p in flat_pts if home_station_km <= p[0] <= target_station_km]
            if not corridor_pts:
                corridor_pts = [p for p in flat_pts if (home_station_km - 0.05) <= p[0] <= (target_station_km + 0.05)]
        else:
            corridor_pts = [p for p in flat_pts if target_station_km <= p[0] <= home_station_km]
            if not corridor_pts:
                corridor_pts = [p for p in flat_pts if (target_station_km - 0.05) <= p[0] <= (home_station_km + 0.05)]
            corridor_pts.reverse()

        raw_pts: List[List[float]] = [[p[1], p[2]] for p in corridor_pts]

        if len(raw_pts) < 2:
            b = self._calculate_bearing(home_coords[0], home_coords[1], target_coords[0], target_coords[1])
            off_target = self._destination_point(target_coords[0], target_coords[1], b + 90, 22.0)
            return [[home_coords[0], home_coords[1]], [off_target[0], off_target[1]]]

        # Subsample to ~120m spacing for smooth, efficient waypoint guidance
        sampled: List[List[float]] = [raw_pts[0]]
        for p in raw_pts[1:]:
            if self._haversine_distance(sampled[-1][0], sampled[-1][1], p[0], p[1]) >= 120.0:
                sampled.append(p)
        if self._haversine_distance(sampled[-1][0], sampled[-1][1], raw_pts[-1][0], raw_pts[-1][1]) > 25.0:
            sampled.append(raw_pts[-1])

        # Determine which side (+90° or -90°) the RSU is located on relative to the road
        b0 = self._calculate_bearing(sampled[0][0], sampled[0][1], sampled[1][0], sampled[1][1])
        opt_r = self._destination_point(sampled[0][0], sampled[0][1], b0 + 90, 22.0)
        opt_l = self._destination_point(sampled[0][0], sampled[0][1], b0 - 90, 22.0)
        side_deg = 90.0 if self._haversine_distance(home_coords[0], home_coords[1], opt_r[0], opt_r[1]) < \
                           self._haversine_distance(home_coords[0], home_coords[1], opt_l[0], opt_l[1]) else -90.0

        offset_waypoints: List[List[float]] = []
        for i in range(len(sampled)):
            if i < len(sampled) - 1:
                b = self._calculate_bearing(sampled[i][0], sampled[i][1], sampled[i+1][0], sampled[i+1][1])
            else:
                b = self._calculate_bearing(sampled[i-1][0], sampled[i-1][1], sampled[i][0], sampled[i][1])
            pt_off = self._destination_point(sampled[i][0], sampled[i][1], b + side_deg, 22.0)
            offset_waypoints.append([pt_off[0], pt_off[1]])

        return [[home_coords[0], home_coords[1]]] + offset_waypoints

    def _move_towards(self, target_lon_lat: Tuple[float, float], speed_mps: Optional[float] = None) -> Tuple[Tuple[float, float], bool]:
        """Steps the drone toward `target_lon_lat` = (lon, lat)."""
        cur_lon, cur_lat = self.current_position
        tgt_lon, tgt_lat = target_lon_lat

        dist_m = self._haversine_distance(cur_lon, cur_lat, tgt_lon, tgt_lat)
        self.distance_to_target_m = dist_m

        if dist_m < 20.0:
            self.distance_to_target_m = 0.0
            return (tgt_lon, tgt_lat), True

        eff_speed = speed_mps if speed_mps is not None else self.cruise_speed_mps
        step_m = eff_speed * self.simulation_interval
        self.bearing_deg = self._calculate_bearing(cur_lon, cur_lat, tgt_lon, tgt_lat)

        if step_m >= dist_m:
            self.distance_to_target_m = 0.0
            return (tgt_lon, tgt_lat), True

        new_lon, new_lat = self._destination_point(cur_lon, cur_lat, self.bearing_deg, step_m)
        self.distance_to_target_m = max(0.0, dist_m - step_m)
        return (new_lon, new_lat), False

    def get_instant_velocity_kmh(self) -> float:
        """Return instantaneous airspeed in km/h with realistic 4-5s wind/trim fluctuation."""
        t = self.flight_time_sec
        omega = 2.0 * math.pi / 4.5  # 4.5 second primary fluctuation cycle

        if self.state in ("CruisingToward", "CruisingBack"):
            speed_noise = 3.8 * math.sin(omega * t + 0.6) + 1.2 * math.cos(2.2 * omega * t)
            return round(max(55.0, self.cruise_speed_kmh + speed_noise), 1)

        if self.state == "Inspecting":
            speed_noise = 1.4 * math.sin(omega * t)
            return round(max(9.0, 12.0 + speed_noise), 1)

        if self.state in ("Liftoff", "Landing", "DescendToInspect", "AscendToCruise"):
            return round(self.liftoff_speed * 3.6, 1)  # Vertical speed (18 km/h = 5 m/s)

        return 0.0

    def get_instant_altitude_m(self) -> float:
        """
        Return instantaneous altitude AGL in meters with 4-5s hover/gust fluctuation.

        - CruisingToward / CruisingBack: fluctuates around 50.0m (48.5 - 51.5m).
        - Inspecting: fluctuates around 18.0m (16.8 - 19.2m, within 15–20m requirement).
        """
        t = self.flight_time_sec
        omega = 2.0 * math.pi / 4.5

        if self.state in ("CruisingToward", "CruisingBack"):
            alt_noise = 1.2 * math.sin(omega * t) + 0.4 * math.cos(0.92 * omega * t)
            return round(max(47.5, min(52.5, 50.0 + alt_noise)), 1)

        if self.state == "Inspecting":
            alt_noise = 1.1 * math.sin(omega * t) + 0.3 * math.cos(0.92 * omega * t)
            return round(max(15.5, min(20.2, 18.0 + alt_noise)), 1)

        return round(self.altitude, 1)

    def get_mission_progress_pct(self) -> float:
        """Computes continuous 0–100% progress across the multi-stage UAV inspection mission."""
        if self.state == "Idle":
            return 0.0
        if self.state == "Liftoff":
            return round(min(15.0, (self.altitude / max(1.0, self.target_cruise_altitude)) * 15.0), 1)
        if self.state == "CruisingToward":
            total_wps = max(1, len(self.corridor_waypoints))
            frac = min(1.0, self.corridor_waypoint_idx / total_wps)
            return round(15.0 + 30.0 * frac, 1)
        if self.state == "DescendToInspect":
            frac = 1.0 - min(1.0, (self.altitude - self.target_inspect_altitude) / max(1.0, (self.target_cruise_altitude - self.target_inspect_altitude)))
            return round(45.0 + 5.0 * frac, 1)
        if self.state == "Inspecting":
            frac = min(1.0, self.time_spent_for_inspection / max(1.0, self.inspection_time))
            return round(50.0 + 25.0 * frac, 1)
        if self.state == "AscendToCruise":
            frac = min(1.0, (self.altitude - self.target_inspect_altitude) / max(1.0, (self.target_cruise_altitude - self.target_inspect_altitude)))
            return round(75.0 + 5.0 * frac, 1)
        if self.state == "CruisingBack":
            total_wps = max(1, len(self.return_waypoints))
            frac = min(1.0, self.return_waypoint_idx / total_wps)
            return round(80.0 + 15.0 * frac, 1)
        if self.state == "Landing":
            frac = 1.0 - min(1.0, self.altitude / max(1.0, self.target_cruise_altitude))
            return round(95.0 + 5.0 * frac, 1)
        return 50.0

    def _record_telemetry_point(self, ts_str: Optional[str] = None) -> None:
        """Appends a telemetry snapshot so `StatisticsCharts.vue` plots a full flight profile."""
        if not ts_str:
            ts_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.statistic.append({
            "Timestamp": ts_str,
            "Altitude": self.get_instant_altitude_m(),
            "Velocity": self.get_instant_velocity_kmh(),
            "BatteryPct": round(self.battery_pct, 1),
            "DistanceToTargetM": round(self.distance_to_target_m, 1),
            "MissionProgressPct": self.get_mission_progress_pct(),
        })
        if len(self.statistic) > 60:
            self.statistic = self.statistic[-60:]

    def action_loop(self) -> None:
        """Executes one tick of the autonomous UAV state machine."""
        if self.state == "Idle":
            self.battery_pct = min(100.0, self.battery_pct + 0.8)
            self.altitude = 0.0
            return

        self.flight_time_sec += self.simulation_interval

        # Record breadcrumb for flight trail visualization
        self.flight_trail.append([self.current_position[0], self.current_position[1]])
        if len(self.flight_trail) > 120:
            self.flight_trail = self.flight_trail[-120:]

        # ====================================================================
        # 1. LIFTOFF: Ascend vertically at home RSU from 0m up to 50m
        # ====================================================================
        if self.state == "Liftoff":
            self.battery_pct = max(5.0, self.battery_pct - 0.25 * self.cruise_drain_coef)
            self.altitude += self.simulation_interval * self.liftoff_speed
            if self.altitude >= self.target_cruise_altitude:
                self.altitude = self.target_cruise_altitude
                self.state = "CruisingToward" if self.corridor_waypoints else "Landing"
                self.corridor_waypoint_idx = 1 if len(self.corridor_waypoints) > 1 else 0

        # ====================================================================
        # 2. CRUISING TOWARD: Cruise at 50m along road verge at 65–70 km/h
        # ====================================================================
        elif self.state == "CruisingToward":
            if not self.corridor_waypoints:
                self.state = "Landing"
                return

            self.altitude = self.target_cruise_altitude
            self.battery_pct = max(5.0, self.battery_pct - 0.2 * self.cruise_drain_coef)
            current_target = self.corridor_waypoints[min(self.corridor_waypoint_idx, len(self.corridor_waypoints) - 1)]
            current_speed_mps = (self.get_instant_velocity_kmh() * 1000.0) / 3600.0

            new_pos, reached = self._move_towards((current_target[0], current_target[1]), current_speed_mps)
            self.current_position = new_pos

            if reached or self.distance_to_target_m < 25.0:
                self.corridor_waypoint_idx += 1
                if self.corridor_waypoint_idx >= len(self.corridor_waypoints):
                    # Arrived beside the warning on the verge -> descend to 18m
                    self.state = "DescendToInspect"

        # ====================================================================
        # 3. DESCEND TO INSPECT: Descend from 50m down to 18m on the verge
        # ====================================================================
        elif self.state == "DescendToInspect":
            self.battery_pct = max(5.0, self.battery_pct - 0.15 * self.cruise_drain_coef)
            self.altitude -= self.simulation_interval * self.liftoff_speed
            if self.altitude <= self.target_inspect_altitude:
                self.altitude = self.target_inspect_altitude
                self.state = "Inspecting"
                self.time_spent_for_inspection = 0.0

        # ====================================================================
        # 4. INSPECTING: Pavement distress LiDAR/camera scan at 18m (15-20m)
        # ====================================================================
        elif self.state == "Inspecting":
            self.altitude = self.target_inspect_altitude
            self.battery_pct = max(5.0, self.battery_pct - 0.25 * self.inspect_drain_coef)
            self.time_spent_for_inspection += self.simulation_interval

            # Slight side-scanning hover sway on verge
            t = self.flight_time_sec
            omega = 2.0 * math.pi / 4.5
            sway_m = 1.5 * math.sin(omega * t)
            if self.corridor_waypoints:
                base_pt = self.corridor_waypoints[-1]
                sway_pt = self._destination_point(base_pt[0], base_pt[1], self.bearing_deg, sway_m)
                self.current_position = sway_pt

            if self.current_inspection_obj is not None:
                self.current_inspection_obj.inspection_progress_pct = self.get_mission_progress_pct()
                self.current_inspection_obj.drone_flight_state = "Inspecting"

            if self.time_spent_for_inspection >= self.inspection_time:
                # Inspection complete -> ascend back up to 50m
                self.state = "AscendToCruise"
                if self.current_inspection_obj is not None:
                    self.current_inspection_obj.update_state("Inspected")
                    self.current_inspection_obj = None
                self.missions_completed += 1

        # ====================================================================
        # 5. ASCEND TO CRUISE: Ascend from 18m back up to 50m
        # ====================================================================
        elif self.state == "AscendToCruise":
            self.battery_pct = max(5.0, self.battery_pct - 0.2 * self.cruise_drain_coef)
            self.altitude += self.simulation_interval * self.liftoff_speed
            if self.altitude >= self.target_cruise_altitude:
                self.altitude = self.target_cruise_altitude
                self.state = "CruisingBack"
                self.return_waypoints = list(reversed(self.corridor_waypoints))
                self.return_waypoint_idx = 1 if len(self.return_waypoints) > 1 else 0

        # ====================================================================
        # 6. CRUISING BACK: Cruise at 50m along road verge back to home RSU
        # ====================================================================
        elif self.state == "CruisingBack":
            self.altitude = self.target_cruise_altitude
            self.battery_pct = max(5.0, self.battery_pct - 0.2 * self.cruise_drain_coef)
            current_target = self.return_waypoints[min(self.return_waypoint_idx, len(self.return_waypoints) - 1)]
            current_speed_mps = (self.get_instant_velocity_kmh() * 1000.0) / 3600.0

            new_pos, reached = self._move_towards((current_target[0], current_target[1]), current_speed_mps)
            self.current_position = new_pos

            if reached or self.distance_to_target_m < 25.0:
                self.return_waypoint_idx += 1
                if self.return_waypoint_idx >= len(self.return_waypoints):
                    self.state = "Landing"

        # ====================================================================
        # 7. LANDING: Descend vertically at home RSU pad from 50m down to 0m
        # ====================================================================
        elif self.state == "Landing":
            self.altitude -= self.simulation_interval * self.liftoff_speed
            if self.altitude <= 0.0:
                self.altitude = 0.0
                self.state = "Idle"
                self.inspection_target = None
                self.corridor_waypoints = []
                self.return_waypoints = []
                self.flight_trail = []

        self._record_telemetry_point()

    def establish_inspection_task(self, warning_obj: Any) -> None:
        """Dispatches the UAV from its RSU pad along the safe verge corridor to inspect `warning_obj`."""
        self.current_inspection_obj = warning_obj
        self.target_warning_id = str(getattr(warning_obj, "id", "warn_01"))
        self.target_warning_km = float(getattr(warning_obj, "position", 42.4))
        self.target_anomaly_type = str(getattr(warning_obj, "anomaly_type", "Corridor Scan"))

        w_coords = getattr(warning_obj, "coordinates", None)
        if w_coords and len(w_coords) >= 2:
            self.inspection_target = (float(w_coords[0]), float(w_coords[1]))
        else:
            self.inspection_target = self.initial_position

        self.corridor_waypoints = self._build_safe_side_corridor(
            self.initial_position,
            self.inspection_target,
            self.target_warning_km
        )
        self.corridor_waypoint_idx = 0
        self.return_waypoints = []
        self.return_waypoint_idx = 0

        self.inspection_time = 18.0 + (random.random() * 6.0)
        self.time_spent_for_inspection = 0.0
        self.flight_time_sec = 0.0
        self.flight_trail = [[self.initial_position[0], self.initial_position[1]]]

        self.distance_to_target_m = self._haversine_distance(
            self.current_position[0],
            self.current_position[1],
            self.inspection_target[0],
            self.inspection_target[1],
        )
        self.initial_target_distance_m = max(100.0, self.distance_to_target_m)
        self.bearing_deg = self._calculate_bearing(
            self.current_position[0],
            self.current_position[1],
            self.corridor_waypoints[1][0] if len(self.corridor_waypoints) > 1 else self.inspection_target[0],
            self.corridor_waypoints[1][1] if len(self.corridor_waypoints) > 1 else self.inspection_target[1],
        )

        warning_obj.assigned_drone_id = self.id
        warning_obj.drone_flight_state = "Liftoff"
        self.state = "Liftoff"
        self.altitude = 0.0

        # Seed initial pre-flight & liftoff ramp
        now_dt = datetime.datetime.now()
        self.statistic = []
        for i in range(6):
            ts = (now_dt - datetime.timedelta(seconds=(5 - i) * 2)).strftime("%H:%M:%S")
            frac = i / 5.0
            self.statistic.append({
                "Timestamp": ts,
                "Altitude": round(frac * 50.0, 1),
                "Velocity": round(frac * (self.liftoff_speed * 3.6), 1),
                "BatteryPct": round(self.battery_pct, 1),
                "DistanceToTargetM": round(self.distance_to_target_m, 1),
                "MissionProgressPct": round(frac * 15.0, 1),
            })

    def to_dict(self) -> Dict[str, Any]:
        """Serializes full UAV telemetry for GeoJSON and the Inspector Panel."""
        mission_pct = self.get_mission_progress_pct()
        vel_kmh = self.get_instant_velocity_kmh()
        alt_m = self.get_instant_altitude_m()

        next_wp = None
        if self.state in ("Liftoff", "CruisingToward") and self.corridor_waypoints:
            wp_idx = self.corridor_waypoint_idx if self.state == "CruisingToward" else 1
            tgt = self.corridor_waypoints[min(wp_idx, len(self.corridor_waypoints) - 1)]
            next_wp = [round(float(tgt[0]), 6), round(float(tgt[1]), 6)]
        elif self.state == "CruisingBack" and self.return_waypoints:
            tgt = self.return_waypoints[min(self.return_waypoint_idx, len(self.return_waypoints) - 1)]
            next_wp = [round(float(tgt[0]), 6), round(float(tgt[1]), 6)]
        elif self.state in ("DescendToInspect", "Inspecting", "AscendToCruise") and self.corridor_waypoints:
            tgt = self.corridor_waypoints[-1]
            next_wp = [round(float(tgt[0]), 6), round(float(tgt[1]), 6)]

        return {
            "id": self.id,
            "State": self.state,
            "HomeRSU": self.home_rsu_id,
            "HomeRSUName": self.home_rsu_name,
            "HomeCoords": [self.initial_position[0], self.initial_position[1]],
            "TargetCoords": list(self.inspection_target) if self.inspection_target else None,
            "NextWaypoint": next_wp,
            "TargetWarningID": getattr(self.current_inspection_obj, "id", None) or self.target_warning_id,
            "TargetStationKm": round(float(getattr(self.current_inspection_obj, "position", self.target_warning_km)), 2),
            "TargetWarningKm": round(float(getattr(self.current_inspection_obj, "position", self.target_warning_km)), 2),
            "TargetAnomalyType": getattr(self.current_inspection_obj, "anomaly_type", None) or self.target_anomaly_type,
            "Altitude": alt_m,
            "TargetAltitude": 50.0 if self.state in ("Liftoff", "CruisingToward", "CruisingBack", "Landing", "AscendToCruise") else 18.0,
            "Velocity": vel_kmh,
            "CruiseSpeedKmh": self.cruise_speed_kmh,
            "BatteryPct": round(self.battery_pct, 1),
            "BearingDeg": round(self.bearing_deg, 1),
            "DistanceToTargetM": round(self.distance_to_target_m, 1),
            "InspectionProgressPct": mission_pct,
            "MissionProgressPct": mission_pct,
            "InspectionDurationSec": round(self.inspection_time, 1),
            "TimeSpentInspectingSec": round(self.time_spent_for_inspection, 1),
            "MissionsCompleted": self.missions_completed,
            "FlightTrail": self.flight_trail,
        }
