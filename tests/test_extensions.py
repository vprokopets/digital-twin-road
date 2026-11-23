"""
tests/test_extensions.py — Unit Tests for Sensor Ingestion, Cartesian CRS & Extension Seams
===========================================================================================

Verifies:
- `WGS84CoordSystem` and `LocalCartesianCoordSystem` strategy distance/bearing/projection.
- 6-sensor hardware telemetry ingestion (`TML KM-100HAS`, `TML KDG-500KPA`, `PT1000`,
  `Truebner SMT100`, `HGS HG-5VHS`, `Silicon Designs 2210-002`) via FastAPI endpoints.
- `DeformationSim.damage_estimation` surface temperature node fix (`temp_displ[1]`).
- `ScenarioLoader` loading a `LocalCartesian` bundle with `embedded_sensors` and `lane_polygons`.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from SimPLs.engine_contract import (
    EntityObservation,
    HttpExternalEngine,
    PythonLocalEngine,
    StepRequest,
    get_model_engine,
    sanitize_json_payload,
    set_model_engine,
)
from SimPLs.temp_deform.deform import DeformationSim
from api.runtime import get_shadow
import dashboard_backend
from dashboard_backend import (
    SensorTelemetryRequest,
    _build_inspector_panel,
    get_engine_status,
    get_sensor_telemetry,
    ingest_sensor_telemetry,
)
from world.geo_utils import (
    LocalCartesianCoordSystem,
    WGS84CoordSystem,
    get_coord_system,
)
from world.scenario_loader import ScenarioLoader
from world.sensor_sources import IngestedSensorStream, SensorFrame, get_sensor_stream, set_sensor_stream


def test_coord_system_wgs84_and_local_cartesian() -> None:
    """Verify WGS84 spherical vs. LocalCartesian planar Euclidean distance, bearing, and projection."""
    wgs = get_coord_system({"mode": "WGS84"})
    assert isinstance(wgs, WGS84CoordSystem)
    assert 111.0 < wgs.distance_km(13.0, 51.0, 13.0, 52.0) < 111.5
    assert abs(wgs.bearing_deg(13.0, 51.0, 14.0, 51.0) - 90.0) < 0.5

    cart = get_coord_system({"mode": "LocalCartesian"})
    assert isinstance(cart, LocalCartesianCoordSystem)
    assert abs(cart.distance_m(0.0, 0.0, 3.0, 4.0) - 5.0) < 1e-9
    assert abs(cart.distance_km(0.0, 0.0, 3.0, 4.0) - 0.005) < 1e-12
    assert abs(cart.bearing_deg(0.0, 0.0, 10.0, 0.0) - 90.0) < 1e-9
    assert abs(cart.bearing_deg(0.0, 0.0, 0.0, 10.0) - 0.0) < 1e-9

    x2, y2 = cart.destination_point(10.0, 20.0, 90.0, 25.0)
    assert abs(x2 - 35.0) < 1e-9
    assert abs(y2 - 20.0) < 1e-9


def test_six_sensor_hardware_ingestion_and_query() -> None:
    """Verify 6-sensor telemetry ingestion and retrieval via REST endpoint handlers."""
    prev_stream = get_sensor_stream()
    try:
        set_sensor_stream(IngestedSensorStream(maxlen=50, forward_to_broker=False))
        req = SensorTelemetryRequest(
            timestamp="2026-11-21T00:00:00Z",
            strain_ue=142.5,
            pressure_kpa=318.0,
            temperature_c=26.4,
            depth_temperatures_c=[26.4, 23.1, 19.8, 15.2],
            moisture_pct=18.7,
            geophone_ppv_mms=4.2,
            accel_rms_g=0.08,
            accel_peak_g=0.34,
            source="beckhoff_ethercat",
        )
        res_post = ingest_sensor_telemetry("rsu_00", req)
        assert res_post["status"] == "success"
        assert res_post["frame"]["strain_ue"] == 142.5
        assert res_post["frame"]["geophone_ppv_mms"] == 4.2
        assert res_post["frame"]["accel_peak_g"] == 0.34

        res_get = get_sensor_telemetry("rsu_00", limit=10)
        assert res_get["status"] == "ok"
        assert res_get["latest"]["pressure_kpa"] == 318.0
        assert len(res_get["history"]) == 1
        assert res_get["hardware_catalog"]["strain_ue"]["model"] == "TML KM-100HAS"
        assert res_get["hardware_catalog"]["geophone_ppv_mms"]["model"] == "HGS HG-5VHS"
        assert res_get["hardware_catalog"]["accel_rms_g"]["model"] == "Silicon Designs 2210-002"
    finally:
        set_sensor_stream(prev_stream)


def test_deformation_uses_surface_temperature_node() -> None:
    """Verify DeformationSim scales wear using top pavement surface temperature (index 1), not soil (-1)."""
    sim = DeformationSim()
    veh = {"Weight": 40000.0}
    hot_wear = sim.damage_estimation(veh, [36.0, 35.0, 28.0, 20.0, 15.0])
    cold_wear = sim.damage_estimation(veh, [15.0, 15.0, 15.0, 15.0, 15.0])
    assert hot_wear > cold_wear
    assert abs(hot_wear - (40000.0 * 0.00001 * (35.0 / 20.0))) < 1e-9


def test_local_cartesian_scenario_bundle_loading(tmp_path: Path) -> None:
    """Verify ScenarioLoader loads LocalCartesian bundle with embedded_sensors and lane_polygons."""
    bdir = tmp_path / "cartesian_track"
    bdir.mkdir()
    (bdir / "scenario.json").write_text(json.dumps({
        "scenario_id": "cartesian_track",
        "name": "Proving Ground Oval",
        "version": "2.0.0",
        "coordinate_system": {
            "mode": "LocalCartesian",
            "unit": "m",
            "origin_gps": [0.0, 0.0],
            "bounds": [[0.0, 0.0], [500.0, 200.0]],
        },
        "simulation": {"scale_multiplier": 5.0, "closed_loop": True},
        "files": {
            "pavement_catalog": "pavement_catalog.json",
            "road_segments": "road_segments.geojson",
            "road_curves": "road_curves.geojson",
            "lane_polygons": "lane_polygons.geojson",
            "infrastructure": "infrastructure.json",
        },
    }), encoding="utf-8")
    (bdir / "pavement_catalog.json").write_text(json.dumps({"pavements": {}}), encoding="utf-8")
    (bdir / "road_segments.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"id": "seg_0", "direction": 1, "station_start_km": 0.0, "station_end_km": 0.1},
            "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [100.0, 0.0]]},
        }],
    }), encoding="utf-8")
    (bdir / "road_curves.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
    (bdir / "lane_polygons.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"lanelet_id": 101},
            "geometry": {"type": "Polygon", "coordinates": [[[0, -1.75], [100, -1.75], [100, 1.75], [0, 1.75], [0, -1.75]]]},
        }],
    }), encoding="utf-8")
    (bdir / "infrastructure.json").write_text(json.dumps({
        "manifest_version": "2.0.0",
        "roadside_units": {"type": "FeatureCollection", "features": []},
        "embedded_sensors": {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"id": "sens_km100_01", "model": "TML KM-100HAS"},
                "geometry": {"type": "Point", "coordinates": [50.0, 0.0]},
            }],
        },
    }), encoding="utf-8")

    loader = ScenarioLoader(scenarios_dir=tmp_path)
    bundle = loader.load("cartesian_track")
    assert bundle.coordinate_system["mode"] == "LocalCartesian"
    assert bundle.simulation["closed_loop"] is True
    assert len(bundle.lane_polygons["features"]) == 1
    assert len(bundle.get_embedded_sensors()["features"]) == 1


def test_python_local_engine_batch_step() -> None:
    """Verify PythonLocalEngine evaluates batch observations into thermal profiles and wear increments."""
    engine = PythonLocalEngine()
    assert engine.is_healthy() is True

    req = StepRequest(
        sim_time_s=15.0,
        dt_s=5.0,
        coordinate_system={"mode": "WGS84"},
        entities=[
            EntityObservation(
                entity_id="veh_1",
                entity_type="vehicle",
                station_km=12.4,
                velocity_kmh=82.0,
                weight_kg=40000.0,
                road_material="Concrete",
                weather_state="Rainy",
                air_temp_c=18.0,
                surface_temp_c=23.0,
                soil_temp_c=14.0,
                serving_rsu_id="rsu_01",
            )
        ],
    )
    resp = engine.evaluate_batch(req)
    assert resp.engine == "python-hpn"
    assert "veh_1" in resp.results
    res = resp.results["veh_1"]
    assert len(res.temperature_profile_c) >= 3
    assert res.damage_increment > 0.0
    assert res.state_vector == res.temperature_profile_c
    assert res.active_contexts == ["Concrete", "Rainy"]


def test_http_external_engine_sanitization_and_fallback() -> None:
    """Verify strict JSON NaN/Inf sanitization, offline fallback, and mocked external solver HTTP 200 parsing."""
    sanitized = sanitize_json_payload({
        "ok": 42.5,
        "nan_val": float("nan"),
        "nested": [float("inf"), 1.5, float("-inf")],
        "tup": (float("nan"), 2.0),
    })
    assert sanitized == {
        "ok": 42.5,
        "nan_val": None,
        "nested": [None, 1.5, None],
        "tup": [None, 2.0],
    }

    req = StepRequest(
        sim_time_s=30.0,
        dt_s=5.0,
        coordinate_system={"mode": "LocalCartesian", "unit": "m"},
        entities=[
            EntityObservation(
                entity_id="veh_101",
                velocity_kmh=86.5,
                weight_kg=40000.0,
                air_temp_c=22.0,
                soil_temp_c=14.5,
                surface_temp_c=26.4,
            )
        ],
        sensor_frames={"rsu_00": {"strain_ue": float("nan"), "temperature_c": 26.4}},
    )
    serialized = req.to_dict()
    assert serialized["sensor_frames"]["rsu_00"]["strain_ue"] is None

    engine = HttpExternalEngine("http://127.0.0.1:59999", timeout_s=0.1, fallback=PythonLocalEngine())

    with patch("SimPLs.engine_contract.requests.get", side_effect=OSError("unreachable")):
        assert engine.is_healthy() is False

    with patch("SimPLs.engine_contract.requests.post", side_effect=OSError("connection refused")):
        fallback_resp = engine.evaluate_batch(req)
        assert fallback_resp.engine == "python-hpn"
        assert "veh_101" in fallback_resp.results

    mock_julia_body = {
        "engine": "external-http",
        "sim_time_s": 30.0,
        "global_active_contexts": ["ConcreteJPCP", "WetCooling"],
        "control_petri_net": {"places": ["p1"], "transitions": ["t1"], "arcs": []},
        "compute_time_ms": 0.85,
        "results": {
            "veh_101": {
                "temperature_profile_c": [28.0, 26.4, 21.8, 14.5],
                "damage_increment": 0.042,
                "state_vector": [28.0, 26.4, 21.8, 14.5],
                "active_contexts": ["ConcreteJPCP", "WetCooling"],
                "solver_mode": "COP-MTK",
                "accuracy": 0.994,
                "introspection": {
                    "engine": "external-http",
                    "source_language": "julia",
                    "active_contexts": ["ConcreteJPCP", "WetCooling"],
                    "code": "@context (ConcreteJPCP, WetCooling) function solve(s) end",
                },
            }
        },
    }
    mock_ok = SimpleNamespace(status_code=200, json=lambda: mock_julia_body)
    mock_health = SimpleNamespace(status_code=200)

    with patch("SimPLs.engine_contract.requests.get", return_value=mock_health):
        assert engine.is_healthy() is True

    with patch("SimPLs.engine_contract.requests.post", return_value=mock_ok):
        julia_resp = engine.evaluate_batch(req)
        assert julia_resp.engine == "external-http"
        assert julia_resp.global_active_contexts == ["ConcreteJPCP", "WetCooling"]
        assert julia_resp.control_petri_net is not None
        item = julia_resp.results["veh_101"]
        assert item.state_vector == [28.0, 26.4, 21.8, 14.5]
        assert item.introspection is not None
        assert item.introspection.source_language == "julia"
        assert item.introspection.active_contexts == ["ConcreteJPCP", "WetCooling"]


def test_embedded_sensor_inspector_and_engine_status() -> None:
    """Verify embedded sensor inspector panel resolution and `/api/engine/status` output."""
    prev_stream = get_sensor_stream()
    prev_engine = get_model_engine()
    try:
        stream = IngestedSensorStream(maxlen=20, forward_to_broker=False)
        set_sensor_stream(stream)
        stream.ingest(SensorFrame(
            station_id="rsu_01",
            timestamp="2026-11-21T01:00:00Z",
            strain_ue=155.0,
            geophone_ppv_mms=3.8,
            accel_peak_g=0.29,
        ))
        panel = _build_inspector_panel(
            "SingleEmbeddedSensorStateDS",
            {"id": "rsu_01", "model": "TML KM-100HAS", "station_km": 12.5},
            "rsu_01",
        )
        assert panel is not None
        assert panel["panel_type"] == "embedded_sensor"
        assert panel["station_id"] == "rsu_01"
        assert panel["latest_frame"]["strain_ue"] == 155.0
        assert "geophone_ppv_mms" in panel["hardware_catalog"]

        set_model_engine(PythonLocalEngine())
        status = get_engine_status()
        assert status["status"] == "ok"
        assert status["engine"] == "python-hpn"
        assert status["healthy"] is True
    finally:
        set_sensor_stream(prev_stream)
        set_model_engine(prev_engine)


def test_api_runtime_syncs_dashboard_backend_shadow_instance() -> None:
    """Verify mutations to `dashboard_backend.shadow_instance` are immediately visible to `api.runtime.get_shadow()`."""
    prev_shadow = dashboard_backend.shadow_instance
    sentinel = object()
    try:
        dashboard_backend.shadow_instance = sentinel
        assert get_shadow() is sentinel
    finally:
        dashboard_backend.shadow_instance = prev_shadow
        assert get_shadow() is prev_shadow


def test_road_segment_inspector_dynamic_structures_and_hydrology() -> None:
    """Verify road_segment inspector panel reflects true Concrete/Asphalt RStO 12 layers + FSS and ClosestWater."""
    concrete_panel = _build_inspector_panel(
        "SingleRoadSegmentStateDS",
        {
            "id": "road_seg_dir2_341",
            "road_name": "A14 Motorway",
            "RoadStructure": "RoadStructure_2",
            "RoadMaterial": "Concrete",
            "RoadStructureConfig": {
                "LoadClass": "Bk100",
                "Standard": "RStO 12 Tafel 2, Zeile 1",
                "RoadType": {"Concrete": {}},
                "Layer_0": {"Name": "Concrete Slab (JPCP C30/37)", "Length": 0.27, "ModulusMPa": 34000},
                "Layer_1": {"Name": "Hydraulically Bound Base (HGT)", "Length": 0.15, "ModulusMPa": 12000},
                "Layer_2": {"Name": "Frost Protection Layer (FSS)", "Length": 0.28, "ModulusMPa": 150},
            },
            "ClosestWater": 8.075,
        },
        "road_seg_dir2_341",
    )
    assert concrete_panel is not None
    assert concrete_panel["road_material"] == "Concrete"
    assert concrete_panel["road_structure_id"] == "RoadStructure_2"
    assert concrete_panel["load_class"] == "Bk100"
    assert [layer["thickness_cm"] for layer in concrete_panel["pavement_layers"]] == [27, 15, 28]
    assert [layer["modulus_mpa"] for layer in concrete_panel["pavement_layers"]] == [34000, 12000, 150]
    assert concrete_panel["pavement_layers"][2]["material"] == "Unbound"
    assert concrete_panel["nearest_water"]["distance_km"] == 8.1
    assert concrete_panel["nearest_water"]["in_influence_zone"] is False

    asphalt_panel = _build_inspector_panel(
        "SingleRoadSegmentStateDS",
        {
            "id": "road_seg_dir1_12",
            "road_name": "A4 Motorway",
            "RoadStructure": "RoadStructure_1",
            "RoadMaterial": "Asphalt",
            "RoadStructureConfig": {
                "LoadClass": "Bk100",
                "Standard": "RStO 12 Tafel 1, Zeile 1",
                "RoadType": {"Asphalt": {}},
                "Layer_0": {"Name": "Surface Course (SMA 11 S)", "Length": 0.04, "ModulusMPa": 6500},
                "Layer_1": {"Name": "Binder Course (AC 16 B S)", "Length": 0.08, "ModulusMPa": 8000},
                "Layer_2": {"Name": "Asphalt Base Course (AC 22 T S)", "Length": 0.22, "ModulusMPa": 7500},
                "Layer_3": {"Name": "Frost Protection Layer (FSS)", "Length": 0.36, "ModulusMPa": 150},
            },
            "ClosestWater": 1.8,
        },
        "road_seg_dir1_12",
    )
    assert asphalt_panel is not None
    assert asphalt_panel["road_material"] == "Asphalt"
    assert asphalt_panel["load_class"] == "Bk100"
    assert [layer["thickness_cm"] for layer in asphalt_panel["pavement_layers"]] == [4, 8, 22, 36]
    assert [layer["modulus_mpa"] for layer in asphalt_panel["pavement_layers"]] == [6500, 8000, 7500, 150]
    assert asphalt_panel["pavement_layers"][3]["material"] == "Unbound"
    assert asphalt_panel["nearest_water"]["distance_km"] == 1.8
    assert asphalt_panel["nearest_water"]["in_influence_zone"] is True


def test_rsto12_road_config_and_catalog_physics_invariants() -> None:
    """Verify RStO 12 road_config.json and pavement_catalog.json thicknesses, FSS, FEM solving, and hierarchy."""
    from SimPLs.temp_deform.temp import TemperatureSim

    root = Path(__file__).resolve().parent.parent
    road_cfg = json.loads((root / "configs" / "road_config.json").read_text(encoding="utf-8"))
    catalog = json.loads((root / "scenarios" / "a14_corridor" / "pavement_catalog.json").read_text(encoding="utf-8"))

    bound_totals_cm: dict[str, float] = {}
    temp_sim = TemperatureSim()

    for idx in range(5):
        key = f"RoadStructure_{idx}"
        assert key in road_cfg
        entry = road_cfg[key]
        layer_keys = sorted(
            (k for k in entry if k.startswith("Layer_")),
            key=lambda name: int(name.split("_", 1)[1]),
        )
        assert len(layer_keys) >= 3
        # Guard against TemperatureSim counting non-layer keys via `"Layer" in k`
        non_layer_matches = [k for k in entry if "Layer" in k and not k.startswith("Layer_")]
        assert non_layer_matches == []

        total_m = 0.0
        for lkey in layer_keys:
            lcfg = entry[lkey]
            length = float(lcfg["Length"])
            k_val = float(lcfg["ThermalConductivity"])
            total_m += length
            assert abs(float(lcfg["CorrespondingStiffness"]) - (k_val / length)) < 1e-3

        assert 0.65 - 1e-6 <= total_m <= 0.70 + 1e-6
        bottom = entry[layer_keys[-1]]
        assert "FSS" in bottom["Name"]
        assert bottom["ModulusMPa"] == 150

        if "Asphalt" in entry["RoadType"]:
            assert float(entry["Layer_0"]["Length"]) == pytest.approx(0.04)

        bound_m = sum(float(entry[lk]["Length"]) for lk in layer_keys[:-1])
        bound_totals_cm[entry["Name"]] = round(bound_m * 100.0, 2)

        profile = temp_sim.temperature_simulation({
            "State": {
                "WeatherState": "Sunny",
                "AirTemperature": 25.0,
                "SoilTemperature": 14.0,
                "RoadMetadata": entry,
            }
        })
        assert len(profile) == len(layer_keys) + 3
        assert all(-50.0 < val < 100.0 for val in profile)

    # Monotonic RStO 12 bound thickness hierarchy: A14 Concrete > A4 Bk100 > A38 Bk32 > DD Bk10 > L Bk3.2
    assert bound_totals_cm["A14"] == 42.0
    assert bound_totals_cm["A4"] == 34.0
    assert bound_totals_cm["A38"] == 30.0
    assert bound_totals_cm["DD"] == 26.0
    assert bound_totals_cm["L"] == 22.0
    assert (
        bound_totals_cm["A14"]
        > bound_totals_cm["A4"]
        > bound_totals_cm["A38"]
        > bound_totals_cm["DD"]
        > bound_totals_cm["L"]
    )

    # Verify pavement_catalog.json total_thickness_m matches the exact sum of listed layers
    for pav_id, pav in catalog["pavements"].items():
        layer_sum = sum(float(layer["thickness_m"]) for layer in pav["layers"])
        assert float(pav["total_thickness_m"]) == pytest.approx(layer_sum, abs=1e-6), pav_id
        assert any("FSS" in layer["name"] for layer in pav["layers"]), pav_id
