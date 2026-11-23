"""
data_curation/fiware/service_group.py — FIWARE Service Group & Persistence Helpers
==================================================================================

Backward-compatible API wrappers delegating to the schema-driven FiwareDeviceManager.
"""

from __future__ import annotations

from typing import Optional
from data_curation.fiware.client import get_default_manager


def register_service_group(
    api_key: str,
    entity_type: str = "Roadside_unit",
    service: str = "openiot",
    servicepath: str = "/",
) -> bool:
    """Registers a FIWARE service group before sensor provisioning."""
    return get_default_manager().register_service_group(
        api_key=api_key,
        entity_type=entity_type,
        service=service,
        servicepath=servicepath,
    )


def activate_persistance_db(
    service: str = "openiot",
    servicepath: str = "/",
    cygnus_url: Optional[str] = None,
) -> bool:
    """Subscribes Orion Context Broker to notify Cygnus for database persistence."""
    return get_default_manager().activate_persistance_db(
        service=service,
        servicepath=servicepath,
        cygnus_url=cygnus_url,
    )
