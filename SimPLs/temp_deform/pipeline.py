"""
SimPLs/temp_deform/pipeline.py — Thermal-Deformation Simulation Product Line
============================================================================

Project: Digital Twin Road Demonstrator — Open Source Road Infrastructure Platform (MIT)
"""

import time
from typing import Dict, Any

from SimPLs.temp_deform.temp import TemperatureSim
from SimPLs.temp_deform.deform import DeformationSim


class TempDeformSimPL:
    """
    Coupled thermal-mechanical simulation pipeline orchestrator.

    Executes the 1D thermal conduction (``TemperatureSim``) and mechanical pavement
    damage estimation (``DeformationSim``) pipeline for each active vehicle.
    """

    def __init__(self) -> None:
        self.current_time = time.time()
        self.simpl_id = id(self)
        self.temp_sim = TemperatureSim()
        self.deform_sim = DeformationSim()
        self.time = time.time()

    def simulation_pipeline(self, vehicle_id: Any, vehicle_obj: Any) -> None:
        """Run coupled thermal diffusion and damage estimation and update vehicle metadata."""
        vehicle_md: Dict[str, Any] = vehicle_obj.params
        temp_displ = self.temp_sim.temperature_simulation(vehicle_md)
        damage = self.deform_sim.damage_estimation(vehicle_md, temp_displ)
        vehicle_md.update({
            "TemperatureDisplacement": temp_displ,
            "Damage": damage,
            "AirTemperature": vehicle_md["State"]["AirTemperature"],
            "RoadSurfaceTemperature": vehicle_md["State"]["RoadSurfaceTemperature"],
            "SoilTemperature": vehicle_md["State"]["SoilTemperature"],
            "WeatherState": vehicle_md["State"]["WeatherState"],
            "RoadStructure": vehicle_md["State"].get("RoadStructure"),
            "RoadsideUnit": vehicle_md["State"].get("RoadsideUnit"),
            "RoadsideUnitName": vehicle_md["State"].get("RoadsideUnitName"),
            "RoadsideUnitTown": vehicle_md["State"].get("RoadsideUnitTown"),
            "RoadsideUnitStation": vehicle_md["State"].get("RoadsideUnitStation"),
            "RoadsideUnitDist": vehicle_md["State"].get("RoadsideUnitDist"),
        })
