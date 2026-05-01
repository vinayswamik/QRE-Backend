"""QASM validation and analysis route handlers."""

import json
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import input_limits
from app.core.rate_limit import (
    enforce_analyze_rate_limit,
    enforce_validate_rate_limit,
)
from app.models.qasm import (
    QasmAnalyzeRequest,
    QasmValidateRequest,
)
from app.services.circuit_metrics import (
    CircuitTooLargeError,
    check_size_limits,
    parse_circuit_metrics,
)
from app.services.qasm_validator import (
    _build_gate_breakdown,
    analyze_qasm,
    validate_qasm,
)
from app.services.quantum_estimator import QuantumEstimator

router = APIRouter(prefix="/qasm", tags=["qasm"])

_estimator_for_defaults = QuantumEstimator()
_stream_estimator = QuantumEstimator()


def _too_large(exc: CircuitTooLargeError) -> HTTPException:
    """Map a CircuitTooLargeError to a 413 HTTPException with structured detail."""
    return HTTPException(status_code=413, detail=exc.detail)


@router.post(
    "/validate",
    summary="Validate OpenQASM code",
    description="Parse and semantically validate an OpenQASM 2.0/3.0 program.",
    dependencies=[Depends(enforce_validate_rate_limit)],
)
def validate(payload: QasmValidateRequest):
    """Validate an OpenQASM 2.0/3.0 program and return parse/semantic results."""
    try:
        return validate_qasm(payload.code)
    except CircuitTooLargeError as exc:
        raise _too_large(exc) from exc


@router.post(
    "/analyze",
    summary="Analyze OpenQASM circuit resources",
    description="Run quantum resource estimation across all vendors using Azure QRE.",
    dependencies=[Depends(enforce_analyze_rate_limit)],
)
def analyze(payload: QasmAnalyzeRequest):
    """Run quantum resource estimation across all vendors for the given circuit."""
    overrides = (
        {
            name: ov.model_dump(exclude_none=True)
            for name, ov in payload.vendor_overrides.items()
        }
        if payload.vendor_overrides
        else None
    )
    custom_vendors = (
        {
            name: cv.model_dump(exclude_none=True)
            for name, cv in payload.custom_vendors.items()
        }
        if payload.custom_vendors
        else None
    )
    try:
        return analyze_qasm(
            payload.code,
            vendor_overrides=overrides,
            custom_vendors=custom_vendors,
        )
    except CircuitTooLargeError as exc:
        raise _too_large(exc) from exc
    except ValueError as exc:
        # Raised when custom vendor names collide with built-in vendors.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _sse_event(event: str, data: dict) -> str:
    """Format a single Server-Sent Events frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream_analysis(payload: QasmAnalyzeRequest) -> Iterator[str]:
    """Yield SSE frames for a streaming /analyze run.

    Emits: validating → preprocessing → estimating → N × vendor_result → complete.
    On early failure (parse error, size cap, bad overrides) yields a single
    `error` frame and stops.
    """
    yield _sse_event("stage", {"stage": "validating"})
    try:
        qubits, gate_counter, gate_qubit_map, depth = parse_circuit_metrics(
            payload.code
        )
        gate_breakdown, n_1q, n_2q, n_toffoli, _ = _build_gate_breakdown(
            gate_counter, gate_qubit_map
        )
        circuit_gates = n_1q + n_2q + n_toffoli
        check_size_limits(qubits, circuit_gates, depth)
    except CircuitTooLargeError as exc:
        yield _sse_event("error", {"status": 413, **exc.detail})
        return
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # noqa: BLE001 — surface any parse failure to the client (pyqasm edge cases)
        yield _sse_event("error", {"status": 400, "message": f"Parse error: {exc}"})
        return

    yield _sse_event(
        "circuit_metadata",
        {
            "circuit_qubits": qubits,
            "circuit_gates": circuit_gates,
            "circuit_depth": depth,
            "gate_breakdown": [cat.model_dump() for cat in gate_breakdown],
        },
    )

    overrides = (
        {
            name: ov.model_dump(exclude_none=True)
            for name, ov in payload.vendor_overrides.items()
        }
        if payload.vendor_overrides
        else None
    )
    custom_vendors = (
        {
            name: cv.model_dump(exclude_none=True)
            for name, cv in payload.custom_vendors.items()
        }
        if payload.custom_vendors
        else None
    )

    try:
        for event in _stream_estimator.estimate_streaming(
            payload.code,
            overrides=overrides,
            custom_vendors=custom_vendors,
        ):
            etype = event.pop("type")
            yield _sse_event(etype, event)
    except ValueError as exc:
        yield _sse_event("error", {"status": 422, "message": str(exc)})


@router.post(
    "/analyze/stream",
    summary="Streaming variant of /analyze with per-vendor progress",
    description=(
        "Identical inputs to /analyze but responds as Server-Sent Events so the "
        "client can render vendor results incrementally. Event types: stage, "
        "circuit_metadata, vendor_result, complete, error."
    ),
    dependencies=[Depends(enforce_analyze_rate_limit)],
)
def analyze_stream(payload: QasmAnalyzeRequest):
    """Stream analysis progress as SSE events."""
    return StreamingResponse(
        _stream_analysis(payload),
        media_type="text/event-stream",
        headers={
            # Disable intermediary buffering so events actually flush to the
            # client in real time (nginx/CloudFront/etc).
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/limits",
    summary="Get input size limits",
    description=(
        "Return the maximum QASM byte length plus structural caps (qubits, "
        "gate count, depth). The frontend uses this to pre-validate input "
        "before hitting the rate-limited endpoints."
    ),
)
def limits() -> dict:
    """Expose the configured input caps for client-side pre-validation."""
    return input_limits()


@router.get(
    "/vendor-defaults",
    summary="Get vendor parameter defaults",
    description=(
        "Return the full vendor configuration map (qubit_params, qec_scheme, "
        "max_code_distance) for every vendor known to the backend. The frontend "
        "uses this to seed the Advanced Override panel so it never duplicates "
        "constants from vendors.json."
    ),
)
def vendor_defaults():
    """Return the unmodified vendors.json contents as the source of truth."""
    return _estimator_for_defaults.vendors
