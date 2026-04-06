"""QASM validation and analysis route handlers."""

from fastapi import APIRouter

from app.models.qasm import (
    QasmAnalyzeRequest,
    QasmValidateRequest,
)
from app.services.qasm_validator import analyze_qasm, validate_qasm

router = APIRouter(prefix="/qasm", tags=["qasm"])


@router.post(
    "/validate",
    summary="Validate OpenQASM code",
    description="Parse and semantically validate an OpenQASM 2.0/3.0 program.",
)
def validate(payload: QasmValidateRequest):
    """Validate an OpenQASM 2.0/3.0 program and return parse/semantic results."""
    return validate_qasm(payload.code)


@router.post(
    "/analyze",
    summary="Analyze OpenQASM circuit resources",
    description="Run quantum resource estimation across all vendors using Azure QRE.",
)
def analyze(payload: QasmAnalyzeRequest):
    """Run quantum resource estimation across all vendors for the given circuit."""
    return analyze_qasm(payload.code)
