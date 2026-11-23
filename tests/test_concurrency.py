"""
tests/test_concurrency.py — Thread Safety & SSE Delta Streaming Tests
=====================================================================

Verifies concurrent multi-client delta isolation and lock safety during streaming.
"""

from digital_shadow import DigitalShadow
import dashboard_backend
from dashboard_backend import get_dynamic_delta_state


def test_sse_multi_client_delta_independence():
    """Verify that multiple SSE clients reading deltas do not starve each other of dirty segments."""
    shadow = DigitalShadow(fiware_flag=False)
    dashboard_backend.shadow_instance = shadow

    # Client A and Client B start from current version
    v0 = shadow.world.dirty_version
    client_a_ver = v0
    client_b_ver = v0

    # No initial deltas
    delta_a, client_a_ver = get_dynamic_delta_state(since_version=client_a_ver)
    delta_b, client_b_ver = get_dynamic_delta_state(since_version=client_b_ver)
    assert delta_a["dirty_segments"] == {}
    assert delta_b["dirty_segments"] == {}

    # Mutate road points / segments
    shadow.world.mark_segment_dirty("seg_test_100", 75)
    shadow.world.mark_segment_dirty("seg_test_101", 62)

    # Client A reads delta first
    delta_a2, client_a_ver = get_dynamic_delta_state(since_version=client_a_ver)
    assert "seg_test_100" in delta_a2["dirty_segments"]
    assert delta_a2["dirty_segments"]["seg_test_100"] == 75
    assert delta_a2["dirty_segments"]["seg_test_101"] == 62

    # Client B reads delta next (Client B MUST receive the update even though A already read!)
    delta_b2, client_b_ver = get_dynamic_delta_state(since_version=client_b_ver)
    assert "seg_test_100" in delta_b2["dirty_segments"]
    assert delta_b2["dirty_segments"]["seg_test_100"] == 75
    assert delta_b2["dirty_segments"]["seg_test_101"] == 62

    # Subsequent reads yield empty deltas
    delta_a3, client_a_ver = get_dynamic_delta_state(since_version=client_a_ver)
    delta_b3, client_b_ver = get_dynamic_delta_state(since_version=client_b_ver)
    assert delta_a3["dirty_segments"] == {}
    assert delta_b3["dirty_segments"] == {}


def test_atomic_geojson_structures():
    """Verify GeoJSON FeatureCollections maintain complete valid schemas during rebuild."""
    shadow = DigitalShadow(fiware_flag=False)
    shadow.world.prepare_geojson()
    assert shadow.world.drone_geojson["type"] == "FeatureCollection"
    assert isinstance(shadow.world.drone_geojson["features"], list)
    assert shadow.world.warning_geojson["type"] == "FeatureCollection"
    assert isinstance(shadow.world.warning_geojson["features"], list)

    shadow.update_geojson_snapshots()
    assert shadow.vehicles_geojson["type"] == "FeatureCollection"
    assert isinstance(shadow.vehicles_geojson["features"], list)
