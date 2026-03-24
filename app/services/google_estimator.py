"""
Google Willow — Surface Code Physical Qubit Estimation

Estimates the number of physical qubits required to run a quantum circuit
on Google's Willow processor using the rotated surface code at code distance d=7.

Methodology:
  1. Data qubits: Each logical qubit requires 2d²−1 = 97 physical qubits
     (d² data + d²−1 ancilla) in the rotated surface code.
  2. Routing overhead: Lattice surgery for logical gates requires ~1.5× the
     data qubit count (compact layout).
  3. Magic state factories: T-gates cannot be executed transversally on surface
     codes. Each T-gate consumes a magic state produced by a 15-to-1
     distillation factory. Toffoli gates decompose into 7 T-gates each.

Chip parameters are from the Willow spec sheet and Nature 2024 paper.

References:
  [1] Google Quantum AI, "Quantum error correction below the surface code
      threshold," Nature 638, 920–926 (2025). arXiv:2408.13687
  [2] Willow spec sheet:
      quantumai.google/static/site-assets/downloads/willow-spec-sheet.pdf
  [3] Fowler et al., "Surface codes: Towards practical large-scale quantum
      computation," Phys. Rev. A 86, 032324 (2012). arXiv:1208.0928
  [4] Litinski, "A Game of Surface Codes," Quantum 3, 128 (2019).
      arXiv:1808.02892
  [5] Litinski, "Magic State Distillation: Not as Costly as You Think,"
      Quantum 3, 205 (2019). arXiv:1905.06903
"""

import math

# ---------------------------------------------------------------------------
# Willow chip constants
# ---------------------------------------------------------------------------

CODE_DISTANCE = 7
"""Best experimentally demonstrated distance on Willow [1]."""

PHYSICAL_QUBITS_PER_LOGICAL = 2 * CODE_DISTANCE**2 - 1  # 97
"""Rotated surface code: d² data qubits + (d²−1) ancilla qubits [3]."""

ROUTING_OVERHEAD = 1.5
"""Compact lattice-surgery routing factor [4]."""

LOGICAL_ERROR_PER_CYCLE = 0.00143
"""Measured logical error rate per surface-code cycle at d=7 [1]."""

LAMBDA = 2.14
"""Error suppression factor (NN decoder) [1]."""

CYCLE_TIME_S = 1.1e-6
"""Surface code cycle time on Willow: 1.1 µs [1]."""

# Magic state distillation (15-to-1 protocol) [5]
FACTORY_TILES = 11
"""Number of surface-code tiles per magic state factory [5]."""

FACTORY_QUBITS = FACTORY_TILES * 2 * CODE_DISTANCE**2  # 1078
"""Physical qubits per factory: 11 tiles × 2d² qubits/tile [4][5]."""

T_GATES_PER_TOFFOLI = 7
"""A Toffoli gate decomposes into 7 T/T† gates in the Clifford+T basis."""

T_STATES_PER_FACTORY = 100
"""Approximate T-state throughput per factory over a typical algorithm run.
Derived from factory production time of ~6d cycles per state [5]."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_google_resources(
    n_logical: int,
    n_t: int,
    n_toffoli: int,
) -> dict:
    """
    Estimate physical qubit requirements for Google Willow (surface code, d=7).

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
        physical_qubits    – total physical qubits required
        data_qubits        – physical qubits for logical data + routing
        distillation_qubits– physical qubits for magic state factories
        code_distance      – surface code distance used (7)
        logical_error_rate – logical error per cycle at this distance
        num_t_gates        – total T-gate count (explicit + from Toffoli)
        num_factories      – number of magic state distillation factories
    """
    n_logical = max(n_logical, 1)

    # --- Data + routing qubits ---
    data_qubits = math.ceil(n_logical * PHYSICAL_QUBITS_PER_LOGICAL * ROUTING_OVERHEAD)

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
    }
