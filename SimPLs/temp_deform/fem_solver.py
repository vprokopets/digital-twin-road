"""
SimPLs/temp_deform/fem_solver.py — 1D FEM Heat Conduction Solver
================================================================

Lightweight in-tree 1D finite-element solver for thermal conduction through
multi-layer pavement structures. Replaces external CALFEM dependencies with
pure NumPy linear algebra:
  - spring1e(k): 2x2 1D conduction/stiffness element
  - assem(edof, K, Ke): element assembly into global conductivity matrix
  - solveq(K, f, bc, bc_val): constrained linear system solver with Dirichlet BCs

Project: Digital Twin Road Demonstrator — Open Source Road Infrastructure Platform (MIT)
"""

from __future__ import annotations

import numpy as np


def spring1e(k: float) -> np.ndarray:
    """
    Return the 2x2 stiffness/conductance matrix for a 1D thermal conduction element.

    Args:
        k: Element thermal conductance or stiffness in W/(m^2*K) or N/m.

    Returns:
        A 2x2 matrix ``[[k, -k], [-k, k]]``.
    """
    return np.array([[k, -k], [-k, k]], dtype=float)


def assem(edof: np.ndarray, K: np.ndarray, Ke: np.ndarray) -> None:
    """
    Assemble element conductivity/stiffness matrix ``Ke`` into global matrix ``K``.

    Uses 1-based ``edof`` DOF indices to maintain convention and modifies ``K`` in-place.

    Args:
        edof: 1D array of 1-based global DOF indices (length 2 for 1D element).
        K: Global matrix modified in-place.
        Ke: Element stiffness/conductance matrix.
    """
    dofs = np.array(edof).flatten() - 1  # convert to 0-based indexing
    for i, gi in enumerate(dofs):
        for j, gj in enumerate(dofs):
            K[gi, gj] += Ke[i, j]


def solveq(
    K: np.ndarray,
    f: np.ndarray,
    bc: np.ndarray,
    bc_val: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Solve the constrained linear system ``K * a = f`` with Dirichlet boundary conditions.

    Args:
        K: Global stiffness/conductivity matrix of shape ``(n, n)``.
        f: Global right-hand-side load/flux vector of shape ``(n, 1)`` or ``(n,)``.
        bc: 1D array of 1-based DOF indices with prescribed Dirichlet values.
        bc_val: 1D array of prescribed values corresponding to ``bc`` indices.

    Returns:
        Tuple ``(a, r)`` containing the full solution nodal vector ``a`` of shape ``(n, 1)``
        and the reaction force/flux vector ``r`` of shape ``(n, 1)``.
    """
    n = K.shape[0]
    K_np = np.asarray(K, dtype=float)
    f_np = np.asarray(f, dtype=float).flatten().copy()

    # Convert 1-based boundary condition indices to 0-based
    bc0 = np.array(bc).flatten() - 1

    # Identify unconstrained (free) DOFs
    all_dofs = np.arange(n)
    free = np.setdiff1d(all_dofs, bc0)

    # Apply Dirichlet boundary conditions to RHS
    for idx, dof in enumerate(bc0):
        f_np[free] -= K_np[np.ix_(free, [dof])].flatten() * bc_val[idx]

    # Solve reduced unconstrained linear system
    K_free = K_np[np.ix_(free, free)]
    f_free = f_np[free]
    a_free = np.linalg.solve(K_free, f_free)

    # Assemble complete nodal solution vector
    a = np.zeros(n, dtype=float)
    a[bc0] = bc_val
    a[free] = a_free

    # Compute reactions (r = K * a - f)
    r = (K_np @ a).flatten() - np.asarray(f, dtype=float).flatten()

    return a.reshape(-1, 1), r.reshape(-1, 1)
