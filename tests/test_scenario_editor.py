"""
tests/test_scenario_editor.py — Scenario Infrastructure & Asset Editing Tests
=============================================================================

Verifies scenario infrastructure persistence and live asset parameter overrides.
"""

import asyncio
import json
from pathlib import Path
import pytest
from fastapi import HTTPException
from dashboard_backend import (
    AssetUpdateRequest,
    SaveScenarioRequest,
    SelectionRequest,
    SimSpeedRequest,
    control_sim_speed,
    root,
    save_scenario_infrastructure,
    select_map_object,
    update_asset_parameters,
)


def test_scenario_loader_save_infrastructure(tmp_path: Path):
    """Verify that save_infrastructure correctly updates infrastructure.json in the scenario bundle."""
    # Create a dummy scenario in tmp_path
    scen_dir = tmp_path / "test_editor_scenario"
    scen_dir.mkdir()
    scenario_desc = {
        "scenario_id": "test_editor_scenario",
        "name": "Test Editor Scenario",
        "version": "2.0.0",
        "files": {
            "infrastructure": "infrastructure.json"
        }
    }
    with open(scen_dir / "scenario.json", "w") as f:
        json.dump(scenario_desc, f)

    initial_infra = {
        "manifest_version": "2.0.0",
        "roadside_units": {"type": "FeatureCollection", "features": []}
    }
    with open(scen_dir / "infrastructure.json", "w") as f:
        json.dump(initial_infra, f)

    from world.scenario_loader import ScenarioLoader
    loader = ScenarioLoader(scenarios_dir=tmp_path)
    bundle = loader.load("test_editor_scenario")
    assert len(bundle.get_roadside_units()["features"]) == 0

    # Now add an RSU and save
    updated_infra = {
        "manifest_version": "2.0.0",
        "roadside_units": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "id": "rsu_test_99",
                        "name": "RSU-Test-99",
                        "station_km": 42.0,
                        "coverage_radius_km": 12.0
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [13.5, 51.1]
                    }
                }
            ]
        }
    }
    success = loader.save_infrastructure("test_editor_scenario", updated_infra)
    assert success is True

    # Reload bundle to verify persistence
    with open(scen_dir / "infrastructure.json") as f:
        saved_on_disk = json.load(f)
    assert len(saved_on_disk["roadside_units"]["features"]) == 1
    assert saved_on_disk["roadside_units"]["features"][0]["properties"]["id"] == "rsu_test_99"


def test_save_scenario_endpoint(monkeypatch, tmp_path: Path):
    """Verify save_scenario_infrastructure function executes cleanly without mutating tracked corridor data."""
    from world.scenario_loader import ScenarioLoader
    loader = ScenarioLoader(scenarios_dir=tmp_path)
    scen_dir = tmp_path / "mock_test_corridor"
    scen_dir.mkdir()
    with open(scen_dir / "scenario.json", "w") as f:
        json.dump({
            "scenario_id": "mock_test_corridor",
            "name": "Mock Corridor",
            "files": {"infrastructure": "infrastructure.json"}
        }, f)
    with open(scen_dir / "infrastructure.json", "w") as f:
        json.dump({
            "manifest_version": "2.0.0",
            "roadside_units": {"type": "FeatureCollection", "features": []}
        }, f)

    monkeypatch.setattr("world.scenario_loader.get_scenario_loader", lambda: loader)
    req = SaveScenarioRequest(
        scenario_id="mock_test_corridor",
        infrastructure={"manifest_version": "2.0.0", "roadside_units": {"type": "FeatureCollection", "features": []}}
    )
    res = save_scenario_infrastructure(req)
    assert res["status"] == "success"
    assert res["scenario_id"] == "mock_test_corridor"


def test_update_asset_parameters_vehicle_and_rsu():
    """Verify live parameter override endpoint for both active vehicles and RSUs."""
    from digital_shadow import DigitalShadow
    import dashboard_backend as db

    ds = DigitalShadow(fiware_flag=False)
    db.shadow_instance = ds

    # Test vehicle parameter update
    assert len(ds.traffic_management.active_vehicles) > 0
    vid = next(iter(ds.traffic_management.active_vehicles.keys()))
    req_v = AssetUpdateRequest(
        asset_type="vehicle",
        asset_id=str(vid),
        properties={"Velocity": 95.0, "Weight": 42000.0, "Direction": -1}
    )
    res_v = update_asset_parameters(req_v)
    assert res_v["status"] == "success"
    vobj = ds.traffic_management.active_vehicles[vid]
    assert vobj.params["Velocity"] == 95.0
    assert vobj.params["Weight"] == 42000.0
    assert vobj.direction == -1

    # Test RSU weather and parameter update
    rsu_features = ds.world.roadside_units.get("features", [])
    assert len(rsu_features) > 0
    rsu_id = rsu_features[0]["properties"]["id"]
    req_r = AssetUpdateRequest(
        asset_type="rsu",
        asset_id=str(rsu_id),
        properties={"AirTemperature": 34.5, "RoadSurfaceTemperature": 41.2, "WeatherState": "Sunny"}
    )
    res_r = update_asset_parameters(req_r)
    assert res_r["status"] == "success"
    w_key = rsu_features[0].get("Weather", rsu_features[0].get("properties", {}).get("Weather"))
    w_obj = ds.world.weather_objects.get(w_key)
    assert w_obj is not None
    assert getattr(w_obj, "air_temp", getattr(w_obj, "air_temperature", None)) == 34.5
    assert getattr(w_obj, "current_state", getattr(w_obj, "weather_condition", None)) == "Sunny"


def test_rsu00_realtime_pi_weather_override_and_reset():
    """Verify RealTimePiWeather (RSU-00) honors manual overrides and resets cleanly."""
    from digital_shadow import DigitalShadow
    import dashboard_backend as db

    ds = DigitalShadow(fiware_flag=False)
    db.shadow_instance = ds

    rsu0 = ds.world.roadside_units["features"][0]
    rsu0_id = rsu0["properties"]["id"]
    w_obj = ds.world.weather_objects[rsu0["Weather"]]

    update_asset_parameters(AssetUpdateRequest(
        asset_type="rsu",
        asset_id=str(rsu0_id),
        properties={"AirTemperature": 38.0, "RoadSurfaceTemperature": 46.5, "WeatherState": "Rainy"},
    ))
    assert w_obj.manual_override is True

    # Stepping update_state must preserve overridden values while manual_override is active
    w_obj.update_state("2026-11-18 13:00:00")
    assert w_obj.air_temp == 38.0
    assert w_obj.road_temp == 46.5
    assert w_obj.current_state == "Rainy"

    # Resetting override resumes live/default sensor computation
    res_reset = update_asset_parameters(AssetUpdateRequest(
        asset_type="rsu",
        asset_id=str(rsu0_id),
        properties={"ResetOverride": True},
    ))
    assert res_reset["updated_properties"]["ResetOverride"] is True
    assert w_obj.manual_override is False
    w_obj.update_state("2026-11-18 13:00:05")
    assert w_obj.current_state != "Rainy" or w_obj.air_temp != 38.0


def test_save_infrastructure_sanitizes_transient_keys(tmp_path: Path):
    """Verify save_infrastructure strips transient runtime fields across all asset collections."""
    from world.scenario_loader import ScenarioLoader

    scen_dir = tmp_path / "clean_save_scenario"
    scen_dir.mkdir()
    with open(scen_dir / "scenario.json", "w", encoding="utf-8") as f:
        json.dump({
            "scenario_id": "clean_save_scenario",
            "name": "Clean Save Test",
            "files": {"infrastructure": "infrastructure.json"},
        }, f)
    with open(scen_dir / "infrastructure.json", "w", encoding="utf-8") as f:
        json.dump({"manifest_version": "2.0.0"}, f)

    loader = ScenarioLoader(scenarios_dir=tmp_path)
    dirty_payload = {
        "manifest_version": "2.0.0",
        "roadside_units": {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "Weather": 123456,
                "Drones": ["uav_01"],
                "AssignedWarnings": ["warn_01"],
                "properties": {
                    "id": "rsu_01",
                    "name": "RSU-01",
                    "station_km": 10.5,
                    "coverage_radius_km": 10.0,
                    "WeatherState": "Rainy",
                    "drone_id": "uav_01",
                    "sensor_source": "Markov",
                    "LastUpdated": "2026-11-18",
                },
                "geometry": {"type": "Point", "coordinates": [13.5, 51.1]},
            }],
        },
        "spawn_points": {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {
                    "id": "jct_01",
                    "daily_aadt": 42000,
                    "vehicles_spawned": 17,
                    "TargetFrom": 0.05,
                },
                "geometry": {"type": "Point", "coordinates": [13.6, 51.1]},
            }],
        },
        "water_sources": {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {
                    "id": "water_01",
                    "basin": "Elbe",
                    "thermal_depression_c": 4.2,
                    "local_soil_temp_c": 10.8,
                },
                "geometry": {"type": "Point", "coordinates": [13.7, 51.1]},
            }],
        },
    }
    assert loader.save_infrastructure("clean_save_scenario", dirty_payload) is True

    saved = json.loads((scen_dir / "infrastructure.json").read_text(encoding="utf-8"))
    rsu_feat = saved["roadside_units"]["features"][0]
    assert "Weather" not in rsu_feat and "Drones" not in rsu_feat and "AssignedWarnings" not in rsu_feat
    assert set(rsu_feat["properties"].keys()) == {"id", "name", "station_km", "coverage_radius_km"}
    assert set(saved["spawn_points"]["features"][0]["properties"].keys()) == {"id", "daily_aadt"}
    assert set(saved["water_sources"]["features"][0]["properties"].keys()) == {"id", "basin"}


def test_mutating_and_status_endpoints_direct():
    """Verify root health, sim speed clamping, 404 handling, and stats_synthetic metadata flag."""
    from digital_shadow import DigitalShadow
    import dashboard_backend as db

    health = asyncio.run(root())
    assert health["status"] == "ok"

    ds = DigitalShadow(fiware_flag=False)
    db.shadow_instance = ds

    speed_res = control_sim_speed(SimSpeedRequest(multiplier=25.0))
    assert speed_res["status"] == "success"
    assert speed_res["sim_speed"] == 10.0

    with pytest.raises(HTTPException) as exc_veh:
        update_asset_parameters(AssetUpdateRequest(asset_type="vehicle", asset_id="missing_v", properties={"Velocity": 80}))
    assert exc_veh.value.status_code == 404

    with pytest.raises(HTTPException) as exc_rsu:
        update_asset_parameters(AssetUpdateRequest(asset_type="rsu", asset_id="missing_rsu", properties={"AirTemperature": 20}))
    assert exc_rsu.value.status_code == 404

    seg_res = select_map_object(SelectionRequest(
        selection_type="SingleRoadSegmentStateDS",
        feature_data={"properties": {"id": "road_seg_dir1_0", "station_start_km": 0.5, "direction": 1}},
    ))
    assert seg_res["status"] == "success"
    assert seg_res["stats_synthetic"] is True
