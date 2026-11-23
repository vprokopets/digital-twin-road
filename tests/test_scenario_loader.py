"""
tests/test_scenario_loader.py — Universal Scenario Loader & Bundle Engine Tests
===============================================================================

Tests schema validation, bundle discovery, RStO 12 pavement catalog retrieval,
infrastructure asset parsing, and FastAPI scenario endpoints.
"""

import json
from pathlib import Path
import pytest
from world.scenario_loader import (
    ScenarioLoader,
    get_scenario_loader,
)
from dashboard_backend import list_scenarios, get_scenario_details, switch_scenario, SwitchScenarioRequest


@pytest.fixture
def root_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def test_scenario_schema_validity(root_dir: Path):
    schema_path = root_dir / "configs" / "scenario_schema.json"
    scenario_path = root_dir / "scenarios" / "a14_corridor" / "scenario.json"

    assert schema_path.exists()
    assert scenario_path.exists()

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario = json.load(f)

    assert schema["metamodel_version"] == "2.0.0"
    assert scenario["scenario_id"] == "a14_corridor"
    assert scenario["coordinate_system"]["mode"] == "WGS84"
    assert "files" in scenario
    assert "pavement_catalog" in scenario["files"]


def test_scenario_loader_discovery():
    loader = get_scenario_loader()
    scenarios = loader.list_available_scenarios()
    assert len(scenarios) >= 1

    ids = [s["scenario_id"] for s in scenarios]
    assert "a14_corridor" in ids


def test_a14_corridor_bundle_contents():
    loader = get_scenario_loader()
    bundle = loader.load("a14_corridor")

    assert bundle.scenario_id == "a14_corridor"
    assert bundle.name == "Dresden–Leipzig A14 Freight Corridor"
    assert bundle.coordinate_system["crs_epsg"] == 4326

    # Test pavement catalog
    pavements = bundle.pavement_catalog.get("pavements", {})
    assert "Asphalt_Bk100_SMA11S" in pavements
    assert "Concrete_Bk100_Rigid" in pavements
    sma = bundle.get_pavement("Asphalt_Bk100_SMA11S")
    assert sma is not None
    assert len(sma["layers"]) >= 3

    # Test infrastructure
    rsus = bundle.get_roadside_units()
    assert rsus.get("type") == "FeatureCollection"
    assert len(rsus.get("features", [])) > 0

    spawns = bundle.get_spawn_points()
    assert spawns.get("type") == "FeatureCollection"
    assert len(spawns.get("features", [])) > 0

    water = bundle.get_water_sources()
    assert water.get("type") == "FeatureCollection"
    assert len(water.get("features", [])) > 0

    # Test traffic profile
    fleet = bundle.traffic_profile.get("fleet_composition", [])
    assert len(fleet) >= 2
    assert any("Actros" in v.get("model", "") for v in fleet)

    # Test geometry
    assert len(bundle.road_segments.get("features", [])) > 0
    assert len(bundle.road_curves.get("features", [])) > 0


def test_legacy_configs_fallback(root_dir: Path):
    # Test loading from a non-existent bundle triggers transparent fallback
    loader = ScenarioLoader(scenarios_dir=root_dir / "non_existent_dir")
    bundle = loader.load("fallback_test")
    assert bundle.scenario_id == "a14_corridor_legacy"
    assert bundle.coordinate_system["mode"] == "WGS84"


def test_scenario_api_endpoints():
    # 1. List scenarios
    data = list_scenarios()
    assert isinstance(data, list)
    assert any(s["scenario_id"] == "a14_corridor" for s in data)

    # 2. Get details
    det = get_scenario_details("a14_corridor")
    assert det["metadata"]["scenario_id"] == "a14_corridor"
    assert "Asphalt_Bk100_SMA11S" in det["pavements"]

    # 3. Switch scenario
    res = switch_scenario(SwitchScenarioRequest(scenario_id="a14_corridor"))
    assert res["status"] == "success"
    assert res["active_scenario"]["scenario_id"] == "a14_corridor"
