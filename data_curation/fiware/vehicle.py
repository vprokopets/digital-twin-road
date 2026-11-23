"""
data_curation/fiware/vehicle.py — FIWARE Vehicle Telematics Connector
=====================================================================

Convenience wrappers forwarding to the universal register_device and send_telemetry.
"""

from __future__ import annotations

from typing import Any, Dict
from data_curation.fiware.client import register_device, send_telemetry
from data_curation.fiware.sensor import Sensor

sensor_data = [
    Sensor("Active", "Bool"),
    Sensor("Velocity", "Float"),
    Sensor("Model", "String"),
    Sensor("Accuracy", "Float"),
    Sensor("coordinates", "Point"),
    Sensor("AirTemperature", "Float"),
    Sensor("RoadSurfaceTemperature", "Float"),
    Sensor("SoilTemperature", "Float"),
]


def register_vehicle(
    api_key: str,
    vehicle_data_static: Dict[str, Any],
) -> bool:
    """Registers a vehicle entity with static attributes in the IoT Agent."""
    device_id = vehicle_data_static.get("ID", "veh_unknown")
    return register_device(
        device_id=device_id,
        api_key=api_key,
        entity_type="Vehicle",
        static_attributes=vehicle_data_static,
    )


def send_sensor_data_vehicle(
    device_id: Any,
    api_key: str,
    sen_dict: Dict[str, Any],
) -> bool:
    """Publishes UltraLight 2.0 telemetry payload for a vehicle."""
    return send_telemetry(
        device_id=device_id,
        api_key=api_key,
        entity_type="Vehicle",
        sensor_dict=sen_dict,
    )
