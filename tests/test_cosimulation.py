"""
tests/test_cosimulation.py — Co-Simulation Loop & Spatial Indexing Tests
========================================================================

Verifies the O(log M) directional binary-search spatial index in Road,
multi-vehicle stepping in World and Vehicle, lazy HPN/FODA inspector
properties, and GeoJSON snapshot generation in DigitalShadow.
"""

from __future__ import annotations

from digital_shadow import DigitalShadow
from world.road import _haversine_km


def test_haversine_and_directional_spatial_index() -> None:
    """Verify fast spherical Haversine distance and O(log M) directional range lookup."""
    shadow = DigitalShadow(fiware_flag=False)
    road = shadow.world.road
    all_pts = road.road_structure_metadata_processed["features"]
    assert len(all_pts) >= 1215

    # Haversine sanity check (~111.2 km per degree latitude)
    dist_km = _haversine_km(51.0, 13.0, 52.0, 13.0)
    assert 111.0 < dist_km < 111.5

    # Directional lookup should only return points in the requested direction within [d_min, d_max]
    pts_dir1 = road.get_points_in_range(1, 5.0, 15.0)
    assert len(pts_dir1) > 0
    for pt in pts_dir1:
        assert pt["properties"].get("direction", 1) == 1
        assert 5.0 <= pt["properties"]["dist"] <= 15.0

    # Nearest point binary search
    sample = pts_dir1[len(pts_dir1) // 2]
    nearest_pt, _, _ = shadow.world.find_closest_point(sample["properties"]["dist"], 1)
    assert nearest_pt["properties"]["id"] == sample["properties"]["id"]


def test_vehicle_lazy_hpn_and_code_properties() -> None:
    """Verify that vehicle HPN state and synthesized mixin code evaluate lazily on access."""
    shadow = DigitalShadow(fiware_flag=False)
    active_vehicles = list(shadow.traffic_management.active_vehicles.values())
    assert len(active_vehicles) > 0
    v = active_vehicles[0]

    hpn_graph = v.hpn_state
    assert "algebraic_expression" in hpn_graph
    assert "arcs" in hpn_graph

    synthesized_code = v.code
    assert "class " in synthesized_code
    assert "HERAKLIT Hybrid Petri Net Composition" in v.heraklit_code


def test_digital_shadow_step_and_inspection() -> None:
    """Verify end-to-end co-simulation stepping, slimmed SSE GeoJSON, and deep entity inspection."""
    shadow = DigitalShadow(fiware_flag=False)
    shadow.update_geojson_snapshots()
    features = shadow.vehicles_geojson.get("features", [])
    assert len(features) > 0

    # Unselected vehicles in broadcast GeoJSON should exclude bulky inspector-only dictionaries
    first_feat = features[0]
    first_props = first_feat["properties"]
    assert "Active" in first_props
    assert "State" not in first_props

    # Inspecting a specific vehicle returns full HPN state, synthesized code, and statistics
    ret, stats, fm_graph, hpn_code, mech_code = shadow.inspect_object(
        {"SingleVehicleStateDS": first_feat}
    )
    assert ret is not None
    assert fm_graph is not None
    assert hpn_code is not None
    assert mech_code is not None
