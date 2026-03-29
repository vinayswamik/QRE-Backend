"""
Quandela Belenos — Honeycomb Floquet Code Physical Qubit Estimation

Estimates the number of physical qubits required to run a quantum circuit
on Quandela's Belenos processor using the Honeycomb Floquet Code at d=5.

Architecture:
  Quandela uses SPOQC (Spin-Optical Quantum Computing) — a hybrid approach
  combining semiconductor quantum dot spin qubits (stationary) with single
  photons (flying qubits) for entanglement. All-to-all connectivity is
  achieved via photonic links, eliminating routing overhead.

Methodology:
  1. Data qubits: The Honeycomb Floquet code at distance d uses 2d² physical
     qubits per logical qubit on a honeycomb lattice. Unlike the surface code,
     syndrome extraction uses native 2-body measurements — no separate ancilla
     qubits are needed.
  2. Code distance d=5: The Honeycomb Floquet code achieves a 6.3% photon loss
     threshold on SPOQC (vs 2.8% for surface code). Photon loss (erasure) is
     the dominant error channel in photonic systems and is easier to correct
     than unknown Pauli errors. d=5 achieves ~10^-3 logical error rate.
  3. Routing overhead: 1.0x — all-to-all photonic connectivity.
  4. Magic state factories: 15-to-1 distillation using 11 honeycomb code
     patches = 11 × 50 = 550 physical qubits per factory.

References:
  [1] Dessertaine et al., "Enhanced Fault-tolerance in Photonic Quantum
      Computing: Honeycomb Floquet Code vs Surface Code in Tailored
      Architecture," arXiv:2410.07065 (Quandela team)
  [2] Hastings & Haah, "Dynamically Generated Logical Qubits,"
      Quantum 5, 564 (2021)
  [3] de Gliniasty et al., "A Spin-Optical Quantum Computing Architecture,"
      Quantum 8, 1423 (2024)
  [4] Wein et al., "Minimizing resource overhead in fusion-based QC with
      hybrid spin-photon devices," PRX Quantum 6, 040362 (2025)
  [5] Nature Photonics 18, 603-609 (2024), "A versatile single-photon-based
      quantum computing platform"
  [6] Quandela Belenos specs, quandela.com/qpus/belenos/
"""

import math

# ---------------------------------------------------------------------------
# Belenos / Honeycomb Floquet Code constants
# ---------------------------------------------------------------------------

CODE_DISTANCE = 5
"""Code distance of the Honeycomb Floquet code [1][2]."""

PHYSICAL_QUBITS_PER_LOGICAL = 2 * CODE_DISTANCE**2  # 50
"""Physical qubits per logical qubit: 2d² on a honeycomb lattice [1][2].
No separate ancilla needed — syndrome extraction uses 2-body measurements."""

ROUTING_OVERHEAD = 1.0
"""Routing factor: all-to-all photonic connectivity eliminates routing overhead [3]."""

LOGICAL_ERROR_PER_CYCLE = 1e-3
"""Estimated logical error rate per QEC cycle at d=5 with ~3% photon loss [1]."""

# Magic state distillation
FACTORY_QUBITS = 550
"""Physical qubits per magic state factory: 11 honeycomb patches × 2d² [1][2]."""

T_GATES_PER_TOFFOLI = 7
"""A Toffoli gate decomposes into 7 T/T† gates in the Clifford+T basis."""

T_STATES_PER_FACTORY = 100
"""Approximate T-state throughput per factory over a typical algorithm run."""

ERROR_CORRECTION_CODE = "Honeycomb Floquet Code"
"""Human-readable name for the QEC code used."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_quandela_resources(
    n_logical: int,
    n_t: int,
    n_toffoli: int,
) -> dict:
    """
    Estimate physical qubit requirements for Quandela Belenos (Honeycomb Floquet).

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
        distillation_qubits – physical qubits for magic state factories
        code_distance       – Honeycomb Floquet code distance (5)
        logical_error_rate  – logical error per cycle
        num_t_gates         – total T-gate count (explicit + from Toffoli)
        num_factories       – number of magic state factories
        error_correction_code – name of the QEC code
    """
    n_logical = max(n_logical, 1)

    # --- Data qubits: n_logical × 2d² (no routing overhead) ---
    data_qubits = n_logical * PHYSICAL_QUBITS_PER_LOGICAL

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
                "citation": "Dessertaine et al., \"Enhanced Fault-tolerance in Photonic Quantum Computing: Honeycomb Floquet Code vs Surface Code,\" arXiv:2410.07065.",
                "url": "https://arxiv.org/abs/2410.07065",
            },
            {
                "key": "2",
                "citation": "Hastings & Haah, \"Dynamically Generated Logical Qubits,\" Quantum 5, 564 (2021).",
                "url": None,
            },
            {
                "key": "3",
                "citation": "de Gliniasty et al., \"A Spin-Optical Quantum Computing Architecture,\" Quantum 8, 1423 (2024).",
                "url": None,
            },
            {
                "key": "4",
                "citation": "Quandela Belenos specifications.",
                "url": "https://www.quandela.com/qpus/belenos/",
            },
        ],
    }
