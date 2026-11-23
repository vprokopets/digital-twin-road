"""
world/traffic_management.py — Corridor Fleet & Traffic Lifecycle Manager
========================================================================

Project: Digital Twin Road Demonstrator
"""

import random
import time
from typing import Dict, Any, List, Optional

from vehicle.vehicle import Vehicle
from data_curation import get_broker_status, register_device, send_telemetry


class TrafficManagement:
    """
    Manages HGV spawning, position stepping, broker sync, and retirement.

    Coordinates active Heavy Goods Vehicles along the highway corridor.
    """

    def __init__(self, params: Dict[str, Any], world: Any, fiware_flag: bool) -> None:
        self.parameters = params
        self.world = world
        self.fiware_flag = fiware_flag
        self._broker_publish: bool = bool(
            fiware_flag or get_broker_status().get("backend") == "native"
        )
        self.vehicles: Dict[Any, Vehicle] = {}
        self.vehicles_to_rm: List[Any] = []
        self.active_vehicles: Dict[Any, Vehicle] = {}
        self.buffer: List[Any] = []
        self.time = time.time()

    def update_vehicles_state(self) -> None:
        """Advance all active vehicles, publish broker telemetry, and retire exited vehicles."""
        for vehicle_obj in list(self.active_vehicles.values()):
            vehicle_obj.update_position()

            if self._broker_publish:
                vehicle_sensor_data = {
                    "Active": vehicle_obj.params["Active"],
                    "Velocity": vehicle_obj.params["Velocity"],
                    "Model": vehicle_obj.mechanical_simulation["Model"],
                    "Accuracy": vehicle_obj.mechanical_simulation["Accuracy"],
                    "coordinates": [
                        float(vehicle_obj.params["State"]["Coordinates"].split(",")[0]),
                        float(vehicle_obj.params["State"]["Coordinates"].split(",")[-1]),
                    ],
                    "AirTemperature": vehicle_obj.params["State"]["AirTemperature"],
                    "RoadSurfaceTemperature": vehicle_obj.params["State"]["RoadSurfaceTemperature"],
                    "SoilTemperature": vehicle_obj.params["State"]["SoilTemperature"],
                }
                send_telemetry(
                    device_id=vehicle_obj.params["ID"],
                    entity_type="Vehicle",
                    sensor_dict=vehicle_sensor_data,
                    api_key="vehicle",
                )

            if vehicle_obj.params["Active"] is False:
                self.vehicles_to_rm.append(vehicle_obj.id)

        self.remove_inactive_vehicles()

    def register_vehicle(self, vehicle_id: Any, vehicle_obj: Vehicle) -> None:
        """Register an active `Vehicle` instance by ID."""
        self.active_vehicles[vehicle_id] = vehicle_obj

    def remove_inactive_vehicles(self) -> None:
        """Remove retired vehicles and close their federation contracts."""
        for vehicle_id in self.vehicles_to_rm:
            self.active_vehicles.pop(vehicle_id, None)
            if hasattr(self.world, "federation_manager"):
                self.world.federation_manager.remove_vehicle_contract(vehicle_id)
        self.vehicles_to_rm = []

    def mark_vehicle_to_rm(self, vehicle_id: Any) -> None:
        """Queue `vehicle_id` for removal at the end of the update cycle."""
        self.vehicles_to_rm.append(vehicle_id)

    def store_vehicle(self, vehicle_id: Any, vehicle_metadata: Vehicle) -> None:
        """Archive vehicle metadata and evict the oldest inactive entry above capacity."""
        self.vehicles[vehicle_id] = vehicle_metadata
        if len(self.vehicles) > 50:
            # Evict oldest inactive vehicle to prevent unbounded memory growth
            for vid in list(self.vehicles.keys()):
                if vid not in self.active_vehicles:
                    self.vehicles.pop(vid, None)
                    break

    def force_spawn_vehicle(
        self,
        junction_id: Optional[str] = None,
        direction: Optional[int] = None,
    ) -> Optional[Vehicle]:
        """Immediately spawns a new Heavy Goods Vehicle (used at startup and via UI demo controls)."""
        if len(self.active_vehicles) >= self.parameters.get("VehicleLimit", 50):
            return None

        veh_params = dict(self.parameters)
        if junction_id:
            veh_params["SpawnJunctionID"] = str(junction_id)
            veh_params["InitialSpeed"] = 30.0
        if direction in (1, -1):
            veh_params["RequestedDirection"] = int(direction)

        new_vehicle = Vehicle(veh_params, self.world)
        self.register_vehicle(new_vehicle.id, new_vehicle)
        self.store_vehicle(new_vehicle.id, new_vehicle)

        if self._broker_publish:
            vehicle_data_static = {
                "ID": new_vehicle.id,
                "Weight": new_vehicle.params["Weight"],
                "Length": new_vehicle.params["Length"],
                "Width": new_vehicle.params["Width"],
                "StartRoute": new_vehicle.params["StartRoute"],
                "EndRoute": new_vehicle.params["EndRoute"],
                "Direction": new_vehicle.direction,
            }
            register_device(
                device_id=new_vehicle.id,
                entity_type="Vehicle",
                api_key="vehicle",
                static_attributes=vehicle_data_static,
            )
        return new_vehicle

    def spawn_vehicle(self) -> Optional[Vehicle]:
        """Probabilistically spawns a new vehicle; ensures at least 2 vehicles stay active."""
        check = random.random()
        min_active = 2
        if (check <= self.parameters.get("SpawnProbability", 0.05) and len(self.active_vehicles) <= 10) or len(self.active_vehicles) < min_active:
            return self.force_spawn_vehicle()
        return None
