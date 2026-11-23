"""
data_curation/fiware — FIWARE Context Broker & IoT Agent Integration
====================================================================

Complete NGSIv2 and UltraLight 2.0 integration for the Road Digital Twin:
- FiwareBroker: BaseDataBroker implementation querying Orion entity store
- FiwareDeviceManager: Declarative IoT Agent manager driven by fiware_schema.json
- RoadsideUnit / Vehicle / Sensor: Domain telemetry and provisioning wrappers
- ServiceGroup: Persistent tenant configuration & Cygnus database persistence

Project: Digital Twin Road Demonstrator — Open Source Road Infrastructure Platform (MIT)
"""

from data_curation.fiware.broker import FiwareBroker
from data_curation.fiware.client import (
    FiwareDeviceManager,
    get_default_manager,
    register_device,
    send_telemetry,
)
from data_curation.fiware.service_group import (
    register_service_group,
    activate_persistance_db,
)
from data_curation.fiware.roadside_unit import (
    register_roadside_unit,
    send_sensor_data_roadside_unit,
)
from data_curation.fiware.vehicle import (
    register_vehicle,
    send_sensor_data_vehicle,
)
from data_curation.fiware.sensor import Sensor

__all__ = [
    "FiwareBroker",
    "FiwareDeviceManager",
    "get_default_manager",
    "register_device",
    "send_telemetry",
    "register_service_group",
    "activate_persistance_db",
    "register_roadside_unit",
    "send_sensor_data_roadside_unit",
    "register_vehicle",
    "send_sensor_data_vehicle",
    "Sensor",
]
