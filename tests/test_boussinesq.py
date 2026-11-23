"""
tests/test_boussinesq.py — Analytical 2D Boussinesq Elastostatics Tests
=======================================================================

Validates analytical Boussinesq surface stress, deflection, and validation bounds.
"""

import math
import pytest
from fastapi import HTTPException
from dashboard_backend import get_boussinesq_stress


def test_boussinesq_stress_calculation():
    """Verify Boussinesq stress computation returns valid numerical grids and expected physics."""
    res = get_boussinesq_stress(axle_load_kn=115.0, tire_config="dual", contact_pressure_kpa=750.0)

    assert res["status"] == "success"
    assert "contact_radius_m" in res
    assert res["contact_radius_m"] > 0.05

    grid_sig = res["sigma_z"]
    assert len(grid_sig) == 40  # nz
    assert len(grid_sig[0]) == 60  # nx

    # Physical attenuation check: stress near surface must exceed stress at bottom
    shallow_max = max(grid_sig[0])
    deep_max = max(grid_sig[-1])
    assert shallow_max > deep_max, f"Shallow stress ({shallow_max}) should exceed deep stress ({deep_max})"

    # Physical millimeter deflection check (sub-5 mm under 115 kN on 350 MPa composite modulus)
    max_wz = max(max(row) for row in res["w_z"])
    assert 0.05 < max_wz < 5.0, f"Expected realistic surface deflection in mm (0.05..5.0), got {max_wz}"


@pytest.mark.parametrize(
    ("axle_load_kn", "contact_pressure_kpa"),
    [(0.0, 750.0), (-10.0, 750.0), (115.0, 0.0), (115.0, -50.0)],
)
def test_boussinesq_rejects_non_positive_inputs(axle_load_kn: float, contact_pressure_kpa: float):
    """Non-positive axle loads or contact pressures must return HTTP 422."""
    with pytest.raises(HTTPException) as exc_info:
        get_boussinesq_stress(
            axle_load_kn=axle_load_kn,
            tire_config="dual",
            contact_pressure_kpa=contact_pressure_kpa,
        )
    assert exc_info.value.status_code == 422


def test_boussinesq_tire_configurations():
    """Verify single vs dual tire configurations adjust contact radius correctly."""
    res_dual = get_boussinesq_stress(axle_load_kn=100.0, tire_config="dual", contact_pressure_kpa=750.0)
    res_single = get_boussinesq_stress(axle_load_kn=100.0, tire_config="single", contact_pressure_kpa=750.0)

    # In single tire config, full wheel load is on one tire, so contact radius must be larger
    assert res_single["contact_radius_m"] > res_dual["contact_radius_m"]
    assert math.isclose(
        res_single["contact_radius_m"],
        res_dual["contact_radius_m"] * math.sqrt(2),
        rel_tol=1e-2,
    )
