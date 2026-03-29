"""
Atom Computing AC1000 — 4D Geometric Code Physical Qubit Estimation

Estimates the number of physical qubits required to run a quantum circuit
on Atom Computing's AC1000 processor using the [[96,6,8]] 4D geometric
code co-developed with Microsoft.

Methodology:
  1. Data qubits: The [[96,6,8]] code encodes 6 logical qubits per code
     block. With syndrome extraction ancillas (~48), each block uses ~144
     physical qubits total. Observed ratio on AC1000: ~24 physical/logical.
  2. Routing overhead: 1.1x — neutral atoms can be physically rearranged
     via optical tweezers, providing near all-to-all connectivity.
  3. Magic state factories: 5-to-1 distillation protocol demonstrated on
     neutral atoms. Each factory uses 5 code blocks × 96 = 480 qubits.
     Toffoli gates decompose into 7 T-gates each.

References:
  [1] Microsoft, "A Topologically Fault-Tolerant Quantum Computer with
      Four Dimensional Geometric Codes," arXiv:2506.15130 (2025).
  [2] Atom Computing + Microsoft, "Fault-tolerant quantum computation
      with a neutral atom processor," arXiv:2411.11822 (2024).
  [3] Microsoft Azure Quantum Blog, "Microsoft and Atom Computing offer
      a commercial quantum machine" (Nov 2024).
  [4] Bluvstein et al., "Logical quantum processor based on reconfigurable
      atom arrays," Nature 626, 58-65 (2024).
  [5] Gupta et al., "Experimental demonstration of logical magic state
      distillation," Nature (2025). (5-to-1 protocol on neutral atoms)
"""

import math

# ---------------------------------------------------------------------------
# AC1000 / 4D Geometric [[96,6,8]] constants
# ---------------------------------------------------------------------------

CODE_DISTANCE = 8
"""Code distance of the [[96,6,8]] 4D geometric code [1]."""

CODE_BLOCK_DATA = 96
"""Data qubits per code block [1]."""

CODE_BLOCK_SYNDROME = 48
"""Syndrome extraction ancilla qubits per code block (approximate) [1][2]."""

CODE_BLOCK_TOTAL = CODE_BLOCK_DATA + CODE_BLOCK_SYNDROME  # 144
"""Total physical qubits per code block (data + syndrome) [1][2]."""

LOGICALS_PER_BLOCK = 6
"""Logical qubits encoded per code block [1]."""

PHYSICAL_PER_LOGICAL = CODE_BLOCK_TOTAL // LOGICALS_PER_BLOCK  # 24
"""Effective physical-to-logical ratio, matches observed AC1000 ratio [2][3]."""

ROUTING_OVERHEAD = 1.1
"""Routing factor: near 1.0 due to atom rearrangement via optical tweezers [2][4]."""

LOGICAL_ERROR_PER_CYCLE = 1e-4
"""Estimated logical error rate per QEC cycle at d=8 [1]."""

# Magic state distillation (5-to-1 protocol on neutral atoms) [5]
FACTORY_QUBITS = 5 * CODE_BLOCK_DATA  # 480
"""Physical qubits per factory: 5 code blocks × 96 qubits (5-to-1 distillation) [5]."""

T_GATES_PER_TOFFOLI = 7
"""A Toffoli gate decomposes into 7 T/T† gates in the Clifford+T basis."""

T_STATES_PER_FACTORY = 100
"""Approximate T-state throughput per factory over a typical algorithm run."""

ERROR_CORRECTION_CODE = "4D Geometric [[96,6,8]]"
"""Human-readable name for the QEC code used."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_atom_resources(
    n_logical: int,
    n_t: int,
    n_toffoli: int,
) -> dict:
    """
    Estimate physical qubit requirements for Atom Computing AC1000 (4D geometric code).

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
        data_qubits         – physical qubits for data blocks + routing
        distillation_qubits – physical qubits for magic state factories
        code_distance       – 4D geometric code distance (8)
        logical_error_rate  – logical error per cycle
        num_t_gates         – total T-gate count (explicit + from Toffoli)
        num_factories       – number of magic state factories
        error_correction_code – name of the QEC code
    """
    n_logical = max(n_logical, 1)

    # --- Data qubits: ceil(n_logical / 6) code blocks × 144 × routing ---
    n_blocks = math.ceil(n_logical / LOGICALS_PER_BLOCK)
    data_qubits = math.ceil(n_blocks * CODE_BLOCK_TOTAL * ROUTING_OVERHEAD)

    # --- Magic state factory overhead ---
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
                "citation": "Microsoft, \"A Topologically Fault-Tolerant Quantum Computer with Four Dimensional Geometric Codes,\" arXiv:2506.15130 (2025).",
                "url": "https://arxiv.org/abs/2506.15130",
            },
            {
                "key": "2",
                "citation": "Atom Computing + Microsoft, \"Fault-tolerant quantum computation with a neutral atom processor,\" arXiv:2411.11822 (2024).",
                "url": "https://arxiv.org/abs/2411.11822",
            },
            {
                "key": "3",
                "citation": "Bluvstein et al., \"Logical quantum processor based on reconfigurable atom arrays,\" Nature 626, 58-65 (2024).",
                "url": "https://arxiv.org/abs/2312.03982",
            },
            {
                "key": "4",
                "citation": "Gupta et al., \"Experimental demonstration of logical magic state distillation,\" Nature (2025).",
                "url": None,
            },
        ],
    }
