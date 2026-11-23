"""
world/federation.py — HLA / FOM Federated Simulation & Dynamic RSU–Vehicle Contracts
====================================================================================

Project: Digital Twin Road Demonstrator — Open Source Road Infrastructure Platform (MIT)

Architectural Overview for Successor
------------------------------------
This module implements **Federated Co-Simulation** between Roadside Units (RSUs) and
Heavy Goods Vehicles (HGVs) in the spirit of:
1. **IEEE 1516 High-Level Architecture (HLA)** & **Federation Object Model (FOM)**
   (`configs/fom_schema.json`).
2. **Design-by-Contract (Dynamic SLA Negotiation)** across V2X coverage cells.
3. **Wolfgang Reisig's HERAKLIT Composition**: Each active contract represents the
   live algebraic composition `M_RSU[i] • M_Material • M_Vehicle[j]`, fusing the RSU's
   exported environmental gate `beta(M_RSU)` with the Vehicle's imported boundary gate
   `alpha(M_Vehicle)`, and vice-versa for road damage feedback.

Topic of the Federation: Fast–Slow Multi-Scale Co-Simulation
------------------------------------------------------------
- **Slow Environmental Scale (RSU Federate, Δt_slow = 5.0 s)**:
  Computes and publishes local micro-climate (`WeatherState`, `AirTemperature`,
  `RoadSurfaceTemperature`), hydrological soil cooling (`SoilTemperature`), and
  pavement structural layer configuration (`RoadStructure_0..4`).
- **Fast Mechanical & Kinematic Scale (Vehicle Federate, Δt_fast = 0.05 s)**:
  Computes and publishes vehicle kinematics (`Kilometer`, `Velocity`, `Weight`),
  tire–pavement contact response (`POD` fast surrogate vs. `FEM` full-order solver),
  projection accuracy (`PODAccuracy`), and local fatigue/rutting `DamageIncrement`.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional
import datetime
import json


@dataclass
class DynamicFederationContract:
    """
    Live bilateral HLA/FOM and Heraklit simulation contract.

    Connects a serving Roadside Unit (`rsu_id`) with an in-transit Vehicle (`vehicle_id`).
    """
    contract_id: str
    federation_name: str
    vehicle_id: str
    rsu_id: str
    rsu_name: str
    rsu_town: str
    rsu_station_km: float
    state: str = "ACTIVE_FAST_SLOW_SYNC"  # 'ACTIVE_FAST_SLOW_SYNC' | 'FOM_BASIS_RECALIBRATION' | 'CELL_HANDOVER'
    heraklit_formula: str = ""
    distance_km: float = 0.0
    rssi_dbm: int = -65
    sla_accuracy_threshold: float = 0.90
    current_accuracy: float = 1.0
    solver_mode: str = "POD"              # 'POD' (Fast Surrogate) | 'FEM' (Slow Exact FOM)
    sync_ticks: int = 0
    recalibrations_count: int = 0
    handover_count: int = 0
    previous_rsu_id: Optional[str] = None
    established_at: str = ""
    last_sync_at: str = ""
    published_by_rsu: Dict[str, Any] = field(default_factory=dict)
    published_by_vehicle: Dict[str, Any] = field(default_factory=dict)
    recent_interactions: List[Dict[str, str]] = field(default_factory=list)

    def log_interaction(self, interaction_class: str, sender: str, receiver: str, summary: str) -> None:
        """Appends an IEEE 1516 HLA Interaction event to the bounded contract log."""
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.recent_interactions.append({
            "timestamp": now_str,
            "interaction": interaction_class,
            "sender": sender,
            "receiver": receiver,
            "summary": summary,
        })
        if len(self.recent_interactions) > 8:
            self.recent_interactions = self.recent_interactions[-8:]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the contract for the REST API, SSE stream, and Inspector UI."""
        return {
            "contract_id": self.contract_id,
            "federation_name": self.federation_name,
            "hla_standard": "IEEE 1516 / Heraklit",
            "vehicle_id": self.vehicle_id,
            "rsu_id": self.rsu_id,
            "rsu_name": self.rsu_name,
            "rsu_town": self.rsu_town,
            "rsu_station_km": self.rsu_station_km,
            "state": self.state,
            "heraklit_formula": self.heraklit_formula,
            "distance_km": round(self.distance_km, 2),
            "rssi_dbm": self.rssi_dbm,
            "sla_accuracy_threshold": self.sla_accuracy_threshold,
            "sla_min_pod_confidence": self.sla_accuracy_threshold,
            "current_accuracy": round(self.current_accuracy, 4),
            "pod_confidence": round(self.current_accuracy, 4),
            "sla_compliant": self.current_accuracy >= self.sla_accuracy_threshold,
            "solver_mode": self.solver_mode,
            "active_solver": self.solver_mode,
            "slow_step_sec": 5.0,
            "fast_step_sec": 0.05,
            "time_scales": {
                "slow_rsu_env_sec": 5.0,
                "fast_vehicle_mech_sec": 0.05,
                "coupling_ratio": "100:1 (Fast-Slow Multi-Rate)",
            },
            "sync_ticks": self.sync_ticks,
            "recalibrations_count": self.recalibrations_count,
            "recalibrations_triggered": self.recalibrations_count,
            "handover_count": self.handover_count,
            "previous_rsu_id": self.previous_rsu_id,
            "established_at": self.established_at,
            "last_sync_at": self.last_sync_at,
            "published_by_rsu": self.published_by_rsu,
            "published_by_vehicle": self.published_by_vehicle,
            "recent_interactions": list(reversed(self.recent_interactions)),
        }


class CorridorFederationManager:
    """
    Central Run-Time Infrastructure (Corridor RTI) contract coordinator.

    Manages all dynamic RSU-Vehicle co-simulation contracts along the corridor.
    """

    def __init__(self) -> None:
        configs_dir = Path(__file__).resolve().parent.parent / "configs"
        fom_path = configs_dir / "fom_schema.json"
        if fom_path.exists():
            with open(fom_path, "r", encoding="utf-8") as f:
                self.fom_schema: Dict[str, Any] = json.load(f)
        else:
            self.fom_schema = {"federation_name": "A14_Corridor_Road_Federation"}

        self.federation_name: str = self.fom_schema.get("federation_name", "A14_Corridor_Road_Federation")
        self.contracts_by_vehicle: Dict[str, DynamicFederationContract] = {}

    def sync_vehicle_contract(
        self,
        vehicle_id: Any,
        vehicle_params: Dict[str, Any],
        just_switched_solver: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create, update, or hand over the dynamic RSU-Vehicle contract for `vehicle_id`."""
        vid_str = str(vehicle_id)
        state_dict = vehicle_params.get("State", {})
        rsu_id = str(state_dict.get("RoadsideUnit") or "rsu_00")
        rsu_name = str(state_dict.get("RoadsideUnitName") or f"RSU ({rsu_id})")
        rsu_town = str(state_dict.get("RoadsideUnitTown") or "A14 Corridor")
        rsu_station = float(state_dict.get("RoadsideUnitStation") or 0.0)
        dist_km = float(state_dict.get("RoadsideUnitDist") or 1.5)
        rssi_dbm = int(round(-55.0 - (dist_km * 2.8)))

        mech_sim = vehicle_params.get("MechanicalSimulation", {})
        raw_model = str(mech_sim.get("Model", "POD"))
        solver_mode = "POD" if raw_model == "POD" else "FEM"
        accuracy = float(mech_sim.get("Accuracy", 1.0))
        threshold = float(mech_sim.get("Threshold", 0.90))

        road_type = "Asphalt"
        road_md = state_dict.get("RoadMetadata", {})
        if isinstance(road_md, dict) and "RoadType" in road_md:
            road_type = list(road_md["RoadType"].keys())[0]

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        heraklit_expr = f"M_RSU[{rsu_id}] • M_Material[{road_type}] • M_Vehicle[{vid_str[-4:]}:{solver_mode}]"

        contract = self.contracts_by_vehicle.get(vid_str)
        if contract is None:
            # Instantiate new Dynamic Federation Contract (JOIN_FEDERATION)
            contract = DynamicFederationContract(
                contract_id=f"HLA-{rsu_id.upper()}-V{vid_str[-4:]}",
                federation_name=self.federation_name,
                vehicle_id=vid_str,
                rsu_id=rsu_id,
                rsu_name=rsu_name,
                rsu_town=rsu_town,
                rsu_station_km=rsu_station,
                state="ACTIVE_FAST_SLOW_SYNC",
                heraklit_formula=heraklit_expr,
                distance_km=dist_km,
                rssi_dbm=rssi_dbm,
                sla_accuracy_threshold=threshold,
                current_accuracy=accuracy,
                solver_mode=solver_mode,
                sync_ticks=1,
                established_at=now_str,
                last_sync_at=now_str,
            )
            contract.log_interaction(
                "ContractNegotiation",
                f"Vehicle #{vid_str[-4:]}",
                rsu_id.upper(),
                f"Joined federation cell at km {rsu_station:.1f} (RSSI {rssi_dbm} dBm)",
            )
            self.contracts_by_vehicle[vid_str] = contract
        else:
            contract.sync_ticks += 1
            contract.last_sync_at = now_str
            contract.distance_km = dist_km
            contract.rssi_dbm = rssi_dbm
            contract.current_accuracy = accuracy
            contract.solver_mode = solver_mode
            contract.heraklit_formula = heraklit_expr

            # Check for RSU Cell Handover
            if contract.rsu_id != rsu_id:
                old_rsu = contract.rsu_id
                contract.previous_rsu_id = old_rsu
                contract.rsu_id = rsu_id
                contract.rsu_name = rsu_name
                contract.rsu_town = rsu_town
                contract.rsu_station_km = rsu_station
                contract.handover_count += 1
                contract.contract_id = f"HLA-{rsu_id.upper()}-V{vid_str[-4:]}"
                contract.state = "CELL_HANDOVER"
                contract.log_interaction(
                    "CorridorCellHandover",
                    old_rsu.upper(),
                    rsu_id.upper(),
                    f"Heraklit re-composition: detached {old_rsu} → bound {rsu_id} (km {rsu_station:.1f})",
                )
            elif solver_mode == "FEM":
                contract.state = "FOM_BASIS_RECALIBRATION"
            else:
                contract.state = "ACTIVE_FAST_SLOW_SYNC"

        # Log solver fidelity transitions (Fast POD <-> Slow FEM)
        if just_switched_solver == "TO_FEM":
            contract.recalibrations_count += 1
            contract.state = "FOM_BASIS_RECALIBRATION"
            contract.log_interaction(
                "FOMBasisRecalibration",
                f"Vehicle #{vid_str[-4:]}",
                rsu_id.upper(),
                f"POD drift ({accuracy:.3f} <= {threshold:.2f}): switched to Full-Order FEM",
            )
        elif just_switched_solver == "TO_POD":
            contract.state = "ACTIVE_FAST_SLOW_SYNC"
            contract.log_interaction(
                "FOMBasisRecalibration",
                rsu_id.upper(),
                f"Vehicle #{vid_str[-4:]}",
                "POD reduced basis synchronized; resumed fast ROM execution (acc=1.00)",
            )
        elif contract.sync_ticks % 4 == 1:
            # Periodic Fast-Slow Boundary Sync interaction log
            contract.log_interaction(
                "FastSlowBoundarySync",
                rsu_id.upper(),
                f"Vehicle #{vid_str[-4:]}",
                f"Env push: {state_dict.get('WeatherState', 'Sunny')}, T_surf={float(state_dict.get('RoadSurfaceTemperature', 25.0)):.1f}°C",
            )

        # Update Published Object Attributes (SOM -> FOM)
        contract.published_by_rsu = {
            "WeatherState": state_dict.get("WeatherState", "Sunny"),
            "AirTemperature": round(float(state_dict.get("AirTemperature", 22.0)), 2),
            "RoadSurfaceTemperature": round(float(state_dict.get("RoadSurfaceTemperature", 26.0)), 2),
            "SoilTemperature": round(float(state_dict.get("SoilTemperature", 14.5)), 2),
            "RoadStructure": state_dict.get("RoadStructure", "RoadStructure_1"),
            "RoadMaterial": road_type,
        }
        contract.published_by_vehicle = {
            "Kilometer": round(float(vehicle_params.get("Kilometer", 0.0)), 2),
            "Velocity": round(float(vehicle_params.get("Velocity", 90.0)), 1),
            "Weight": int(vehicle_params.get("Weight", 35000)),
            "SolverMode": solver_mode,
            "PODAccuracy": round(accuracy, 4),
            "DamageIncrement": round(float(vehicle_params.get("Damage", 0.05)), 4),
        }

        return contract.to_dict()

    def remove_vehicle_contract(self, vehicle_id: Any) -> None:
        """Cleans up contract when a vehicle exits the corridor."""
        self.contracts_by_vehicle.pop(str(vehicle_id), None)

    def get_contracts_for_rsu(self, rsu_id: str) -> List[Dict[str, Any]]:
        """Returns all active vehicle contracts currently bound to `rsu_id`."""
        target = str(rsu_id)
        return [
            c.to_dict()
            for c in self.contracts_by_vehicle.values()
            if str(c.rsu_id) == target
        ]

    def get_federation_summary(self) -> Dict[str, Any]:
        """Returns aggregate HLA/Heraklit federation statistics across the corridor."""
        contracts = list(self.contracts_by_vehicle.values())
        return {
            "active_contracts_count": len(contracts),
            "total_Negotiations": len(contracts),
            "total_FastSlowSyncs": sum(c.sync_ticks for c in contracts),
            "total_Recalibrations": sum(c.recalibrations_count for c in contracts),
            "total_Handovers": sum(c.handover_count for c in contracts),
        }
