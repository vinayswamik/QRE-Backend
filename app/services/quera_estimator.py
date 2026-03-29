"""
QuEra Aquila — Surface Code Physical Qubit Estimation

Estimates the number of physical qubits required to run a quantum circuit
on QuEra's Aquila processor using the rotated surface code at code
distance d=7.

Methodology:
  1. Data qubits: 2d²−1 = 97 physical qubits per logical qubit in the
     rotated surface code (same formula as Google/Rigetti).
  2. Routing overhead: 1.2x — neutral atom rearrangement via optical
     tweezers reduces routing overhead vs. fixed-grid architectures (1.5x)
     while not fully eliminating it like trapped ions (1.0x).
  3. Magic state factories: 15-to-1 distillation, 11 tiles × 2d² = 1078
     physical qubits per factory. Toffoli → 7 T-gates each.

  QuEra (Harvard/MIT collaboration) demonstrated surface codes at d=3, 5, 7
  on reconfigurable atom arrays, published in Nature 2023.

References:
  [1] Bluvstein et al., "Logical quantum processor based on reconfigurable
      atom arrays," Nature 626, 58-65 (2024). arXiv:2312.03982
  [2] Gupta et al., "Experimental demonstration of logical magic state
      distillation," Nature (2025).
  [3] Fowler et al., "Surface codes: Towards practical large-scale quantum
      computation," Phys. Rev. A 86, 032324 (2012). arXiv:1208.0928
  [4] Cong et al., "An Architecture for Improved Surface Code Connectivity
      in Neutral Atoms," arXiv:2309.13507 (2023).
"""

import math

# ---------------------------------------------------------------------------
# Aquila / Surface Code constants
# ---------------------------------------------------------------------------

CODE_DISTANCE = 7
"""Code distance demonstrated on neutral atom arrays [1]."""

PHYSICAL_QUBITS_PER_LOGICAL = 2 * CODE_DISTANCE**2 - 1  # 97
"""Rotated surface code: d² data + (d²−1) ancilla qubits [3]."""

ROUTING_OVERHEAD = 1.2
"""Routing factor: reduced by atom rearrangement vs. fixed grid [4]."""

LOGICAL_ERROR_PER_CYCLE = 1e-3
"""Estimated logical error per cycle at d=7 on neutral atoms [1]."""

# Magic state distillation (15-to-1 protocol)
FACTORY_TILES = 11
"""Number of surface-code tiles per magic state factory."""

FACTORY_QUBITS = FACTORY_TILES * 2 * CODE_DISTANCE**2  # 1078
"""Physical qubits per factory: 11 tiles × 2d² qubits/tile."""

T_GATES_PER_TOFFOLI = 7
"""A Toffoli gate decomposes into 7 T/T† gates in the Clifford+T basis."""

T_STATES_PER_FACTORY = 100
"""Approximate T-state throughput per factory over a typical algorithm run."""

ERROR_CORRECTION_CODE = "Rotated Surface Code"
"""Human-readable name for the QEC code used."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_quera_resources(
    n_logical: int,
    n_t: int,
    n_toffoli: int,
) -> dict:
    """
    Estimate physical qubit requirements for QuEra Aquila (surface code, d=7).

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
        code_distance       – surface code distance (7)
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
                "citation": "Bluvstein et al., \"Logical quantum processor based on reconfigurable atom arrays,\" Nature 626, 58-65 (2024).",
                "url": "https://arxiv.org/abs/2312.03982",
            },
            {
                "key": "2",
                "citation": "Gupta et al., \"Experimental demonstration of logical magic state distillation,\" Nature (2025).",
                "url": None,
            },
            {
                "key": "3",
                "citation": "Fowler et al., \"Surface codes: Towards practical large-scale quantum computation,\" Phys. Rev. A 86, 032324 (2012).",
                "url": "https://arxiv.org/abs/1208.0928",
            },
            {
                "key": "4",
                "citation": "Cong et al., \"An Architecture for Improved Surface Code Connectivity in Neutral Atoms,\" arXiv:2309.13507 (2023).",
                "url": "https://arxiv.org/abs/2309.13507",
            },
        ],
    }
