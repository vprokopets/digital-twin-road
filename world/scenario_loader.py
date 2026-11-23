"""
world/scenario_loader.py — Universal Scenario Loader & Packaging Engine
=======================================================================

Loads, validates, and manages multi-corridor and proving-ground scenario bundles.
Supports standard public highway networks (A14) as well as closed test tracks (ATC, SML).
Includes transparent fallback to legacy configs/ for backward compatibility.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("scenario_loader")


@dataclass
class ScenarioBundle:
    """In-memory representation of a fully resolved simulation scenario bundle."""

    scenario_id: str
    name: str
    version: str = "2.0.0"
    description: str = ""
    author: str = "Volodymyr Prokopets"
    coordinate_system: Dict[str, Any] = field(default_factory=lambda: {"mode": "WGS84", "crs_epsg": 4326})
    environment: Dict[str, Any] = field(default_factory=dict)
    simulation: Dict[str, Any] = field(default_factory=dict)
    files: Dict[str, str] = field(default_factory=dict)
    bundle_dir: Optional[Path] = None

    pavement_catalog: Dict[str, Any] = field(default_factory=dict)
    infrastructure: Dict[str, Any] = field(default_factory=dict)
    traffic_profile: Dict[str, Any] = field(default_factory=dict)
    road_segments: Dict[str, Any] = field(default_factory=dict)
    road_curves: Dict[str, Any] = field(default_factory=dict)
    lane_polygons: Dict[str, Any] = field(default_factory=dict)

    def get_roadside_units(self) -> Dict[str, Any]:
        """Returns a defensive deep copy of the RSU GeoJSON FeatureCollection."""
        if "roadside_units" in self.infrastructure:
            return copy.deepcopy(self.infrastructure["roadside_units"])
        return {"type": "FeatureCollection", "features": []}

    def get_spawn_points(self) -> Dict[str, Any]:
        """Returns a defensive deep copy of the vehicle spawn points GeoJSON FeatureCollection."""
        if "spawn_points" in self.infrastructure:
            return copy.deepcopy(self.infrastructure["spawn_points"])
        return {"type": "FeatureCollection", "features": []}

    def get_water_sources(self) -> Dict[str, Any]:
        """Returns a defensive deep copy of the hydrological cooling sources GeoJSON FeatureCollection."""
        if "water_sources" in self.infrastructure:
            return copy.deepcopy(self.infrastructure["water_sources"])
        return {"type": "FeatureCollection", "features": []}

    def get_embedded_sensors(self) -> Dict[str, Any]:
        """Returns a defensive deep copy of embedded pavement sensor stations GeoJSON FeatureCollection."""
        if "embedded_sensors" in self.infrastructure:
            return copy.deepcopy(self.infrastructure["embedded_sensors"])
        return {"type": "FeatureCollection", "features": []}

    def get_pavement(self, pavement_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a structural pavement configuration from the catalog."""
        pavements = self.pavement_catalog.get("pavements", {})
        return pavements.get(pavement_id)

    def summary(self) -> Dict[str, Any]:
        """Returns an API-friendly summary of the scenario."""
        seg_count = len(self.road_segments.get("features", []))
        rsu_count = len(self.get_roadside_units().get("features", []))
        spawn_count = len(self.get_spawn_points().get("features", []))
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "crs_mode": self.coordinate_system.get("mode", "WGS84"),
            "origin_gps": self.coordinate_system.get("origin_gps", [0.0, 0.0]),
            "road_segments_count": seg_count,
            "roadside_units_count": rsu_count,
            "spawn_points_count": spawn_count,
        }


class ScenarioLoader:
    """Manages discovery, validation, and loading of scenario bundles."""

    ROOT_DIR = Path(__file__).resolve().parent.parent
    DEFAULT_SCENARIOS_DIR = ROOT_DIR / "scenarios"
    DEFAULT_CONFIGS_DIR = ROOT_DIR / "configs"

    def __init__(self, scenarios_dir: Optional[Path] = None, configs_dir: Optional[Path] = None) -> None:
        self.scenarios_dir = scenarios_dir or self.DEFAULT_SCENARIOS_DIR
        self.configs_dir = configs_dir or self.DEFAULT_CONFIGS_DIR
        self._cached_bundles: Dict[str, ScenarioBundle] = {}

    def list_available_scenarios(self) -> List[Dict[str, Any]]:
        """Lists all discoverable scenario bundles."""
        summaries: List[Dict[str, Any]] = []

        if self.scenarios_dir.exists():
            for sdir in sorted(self.scenarios_dir.iterdir()):
                if sdir.is_dir() and (sdir / "scenario.json").exists():
                    try:
                        bundle = self.load(sdir.name)
                        summaries.append(bundle.summary())
                    except Exception as e:
                        logger.warning("Could not parse scenario in %s: %s", sdir, e)

        # If no scenario directory exists yet, provide fallback summary
        if not summaries:
            summaries.append({
                "scenario_id": "a14_corridor_legacy",
                "name": "Dresden–Leipzig A14 Corridor (Configs Fallback)",
                "version": "1.0.0",
                "description": "Legacy configs/ directory fallback",
                "author": "Volodymyr Prokopets",
                "crs_mode": "WGS84",
                "origin_gps": [13.737, 51.063],
                "road_segments_count": 0,
                "roadside_units_count": 0,
                "spawn_points_count": 0,
            })

        return summaries

    def load(self, scenario_id_or_path: str | Path = "a14_corridor") -> ScenarioBundle:
        """Loads a scenario bundle by ID or filesystem path, with automatic fallback and traversal prevention."""
        target_path: Path
        if isinstance(scenario_id_or_path, Path):
            target_path = scenario_id_or_path.resolve()
        else:
            safe_name = Path(scenario_id_or_path).name
            cand = (self.scenarios_dir / safe_name).resolve()
            target_path = cand if cand.exists() else (self.scenarios_dir / scenario_id_or_path).resolve()

        # Prevent arbitrary path traversal outside scenarios_dir
        try:
            target_path.relative_to(self.scenarios_dir.resolve())
        except ValueError:
            logger.warning("Attempted path traversal in scenario loader: '%s'", scenario_id_or_path)
            target_path = self.scenarios_dir / "a14_corridor"

        # Check in-memory cache
        cache_key = str(target_path.resolve()) if target_path.exists() else str(scenario_id_or_path)
        if cache_key in self._cached_bundles:
            return self._cached_bundles[cache_key]

        # 1. Load from modern scenario bundle
        if target_path.exists() and (target_path / "scenario.json").exists():
            bundle = self._load_from_bundle_dir(target_path)
            self._cached_bundles[cache_key] = bundle
            return bundle

        # 2. Transparent fallback to legacy configs/
        logger.info("Scenario bundle '%s' not found. Falling back to legacy configs/.", scenario_id_or_path)
        bundle = self._load_from_legacy_configs()
        self._cached_bundles[cache_key] = bundle
        return bundle

    def save_infrastructure(self, scenario_id: str, infrastructure_data: Dict[str, Any]) -> bool:
        """Persists updated infrastructure back to scenario files and refreshes bundle cache."""
        bundle = self.load(scenario_id)
        if bundle.bundle_dir and bundle.bundle_dir.exists():
            infra_filename = bundle.files.get("infrastructure", "infrastructure.json")
            infra_file = bundle.bundle_dir / infra_filename

            # Sanitize runtime transient keys before writing to disk
            cleaned_infra = copy.deepcopy(infrastructure_data)
            rsu_transient_props = {
                "LastUpdated",
                "sensor_source",
                "drone_id",
                "WeatherState",
                "AirTemperature",
                "RoadSurfaceTemperature",
                "ClosestPointDist",
            }
            for feat in cleaned_infra.get("roadside_units", {}).get("features", []):
                feat.pop("Weather", None)
                feat.pop("Drones", None)
                feat.pop("AssignedWarnings", None)
                props = feat.get("properties")
                if isinstance(props, dict):
                    for key in rsu_transient_props:
                        props.pop(key, None)

            spawn_transient_props = {
                "ClosestPoint",
                "ClosestPointDist",
                "vehicles_spawned",
                "vehicles_destined",
                "TargetFrom",
                "TargetTo",
            }
            for feat in cleaned_infra.get("spawn_points", {}).get("features", []):
                props = feat.get("properties")
                if isinstance(props, dict):
                    for key in spawn_transient_props:
                        props.pop(key, None)

            water_transient_props = {
                "ClosestPoint",
                "ClosestPointDist",
                "station_km",
                "distance_to_highway_m",
                "affected_segments_count",
                "affected_corridor_span_km",
                "affected_corridor_end_km",
                "max_moisture_coef",
                "soil_temp_dry_c",
                "soil_temp_saturated_c",
                "local_soil_temp_c",
                "thermal_depression_c",
            }
            for feat in cleaned_infra.get("water_sources", {}).get("features", []):
                props = feat.get("properties")
                if isinstance(props, dict):
                    for key in water_transient_props:
                        props.pop(key, None)

            with open(infra_file, "w", encoding="utf-8") as f:
                json.dump(cleaned_infra, f, indent=2)
            bundle.infrastructure = cleaned_infra
            logger.info("Successfully saved infrastructure for scenario '%s' to %s", scenario_id, infra_file)
            return True
        return False

    def _load_from_bundle_dir(self, bdir: Path) -> ScenarioBundle:
        with open(bdir / "scenario.json", "r", encoding="utf-8") as f:
            desc = json.load(f)

        files = desc.get("files", {})

        def _read_file(key: str, default_name: str) -> Dict[str, Any]:
            fname = files.get(key, default_name)
            fpath = bdir / fname
            if fpath.exists():
                with open(fpath, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}

        bundle = ScenarioBundle(
            scenario_id=desc.get("scenario_id", bdir.name),
            name=desc.get("name", bdir.name),
            version=desc.get("version", "2.0.0"),
            description=desc.get("description", ""),
            author=desc.get("author", "Volodymyr Prokopets"),
            coordinate_system=desc.get("coordinate_system", {"mode": "WGS84", "crs_epsg": 4326}),
            environment=desc.get("environment", {}),
            simulation=desc.get("simulation", {}),
            files=files,
            bundle_dir=bdir,
            pavement_catalog=_read_file("pavement_catalog", "pavement_catalog.json"),
            infrastructure=_read_file("infrastructure", "infrastructure.json"),
            traffic_profile=_read_file("traffic_profile", "traffic_profile.json"),
            road_segments=_read_file("road_segments", "road_segments.geojson"),
            road_curves=_read_file("road_curves", "road_curves.geojson"),
            lane_polygons=_read_file("lane_polygons", "lane_polygons.geojson"),
        )
        return bundle

    def _load_from_legacy_configs(self) -> ScenarioBundle:
        """Constructs a backward-compatible ScenarioBundle from files in configs/."""
        def _read_cfg(name: str) -> Dict[str, Any]:
            p = self.configs_dir / name
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}

        rsus = _read_cfg("road_roadside_units.json")
        spawns = _read_cfg("road_spawn_points.json")
        water = _read_cfg("road_water_sources.json")
        segments = _read_cfg("road_segments.geojson")
        curves = _read_cfg("road_curves.geojson")
        global_cfg = _read_cfg("global_config.json")

        infra = {
            "manifest_version": "1.0.0-fallback",
            "roadside_units": rsus,
            "spawn_points": spawns,
            "water_sources": water,
        }

        return ScenarioBundle(
            scenario_id="a14_corridor_legacy",
            name="Dresden–Leipzig A14 Corridor",
            version="1.0.0-legacy",
            description="Loaded dynamically from legacy configs/ directory",
            coordinate_system={"mode": "WGS84", "crs_epsg": 4326, "origin_gps": [13.736757, 51.063404]},
            environment=global_cfg.get("Weather", {}),
            simulation=global_cfg.get("Simulation", {}),
            bundle_dir=self.configs_dir,
            infrastructure=infra,
            road_segments=segments,
            road_curves=curves,
        )


# Global singleton scenario loader
_global_scenario_loader = ScenarioLoader()
_active_scenario_bundle: Optional[ScenarioBundle] = None


def get_scenario_loader() -> ScenarioLoader:
    """Return the global singleton `ScenarioLoader` instance."""
    return _global_scenario_loader


def get_active_scenario(scenario_id: Optional[str] = None) -> ScenarioBundle:
    """Return the active `ScenarioBundle`, loading `scenario_id` (default `'a14_corridor'`) if needed."""
    global _active_scenario_bundle
    if scenario_id is None:
        if _active_scenario_bundle is None:
            _active_scenario_bundle = get_scenario_loader().load("a14_corridor")
        return _active_scenario_bundle
    if _active_scenario_bundle is None or _active_scenario_bundle.scenario_id != scenario_id:
        _active_scenario_bundle = get_scenario_loader().load(scenario_id)
    return _active_scenario_bundle


def set_active_scenario(scenario_id_or_bundle: str | ScenarioBundle) -> ScenarioBundle:
    """Switch the active global scenario bundle by ID or preloaded `ScenarioBundle`."""
    global _active_scenario_bundle
    if isinstance(scenario_id_or_bundle, ScenarioBundle):
        _active_scenario_bundle = scenario_id_or_bundle
    else:
        _active_scenario_bundle = get_scenario_loader().load(scenario_id_or_bundle)
    return _active_scenario_bundle
