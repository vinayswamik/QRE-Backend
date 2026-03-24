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


class GoogleResourceDetail(BaseModel):
    """Surface code estimation breakdown for Google Willow."""

    code_distance: int = Field(..., description="Surface code distance d")
    logical_error_rate: float = Field(
        ..., description="Logical error per surface code cycle at chosen d"
    )
    num_t_gates: int = Field(
        ..., description="Total T-gate count (explicit + Toffoli decomposition)"
    )
    num_factories: int = Field(
        ..., description="Number of magic state distillation factories"
    )
    data_qubits: int = Field(
        ..., description="Physical qubits for data + routing (excluding factories)"
    )
    distillation_qubits: int = Field(
        ..., description="Physical qubits for magic state factories"
    )


class VendorResourceEstimate(BaseModel):
    name: str
    physical_qubits: int
    physical_gates: int
    success_probability: float
    runtime_seconds: float
    detail: GoogleResourceDetail | None = Field(
        default=None,
        description="Detailed breakdown (present for vendors with surface-code estimation)",
    )


class QasmAnalyzeResponse(BaseModel):
    circuit_qubits: int = Field(..., description="Logical qubits in the circuit")
    circuit_gates: int = Field(..., description="Total gate operations in the circuit")
    gate_breakdown: list[GateCategoryBreakdown]
    vendors: list[VendorResourceEstimate]
