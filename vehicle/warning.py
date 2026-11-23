"""
vehicle/warning.py — Structural Road Anomaly & Warning Point Entity
===================================================================

Project: Digital Twin Road Demonstrator

Represents a localized road surface or subbase anomaly detected by an in-transit
Heavy Goods Vehicle (or triggered manually during demonstrations) and assigned to
the nearest Roadside Unit (RSU) for autonomous UAV (AerialDrone) inspection.
"""

from __future__ import annotations
import datetime
import random
from typing import Optional, List, Dict, Any

ANOMALY_CATALOG = [
    ("Viscoelastic Rutting Hotspot", "High", "Surface SMA 11 S permanent wheel-path depression > 8 mm"),
    ("Thermal Fatigue Micro-Crack", "Moderate", "Transverse surface cracking induced by steep ΔT gradient"),
    ("Binder-Base Delamination", "Critical", "Interlayer shear bond degradation between AC 16 B S and AC 22 T S"),
    ("Subbase Moisture Voiding", "High", "Local loss of Winkler subgrade support due to water table seepage"),
]


class Warning:
    """
    Road anomaly warning point with full inspection lifecycle tracking.

    Transitions through `'New' -> 'Under Inspection' -> 'Inspected'`.
    """

    def __init__(
        self,
        position: float,
        direction: int = 1,
        vehicle_id: Optional[Any] = None,
        vehicle_weight: Optional[float] = None,
        surface_temp: Optional[float] = None,
        anomaly_type: Optional[str] = None,
        severity: Optional[str] = None,
        velocity_kmh: Optional[float] = None,
    ) -> None:
        self.id: str = f"warn_{int(random.uniform(1000, 9999))}"
        self.position: float = round(float(position), 3)
        self.direction: int = direction
        self.carriageway: str = "Dresden → Leipzig" if direction == 1 else "Leipzig → Dresden"
        self.coordinates: Optional[List[float]] = None
        self.state: str = "New"  # 'New' | 'Under Inspection' | 'Inspected'
        self.created_at: str = datetime.datetime.now().strftime("%H:%M:%S")
        self.inspected_at: Optional[str] = None
        self.inspected_ticks: int = 0

        cat_name, cat_sev, cat_desc = random.choice(ANOMALY_CATALOG)
        self.anomaly_type: str = anomaly_type or cat_name
        self.severity: str = severity or cat_sev
        self.description: str = cat_desc

        if vehicle_id is None:
            self.trigger_vehicle_id: str = "HGV-101"
        else:
            raw_vid = str(vehicle_id).strip()
            self.trigger_vehicle_id = f"HGV-{raw_vid}" if raw_vid.isdigit() else raw_vid

        self.trigger_vehicle_weight_kg: int = int(vehicle_weight or random.randint(32000, 39500))
        self.trigger_velocity_kmh: float = round(float(velocity_kmh or random.uniform(84.0, 93.0)), 1)
        self.surface_temp_c: float = round(float(surface_temp or 26.5), 1)
        self.estimated_rut_depth_mm: float = round(random.uniform(5.6, 9.4), 1)
        self.confidence_score: float = round(random.uniform(0.91, 0.98), 2)

        # Populated by World.register_warning() and updated in World.warning_handling()
        self.segment_id: str = ""
        self.segment_name: str = ""
        self.segment_health: int = 80
        self.road_structure: str = "RoadStructure_1"
        self.assigned_rsu_id: str = ""
        self.assigned_rsu_name: str = ""
        self.assigned_rsu_dist_km: float = 0.0
        self.assigned_drone_id: Optional[str] = None
        self.drone_flight_state: str = "Queued for Dispatch"
        self.inspection_progress_pct: float = 0.0

    def update_state(self, state: str) -> None:
        """Update warning lifecycle state and stamp completion metadata when inspected."""
        self.state = state
        if state == "Inspected":
            self.inspected_at = datetime.datetime.now().strftime("%H:%M:%S")
            self.inspection_progress_pct = 100.0
            self.drone_flight_state = "Mission Complete"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes warning metadata for GeoJSON properties and the Inspector Panel."""
        return {
            "id": self.id,
            "State": self.state,
            "AnomalyType": self.anomaly_type,
            "Severity": self.severity,
            "Description": self.description,
            "Kilometer": self.position,
            "Position": self.position,
            "Direction": self.direction,
            "Carriageway": self.carriageway,
            "CreatedAt": self.created_at,
            "InspectedAt": self.inspected_at or "Pending",
            "TriggerVehicleID": self.trigger_vehicle_id,
            "TriggeredByVehicle": self.trigger_vehicle_id,
            "TriggerVehicleWeight": self.trigger_vehicle_weight_kg,
            "TriggerWeightKg": self.trigger_vehicle_weight_kg,
            "TriggerVelocityKmh": self.trigger_velocity_kmh,
            "SurfaceTempAtTrigger": self.surface_temp_c,
            "EstimatedRutDepthMm": self.estimated_rut_depth_mm,
            "ConfidenceScore": self.confidence_score,
            "SegmentID": self.segment_id,
            "SegmentName": self.segment_name,
            "SegmentHealth": self.segment_health,
            "RoadStructure": self.road_structure,
            "AssignedRSU": self.assigned_rsu_id,
            "AssignedRSUName": self.assigned_rsu_name,
            "AssignedRSUDistKm": round(self.assigned_rsu_dist_km, 2),
            "AssignedDroneID": self.assigned_drone_id or "Awaiting Dispatch",
            "DroneFlightState": self.drone_flight_state,
            "InspectionProgressPct": round(self.inspection_progress_pct, 1),
            "DroneMissionProgressPct": round(self.inspection_progress_pct, 1),
        }
