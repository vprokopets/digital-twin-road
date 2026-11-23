"""
world/geo_utils.py — Geodesic, Cartesian & Navigation Utilities
===============================================================

Provides the `CoordSystem` strategy interface (`WGS84CoordSystem` and
`LocalCartesianCoordSystem`) alongside bearing, heading, and intermediate
coordinate helpers. GeoJSON coordinate pairs follow `(lon, lat)` / `(x_m, y_m)`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import math
from typing import Any, Dict, Optional, Sequence, Tuple
import geopy.distance as gp

R_EARTH_M = 6371008.8


class CoordSystem(ABC):
    """Strategy interface for distance, bearing, and projection math."""

    mode: str

    @abstractmethod
    def distance_m(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Returns metric distance between `(x1, y1)` and `(x2, y2)`."""

    def distance_km(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Returns distance in kilometers between `(x1, y1)` and `(x2, y2)`."""
        return self.distance_m(x1, y1, x2, y2) / 1000.0

    @abstractmethod
    def bearing_deg(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Returns compass azimuth in degrees [0, 360) where 0° = +Y (North), 90° = +X (East)."""

    @abstractmethod
    def destination_point(self, x1: float, y1: float, bearing_deg: float, distance_m: float) -> Tuple[float, float]:
        """Projects `(x1, y1)` along `bearing_deg` by `distance_m` meters."""


class WGS84CoordSystem(CoordSystem):
    """Spherical WGS84 geodesic coordinate system (`x = lon_deg`, `y = lat_deg`)."""

    mode = "WGS84"

    def distance_m(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Returns spherical Haversine distance in meters between two `(lon, lat)` pairs."""
        phi1 = math.radians(y1)
        phi2 = math.radians(y2)
        dphi = math.radians(y2 - y1)
        dlambda = math.radians(x2 - x1)
        a = math.sin(dphi * 0.5) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda * 0.5) ** 2
        return 2.0 * R_EARTH_M * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))

    def bearing_deg(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Returns initial spherical compass bearing from `(lon1, lat1)` to `(lon2, lat2)`."""
        lat1_rad, lon1_rad = math.radians(y1), math.radians(x1)
        lat2_rad, lon2_rad = math.radians(y2), math.radians(x2)
        dlon_rad = lon2_rad - lon1_rad

        x = math.sin(dlon_rad) * math.cos(lat2_rad)
        y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad)
        return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0

    def destination_point(self, x1: float, y1: float, bearing_deg: float, distance_m: float) -> Tuple[float, float]:
        """Returns projected `(lon, lat)` after moving `distance_m` along `bearing_deg`."""
        angular_distance_rad = distance_m / R_EARTH_M
        lat1_rad = math.radians(y1)
        lon1_rad = math.radians(x1)
        bearing_rad = math.radians(bearing_deg)

        lat2_rad = math.asin(
            math.sin(lat1_rad) * math.cos(angular_distance_rad)
            + math.cos(lat1_rad) * math.sin(angular_distance_rad) * math.cos(bearing_rad)
        )
        lon2_rad = lon1_rad + math.atan2(
            math.sin(bearing_rad) * math.sin(angular_distance_rad) * math.cos(lat1_rad),
            math.cos(angular_distance_rad) - math.sin(lat1_rad) * math.sin(lat2_rad),
        )
        return math.degrees(lon2_rad), math.degrees(lat2_rad)


class LocalCartesianCoordSystem(CoordSystem):
    """Flat Euclidean local facility / test-track coordinate system (`x_m`, `y_m` in meters)."""

    mode = "LocalCartesian"

    def distance_m(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Returns planar Euclidean distance in meters."""
        return math.hypot(x2 - x1, y2 - y1)

    def bearing_deg(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Returns planar compass bearing in degrees [0, 360) where 0° = +Y, 90° = +X."""
        dx = x2 - x1
        dy = y2 - y1
        return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0

    def destination_point(self, x1: float, y1: float, bearing_deg: float, distance_m: float) -> Tuple[float, float]:
        """Returns projected `(x_m, y_m)` after moving `distance_m` along `bearing_deg`."""
        rad = math.radians(bearing_deg)
        return x1 + distance_m * math.sin(rad), y1 + distance_m * math.cos(rad)


def get_coord_system(crs_cfg: Optional[Dict[str, Any]] = None) -> CoordSystem:
    """Factory returning `LocalCartesianCoordSystem` or `WGS84CoordSystem` from scenario config."""
    mode = (crs_cfg or {}).get("mode", "WGS84")
    if str(mode).lower() in ("localcartesian", "cartesian", "local"):
        return LocalCartesianCoordSystem()
    return WGS84CoordSystem()


def calculate_bearing(point_a: Sequence[float], point_b: Sequence[float]) -> float:
    """Compute initial compass bearing from point_a to point_b (lat, lon) in degrees [0, 360)."""
    lat1 = math.radians(point_a[0])
    lat2 = math.radians(point_b[0])
    diff_long = math.radians(point_b[1] - point_a[1])

    x = math.sin(diff_long) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(diff_long))

    initial_bearing = math.degrees(math.atan2(x, y))
    return (initial_bearing + 360.0) % 360.0


def calculate_intermediate_point(start_point: Sequence[float], end_point: Sequence[float], distance_km: float) -> str:
    """Compute intermediate decimal coordinate string along the bearing at distance_km."""
    brng = calculate_bearing(start_point, end_point)
    return gp.distance(kilometers=distance_km).destination(start_point, brng).format_decimal()


class Auxiliary:
    """Backwards-compatible wrapper class for legacy callers."""

    @staticmethod
    def calculate_bearing(point_a: Sequence[float], point_b: Sequence[float]) -> float:
        """Delegate to module-level ``calculate_bearing``."""
        return calculate_bearing(point_a, point_b)

    @staticmethod
    def calculate_intermediate_point(start_point: Sequence[float], end_point: Sequence[float], distance: float) -> str:
        """Delegate to module-level ``calculate_intermediate_point``."""
        return calculate_intermediate_point(start_point, end_point, distance)
