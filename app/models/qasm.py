"""Request and response models for the QASM validation and analysis API."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class QasmValidateRequest(BaseModel):
    """Payload for the /qasm/validate endpoint."""

    code: str = Field(
        ...,
        min_length=1,
        max_length=100_000,
        description="OpenQASM source code to validate",
    )


class QasmValidateResponse(BaseModel):
    """Result of QASM validation indicating success or error details."""

    valid: bool = Field(..., description="Whether the QASM code is valid")
    message: str = Field(..., description="Human-readable result or error description")
    error_type: str | None = Field(
        default=None, description="Exception class name when validation fails"
    )
    line: int | None = Field(
        default=None,
        description="1-indexed line number of the offending token, if known",
    )
    column: int | None = Field(
        default=None, description="0-indexed column of the offending token, if known"
    )
    snippet: str | None = Field(
        default=None, description="The source line where the error occurred, if known"
    )
    hint: str | None = Field(
        default=None, description="Short human hint for the class of error"
    )


class VendorOverride(BaseModel):
    """Per-vendor parameter override.

    Any combination of `qubit_params`, `qec_scheme`, and `max_code_distance`
    may be supplied; only the fields present are merged over the defaults from
    vendors.json. Unknown keys are rejected so typos fail fast instead of
    silently no-op'ing.
    """

    qubit_params: dict[str, Any] | None = None
    qec_scheme: dict[str, Any] | None = None
    max_code_distance: int | None = None

    model_config = {"extra": "forbid"}


class CustomVendorSpec(BaseModel):
    """A user-supplied vendor spec mirroring the shape of vendors.json entries.

    Unlike VendorOverride (which only layers a few fields on top of a built-in
    vendor), this carries a complete standalone vendor that runs side-by-side
    with the built-ins. All top-level hardware metadata is required so the
    frontend can render the result consistently; qubit_params and qec_scheme
    are validated at the estimator layer (see `_validate_vendor_spec`).
    """

    processor: str = Field(..., min_length=1, max_length=120)
    technology: str = Field(..., min_length=1, max_length=120)
    year: int | None = Field(default=None, ge=1900, le=2100)
    source: str = Field(default="", max_length=400)
    qubit_params: dict[str, Any]
    qec_scheme: dict[str, Any]
    max_code_distance: int | None = Field(default=None, ge=3, le=10_000)

    model_config = {"extra": "forbid"}


MAX_CUSTOM_VENDORS = 3


class QasmAnalyzeRequest(BaseModel):
    """Payload for the /qasm/analyze endpoint."""

    code: str = Field(
        ...,
        min_length=1,
        max_length=100_000,
        description="OpenQASM source code to analyze",
    )
    vendor_overrides: dict[str, VendorOverride] | None = Field(
        default=None,
        description=(
            "Optional per-vendor parameter overrides keyed by backend vendor "
            "name (e.g. 'Google Willow'). Only the supplied fields are merged "
            "over the defaults; everything else falls back to vendors.json."
        ),
    )
    custom_vendors: dict[str, CustomVendorSpec] | None = Field(
        default=None,
        description=(
            f"Optional user-defined vendors, up to {MAX_CUSTOM_VENDORS}, "
            "keyed by display name. Each entry is a full vendor spec and is "
            "estimated alongside the built-in vendors. Names must not collide "
            "with built-in vendors."
        ),
    )

    @field_validator("custom_vendors")
    @classmethod
    def _cap_custom_vendors(
        cls, v: dict[str, CustomVendorSpec] | None
    ) -> dict[str, CustomVendorSpec] | None:
        if v is None:
            return v
        if len(v) > MAX_CUSTOM_VENDORS:
            raise ValueError(
                f"At most {MAX_CUSTOM_VENDORS} custom vendors allowed "
                f"(got {len(v)})"
            )
        for name in v:
            stripped = name.strip()
            if not stripped:
                raise ValueError("Custom vendor names must be non-empty")
            if len(stripped) > 60:
                raise ValueError(
                    f"Custom vendor name too long ({len(stripped)} chars, max 60)"
                )
        return v


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
    runtime_seconds: float | None = None
    physical_qubits: int | None = None
    logical_error_rate: float | None = None

    # Enriched Q# fields (status == "success" only). Every field is optional
    # so "not_available" / "above_threshold" / "error" responses don't need
    # to populate them.
    rqops: float | None = None
    clock_frequency: float | None = None
    code_distance: int | None = None
    physical_qubits_for_algorithm: int | None = None
    physical_qubits_for_tfactories: int | None = None
    algorithmic_logical_qubits: int | None = None
    algorithmic_logical_depth: int | None = None
    logical_depth: int | None = None
    num_tstates: int | None = None
    num_tfactories: int | None = None
    num_tfactory_runs: int | None = None
    required_logical_qubit_error_rate: float | None = None
    required_logical_tstate_error_rate: float | None = None
    clifford_error_rate: float | None = None
    logical_cycle_time_ns: float | None = None
    tfactory_physical_qubits: int | None = None
    tfactory_runtime_seconds: float | None = None
    tfactory_num_rounds: int | None = None
    formatted: dict[str, Any] | None = None

    # Present when status == "not_available"
    reason: str | None = None

    # Present when status in ("above_threshold", "error")
    detail: str | None = None

    # Present when status == "above_threshold"
    failing_field: str | None = None
    failing_value: float | None = None


class QasmAnalyzeResponse(BaseModel):
    """Full analysis response with circuit metadata, gate breakdown, and vendor estimates."""

    circuit_qubits: int
    circuit_gates: int
    circuit_depth: int
    gate_breakdown: list[GateCategoryBreakdown]
    vendors: dict[str, VendorEstimateResult]
