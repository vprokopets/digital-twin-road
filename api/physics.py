"""
api/physics.py — Analytical Mechanics, Thermal Field & Engine Status Router
===========================================================================

Provides standalone 1D thermal depth profiles, 2D Boussinesq pavement stress
fields, multi-year rutting prognosis traces, and active model-engine status.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from SimPLs.engine_contract import get_model_engine

router = APIRouter(tags=["Physics"])


class ThermalRequest(BaseModel):
    """Input boundary conditions and pavement layer stack for 1D steady-state thermal FEM."""

    surface_temp: float
    soil_temp: float
    road_structure: dict


@router.get("/dashboard/prediction_plot")
def get_prediction_plot(state: Optional[float] = None) -> Dict[str, Any]:
    """Computes 3-to-15 year pavement rutting prognosis curves scaled by segment health."""
    x_vals = [0.0, 0.33, 0.4, 0.45, 0.5, 0.55, 0.6, 0.67, 1.0]
    y_3_base = [-0.0015, 0.0005, -0.0005, -0.0045, -0.0053, -0.0045, 0.0000, 0.0005, -0.0015]
    y_6_base = [-0.0025, 0.0010, -0.0015, -0.0075, -0.0092, -0.0075, -0.0015, 0.0010, -0.0025]
    y_9_base = [-0.0030, 0.0015, -0.0025, -0.0105, -0.0128, -0.0105, -0.0020, 0.0015, -0.0030]
    y_12_base = [-0.0038, 0.0018, -0.0035, -0.0126, -0.0155, -0.0126, -0.0025, 0.0018, -0.0038]
    y_15_base = [-0.0042, 0.0020, -0.0030, -0.0148, -0.0185, -0.0148, -0.0028, 0.0020, -0.0042]

    if state is None:
        return {
            "status": "empty",
            "message": "Select a road point on the map to view the long-term prediction",
            "x": x_vals,
            "traces": [],
        }

    scale = 1 + ((100 - state) / 100.0)
    return {
        "status": "success",
        "state": state,
        "x": x_vals,
        "traces": [
            {"name": "3 years", "y": [y * scale for y in y_3_base], "color": "#c96515", "dash": [5, 5]},
            {"name": "6 years", "y": [y * scale for y in y_6_base], "color": "#69359c", "dash": [10, 5]},
            {"name": "9 years", "y": [y * scale for y in y_9_base], "color": "#13a7e8", "dash": [5, 5, 1, 5]},
            {"name": "12 years", "y": [y * scale for y in y_12_base], "color": "#00a250", "dash": [20, 5]},
            {"name": "15 years", "y": [y * scale for y in y_15_base], "color": "#000000", "dash": []},
        ],
    }


@router.get("/dashboard/boussinesq_stress")
def get_boussinesq_stress(
    axle_load_kn: float = 115.0,
    tire_config: str = "dual",
    contact_pressure_kpa: float = 750.0,
) -> Dict[str, Any]:
    """Computes analytical 2D Boussinesq elastostatic cross-section stresses under HGV axle load."""
    if axle_load_kn <= 0.0 or contact_pressure_kpa <= 0.0:
        raise HTTPException(
            status_code=422,
            detail="axle_load_kn and contact_pressure_kpa must be positive",
        )
    p_wheel_n = (axle_load_kn * 1000.0) / 2.0
    if tire_config == "dual":
        tire_offsets = [-0.17, 0.17]
        p_tire_n = p_wheel_n / 2.0
    else:
        tire_offsets = [0.0]
        p_tire_n = p_wheel_n

    contact_radius = math.sqrt(p_tire_n / (math.pi * (contact_pressure_kpa * 1000.0)))
    a = max(0.05, contact_radius)

    nx, nz = 60, 40
    x_min, x_max = -1.5, 1.5
    z_min, z_max = 0.005, 1.50
    dx = (x_max - x_min) / (nx - 1)
    dz = (z_max - z_min) / (nz - 1)

    grid_sigma_z: List[List[float]] = []
    grid_w_z: List[List[float]] = []
    grid_tau_max: List[List[float]] = []

    e_equiv_pa = 350.0e6  # Pa (350 MPa equivalent composite modulus)
    nu_equiv = 0.35

    for iz in range(nz):
        z = z_min + iz * dz
        row_sig = []
        row_w = []
        row_tau = []
        centerline = 1.0 - (z**3) / ((a**2 + z**2) ** 1.5)
        spread = math.sqrt(a**2 + 0.45 * z**2)

        for ix in range(nx):
            x = x_min + ix * dx
            sig_z = 0.0
            w_z = 0.0
            sig_x = 0.0

            for tx in tire_offsets:
                r = abs(x - tx)
                lateral = (1.0 + (r / spread) ** 2) ** (-2.5)
                tire_sig_z = contact_pressure_kpa * centerline * lateral
                sig_z += tire_sig_z

                rad_factor = z / math.sqrt(r**2 + z**2)
                tire_sig_x = tire_sig_z * (1.0 - 0.7 * rad_factor)
                sig_x += tire_sig_x

                w_center = (
                    (2.0 * (contact_pressure_kpa * 1000.0) * (1.0 - nu_equiv**2) * a / e_equiv_pa)
                    * (math.sqrt(1.0 + (z / a) ** 2) - (z / a))
                    * 1000.0
                )
                w_lateral = (1.0 + (r / (a + 0.75 * z)) ** 2) ** (-0.75)
                w_z += w_center * w_lateral

            tau = max(0.0, (sig_z - sig_x) * 0.5)
            row_sig.append(round(sig_z, 1))
            row_w.append(round(w_z, 3))
            row_tau.append(round(tau, 1))

        grid_sigma_z.append(row_sig)
        grid_w_z.append(row_w)
        grid_tau_max.append(row_tau)

    return {
        "status": "success",
        "tire_config": tire_config,
        "axle_load_kn": axle_load_kn,
        "contact_pressure_kpa": contact_pressure_kpa,
        "contact_radius_m": round(a, 4),
        "x_coords": [round(x_min + i * dx, 3) for i in range(nx)],
        "z_coords": [round(z_min + j * dz, 3) for j in range(nz)],
        "sigma_z": grid_sigma_z,
        "w_z": grid_w_z,
        "tau_max": grid_tau_max,
    }


@router.post("/dashboard/thermal_distribution")
def compute_thermal_distribution(req: ThermalRequest) -> Dict[str, Any]:
    """Computes steady-state 1D depth temperature profile across pavement layers."""
    layers = []
    layer_keys = sorted(
        [k for k in req.road_structure.keys() if k.startswith("Layer_")],
        key=lambda key: (0, int(key.split("_", 1)[1])) if key.split("_", 1)[1].isdigit() else (1, key),
    )
    for k in layer_keys:
        v = req.road_structure[k]
        if isinstance(v, dict):
            layers.append(v)

    if not layers:
        return {"status": "success", "depths": [0, 1], "temps": [req.surface_temp, req.soil_temp]}

    for layer in layers:
        if float(layer.get("ThermalConductivity", 1.5)) <= 0.0:
            raise HTTPException(
                status_code=422,
                detail="Layer ThermalConductivity must be positive",
            )
    r_total = sum(layer.get("Length", 0.1) / float(layer.get("ThermalConductivity", 1.5)) for layer in layers)
    if r_total <= 0.0:
        raise HTTPException(
            status_code=422,
            detail="Total pavement thermal resistance must be positive",
        )
    if r_total == 0:
        r_total = 1.0

    q = (req.surface_temp - req.soil_temp) / r_total
    depths = [0.0]
    temps = [req.surface_temp]
    current_depth = 0.0
    current_temp = req.surface_temp

    for layer in layers:
        length = layer.get("Length", 0.1)
        k = layer.get("ThermalConductivity", 1.5)
        step = 0.05
        num_substeps = max(1, int(length / step))
        actual_step = length / num_substeps
        for _ in range(num_substeps):
            delta_t = q * (actual_step / k)
            current_depth += actual_step
            current_temp -= delta_t
            depths.append(current_depth)
            temps.append(current_temp)

    return {"status": "success", "depths": depths, "temps": temps}


@router.get("/api/engine/status")
def get_engine_status() -> Dict[str, Any]:
    """Returns health and configuration of the active local or external model engine."""
    return get_model_engine().status()
