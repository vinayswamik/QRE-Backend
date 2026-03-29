"""
Rigetti Ankaa-3 — Surface Code Physical Qubit Estimation

Estimates the number of physical qubits required to run a quantum circuit
on Rigetti's Ankaa-3 processor using the rotated surface code at code
distance d=3.

Methodology:
  Same QEC framework as Google Willow (rotated surface code) but at d=3
  (conservative) since Rigetti's 2Q error rate (~0.5%) is near the
  surface code threshold.
  1. Data qubits: 2d²−1 = 17 physical qubits per logical qubit.
  2. Routing overhead: 1.5x for lattice surgery on the square lattice.
  3. Magic state factories: 15-to-1 distillation, 11 tiles × 2d² = 198
     physical qubits per factory. Toffoli → 7 T-gates each.

References:
  [1] Sheridan et al. (Rigetti + Riverlane), "Real-time quantum error
      correction on a low-latency quantum processor," arXiv:2410.05202 (2024).
  [2] Rigetti, "Ankaa-3 System Launch" (Dec 2024).
      investors.rigetti.com/news-releases/
  [3] Fowler et al., "Surface codes: Towards practical large-scale quantum
      computation," Phys. Rev. A 86, 032324 (2012). arXiv:1208.0928
  [4] Litinski, "A Game of Surface Codes," Quantum 3, 128 (2019).
      arXiv:1808.02892
  [5] Litinski, "Magic State Distillation: Not as Costly as You Think,"
      Quantum 3, 205 (2019). arXiv:1905.06903
"""

import math

# ---------------------------------------------------------------------------
# Ankaa-3 / Surface Code constants
# ---------------------------------------------------------------------------

CODE_DISTANCE = 3
"""Conservative code distance for surface code on Ankaa-3 [1][3]."""

PHYSICAL_QUBITS_PER_LOGICAL = 2 * CODE_DISTANCE**2 - 1  # 17
"""Rotated surface code: d² data + (d²−1) ancilla qubits [3]."""

ROUTING_OVERHEAD = 1.5
"""Compact lattice-surgery routing factor for square lattice [4]."""

LOGICAL_ERROR_PER_CYCLE = 7.5e-3
"""Estimated logical error per cycle at d=3 with p_phys~0.5%.
Computed via p_L ≈ 0.03 × (p_phys/p_threshold)^((d+1)/2) [3]."""

# Magic state distillation (15-to-1 protocol) [5]
FACTORY_TILES = 11
"""Number of surface-code tiles per magic state factory [5]."""

FACTORY_QUBITS = FACTORY_TILES * 2 * CODE_DISTANCE**2  # 198
"""Physical qubits per factory: 11 tiles × 2d² qubits/tile [4][5]."""

T_GATES_PER_TOFFOLI = 7
"""A Toffoli gate decomposes into 7 T/T† gates in the Clifford+T basis."""

T_STATES_PER_FACTORY = 100
"""Approximate T-state throughput per factory over a typical algorithm run."""

ERROR_CORRECTION_CODE = "Rotated Surface Code"
"""Human-readable name for the QEC code used."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_rigetti_resources(
    n_logical: int,
    n_t: int,
    n_toffoli: int,
) -> dict:
    """
    Estimate physical qubit requirements for Rigetti Ankaa-3 (surface code, d=3).

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
        data_qubits         – physical qubits for data + routing
        distillation_qubits – physical qubits for magic state factories
        code_distance       – surface code distance (3)
        logical_error_rate  – logical error per cycle
        num_t_gates         – total T-gate count (explicit + from Toffoli)
        num_factories       – number of magic state factories
        error_correction_code – name of the QEC code
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
        "error_correction_code": ERROR_CORRECTION_CODE,
        "physical_qubits_per_logical": PHYSICAL_QUBITS_PER_LOGICAL,
        "routing_overhead": ROUTING_OVERHEAD,
        "factory_qubits_each": FACTORY_QUBITS,
        "t_states_per_factory": T_STATES_PER_FACTORY,
        "references": [
            {
                "key": "1",
                "citation": "Sheridan et al., \"Real-time quantum error correction on a low-latency quantum processor,\" arXiv:2410.05202 (2024).",
                "url": "https://arxiv.org/abs/2410.05202",
            },
            {
                "key": "2",
                "citation": "Rigetti, \"Ankaa-3 System Launch\" (Dec 2024).",
                "url": "https://investors.rigetti.com/news-releases/",
            },
            {
                "key": "3",
                "citation": "Fowler et al., \"Surface codes: Towards practical large-scale quantum computation,\" Phys. Rev. A 86, 032324 (2012).",
                "url": "https://arxiv.org/abs/1208.0928",
            },
            {
                "key": "4",
                "citation": "Litinski, \"A Game of Surface Codes,\" Quantum 3, 128 (2019).",
                "url": "https://arxiv.org/abs/1808.02892",
            },
            {
                "key": "5",
                "citation": "Litinski, \"Magic State Distillation: Not as Costly as You Think,\" Quantum 3, 205 (2019).",
                "url": "https://arxiv.org/abs/1905.06903",
            },
        ],
    }
