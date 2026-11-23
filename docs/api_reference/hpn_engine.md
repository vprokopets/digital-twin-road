# Heraklit Petri Net Engine (`hpn.py`)

The `hpn.py` module provides an executable, pure-Python implementation of Wolfgang Reisig's Compositional Hybrid Petri Nets and Heraklit module algebra.

---

## Classes & Data Structures

### `class hpn.HPNPlace`

Represents a Place in a Hybrid Petri Net.

* **Parameters:**
  - `id` (*str*): Unique place identifier (e.g. `"P_Sunny"`, `"P_AirTemp"`).
  - `label` (*str*): Human-readable label displayed in Vue Flow.
  - `kind` (*str*): `"discrete"` (integer token marking) or `"continuous"` (real fluid level).
  - `gate` (*str*): `"alpha"` (left interface), `"beta"` (right interface), `"fused"` (shared boundary), or `"internal"`.
  - `interface_tag` (*Optional[str]*): Matching semantic key used during algebraic composition.
  - `tokens` (*float*): Integer token count (discrete) or non-negative fluid level (continuous).

---

### `class hpn.HPNTransition`

Represents a Transition in a Hybrid Petri Net.

* **Parameters:**
  - `kind` (*str*): `"discrete"` (instantaneous guarded firing) or `"continuous"` (fluid flow rate $dx/dt = v_c(t)$).
  - `rate` (*float*): Firing velocity for continuous fluid arcs.
  - `enabled` (*bool*): Whether input places satisfy activation preconditions.

---

### `class hpn.HeraklitModule`

A composable Heraklit module $M = (\alpha(M), N(M), \beta(M))$.

* **Methods:**
  - `compose(other: HeraklitModule) -> HeraklitModule`: Algebraically fuses matching interface tags in $\beta(\text{self}) \cap \alpha(\text{other})$, producing a merged module.
  - `__matmul__(other: HeraklitModule) -> HeraklitModule`: Pythonic operator overload allowing `M1 @ M2` syntax for Heraklit composition $M_1 \bullet M_2$.

---

## High-Level Controller

### `class hpn.HeraklitHPNController()`

Manages the dynamic composition of environmental, material, and vehicle modules during co-simulation.

* **`step(...) -> Tuple[str, float, Optional[str]]`:**
  Executes one Hybrid Petri Net evaluation step:

  1. Builds $M_{\text{RSU}}$ from RSU weather and temperature states.
  2. Builds $M_{\text{Material}}$ from pavement physical parameters.
  3. Builds $M_{\text{Vehicle}}$ from vehicle kinematics and solver confidence.
  4. Composes: `self.composed_module = (m_rsu @ m_mat) @ m_veh`.
  5. Returns active solver mode, numerical accuracy, and fired transition ID.

* **`to_dict() -> Dict[str, Any]`:**
  Serializes the composed Petri Net into Vue Flow nodes and edges for interactive frontend visualization.
