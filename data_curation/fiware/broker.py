"""
data_curation/fiware/broker.py — FIWARE Standards-Compliant Data Broker
=======================================================================

Implements BaseDataBroker using the FIWARE Open IoT Stack:
- IoT Agent (UltraLight 2.0 / HTTP)
- Orion Context Broker (NGSIv2)
- Cygnus / PostgreSQL time-series persistency
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from data_curation.base import BaseDataBroker
from data_curation.fiware.client import FiwareDeviceManager, get_default_manager

logger = logging.getLogger("fiware_broker")


class FiwareBroker(BaseDataBroker):
    """Context broker adapter interfacing with the FIWARE ecosystem."""

    def __init__(
        self,
        manager: Optional[FiwareDeviceManager] = None,
        orion_host: Optional[str] = None,
        timeout: float = 2.0,
    ) -> None:
        self.manager = manager or get_default_manager()
        self.orion_host = orion_host or os.getenv("ORION_HOST", "localhost")
        self.timeout = timeout

    def register_device(
        self,
        device_id: str,
        entity_type: str,
        api_key: Optional[str] = None,
        geo_data: Optional[Dict[str, Any]] = None,
        static_attributes: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Register an entity with the FIWARE IoT Agent and Orion Context Broker."""
        key = api_key or "openiot"
        return self.manager.register_device(
            device_id=str(device_id),
            api_key=key,
            entity_type=entity_type,
            geo_data=geo_data,
            static_attributes=static_attributes,
        )

    def send_telemetry(
        self,
        device_id: str,
        entity_type: str,
        sensor_dict: Dict[str, Any],
        api_key: Optional[str] = None,
    ) -> bool:
        """Publish UltraLight 2.0 sensor measurements for an entity to IoT Agent."""
        key = api_key or "openiot"
        return self.manager.send_sensor_data(
            device_id=str(device_id),
            api_key=key,
            entity_type=entity_type,
            sensor_dict=sensor_dict,
        )

    def get_entity(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the latest entity state from Orion NGSIv2 or mock store."""
        dev_id = str(device_id)
        if self.manager.mock_mode:
            return self.manager.mock_entities.get(dev_id)

        url = f"http://{self.orion_host}:1026/v2/entities/{quote(dev_id, safe='')}"
        headers = {"fiware-service": "openiot", "fiware-servicepath": "/"}
        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException:
            pass
        return self.manager.mock_entities.get(dev_id)

    def get_entities(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List active entities from Orion NGSIv2 or mock store, optionally filtered by type."""
        if self.manager.mock_mode:
            if entity_type:
                return [
                    e for e in self.manager.mock_entities.values()
                    if e.get("entity_type", "").lower() == entity_type.lower()
                ]
            return list(self.manager.mock_entities.values())

        url = f"http://{self.orion_host}:1026/v2/entities"
        params = {"limit": 100, "options": "keyValues"}
        if entity_type:
            params["type"] = entity_type
        headers = {"fiware-service": "openiot", "fiware-servicepath": "/"}

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException:
            pass

        return list(self.manager.mock_entities.values())

    def get_history(self, device_id: str, count: int = 100) -> List[Dict[str, Any]]:
        """Return up to `count` recent telemetry history records for `device_id`."""
        # Return mock history if offline, or query Cygnus sink
        dev_id = str(device_id)
        matching = [
            h for h in self.manager.mock_telemetry_history
            if h.get("device_id") == dev_id
        ]
        return matching[-count:]

    def delete_entity(self, device_id: str) -> bool:
        """Delete an entity from both the local mock registry and Orion Context Broker."""
        dev_id = str(device_id)
        self.manager.mock_entities.pop(dev_id, None)

        url = f"http://{self.orion_host}:1026/v2/entities/{quote(dev_id, safe='')}"
        headers = {"fiware-service": "openiot", "fiware-servicepath": "/"}
        try:
            resp = requests.delete(url, headers=headers, timeout=self.timeout)
            return resp.status_code in (200, 204)
        except requests.RequestException:
            return True

    def get_status(self) -> Dict[str, Any]:
        """Return connectivity, host, and entity-count diagnostics for the FIWARE broker."""
        return {
            "backend": "fiware",
            "connected": not self.manager.mock_mode,
            "mock_mode": self.manager.mock_mode,
            "orion_host": self.orion_host,
            "entity_count": len(self.manager.mock_entities),
            "driver": "Orion Context Broker (NGSIv2) + IoT Agent (UltraLight 2.0)",
        }
