"""
vehicle/vehicle.py — Heavy Goods Vehicle (HGV) Federate & Dynamic Code Synthesis
================================================================================

Project: Digital Twin Road Demonstrator — Open Source Road Infrastructure Platform (MIT)

Architectural Role
------------------
Each `Vehicle` instance acts as a **Fast-Scale Mechanical & Kinematic Federate** that:
1. Travels between two real Autobahn junctions (`StartJunction` -> `EndJunction`) along
   the Dresden–Leipzig A4/A14 corridor.
2. Maintains an isolated pure-Python **FODA Feature Model** (`self.feature_model`)
   and a **Heraklit Hybrid Petri Net Controller** (`self.hpn`).
3. Dynamically synthesizes its thermal-mechanical simulation class via Python Mixins
   (`fm.compose_simulation_class`) using Heraklit HPN algebra.
4. Negotiates and updates a live **HLA/FOM Dynamic Contract** with the serving Roadside
   Unit (`world.federation_manager`), exchanging environmental boundary conditions and
   fast-scale telemetry/damage increments.
5. Records its historical GPS breadcrumb trail (`self.trajectory`) for Flightradar24-style
   colored past trajectory visualization on the GIS map.
"""

from __future__ import annotations
import logging
import math
import random
import time
from typing import Dict, Any, List
from vehicle.warning import Warning
import fm
from hpn import HeraklitHPNController

HGV_CLASSES = [
    ("5-Axle Semi-Trailer (40t)", "EU Class N3 • 2+3 Axle", 5),
    ("4-Axle Heavy Dumper (36t)", "EU Class N3 • 2+2 Axle", 4),
    ("6-Axle Low-Loader HGV (44t)", "EU Class N3 • 3+3 Axle", 6),
]


class Vehicle:
    """
    Simulated Heavy Goods Vehicle with FODA variability and Heraklit HPN runtime.

    Maintains coupled kinematic state, thermal-mechanical feature composition, and
    dynamic HLA/FOM RSU federation contract synchronization.
    """

    _counter: int = 100

    def __init__(self, params: Dict[str, Any], world: Any) -> None:
        Vehicle._counter += 1
        self.id: int = Vehicle._counter
        self.feature_model: Dict[str, Any] = fm.clone_feature_model()
        self.hpn: HeraklitHPNController = HeraklitHPNController()

        veh_class_name, axle_cfg, num_axles = random.choice(HGV_CLASSES)
        weight_kg = random.randint(30000, 42000)

        # Distinct cruise speed profile calibrated by vehicle class, mass, and driver preference
        base_cruise = {
            5: 87.5,  # 5-Axle Semi-Trailer (40t)
            4: 84.5,  # 4-Axle Heavy Dumper (36t)
            6: 81.5,  # 6-Axle Low-Loader HGV (44t)
        }.get(num_axles, 86.0)
        driver_pref = ((hash(self.id) % 11) - 5) * 0.7  # -3.5 to +3.5 km/h
        self.cruise_speed: float = round(base_cruise + driver_pref, 1)

        # On-demand manual spawn from intersection starts at 30 km/h and accelerates
        self.is_manual_spawn: bool = bool(params.get("SpawnJunctionID") or params.get("InitialSpeed"))
        initial_speed: float = float(params.get("InitialSpeed", 30.0 if self.is_manual_spawn else self.cruise_speed))
        self.prev_velocity: float = initial_speed
        self.urban_stop_countdown: int = 0
        self.time_until_next_stop: int = random.randint(4, 9)

        self.params: Dict[str, Any] = {
            "Active": True,
            "ID": self.id,
            "Callsign": f"HGV-{self.id}",
            "VehicleClass": veh_class_name,
            "AxleConfig": axle_cfg,
            "Axles": num_axles,
            "Weight": weight_kg,
            "CruiseSpeed": self.cruise_speed,
            "Velocity": initial_speed,
            "ExtrapolatedVelocity": initial_speed,
            "Length": 16.5,
            "Width": 2.55,
            "Damage": 0.05,
        }
        self.mechanical_simulation: Dict[str, Any] = {
            "Model": "POD",
            "Accuracy": round(0.95 + random.random() * 0.04, 4),
            "Threshold": 0.90,
        }
        self.warning_probability: float = 0.002

        self.params["MechanicalSimulation"] = self.mechanical_simulation
        for k, v in params.items():
            self.params[k] = v

        self.world = world
        self.trajectory: List[Dict[str, Any]] = []
        self.federation_contract: Dict[str, Any] = {}
        self._active_features: List[str] = []
        self._sim_cls: Any = None

        self.generate_route(self.world.road_spawn_metadata)
        self.position: float = float(self.params["StartRoute"])
        self.prev_position: float = self.position
        self.direction: int = 1 if self.params["EndRoute"] > self.params["StartRoute"] else -1

        self.params.update({
            "LastPosition": round(self.position, 3),
            "Kilometer": round(self.position, 3),
            "Direction": self.direction,
            "RouteProgressPct": 0.0,
            "RemainingKm": round(abs(self.params["EndRoute"] - self.params["StartRoute"]), 2),
        })
        self.current_lane: int = 1 if self.direction == 1 else -1
        self.lane_pos_central: float = 0.5
        self.statistic: List[Dict[str, Any]] = []
        self.is_initialized: bool = False
        self.update_states()
        self.is_initialized = True

    def generate_route(self, spawn_points: Dict[str, Any]) -> None:
        """Selects origin and destination junctions and records their names/codes."""
        features = spawn_points.get("features", [])
        if not features:
            self.params.update({"StartRoute": 0.0, "EndRoute": 100.0})
            return

        # Check if spawned on demand at a specific user-selected junction
        requested_jct_id = self.params.get("SpawnJunctionID")
        start_feat = None
        if requested_jct_id:
            for feat in features:
                if str(feat.get("properties", {}).get("id")) == str(requested_jct_id):
                    start_feat = feat
                    break

        if start_feat is None:
            start_feat = features[0]
            point_start = random.random()
            counter_start = 0.0
            for point in features:
                counter_start += point["properties"].get("TargetFrom", 1.0 / len(features))
                if counter_start >= point_start:
                    start_feat = point
                    break

        start_km = float(start_feat["properties"].get("ClosestPoint", 0.0))

        # Select a destination junction ensuring significant corridor travel (and requested direction if set)
        requested_dir = self.params.get("RequestedDirection")
        end_feat = features[-1]
        attempts = 0
        while attempts < 30:
            attempts += 1
            point_end = random.random()
            counter_end = 0.0
            for point in features:
                counter_end += point["properties"].get("TargetTo", 1.0 / len(features))
                if counter_end >= point_end:
                    end_feat = point
                    break
            end_km = float(end_feat["properties"].get("ClosestPoint", 100.0))
            if requested_dir == 1:
                if (end_km - start_km) > 12.0:
                    break
            elif requested_dir == -1:
                if (start_km - end_km) > 12.0:
                    break
            elif abs(end_km - start_km) > 12.0:
                break

        # Fallback if sampled destination violated direction or span constraint
        end_km_cur = float(end_feat["properties"].get("ClosestPoint", 100.0))
        invalid_dir = (
            (requested_dir == 1 and end_km_cur <= start_km)
            or (requested_dir == -1 and end_km_cur >= start_km)
        )
        if invalid_dir or abs(end_km_cur - start_km) <= 5.0:
            if requested_dir == 1:
                candidates = [f for f in features if float(f["properties"].get("ClosestPoint", 0.0)) > start_km]
            elif requested_dir == -1:
                candidates = [f for f in features if float(f["properties"].get("ClosestPoint", 0.0)) < start_km]
            else:
                candidates = []
            pool = candidates if candidates else features
            end_feat = max(pool, key=lambda f: abs(float(f["properties"].get("ClosestPoint", 0.0)) - start_km))

        s_props = start_feat["properties"]
        e_props = end_feat["properties"]

        # Update junction traffic counters
        s_props["vehicles_spawned"] = int(s_props.get("vehicles_spawned", 0)) + 1
        e_props["vehicles_destined"] = int(e_props.get("vehicles_destined", 0)) + 1

        self.params.update({
            "StartRoute": round(float(s_props.get("ClosestPoint", 0.0)), 2),
            "EndRoute": round(float(e_props.get("ClosestPoint", 100.0)), 2),
            "StartJunctionID": s_props.get("id", "jct_origin"),
            "StartJunctionCode": s_props.get("code", "AS"),
            "StartJunctionShort": s_props.get("short_code", "ORIG"),
            "StartJunctionName": s_props.get("name", "Origin Junction"),
            "EndJunctionID": e_props.get("id", "jct_dest"),
            "EndJunctionCode": e_props.get("code", "AS"),
            "EndJunctionShort": e_props.get("short_code", "DEST"),
            "EndJunctionName": e_props.get("name", "Destination Junction"),
        })

    def update_position(self) -> None:
        """Advances vehicle position along the corridor and updates progress metrics."""
        t0 = time.perf_counter()
        if self.params["Active"] is True:
            self.prev_position = self.position
            step_km = self.direction * (self.params["Velocity"] / 3600.0 * self.params.get("UpdatePeriod", 1.0)) * 5.0
            self.position = self.position + step_km
            self.update_states()

        if self.direction * self.position >= self.direction * self.params["EndRoute"]:
            self.position = float(self.params["EndRoute"])
            self.params["Active"] = False

        total_span = max(0.1, abs(self.params["EndRoute"] - self.params["StartRoute"]))
        travelled = abs(self.position - self.params["StartRoute"])
        progress_pct = max(0.0, min(100.0, (travelled / total_span) * 100.0))
        remaining_km = max(0.0, abs(self.params["EndRoute"] - self.position))

        self._last_pos_compute_ms = (time.perf_counter() - t0) * 1000.0
        self.params.update({
            "LastPosition": round(self.position, 3),
            "Kilometer": round(self.position, 3),
            "IntervalBegin": self.prev_position if self.direction == 1 else self.position,
            "IntervalEnd": self.position if self.direction == 1 else self.prev_position,
            "RouteProgressPct": round(progress_pct, 1),
            "RemainingKm": round(remaining_km, 2),
        })

    def update_states(self) -> None:
        """Couple environmental boundary states with FODA, Heraklit HPN, and HLA contracts."""
        self.produce_warning()
        states = self.world.get_states_for_position(self.position, self.direction)
        lanes_count = int(states["RoadMetadata"].get("Lanes", 2))
        self.current_lane = max(1, round(random.random() * lanes_count))
        if self.direction == -1:
            self.current_lane = -self.current_lane
        self.lane_pos_central = 0.5

        states.update({
            "Direction": self.direction,
            "Lane": self.current_lane,
            "LanePosition": self.lane_pos_central,
        })

        # 1. Road gradient / topography influence (Elbe valley ascent km 4 to 24)
        pos = float(self.position)
        grade_effect = 0.0
        if 4.0 <= pos <= 24.0:
            weight_factor = float(self.params.get("Weight", 38000)) / 40000.0
            grade_effect = - weight_factor * 6.0 * math.sin(((pos - 4.0) / 20.0) * math.pi)

        # 2. Highway interchange merge / junction influence (km 0, 44, 98)
        jct_dist = min(abs(pos - 0.0), abs(pos - 44.0), abs(pos - 98.0))
        jct_effect = -4.0 * math.exp(-(jct_dist**2) / 3.0) if jct_dist < 3.0 else 0.0

        # 3. Individual driver micro-dynamics (independent phase per vehicle ID)
        t_now = time.time()
        driver_wave = 1.6 * math.sin((t_now + self.id * 23.7) / 14.0)

        # 4. Weather boundary condition
        weather = str(states.get("WeatherState", "Sunny"))
        weather_effect = -4.0 if weather in ("Rainy", "Thunderstorm") else 0.0

        # 5. Speed dynamics: Urban cruising (30-50 km/h) in Dresden/Leipzig vs Autobahn cruising (80-95 km/h)
        is_urban_dresden = (pos < 4.2)
        is_urban_leipzig = (pos > 108.4)
        is_urban = is_urban_dresden or is_urban_leipzig

        cur_vel = float(self.params.get("Velocity", 30.0 if self.is_manual_spawn else self.cruise_speed))
        self.prev_velocity = cur_vel

        if not getattr(self, "is_initialized", True):
            new_vel = round(cur_vel, 1)
            traffic_state = "Spawned (Accelerating from 30 km/h)" if self.is_manual_spawn else "Cruise Baseline"
        elif is_urban:
            # Dresden (km 0.0-4.2) and Leipzig (km 108.4-122.0) Urban Zone: cruise 30-50 km/h with optional stops
            urban_target = 40.0 + ((hash(self.id * 17) % 11) - 5) * 1.0 + driver_wave
            urban_target = max(32.0, min(48.0, urban_target))

            if self.urban_stop_countdown > 0:
                # Actively stopped at traffic light or traffic jam
                self.urban_stop_countdown -= 1
                new_vel = 0.0
                traffic_state = "Stopped (Traffic Light / Congestion)"
            else:
                self.time_until_next_stop -= 1
                at_traffic_light = (is_urban_dresden and any(abs(pos - tl) < 0.20 for tl in (1.2, 2.6))) or \
                                   (is_urban_leipzig and any(abs(pos - tl) < 0.20 for tl in (112.4, 117.6)))

                if (self.time_until_next_stop <= 0 or at_traffic_light) and random.random() < 0.60:
                    # Initiate a stop for 1-2 update cycles (5-10 seconds idle)
                    self.urban_stop_countdown = random.choice([1, 2])
                    self.time_until_next_stop = random.randint(5, 10)
                    new_vel = 0.0
                    traffic_state = "Traffic Light Red (Stopping)"
                else:
                    # Cruising 30-50 km/h: accelerate if starting from stop/spawn, or decelerate if coming from motorway
                    if cur_vel < 25.0:
                        new_vel = round(min(urban_target, cur_vel + 12.0), 1)
                        traffic_state = f"Urban Accelerating ({new_vel:.0f} km/h)"
                    elif cur_vel > 52.0:
                        new_vel = round(max(urban_target, cur_vel - 16.0), 1)
                        traffic_state = f"Urban Decelerating ({new_vel:.0f} km/h)"
                    else:
                        new_vel = round(max(30.0, min(50.0, urban_target)), 1)
                        traffic_state = f"Urban Cruising ({new_vel:.0f} km/h)"
        else:
            # Autobahn corridor (km 4.2 to 108.4): cruise 80-95 km/h
            base_spd = getattr(self, "cruise_speed", 88.0)
            hwy_target = max(72.0, min(98.0, base_spd + grade_effect + jct_effect + driver_wave + weather_effect))
            if cur_vel < 70.0:
                # Accelerate from urban/spawn speed up to highway cruising speed
                new_vel = round(min(hwy_target, cur_vel + 12.0), 1)
                traffic_state = f"Autobahn Accelerating ({new_vel:.0f} km/h)"
            else:
                new_vel = round(hwy_target, 1)
                traffic_state = f"Autobahn Cruising ({new_vel:.0f} km/h)"

        self.params.update({
            "State": states,
            "Velocity": new_vel,
            "ExtrapolatedVelocity": new_vel,
            "TrafficState": traffic_state,
        })

        weather = str(states.get("WeatherState", "Sunny"))
        road_material = list(states["RoadMetadata"]["RoadType"].keys())[0]

        # 1. Update FODA environmental & material features
        self.toggle_feature(weather)
        self.toggle_feature(road_material)
        self.toggle_feature("Westergaard" if str(road_material).strip().lower() == "concrete" else "Boussinesq")
        active_features = self.get_active_features()

        # 2. Compose Python Mixin Simulation Class
        sim_cls = self.compose_simulation_class(active_features)
        sim_instance = sim_cls() if sim_cls is not None else None

        # 3. Step Compositional Heraklit Hybrid Petri Net (Fast-Slow ODE + Guarded Transitions)
        foda_solver_feat, updated_acc, just_switched = self.hpn.step(
            rsu_id=str(states.get("RoadsideUnit") or "rsu_00"),
            weather_state=weather,
            road_material=road_material,
            air_temp=float(states.get("AirTemperature", 22.0)),
            road_temp=float(states.get("RoadSurfaceTemperature", 26.0)),
            soil_temp=float(states.get("SoilTemperature", 14.5)),
            velocity_kmh=new_vel,
            weight_kg=float(self.params["Weight"]),
            mechanical_simulation=self.mechanical_simulation,
            composed_mixin_instance=sim_instance,
            damage_increment=float(self.params.get("Damage", 0.05)),
        )
        self.toggle_feature(foda_solver_feat)
        active_features = self.get_active_features()
        self._active_features = active_features
        self._sim_cls = self.compose_simulation_class(active_features)

        # 4. Synchronize Dynamic HLA/FOM Federation Contract with serving RSU
        if hasattr(self.world, "federation_manager"):
            self.federation_contract = self.world.federation_manager.sync_vehicle_contract(
                self.id, self.params, just_switched_solver=just_switched
            )

        # 5. Append GPS breadcrumb for Flightradar24-style past trajectory trail
        raw_coords = str(states.get("Coordinates", "13.5, 51.1")).split(",")
        try:
            lon = float(raw_coords[0].strip())
            lat = float(raw_coords[-1].strip())
            self.trajectory.append({
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "km": round(self.position, 3),
                "vel": round(new_vel, 1),
                "temp": round(float(states.get("RoadSurfaceTemperature", 25.0)), 1),
                "solver": foda_solver_feat,
            })
            if len(self.trajectory) > 120:
                self.trajectory = self.trajectory[-120:]
        except Exception as exc:
            logging.debug("Failed to parse vehicle coordinates '%s': %s", raw_coords, exc)

        comp_mod = self.hpn.composed_module
        self.params["HPN"] = {
            "formula": comp_mod.name if comp_mod is not None else "",
            "solver": foda_solver_feat,
            "accuracy": updated_acc,
            "last_transition": self.hpn.last_fired_transition,
        }
        self.params["FederationContract"] = self.federation_contract
        self.params["Trajectory"] = self.trajectory

    @property
    def hpn_state(self) -> Dict[str, Any]:
        """Lazily serializes the composed Heraklit HPN into Vue Flow nodes/edges on inspection."""
        return self.hpn.to_dict()

    @property
    def heraklit_code(self) -> str:
        """Lazily generates the Heraklit HPN code snippet on inspection."""
        af = self._active_features or self.get_active_features()
        return self.hpn.generate_heraklit_code_snippet(af)

    @property
    def code(self) -> str:
        """Lazily synthesizes the Python Mixin + Heraklit HPN source code on inspection."""
        af = self._active_features or self.get_active_features()
        cls = self._sim_cls or self.compose_simulation_class(af)
        return fm.get_code(cls, self.heraklit_code)

    def indent_code(self, code: str, spaces: int = 4) -> str:
        """Indent synthesized Mixin source code lines by `spaces`."""
        return fm.indent_code(code, spaces)

    def toggle_feature(self, clicked_feature_id: str) -> Dict[str, Any]:
        """Toggle a FODA feature selection in this vehicle's isolated feature model."""
        self.feature_model = fm.toggle_feature(self.feature_model, clicked_feature_id)
        return self.feature_model

    def get_active_features(self) -> List[str]:
        """Return currently active FODA feature names for this vehicle."""
        return fm.get_active_features(self.feature_model)

    def compose_simulation_class(self, active_features: List[str]) -> Any:
        """Compose a `ThermalModel` subclass from the given active FODA feature list."""
        return fm.compose_simulation_class(active_features)

    def produce_warning(self) -> None:
        """Stochastically emit a structural road anomaly warning at the vehicle's position."""
        if random.random() < self.warning_probability:
            surf_temp = 26.0
            if "State" in self.params and isinstance(self.params["State"], dict):
                surf_temp = float(self.params["State"].get("RoadSurfaceTemperature", 26.0))
            self.world.register_warning(
                Warning(
                    position=self.position,
                    direction=self.direction,
                    vehicle_id=self.id,
                    vehicle_weight=self.params.get("Weight", 35000),
                    surface_temp=surf_temp,
                )
            )

    def compute_kinematic_axles(self) -> Dict[str, Any]:
        """
        Compute dynamic axle load distribution, pitch transfer, and impact factors.

        Evaluated on-demand during active vehicle selection to eliminate overhead
        on the rest of the fleet during continuous 5s updates.
        """
        weight_kg = float(self.params.get("Weight", 40000))
        total_kn = (weight_kg * 9.81) / 1000.0

        v = float(self.params.get("Velocity", 80.0))
        v_old = getattr(self, "prev_velocity", v)
        dt = 5.0
        accel = (v - v_old) / (3.6 * dt)

        # Local road longitudinal slope in percent (Elbe valley ascent km 4 to 24)
        pos = float(self.position)
        slope_pct = 3.5 * math.sin(((pos - 4.0) / 20.0) * math.pi) if 4.0 <= pos <= 24.0 else 0.0

        # Pitch dynamic weight transfer: a_long = a + g * sin(theta)
        a_long = accel + 9.81 * (slope_pct / 100.0)
        pitch_kn = (total_kn * a_long / 9.81) * (1.8 / 6.5) * 0.45

        # Speed-dependent dynamic load coefficient (DLC, ISO 8608 roughness)
        dlc = 0.05 * ((v / 80.0) ** 1.3)

        veh_class = str(self.params.get("VehicleClass", "5-Axle"))
        if "4-Axle" in veh_class:
            base_axles = [
                {"id": 1, "name": "Axle 1 (Front Steer)", "group": "Front Steer", "type": "single", "tire": "385/65R22.5", "pct": 0.208, "is_drive": False, "is_steer": True, "pressure": 750.0},
                {"id": 2, "name": "Axle 2 (2nd Steer)", "group": "Front Steer", "type": "single", "tire": "385/65R22.5", "pct": 0.208, "is_drive": False, "is_steer": True, "pressure": 750.0},
                {"id": 3, "name": "Axle 3 (Drive Tandem 1)", "group": "Rear Drive Tandem", "type": "dual", "tire": "315/80R22.5", "pct": 0.292, "is_drive": True, "is_steer": False, "pressure": 800.0},
                {"id": 4, "name": "Axle 4 (Drive Tandem 2)", "group": "Rear Drive Tandem", "type": "dual", "tire": "315/80R22.5", "pct": 0.292, "is_drive": True, "is_steer": False, "pressure": 800.0},
            ]
        elif "6-Axle" in veh_class:
            base_axles = [
                {"id": 1, "name": "Axle 1 (Front Steer)", "group": "Tractor Steer", "type": "single", "tire": "385/65R22.5", "pct": 0.160, "is_drive": False, "is_steer": True, "pressure": 750.0},
                {"id": 2, "name": "Axle 2 (Pusher Axle)", "group": "Tractor Pusher", "type": "single", "tire": "385/65R22.5", "pct": 0.160, "is_drive": False, "is_steer": False, "pressure": 750.0},
                {"id": 3, "name": "Axle 3 (Drive Axle)", "group": "Tractor Drive", "type": "dual", "tire": "315/80R22.5", "pct": 0.260, "is_drive": True, "is_steer": False, "pressure": 800.0},
                {"id": 4, "name": "Axle 4 (Trailer Tridem 1)", "group": "Trailer Tridem", "type": "dual", "tire": "245/70R17.5", "pct": 0.140, "is_drive": False, "is_steer": False, "pressure": 750.0},
                {"id": 5, "name": "Axle 5 (Trailer Tridem 2)", "group": "Trailer Tridem", "type": "dual", "tire": "245/70R17.5", "pct": 0.140, "is_drive": False, "is_steer": False, "pressure": 750.0},
                {"id": 6, "name": "Axle 6 (Trailer Tridem 3)", "group": "Trailer Tridem", "type": "dual", "tire": "245/70R17.5", "pct": 0.140, "is_drive": False, "is_steer": False, "pressure": 750.0},
            ]
        else:
            # 5-Axle Semi-Trailer (EU Class N3 standard 40t)
            base_axles = [
                {"id": 1, "name": "Axle 1 (Front Steer)", "group": "Tractor Steer", "type": "single", "tire": "385/65R22.5", "pct": 0.175, "is_drive": False, "is_steer": True, "pressure": 750.0},
                {"id": 2, "name": "Axle 2 (Drive Axle)", "group": "Tractor Drive", "type": "dual", "tire": "315/80R22.5", "pct": 0.2875, "is_drive": True, "is_steer": False, "pressure": 800.0},
                {"id": 3, "name": "Axle 3 (Trailer Tridem 1)", "group": "Semitrailer", "type": "single", "tire": "385/65R22.5", "pct": 0.179, "is_drive": False, "is_steer": False, "pressure": 750.0},
                {"id": 4, "name": "Axle 4 (Trailer Tridem 2)", "group": "Semitrailer", "type": "single", "tire": "385/65R22.5", "pct": 0.179, "is_drive": False, "is_steer": False, "pressure": 750.0},
                {"id": 5, "name": "Axle 5 (Trailer Tridem 3)", "group": "Semitrailer", "type": "single", "tire": "385/65R22.5", "pct": 0.179, "is_drive": False, "is_steer": False, "pressure": 750.0},
            ]

        axle_results = []
        for a in base_axles:
            p_stat = total_kn * a["pct"]
            if a.get("is_steer"):
                delta_p = -pitch_kn * 0.5
            elif a.get("is_drive"):
                delta_p = pitch_kn * 0.6
            else:
                delta_p = pitch_kn * (0.4 / max(1, len(base_axles) - 2))

            p_dyn = max(30.0, (p_stat + delta_p) * (1.0 + dlc))
            dif = p_dyn / max(1.0, p_stat)

            tires_count = 4 if a["type"] == "dual" else 2
            p_tire_n = (p_dyn * 1000.0) / tires_count
            radius_m = math.sqrt(p_tire_n / (math.pi * (a["pressure"] * 1000.0)))
            damage_factor = (p_dyn / 100.0) ** 4.0

            axle_results.append({
                "id": a["id"],
                "name": a["name"],
                "group": a["group"],
                "type": a["type"],
                "tire": a["tire"],
                "is_drive": a["is_drive"],
                "is_steer": a["is_steer"],
                "p_stat_kn": round(p_stat, 1),
                "p_dyn_kn": round(p_dyn, 1),
                "wheel_load_kn": round(p_dyn / 2.0, 1),
                "tire_load_kn": round(p_tire_n / 1000.0, 1),
                "dif": round(dif, 3),
                "pressure_kpa": a["pressure"],
                "contact_radius_cm": round(radius_m * 100.0, 1),
                "damage_factor": round(damage_factor, 2),
            })

        summary = {
            "velocity_kmh": round(v, 1),
            "accel_mps2": round(accel, 2),
            "slope_pct": round(slope_pct, 2),
            "dlc": round(dlc, 3),
            "total_static_kn": round(total_kn, 1),
            "total_dynamic_kn": round(sum(ax["p_dyn_kn"] for ax in axle_results), 1),
        }
        return {"axles": axle_results, "summary": summary}
