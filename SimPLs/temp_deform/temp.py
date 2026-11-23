"""
SimPLs/temp_deform/temp.py — 1D Layered Pavement Thermal Conduction Simulation
==============================================================================

Project: Digital Twin Road Demonstrator
"""

from __future__ import annotations
from typing import Any, Dict, List
import numpy as np
import SimPLs.temp_deform.fem_solver as cfc
from fm import (
    RoadMaterial,
    AsphaltMixin,
    ConcreteMixin,
    GravelMixin,
    WeatherState,
    SunnyMixin,
    CloudyMixin,
    RainyMixin,
    SnowyMixin,
    ThermalModel,
)

__all__ = [
    "TemperatureSim",
    "RoadMaterial",
    "AsphaltMixin",
    "ConcreteMixin",
    "GravelMixin",
    "WeatherState",
    "SunnyMixin",
    "CloudyMixin",
    "RainyMixin",
    "SnowyMixin",
    "ThermalModel",
]


class TemperatureSim:
    """1D steady-state finite-element pavement depth temperature solver."""

    def __init__(self) -> None:
        self.temp_displ: np.ndarray = np.array([])

    def temperature_simulation(self, vehicle_md: Dict[str, Any]) -> List[float]:
        """Solves nodal temperatures from ambient air (index 0) across layers down to subgrade soil (index -1)."""
        road_md = vehicle_md["State"]["RoadMetadata"]
        layers_number = len([x for x in road_md if "Layer" in x])
        air_temp = float(vehicle_md["State"]["AirTemperature"])
        soil_temp = float(vehicle_md["State"]["SoilTemperature"])

        if layers_number == 0:
            self.temp_displ = np.array([[air_temp], [soil_temp]], dtype=float)
            return [air_temp, soil_temp]

        Edof = np.array([[x, x + 1] for x in range(1, layers_number + 3)])
        K = np.zeros((layers_number + 3, layers_number + 3), dtype=float)
        f = np.zeros((layers_number + 3, 1), dtype=float)
        # Apply solar heat flux to free pavement surface node (DOF 2 / index 1), not fixed air Dirichlet node 1 (index 0)
        f[1] = 10.0 if vehicle_md["State"].get("WeatherState") == "Sunny" else 0.0

        cfc.assem(Edof[0, :], K, cfc.spring1e(1.0 / 0.04))
        cfc.assem(Edof[layers_number + 1, :], K, cfc.spring1e(1.0 / 0.04))

        for layer in range(layers_number):
            cfc.assem(Edof[layer + 1, :], K, cfc.spring1e(road_md[f"Layer_{layer}"]["CorrespondingStiffness"]))
        bc = np.array([1, layers_number + 3])
        bc_val = np.array([air_temp, soil_temp])
        self.temp_displ, _ = cfc.solveq(K, f, bc, bc_val)
        return [layer_temp.item(0) for layer_temp in self.temp_displ]
