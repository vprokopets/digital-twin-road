"""
SimPLs/engine_contract.py — Model Engine Strategy & External Solver Sidecar Bridge
==================================================================================

Defines a decoupled, batch-step simulation contract (`BaseModelEngine`) so the
default Pure-Python Hybrid Petri Net / FEM pipeline (`PythonLocalEngine`) can
be swapped at runtime for an external HTTP solver sidecar
(`HttpExternalEngine` via `EXTERNAL_SOLVER_URL`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
import logging
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from SimPLs.temp_deform.deform import DeformationSim
from SimPLs.temp_deform.temp import TemperatureSim

_DEFAULT_PAVEMENT_LAYERS: Dict[str, Any] = {
    "Layer_0": {"ThermalConductivity": 1.5, "Length": 0.04, "CorrespondingStiffness": 37.5},
    "Layer_1": {"ThermalConductivity": 1.6, "Length": 0.08, "CorrespondingStiffness": 20.0},
    "Layer_2": {"ThermalConductivity": 1.45, "Length": 0.22, "CorrespondingStiffness": 6.5909},
    "Layer_3": {"ThermalConductivity": 2.0, "Length": 0.36, "CorrespondingStiffness": 5.5556},
}


def sanitize_json_payload(obj: Any) -> Any:
    """Recursively replace non-finite floats (`NaN`, `Inf`, `-Inf`) with `None` for strict JSON."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanitize_json_payload(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_json_payload(v) for v in obj]
    if isinstance(obj, tuple):
        return [sanitize_json_payload(v) for v in obj]
    return obj


@dataclass
class EntityObservation:
    """Normalized physical observation bundle for a single tracked simulation entity."""

    entity_id: str
    entity_type: str = "vehicle"
    station_km: float = 0.0
    direction: int = 1
    velocity_kmh: float = 0.0
    weight_kg: float = 40000.0
    road_material: str = "Asphalt"
    weather_state: str = "Sunny"
    air_temp_c: float = 22.0
    surface_temp_c: float = 26.0
    soil_temp_c: float = 14.5
    serving_rsu_id: Optional[str] = None
    segment_id: Optional[str] = None
    rsu_distance_km: Optional[float] = None
    state_vector: List[float] = field(default_factory=list)
    sensor_frame: Optional[Dict[str, Any]] = None
    pavement_layers: Optional[Dict[str, Any]] = None
    axle_loads_kn: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the observation into a strict JSON-safe dictionary."""
        return sanitize_json_payload(asdict(self))


@dataclass
class ModelIntrospection:
    """Language- and paradigm-agnostic solver introspection payload for UI inspection."""

    engine: str = "python-hpn"
    source_language: str = "python"
    active_contexts: List[str] = field(default_factory=list)
    dispatch_signature: Optional[str] = None
    constraints: List[str] = field(default_factory=list)
    control_petri_net: Optional[Dict[str, Any]] = None
    code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes introspection metadata into a strict JSON-safe dictionary."""
        return sanitize_json_payload(asdict(self))


@dataclass
class EntityStepResult:
    """Per-entity model evaluation output produced by a simulation engine step."""

    entity_id: str
    temperature_profile_c: List[float] = field(default_factory=list)
    damage_increment: float = 0.0
    state_vector: List[float] = field(default_factory=list)
    active_contexts: List[str] = field(default_factory=list)
    solver_mode: str = "POD"
    accuracy: float = 0.99
    introspection: Optional[ModelIntrospection] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes step result fields into a strict JSON-safe dictionary."""
        data = asdict(self)
        if self.introspection is not None:
            data["introspection"] = self.introspection.to_dict()
        return sanitize_json_payload(data)


@dataclass
class StepRequest:
    """Serialized batch-tick input sent once per simulation step to the active engine."""

    sim_time_s: float
    dt_s: float
    coordinate_system: Dict[str, Any]
    entities: List[EntityObservation]
    sensor_frames: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the full batch request with non-finite floats stripped."""
        return sanitize_json_payload({
            "sim_time_s": self.sim_time_s,
            "dt_s": self.dt_s,
            "coordinate_system": self.coordinate_system,
            "entities": [entity.to_dict() for entity in self.entities],
            "sensor_frames": self.sensor_frames,
        })


@dataclass
class StepResponse:
    """Aggregated batch-tick output returned by a local or external model engine."""

    engine: str
    sim_time_s: float
    results: Dict[str, EntityStepResult]
    global_active_contexts: List[str] = field(default_factory=list)
    control_petri_net: Optional[Dict[str, Any]] = None
    compute_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the aggregated batch step response into a JSON-safe dictionary."""
        return sanitize_json_payload({
            "engine": self.engine,
            "sim_time_s": self.sim_time_s,
            "results": {k: v.to_dict() for k, v in self.results.items()},
            "global_active_contexts": self.global_active_contexts,
            "control_petri_net": self.control_petri_net,
            "compute_time_ms": self.compute_time_ms,
        })


class BaseModelEngine(ABC):
    """Abstract strategy interface for pluggable thermal-mechanical simulation engines."""

    engine_name: str = "base"

    @abstractmethod
    def is_healthy(self) -> bool:
        """Returns whether the model engine is reachable and ready to evaluate steps."""

    @abstractmethod
    def evaluate_batch(self, req: StepRequest) -> StepResponse:
        """Evaluates all entities and sensor frames for a single simulation step."""

    def status(self) -> Dict[str, Any]:
        """Returns runtime status metadata exposed via `GET /api/engine/status`."""
        return {
            "status": "ok",
            "engine": self.engine_name,
            "healthy": self.is_healthy(),
        }


class PythonLocalEngine(BaseModelEngine):
    """Default in-process Python solver wrapping `TemperatureSim` and `DeformationSim`."""

    engine_name: str = "python-hpn"

    def __init__(self) -> None:
        self._temp_sim = TemperatureSim()
        self._deform_sim = DeformationSim()

    def is_healthy(self) -> bool:
        """Always returns True for the built-in local Python solver."""
        return True

    def evaluate_batch(self, req: StepRequest) -> StepResponse:
        """Evaluates all entities in `req` using local 1D thermal FEM and surface wear."""
        t0 = time.perf_counter()
        results: Dict[str, EntityStepResult] = {}

        for obs in req.entities:
            layers = obs.pavement_layers if (obs.pavement_layers and any("Layer" in k for k in obs.pavement_layers)) else _DEFAULT_PAVEMENT_LAYERS
            synth_md = {
                "Weight": obs.weight_kg,
                "State": {
                    "WeatherState": obs.weather_state,
                    "AirTemperature": obs.air_temp_c,
                    "RoadSurfaceTemperature": obs.surface_temp_c,
                    "SoilTemperature": obs.soil_temp_c,
                    "RoadMetadata": layers,
                },
            }
            temp_displ = self._temp_sim.temperature_simulation(synth_md)
            damage = self._deform_sim.damage_estimation(synth_md, temp_displ)
            contexts = [c for c in (obs.road_material, obs.weather_state) if c]
            results[obs.entity_id] = EntityStepResult(
                entity_id=obs.entity_id,
                temperature_profile_c=list(temp_displ),
                damage_increment=float(damage),
                state_vector=list(temp_displ),
                active_contexts=contexts,
                solver_mode="POD",
                accuracy=0.99,
                introspection=ModelIntrospection(
                    engine=self.engine_name,
                    source_language="python",
                    active_contexts=contexts,
                ),
            )

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return StepResponse(
            engine=self.engine_name,
            sim_time_s=req.sim_time_s,
            results=results,
            compute_time_ms=elapsed_ms,
        )


class HttpExternalEngine(BaseModelEngine):
    """
    HTTP sidecar client for external simulation solvers.

    Serializes `/step` calls behind a threading lock so stateful single-process
    workers never experience concurrent mutations to global context sets or
    control structures.
    """

    engine_name: str = "external-http"

    def __init__(
        self,
        base_url: str,
        timeout_s: float = 2.0,
        fallback: Optional[BaseModelEngine] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = float(timeout_s)
        self.fallback = fallback
        self._lock = threading.Lock()

    def is_healthy(self) -> bool:
        """Checks `GET {base_url}/health` on the external solver sidecar."""
        try:
            resp = requests.get(
                f"{self.base_url}/health",
                timeout=min(1.0, self.timeout_s),
            )
            return resp.status_code == 200
        except Exception as exc:
            logging.debug("External engine health check failed for %s: %s", self.base_url, exc)
            return False

    def status(self) -> Dict[str, Any]:
        """Returns external sidecar connection status alongside fallback info."""
        info = super().status()
        info["base_url"] = self.base_url
        info["has_fallback"] = self.fallback is not None
        return info

    def evaluate_batch(self, req: StepRequest) -> StepResponse:
        """
        Posts a serialized batch tick to `POST {base_url}/step`.

        Falls back gracefully to `self.fallback` if the sidecar is unavailable or returns
        a non-200 response.
        """
        payload = req.to_dict()
        t0 = time.perf_counter()
        try:
            with self._lock:
                resp = requests.post(
                    f"{self.base_url}/step",
                    json=payload,
                    timeout=self.timeout_s,
                )
            if resp.status_code != 200:
                raise RuntimeError(f"External solver returned HTTP {resp.status_code}")

            raw = resp.json()
            parsed_results: Dict[str, EntityStepResult] = {}
            raw_results = raw.get("results", {})
            for eid, item in raw_results.items():
                if not isinstance(item, dict):
                    continue
                intro_raw = item.get("introspection")
                intro_obj: Optional[ModelIntrospection] = None
                if isinstance(intro_raw, dict):
                    intro_obj = ModelIntrospection(
                        engine=str(intro_raw.get("engine", raw.get("engine", self.engine_name))),
                        source_language=str(intro_raw.get("source_language", "julia")),
                        active_contexts=list(intro_raw.get("active_contexts", item.get("active_contexts", []))),
                        dispatch_signature=intro_raw.get("dispatch_signature"),
                        constraints=list(intro_raw.get("constraints", [])),
                        control_petri_net=intro_raw.get("control_petri_net"),
                        code=intro_raw.get("code"),
                    )

                parsed_results[str(eid)] = EntityStepResult(
                    entity_id=str(item.get("entity_id", eid)),
                    temperature_profile_c=[float(v) for v in item.get("temperature_profile_c", [])],
                    damage_increment=float(item.get("damage_increment", 0.0)),
                    state_vector=[float(v) for v in item.get("state_vector", [])],
                    active_contexts=[str(c) for c in item.get("active_contexts", [])],
                    solver_mode=str(item.get("solver_mode", "COP")),
                    accuracy=float(item.get("accuracy", 0.99)),
                    introspection=intro_obj,
                )

            elapsed_ms = float(raw.get("compute_time_ms") or round((time.perf_counter() - t0) * 1000.0, 3))
            return StepResponse(
                engine=str(raw.get("engine", self.engine_name)),
                sim_time_s=float(raw.get("sim_time_s", req.sim_time_s)),
                results=parsed_results,
                global_active_contexts=[str(c) for c in raw.get("global_active_contexts", [])],
                control_petri_net=raw.get("control_petri_net"),
                compute_time_ms=elapsed_ms,
            )
        except Exception as exc:
            logging.debug("External engine step failed (%s); checking fallback.", exc)
            if self.fallback is not None:
                return self.fallback.evaluate_batch(req)
            raise


_model_engine: Optional[BaseModelEngine] = None
_engine_lock = threading.Lock()


def get_model_engine() -> BaseModelEngine:
    """Returns the process-wide simulation model engine (configured lazily via `EXTERNAL_SOLVER_URL`)."""
    global _model_engine
    with _engine_lock:
        if _model_engine is None:
            external_url = os.getenv("EXTERNAL_SOLVER_URL", "").strip()
            if external_url:
                timeout_raw = os.getenv("EXTERNAL_SOLVER_TIMEOUT_S", "2.0")
                try:
                    timeout_s = float(timeout_raw)
                except ValueError:
                    timeout_s = 2.0
                _model_engine = HttpExternalEngine(
                    base_url=external_url,
                    timeout_s=timeout_s,
                    fallback=PythonLocalEngine(),
                )
            else:
                _model_engine = PythonLocalEngine()
        return _model_engine


def set_model_engine(engine: Optional[BaseModelEngine]) -> None:
    """Overrides (or clears when `None`) the active simulation model engine."""
    global _model_engine
    with _engine_lock:
        _model_engine = engine


__all__ = [
    "BaseModelEngine",
    "EntityObservation",
    "EntityStepResult",
    "HttpExternalEngine",
    "ModelIntrospection",
    "PythonLocalEngine",
    "StepRequest",
    "StepResponse",
    "get_model_engine",
    "sanitize_json_payload",
    "set_model_engine",
]
