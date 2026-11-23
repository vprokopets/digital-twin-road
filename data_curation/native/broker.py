"""
data_curation/native/broker.py — Native In-Memory Data Broker
=============================================================

Zero-dependency, thread-safe in-memory context broker for the Digital Twin.
Ideal for standalone local execution, high-frequency physics co-simulation,
and resource-constrained edge nodes.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from data_curation.base import BaseDataBroker

logger = logging.getLogger("native_broker")


class NativeBroker(BaseDataBroker):
    """
    Thread-safe in-memory context broker for local Digital Twin execution.

    Provides fast active-state lookup and bounded ring-buffer historical
    time-series logging.
    """

    def __init__(self, max_history_per_device: int = 500) -> None:
        self.max_history = max_history_per_device
        self._lock = threading.RLock()
        self._entities: Dict[str, Dict[str, Any]] = {}
        self._history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._subscribers: List[Callable[[str, str, Dict[str, Any]], None]] = []

    def register_device(
        self,
        device_id: str,
        entity_type: str,
        api_key: Optional[str] = None,
        geo_data: Optional[Dict[str, Any]] = None,
        static_attributes: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Register an entity in the thread-safe in-memory state table."""
        dev_id = str(device_id)
        with self._lock:
            entity = {
                "id": dev_id,
                "type": entity_type,
                "created_at": time.time(),
                "updated_at": time.time(),
                "static_attributes": static_attributes or {},
                "telemetry": {},
            }
            if geo_data and "geometry" in geo_data:
                entity["coordinates"] = geo_data["geometry"]["coordinates"]
            elif static_attributes and "coordinates" in static_attributes:
                entity["coordinates"] = static_attributes["coordinates"]

            self._entities[dev_id] = entity
            logger.debug("[NativeBroker] Registered entity %s (%s)", dev_id, entity_type)
            return True

    def send_telemetry(
        self,
        device_id: str,
        entity_type: str,
        sensor_dict: Dict[str, Any],
        api_key: Optional[str] = None,
    ) -> bool:
        """Update live telemetry, append bounded ring-buffer history, and notify subscribers."""
        dev_id = str(device_id)
        now = time.time()
        with self._lock:
            if dev_id not in self._entities:
                # Auto-provision if entity sends telemetry without explicit registration
                self.register_device(dev_id, entity_type)

            entity = self._entities[dev_id]
            entity["telemetry"].update(sensor_dict)
            entity["updated_at"] = now

            if "coordinates" in sensor_dict:
                entity["coordinates"] = sensor_dict["coordinates"]

            # Append to time-series history
            hist_entry = {
                "timestamp": now,
                "data": dict(sensor_dict),
            }
            hist = self._history[dev_id]
            hist.append(hist_entry)
            if len(hist) > self.max_history:
                hist.pop(0)

            # Notify subscribers
            for cb in self._subscribers:
                try:
                    cb(dev_id, entity_type, sensor_dict)
                except Exception as e:
                    logger.warning("[NativeBroker] Subscriber callback error: %s", e)

            return True

    def get_entity(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Return a shallow copy of a single entity record by ID, or None."""
        with self._lock:
            ent = self._entities.get(str(device_id))
            return dict(ent) if ent else None

    def get_entities(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return copies of all entities, optionally filtered case-insensitively by type."""
        with self._lock:
            if entity_type is None:
                return [dict(e) for e in self._entities.values()]
            return [
                dict(e) for e in self._entities.values()
                if e.get("type", "").lower() == entity_type.lower()
            ]

    def get_history(self, device_id: str, count: int = 100) -> List[Dict[str, Any]]:
        """Return up to `count` recent history snapshots for `device_id`."""
        with self._lock:
            hist = self._history.get(str(device_id), [])
            return [dict(h) for h in hist[-count:]]

    def delete_entity(self, device_id: str) -> bool:
        """Remove an entity and its telemetry history from the in-memory store."""
        dev_id = str(device_id)
        with self._lock:
            if dev_id in self._entities:
                del self._entities[dev_id]
                self._history.pop(dev_id, None)
                return True
            return False

    def subscribe(self, callback: Callable[[str, str, Dict[str, Any]], None]) -> None:
        """Subscribe an event listener to real-time telemetry updates."""
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def get_status(self) -> Dict[str, Any]:
        """Return live entity and buffered history counts for the Native broker."""
        with self._lock:
            return {
                "backend": "native",
                "connected": True,
                "entity_count": len(self._entities),
                "history_buffer_count": sum(len(h) for h in self._history.values()),
                "driver": "In-Memory Thread-Safe Dict",
            }
