"""Shared circuit parsing + structural limit checks.

Extracted so both the validator (for /validate and /analyze pre-checks) and
the estimator (for metadata in the response) share one parse + one set of
caps, rather than each module recomputing qubit/gate/depth counts.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pyqasm
from openqasm3.ast import QuantumGate, QuantumPhase
from pyqasm.exceptions import ValidationError

from app.core.config import input_limits, settings


class CircuitTooLargeError(Exception):
    """Raised when a parsed circuit exceeds a configured structural cap.

    `detail` is the JSON body returned by the 413 handler. It names the
    specific metric that failed so the frontend can show a targeted message
    instead of a generic "too big" error.
    """

    def __init__(self, detail: dict[str, Any]):
        super().__init__(detail.get("message", "Circuit too large"))
        self.detail = detail


def parse_circuit_metrics(
    code: str,
) -> tuple[int, Counter, dict[str, int], int]:
    """Parse QASM once and return (qubits, gate_counter, gate_qubit_map, depth).

    This is the single source of truth for circuit metadata across the
    validator (structural checks) and the analyzer (response payload).
    """
    module = pyqasm.loads(code)
    module.unroll()
    module.remove_barriers()

    total_qubits = max(module.num_qubits, 1)
    try:
        circuit_depth = module.depth()
    except ValidationError:
        # pyqasm.depth() can reject QASM2 programs containing QuantumPhase
        # after unroll. Drop non-physical phase/no-op lines and recompute.
        cleaned_lines = []
        for line in str(module).splitlines():
            stripped = line.strip()
            if stripped.startswith("gphase(") or stripped.startswith("nop "):
                continue
            cleaned_lines.append(line)
        cleaned_module = pyqasm.loads("\n".join(cleaned_lines))
        cleaned_module.unroll()
        cleaned_module.remove_barriers()
        circuit_depth = cleaned_module.depth()

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


def check_size_limits(qubits: int, gate_count: int, depth: int) -> None:
    """Raise CircuitTooLargeError if any structural cap is exceeded.

    Limits come from settings so they can be tuned per-environment without
    code changes. The error carries the failing metric + the configured cap
    so the frontend can render a precise message.
    """
    limits = input_limits()
    limit_note = (
        'Use GET /api/v1/qasm/limits (or the same names in JSON field "limits") '
        "for all supported ceilings."
    )
    if qubits > settings.MAX_QUBITS:
        raise CircuitTooLargeError(
            {
                "error": "circuit_too_large",
                "message": (
                    f"This input is too large: the circuit declares {qubits} qubits, "
                    f"but this backend supports up to {settings.MAX_QUBITS}. "
                    f"{limit_note}"
                ),
                "field": "qubits",
                "value": qubits,
                "limit": settings.MAX_QUBITS,
                "limits": limits,
            }
        )
    if gate_count > settings.MAX_GATE_COUNT:
        raise CircuitTooLargeError(
            {
                "error": "circuit_too_large",
                "message": (
                    f"This input is too large: parsed gate count is {gate_count:,}, "
                    f"but this backend supports up to {settings.MAX_GATE_COUNT:,}. "
                    f"{limit_note}"
                ),
                "field": "gate_count",
                "value": gate_count,
                "limit": settings.MAX_GATE_COUNT,
                "limits": limits,
            }
        )
    if depth > settings.MAX_CIRCUIT_DEPTH:
        raise CircuitTooLargeError(
            {
                "error": "circuit_too_large",
                "message": (
                    f"This input is too large: circuit depth is {depth:,}, "
                    f"but this backend supports depth up to {settings.MAX_CIRCUIT_DEPTH:,}. "
                    f"{limit_note}"
                ),
                "field": "depth",
                "value": depth,
                "limit": settings.MAX_CIRCUIT_DEPTH,
                "limits": limits,
            }
        )
