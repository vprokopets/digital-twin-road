"""
data_curation — Data Curation & Brokering Package
=================================================

Pluggable, multi-backend context brokering and data curation for the Road Digital Twin.
Supports:
  - "native": In-memory thread-safe state engine (default, 0 dependencies, sub-microsecond)
  - "fiware": European open-standards stack (Orion Context Broker + IoT Agent UltraLight)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from data_curation.base import BaseDataBroker
from data_curation.native.broker import NativeBroker
from data_curation.fiware.broker import FiwareBroker

logger = logging.getLogger("data_curation")

# Singleton broker cache
_active_broker: Optional[BaseDataBroker] = None
_broker_registry: Dict[str, BaseDataBroker] = {}


def _resolve_default_backend() -> str:
    """Resolves default backend from environment or global_config.json."""
    env_backend = os.getenv("DATA_BROKER_BACKEND")
    if env_backend:
        return env_backend.lower()

    cfg_path = Path(__file__).resolve().parent.parent / "configs" / "global_config.json"
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            backend = cfg.get("DataBroker", {}).get("backend")
            if backend:
                return str(backend).lower()
        except Exception:
            pass

    return "native"


def get_data_broker(backend: Optional[str] = None) -> BaseDataBroker:
    """Factory function returning the configured or requested data broker singleton."""
    global _active_broker
    selected = (backend or _resolve_default_backend()).lower()

    if selected not in _broker_registry:
        if selected == "fiware":
            _broker_registry[selected] = FiwareBroker()
        elif selected == "native":
            _broker_registry[selected] = NativeBroker()
        else:
            logger.warning("Unknown data broker backend '%s'. Falling back to 'native'.", selected)
            selected = "native"
            if "native" not in _broker_registry:
                _broker_registry["native"] = NativeBroker()

    _active_broker = _broker_registry[selected]
    return _active_broker


# -------------------------------------------------------------------------
# Universal Module-Level Convenience Functions
# -------------------------------------------------------------------------
def register_device(
    device_id: Any,
    entity_type: str,
    api_key: Optional[str] = None,
    geo_data: Optional[Dict[str, Any]] = None,
    static_attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    """Universal entity registration delegated to the active data broker."""
    return get_data_broker().register_device(
        device_id=str(device_id),
        entity_type=entity_type,
        api_key=api_key,
        geo_data=geo_data,
        static_attributes=static_attributes,
    )


def send_telemetry(
    device_id: Any,
    entity_type: str,
    sensor_dict: Dict[str, Any],
    api_key: Optional[str] = None,
) -> bool:
    """Universal telemetry publishing delegated to the active data broker."""
    return get_data_broker().send_telemetry(
        device_id=str(device_id),
        entity_type=entity_type,
        sensor_dict=sensor_dict,
        api_key=api_key,
    )


def get_entity(device_id: Any) -> Optional[Dict[str, Any]]:
    """Retrieves active state for an entity from the active data broker."""
    return get_data_broker().get_entity(str(device_id))


def get_entities(entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all active entities from the active data broker."""
    return get_data_broker().get_entities(entity_type=entity_type)


def get_history(device_id: Any, count: int = 100) -> List[Dict[str, Any]]:
    """Retrieves historical events for an entity from the active data broker."""
    return get_data_broker().get_history(str(device_id), count=count)


def delete_entity(device_id: Any) -> bool:
    """Deletes an entity from the active data broker."""
    return get_data_broker().delete_entity(str(device_id))


def get_broker_status() -> Dict[str, Any]:
    """Retrieves status and connectivity details of the active data broker."""
    return get_data_broker().get_status()


__all__ = [
    "BaseDataBroker",
    "NativeBroker",
    "FiwareBroker",
    "get_data_broker",
    "register_device",
    "send_telemetry",
    "get_entity",
    "get_entities",
    "get_history",
    "delete_entity",
    "get_broker_status",
]
