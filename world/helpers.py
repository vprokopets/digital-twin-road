"""
world/helpers.py — Weather Classification & Wind Cardinal Utilities
===================================================================

Project: Digital Twin Road Demonstrator
"""

from __future__ import annotations
from typing import Any, Optional

LUX_BRIGHT_CLOUDY = 8000.0
RAIN_THRESHOLD_LIGHT = 0.01


def get_abbreviated_cardinal_8pt(degrees: Optional[float]) -> str:
    """Converts wind direction in degrees [0, 360) to an 8-point cardinal abbreviation."""
    if degrees is None:
        return "---"
    deg = float(degrees) % 360.0
    index = int((deg + 22.5) // 45.0) % 8
    abbreviations_8pt = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return abbreviations_8pt[index]


def get_weather_assumption(
    lux: Optional[float],
    rain_rate: Optional[float],
    temperature: Optional[float],
    humidity: Optional[float],
    pressure: Optional[float],
    current_dt_object: Any,
    dewpoint_val: Optional[float],
) -> str:
    """Infers categorical weather regime ('Sunny', 'Cloudy', 'Rainy') from station telemetry."""
    _ = (temperature, humidity, pressure, dewpoint_val)
    hour = getattr(current_dt_object, "hour", 12)
    is_daytime = 6 <= hour < 20

    if (rain_rate or 0.0) > RAIN_THRESHOLD_LIGHT:
        return "Rainy"
    if not is_daytime:
        return "Cloudy"
    if (lux or 0.0) >= LUX_BRIGHT_CLOUDY:
        return "Sunny"
    return "Cloudy"
