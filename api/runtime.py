"""
api/runtime.py — Shared Runtime State Accessor for FastAPI Routers
==================================================================

Provides `get_shadow()` and `set_shadow()` so modular routers read and mutate
the active `DigitalShadow` engine without circular imports while preserving full
compatibility with direct assignments to `dashboard_backend.shadow_instance`.
"""

from __future__ import annotations

import sys
import threading
from typing import Any, Optional

_shadow_instance: Optional[Any] = None
_processing_thread: Optional[threading.Thread] = None


def get_shadow() -> Optional[Any]:
    """
    Returns the active `DigitalShadow` instance.

    Reads `dashboard_backend.shadow_instance` first if `dashboard_backend` is loaded
    so tests or scripts mutating that attribute propagate seamlessly to all routers.
    """
    db_mod = sys.modules.get("dashboard_backend")
    if db_mod is not None and hasattr(db_mod, "shadow_instance"):
        return db_mod.shadow_instance
    return _shadow_instance


def set_shadow(inst: Optional[Any]) -> None:
    """Sets the active `DigitalShadow` instance and synchronizes `dashboard_backend` if loaded."""
    global _shadow_instance
    _shadow_instance = inst
    db_mod = sys.modules.get("dashboard_backend")
    if db_mod is not None:
        db_mod.shadow_instance = inst


def get_processing_thread() -> Optional[threading.Thread]:
    """Returns the background simulation worker thread reference, if running."""
    return _processing_thread


def set_processing_thread(thread: Optional[threading.Thread]) -> None:
    """Stores the background simulation worker thread reference and mirrors to `dashboard_backend`."""
    global _processing_thread
    _processing_thread = thread
    db_mod = sys.modules.get("dashboard_backend")
    if db_mod is not None:
        db_mod.processing_thread = thread
