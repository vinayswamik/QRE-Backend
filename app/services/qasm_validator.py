import json
import logging
from collections import Counter
from pathlib import Path

import pyqasm
from openqasm3.ast import QuantumGate, QuantumPhase
from pyqasm.exceptions import QASM3ParsingError, QasmParsingError, ValidationError

from app.models.qasm import (
    GateCategoryBreakdown,
    GateDetail,
    GoogleResourceDetail,
    QasmAnalyzeResponse,
    QasmValidateResponse,
    VendorResourceEstimate,
)
from app.services.google_estimator import estimate_google_resources

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vendor hardware specs — loaded from app/core/vendors.json
# ---------------------------------------------------------------------------

_VENDORS_PATH = Path(__file__).parent.parent / "core" / "vendors.json"
_VENDOR_SPECS: list[dict] = json.loads(_VENDORS_PATH.read_text())

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
) -> tuple[list[GateCategoryBreakdown], int, int, int, int]:
    """Return (gate_breakdown, n_1q, n_2q, n_toffoli, n_t)."""
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
    n_2q = sum(categories["2Q"].values())
    n_toffoli = sum(categories["Toffoli"].values())
    # T / T† gates counted from 1Q category for magic state estimation
    n_t = categories["1Q"].get("t", 0) + categories["1Q"].get("tdg", 0)
    return breakdown, n_1q, n_2q, n_toffoli, n_t


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
    except (ValidationError, QASM3ParsingError, QasmParsingError, TypeError, ValueError) as exc:
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
    gate_breakdown, n_1q, n_2q, n_toffoli, n_t = _build_gate_breakdown(
        gate_counter, gate_qubit_map
    )
    # For non-surface-code vendors, Toffoli gates are approximated as 2Q
    n_2q_with_toffoli = n_2q + n_toffoli
    logger.debug(
        "QASM analysis: %d qubits, %d gates (%d 1Q, %d 2Q, %d Toffoli, %d T/Tdg)",
        circuit_qubits, circuit_gates, n_1q, n_2q, n_toffoli, n_t,
    )

    vendors = []
    for v in _VENDOR_SPECS:
        if v.get("estimation_model") == "surface_code":
            # Google Willow: surface-code resource estimation
            result = estimate_google_resources(
                n_logical=circuit_qubits,
                n_t=n_t,
                n_toffoli=n_toffoli,
            )
            # Success probability using Willow fidelities
            success_prob = (
                (v["fidelity_1q"] ** n_1q)
                * (v["fidelity_2q"] ** n_2q_with_toffoli)
                * 100.0
            )
            success_prob = max(0.0, min(100.0, round(success_prob, 4)))

            # Runtime: sequential gate times (lower bound)
            runtime_s = n_1q * v["gate_time_1q"] + n_2q_with_toffoli * v["gate_time_2q"]
            runtime_s = round(runtime_s, 6)

            vendors.append(VendorResourceEstimate(
                name=v["name"],
                physical_qubits=result["physical_qubits"],
                physical_gates=circuit_gates,
                success_probability=success_prob,
                runtime_seconds=runtime_s,
                detail=GoogleResourceDetail(
                    code_distance=result["code_distance"],
                    logical_error_rate=result["logical_error_rate"],
                    num_t_gates=result["num_t_gates"],
                    num_factories=result["num_factories"],
                    data_qubits=result["data_qubits"],
                    distillation_qubits=result["distillation_qubits"],
                ),
            ))
        else:
            # Flat-multiplier estimation for other vendors
            physical_qubits = circuit_qubits * v["qubits_per_logical"]
            physical_gates = circuit_gates * v["gates_per_logical"]

            success_prob = (
                (v["fidelity_1q"] ** n_1q)
                * (v["fidelity_2q"] ** n_2q_with_toffoli)
                * 100.0
            )
            success_prob = max(0.0, min(100.0, round(success_prob, 4)))

            runtime_s = (
                n_1q * v["gate_time_1q"] + n_2q_with_toffoli * v["gate_time_2q"]
            )
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
