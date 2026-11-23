"""
tests/test_fiware_schema.py — Declarative FIWARE Metamodel & Client Tests
=========================================================================

Tests JSON schema validity, template retrieval, UltraLight 2.0 serialization,
and mock mode device registration & telemetry publishing.
"""

import json
from pathlib import Path
import pytest

from data_curation.fiware.client import FiwareDeviceManager
from data_curation.fiware.roadside_unit import register_roadside_unit, send_sensor_data_roadside_unit
from data_curation.fiware.vehicle import register_vehicle, send_sensor_data_vehicle
from data_curation.fiware.service_group import register_service_group, activate_persistance_db


@pytest.fixture
def schema_path() -> Path:
    p = Path(__file__).resolve().parent.parent / "configs" / "fiware_schema.json"
    assert p.exists(), f"FIWARE schema not found at {p}"
    return p


@pytest.fixture
def mock_manager(schema_path: Path) -> FiwareDeviceManager:
    return FiwareDeviceManager(schema_path=schema_path, mock_mode=True)


def test_schema_structure(schema_path: Path):
    with open(schema_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("metamodel_version") == "2.0.0"
    assert "service_groups" in data
    assert len(data["service_groups"]) >= 3

    assert "entity_templates" in data
    templates = data["entity_templates"]
    assert "Roadside_unit" in templates
    assert "Vehicle" in templates
    assert "Embedded_sensor" in templates
    assert "Inspection_drone" in templates

    assert "persistency" in data
    assert data["persistency"]["sink"] == "postgresql"


def test_manager_template_lookup(mock_manager: FiwareDeviceManager):
    rsu_tpl = mock_manager.get_template("Roadside_unit")
    assert "dynamic_sensors" in rsu_tpl
    assert any(s["name"] == "RoadSurfaceTemperature" for s in rsu_tpl["dynamic_sensors"])

    veh_tpl = mock_manager.get_template("Vehicle")
    assert any(s["name"] == "Velocity" for s in veh_tpl["dynamic_sensors"])

    emb_tpl = mock_manager.get_template("Embedded_sensor")
    assert any(s["name"] == "Microstrain" for s in emb_tpl["dynamic_sensors"])


def test_ultralight_formatting(mock_manager: FiwareDeviceManager):
    # RSU formatting
    rsu_data = {
        "Weather": "Sunny",
        "AirTemperature": 21.5,
        "RoadSurfaceTemperature": 28.2,
        "SoilTemperature": 18.0,
    }
    payload = mock_manager.format_ultralight("Roadside_unit", rsu_data)
    assert "Weather|Sunny" in payload
    assert "AirTemperature|21.5" in payload
    assert "RoadSurfaceTemperature|28.2" in payload
    assert "SoilTemperature|18.0" in payload

    # Vehicle formatting
    veh_data = {
        "Active": True,
        "Velocity": 82.4,
        "Model": "Actros_1845",
        "Accuracy": 0.05,
        "DynamicAxleLoad": 115.0,
    }
    veh_payload = mock_manager.format_ultralight("Vehicle", veh_data)
    assert "Active|True" in veh_payload
    assert "Velocity|82.4" in veh_payload
    assert "Model|Actros_1845" in veh_payload
    assert "DynamicAxleLoad|115.0" in veh_payload


def test_mock_device_registration_and_telemetry(mock_manager: FiwareDeviceManager):
    # 1. Register service group
    ok_sg = mock_manager.register_service_group("test_api_key", entity_type="Roadside_unit")
    assert ok_sg is True

    # 2. Register device
    geo = {
        "geometry": {
            "coordinates": [13.737, 51.063],
            "type": "Point",
        }
    }
    ok_dev = mock_manager.register_device("rsu_test_01", "test_api_key", "Roadside_unit", geo_data=geo)
    assert ok_dev is True
    assert "rsu_test_01" in mock_manager.mock_entities
    entry = mock_manager.mock_entities["rsu_test_01"]
    assert entry["entity_type"] == "Roadside_unit"

    # 3. Send telemetry
    ok_tel = mock_manager.send_sensor_data(
        "rsu_test_01",
        "test_api_key",
        "Roadside_unit",
        {"Weather": "Cloudy", "AirTemperature": 15.0},
    )
    assert ok_tel is True
    assert len(mock_manager.mock_telemetry_history) == 1
    hist = mock_manager.mock_telemetry_history[0]
    assert hist["device_id"] == "rsu_test_01"
    assert "Weather|Cloudy" in hist["data"]


def test_backward_compatible_wrappers():
    # Service group
    assert register_service_group("legacy_key") is not None

    # Cygnus persistence
    assert activate_persistance_db() is not None

    # RSU registration & telemetry
    geo = {"geometry": {"coordinates": [13.5, 51.1], "type": "Point"}}
    assert register_roadside_unit("rsu_legacy", "key", geo) is not None
    assert send_sensor_data_roadside_unit("rsu_legacy", "key", {"Weather": "Rainy"}) is not None

    # Vehicle registration & telemetry
    veh_static = {"ID": "veh_legacy", "Weight": 24000, "Length": 16}
    assert register_vehicle("key", veh_static) is not None
    assert send_sensor_data_vehicle("veh_legacy", "key", {"Velocity": 75.0}) is not None
