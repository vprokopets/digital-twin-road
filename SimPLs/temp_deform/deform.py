"""
SimPLs/temp_deform/deform.py — Pavement Surface Wear & Damage Estimation
========================================================================

Estimates incremental pavement wear from vehicle gross weight and the
computed top-surface pavement nodal temperature.
"""

from typing import Dict, Any, Sequence


class DeformationSim:
    """Estimates incremental pavement surface wear from vehicle load and thermal state."""

    def damage_estimation(self, vehicle_md: Dict[str, Any], temp_displ: Sequence[float]) -> float:
        """Computes incremental damage scaled by asphalt temperature stiffness loss above 20 °C."""
        weight = float(vehicle_md.get("Weight", 36000.0))
        damage = weight * 0.00001
        if temp_displ:
            # Node 0 is ambient air boundary; Node 1 is the top pavement surface node (Node -1 is deep soil).
            surface_temp = float(temp_displ[1] if len(temp_displ) > 1 else temp_displ[0])
            temp_coef = surface_temp / 20.0 if surface_temp > 20.0 else 1.0
        else:
            temp_coef = 1.0
        return damage * temp_coef
