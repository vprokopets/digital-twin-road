"""
hpn.py — Pure-Python Compositional Hybrid Petri Nets (HPN) with HERAKLIT Algebra
================================================================================

Project: Digital Twin Road Demonstrator

Overview for Successor / Maintainer
-----------------------------------
This module implements a pure-Python **Hybrid Petri Net (HPN)** runtime coupled with:
1. **FODA Feature Variability (`fm.py`)**: Discrete places ($P_d$) correspond 1-to-1 with
   active features in the FODA feature tree (`Road Material`, `Weather State`, `Mechanical Model`).
2. **Mixin-Based Dynamic Code Synthesis**: Continuous transition firing rates ($v_c(t)$)
   are parameterized directly by the synthesized Python Mixin class (`AsphaltMixin`,
   `ConcreteMixin`, `SunnyMixin`, etc.).
3. **Wolfgang Reisig's HERAKLIT Composition Algebra**:
   Every subsystem (RSU Edge Node, Weather Feature, Pavement Material Feature, Fast/Slow
   Mechanical Solver) is modeled as an algebraic **Heraklit Module**:
       M = (alpha(M), N(M), beta(M))
   where:
     - `alpha(M)` (Left Gate / Imported Interface): Labeled places/transitions receiving
       tokens or continuous flows from upstream modules.
     - `N(M)` (Interior): Internal discrete places ($P_d$), continuous places ($P_c$),
       discrete guarded transitions ($T_d$), and continuous fluid transitions ($T_c$).
     - `beta(M)` (Right Gate / Exported Interface): Labeled places/transitions exposed
       to downstream modules.
   The **Heraklit Composition Operator** (`M1.compose(M2)` or `M1 @ M2`) fuses matching
   interface labels in `beta(M1) ∩ alpha(M2)` into shared boundary places and synchronized
   transitions, satisfying associativity: `(M1 • M2) • M3 == M1 • (M2 • M3)`.

Note on External Solvers
------------------------
This engine runs 100% in pure Python with zero external solver dependencies.
To integrate external runtime solvers in the future, `HeraklitHPNController.to_dict()`
serializes the discrete marking $M_d$ and continuous state $M_c$ into JSON.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
from typing import Dict, List, Optional, Any, Tuple
import random


# ============================================================================
# 1. Core Hybrid Petri Net Primitives (Places, Transitions, Arcs)
# ============================================================================

@dataclass
class HPNPlace:
    r"""
    Represents a Place in a Hybrid Petri Net.

    - kind == 'discrete'  ($P_d$): Holds integer tokens $m \in \{0, 1, \dots\}$.
    - kind == 'continuous' ($P_c$): Holds a non-negative or signed real fluid level $x \in \mathbb{R}$.
    - gate: 'alpha' (left entry interface), 'beta' (right exit interface),
      'fused' (shared boundary place after Heraklit composition), or 'internal'.
    """
    id: str
    label: str
    kind: str = "discrete"          # 'discrete' | 'continuous'
    module: str = "M_Core"          # Owning Heraklit module name
    gate: str = "internal"          # 'alpha' | 'internal' | 'beta' | 'fused'
    interface_tag: Optional[str] = None  # Tag used for Heraklit fusion: beta(M1) ∩ alpha(M2)
    tokens: float = 0.0             # Integer token count (if discrete) or fluid level (if continuous)
    unit: str = ""
    foda_feature: Optional[str] = None


@dataclass
class HPNTransition:
    """
    Represents a Transition in a Hybrid Petri Net.

    - kind == 'discrete' ($T_d$): Fires instantaneously when input places hold tokens and ``guard_expr`` holds.
    - kind == 'continuous' ($T_c$): Fires continuously at fluid rate ``rate`` ($dx/dt = v(t)$).
    """
    id: str
    label: str
    kind: str = "discrete"          # 'discrete' | 'continuous'
    module: str = "M_Core"
    gate: str = "internal"          # 'alpha' | 'internal' | 'beta' | 'fused'
    interface_tag: Optional[str] = None
    guard_label: str = ""
    rate: float = 0.0               # Firing rate for continuous transitions
    enabled: bool = False
    last_fired: bool = False


@dataclass
class HPNArc:
    """
    Directed arc connecting a Place -> Transition or Transition -> Place.

    Attributes:
        arc_type: Flow semantics — ``'normal'`` (standard token/fluid flow),
            ``'test'`` (read/enabling arc without consuming tokens),
            ``'inhibitor'`` (inhibits transition above threshold),
            ``'reset'`` (resets continuous place to 0.0 when discrete transition fires), or
            ``'fusion'`` (Heraklit interface fusion link between composed modules).
    """
    source: str
    target: str
    arc_type: str = "normal"        # 'normal' | 'test' | 'inhibitor' | 'reset' | 'fusion'
    weight: float = 1.0
    label: str = ""


# ============================================================================
# 2. Heraklit Algebraic Module M = (alpha(M), N(M), beta(M))
# ============================================================================

@dataclass
class HeraklitModule:
    """
    Composable Hybrid Petri Net module in the sense of Wolfgang Reisig's HERAKLIT.

    Supports the algebraic composition operator ``M1 @ M2`` (``compose``).
    """
    name: str
    title: str
    time_scale: str = "fast"        # 'slow' (RSU / Environment) | 'fast' (Vehicle / Mechanics)
    places: Dict[str, HPNPlace] = field(default_factory=dict)
    transitions: Dict[str, HPNTransition] = field(default_factory=dict)
    arcs: List[HPNArc] = field(default_factory=list)
    composed_from: List[str] = field(default_factory=list)

    @property
    def alpha_interface(self) -> Dict[str, str]:
        """Returns mapping {interface_tag: place_or_transition_id} for the Left Interface alpha(M)."""
        res: Dict[str, str] = {}
        for pid, p in self.places.items():
            if p.gate in ("alpha", "fused") and p.interface_tag:
                res[p.interface_tag] = pid
        for tid, t in self.transitions.items():
            if t.gate in ("alpha", "fused") and t.interface_tag:
                res[t.interface_tag] = tid
        return res

    @property
    def beta_interface(self) -> Dict[str, str]:
        """Returns mapping {interface_tag: place_or_transition_id} for the Right Interface beta(M)."""
        res: Dict[str, str] = {}
        for pid, p in self.places.items():
            if p.gate in ("beta", "fused") and p.interface_tag:
                res[p.interface_tag] = pid
        for tid, t in self.transitions.items():
            if t.gate in ("beta", "fused") and t.interface_tag:
                res[t.interface_tag] = tid
        return res

    def compose(self, other: "HeraklitModule") -> "HeraklitModule":
        """
        Compute Heraklit Composition ``M_composed = self • other``.

        Fuses matching interface tags in ``beta(self) ∩ alpha(other)``:
        if both are places with the same ``interface_tag``, they are merged into a
        single shared boundary place (``gate='fused'``), redirecting all incoming
        and outgoing arcs in ``other`` to the fused place in ``self``.
        """
        composed_name = f"{self.name} • {other.name}"
        composed_title = f"{self.title} • {other.title}"
        merged_places: Dict[str, HPNPlace] = {k: HPNPlace(**vars(v)) for k, v in self.places.items()}
        merged_transitions: Dict[str, HPNTransition] = {k: HPNTransition(**vars(v)) for k, v in self.transitions.items()}
        merged_arcs: List[HPNArc] = [HPNArc(**vars(a)) for a in self.arcs]

        beta_map = self.beta_interface
        id_remap: Dict[str, str] = {}

        # 1. Fuse matching places in beta(self) ∩ alpha(other)
        for pid, p in other.places.items():
            if p.gate == "alpha" and p.interface_tag and p.interface_tag in beta_map:
                target_pid = beta_map[p.interface_tag]
                if target_pid in merged_places:
                    merged_places[target_pid].gate = "fused"
                    id_remap[pid] = target_pid
                    continue
            merged_places[pid] = HPNPlace(**vars(p))

        # 2. Fuse matching transitions in beta(self) ∩ alpha(other)
        for tid, t in other.transitions.items():
            if t.gate == "alpha" and t.interface_tag and t.interface_tag in beta_map:
                target_tid = beta_map[t.interface_tag]
                if target_tid in merged_transitions:
                    merged_transitions[target_tid].gate = "fused"
                    id_remap[tid] = target_tid
                    continue
            merged_transitions[tid] = HPNTransition(**vars(t))

        # 3. Copy arcs from `other`, remapping fused interface endpoints
        for a in other.arcs:
            src = id_remap.get(a.source, a.source)
            dst = id_remap.get(a.target, a.target)
            arc_type = "fusion" if (a.source in id_remap or a.target in id_remap) else a.arc_type
            merged_arcs.append(HPNArc(source=src, target=dst, arc_type=arc_type, weight=a.weight, label=a.label))

        sub_modules = (self.composed_from or [self.name]) + (other.composed_from or [other.name])
        return HeraklitModule(
            name=composed_name,
            title=composed_title,
            time_scale="multi-scale" if self.time_scale != other.time_scale else self.time_scale,
            places=merged_places,
            transitions=merged_transitions,
            arcs=merged_arcs,
            composed_from=sub_modules,
        )

    def __matmul__(self, other: "HeraklitModule") -> "HeraklitModule":
        """Overloads `M1 @ M2` as Pythonic syntax for Heraklit composition `M1 • M2`."""
        return self.compose(other)


# ============================================================================
# 3. Elementary Heraklit Module Builders (RSU, Weather, Material, Solver)
# ============================================================================

def build_rsu_env_module(
    rsu_id: str = "rsu_00",
    weather_state: str = "Sunny",
    air_temp: float = 24.0,
    road_temp: float = 28.5,
    soil_temp: float = 14.5,
) -> HeraklitModule:
    """
    Construct the slow-scale Roadside Unit Environmental Module ``M_RSU``.

    Exports environmental boundary conditions via its right gate ``beta(M_RSU)``.
    """
    m = HeraklitModule(name=f"M_RSU[{rsu_id}]", title=f"RSU Edge Module ({rsu_id})", time_scale="slow")

    # Discrete Weather State Places (Markov / Real-Time Pi)
    for w in ["Sunny", "Cloudy", "Rainy", "Snowy"]:
        m.places[f"P_{w}"] = HPNPlace(
            id=f"P_{w}",
            label=f"Weather: {w}",
            kind="discrete",
            module="M_RSU",
            gate="beta" if w == weather_state else "internal",
            interface_tag=f"IF_Weather_{w}",
            tokens=1.0 if w == weather_state else 0.0,
            foda_feature=w,
        )

    # Continuous Environmental Boundary Places (Exported via beta gate to Vehicle)
    m.places["Pc_AirTemp"] = HPNPlace(
        id="Pc_AirTemp",
        label="T_air (RSU)",
        kind="continuous",
        module="M_RSU",
        gate="beta",
        interface_tag="IF_AirTemp",
        tokens=round(air_temp, 2),
        unit="°C",
    )
    m.places["Pc_SoilTemp"] = HPNPlace(
        id="Pc_SoilTemp",
        label="T_soil (Hydro)",
        kind="continuous",
        module="M_RSU",
        gate="beta",
        interface_tag="IF_SoilTemp",
        tokens=round(soil_temp, 2),
        unit="°C",
    )

    # Slow-scale environmental transition
    m.transitions["Tc_EnvSync"] = HPNTransition(
        id="Tc_EnvSync",
        label="Tc_SlowEnvBroadcast",
        kind="continuous",
        module="M_RSU",
        gate="beta",
        interface_tag="IF_EnvSync",
        guard_label="Δt_slow = 5.0s",
        rate=round((road_temp - soil_temp) / 5.0, 2),
        enabled=True,
    )

    active_w_pid = f"P_{weather_state}" if f"P_{weather_state}" in m.places else "P_Sunny"
    m.arcs.extend([
        HPNArc(source=active_w_pid, target="Tc_EnvSync", arc_type="test", label="Markov State"),
        HPNArc(source="Tc_EnvSync", target="Pc_AirTemp", arc_type="normal"),
        HPNArc(source="Tc_EnvSync", target="Pc_SoilTemp", arc_type="normal"),
    ])
    return m


def build_material_thermal_module(
    road_material: str = "Asphalt",
    surface_temp: float = 28.5,
    solar_flux: float = 800.0,
    albedo: float = 0.15,
    conductivity: float = 1.5,
) -> HeraklitModule:
    """
    Construct the Pavement Material & 1D Thermal Conduction Module ``M_Material``.

    Imports ``IF_AirTemp`` and ``IF_SoilTemp`` on its Left Gate ``alpha(M_Material)``
    and exports ``IF_SurfaceTemp`` and ``IF_StiffnessFactor`` on ``beta(M_Material)``.
    """
    m = HeraklitModule(name="M_Material", title="Pavement Material & Thermal Module", time_scale="slow")

    # Left Gate (Imported from M_RSU)
    m.places["Alpha_AirTemp"] = HPNPlace(
        id="Alpha_AirTemp",
        label="T_air (In)",
        kind="continuous",
        module="M_Material",
        gate="alpha",
        interface_tag="IF_AirTemp",
        tokens=round(surface_temp - 3.0, 2),
        unit="°C",
    )
    m.places["Alpha_SoilTemp"] = HPNPlace(
        id="Alpha_SoilTemp",
        label="T_soil (In)",
        kind="continuous",
        module="M_Material",
        gate="alpha",
        interface_tag="IF_SoilTemp",
        tokens=14.5,
        unit="°C",
    )

    # Discrete Material Places (FODA XOR: Asphalt vs Concrete)
    for mat in ["Asphalt", "Concrete"]:
        m.places[f"P_{mat}"] = HPNPlace(
            id=f"P_{mat}",
            label=f"Material: {mat}",
            kind="discrete",
            module="M_Material",
            gate="internal",
            tokens=1.0 if mat == road_material else 0.0,
            foda_feature=mat,
        )

    # Continuous Heat Flux Transition (Rate governed by Mixin!)
    net_solar_rate = round((1.0 - albedo) * solar_flux / 100.0, 2)
    m.transitions["Tc_HeatBalance"] = HPNTransition(
        id="Tc_HeatBalance",
        label="Tc_1D_ThermalFlux",
        kind="continuous",
        module="M_Material",
        gate="internal",
        guard_label=f"k={conductivity} W/mK, α={albedo}",
        rate=net_solar_rate,
        enabled=True,
    )

    # Right Gate: Continuous Surface Temperature exported to Fast Mechanical Solver
    m.places["Pc_SurfaceTemp"] = HPNPlace(
        id="Pc_SurfaceTemp",
        label="T_surface (0cm)",
        kind="continuous",
        module="M_Material",
        gate="beta",
        interface_tag="IF_SurfaceTemp",
        tokens=round(surface_temp, 2),
        unit="°C",
    )

    active_mat_pid = f"P_{road_material}" if f"P_{road_material}" in m.places else "P_Asphalt"
    m.arcs.extend([
        HPNArc(source="Alpha_AirTemp", target="Tc_HeatBalance", arc_type="normal"),
        HPNArc(source="Alpha_SoilTemp", target="Tc_HeatBalance", arc_type="normal"),
        HPNArc(source=active_mat_pid, target="Tc_HeatBalance", arc_type="test", label="Mixin Rate"),
        HPNArc(source="Tc_HeatBalance", target="Pc_SurfaceTemp", arc_type="normal"),
    ])
    return m


def build_vehicle_solver_module(
    solver_mode: str = "POD",
    accuracy: float = 0.96,
    threshold: float = 0.90,
    velocity_kmh: float = 90.0,
    weight_kg: float = 35000.0,
    damage_increment: float = 0.05,
    just_switched: Optional[str] = None,
) -> HeraklitModule:
    """
    Construct the Fast-Scale Vehicle Mechanical & Solver Fidelity Module ``M_Vehicle``.

    Imports ``IF_SurfaceTemp`` via ``alpha(M_Vehicle)`` and manages the guarded discrete
    switching between the fast Reduced-Order Model (``POD``) and Full-Order Model (``FEM``).
    """
    m = HeraklitModule(name="M_Vehicle", title="Fast Vehicle & POD/FEM Solver Module", time_scale="fast")

    # Left Gate: Imported Surface Temperature from M_Material
    m.places["Alpha_SurfaceTemp"] = HPNPlace(
        id="Alpha_SurfaceTemp",
        label="T_surface (In)",
        kind="continuous",
        module="M_Vehicle",
        gate="alpha",
        interface_tag="IF_SurfaceTemp",
        tokens=28.5,
        unit="°C",
    )

    is_pod = solver_mode in ("POD", "MOR")
    pod_error = max(0.0, round(1.0 - accuracy, 4))
    max_error_guard = round(1.0 - threshold, 2)

    # Discrete Solver Places (FODA: POD vs FEM)
    m.places["P_POD"] = HPNPlace(
        id="P_POD",
        label="Solver: POD (Fast ROM)",
        kind="discrete",
        module="M_Vehicle",
        gate="internal",
        tokens=1.0 if is_pod else 0.0,
        foda_feature="POD",
    )
    m.places["P_FEM"] = HPNPlace(
        id="P_FEM",
        label="Solver: FEM (Exact FOM)",
        kind="discrete",
        module="M_Vehicle",
        gate="internal",
        tokens=0.0 if is_pod else 1.0,
        foda_feature="FEM",
    )

    # Continuous Place: Accumulated POD Projection Residual Error
    m.places["Pc_PODError"] = HPNPlace(
        id="Pc_PODError",
        label="POD Drift Error",
        kind="continuous",
        module="M_Vehicle",
        gate="internal",
        tokens=pod_error,
        unit="err",
    )

    # Right Gate: Exported Damage Increment & Telemetry back to RSU/Road
    m.places["Pc_DamageOut"] = HPNPlace(
        id="Pc_DamageOut",
        label="ΔDamage (Out)",
        kind="continuous",
        module="M_Vehicle",
        gate="beta",
        interface_tag="IF_RoadDamage",
        tokens=round(damage_increment, 4),
        unit="idx",
    )

    # Fast Continuous Load & Error Accumulation Transition
    m.transitions["Tc_FastLoadStep"] = HPNTransition(
        id="Tc_FastLoadStep",
        label="Tc_TireContactLoad",
        kind="continuous",
        module="M_Vehicle",
        gate="internal",
        guard_label=f"v={velocity_kmh:.0f} km/h, F={weight_kg/1000:.1f}t",
        rate=round(velocity_kmh / 3600.0, 4),
        enabled=True,
    )

    # Guarded Discrete Transition: Switch POD -> FEM when error >= 1 - threshold
    m.transitions["Td_SwitchToFEM"] = HPNTransition(
        id="Td_SwitchToFEM",
        label="Td_TriggerFEM",
        kind="discrete",
        module="M_Vehicle",
        gate="internal",
        guard_label=f"Guard: err >= {max_error_guard:.2f}",
        enabled=is_pod and (pod_error >= max_error_guard),
        last_fired=(just_switched == "TO_FEM"),
    )

    # Guarded Discrete Transition: Basis Recalibration FEM -> POD (with Reset Arc on Pc_PODError)
    m.transitions["Td_RecalibratePOD"] = HPNTransition(
        id="Td_RecalibratePOD",
        label="Td_BasisRecalibrate",
        kind="discrete",
        module="M_Vehicle",
        gate="beta",
        interface_tag="IF_BasisSync",
        guard_label="Guard: Basis Sync Complete",
        enabled=(not is_pod) and (accuracy >= 1.0),
        last_fired=(just_switched == "TO_POD"),
    )

    m.arcs.extend([
        HPNArc(source="Alpha_SurfaceTemp", target="Tc_FastLoadStep", arc_type="normal"),
        HPNArc(source="P_POD" if is_pod else "P_FEM", target="Tc_FastLoadStep", arc_type="test", label="Active Solver"),
        HPNArc(source="Tc_FastLoadStep", target="Pc_PODError", arc_type="normal"),
        HPNArc(source="Tc_FastLoadStep", target="Pc_DamageOut", arc_type="normal"),
        # POD -> FEM Guarded Switch
        HPNArc(source="P_POD", target="Td_SwitchToFEM", arc_type="normal"),
        HPNArc(source="Pc_PODError", target="Td_SwitchToFEM", arc_type="test", label=f"err≥{max_error_guard}"),
        HPNArc(source="Td_SwitchToFEM", target="P_FEM", arc_type="normal"),
        # FEM -> POD Basis Recalibration + Reset Arc
        HPNArc(source="P_FEM", target="Td_RecalibratePOD", arc_type="normal"),
        HPNArc(source="Td_RecalibratePOD", target="P_POD", arc_type="normal"),
        HPNArc(source="Td_RecalibratePOD", target="Pc_PODError", arc_type="reset", label="Reset err:=0"),
    ])
    return m


# ============================================================================
# 4. Stateful Vehicle HPN Controller (Coupled to FODA & Mixins)
# ============================================================================

class HeraklitHPNController:
    """
    Per-vehicle (or per-segment) Hybrid Petri Net controller coupled to FODA & Mixins.

    1. Steps continuous places (surface temperature, POD drift residual, cumulative damage)
       using rates supplied by the dynamically composed Mixin class from ``fm.py``.
    2. Evaluates and fires guarded discrete transitions (``Td_SwitchToFEM``, ``Td_RecalibratePOD``),
       automatically synchronizing the FODA feature tree (``THERMAL_ROAD_MODEL``).
    3. Composes the full Heraklit module chain ``M_Federated = M_RSU[rsu_id] • M_Material • M_Vehicle``
       and exports both the interactive Vue Flow graph and readable Python Heraklit code.
    """

    def __init__(self) -> None:
        self.step_count: int = 0
        self.last_fired_transition: Optional[str] = None
        self.transition_history: List[Dict[str, Any]] = []
        self.composed_module: Optional[HeraklitModule] = None

    def step(
        self,
        rsu_id: str,
        weather_state: str,
        road_material: str,
        air_temp: float,
        road_temp: float,
        soil_temp: float,
        velocity_kmh: float,
        weight_kg: float,
        mechanical_simulation: Dict[str, Any],
        composed_mixin_instance: Any = None,
        damage_increment: float = 0.05,
    ) -> Tuple[str, float, Optional[str]]:
        """
        Execute one Hybrid Petri Net step (continuous ODE evolution and discrete transitions).

        Returns:
            Tuple ``(active_foda_solver_feature, updated_accuracy, fired_transition_id)``.
        """
        self.step_count += 1
        just_switched: Optional[str] = None

        # Extract physical parameters from composed Mixin instance if available
        solar_flux = 800.0
        albedo = 0.15 if road_material == "Asphalt" else 0.35
        conductivity = 1.5 if road_material == "Asphalt" else 1.8

        if composed_mixin_instance is not None:
            try:
                solar_flux = float(composed_mixin_instance.get_solar_radiation())
                albedo = float(composed_mixin_instance.get_albedo())
                conductivity = float(composed_mixin_instance.get_thermal_conductivity())
            except Exception as exc:
                logging.debug("Falling back to default thermal constants in HPN step: %s", exc)

        current_model = mechanical_simulation.get("Model", "POD")
        accuracy = float(mechanical_simulation.get("Accuracy", 1.0))
        threshold = float(mechanical_simulation.get("Threshold", 0.90))

        # 1. Continuous Transition: POD Projection Drift Rate (faster under heavy load & high temp gradient)
        temp_gradient_factor = 1.0 + abs(road_temp - soil_temp) / 40.0
        load_factor = weight_kg / 35000.0
        if current_model == "POD":
            # Continuous drift accumulation on Pc_PODError
            if random.random() > 0.35:
                drift_step = (0.004 + random.random() * 0.008) * temp_gradient_factor * load_factor
                accuracy = max(0.80, accuracy - drift_step)
        else:
            # In FEM (Full-Order) mode, basis recalibration restores accuracy
            accuracy = min(1.01, accuracy + 0.015)

        # 2. Evaluate Guarded Discrete Transitions
        foda_solver_feature = "POD" if current_model == "POD" else "FEM"

        if current_model == "POD" and accuracy <= threshold:
            # Fire Td_SwitchToFEM!
            current_model = "FOM"
            foda_solver_feature = "FEM"
            just_switched = "TO_FEM"
            self.last_fired_transition = "Td_SwitchToFEM (POD → FEM)"
            self.transition_history.append({
                "step": self.step_count,
                "transition": "Td_SwitchToFEM",
                "reason": f"POD accuracy {accuracy:.3f} <= SLA threshold {threshold:.2f}",
                "new_mode": "FEM",
            })
        elif current_model == "FOM" and accuracy >= 1.0:
            # Fire Td_RecalibratePOD (with Reset Arc on Pc_PODError := 0)!
            accuracy = 1.0
            current_model = "POD"
            foda_solver_feature = "POD"
            just_switched = "TO_POD"
            self.last_fired_transition = "Td_RecalibratePOD (FEM → POD)"
            self.transition_history.append({
                "step": self.step_count,
                "transition": "Td_RecalibratePOD",
                "reason": "Reduced POD basis recalibrated via FOM step (Reset err := 0)",
                "new_mode": "POD",
            })

        # Keep bounded history
        if len(self.transition_history) > 10:
            self.transition_history = self.transition_history[-10:]

        mechanical_simulation["Model"] = current_model
        mechanical_simulation["Accuracy"] = round(accuracy, 4)

        # 3. Perform Heraklit Algebraic Module Composition: M_RSU • M_Material • M_Vehicle
        m_rsu = build_rsu_env_module(
            rsu_id=str(rsu_id or "rsu_00"),
            weather_state=weather_state,
            air_temp=air_temp,
            road_temp=road_temp,
            soil_temp=soil_temp,
        )
        m_mat = build_material_thermal_module(
            road_material=road_material,
            surface_temp=road_temp,
            solar_flux=solar_flux,
            albedo=albedo,
            conductivity=conductivity,
        )
        m_veh = build_vehicle_solver_module(
            solver_mode=foda_solver_feature,
            accuracy=accuracy,
            threshold=threshold,
            velocity_kmh=velocity_kmh,
            weight_kg=weight_kg,
            damage_increment=damage_increment,
            just_switched=just_switched,
        )

        # Associative Heraklit Composition: (M_RSU • M_Material) • M_Vehicle
        self.composed_module = (m_rsu @ m_mat) @ m_veh

        return foda_solver_feature, accuracy, just_switched

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the composed Heraklit HPN into a JSON-ready dictionary.

        Used by frontend Vue Flow rendering (``nodes`` & ``edges``) and optional FIWARE mirroring.
        """
        if self.composed_module is None:
            return {}

        mod = self.composed_module
        places_list = []
        nodes_list = []
        for p in mod.places.values():
            # Only include active weather place + both material & solver places + continuous places
            # so the visual graph stays crisp, uncluttered, and easy to read
            if p.id.startswith("P_") and p.module == "M_RSU" and p.tokens <= 0:
                continue
            p_dict = {
                "id": p.id,
                "node_type": "place",
                "label": p.label,
                "kind": p.kind,
                "module": p.module,
                "gate": p.gate,
                "interface_tag": p.interface_tag,
                "tokens": p.tokens,
                "unit": p.unit,
                "foda_feature": p.foda_feature,
            }
            places_list.append(p_dict)
            nodes_list.append(p_dict)

        valid_node_ids = {p["id"] for p in places_list} | set(mod.transitions.keys())
        transitions_list = []
        for t in mod.transitions.values():
            t_dict = {
                **vars(t),
                "node_type": "transition",
            }
            transitions_list.append(t_dict)
            nodes_list.append(t_dict)

        arcs_list = []
        edges_list = []
        for idx, a in enumerate(mod.arcs):
            if a.source in valid_node_ids and a.target in valid_node_ids:
                a_dict = {
                    **vars(a),
                    "id": f"arc_{idx}_{a.source}_{a.target}",
                    "animated": a.arc_type in ("normal", "fusion"),
                }
                arcs_list.append(a_dict)
                edges_list.append(a_dict)

        active_solver = "FEM" if mod.places.get("P_FEM") and mod.places["P_FEM"].tokens > 0 else "POD"
        structured_modules = [
            {"name": "M_RSU_Env", "label": "RSU Slow Env", "alpha_gates": [], "beta_gates": ["T_air", "T_surf"]},
            {"name": "M_Mat_Thermal", "label": "1D Pavement FEM", "alpha_gates": ["T_air", "T_surf"], "beta_gates": ["T_grad", "E_mod"]},
            {"name": "M_Veh_Solver", "label": "Fast POD/FEM", "alpha_gates": ["T_grad", "E_mod"], "beta_gates": ["D_rut"]},
        ]

        return {
            "composition_formula": mod.name,
            "algebraic_expression": mod.name,
            "active_solver": active_solver,
            "title": mod.title,
            "time_scale": mod.time_scale,
            "modules": structured_modules,
            "step_count": self.step_count,
            "last_fired_transition": self.last_fired_transition,
            "transition_history": self.transition_history,
            "places": places_list,
            "transitions": transitions_list,
            "arcs": arcs_list,
            "nodes": nodes_list,
            "edges": edges_list,
        }

    def generate_heraklit_code_snippet(self, active_features: List[str]) -> str:
        """
        Generate a human-readable Python snippet of the composed Heraklit HPN.

        Shows active module composition and Mixin bindings for the Inspector Code View.
        """
        if self.composed_module is None:
            return "# Heraklit HPN not yet initialized."

        mod = self.composed_module
        discrete_active = [p.id for p in mod.places.values() if p.kind == "discrete" and p.tokens > 0]
        cont_summary = ", ".join(
            f"{p.id}={p.tokens}{p.unit}" for p in mod.places.values() if p.kind == "continuous"
        )
        return (
            f"# ==========================================================================\n"
            f"# HERAKLIT Hybrid Petri Net Composition (Reisig Module Algebra)\n"
            f"# Formula : {mod.name}\n"
            f"# Features: {active_features}\n"
            f"# ==========================================================================\n\n"
            f"class ComposedHeraklitHPN(HeraklitModule):\n"
            f"    \"\"\"Auto-composed multi-scale HPN: Slow RSU Env • Pavement • Fast Vehicle.\"\"\"\n"
            f"    composition_expr = \"{mod.name}\"\n"
            f"    active_discrete_marking = {discrete_active}\n"
            f"    continuous_state = \"{cont_summary}\"\n\n"
            f"    def fire_hybrid_step(self, m_rsu, m_material, m_vehicle):\n"
            f"        # Associative Heraklit composition fusing beta(M_i) ∩ alpha(M_j)\n"
            f"        federated_net = (m_rsu @ m_material) @ m_vehicle\n"
            f"        if federated_net.places['Pc_PODError'].tokens >= 0.10:\n"
            f"            federated_net.fire_discrete('Td_SwitchToFEM')  # Guarded POD -> FEM\n"
            f"        return federated_net\n"
        )
