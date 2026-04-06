"""High-level QASM validation and analysis service."""

from collections import Counter

import pyqasm
from openqasm3.ast import QuantumGate, QuantumPhase
from pyqasm.exceptions import (
    QASM3ParsingError,
    QasmParsingError,
    UnrollError,
    ValidationError,
)

from app.models.qasm import (
    GateCategoryBreakdown,
    GateDetail,
    QasmAnalyzeResponse,
    QasmValidateResponse,
    VendorEstimateResult,
)
from app.services.quantum_estimator import QuantumEstimator

_estimator = QuantumEstimator()


def _classify_gate(num_qubits: int) -> str:
    if num_qubits == 1:
        return "1Q"
    if num_qubits == 2:
        return "2Q"
    return "Toffoli"


def _parse_gate_counts(code: str) -> tuple[int, Counter, dict[str, int], int]:
    module = pyqasm.loads(code)
    module.unroll()
    module.remove_barriers()

    total_qubits = max(module.num_qubits, 1)
    try:
        circuit_depth = module.depth()
    except (UnrollError, ValidationError, ValueError):
        circuit_depth = sum(
            1
            for stmt in module.unrolled_ast.statements
            if isinstance(stmt, (QuantumGate, QuantumPhase))
        )

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

    return total_qubits, gate_counter, gate_qubit_map, circuit_depth


def _build_gate_breakdown(
    gate_counter: Counter, gate_qubit_map: dict[str, int]
) -> tuple[list[GateCategoryBreakdown], int, int, int, int]:
    categories: dict[str, Counter] = {
        "1Q": Counter(),
        "2Q": Counter(),
        "Toffoli": Counter(),
    }
    for gate, count in gate_counter.items():
        num_qubits = gate_qubit_map.get(gate, 1)
        categories[_classify_gate(num_qubits)][gate] = count

    total_all = sum(gate_counter.values()) or 1
    breakdown: list[GateCategoryBreakdown] = []
    for cat_name in ("1Q", "2Q", "Toffoli"):
        cat_counter = categories[cat_name]
        cat_total = sum(cat_counter.values())
        gates = [
            GateDetail(name=g, count=c, percentage=round(c / total_all * 100, 2))
            for g, c in sorted(cat_counter.items(), key=lambda x: -x[1])
        ]
        breakdown.append(
            GateCategoryBreakdown(
                name=cat_name,
                value=cat_total,
                percentage=round(cat_total / total_all * 100, 2),
                gates=gates,
            )
        )

    n_1q = sum(categories["1Q"].values())
    n_2q = sum(categories["2Q"].values())
    n_toffoli = sum(categories["Toffoli"].values())
    return (
        breakdown,
        n_1q,
        n_2q,
        n_toffoli,
        (categories["1Q"].get("t", 0) + categories["1Q"].get("tdg", 0)),
    )


def validate_qasm(code: str) -> QasmValidateResponse:
    """Parse and semantically validate an OpenQASM program."""
    try:
        module = pyqasm.loads(code)
        module.validate()
        return QasmValidateResponse(valid=True, message="QASM code is valid")
    except (
        ValidationError,
        QASM3ParsingError,
        QasmParsingError,
        TypeError,
        ValueError,
    ) as exc:
        error_type = type(exc).__name__
        message = str(exc) or f"Validation failed ({error_type})"
        return QasmValidateResponse(valid=False, message=message, error_type=error_type)


def analyze_qasm(code: str) -> QasmAnalyzeResponse:
    """Estimate quantum resources for the given circuit across all vendors."""
    circuit_qubits, gate_counter, gate_qubit_map, circuit_depth = _parse_gate_counts(
        code
    )
    gate_breakdown, n_1q, n_2q, n_toffoli, _ = _build_gate_breakdown(
        gate_counter, gate_qubit_map
    )
    circuit_gates = n_1q + n_2q + n_toffoli

    raw_results = _estimator.estimate(code)
    vendors = {name: VendorEstimateResult(**data) for name, data in raw_results.items()}

    return QasmAnalyzeResponse(
        circuit_qubits=circuit_qubits,
        circuit_gates=circuit_gates,
        circuit_depth=circuit_depth,
        gate_breakdown=gate_breakdown,
        vendors=vendors,
    )
