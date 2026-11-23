"""
api/fiware.py — FIWARE Orion & Active Data Broker Introspection Router
======================================================================

Exposes runtime connectivity checks, service-group endpoint metadata, single-entity
resolution, entity listings, and idle-entity cleanup against the active `data_curation`
broker (Native in-memory or FIWARE).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests

from api.runtime import get_shadow

router = APIRouter(tags=["FIWARE & Broker"])


class CleanIdleRequest(BaseModel):
    """List of stale FIWARE entity IDs requested for deletion."""

    entity_ids: List[str]


def _build_broker_connection_metadata() -> Dict[str, Any]:
    """Builds endpoint URLs and FIWARE service-group definitions from schema + env."""
    orion_host = os.getenv("ORION_HOST", "localhost")
    iota_host = os.getenv("IOT_AGENT_HOST", "localhost")
    iota_south_host = os.getenv("IOT_AGENT_SOUTH_HOST", "localhost")

    schema_groups: List[Dict[str, Any]] = []
    try:
        from data_curation.fiware.client import get_default_manager

        mgr = get_default_manager()
        schema_groups = list(mgr.schema.get("service_groups", []))
    except Exception:
        schema_groups = []

    runtime_keys = {
        "Roadside_unit": "rs",
        "Vehicle": "vehicle",
    }
    service_groups: List[Dict[str, Any]] = []
    for sg in schema_groups:
        et = str(sg.get("entity_type", ""))
        rkey = runtime_keys.get(et, str(sg.get("apikey", "")))
        resource = str(sg.get("resource", "/iot/d"))
        service_groups.append({
            **sg,
            "runtime_apikey": rkey,
            "ultralight_endpoint": f"http://{iota_south_host}:7896{resource}?k={rkey}&i=<id>",
        })

    endpoints = {
        "orion_entities": f"http://{orion_host}:1026/v2/entities",
        "orion_version": f"http://{orion_host}:1026/version",
        "iota_services": f"http://{iota_host}:4041/iot/services",
        "iota_devices": f"http://{iota_host}:4041/iot/devices",
        "iota_ultralight": f"http://{iota_south_host}:7896/iot/d",
        "roadside_weather_ingest": "/dashboard/weather_data",
        "embedded_sensor_ingest": "/api/telemetry/sensors/{station_id}",
        "broker_entities": "/dashboard/fiware_entities",
        "broker_entity_template": "/dashboard/fiware_entities/{entity_id}",
        "broker_entity_history_template": "/dashboard/fiware_entities/{entity_id}/history",
    }

    return {
        "fiware_service": "openiot",
        "fiware_servicepath": "/",
        "endpoints": endpoints,
        "service_groups": service_groups,
    }


@router.get("/dashboard/fiware_status")
def get_fiware_status() -> Dict[str, Any]:
    """Returns FIWARE / active data broker connection status, endpoints, and service groups."""
    from data_curation import get_broker_status

    st = get_broker_status()
    shadow = get_shadow()
    fiware_connected = bool(shadow.fiware_flag) if shadow is not None else False
    broker_active = bool(fiware_connected or st.get("connected", False))
    conn_meta = _build_broker_connection_metadata()
    return {
        "enabled": broker_active,
        "connected": broker_active,
        "fiware_connected": fiware_connected,
        "backend": st.get("backend", "native"),
        "driver": st.get("driver", "In-Memory"),
        "entity_count": st.get("entity_count", 0),
        **conn_meta,
    }


@router.get("/dashboard/data_broker_status")
def get_data_broker_status_endpoint() -> Dict[str, Any]:
    """Returns detailed runtime metrics for the configured `data_curation` broker."""
    from data_curation import get_broker_status

    return get_broker_status()


@router.get("/dashboard/fiware_entities")
def get_fiware_entities() -> List[Dict[str, Any]]:
    """Lists curated digital twin entities from the active data broker or Orion."""
    shadow = get_shadow()
    if shadow is None:
        return []
    return shadow.get_fiware_entities()


@router.get("/dashboard/fiware_entities/{entity_id}")
def get_fiware_entity(entity_id: str) -> Dict[str, Any]:
    """Retrieves a single curated entity by ID from Native/FIWARE broker or Orion."""
    from data_curation import get_entity

    ent = get_entity(entity_id)
    if ent is not None:
        return ent

    shadow = get_shadow()
    if shadow is not None and shadow.fiware_flag:
        orion_host = os.getenv("ORION_HOST", "localhost")
        url = f"http://{orion_host}:1026/v2/entities/{quote(entity_id, safe='')}"
        headers = {"fiware-service": "openiot", "fiware-servicepath": "/"}
        try:
            resp = requests.get(
                url,
                headers=headers,
                params={"options": "keyValues"},
                timeout=2.5,
            )
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException:
            pass

    raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")


@router.get("/dashboard/fiware_entities/{entity_id}/history")
def get_fiware_entity_history(entity_id: str, limit: int = 50) -> Dict[str, Any]:
    """Retrieves bounded time-series history for an entity from the active broker."""
    from data_curation import get_broker_status, get_entity, get_history

    clamped_limit = max(1, min(int(limit), 500))
    st = get_broker_status()
    history = get_history(entity_id, count=clamped_limit)
    if not history and get_entity(entity_id) is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    return {
        "entity_id": entity_id,
        "backend": st.get("backend", "native"),
        "driver": st.get("driver", "In-Memory"),
        "limit": clamped_limit,
        "count": len(history),
        "history": history,
    }


@router.post("/dashboard/fiware_entities/clean_idle")
def clean_idle_fiware_entities(req: CleanIdleRequest) -> Dict[str, List[str]]:
    """Deletes idle/stale entities from the FIWARE Orion Context Broker."""
    shadow = get_shadow()
    if shadow is None:
        raise HTTPException(status_code=500, detail="Shadow not initialized")

    deleted: List[str] = []
    failed: List[str] = []
    for eid in req.entity_ids:
        if shadow.delete_fiware_entity(eid):
            deleted.append(eid)
        else:
            failed.append(eid)
    return {"deleted": deleted, "failed": failed}
