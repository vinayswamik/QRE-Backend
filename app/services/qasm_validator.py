import logging
from collections import Counter

import pyqasm
from openqasm3.ast import QuantumGate, QuantumPhase

from app.models.qasm import (
    GateCategoryBreakdown,
    GateDetail,
    QasmAnalyzeResponse,
    QasmValidateResponse,
    VendorResourceEstimate,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vendor hardware specs (sourced from vendors/hardware_data JSON files)
# ---------------------------------------------------------------------------

_VENDOR_SPECS = [
    {
        "name": "Google",
        "qubits_per_logical": 101,
        "gates_per_logical": 314,
        # Gate fidelities (1 - error_rate)
        "fidelity_1q": 0.9990,
        "fidelity_2q": 0.9950,
        # Gate times in seconds
        "gate_time_1q": 15e-9,
        "gate_time_2q": 30e-9,
    },
    {
        "name": "IBM",
        "qubits_per_logical": 127,
        "gates_per_logical": 2500,
        "fidelity_1q": 0.99981,
        "fidelity_2q": 0.9971,
        "gate_time_1q": 35e-9,
        "gate_time_2q": 68e-9,
    },
    {
        "name": "IonQ",
        "qubits_per_logical": 64,
        "gates_per_logical": 1200,
        "fidelity_1q": 0.9997,
        "fidelity_2q": 0.9967,
        "gate_time_1q": 10e-6,
        "gate_time_2q": 200e-6,
    },
    {
        "name": "Quantinuum",
        "qubits_per_logical": 32,
        "gates_per_logical": 800,
        "fidelity_1q": 0.99997,
        "fidelity_2q": 0.9993,
        "gate_time_1q": 10e-6,
        "gate_time_2q": 200e-6,
    },
    {
        "name": "Rigetti",
        "qubits_per_logical": 84,
        "gates_per_logical": 1600,
        "fidelity_1q": 0.9950,
        "fidelity_2q": 0.9700,
        "gate_time_1q": 40e-9,
        "gate_time_2q": 80e-9,
    },
    {
        "name": "Atom Computing",
        "qubits_per_logical": 100,
        "gates_per_logical": 2000,
        "fidelity_1q": 0.9990,
        "fidelity_2q": 0.9950,
        "gate_time_1q": 1e-6,
        "gate_time_2q": 500e-6,
    },
]

def _classify_gate(num_qubits: int) -> str:
    """Classify a gate by its qubit arity: 1Q, 2Q, or Toffoli (3+)."""
    if num_qubits >= 3:
        return "Toffoli"
    if num_qubits == 2:
        return "2Q"
    return "1Q"


def _parse_gate_counts(code: str) -> tuple[int, Counter, dict[str, int]]:
    """
    Return (logical_qubit_count, gate_counter, gate_qubit_map).
    gate_qubit_map maps gate name → number of qubits it acts on.
    """
    module = pyqasm.loads(code)
    module.unroll()
    module.remove_barriers()
    module.remove_measurements()
    module.remove_includes()

    total_qubits = max(module.num_qubits, 1)
    gate_counter: Counter = Counter()
    gate_qubit_map: dict[str, int] = {}
    for stmt in module.unrolled_ast.statements:
        if isinstance(stmt, QuantumGate):
            name = stmt.name.name.lower()
            gate_counter[name] += 1
            gate_qubit_map[name] = len(stmt.qubits)
        elif isinstance(stmt, QuantumPhase):
            gate_counter["gphase"] += 1
            gate_qubit_map["gphase"] = len(stmt.qubits)

    return total_qubits, gate_counter, gate_qubit_map


def _build_gate_breakdown(
    gate_counter: Counter, gate_qubit_map: dict[str, int]
) -> tuple[list[GateCategoryBreakdown], int, int]:
    """Return (gate_breakdown, n_1q, n_2q) for use in resource estimates."""
    categories: dict[str, Counter] = {"1Q": Counter(), "2Q": Counter(), "Toffoli": Counter()}
    for gate, count in gate_counter.items():
        num_qubits = gate_qubit_map.get(gate, 1)
        categories[_classify_gate(num_qubits)][gate] = count

    total_all = sum(gate_counter.values()) or 1
    breakdown: list[GateCategoryBreakdown] = []
    for cat_name in ("1Q", "2Q", "Toffoli"):
        cat_counter = categories[cat_name]
        cat_total = sum(cat_counter.values())
        gates = [
            GateDetail(
                name=g,
                count=c,
                percentage=round(c / total_all * 100, 2),
            )
            for g, c in sorted(cat_counter.items(), key=lambda x: -x[1])
        ]
        breakdown.append(GateCategoryBreakdown(
            name=cat_name,
            value=cat_total,
            percentage=round(cat_total / total_all * 100, 2),
            gates=gates,
        ))

    n_1q = sum(categories["1Q"].values())
    # Toffoli decomposes into ~6 CNOTs; approximate as 2Q for fidelity/runtime
    n_2q = sum(categories["2Q"].values()) + sum(categories["Toffoli"].values())
    return breakdown, n_1q, n_2q


def validate_qasm(code: str) -> QasmValidateResponse:
    """
    Parse and validate an OpenQASM program using pyqasm.

    Returns a QasmValidateResponse indicating success or the first error
    encountered during parsing / semantic analysis.
    """
    try:
        module = pyqasm.loads(code)
        module.validate()
        logger.debug("QASM validation succeeded")
        return QasmValidateResponse(valid=True, message="QASM code is valid")
    except Exception as exc:
        error_type = type(exc).__name__
        message = str(exc) or f"Validation failed ({error_type})"
        logger.debug("QASM validation failed: %s – %s", error_type, message)
        return QasmValidateResponse(valid=False, message=message, error_type=error_type)


def analyze_qasm(code: str) -> QasmAnalyzeResponse:
    """
    Parse an OpenQASM program and return per-vendor physical resource estimates.

    Assumes the circuit is already valid (call validate_qasm first).
    """
    circuit_qubits, gate_counter, gate_qubit_map = _parse_gate_counts(code)
    circuit_gates = sum(gate_counter.values()) or 1
    gate_breakdown, n_1q, n_2q = _build_gate_breakdown(gate_counter, gate_qubit_map)
    logger.debug("QASM analysis: %d qubits, %d gates (%d 1Q, %d 2Q)", circuit_qubits, circuit_gates, n_1q, n_2q)

    vendors = []
    for v in _VENDOR_SPECS:
        physical_qubits = circuit_qubits * v["qubits_per_logical"]
        physical_gates = circuit_gates * v["gates_per_logical"]

        # Success probability: product of per-gate fidelities
        success_prob = (v["fidelity_1q"] ** n_1q) * (v["fidelity_2q"] ** n_2q) * 100.0
        success_prob = max(0.0, min(100.0, round(success_prob, 4)))

        # Runtime estimate: sequential gate times (lower bound)
        runtime_s = n_1q * v["gate_time_1q"] + n_2q * v["gate_time_2q"]
        runtime_s = round(runtime_s, 6)

        vendors.append(VendorResourceEstimate(
            name=v["name"],
            physical_qubits=physical_qubits,
            physical_gates=physical_gates,
            success_probability=success_prob,
            runtime_seconds=runtime_s,
        ))

    return QasmAnalyzeResponse(
        circuit_qubits=circuit_qubits,
        circuit_gates=circuit_gates,
        gate_breakdown=gate_breakdown,
        vendors=vendors,
    )
