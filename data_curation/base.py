"""
data_curation/base.py — Abstract Data Curation Broker Interface
===============================================================

Defines the abstract interface BaseDataBroker. All data curation backends
(Native, FIWARE) implement this contract, enabling seamless plug-and-play
substitution across the Digital Twin platform.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseDataBroker(ABC):
    """Abstract Base Class for Digital Twin data curation and context brokering."""

    @abstractmethod
    def register_device(
        self,
        device_id: str,
        entity_type: str,
        api_key: Optional[str] = None,
        geo_data: Optional[Dict[str, Any]] = None,
        static_attributes: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Registers/provisions an entity (RSU, Vehicle, Sensor) in the context registry."""
        pass

    @abstractmethod
    def send_telemetry(
        self,
        device_id: str,
        entity_type: str,
        sensor_dict: Dict[str, Any],
        api_key: Optional[str] = None,
    ) -> bool:
        """Publishes sensor telemetry to the broker."""
        pass

    @abstractmethod
    def get_entity(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves active/last-value state for an entity."""
        pass

    @abstractmethod
    def get_entities(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Queries active entities, optionally filtered by entity_type."""
        pass

    @abstractmethod
    def get_history(self, device_id: str, count: int = 100) -> List[Dict[str, Any]]:
        """Retrieves historical time-series entries for an entity."""
        pass

    @abstractmethod
    def delete_entity(self, device_id: str) -> bool:
        """Removes an entity from the active context."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns the operational status, backend type, and connectivity metrics."""
        pass
