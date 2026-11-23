"""
data_curation/fiware/sensor.py — FIWARE UltraLight 2.0 Sensor Attribute Descriptor
==================================================================================

Lightweight descriptor mapping sensor attributes to FIWARE IoT Agent payloads.
"""

from typing import Dict


class Sensor:
    """Represents a single UltraLight 2.0 sensor attribute binding."""

    def __init__(self, name: str, datatype: str) -> None:
        self.name = name
        self.datatype = datatype

    def JSON_register_sensor(self) -> Dict[str, str]:
        """Serializes the sensor descriptor for IoT Agent device provisioning."""
        return {
            'object_id': self.name,
            'name': self.name,
            'type': self.datatype,
        }
