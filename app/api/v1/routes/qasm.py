"""QASM validation and analysis route handlers."""

from fastapi import APIRouter, Depends, HTTPException

from app.models.qasm import (
    QasmAnalyzeRequest,
    QasmValidateRequest,
)
from app.core.rate_limit import (
    enforce_analyze_rate_limit,
    enforce_validate_rate_limit,
)
from app.services.qasm_validator import analyze_qasm, validate_qasm
from app.services.quantum_estimator import QuantumEstimator

router = APIRouter(prefix="/qasm", tags=["qasm"])

_estimator_for_defaults = QuantumEstimator()


@router.post(
    "/validate",
    summary="Validate OpenQASM code",
    description="Parse and semantically validate an OpenQASM 2.0/3.0 program.",
    dependencies=[Depends(enforce_validate_rate_limit)],
)
def validate(payload: QasmValidateRequest):
    """Validate an OpenQASM 2.0/3.0 program and return parse/semantic results."""
    return validate_qasm(payload.code)


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
    except ValueError as exc:
        # Raised when custom vendor names collide with built-in vendors.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
