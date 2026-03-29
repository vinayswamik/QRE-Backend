"""
Quantinuum Helios — Color Code Physical Qubit Estimation

Estimates the number of physical qubits required to run a quantum circuit
on Quantinuum's Helios processor using the [[7,1,3]] Steane color code
with code-switching to the [[15,1,3]] quantum Reed-Muller code for T-gates.

Methodology:
  1. Data qubits: Each logical qubit uses 7 data + 4 flag/ancilla = 11
     physical qubits in the Steane [[7,1,3]] color code at distance 3.
  2. Routing overhead: 1.0x — trapped-ion QCCD architecture provides
     all-to-all connectivity via ion shuttling, eliminating SWAP overhead.
  3. T-gate factories: Quantinuum uses code switching (not distillation)
     between the Steane code (Cliffords) and [[15,1,3]] Reed-Muller code
     (transversal T-gate). Each factory needs only 28 physical qubits
     (15 QRM + 7 Steane + 6 ancilla) — ~10x more efficient than surface
     code distillation factories.

References:
  [1] Quantinuum, "Helios: A 98-qubit trapped-ion quantum computer,"
      arXiv:2511.05465 (2025).
  [2] Quantinuum, "Experimental Demonstration of High-Fidelity Logical
      Magic States from Code Switching," Phys. Rev. X, arXiv:2506.14169 (2025).
  [3] Quantinuum, "Breaking even with magic: high-fidelity logical
      non-Clifford gate," arXiv:2506.14688 (2025).
  [4] Quantinuum Helios Product Data Sheet v1.01 (Jan 2026).
  [5] Steane, "Multiple-particle interference and quantum error correction,"
      Proc. R. Soc. A 452, 2551-2577 (1996).
"""

import math

# ---------------------------------------------------------------------------
# Helios / Color Code [[7,1,3]] constants
# ---------------------------------------------------------------------------

CODE_DISTANCE = 3
"""Code distance of the [[7,1,3]] Steane color code [5]."""

DATA_QUBITS_PER_LOGICAL = 7
"""Data qubits per logical qubit in the Steane code [5]."""

ANCILLA_QUBITS_PER_LOGICAL = 4
"""Flag/ancilla qubits for fault-tolerant syndrome extraction [1]."""

PHYSICAL_PER_LOGICAL = DATA_QUBITS_PER_LOGICAL + ANCILLA_QUBITS_PER_LOGICAL  # 11
"""Total physical qubits per logical qubit [1]."""

ROUTING_OVERHEAD = 1.0
"""Routing factor: all-to-all connectivity via ion shuttling [1]."""

LOGICAL_ERROR_PER_CYCLE = 5e-4
"""Estimated logical error rate per QEC cycle at d=3 [1]."""

# Code-switching T-gate factory [2][3]
FACTORY_QUBITS = 28
"""Physical qubits per code-switching factory: 15 (QRM) + 7 (Steane) + 6 (ancilla) [2]."""

T_GATES_PER_TOFFOLI = 7
"""A Toffoli gate decomposes into 7 T/T† gates in the Clifford+T basis."""

T_STATES_PER_FACTORY = 100
"""Approximate T-state throughput per factory over a typical algorithm run."""

ERROR_CORRECTION_CODE = "Color Code [[7,1,3]] + Reed-Muller [[15,1,3]]"
"""Human-readable name for the QEC code used."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_quantinuum_resources(
    n_logical: int,
    n_t: int,
    n_toffoli: int,
) -> dict:
    """
    Estimate physical qubit requirements for Quantinuum Helios (color code).

    Parameters
    ----------
    n_logical : int
        Number of logical qubits in the circuit.
    n_t : int
        Number of explicit T / T† gates in the circuit.
    n_toffoli : int
        Number of Toffoli (CCX) gates in the circuit.

    Returns
    -------
    dict with keys:
        physical_qubits     – total physical qubits required
        data_qubits         – physical qubits for logical data
        distillation_qubits – physical qubits for code-switching factories
        code_distance       – color code distance (3)
        logical_error_rate  – logical error per cycle
        num_t_gates         – total T-gate count (explicit + from Toffoli)
        num_factories       – number of code-switching factories
        error_correction_code – name of the QEC code
    """
    n_logical = max(n_logical, 1)

    # --- Data qubits: n_logical * 11 (no routing overhead) ---
    data_qubits = math.ceil(n_logical * PHYSICAL_PER_LOGICAL * ROUTING_OVERHEAD)

    # --- Code-switching factory overhead ---
    total_t_gates = n_t + T_GATES_PER_TOFFOLI * n_toffoli

    if total_t_gates > 0:
        n_factories = max(1, math.ceil(total_t_gates / T_STATES_PER_FACTORY))
        distillation_qubits = n_factories * FACTORY_QUBITS
    else:
        n_factories = 0
        distillation_qubits = 0

    # --- Total ---
    physical_qubits = data_qubits + distillation_qubits

    return {
        "physical_qubits": physical_qubits,
        "data_qubits": data_qubits,
        "distillation_qubits": distillation_qubits,
        "code_distance": CODE_DISTANCE,
        "logical_error_rate": LOGICAL_ERROR_PER_CYCLE,
        "num_t_gates": total_t_gates,
        "num_factories": n_factories,
        "error_correction_code": ERROR_CORRECTION_CODE,
        "physical_qubits_per_logical": PHYSICAL_PER_LOGICAL,
        "routing_overhead": ROUTING_OVERHEAD,
        "factory_qubits_each": FACTORY_QUBITS,
        "t_states_per_factory": T_STATES_PER_FACTORY,
        "references": [
            {
                "key": "1",
                "citation": "Quantinuum, \"Helios: A 98-qubit trapped-ion quantum computer,\" arXiv:2511.05465 (2025).",
                "url": "https://arxiv.org/abs/2511.05465",
            },
            {
                "key": "2",
                "citation": "Quantinuum, \"Experimental Demonstration of High-Fidelity Logical Magic States from Code Switching,\" arXiv:2506.14169 (2025).",
                "url": "https://arxiv.org/abs/2506.14169",
            },
            {
                "key": "3",
                "citation": "Quantinuum, \"Breaking even with magic: high-fidelity logical non-Clifford gate,\" arXiv:2506.14688 (2025).",
                "url": "https://arxiv.org/abs/2506.14688",
            },
            {
                "key": "4",
                "citation": "Quantinuum Helios Product Data Sheet v1.01 (Jan 2026).",
                "url": None,
            },
            {
                "key": "5",
                "citation": "Steane, \"Multiple-particle interference and quantum error correction,\" Proc. R. Soc. A 452, 2551-2577 (1996).",
                "url": None,
            },
        ],
    }
