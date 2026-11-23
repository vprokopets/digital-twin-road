"""
tests/test_release_regressions.py — Pre-Release Regression Tests
================================================================

Regression tests for physics, FEM, scenario persistence, RSU synchronization,
weather/deque resilience, and API validation.
"""

from __future__ import annotations

import asyncio
from collections import deque
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from SimPLs.temp_deform.temp import TemperatureSim
from api.runtime import get_shadow, set_shadow
import dashboard_backend
from dashboard_backend import SaveScenarioRequest, app, save_scenario_infrastructure
from data_curation import (
    NativeBroker,
    delete_entity,
    get_entity,
    register_device,
    send_telemetry,
)
import fm
from vehicle.vehicle import Vehicle
from world.helpers import get_abbreviated_cardinal_8pt
import world.scenario_loader as sl
from world.weather_sources import RealTimePiWeather
from world.world import World


def test_fem_1d_solar_flux_increases_surface_temperature():
    """Sunny conditions inject solar heat flux at surface node DOF 2, exceeding Cloudy."""
    solver = TemperatureSim()
    base_md = {
        "AirTemperature": 20.0,
        "SoilTemperature": 10.0,
        "RoadMetadata": {
            "Layer_0": {"CorrespondingStiffness": 20.0},
            "Layer_1": {"CorrespondingStiffness": 15.0},
        },
    }

    sunny = solver.temperature_simulation({"State": {**base_md, "WeatherState": "Sunny"}})
    cloudy = solver.temperature_simulation({"State": {**base_md, "WeatherState": "Cloudy"}})

    assert len(sunny) == 5
    assert sunny[0] == pytest.approx(20.0)
    assert sunny[-1] == pytest.approx(10.0)
    assert sunny[1] > cloudy[1]
    assert sunny[2] > cloudy[2]

    # Guard against 0 pavement layers
    zero_layers = solver.temperature_simulation(
        {
            "State": {
                "AirTemperature": 18.0,
                "SoilTemperature": 11.0,
                "WeatherState": "Sunny",
                "RoadMetadata": {},
            }
        }
    )
    assert zero_layers == [18.0, 11.0]


def test_concrete_material_toggles_westergaard_mixin():
    """Concrete segments must compose WestergaardMixin rather than leaving Boussinesq active."""

    class _DummyWorld:
        road_spawn_metadata = {"type": "FeatureCollection", "features": []}

        def __init__(self, material_name: str):
            self.material_name = material_name

        def get_states_for_position(self, position: float, direction: int):
            return {
                "Coordinates": "13.5, 51.1",
                "AirTemperature": 21.0,
                "RoadSurfaceTemperature": 24.0,
                "SoilTemperature": 13.0,
                "WeatherState": "Sunny",
                "RoadsideUnit": "rsu_00",
                "RoadMetadata": {"RoadType": {self.material_name: {}}},
            }

    dummy_world = _DummyWorld("Concrete")
    veh = Vehicle({"VehicleLimit": 50}, dummy_world)
    assert veh._sim_cls is not None
    assert issubclass(veh._sim_cls, fm.WestergaardMixin)
    assert not issubclass(veh._sim_cls, fm.BoussinesqMixin)

    dummy_world.material_name = "Asphalt"
    veh.update_states()
    assert veh._sim_cls is not None
    assert issubclass(veh._sim_cls, fm.BoussinesqMixin)
    assert not issubclass(veh._sim_cls, fm.WestergaardMixin)


def test_active_scenario_persists_across_default_get(monkeypatch, tmp_path: Path):
    """Calling get_active_scenario() without args must preserve custom active bundles."""
    scen_dir = tmp_path / "custom_test_corridor"
    scen_dir.mkdir()
    with open(scen_dir / "scenario.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "scenario_id": "custom_test_corridor",
                "name": "Custom Test Corridor",
                "version": "2.0.0",
                "files": {"infrastructure": "infrastructure.json"},
            },
            f,
        )
    with open(scen_dir / "infrastructure.json", "w", encoding="utf-8") as f:
        json.dump({"manifest_version": "2.0.0", "roadside_units": {"type": "FeatureCollection", "features": []}}, f)

    orig_loader = sl._global_scenario_loader
    orig_bundle = sl._active_scenario_bundle
    try:
        monkeypatch.setattr(sl, "_global_scenario_loader", sl.ScenarioLoader(scenarios_dir=tmp_path))
        monkeypatch.setattr(sl, "_active_scenario_bundle", None)

        sl.set_active_scenario("custom_test_corridor")
        active = sl.get_active_scenario()
        assert active.scenario_id == "custom_test_corridor"
    finally:
        sl._global_scenario_loader = orig_loader
        sl._active_scenario_bundle = orig_bundle


def test_save_scenario_syncs_new_rsu_without_weather_keyerror(monkeypatch, tmp_path: Path):
    """Adding an RSU via /api/scenarios/save initializes Weather/Drone and avoids KeyError on tick."""
    scen_dir = tmp_path / "save_sync_corridor"
    scen_dir.mkdir()
    with open(scen_dir / "scenario.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "scenario_id": "save_sync_corridor",
                "name": "Save Sync Corridor",
                "version": "2.0.0",
                "files": {"infrastructure": "infrastructure.json"},
            },
            f,
        )
    with open(scen_dir / "infrastructure.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "manifest_version": "2.0.0",
                "roadside_units": {"type": "FeatureCollection", "features": []},
                "spawn_points": {"type": "FeatureCollection", "features": []},
                "water_sources": {"type": "FeatureCollection", "features": []},
            },
            f,
        )

    configs_dir = Path(__file__).resolve().parent.parent / "configs"
    with open(configs_dir / "global_config.json", "r", encoding="utf-8") as f:
        global_cfg = json.load(f)

    orig_loader = sl._global_scenario_loader
    orig_bundle = sl._active_scenario_bundle
    orig_runtime_shadow = get_shadow()
    orig_backend_shadow = dashboard_backend.shadow_instance

    try:
        tmp_loader = sl.ScenarioLoader(scenarios_dir=tmp_path, configs_dir=configs_dir)
        monkeypatch.setattr(sl, "_global_scenario_loader", tmp_loader)
        monkeypatch.setattr(sl, "_active_scenario_bundle", None)
        sl.set_active_scenario("save_sync_corridor")

        w = World(global_cfg["Weather"], fiware_flag=False)
        w.read_road_metadata()
        fake_shadow = SimpleNamespace(world=w, _lock=threading.RLock())
        set_shadow(fake_shadow)
        dashboard_backend.shadow_instance = fake_shadow

        req = SaveScenarioRequest(
            scenario_id="save_sync_corridor",
            infrastructure={
                "roadside_units": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"id": "rsu_new_99", "name": "RSU-99", "station_km": 18.5},
                            "geometry": {"type": "Point", "coordinates": [13.52, 51.08]},
                        }
                    ],
                }
            },
        )
        res = save_scenario_infrastructure(req)
        assert res["status"] == "success"

        w.update_weather_state("2026-11-23 12:00:00")
        assert len(w.roadside_units["features"]) == 1
        rsu_feat = w.roadside_units["features"][0]
        assert rsu_feat["Weather"] in w.weather_objects
        assert rsu_feat["properties"]["drone_id"] in w.drone_objects
        assert rsu_feat["properties"]["WeatherState"] in ("Sunny", "Cloudy", "Rainy")
    finally:
        set_shadow(orig_runtime_shadow)
        dashboard_backend.shadow_instance = orig_backend_shadow
        sl._global_scenario_loader = orig_loader
        sl._active_scenario_bundle = orig_bundle


@pytest.mark.parametrize(
    ("deg", "expected"),
    [
        (0.0, "N"),
        (1.0, "N"),
        (22.0, "N"),
        (359.0, "N"),
        (45.0, "NE"),
        (90.0, "E"),
        (180.0, "S"),
        (270.0, "W"),
    ],
)
def test_abbreviated_cardinal_8pt_boundaries(deg: float, expected: str):
    """8-point compass sectors must center N on [337.5, 22.5)."""
    assert get_abbreviated_cardinal_8pt(deg) == expected


def test_realtime_pi_weather_skips_none_in_deque():
    """Trailing None telemetry values must fall back to prior valid value or default."""
    with open(Path(__file__).resolve().parent.parent / "configs" / "global_config.json", "r", encoding="utf-8") as f:
        weather_cfg = json.load(f)["Weather"]
    pi = RealTimePiWeather(weather_cfg, source_id="test_pi")
    assert pi._get_latest_from_deque(deque([21.5, None]), 25.0) == pytest.approx(21.5)
    assert pi._get_latest_from_deque(deque([None]), 25.0) == pytest.approx(25.0)


def _call_fastapi(method: str, path: str, *, params: dict | None = None, json_body: dict | None = None):
    """Calls FastAPI via TestClient when httpx is installed, or direct ASGI dispatch offline."""
    try:
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.request(method, path, params=params, json=json_body)
        return resp.status_code, resp.json()
    except RuntimeError:
        body_bytes = json.dumps(json_body).encode("utf-8") if json_body is not None else b""
        query_bytes = urlencode(params or {}).encode("utf-8")
        headers = [(b"host", b"testserver")]
        if json_body is not None:
            headers.extend([
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body_bytes)).encode("ascii")),
            ])

        async def _invoke():
            status_code = 500
            chunks = []
            sent = False

            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body_bytes, "more_body": False}
                return {"type": "http.disconnect"}

            async def send(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = int(message["status"])
                elif message["type"] == "http.response.body":
                    chunks.append(message.get("body", b""))

            scope = {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": method.upper(),
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("ascii"),
                "query_string": query_bytes,
                "headers": headers,
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
            }
            await app(scope, receive, send)
            raw = b"".join(chunks).decode("utf-8")
            return status_code, json.loads(raw) if raw else {}

        return asyncio.run(_invoke())


def test_fastapi_http_smoke_and_validation_endpoints():
    """HTTP smoke test for /, /health, validation status codes, and /api/assets/update."""
    orig_runtime_shadow = get_shadow()
    orig_backend_shadow = dashboard_backend.shadow_instance

    try:
        code_root, data_root = _call_fastapi("GET", "/")
        assert code_root == 200
        assert data_root["status"] == "ok"

        set_shadow(None)
        dashboard_backend.shadow_instance = None
        code_h0, _ = _call_fastapi("GET", "/health")
        assert code_h0 == 503

        fake_world = SimpleNamespace(
            roadside_units={"type": "FeatureCollection", "features": []},
            weather_objects={},
        )
        fake_shadow = SimpleNamespace(
            world=fake_world,
            _lock=threading.RLock(),
            sim_healthy=True,
            last_tick_at="2026-11-23 12:00:00",
        )
        set_shadow(fake_shadow)
        dashboard_backend.shadow_instance = fake_shadow
        code_h1, _ = _call_fastapi("GET", "/health")
        assert code_h1 == 200

        fake_shadow.sim_healthy = False
        code_h2, _ = _call_fastapi("GET", "/health")
        assert code_h2 == 503

        code_bouss, _ = _call_fastapi("GET", "/dashboard/boussinesq_stress", params={"axle_load_kn": 0})
        assert code_bouss == 422

        code_therm, _ = _call_fastapi(
            "POST",
            "/dashboard/thermal_distribution",
            json_body={
                "air_temp": 20.0,
                "soil_temp": 10.0,
                "weather_state": "Sunny",
                "road_structure": {"Layer_0": {"Length": 0.1, "ThermalConductivity": 0.0}},
            },
        )
        assert code_therm == 422

        code_asset, _ = _call_fastapi(
            "POST",
            "/api/assets/update",
            json_body={"asset_type": "invalid", "asset_id": "x", "properties": {"foo": 1}},
        )
        assert code_asset == 400
    finally:
        set_shadow(orig_runtime_shadow)
        dashboard_backend.shadow_instance = orig_backend_shadow


def test_unified_native_broker_records_and_deletes_entities(monkeypatch):
    """Module-level data_curation functions must support registration, telemetry, and deletion."""
    import data_curation as dc

    broker = NativeBroker()
    monkeypatch.setattr(dc, "get_data_broker", lambda backend=None: broker)

    assert register_device(device_id="rsu_unit_test", entity_type="Roadside_unit", api_key="rs")
    assert send_telemetry(device_id="rsu_unit_test", entity_type="Roadside_unit", sensor_dict={"AirTemperature": 19.5})
    ent = get_entity("rsu_unit_test")
    assert ent is not None
    assert ent["telemetry"]["AirTemperature"] == 19.5

    assert delete_entity("rsu_unit_test") is True
    assert get_entity("rsu_unit_test") is None


def test_fiware_status_exposes_endpoints_and_service_groups():
    """GET /dashboard/fiware_status exposes universal endpoints and FIWARE service groups."""
    code, payload = _call_fastapi("GET", "/dashboard/fiware_status")
    assert code == 200

    endpoints = payload.get("endpoints", {})
    for key in (
        "roadside_weather_ingest",
        "embedded_sensor_ingest",
        "broker_entity_history_template",
        "orion_entities",
        "iota_services",
        "iota_ultralight",
    ):
        assert key in endpoints and endpoints[key]

    entity_types = {sg.get("entity_type") for sg in payload.get("service_groups", [])}
    assert "Roadside_unit" in entity_types
    assert "Vehicle" in entity_types


def test_fiware_single_entity_endpoint_returns_200_and_404(monkeypatch):
    """GET /dashboard/fiware_entities/{entity_id} resolves registered entities and 404s when missing."""
    import data_curation as dc

    broker = NativeBroker()
    monkeypatch.setattr(dc, "get_data_broker", lambda backend=None: broker)
    assert register_device(device_id="rsu_lookup_01", entity_type="Roadside_unit", api_key="rs")
    assert send_telemetry(
        device_id="rsu_lookup_01",
        entity_type="Roadside_unit",
        sensor_dict={"AirTemperature": 21.0},
    )

    code_ok, ent = _call_fastapi("GET", "/dashboard/fiware_entities/rsu_lookup_01")
    assert code_ok == 200
    assert ent["id"] == "rsu_lookup_01"
    assert ent["telemetry"]["AirTemperature"] == 21.0

    code_missing, _ = _call_fastapi("GET", "/dashboard/fiware_entities/does_not_exist_999")
    assert code_missing == 404


def test_inspector_panels_include_broker_link_for_vehicle_and_rsu():
    """Vehicle and RSU inspector panels expose active Native/FIWARE entity links."""
    veh_panel = dashboard_backend._build_inspector_panel(
        "SingleVehicleStateDS",
        {"id": "101", "Velocity": 85.0, "Weight": 36000.0},
        "101",
    )
    assert veh_panel is not None
    v_link = veh_panel.get("broker_link")
    assert v_link is not None
    assert v_link["entity_id"] == "101"
    assert v_link["entity_type"] == "Vehicle"
    assert v_link["service_group"] == "vehicle"
    assert v_link["entity_api_url"] == "/dashboard/fiware_entities/101"
    assert "v2/entities/101" in v_link["orion_url"]
    assert "k=vehicle&i=101" in v_link["ultralight_url"]

    rsu_panel = dashboard_backend._build_inspector_panel(
        "SingleRoadsideUnitsStateDS",
        {"id": "rsu_01", "name": "RSU-01"},
        "rsu_01",
    )
    assert rsu_panel is not None
    r_link = rsu_panel.get("broker_link")
    assert r_link is not None
    assert r_link["entity_id"] == "rsu_01"
    assert r_link["entity_type"] == "Roadside_unit"
    assert r_link["service_group"] == "rs"
    assert r_link["entity_api_url"] == "/dashboard/fiware_entities/rsu_01"
    assert "v2/entities/rsu_01" in r_link["orion_url"]
    assert "k=rs&i=rsu_01" in r_link["ultralight_url"]


def test_fiware_entity_history_endpoint_returns_bounded_history_and_404(monkeypatch):
    """GET /dashboard/fiware_entities/{entity_id}/history returns bounded history and 404s when missing."""
    import data_curation as dc

    broker = NativeBroker()
    monkeypatch.setattr(dc, "get_data_broker", lambda backend=None: broker)

    assert register_device(device_id="rsu_hist_01", entity_type="Roadside_unit", api_key="rs")
    for temp in (18.0, 19.0, 20.0):
        assert send_telemetry(
            device_id="rsu_hist_01",
            entity_type="Roadside_unit",
            sensor_dict={"AirTemperature": temp},
        )

    code_ok, payload = _call_fastapi(
        "GET",
        "/dashboard/fiware_entities/rsu_hist_01/history",
        params={"limit": 2},
    )
    assert code_ok == 200
    assert payload["entity_id"] == "rsu_hist_01"
    assert payload["backend"] == "native"
    assert payload["limit"] == 2
    assert payload["count"] == 2
    assert payload["history"][0]["data"]["AirTemperature"] == 19.0
    assert payload["history"][-1]["data"]["AirTemperature"] == 20.0

    code_missing, _ = _call_fastapi("GET", "/dashboard/fiware_entities/missing_entity_999/history")
    assert code_missing == 404


def test_docs_catalog_lists_locked_builtin_docs_and_serves_markdown():
    """GET /api/docs returns zensical sections with locked=True and serves built-in Markdown safely."""
    code, catalog = _call_fastapi("GET", "/api/docs")
    assert code == 200
    assert catalog["builtin_count"] >= 20
    section_titles = [s["title"] for s in catalog["sections"]]
    assert "Overview" in section_titles
    assert "Getting Started" in section_titles
    assert "Scientific Foundations" in section_titles
    for sec in catalog["sections"]:
        for art in sec["articles"]:
            assert art["locked"] is True
            assert art["source"] == "builtin"

    code_art, article = _call_fastapi("GET", "/api/docs/article", params={"id": "index.md"})
    assert code_art == 200
    assert article["locked"] is True
    assert article["source"] == "builtin"
    assert len(article["content"].strip()) > 20

    code_trav, _ = _call_fastapi("GET", "/api/docs/article", params={"id": "../README.md"})
    assert code_trav in (400, 404)


def test_docs_custom_article_crud_lifecycle(monkeypatch, tmp_path):
    """Custom documentation endpoints support create, read, update, and delete in docs/custom/."""
    import api.docs as api_docs

    monkeypatch.setattr(api_docs, "CUSTOM_DOCS_DIR", tmp_path)

    code_create, created = _call_fastapi(
        "POST",
        "/api/docs/custom",
        json_body={
            "title": "A14 Field Calibration Note",
            "section": "Custom Articles",
            "content": "# Calibration\n\nInitial **test** content.",
        },
    )
    assert code_create == 200
    slug = created["slug"]
    assert created["id"] == f"custom/{slug}"
    assert created["locked"] is False
    assert (tmp_path / f"{slug}.md").is_file()

    code_cat, catalog = _call_fastapi("GET", "/api/docs")
    assert code_cat == 200
    custom_ids = [a["id"] for a in catalog["custom_articles"]]
    assert f"custom/{slug}" in custom_ids

    code_get, fetched = _call_fastapi("GET", "/api/docs/article", params={"id": f"custom/{slug}"})
    assert code_get == 200
    assert fetched["locked"] is False
    assert fetched["title"] == "A14 Field Calibration Note"
    assert fetched["content"].startswith("# Calibration")
    assert "updated_at:" not in fetched["content"]

    code_upd, updated = _call_fastapi(
        "PUT",
        f"/api/docs/custom/{slug}",
        json_body={
            "title": "A14 Field Calibration Note v2",
            "section": "Field Notes",
            "content": "# Calibration v2\n\nUpdated note body.",
        },
    )
    assert code_upd == 200
    assert updated["title"] == "A14 Field Calibration Note v2"
    assert updated["section"] == "Field Notes"
    assert "Updated note body." in updated["content"]

    code_del, deleted = _call_fastapi("DELETE", f"/api/docs/custom/{slug}")
    assert code_del == 200
    assert deleted["deleted"] == f"custom/{slug}"

    code_after, _ = _call_fastapi("GET", "/api/docs/article", params={"id": f"custom/{slug}"})
    assert code_after == 404

    code_bad, _ = _call_fastapi(
        "POST",
        "/api/docs/custom",
        json_body={"title": "Bad Slug", "slug": "../escape", "content": "nope"},
    )
    assert code_bad == 400


def test_fiware_registration_treats_409_conflict_as_idempotent(monkeypatch):
    """Existing FIWARE resources returning 409 Conflict must be treated as registered."""
    from data_curation.fiware.client import FiwareDeviceManager
    import requests

    mgr = FiwareDeviceManager(mock_mode=False)
    monkeypatch.setattr(requests, "post", lambda *a, **kw: SimpleNamespace(status_code=409, text="AlreadyExists"))

    assert mgr.register_service_group(api_key="rs", entity_type="Roadside_unit") is True
    assert mgr.register_device(device_id="rsu_01", api_key="rs", entity_type="Roadside_unit") is True
    assert mgr.activate_persistance_db() is True
    assert mgr.mock_mode is False


def test_fiware_entity_url_encodes_special_ids(monkeypatch):
    """FiwareBroker and /dashboard/fiware_entities Orion fallback must URL-encode entity IDs."""
    import data_curation as dc
    from data_curation.fiware.broker import FiwareBroker
    from data_curation.fiware.client import FiwareDeviceManager
    import requests

    special_id = "urn:ngsi-ld:Vehicle:101/A14?x=1"
    seen_urls = []

    def fake_get(url, *args, **kwargs):
        seen_urls.append(url)
        return SimpleNamespace(status_code=200, json=lambda: {"id": special_id})

    monkeypatch.setattr(requests, "get", fake_get)

    mgr = FiwareDeviceManager(orion_host="orion", mock_mode=False)
    broker = FiwareBroker(manager=mgr, orion_host="orion")
    res = broker.get_entity(special_id)
    assert res == {"id": special_id}
    assert seen_urls[-1].endswith("/v2/entities/urn%3Angsi-ld%3AVehicle%3A101%2FA14%3Fx%3D1")

    monkeypatch.setattr(dc, "get_entity", lambda _eid: None)
    orig_shadow = get_shadow()
    fake_shadow = SimpleNamespace(fiware_flag=True)
    set_shadow(fake_shadow)
    try:
        code, payload = _call_fastapi("GET", "/dashboard/fiware_entities/urn:ngsi-ld:Vehicle:101")
        assert code == 200
        assert payload["id"] == special_id
        assert seen_urls[-1].endswith("/v2/entities/urn%3Angsi-ld%3AVehicle%3A101")
    finally:
        set_shadow(orig_shadow)


def test_dockerignore_keeps_builtin_docs_and_excludes_custom_docs():
    """Backend Docker build must include built-in docs/ while excluding docs/_build and docs/custom."""
    dockerignore_path = Path(__file__).resolve().parent.parent / ".dockerignore"
    entries = {
        line.strip().rstrip("/")
        for line in dockerignore_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert "docs" not in entries
    assert "docs/_build" in entries
    assert "docs/custom" in entries
