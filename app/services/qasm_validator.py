import json
import logging
from collections import Counter
from pathlib import Path

import pyqasm
from openqasm3.ast import QuantumGate, QuantumPhase
from pyqasm.exceptions import QASM3ParsingError, QasmParsingError, ValidationError

from app.models.qasm import (
    GateCategoryBreakdown,
    GateDecompositionEntry,
    GateDetail,
    QasmAnalyzeResponse,
    QasmValidateResponse,
    Reference,
    ResourceDetail,
    VendorResourceEstimate,
)
from app.services.gate_decomposer import decompose_for_vendor, get_native_2q_gate
from app.services.atom_estimator import estimate_atom_resources
from app.services.google_estimator import estimate_google_resources
from app.services.ibm_estimator import estimate_ibm_resources
from app.services.ionq_estimator import estimate_ionq_resources
from app.services.quantinuum_estimator import estimate_quantinuum_resources
from app.services.quandela_estimator import estimate_quandela_resources
from app.services.quera_estimator import estimate_quera_resources
from app.services.rigetti_estimator import estimate_rigetti_resources

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


def _parse_gate_counts(code: str) -> tuple[int, Counter, dict[str, int], int]:
    """
    Return (logical_qubit_count, gate_counter, gate_qubit_map, circuit_depth).
    gate_qubit_map maps gate name → number of qubits it acts on.
    """
    module = pyqasm.loads(code)
    module.unroll()
    module.remove_barriers()
    # module.remove_measurements() # need for runtime calculation
    # module.remove_includes() # need for running on other tools

    total_qubits = max(module.num_qubits, 1)
    try:
        circuit_depth = module.depth()
    except Exception:
        # Fallback when depth() fails (e.g. some QASM 2.0 constructs like rzz)
        circuit_depth = sum(
            1 for stmt in module.unrolled_ast.statements
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
    circuit_qubits, gate_counter, gate_qubit_map, circuit_depth = _parse_gate_counts(code)
    circuit_gates = sum(gate_counter.values()) or 1
    gate_breakdown, n_1q, n_2q, n_toffoli, n_t = _build_gate_breakdown(
        gate_counter, gate_qubit_map
    )
    logger.debug(
        "QASM analysis: %d qubits, %d gates (%d 1Q, %d 2Q, %d Toffoli, %d T/Tdg), depth %d",
        circuit_qubits, circuit_gates, n_1q, n_2q, n_toffoli, n_t, circuit_depth,
    )

    # Estimator dispatch map: estimation_model -> estimator function
    _estimator_map = {
        "surface_code": estimate_google_resources,
        "bb_code": estimate_ibm_resources,
        "bb5_code": estimate_ionq_resources,
        "color_code": estimate_quantinuum_resources,
        "surface_code_rigetti": estimate_rigetti_resources,
        "geometric_4d": estimate_atom_resources,
        "surface_code_quera": estimate_quera_resources,
        "honeycomb_floquet": estimate_quandela_resources,
    }

    vendors = []
    for v in _VENDOR_SPECS:
        estimation_model = v.get("estimation_model")
        estimator_fn = _estimator_map.get(estimation_model)

        # Native gate decomposition for this vendor
        decomp = decompose_for_vendor(v["name"], gate_counter, gate_qubit_map)

        # Success probability: f_1q^native_1q × f_2q^native_2q × f_readout^n_qubits
        success_prob = (
            (v["fidelity_1q"] ** decomp.native_1q)
            * (v["fidelity_2q"] ** decomp.native_2q)
            * (v["fidelity_readout"] ** circuit_qubits)
            * 100.0
        )
        success_prob = max(0.0, min(100.0, round(success_prob, 4)))

        # Runtime: circuit_depth × gate_time_2q (depth-based, accounts for parallelism)
        runtime_s = round(circuit_depth * v["gate_time_2q"], 12)

        # Gate decomposition breakdown for frontend modal
        gate_decomp_entries = [
            GateDecompositionEntry(
                gate=g.gate, count=g.count, native_1q=g.native_1q, native_2q=g.native_2q
            )
            for g in decomp.per_gate
        ]

        if estimator_fn is not None:
            # QEC-based resource estimation
            result = estimator_fn(
                n_logical=circuit_qubits,
                n_t=n_t,
                n_toffoli=n_toffoli,
            )

            # Build references from estimator result
            refs = [
                Reference(key=r["key"], citation=r["citation"], url=r.get("url"))
                for r in result.get("references", [])
            ]

            vendors.append(VendorResourceEstimate(
                name=v["name"],
                physical_qubits=result["physical_qubits"],
                physical_gates=decomp.total,
                success_probability=success_prob,
                runtime_seconds=runtime_s,
                native_1q_count=decomp.native_1q,
                native_2q_count=decomp.native_2q,
                native_2q_gate=get_native_2q_gate(v["name"]),
                gate_decomposition=gate_decomp_entries,
                fidelity_1q=v["fidelity_1q"],
                fidelity_2q=v["fidelity_2q"],
                fidelity_readout=v["fidelity_readout"],
                gate_time_2q=v["gate_time_2q"],
                detail=ResourceDetail(
                    error_correction_code=result["error_correction_code"],
                    code_distance=result["code_distance"],
                    logical_error_rate=result["logical_error_rate"],
                    num_t_gates=result["num_t_gates"],
                    num_factories=result["num_factories"],
                    data_qubits=result["data_qubits"],
                    distillation_qubits=result["distillation_qubits"],
                    physical_qubits_per_logical=result["physical_qubits_per_logical"],
                    routing_overhead=result["routing_overhead"],
                    factory_qubits_each=result["factory_qubits_each"],
                    t_states_per_factory=result["t_states_per_factory"],
                    references=refs,
                ),
            ))
        else:
            # Fallback flat-multiplier estimation (no QEC detail)
            physical_qubits = circuit_qubits * v["qubits_per_logical"]
            vendors.append(VendorResourceEstimate(
                name=v["name"],
                physical_qubits=physical_qubits,
                physical_gates=decomp.total,
                success_probability=success_prob,
                runtime_seconds=runtime_s,
                native_1q_count=decomp.native_1q,
                native_2q_count=decomp.native_2q,
                native_2q_gate=get_native_2q_gate(v["name"]),
                gate_decomposition=gate_decomp_entries,
                fidelity_1q=v["fidelity_1q"],
                fidelity_2q=v["fidelity_2q"],
                fidelity_readout=v["fidelity_readout"],
                gate_time_2q=v["gate_time_2q"],
            ))

    return QasmAnalyzeResponse(
        circuit_qubits=circuit_qubits,
        circuit_gates=circuit_gates,
        circuit_depth=circuit_depth,
        gate_breakdown=gate_breakdown,
        vendors=vendors,
    )
