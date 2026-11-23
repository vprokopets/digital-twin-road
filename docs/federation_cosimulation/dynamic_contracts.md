# Dynamic Simulation SLA Contracts

To ensure numerical fidelity across distributed V2X edge cells, the platform implements **Design-by-Contract** co-simulation via the `DynamicFederationContract` class in `world/federation.py`.

---

## Contract Lifecycle State Machine

A bilateral simulation contract transitions through four formal operational states:

```text
[ Vehicle Enters 10 km Cell ]
             │
             v
+────────────────────────────+
|   CONTRACT_NEGOTIATION     | <── Initial V2X Handshake (RSSI >= -85 dBm)
+────────────┬───────────────+
             │
             v
+────────────────────────────+
|   ACTIVE_FAST_SLOW_SYNC    | <── Normal 5.0 s boundary exchange
+────────────┬───────────────+
             │
     ┌───────┴────────────────────────┐
     │ Accuracy < 0.90                │ Egress into next cell
     v                                v
+────────────────────────────+   +────────────────────────────+
|  FOM_BASIS_RECALIBRATION   |   |       CELL_HANDOVER        |
|  (Full FEM Fallback Step)  |   |  (Session Transfer to RSU) |
+────────────┬───────────────+   +────────────┬───────────────+
             │                                │
             v                                v
     Accuracy Restored                Contract Re-Established
```

---

## Contract Schema & Attributes

Each active contract maintains the following verified attributes:

| Field | Type | Description |
| :--- | :--- | :--- |
| `contract_id` | String | Unique contract identifier (e.g. `HLA-RSU_01-V0101`). |
| `federation_name` | String | Federation identifier (`A14_Corridor_Road_Federation`). |
| `rsu_id` / `vehicle_id` | String | The two participating federates bound by the agreement. |
| `sla_accuracy_threshold`| Float | Minimum permissible numerical confidence (default: `0.90`). |
| `current_accuracy` | Float | Real-time surrogate confidence metric ($0.0 \text{ to } 1.0$). |
| `solver_mode` | String | Active solver feature: `POD` (Fast Surrogate) vs. `FEM` (Exact Model). |
| `heraklit_formula` | String | Executable algebraic formula: $M_{\text{RSU}} \bullet M_{\text{Material}} \bullet M_{\text{Vehicle}}$. |
| `sync_ticks` | Integer | Cumulative fast-slow synchronization steps successfully executed. |
| `recalibrations_count` | Integer | Total fallback recalibrations triggered by SLA breaches. |
| `recent_interactions` | List | Bounded historical event log of the last 8 IEEE 1516 interaction events. |

---

## Corridor Federation Manager (Corridor RTI)

The `CorridorFederationManager` acts as the centralized **Run-Time Infrastructure (Corridor RTI)**:

* Maintains `self.contracts_by_vehicle: Dict[str, DynamicFederationContract]`.
* Evaluates cell distance and triggers automatic handovers when a vehicle passes the geometric midpoint between two RSUs.
* Exposes `get_federation_summary()`, broadcasting real-time metrics (active contracts count, fast-slow syncs, total handovers) to the frontend HUD badge.
