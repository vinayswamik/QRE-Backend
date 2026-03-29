"""
Gate Decomposition Service

Decomposes standard OpenQASM gates into vendor-native gate counts for
accurate physical gate estimation, success probability, and runtime.

Each vendor's quantum processor has a native gate set. Standard QASM
gates (h, cx, t, etc.) must be decomposed into native gates for
execution. This affects physical gate count, success probability
(via gate fidelities), and runtime (via gate times).

Native gate sets per vendor (from published specs):
  Google Willow:       √iSWAP  + {Rz*, √X}          [1]
  IBM Heron R3:        CZ      + {Rz*, √X, X}       [2]
  IonQ Forte:          MS (XX) + {GPI, GPI2}         [3]
  Quantinuum Helios:   ZZMax   + {U1q, Rz*}          [4]
  Rigetti Ankaa-3:     iSWAP   + {Rz*, Rx}           [5]
  Atom Computing:      CZ      + {Ry, Rz}            [6]
  QuEra Aquila:        CZ      + {Ry, Rz}            [7]
  Quandela Belenos:    CSIGN   + {Ry, Rz}            [8]

  * Rz is virtual (zero cost) on superconducting and trapped-ion platforms.

References:
  [1] Cirq SqrtIswapTargetGateset — quantumai.google/reference/python/cirq
  [2] IBM Quantum Heron R3 processor docs — quantum.cloud.ibm.com/docs
  [3] IonQ Native Gates — docs.ionq.com/guides/getting-started-with-native-gates
  [4] Quantinuum H-series docs — docs.quantinuum.com/systems
  [5] Quilc / pyQuil compiler — pyquil-docs.rigetti.com/en/stable/compiler.html
  [6] Atom Computing AC1000 — atom-computing.com/ac1000/
  [7] Bloqade SDK — quera.com/bloqade
  [8] Perceval SDK — perceval.quandela.net
"""

from collections import Counter
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class GateDecomposition:
    """Decomposition result for a single gate type."""

    gate: str
    count: int
    native_1q: int
    native_2q: int


@dataclass
class DecompositionResult:
    """Full decomposition result for a circuit on a specific vendor."""

    native_1q: int
    native_2q: int
    total: int
    per_gate: list[GateDecomposition] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Virtual gates — zero physical cost on all platforms
# ---------------------------------------------------------------------------

VIRTUAL_GATES = frozenset({
    "rz", "s", "sdg", "t", "tdg", "z", "id", "gphase",
})
"""Gates implemented via frame changes (virtual Z) on superconducting and
trapped-ion platforms. No physical pulse required → zero cost."""


# ---------------------------------------------------------------------------
# Per-vendor 2Q gate decomposition costs
# ---------------------------------------------------------------------------

# Each entry maps a standard 2Q gate to (extra_1q, native_2q):
#   extra_1q  — additional single-qubit gates from the decomposition
#   native_2q — number of native two-qubit gate operations
#
# Toffoli (3Q+) is handled separately: 6 CNOT + 9 single-qubit (standard).

VENDOR_2Q_COSTS: dict[str, dict[str, tuple[int, int]]] = {
    "Google": {
        # Native 2Q: √iSWAP.  CX = 2 √iSWAP + 4 rotations.
        "cx": (4, 2),
        "cz": (2, 2),
    },
    "IBM": {
        # Native 2Q: CZ.  CX = H·CZ·H = 1 CZ + 2 Hadamards.
        "cx": (2, 1),
        "cz": (0, 1),
    },
    "IonQ": {
        # Native 2Q: MS (Mølmer-Sørensen / XX).  CX = 1 MS + 4 rotations.
        "cx": (4, 1),
        "cz": (4, 1),
    },
    "Quantinuum": {
        # Native 2Q: ZZMax (RZZ(π/2)).  CX = 1 ZZ + 4 rotations.
        "cx": (4, 1),
        "cz": (4, 1),
    },
    "Rigetti": {
        # Native 2Q: iSWAP.  CX = 2 iSWAP + 4 rotations.
        "cx": (4, 2),
        "cz": (2, 2),
    },
    "Atom Computing": {
        # Native 2Q: CZ (Rydberg blockade).  CX = 1 CZ + 2 H.
        "cx": (2, 1),
        "cz": (0, 1),
    },
    "QuEra": {
        # Native 2Q: CZ (Rydberg blockade).  CX = 1 CZ + 2 H.
        "cx": (2, 1),
        "cz": (0, 1),
    },
    "Quandela": {
        # Native 2Q: CSIGN ≡ CZ (heralded linear optical).  CX = 1 CSIGN + 2 H.
        "cx": (2, 1),
        "cz": (0, 1),
    },
}

# Human-readable name for each vendor's native 2Q gate.
VENDOR_NATIVE_2Q_GATE: dict[str, str] = {
    "Google": "√iSWAP",
    "IBM": "CZ",
    "IonQ": "MS",
    "Quantinuum": "ZZMax",
    "Rigetti": "iSWAP",
    "Atom Computing": "CZ",
    "QuEra": "CZ",
    "Quandela": "CSIGN",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decompose_for_vendor(
    vendor_name: str,
    gate_counter: Counter,
    gate_qubit_map: dict[str, int],
) -> DecompositionResult:
    """
    Decompose circuit gates into vendor-native gate counts.

    Parameters
    ----------
    vendor_name : str
        Vendor name (must match key in VENDOR_2Q_COSTS).
    gate_counter : Counter
        Gate name → count from circuit analysis.
    gate_qubit_map : dict
        Gate name → number of qubits it acts on.

    Returns
    -------
    DecompositionResult with native 1Q/2Q gate counts and per-gate breakdown.
    """
    costs = VENDOR_2Q_COSTS[vendor_name]
    cx_extra_1q, cx_n_2q = costs["cx"]

    native_1q = 0
    native_2q = 0
    per_gate: list[GateDecomposition] = []

    for gate, count in gate_counter.items():
        nq = gate_qubit_map.get(gate, 1)

        if gate in VIRTUAL_GATES:
            per_gate.append(GateDecomposition(gate, count, 0, 0))

        elif nq == 1:
            native_1q += count
            per_gate.append(GateDecomposition(gate, count, count, 0))

        elif nq == 2:
            extra_1q, n_2q = costs.get(gate, costs["cx"])
            g_1q = count * extra_1q
            g_2q = count * n_2q
            native_1q += g_1q
            native_2q += g_2q
            per_gate.append(GateDecomposition(gate, count, g_1q, g_2q))

        else:
            # Toffoli / multi-qubit: 6 CNOT + 9 single-qubit (standard)
            g_2q = count * 6 * cx_n_2q
            g_1q = count * (9 + 6 * cx_extra_1q)
            native_1q += g_1q
            native_2q += g_2q
            per_gate.append(GateDecomposition(gate, count, g_1q, g_2q))

    return DecompositionResult(
        native_1q=native_1q,
        native_2q=native_2q,
        total=native_1q + native_2q,
        per_gate=per_gate,
    )


def get_native_2q_gate(vendor_name: str) -> str:
    """Return the human-readable name of a vendor's native 2Q gate."""
    return VENDOR_NATIVE_2Q_GATE.get(vendor_name, "CX")
