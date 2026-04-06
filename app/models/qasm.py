"""Request and response models for the QASM validation and analysis API."""

from typing import Literal

from pydantic import BaseModel, Field


class QasmValidateRequest(BaseModel):
    """Payload for the /qasm/validate endpoint."""

    code: str = Field(..., min_length=1, description="OpenQASM source code to validate")


class QasmValidateResponse(BaseModel):
    """Result of QASM validation indicating success or error details."""

    valid: bool = Field(..., description="Whether the QASM code is valid")
    message: str = Field(..., description="Human-readable result or error description")
    error_type: str | None = Field(
        default=None, description="Exception class name when validation fails"
    )


class QasmAnalyzeRequest(BaseModel):
    """Payload for the /qasm/analyze endpoint."""

    code: str = Field(..., min_length=1, description="OpenQASM source code to analyze")


class GateDetail(BaseModel):
    """Count and percentage for a single gate type."""

    name: str
    count: int
    percentage: float


class GateCategoryBreakdown(BaseModel):
    """Aggregated gate counts for a qubit-arity category (1Q, 2Q, Toffoli)."""

    name: str
    value: int
    percentage: float
    gates: list[GateDetail]


class VendorEstimateResult(BaseModel):
    """Single vendor estimation result from Azure QRE."""

    status: Literal["success", "not_available", "above_threshold", "error"]
    processor: str
    technology: str
    year: int | None = None
    source: str

    # Present when status == "success"
    qec_scheme: str | None = None
    runtime: str | None = None
    physical_qubits: int | None = None
    total_logical_gates: int | None = None
    logical_error_rate: float | None = None

    # Present when status == "not_available"
    reason: str | None = None

    # Present when status in ("above_threshold", "error")
    detail: str | None = None


class QasmAnalyzeResponse(BaseModel):
    """Full analysis response with circuit metadata, gate breakdown, and vendor estimates."""

    circuit_qubits: int
    circuit_gates: int
    circuit_depth: int
    gate_breakdown: list[GateCategoryBreakdown]
    vendors: dict[str, VendorEstimateResult]
