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


class Reference(BaseModel):
    """A citation for the estimation methodology."""

    key: str = Field(..., description="Reference number, e.g. '1'")
    citation: str = Field(..., description="Full citation text")
    url: str | None = Field(default=None, description="URL (arXiv, DOI, etc.)")


class ResourceDetail(BaseModel):
    """QEC resource estimation breakdown."""

    error_correction_code: str = Field(
        ..., description="Name of the QEC code used (e.g. 'Rotated Surface Code')"
    )
    code_distance: int = Field(..., description="Code distance d")
    logical_error_rate: float = Field(
        ..., description="Logical error per QEC cycle at chosen d"
    )
    num_t_gates: int = Field(
        ..., description="Total T-gate count (explicit + Toffoli decomposition)"
    )
    num_factories: int = Field(
        ..., description="Number of non-Clifford gate production units"
    )
    data_qubits: int = Field(
        ..., description="Physical qubits for data + routing (excluding factories)"
    )
    distillation_qubits: int = Field(
        ..., description="Physical qubits for T-state production"
    )
    physical_qubits_per_logical: int = Field(
        ..., description="Physical qubits per logical qubit (before routing)"
    )
    routing_overhead: float = Field(
        ..., description="Routing multiplier applied to data qubits"
    )
    factory_qubits_each: int = Field(
        ..., description="Physical qubits per single magic state factory"
    )
    t_states_per_factory: int = Field(
        ..., description="T-state throughput per factory"
    )
    references: list[Reference] = Field(
        default_factory=list, description="Citations for the estimation methodology"
    )


# Backward-compatible alias
GoogleResourceDetail = ResourceDetail


class GateDecompositionEntry(BaseModel):
    """Per-gate decomposition into vendor-native gates."""

    gate: str = Field(..., description="Circuit gate name, e.g. 'cx'")
    count: int = Field(..., description="How many in the circuit")
    native_1q: int = Field(..., description="Native 1Q operations after decomposition")
    native_2q: int = Field(..., description="Native 2Q operations after decomposition")


class VendorResourceEstimate(BaseModel):
    name: str
    physical_qubits: int
    physical_gates: int
    success_probability: float
    runtime_seconds: float
    native_1q_count: int = Field(
        default=0, description="Total native 1Q gates after decomposition"
    )
    native_2q_count: int = Field(
        default=0, description="Total native 2Q gates after decomposition"
    )
    native_2q_gate: str = Field(
        default="CX", description="Name of native 2Q gate (e.g. '√iSWAP')"
    )
    gate_decomposition: list[GateDecompositionEntry] = Field(
        default_factory=list, description="Per-gate breakdown for gates modal"
    )
    fidelity_1q: float = Field(
        default=0.0, description="Vendor 1Q gate fidelity"
    )
    fidelity_2q: float = Field(
        default=0.0, description="Vendor 2Q gate fidelity"
    )
    fidelity_readout: float = Field(
        default=0.0, description="Vendor readout/measurement fidelity"
    )
    gate_time_2q: float = Field(
        default=0.0, description="Vendor 2Q gate time in seconds"
    )
    detail: ResourceDetail | None = Field(
        default=None,
        description="QEC estimation breakdown (present for all vendors with QEC estimation)",
    )


class QasmAnalyzeResponse(BaseModel):
    circuit_qubits: int = Field(..., description="Logical qubits in the circuit")
    circuit_gates: int = Field(..., description="Total gate operations in the circuit")
    circuit_depth: int = Field(default=0, description="Circuit depth from pyqasm")
    gate_breakdown: list[GateCategoryBreakdown]
    vendors: list[VendorResourceEstimate]
