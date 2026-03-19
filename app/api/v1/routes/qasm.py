from fastapi import APIRouter

from app.models.qasm import QasmAnalyzeRequest, QasmAnalyzeResponse, QasmValidateRequest, QasmValidateResponse
from app.services.qasm_validator import analyze_qasm, validate_qasm

router = APIRouter(prefix="/qasm", tags=["qasm"])


@router.post(
    "/validate",
    response_model=QasmValidateResponse,
    summary="Validate OpenQASM code",
    description="Parse and semantically validate an OpenQASM 2.0/3.0 program using pyqasm.",
)
def validate(payload: QasmValidateRequest) -> QasmValidateResponse:
    return validate_qasm(payload.code)


@router.post(
    "/analyze",
    response_model=QasmAnalyzeResponse,
    summary="Analyze OpenQASM circuit resources",
    description="Parse a valid OpenQASM program and return per-vendor physical qubit/gate estimates.",
)
def analyze(payload: QasmAnalyzeRequest) -> QasmAnalyzeResponse:
    return analyze_qasm(payload.code)
