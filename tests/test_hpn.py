"""
tests/test_hpn.py — Heraklit Compositional Hybrid Petri Net Tests
=================================================================

Unit tests for Wolfgang Reisig's Heraklit Compositional Hybrid Petri Nets.
"""

from hpn import HeraklitHPNController, build_rsu_env_module, build_material_thermal_module, build_vehicle_solver_module


def test_heraklit_algebraic_composition():
    """Verify algebraic composition M1 @ M2 fuses boundary interfaces without error."""
    m_rsu = build_rsu_env_module(
        rsu_id="rsu_01",
        weather_state="Sunny",
        air_temp=22.0,
        road_temp=25.0,
        soil_temp=18.0,
    )
    m_mat = build_material_thermal_module(
        road_material="Asphalt",
        surface_temp=25.0,
        solar_flux=600.0,
        albedo=0.15,
        conductivity=1.2,
    )
    m_veh = build_vehicle_solver_module(
        solver_mode="FastSurrogate",
        accuracy=0.98,
        threshold=0.90,
        velocity_kmh=80.0,
        weight_kg=38000.0,
        damage_increment=0.15,
        just_switched=False,
    )

    # Compose modules using Reisig's Heraklit operator (@)
    composed = (m_rsu @ m_mat) @ m_veh
    assert composed is not None
    assert len(composed.places) > 0
    assert len(composed.transitions) > 0


def test_hpn_controller_evaluation():
    """Verify high-level controller evaluates state and serializes graph for Vue Flow."""
    controller = HeraklitHPNController()
    solver_mode, accuracy, fired = controller.step(
        rsu_id="rsu_02",
        weather_state="Rainy",
        road_material="Concrete",
        air_temp=14.0,
        road_temp=12.0,
        soil_temp=10.0,
        velocity_kmh=65.0,
        weight_kg=42000.0,
        mechanical_simulation={"Model": "POD", "Accuracy": 0.95},
        damage_increment=0.22,
    )

    assert solver_mode in ("FastSurrogate", "FEAPMechanicalModel", "POD")
    assert 0.0 <= accuracy <= 1.0

    graph_dict = controller.to_dict()
    assert "nodes" in graph_dict
    assert "edges" in graph_dict
    assert len(graph_dict["nodes"]) > 0
