from pydantic import BaseModel, Field


class QasmValidateRequest(BaseModel):
    code: str = Field(..., min_length=1, description="OpenQASM source code to validate")


class QasmValidateResponse(BaseModel):
    valid: bool = Field(..., description="Whether the QASM code is valid")
    message: str = Field(..., description="Human-readable result or error description")
    error_type: str | None = Field(
        default=None, description="Exception class name when validation fails"
    )


class QasmAnalyzeRequest(BaseModel):
    code: str = Field(..., min_length=1, description="OpenQASM source code to analyze")


class GateDetail(BaseModel):
    name: str
    count: int
    percentage: float


class GateCategoryBreakdown(BaseModel):
    name: str
    value: int
    percentage: float
    gates: list[GateDetail]


class VendorResourceEstimate(BaseModel):
    name: str
    physical_qubits: int
    physical_gates: int
    success_probability: float
    runtime_seconds: float


class QasmAnalyzeResponse(BaseModel):
    circuit_qubits: int = Field(..., description="Logical qubits in the circuit")
    circuit_gates: int = Field(..., description="Total gate operations in the circuit")
    gate_breakdown: list[GateCategoryBreakdown]
    vendors: list[VendorResourceEstimate]
