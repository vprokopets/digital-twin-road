# Wolfgang Reisig's Heraklit Algebra & Hybrid Petri Nets

The platform implements the formal mathematical framework developed by **Prof. Dr. Wolfgang Reisig** (Humboldt-Universität zu Berlin) for compositional cyber-physical systems: **HERAKLIT Compositional Hybrid Petri Nets**.

---

## Mathematical Definition of a Heraklit Module

In Heraklit, any concurrent system or physical subsystem is represented as an algebraic module:

$$M = \big(\alpha(M), \; N(M), \; \beta(M)\big)$$

where:

* $\alpha(M)$ (Left Interface Gate): The set of imported places and transitions through which the module receives tokens or continuous fluid flows from upstream environments.
* $N(M)$ (Interior Net): An internal Hybrid Petri Net comprising:
  - Discrete places $P_d$ (integer token markings $m \in \{0, 1, 2, \dots\}$).
  - Continuous fluid places $P_c$ (real-valued fluid levels $x \in \mathbb{R}_{\ge 0}$).
  - Discrete transitions $T_d$ (instantaneous guarded firing).
  - Continuous transitions $T_c$ (differential flow rate $dx/dt = v_c(t)$).
  - Directed arcs (flow arcs, read/test arcs, inhibitor arcs, reset arcs).
* $\beta(M)$ (Right Interface Gate): The set of exported places and transitions exposed to downstream systems.

---

## The Heraklit Composition Operator ($\bullet$)

Two Heraklit modules $M_1$ and $M_2$ are composed via the associative interface-fusion operator:

$$M_{\text{composed}} = M_1 \bullet M_2$$

where $M_1$ is the upstream exporting module (providing states through $\beta(M_1)$), $M_2$ is the downstream importing module (consuming states through $\alpha(M_2)$), and $\bullet$ fuses matching interface gates into a single unified transition net. In our pure-Python implementation (`hpn.py`), this operator is overloaded directly using Python's matrix multiplication syntax:

```python
# Pure Python Heraklit Module Composition
M_composed = M1 @ M2
```

### Boundary Gate Fusion Mechanics

When $M_1 \bullet M_2$ is evaluated, matching interface tags in the right gate of $M_1$ and the left gate of $M_2$ are algebraically fused:

$$\beta(M_1) \cap \alpha(M_2) \implies \text{Shared Fused Boundary Places / Transitions}$$

1. If place $p_1 \in \beta(M_1)$ and place $p_2 \in \alpha(M_2)$ share tag $\tau$, they are merged into a single boundary place $p_{\text{fused}}$ marked with `gate = 'fused'`.
2. All incoming arcs to $p_2$ and outgoing arcs from $p_1$ are automatically remapped to $p_{\text{fused}}$.
3. The remaining gates form the external boundary of the composed system:

$$\alpha(M_1 \bullet M_2) = \alpha(M_1) \cup \big(\alpha(M_2) \setminus \beta(M_1)\big)$$

$$\beta(M_1 \bullet M_2) = \beta(M_2) \cup \big(\beta(M_1) \setminus \alpha(M_2)\big)$$

where the set operators govern external interface visibility across composition:

* $\cap$: Shared interface tags between $\beta(M_1)$ and $\alpha(M_2)$ that merge into coupled interior places or transitions.
* $\cup$: Union of remaining unmatched left ($\alpha$) and right ($\beta$) gates exposed on the outer module boundary.
* $\setminus$: Set difference removing internal gates already satisfied across the fused boundary.

### Associativity Theorem

The composition operator strictly satisfies associativity:

$$(M_1 \bullet M_2) \bullet M_3 \equiv M_1 \bullet (M_2 \bullet M_3)$$

Here $\equiv$ denotes structural and behavioral net isomorphism up to tag-preserving relabeling. This property guarantees that whether an edge RSU and a pavement layer are composed first, or the pavement layer and a freight vehicle are composed first, the resulting physical continuum is mathematically identical.

---

## The Highway Demonstrator Composed Equation

In the running simulation (`hpn.py`), every passing vehicle evaluates the ternary composition linking active RSU communication cell $i$ and individual vehicle federate $j$:

$$M_{\text{System}} = \Big( M_{\text{RSU}}[i] \;\bullet\; M_{\text{Material}}[\text{Asphalt}] \Big) \;\bullet\; M_{\text{Vehicle}}[j]$$

| Module | Interface Role | Domain Responsibilities |
| :--- | :--- | :--- |
| **$M_{\text{RSU}}$** | Environmental Provider ($\beta$) | Exports discrete weather state places (Sunny, Cloudy, Rainy) and continuous temperature fluid levels. |
| **$M_{\text{Material}}$** | Pavement Transducer ($\alpha \cap \beta$) | Fuses with RSU weather; parameterizes thermal conductivity, solar absorption, and surface albedo. |
| **$M_{\text{Vehicle}}$** | Mechanical Solver ($\alpha$) | Fuses with pavement material; monitors surrogate accuracy SLA and fires solver-mode transitions. |

---

## Coupling with FODA Feature Models (`fm.py`)

The discrete token marking $M_d$ of the Petri Net maintains a 1-to-1 bijective mapping with active leaves in the **FODA Feature Tree** (Feature-Oriented Domain Analysis):

* A token in discrete place $P_{\text{Asphalt}}$ activates the synthesized `AsphaltMixin` in Python.
* A token in discrete place $P_{\text{FastSurrogate}}$ sets the active mechanical solver to the Boussinesq surrogate.
* Continuous transition firing rates $v_c(t)$ are parameterized directly by methods on the active synthesized Mixin class.
