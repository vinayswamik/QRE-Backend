"""
IonQ Forte Enterprise — BB5 Code Physical Qubit Estimation

Estimates the number of physical qubits required to run a quantum circuit
on IonQ's Forte Enterprise processor using the BB5 [[48,4,7]] code.

Methodology:
  1. Data qubits: The [[48,4,7]] BB5 code encodes 4 logical qubits into
     48 physical qubits per code block at distance 7.
  2. Routing overhead: 1.0x — trapped-ion all-to-all connectivity
     eliminates SWAP-gate routing entirely.
  3. Magic state factories: Constant-overhead magic state injection into
     qLDPC codes. Each factory uses one code block (~48 physical qubits).
     Toffoli gates decompose into 7 T-gates each.

BB5 codes achieve the same logical error rate as the distance-7 surface
code while using 4x fewer physical qubits per logical qubit.

References:
  [1] Maurya et al., "BB5: A Near-Optimal Quantum Error Correcting Code
      for Trapped-Ion Quantum Computers," arXiv:2503.22071 (2025).
      Published in Quantum journal, Nov 2025.
  [2] IonQ Blog, "Our novel, efficient approach to quantum error correction"
      ionq.com/blog/our-novel-efficient-approach-to-quantum-error-correction
  [3] Error Correction Zoo, "BB5 code"
      errorcorrectionzoo.org/c/bb5
  [4] IonQ, "Forte Enterprise specifications"
      ionq.com/quantum-systems/forte-enterprise
  [5] Wills et al., "Constant-Overhead Magic State Injection,"
      arXiv:2505.06981 (2025).
"""

import math

# ---------------------------------------------------------------------------
# Forte Enterprise / BB5 [[48,4,7]] constants
# ---------------------------------------------------------------------------

CODE_DISTANCE = 7
"""Code distance of the [[48,4,7]] BB5 code [1]."""

CODE_BLOCK_QUBITS = 48
"""Physical qubits per BB5 code block [1]."""

LOGICALS_PER_BLOCK = 4
"""Logical qubits encoded per code block [1]."""

PHYSICAL_PER_LOGICAL = CODE_BLOCK_QUBITS // LOGICALS_PER_BLOCK  # 12
"""Effective physical-to-logical ratio [1]."""

ROUTING_OVERHEAD = 1.0
"""Routing factor: all-to-all trapped-ion connectivity, no SWAP overhead [2]."""

LOGICAL_ERROR_PER_CYCLE = 5e-5
"""Logical error rate per QEC cycle at d=7, p_phys~1e-3 [1]."""

# Magic state injection (constant-overhead for qLDPC codes) [5]
FACTORY_QUBITS = CODE_BLOCK_QUBITS  # 48
"""Physical qubits per magic state factory (one code block) [1][5]."""

T_GATES_PER_TOFFOLI = 7
"""A Toffoli gate decomposes into 7 T/T† gates in the Clifford+T basis."""

T_STATES_PER_FACTORY = 100
"""Approximate T-state throughput per factory over a typical algorithm run."""

ERROR_CORRECTION_CODE = "BB5 [[48,4,7]]"
"""Human-readable name for the QEC code used."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_ionq_resources(
    n_logical: int,
    n_t: int,
    n_toffoli: int,
) -> dict:
    """
    Estimate physical qubit requirements for IonQ Forte Enterprise (BB5 code).

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
        data_qubits         – physical qubits for logical data blocks
        distillation_qubits – physical qubits for magic state factories
        code_distance       – BB5 code distance (7)
        logical_error_rate  – logical error per cycle
        num_t_gates         – total T-gate count (explicit + from Toffoli)
        num_factories       – number of magic state factories
        error_correction_code – name of the QEC code
    """
    n_logical = max(n_logical, 1)

    # --- Data qubits: ceil(n_logical / 4) full code blocks ---
    n_blocks = math.ceil(n_logical / LOGICALS_PER_BLOCK)
    data_qubits = n_blocks * CODE_BLOCK_QUBITS

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
                "citation": "Maurya et al., \"BB5: A Near-Optimal Quantum Error Correcting Code for Trapped-Ion Quantum Computers,\" arXiv:2503.22071 (2025).",
                "url": "https://arxiv.org/abs/2503.22071",
            },
            {
                "key": "2",
                "citation": "IonQ Blog, \"Our novel, efficient approach to quantum error correction.\"",
                "url": "https://ionq.com/blog/our-novel-efficient-approach-to-quantum-error-correction",
            },
            {
                "key": "3",
                "citation": "Error Correction Zoo, \"BB5 code.\"",
                "url": "https://errorcorrectionzoo.org/c/bb5",
            },
            {
                "key": "4",
                "citation": "IonQ, \"Forte Enterprise specifications.\"",
                "url": "https://ionq.com/quantum-systems/forte-enterprise",
            },
        ],
    }
