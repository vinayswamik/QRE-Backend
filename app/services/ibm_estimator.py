"""
IBM Heron R3 — Bivariate Bicycle Code Physical Qubit Estimation

Estimates the number of physical qubits required to run a quantum circuit
on IBM's Heron R3 processor using the Bivariate Bicycle (BB) [[144,12,12]]
code, also known as the "Gross Code."

Methodology:
  1. Data qubits: The [[144,12,12]] code encodes 12 logical qubits into
     144 data + 144 syndrome = 288 physical qubits per code block.
  2. Routing overhead: 1.0x — the BB code's 2-layer routing structure
     eliminates the need for additional routing qubits.
  3. Magic state factories: T-gates require magic state injection via
     distillation within a BB code block (~288 physical qubits per factory).
     Toffoli gates decompose into 7 T-gates each.

Chip parameters are from IBM Quantum specs and Nature 2024 publication.

References:
  [1] Bravyi et al., "High-threshold and low-overhead fault-tolerant quantum
      memory," Nature 627, 778-782 (2024). arXiv:2308.07915
  [2] IBM Quantum Blog, "Landmark error correction paper on Nature cover"
      ibm.com/quantum/blog/nature-qldpc-error-correction
  [3] IBM Quantum Hardware, "Heron R3 processor specifications"
      ibm.com/quantum/hardware
  [4] IBM Quantum Blog, "Computing with error-corrected quantum computers"
      ibm.com/quantum/blog/qldpc-codes
"""

import math

# ---------------------------------------------------------------------------
# Heron R3 / BB [[144,12,12]] constants
# ---------------------------------------------------------------------------

CODE_DISTANCE = 12
"""Code distance of the [[144,12,12]] Bivariate Bicycle code [1]."""

CODE_BLOCK_DATA = 144
"""Data qubits per BB code block [1]."""

CODE_BLOCK_SYNDROME = 144
"""Syndrome (ancilla) qubits per BB code block [1]."""

CODE_BLOCK_TOTAL = CODE_BLOCK_DATA + CODE_BLOCK_SYNDROME  # 288
"""Total physical qubits per BB code block (data + syndrome) [1]."""

LOGICALS_PER_BLOCK = 12
"""Logical qubits encoded per code block [1]."""

PHYSICAL_PER_LOGICAL = CODE_BLOCK_TOTAL // LOGICALS_PER_BLOCK  # 24
"""Effective physical-to-logical ratio [1]."""

ROUTING_OVERHEAD = 1.0
"""Routing factor: BB codes use 2-layer routing built into code structure [1][4]."""

LOGICAL_ERROR_PER_CYCLE = 6e-6
"""Estimated logical error rate per QEC cycle at d=12, p_phys~0.2% [1]."""

# Magic state distillation
FACTORY_QUBITS = CODE_BLOCK_TOTAL  # 288
"""Physical qubits per magic state factory (one BB code block) [1][4]."""

T_GATES_PER_TOFFOLI = 7
"""A Toffoli gate decomposes into 7 T/T† gates in the Clifford+T basis."""

T_STATES_PER_FACTORY = 100
"""Approximate T-state throughput per factory over a typical algorithm run."""

ERROR_CORRECTION_CODE = "Bivariate Bicycle [[144,12,12]]"
"""Human-readable name for the QEC code used."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_ibm_resources(
    n_logical: int,
    n_t: int,
    n_toffoli: int,
) -> dict:
    """
    Estimate physical qubit requirements for IBM Heron R3 (BB code).

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
        code_distance       – BB code distance (12)
        logical_error_rate  – logical error per cycle
        num_t_gates         – total T-gate count (explicit + from Toffoli)
        num_factories       – number of magic state factories
        error_correction_code – name of the QEC code
    """
    n_logical = max(n_logical, 1)

    # --- Data qubits: ceil(n_logical / 12) full code blocks ---
    n_blocks = math.ceil(n_logical / LOGICALS_PER_BLOCK)
    data_qubits = n_blocks * CODE_BLOCK_TOTAL

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
                "citation": "Bravyi et al., \"High-threshold and low-overhead fault-tolerant quantum memory,\" Nature 627, 778-782 (2024).",
                "url": "https://arxiv.org/abs/2308.07915",
            },
            {
                "key": "2",
                "citation": "IBM Quantum Blog, \"Landmark error correction paper on Nature cover.\"",
                "url": "https://www.ibm.com/quantum/blog/nature-qldpc-error-correction",
            },
            {
                "key": "3",
                "citation": "IBM Quantum, \"Heron R3 processor specifications.\"",
                "url": "https://www.ibm.com/quantum/hardware",
            },
            {
                "key": "4",
                "citation": "IBM Quantum Blog, \"Computing with error-corrected quantum computers.\"",
                "url": "https://www.ibm.com/quantum/blog/qldpc-codes",
            },
        ],
    }
