"""
world/weather_sources.py — Hardware-in-the-Loop Weather Data Sources
====================================================================

Provides abstract `BaseWeather` and live Raspberry Pi telemetry bridge
`RealTimePiWeather`, populated via FastAPI `POST /dashboard/weather_data`.
"""

import copy
import logging
from collections import deque
from typing import Any, Deque, Dict, List, Optional

# --- Global Data Storage for Raspberry Pi Data ---
# Populated by the FastAPI `/dashboard/weather_data` endpoint in dashboard_backend.py
# and consumed by RealTimePiWeather on RSU-00.
pi_timestamps = deque(maxlen=100)
pi_temperatures = deque(maxlen=100)
pi_humidities = deque(maxlen=100)
pi_pressures = deque(maxlen=100)
pi_dewpoints = deque(maxlen=100)
pi_lux_values = deque(maxlen=100)
pi_wind_speeds = deque(maxlen=100)
pi_rain_values = deque(maxlen=100)
pi_wind_directions_deg = deque(maxlen=100)
pi_last_wind_cardinal_str = "N/A"
pi_weather_assumption_str = "Sunny"


class BaseWeather:
    """
    Abstract base class for weather data sources.

    Subclasses should implement temperature, humidity, wind, and weather-state queries.
    """

    def __init__(self, source_id: str = "unknown") -> None:
        self.source_id = source_id
        logging.info(f"BaseWeather source '{self.source_id}' initialized.")

    def get_temperature(self) -> float:
        """Returns ambient air temperature in °C."""
        raise NotImplementedError

    def get_humidity(self) -> float:
        """Returns relative humidity in %."""
        raise NotImplementedError

    def get_pressure(self) -> float:
        """Returns atmospheric barometric pressure in hPa."""
        raise NotImplementedError

    def get_lux(self) -> float:
        """Returns ambient solar illuminance in lux."""
        raise NotImplementedError

    def get_rain_rate(self) -> float:
        """Returns precipitation rate in mm/h."""
        raise NotImplementedError

    def get_wind_speed(self) -> float:
        """Returns wind speed in m/s."""
        raise NotImplementedError

    def get_wind_direction_degrees(self) -> float:
        """Returns wind azimuth in degrees [0, 360)."""
        raise NotImplementedError

    def get_wind_direction_cardinal(self) -> str:
        """Returns 8-point cardinal wind direction label."""
        raise NotImplementedError

    def get_dewpoint(self) -> float:
        """Returns dew point temperature in °C."""
        raise NotImplementedError

    def get_assumption(self) -> str:
        """Returns inferred micro-climate weather state ('Sunny', 'Cloudy', 'Rainy')."""
        raise NotImplementedError

    def update_data(self, new_data_dict: Optional[Dict[str, Any]] = None) -> None:
        """Optional hook for sources requiring explicit updates when not polling live."""
        pass


class RealTimePiWeather(BaseWeather):
    """Live Raspberry Pi meteorological station backed by module-level telemetry ring buffers."""

    def __init__(self, params: Dict[str, Any], source_id: str = "rpi_realtime") -> None:
        super().__init__(source_id)
        logging.info(f"RealTimePiWeather source '{self.source_id}' initialized.")
        self.params: Dict[str, Any] = params
        self.previous_state: str = self.get_assumption()
        self.current_state: str = self.get_assumption()
        self.sunny_weather_effect: float = 0.5
        self.air_temp: float = self.get_temperature()
        self.road_temp: float = self.air_temp + (self.air_temp * 0.6 * self.sunny_weather_effect)
        self.manual_override: bool = False

        self.state: Dict[str, Any] = {}
        self.statistic: List[Dict[str, Any]] = []

    def _get_latest_from_deque(self, data_deque: Deque[Any], default_val: float = 0.0) -> float:
        if data_deque:
            for val in reversed(data_deque):
                if val is not None:
                    return float(val)
        return default_val

    def get_temperature(self) -> float:
        """Returns latest Raspberry Pi ambient temperature in °C or regime baseline fallback."""
        default_temp = 25.0
        if hasattr(self, 'params') and self.params:
            default_temp = float(self.params.get('StandardTemp', {}).get('Air', {}).get(self.current_state, 25.0))
        return self._get_latest_from_deque(pi_temperatures, default_temp)

    def get_humidity(self) -> float:
        """Returns latest relative humidity reading in %."""
        return self._get_latest_from_deque(pi_humidities, 50.0)

    def get_pressure(self) -> float:
        """Returns latest atmospheric pressure reading in hPa."""
        return self._get_latest_from_deque(pi_pressures, 1000.0)

    def get_lux(self) -> float:
        """Returns latest illuminance reading in lux."""
        return self._get_latest_from_deque(pi_lux_values, 0.0)

    def get_rain_rate(self) -> float:
        """Returns latest rainfall intensity reading."""
        return self._get_latest_from_deque(pi_rain_values, 0.0)

    def get_wind_speed(self) -> float:
        """Returns latest wind speed reading in m/s."""
        return self._get_latest_from_deque(pi_wind_speeds, 0.0)

    def get_wind_direction_degrees(self) -> float:
        """Returns latest wind direction in degrees."""
        return self._get_latest_from_deque(pi_wind_directions_deg, 0.0)

    def get_wind_direction_cardinal(self) -> str:
        """Returns latest 8-point cardinal wind direction."""
        return pi_last_wind_cardinal_str if pi_last_wind_cardinal_str else "N/A"

    def get_dewpoint(self) -> float:
        """Returns latest dewpoint temperature in °C."""
        return self._get_latest_from_deque(pi_dewpoints, 5.0)

    def get_assumption(self) -> str:
        """Returns latest inferred micro-climate weather label."""
        return pi_weather_assumption_str if pi_weather_assumption_str else "Awaiting Pi..."

    def update_state(self, timestamp: str) -> None:
        """Updates weather state from live Raspberry Pi buffers (unless `manual_override` is active)."""
        if getattr(self, "manual_override", False):
            self.state.update({
                'Timestamp': timestamp,
                'Weather': self.current_state,
                'AirTemperature': self.air_temp,
                'RoadSurfaceTemperature': self.road_temp
            })
            self.statistic.append(copy.deepcopy(self.state))
            if len(self.statistic) > 100:
                self.statistic = self.statistic[-100:]
            return

        self.previous_state = self.current_state
        self.current_state = self.get_assumption()

        swe_sign = 1 if self.current_state == 'Sunny' else -1  # Sunny weather effect
        self.sunny_weather_effect = self.sunny_weather_effect + swe_sign * (self.params['UpdatePeriod'] / 3600)
        if self.sunny_weather_effect > 1:
            self.sunny_weather_effect = 1
        elif self.sunny_weather_effect < 0:
            self.sunny_weather_effect = 0
        self.air_temp = self.get_temperature()
        self.road_temp = self.air_temp + (self.air_temp * 0.6 * self.sunny_weather_effect)
        self.state.update({
            'Timestamp': timestamp,
            'Weather': self.current_state,
            'AirTemperature': self.air_temp,
            'RoadSurfaceTemperature': self.road_temp
        })
        self.statistic.append(copy.deepcopy(self.state))
        if len(self.statistic) > 100:
            self.statistic = self.statistic[-100:]
