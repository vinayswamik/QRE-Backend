"""High-level QASM validation and analysis service."""

import logging
import re
import sys
from collections import Counter
from io import StringIO

import pyqasm
from pyqasm.exceptions import (
    QASM3ParsingError,
    QasmParsingError,
    ValidationError,
)

from app.models.qasm import (
    GateCategoryBreakdown,
    GateDetail,
    QasmAnalyzeResponse,
    QasmValidateResponse,
    VendorEstimateResult,
)
from app.services.circuit_metrics import check_size_limits, parse_circuit_metrics
from app.services.quantum_estimator import QuantumEstimator

_estimator = QuantumEstimator()

_HINTS: dict[str, str] = {
    "ValidationError": (
        "Validation failed. Check register sizes, gate names, and argument counts."
    ),
    "QASM3ParsingError": (
        "Syntax error. Check for a missing ';', unbalanced braces, or an undeclared register."
    ),
    "QasmParsingError": (
        "Parser error. Check the circuit structure and gate declarations."
    ),
    "TypeError": "Type error. A value has the wrong type \u2014 check gate arguments.",
    "ValueError": "Value error. A numeric or enum value is out of range.",
}

_LINE_COL_RE = re.compile(r"Error at line (\d+), column (\d+)")
_SNIPPET_RE = re.compile(r">>>>>>\s*(.+?)(?:\n|$)")


class _CapturingHandler(logging.Handler):
    """Buffer log records emitted by pyqasm during validate()."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - trivial
        self.messages.append(record.getMessage())


def _walk_exception_chain(exc: BaseException):
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        yield cur
        cur = cur.__cause__ or cur.__context__


def _find_offending_token(exc: BaseException):
    """Walk the __cause__/__context__ chain for an ANTLR offendingToken."""
    for cur in _walk_exception_chain(exc):
        for arg in getattr(cur, "args", ()) or ():
            tok = getattr(arg, "offendingToken", None)
            if tok is not None:
                return tok
    return None


def _extract_error_location(
    exc: BaseException, log_messages: list[str], code: str
) -> tuple[int | None, int | None, str | None]:
    line: int | None = None
    column: int | None = None
    snippet: str | None = None

    for msg in log_messages:
        lc = _LINE_COL_RE.search(msg)
        if lc and line is None:
            line, column = int(lc.group(1)), int(lc.group(2))
        sn = _SNIPPET_RE.search(msg)
        if sn and snippet is None:
            snippet = sn.group(1).strip() or None

    if line is None:
        tok = _find_offending_token(exc)
        if tok is not None:
            line = getattr(tok, "line", None)
            column = getattr(tok, "column", None)

    if snippet is None and line is not None:
        source_lines = code.splitlines()
        if 1 <= line <= len(source_lines):
            snippet = source_lines[line - 1].strip() or None

    return line, column, snippet


def _classify_gate(num_qubits: int) -> str:
    if num_qubits == 1:
        return "1Q"
    if num_qubits == 2:
        return "2Q"
    return "Toffoli"


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
    """Parse and semantically validate an OpenQASM program.

    On successful parse also enforces structural limits (qubits, gate count,
    depth); violations propagate as CircuitTooLargeError for the route layer
    to convert into a 413 response.
    """
    pyqasm_logger = logging.getLogger("pyqasm")
    capture = _CapturingHandler()
    stashed_handlers = list(pyqasm_logger.handlers)
    pyqasm_logger.handlers = [capture]
    saved_stderr = sys.stderr
    sys.stderr = StringIO()
    try:
        try:
            module = pyqasm.loads(code)
            module.validate()
            qubits, gate_counter, _, depth = parse_circuit_metrics(code)
            check_size_limits(qubits, sum(gate_counter.values()), depth)
            return QasmValidateResponse(valid=True, message="QASM code is valid")
        except (
            ValidationError,
            QASM3ParsingError,
            QasmParsingError,
            TypeError,
            ValueError,
        ) as exc:
            error_type = type(exc).__name__
            raw = (str(exc) or "").strip().rstrip(":").strip()
            is_parser_wrap = raw in ("", "Failed to parse OpenQASM string")
            if is_parser_wrap:
                message = "Syntax error: OpenQASM parser could not continue"
                hint_key = "QASM3ParsingError"
            else:
                message = raw
                hint_key = error_type
            line, column, snippet = _extract_error_location(exc, capture.messages, code)
            return QasmValidateResponse(
                valid=False,
                message=message,
                error_type=error_type,
                line=line,
                column=column,
                snippet=snippet,
                hint=_HINTS.get(hint_key),
            )
    finally:
        pyqasm_logger.handlers = stashed_handlers
        sys.stderr = saved_stderr


def analyze_qasm(
    code: str,
    vendor_overrides: dict[str, dict] | None = None,
    custom_vendors: dict[str, dict] | None = None,
) -> QasmAnalyzeResponse:
    """Estimate quantum resources for the given circuit across all vendors.

    Enforces structural size caps before touching the estimator so oversized
    circuits fail fast with CircuitTooLargeError instead of OOM/timeout.
    """
    circuit_qubits, gate_counter, gate_qubit_map, circuit_depth = parse_circuit_metrics(
        code
    )
    gate_breakdown, n_1q, n_2q, n_toffoli, _ = _build_gate_breakdown(
        gate_counter, gate_qubit_map
    )
    circuit_gates = n_1q + n_2q + n_toffoli
    check_size_limits(circuit_qubits, circuit_gates, circuit_depth)

    raw_results = _estimator.estimate(
        code,
        overrides=vendor_overrides,
        custom_vendors=custom_vendors,
    )
    vendors = {name: VendorEstimateResult(**data) for name, data in raw_results.items()}

    return QasmAnalyzeResponse(
        circuit_qubits=circuit_qubits,
        circuit_gates=circuit_gates,
        circuit_depth=circuit_depth,
        gate_breakdown=gate_breakdown,
        vendors=vendors,
    )
