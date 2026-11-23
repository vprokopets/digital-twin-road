"""
data_curation/fiware/client.py — FIWARE Client & Declarative Device Manager
===========================================================================

Schema-driven IoT client supporting UltraLight 2.0 / NGSIv2 for the Road Digital Twin.
Validates entity templates, provisions IoT Agent service groups, and handles live or
mocked telemetry publishing.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("fiware_client")


class FiwareDeviceManager:
    """
    Schema-driven manager for FIWARE IoT Agent devices and Cygnus subscriptions.

    Handles device provisioning, UltraLight 2.0 payload formatting, and Cygnus
    persistency subscriptions from declarative JSON schemas.
    """

    DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "fiware_schema.json"

    def __init__(
        self,
        schema_path: Optional[str | Path] = None,
        orion_host: Optional[str] = None,
        iota_host: Optional[str] = None,
        iota_south_host: Optional[str] = None,
        mock_mode: bool = False,
        timeout: float = 2.0,
    ) -> None:
        self.schema_path = Path(schema_path) if schema_path else self.DEFAULT_SCHEMA_PATH
        self.orion_host = orion_host or os.getenv("ORION_HOST", "localhost")
        self.iota_host = iota_host or os.getenv("IOT_AGENT_HOST", "localhost")
        self.iota_south_host = iota_south_host or os.getenv("IOT_AGENT_SOUTH_HOST", "localhost")
        self.mock_mode = mock_mode
        self.timeout = timeout

        self.schema: Dict[str, Any] = {}
        self.service_groups: Dict[str, Dict[str, Any]] = {}
        self.entity_templates: Dict[str, Dict[str, Any]] = {}
        self.persistency_config: Dict[str, Any] = {}

        # In-memory mock store for offline execution and testing
        self.mock_entities: Dict[str, Dict[str, Any]] = {}
        self.mock_telemetry_history: List[Dict[str, Any]] = []

        self.load_schema()

    def _probe_http_endpoint(
        self,
        url: str,
        *,
        retries: int = 1,
        retry_delay: float = 1.0,
        timeout: float = 0.8,
    ) -> bool:
        """Polls an HTTP health endpoint and sets mock_mode=True only if all attempts fail."""
        if self.mock_mode:
            return False
        attempts = max(1, int(retries))
        for idx in range(attempts):
            try:
                resp = requests.get(url, timeout=timeout)
                if resp.status_code == 200:
                    return True
            except requests.RequestException:
                pass
            if idx < attempts - 1 and retry_delay > 0:
                time.sleep(retry_delay)
        self.mock_mode = True
        return False

    def check_connection(self, *, retries: int = 1, retry_delay: float = 1.0) -> bool:
        """Pings the Orion Context Broker /version endpoint to verify connectivity."""
        return self._probe_http_endpoint(
            f"http://{self.orion_host}:1026/version",
            retries=retries,
            retry_delay=retry_delay,
            timeout=0.8,
        )

    def check_iot_agent(self, *, retries: int = 1, retry_delay: float = 1.0) -> bool:
        """Pings the IoT Agent North /iot/about endpoint to verify connectivity."""
        return self._probe_http_endpoint(
            f"http://{self.iota_host}:4041/iot/about",
            retries=retries,
            retry_delay=retry_delay,
            timeout=1.0,
        )

    def load_schema(self) -> None:
        """Loads and parses the declarative FIWARE JSON schema."""
        if not self.schema_path.exists():
            logger.warning("FIWARE schema not found at %s. Using in-memory fallback.", self.schema_path)
            self._load_fallback_schema()
            return

        with open(self.schema_path, "r", encoding="utf-8") as f:
            self.schema = json.load(f)

        self.service_groups = {
            sg.get("entity_type", sg.get("id")): sg for sg in self.schema.get("service_groups", [])
        }
        self.entity_templates = self.schema.get("entity_templates", {})
        self.persistency_config = self.schema.get("persistency", {})
        logger.debug(
            "Loaded FIWARE schema v%s (%d templates, %d service groups)",
            self.schema.get("metamodel_version", "unknown"),
            len(self.entity_templates),
            len(self.service_groups),
        )

    def _load_fallback_schema(self) -> None:
        self.schema = {
            "metamodel_version": "2.0.0-fallback",
            "service_groups": [],
            "entity_templates": {
                "Roadside_unit": {
                    "dynamic_sensors": [
                        {"name": "Weather", "type": "Text"},
                        {"name": "AirTemperature", "type": "Float"},
                        {"name": "RoadSurfaceTemperature", "type": "Float"},
                        {"name": "SoilTemperature", "type": "Float"},
                    ]
                },
                "Vehicle": {
                    "dynamic_sensors": [
                        {"name": "Active", "type": "Bool"},
                        {"name": "Velocity", "type": "Float"},
                        {"name": "Model", "type": "String"},
                        {"name": "Accuracy", "type": "Float"},
                        {"name": "coordinates", "type": "Point"},
                        {"name": "AirTemperature", "type": "Float"},
                        {"name": "RoadSurfaceTemperature", "type": "Float"},
                        {"name": "SoilTemperature", "type": "Float"},
                    ]
                },
            },
        }
        self.entity_templates = self.schema["entity_templates"]

    def get_template(self, entity_type: str) -> Dict[str, Any]:
        """Returns the entity template for a given entity type."""
        template = self.entity_templates.get(entity_type)
        if not template:
            # Fallback for case sensitivity or alternative naming
            for key, val in self.entity_templates.items():
                if key.lower() == entity_type.lower():
                    return val
            return {"static_attributes": [], "dynamic_sensors": []}
        return template

    # -------------------------------------------------------------------------
    # Service Groups & Persistence
    # -------------------------------------------------------------------------
    def register_service_group(
        self,
        api_key: str,
        entity_type: str = "Roadside_unit",
        service: str = "openiot",
        servicepath: str = "/",
    ) -> bool:
        """Registers a service group with the IoT Agent."""
        headers = {
            "Content-Type": "application/json",
            "fiware-service": service,
            "fiware-servicepath": servicepath,
        }
        url = f"http://{self.iota_host}:4041/iot/services"
        payload = {
            "services": [
                {
                    "apikey": api_key,
                    "cbroker": f"http://{self.orion_host}:1026",
                    "entity_type": entity_type,
                    "resource": "/iot/d",
                }
            ]
        }

        if self.mock_mode:
            logger.info("[MOCK] Registered FIWARE service group %s (type=%s)", api_key, entity_type)
            return True

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            logger.info("Service group registration response [%d]: %s", resp.status_code, resp.text)
            return resp.status_code in (200, 201, 409)
        except requests.RequestException as e:
            logger.warning("Could not reach IoT Agent at %s: %s. Continuing in mock mode.", url, e)
            self.mock_mode = True
            return False

    def activate_persistance_db(
        self,
        service: str = "openiot",
        servicepath: str = "/",
        cygnus_url: Optional[str] = None,
    ) -> bool:
        """Subscribes Orion Context Broker to notify Cygnus for database persistence."""
        cygnus_endpoint = cygnus_url or self.persistency_config.get(
            "cygnus_url", "http://cygnus:5055/notify"
        )
        headers = {
            "Content-Type": "application/json",
            "fiware-service": service,
            "fiware-servicepath": servicepath,
        }
        json_data = {
            "description": self.persistency_config.get(
                "subscription_description", "Notify Cygnus Postgres of all context changes"
            ),
            "subject": {
                "entities": self.persistency_config.get("entities", [{"idPattern": ".*"}]),
            },
            "notification": {
                "http": {
                    "url": cygnus_endpoint,
                },
            },
            "throttling": self.persistency_config.get("throttling_s", 0),
        }

        if self.mock_mode:
            logger.info("[MOCK] Activated Cygnus persistence subscription to %s", cygnus_endpoint)
            return True

        url = f"http://{self.orion_host}:1026/v2/subscriptions"
        try:
            resp = requests.post(url, headers=headers, json=json_data, timeout=self.timeout)
            logger.info("Cygnus subscription response [%d]: %s", resp.status_code, resp.text)
            return resp.status_code in (200, 201, 409)
        except requests.RequestException as e:
            logger.warning("Could not reach Orion broker at %s: %s. Continuing in mock mode.", url, e)
            self.mock_mode = True
            return False

    # -------------------------------------------------------------------------
    # Device Registration
    # -------------------------------------------------------------------------
    def register_device(
        self,
        device_id: str,
        api_key: str,
        entity_type: str,
        geo_data: Optional[Dict[str, Any]] = None,
        static_attributes: Optional[Dict[str, Any]] = None,
        service: str = "openiot",
        servicepath: str = "/",
    ) -> bool:
        """Registers a device with the IoT Agent using its template schema."""
        template = self.get_template(entity_type)
        static_values = static_attributes or {}

        # Build static attributes
        static_data: List[Dict[str, Any]] = []
        if geo_data and "geometry" in geo_data:
            static_data.append({
                "name": "coordinates",
                "type": "Point",
                "value": geo_data["geometry"]["coordinates"],
            })
        elif "coordinates" in static_values:
            static_data.append({
                "name": "coordinates",
                "type": "Point",
                "value": static_values["coordinates"],
            })

        for attr in template.get("static_attributes", []):
            attr_name = attr["name"]
            if attr_name == "coordinates":
                continue
            val = static_values.get(attr_name, attr.get("default", 0))
            static_data.append({
                "name": attr_name,
                "type": attr.get("type", "Text"),
                "value": val,
            })

        # Build dynamic sensor schema
        sensor_schema: List[Dict[str, Any]] = []
        for sen in template.get("dynamic_sensors", []):
            sensor_schema.append({
                "object_id": sen.get("object_id", sen["name"]),
                "name": sen["name"],
                "type": sen.get("type", "Float"),
            })

        device_entry = {
            "device_id": str(device_id),
            "entity_name": str(device_id),
            "entity_type": entity_type,
            "protocol": "PDI-IoTA-UltraLight",
            "transport": "HTTP",
            "apikey": api_key,
            "timezone": "Europe/Berlin",
            "attributes": sensor_schema,
            "static_attributes": static_data,
        }

        # Save to mock registry
        self.mock_entities[str(device_id)] = device_entry

        if self.mock_mode:
            logger.debug("[MOCK] Registered device %s (type=%s)", device_id, entity_type)
            return True

        headers = {
            "Content-Type": "application/json",
            "fiware-service": service,
            "fiware-servicepath": servicepath,
        }
        url = f"http://{self.iota_host}:4041/iot/devices"
        payload = {"devices": [device_entry]}

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            logger.debug("Device %s registration [%d]: %s", device_id, resp.status_code, resp.text)
            return resp.status_code in (200, 201, 409)
        except requests.RequestException as e:
            logger.debug("IoT Agent unreachable for %s registration: %s. Registered in mock store.", device_id, e)
            return True

    # -------------------------------------------------------------------------
    # Telemetry Serialization & Publishing
    # -------------------------------------------------------------------------
    def format_ultralight(
        self,
        entity_type: str,
        sensor_dict: Dict[str, Any],
    ) -> str:
        """
        Format a sensor dictionary into an UltraLight 2.0 pipe-delimited payload.

        Example:
            ``'Weather|Sunny|AirTemperature|22.5'``
        """
        template = self.get_template(entity_type)
        defined_sensors = template.get("dynamic_sensors", [])

        parts: List[str] = []
        if defined_sensors:
            for sen in defined_sensors:
                name = sen["name"]
                if name in sensor_dict:
                    val = sensor_dict[name]
                    parts.append(f"{name}|{val}")
        else:
            for k, v in sensor_dict.items():
                parts.append(f"{k}|{v}")

        return "|".join(parts)

    def send_sensor_data(
        self,
        device_id: str,
        api_key: str,
        entity_type: str,
        sensor_dict: Dict[str, Any],
    ) -> bool:
        """Publishes UltraLight 2.0 telemetry payload to the IoT Agent Southbound port (7896)."""
        data = self.format_ultralight(entity_type, sensor_dict)
        if not data:
            return False

        # Record in mock history
        self.mock_telemetry_history.append({
            "device_id": str(device_id),
            "entity_type": entity_type,
            "data": data,
            "raw": sensor_dict,
        })
        if len(self.mock_telemetry_history) > 500:
            self.mock_telemetry_history.pop(0)

        if self.mock_mode:
            return True

        headers = {"Content-Type": "text/plain"}
        params = {"k": api_key, "i": str(device_id)}
        url = f"http://{self.iota_south_host}:7896/iot/d"

        try:
            resp = requests.post(url, params=params, headers=headers, data=data, timeout=self.timeout)
            return resp.status_code in (200, 201)
        except requests.RequestException:
            # Silently tolerate IoT Agent south port being offline in local simulations
            return True


# Global singleton instance for backward compatibility
_default_manager: Optional[FiwareDeviceManager] = None


def get_default_manager() -> FiwareDeviceManager:
    """Returns the default FiwareDeviceManager singleton."""
    global _default_manager
    if _default_manager is None:
        _default_manager = FiwareDeviceManager()
    return _default_manager


# -------------------------------------------------------------------------
# Universal Module-Level Convenience Functions
# -------------------------------------------------------------------------
def register_device(
    device_id: Any,
    api_key: str,
    entity_type: str,
    geo_data: Optional[Dict[str, Any]] = None,
    static_attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    """Universal device registration for any entity type defined in the FIWARE schema."""
    return get_default_manager().register_device(
        device_id=str(device_id),
        api_key=api_key,
        entity_type=entity_type,
        geo_data=geo_data,
        static_attributes=static_attributes,
    )


def send_telemetry(
    device_id: Any,
    api_key: str,
    entity_type: str,
    sensor_dict: Dict[str, Any],
) -> bool:
    """Universal UltraLight telemetry transmission for any entity type."""
    return get_default_manager().send_sensor_data(
        device_id=str(device_id),
        api_key=api_key,
        entity_type=entity_type,
        sensor_dict=sensor_dict,
    )

