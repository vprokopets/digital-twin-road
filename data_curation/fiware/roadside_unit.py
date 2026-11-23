"""
data_curation/fiware/roadside_unit.py — FIWARE Roadside Unit (RSU) Connector
============================================================================

Convenience wrappers forwarding to the universal register_device and send_telemetry.
"""

from __future__ import annotations

from typing import Any, Dict
from data_curation.fiware.client import register_device, send_telemetry
from data_curation.fiware.sensor import Sensor

sensor_data = [
    Sensor("Weather", "Float"),
    Sensor("AirTemperature", "Float"),
    Sensor("RoadSurfaceTemperature", "Float"),
]


def register_roadside_unit(
    device_id: Any,
    api_key: str,
    geo_data: Dict[str, Any],
) -> bool:
    """Registers an RSU device with coordinates in the IoT Agent."""
    return register_device(
        device_id=device_id,
        api_key=api_key,
        entity_type="Roadside_unit",
        geo_data=geo_data,
    )


def send_sensor_data_roadside_unit(
    device_id: Any,
    api_key: str,
    sen_dict: Dict[str, Any],
) -> bool:
    """Publishes UltraLight 2.0 telemetry payload for an RSU."""
    return send_telemetry(
        device_id=device_id,
        api_key=api_key,
        entity_type="Roadside_unit",
        sensor_dict=sen_dict,
    )
