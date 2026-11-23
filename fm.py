"""
fm.py — Pure Python FODA Feature Model & Dynamic Mixin Class Synthesis
======================================================================

Project: Digital Twin Road Demonstrator

Architecture & Successor Notes
------------------------------
1. **Pure Python FODA Representation (`THERMAL_ROAD_MODEL`)**:
   Models domain variability (`Road Material`, `Weather State`, `Mechanical Model`)
   as a hierarchical dictionary without requiring external UVL/DSL parsers.
2. **Dynamic Mixin Composition (`compose_simulation_class`)**:
   Synthesizes a runtime simulation class combining `ThermalModel` with the active
   material (`AsphaltMixin` | `ConcreteMixin`) and weather (`SunnyMixin` | `CloudyMixin`
   | `RainyMixin` | `SnowyMixin`) mixins.
3. **Coupling with Compositional Hybrid Petri Nets (`hpn.py`)**:
   The active FODA configuration corresponds 1-to-1 with the discrete token marking $M_d$
   of the vehicle's Heraklit Hybrid Petri Net (`HeraklitHPNController`), while the
   synthesized mixin methods provide the continuous flow rates $v_c(t)$ for the HPN's
   continuous transitions.
"""

import copy
import functools
import inspect
import abc
import math
from typing import Dict, Any, List, Optional, Tuple, Type

# -------------------------------- Feature Model Definition --------------------------------
THERMAL_ROAD_MODEL: Dict[str, Any] = {
    "name": "Road Simulation",
    "cardinality": "[1..1]",
    "active": True,
    "features": [
        {
            "name": "Road Material",
            "cardinality": "[1..1]",
            "active": True,
            "features": [
                {
                    "name": "Asphalt",
                    "cardinality": "[0..1]",
                    "active": True,
                },
                {
                    "name": "Concrete",
                    "cardinality": "[0..1]",
                    "active": False,
                },
            ],
        },
        {
            "name": "Weather State",
            "cardinality": "[1..1]",
            "active": True,
            "features": [
                {
                    "name": "Sunny",
                    "cardinality": "[0..1]",
                    "active": True,
                },
                {
                    "name": "Cloudy",
                    "cardinality": "[0..1]",
                    "active": False,
                },
                {
                    "name": "Rainy",
                    "cardinality": "[0..1]",
                    "active": False,
                },
                {
                    "name": "Snowy",
                    "cardinality": "[0..1]",
                    "active": False,
                },
            ],
        },
        {
            "name": "Mechanical Model",
            "cardinality": "[1..1]",
            "active": True,
            "features": [
                {
                    "name": "FEM",
                    "cardinality": "[0..1]",
                    "active": False,
                },
                {
                    "name": "POD",
                    "cardinality": "[0..1]",
                    "active": True,
                },
            ],
        },
        {
            "name": "Pavement Mechanics",
            "cardinality": "[1..1]",
            "active": True,
            "features": [
                {
                    "name": "Boussinesq",
                    "cardinality": "[0..1]",
                    "active": True,
                },
                {
                    "name": "Westergaard",
                    "cardinality": "[0..1]",
                    "active": False,
                },
            ],
        },
    ],
}


# -----------------------------------------------------------------------------
# Structural Variant Discriminator (ETSI ITS-G5 CAM Configuration Token)
# -----------------------------------------------------------------------------
# In cooperative intelligent transport systems (C-ITS, ETSI EN 302 637-2),
# transmitting high-dimensional finite-element meshes or layered pavement cross-
# sections over 5.9 GHz ITS-G5 channels is strictly bandwidth-prohibitive.
#
# To solve this in the Software Product Line (SPL) architecture, vehicles and
# roadside units (RSUs) negotiate a 1-byte integer Structural Variant Discriminator:
#   Token 1 = Asphalt Flexible Pavement  -> Boussinesq elastostatic half-space kernel
#   Token 2 = Concrete Rigid Pavement   -> Westergaard plate on Winkler spring foundation
#
# This configuration token triggers deterministic, microsecond-scale dynamic mixin
# composition at both the vehicle edge and the roadside digital shadow.
# -----------------------------------------------------------------------------
STRUCTURAL_TOKEN_ASPHALT: int = 1
STRUCTURAL_TOKEN_CONCRETE: int = 2


def encode_structural_token(pavement_type: str) -> int:
    """Encode a pavement material name into an ETSI ITS-G5 CAM Structural Variant token."""
    p = pavement_type.strip().lower()
    if "concrete" in p or "beton" in p:
        return STRUCTURAL_TOKEN_CONCRETE
    return STRUCTURAL_TOKEN_ASPHALT


def decode_structural_token(token: int) -> str:
    """Decode an ETSI ITS-G5 CAM integer token into its pavement family name."""
    if token == STRUCTURAL_TOKEN_CONCRETE:
        return "Concrete"
    return "Asphalt"


# --------------------- Helper Functions ---------------------

def clone_feature_model() -> Dict[str, Any]:
    """Returns an independent deep copy of THERMAL_ROAD_MODEL for per-vehicle state isolation."""
    return copy.deepcopy(THERMAL_ROAD_MODEL)


def toggle_feature(feature_model: Dict[str, Any], clicked_feature_id: str) -> Dict[str, Any]:
    """Activate `clicked_feature_id` and deactivate its XOR siblings in `feature_model`."""
    def deactivate_subtree(subtree: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for feat in subtree:
            feat["active"] = False
            if "features" in feat:
                deactivate_subtree(feat["features"])
        return subtree

    def traverse(node: Dict[str, Any]) -> Dict[str, Any]:
        for feature in node.get("features", []):
            if feature["name"] == clicked_feature_id:
                feature["active"] = True
                for sibling in node["features"]:
                    if sibling["name"] != clicked_feature_id:
                        sibling["active"] = False
                        if "features" in sibling:
                            deactivate_subtree(sibling["features"])
            else:
                if "features" in feature:
                    traverse(feature)
        return node

    return traverse(feature_model)


def toggle_feature_global(clicked_feature_id: str) -> Dict[str, Any]:
    """Toggles the global `THERMAL_ROAD_MODEL` (maintained for backwards compatibility)."""
    global THERMAL_ROAD_MODEL
    THERMAL_ROAD_MODEL = toggle_feature(THERMAL_ROAD_MODEL, clicked_feature_id)
    return THERMAL_ROAD_MODEL


def get_active_features(feature_model: Dict[str, Any]) -> List[str]:
    """Returns a list of all currently active feature names in `feature_model`."""
    active_features: List[str] = []

    def traverse(feature: Dict[str, Any]) -> None:
        if feature.get("active"):
            active_features.append(feature["name"])
        for sub_feature in feature.get("features", []):
            traverse(sub_feature)

    traverse(feature_model)
    return active_features


@functools.lru_cache(maxsize=64)
def _compose_cached_class(active_features_tuple: Tuple[str, ...]) -> Optional[Type["ThermalModel"]]:
    mixins = []

    if "Asphalt" in active_features_tuple:
        mixins.append(AsphaltMixin)
    elif "Concrete" in active_features_tuple:
        mixins.append(ConcreteMixin)

    if "Sunny" in active_features_tuple:
        mixins.append(SunnyMixin)
    elif "Cloudy" in active_features_tuple:
        mixins.append(CloudyMixin)
    elif "Rainy" in active_features_tuple:
        mixins.append(RainyMixin)
    elif "Snowy" in active_features_tuple:
        mixins.append(SnowyMixin)

    if "Westergaard" in active_features_tuple or ("Concrete" in active_features_tuple and "Boussinesq" not in active_features_tuple):
        mixins.append(WestergaardMixin)
    else:
        mixins.append(BoussinesqMixin)

    if mixins:
        name = "".join([m.__name__.replace("Mixin", "") for m in mixins]) + "Model"
        SimulationClass = type(name, (*mixins, ThermalModel), {})
        return SimulationClass
    return None


def compose_simulation_class(active_features: List[str]) -> Optional[Type["ThermalModel"]]:
    """Synthesize a `ThermalModel` subclass inheriting active material/weather/mechanics Mixins."""
    return _compose_cached_class(tuple(active_features))


@functools.lru_cache(maxsize=32)
def _get_cached_mixin_source(cls: Type) -> str:
    code = ""
    for base in cls.__bases__:
        if base is not object and base.__name__ not in ("RoadMaterial", "WeatherState", "MechanicsModel"):
            if code:
                code += "\n"
            code += f"# Source code for {base.__name__}:\n"
            code += indent_code(inspect.getsource(base)) + "\n"
    return code


def get_code(cls: Optional[Type], heraklit_snippet: str = "") -> str:
    """Extract Mixin source code for `cls` and optionally append a Heraklit composition snippet."""
    if cls is None:
        return "No model selected."

    code = _get_cached_mixin_source(cls)
    if heraklit_snippet:
        code += "\n" + heraklit_snippet
    return code


def indent_code(code: str, spaces: int = 4) -> str:
    """Indents a block of source code by `spaces`."""
    lines = code.splitlines()
    return "\n".join(" " * spaces + line for line in lines)


# --------------------- Simulation Code (Mixin Layers) ---------------------

class RoadMaterial(abc.ABC):
    """Abstract base mixin defining pavement thermophysical properties."""

    @abc.abstractmethod
    def get_thermal_conductivity(self) -> float:
        """Return thermal conductivity k in W/(m*K)."""
        pass

    @abc.abstractmethod
    def get_heat_capacity(self) -> float:
        """Return specific heat capacity c_p in J/(kg*K)."""
        pass

    @abc.abstractmethod
    def get_density(self) -> float:
        """Return bulk material density rho in kg/m^3."""
        pass

    @abc.abstractmethod
    def get_albedo(self) -> float:
        """Return surface solar albedo in [0, 1]."""
        pass

    def discretize_space(self, depth: float, nodes: int) -> List[float]:
        """Return uniform layer element thicknesses for `depth` split across `nodes`."""
        return [depth / nodes for _ in range(nodes)]


class AsphaltMixin(RoadMaterial):
    """Viscoelastic mastic asphalt (SMA 11 S / AC 16 B S) material mixin."""

    def get_thermal_conductivity(self) -> float:
        """Return asphalt thermal conductivity k in W/(m*K)."""
        return 1.5

    def get_heat_capacity(self) -> float:
        """Return asphalt specific heat capacity c_p in J/(kg*K)."""
        return 920

    def get_density(self) -> float:
        """Return asphalt bulk density rho in kg/m^3."""
        return 2300

    def get_albedo(self) -> float:
        """Return asphalt surface solar albedo in [0, 1]."""
        return 0.15


class ConcreteMixin(RoadMaterial):
    """Rigid jointed plain concrete pavement (JPCP) slab mixin."""

    def get_thermal_conductivity(self) -> float:
        """Return concrete thermal conductivity k in W/(m*K)."""
        return 1.8

    def get_heat_capacity(self) -> float:
        """Return concrete specific heat capacity c_p in J/(kg*K)."""
        return 880

    def get_density(self) -> float:
        """Return concrete bulk density rho in kg/m^3."""
        return 2400

    def get_albedo(self) -> float:
        """Return concrete surface solar albedo in [0, 1]."""
        return 0.35


class GravelMixin(RoadMaterial):
    """Unbound granular subbase / aggregate material mixin."""

    def get_thermal_conductivity(self) -> float:
        """Return gravel subbase thermal conductivity k in W/(m*K)."""
        return 0.7

    def get_heat_capacity(self) -> float:
        """Return gravel specific heat capacity c_p in J/(kg*K)."""
        return 800

    def get_density(self) -> float:
        """Return gravel bulk density rho in kg/m^3."""
        return 1800

    def get_albedo(self) -> float:
        """Return gravel surface solar albedo in [0, 1]."""
        return 0.3


class WeatherState(abc.ABC):
    """Abstract base mixin defining atmospheric boundary conditions."""

    @abc.abstractmethod
    def get_solar_radiation(self) -> float:
        """Return incident solar irradiance in W/m^2."""
        pass

    @abc.abstractmethod
    def get_convective_heat_transfer_coefficient(self) -> float:
        """Return baseline convective heat transfer coefficient h_c in W/(m^2*K)."""
        pass

    def calculate_convection(self, base_hc: float, wind_speed: float) -> float:
        """Adjust convective transfer coefficient `base_hc` for surface `wind_speed`."""
        return base_hc + (2.0 * wind_speed)

    def compute_radiation_balance(self, T_surf: float, T_sky: float) -> float:
        """Return net longwave radiative flux between pavement `T_surf` and sky `T_sky`."""
        sigma = 5.67e-8
        epsilon = 0.95
        return epsilon * sigma * (T_surf**4 - T_sky**4)

    def compute_latent_heat(self) -> float:
        """Return latent heat flux contribution in W/m^2."""
        return 0.0


class SunnyMixin(WeatherState):
    """Clear-sky high shortwave irradiance boundary condition."""

    def get_solar_radiation(self) -> float:
        """Return clear-sky solar irradiance in W/m^2."""
        return 800

    def get_convective_heat_transfer_coefficient(self) -> float:
        """Return calm clear-sky convective coefficient h_c in W/(m^2*K)."""
        return 10

    def compute_radiation_balance(self, T_surf: float, T_sky: float) -> float:
        """Return clear-sky net longwave radiation balance in W/m^2."""
        return 0.5 * 5.67e-8 * (T_surf**4 - T_sky**4)


class CloudyMixin(WeatherState):
    """Diffuse overcast irradiance with reduced longwave sky loss."""

    def get_solar_radiation(self) -> float:
        """Return overcast solar irradiance in W/m^2."""
        return 200

    def get_convective_heat_transfer_coefficient(self) -> float:
        """Return overcast convective coefficient h_c in W/(m^2*K)."""
        return 15

    def compute_radiation_balance(self, T_surf: float, T_sky: float) -> float:
        """Return overcast attenuated longwave radiation balance in W/m^2."""
        return 0.1 * 5.67e-8 * (T_surf**4 - T_sky**4)


class RainyMixin(WeatherState):
    """Wet surface boundary with evaporative cooling and elevated convection."""

    def get_solar_radiation(self) -> float:
        """Return rainy overcast solar irradiance in W/m^2."""
        return 100

    def get_convective_heat_transfer_coefficient(self) -> float:
        """Return windy rain convective coefficient h_c in W/(m^2*K)."""
        return 25

    def compute_latent_heat(self) -> float:
        """Return evaporative latent cooling heat flux in W/m^2."""
        return -50.0


class SnowyMixin(WeatherState):
    """Freezing precipitation boundary with latent phase-change heat sink."""

    def get_solar_radiation(self) -> float:
        """Return snow-storm solar irradiance in W/m^2."""
        return 0

    def get_convective_heat_transfer_coefficient(self) -> float:
        """Return snowy boundary convective coefficient h_c in W/(m^2*K)."""
        return 18

    def compute_latent_heat(self) -> float:
        """Return phase-change snowmelt latent heat sink in W/m^2."""
        return -30.0


# -----------------------------------------------------------------------------
# Pavement Mechanics Mixins (Boussinesq Continuum vs. Westergaard Plate)
# -----------------------------------------------------------------------------

class MechanicsModel(abc.ABC):
    """Abstract base mixin defining pavement mechanics boundary response."""

    @abc.abstractmethod
    def compute_surface_deflection(self, wheel_load_n: float, contact_radius_m: float) -> float:
        """Returns peak surface deflection w_0 in millimeters."""
        pass

    @abc.abstractmethod
    def compute_critical_stress(self, wheel_load_n: float, contact_radius_m: float) -> float:
        """Returns critical structural stress (shear for asphalt, bending tension for concrete) in kPa."""
        pass


class BoussinesqMixin(MechanicsModel):
    """
    Boussinesq (1885) elastostatic half-space continuum mechanics mixin.

    Active for flexible asphalt pavements (RStO 12 Construction Class Bk100).
    Structural Variant Token = 1.
    """
    E_equiv_mpa: float = 350.0  # Equivalent half-space modulus (MPa)
    nu_equiv: float = 0.35      # Poisson's ratio

    def compute_surface_deflection(self, wheel_load_n: float, contact_radius_m: float) -> float:
        """Peak deflection under circular footprint: w_0 = (2 * p * (1 - nu^2) * a) / E in mm."""
        if contact_radius_m <= 0:
            return 0.0
        p0_kpa = wheel_load_n / (math.pi * contact_radius_m**2 * 1000.0)
        e_kpa = self.E_equiv_mpa * 1000.0
        w0_m = (2.0 * (p0_kpa * 1000.0) * (1.0 - self.nu_equiv**2) * contact_radius_m) / (e_kpa * 1000.0)
        return float(w0_m * 1000.0)

    def compute_critical_stress(self, wheel_load_n: float, contact_radius_m: float) -> float:
        """Max shear stress tau_max at critical depth z = a / sqrt(2) in kPa."""
        if contact_radius_m <= 0:
            return 0.0
        p0_kpa = wheel_load_n / (math.pi * contact_radius_m**2 * 1000.0)
        return float(0.31 * p0_kpa)


class WestergaardMixin(MechanicsModel):
    """
    Westergaard (1926) rigid thin plate on Winkler elastic foundation mixin.

    Active for rigid concrete pavements (JPCP Slab on HGT Base).
    Structural Variant Token = 2.
    """
    slab_thickness_m: float = 0.27       # RStO 12 Tafel 2 Zeile 1 Bk100 slab thickness h = 27 cm
    E_concrete_mpa: float = 34000.0      # Concrete Young's Modulus (C30/37)
    nu_concrete: float = 0.20            # Poisson's ratio
    k_winkler_mpa_m: float = 80.0        # Subgrade reaction modulus k (MN/m^3 or MPa/m)

    def get_radius_of_relative_stiffness(self) -> float:
        """Compute Westergaard radius of relative stiffness ell = [E*h^3 / (12*(1-nu^2)*k)]^(1/4) in meters."""
        d_rigidity = (self.E_concrete_mpa * 1e6 * (self.slab_thickness_m**3)) / (12.0 * (1.0 - self.nu_concrete**2))
        k_pa_m = self.k_winkler_mpa_m * 1e6
        ell = (d_rigidity / k_pa_m) ** 0.25
        return float(ell)

    def compute_surface_deflection(self, wheel_load_n: float, contact_radius_m: float) -> float:
        """Westergaard interior load peak deflection: w_0 = P / (8 * k * ell^2) in mm."""
        ell = self.get_radius_of_relative_stiffness()
        k_pa_m = self.k_winkler_mpa_m * 1e6
        w0_m = wheel_load_n / (8.0 * k_pa_m * (ell**2))
        return float(w0_m * 1000.0)

    def compute_critical_stress(self, wheel_load_n: float, contact_radius_m: float) -> float:
        """
        Compute critical flexural tensile bending stress at the slab bottom in kPa.

        Uses the Westergaard interior load formulation:
        ``sigma_bend = [ 3 * P * (1 + nu) / (2 * pi * h^2) ] * [ ln(ell / b) + 0.6159 ]``.
        """
        ell = self.get_radius_of_relative_stiffness()
        h = self.slab_thickness_m
        a = max(0.05, contact_radius_m)
        if a < 1.724 * h:
            b = math.sqrt(1.6 * (a**2) + h**2) - 0.675 * h
        else:
            b = a

        nu = self.nu_concrete
        prefactor = (3.0 * wheel_load_n * (1.0 + nu)) / (2.0 * math.pi * (h**2))
        sigma_pa = prefactor * (math.log(ell / b) + 0.6159)
        return float(sigma_pa / 1000.0)


class ThermalModel(RoadMaterial, WeatherState, MechanicsModel):
    """Base simulation class combining RoadMaterial, WeatherState, and MechanicsModel mixins."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.surface_temperature: float = 25.0

    def compute_surface_deflection(self, wheel_load_n: float, contact_radius_m: float) -> float:
        """Return fallback surface deflection in millimeters."""
        return 0.0

    def compute_critical_stress(self, wheel_load_n: float, contact_radius_m: float) -> float:
        """Return fallback critical structural stress in kPa."""
        return 0.0

    def simulate_temperature_change(self, time_step: float = 60.0) -> float:
        """Advance surface temperature by `time_step` seconds using mixed-in physics."""
        solar_heat_flux = (1.0 - self.get_albedo()) * self.get_solar_radiation()
        convective_heat_loss = self.get_convective_heat_transfer_coefficient() * (self.surface_temperature - 20.0)
        net_heat_flux = solar_heat_flux - convective_heat_loss + self.compute_latent_heat()
        delta_temp = (net_heat_flux / (self.get_density() * self.get_heat_capacity())) * time_step
        self.surface_temperature += delta_temp
        return self.surface_temperature

    def __str__(self) -> str:
        return f"{self.__class__.__name__}: Surface Temp = {self.surface_temperature:.2f} C"
