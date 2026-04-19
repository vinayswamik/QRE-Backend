# QRE Backend

QRE Backend is a FastAPI service for validating and analyzing OpenQASM 2.0/3.0 circuits.
It combines `pyqasm` parsing with Azure Quantum Resource Estimator (Q#) to return
fault-tolerant physical resource estimates across multiple real hardware vendors.

---

## What This API Does

- Validates QASM syntax and semantics with structured error diagnostics.
- Analyzes gate counts, qubit count, and circuit depth.
- Estimates fault-tolerant resources across vendor hardware profiles.
- Supports per-request vendor parameter overrides.
- Supports up to 3 custom user-defined vendors per request.

---

## Supported Vendors

The backend currently estimates against these built-in active vendors:

| Vendor | Processor | Technology | QEC Scheme |
|---|---|---|---|
| Google Willow | Willow (105 qubits) | Superconducting (transmon) | `surface_code` |
| IBM Heron R3 | Heron R3 / ibm_boston (156 qubits) | Superconducting (transmon, tunable coupler) | `ibm_qldpc_bivariate_bicycle` |
| Rigetti Ankaa-3 | Ankaa-3 (84 qubits) | Superconducting | `surface_code` |
| IonQ Tempo | Tempo (100 qubits, #AQ 64, all-to-all) | Trapped Ion (Barium-137) | `surface_code` |
| Quantinuum Helios | Helios (98 qubits, all-to-all via QCCD shuttling) | Trapped Ion (QCCD architecture, Ba-137, Yb-171 coolant) | `quantinuum_color_code` |
| Atom Computing | AC1000 (>1200 qubits, Yb-171 nuclear-spin) | Neutral Atom (Ytterbium-171) | `surface_code` |
| QuEra Gemini | Gemini (260 qubits, Rb-87, DQA shuttling) | Neutral Atom (Rubidium-87, Rydberg gates) | `surface_code` |

Note: unavailable vendors listed in `app/core/vendors.json` are excluded from `/analyze` results.

---

## Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI |
| QASM Parsing | pyqasm |
| Resource Estimation | Azure Quantum Resource Estimator (Q#) |
| Runtime | Python 3.13 |
| AWS Runtime | Lambda (Mangum adapter) |
| Config | Pydantic Settings |

---

## API Reference

Base URL (local): `http://localhost:8000`

Interactive docs:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### `POST /api/v1/qasm/validate`

Validate an OpenQASM 2.0/3.0 program.

**Request**

```json
{
  "code": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[2];\nh q[0];\ncx q[0],q[1];"
}
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `valid` | `bool` | Whether validation succeeded |
| `message` | `string` | Human-readable success/failure message |
| `error_type` | `string \| null` | Exception class for failures |
| `line` | `int \| null` | 1-indexed error line when known |
| `column` | `int \| null` | 0-indexed error column when known |
| `snippet` | `string \| null` | Source line near the failure |
| `hint` | `string \| null` | Friendly hint for the error class |

**Example invalid response**

```json
{
  "valid": false,
  "message": "Qubit index out of range",
  "error_type": "ValidationError",
  "line": 4,
  "column": 2,
  "snippet": "h q[5];",
  "hint": "Validation failed. Check register sizes, gate names, and argument counts."
}
```

---

### `POST /api/v1/qasm/analyze`

Analyze a circuit and estimate resources across active vendors.

The request supports:
- `vendor_overrides`: patch selected fields (`qubit_params`, `qec_scheme`, `max_code_distance`) for built-in vendors.
- `custom_vendors`: add up to 3 full vendor specs estimated alongside built-ins.

**Request (full shape)**

```json
{
  "code": "OPENQASM 3.0;\ninclude \"stdgates.inc\";\nqubit[2] q;\nbit[2] c;\nh q[0];\ncx q[0], q[1];\nc = measure q;",
  "vendor_overrides": {
    "Google Willow": {
      "qubit_params": {
        "two_qubit_gate_error_rate": 0.0015
      },
      "max_code_distance": 400
    }
  },
  "custom_vendors": {
    "MyLab QPU": {
      "processor": "Lab 9000",
      "technology": "Exotic",
      "year": 2026,
      "source": "internal",
      "qubit_params": {
        "name": "mylab",
        "instruction_set": "GateBased",
        "one_qubit_gate_time": "10 ns",
        "two_qubit_gate_time": "20 ns",
        "one_qubit_measurement_time": "200 ns",
        "one_qubit_gate_error_rate": 0.0001,
        "two_qubit_gate_error_rate": 0.001,
        "one_qubit_measurement_error_rate": 0.001,
        "t_gate_time": "10 ns",
        "t_gate_error_rate": 0.0001,
        "idle_error_rate": 0.00001
      },
      "qec_scheme": {
        "name": "surface_code",
        "crossing_prefactor": 0.03,
        "error_correction_threshold": 0.01,
        "distance_coefficient_power": 0,
        "logical_cycle_time": "(4 * twoQubitGateTime + 2 * oneQubitMeasurementTime) * codeDistance",
        "physical_qubits_per_logical_qubit": "2 * codeDistance * codeDistance"
      },
      "max_code_distance": 500
    }
  }
}
```

**Top-level response**

| Field | Type | Description |
|---|---|---|
| `circuit_qubits` | `int` | Number of logical qubits |
| `circuit_gates` | `int` | Total physical gate count used by analysis |
| `circuit_depth` | `int` | Circuit depth after preprocessing |
| `gate_breakdown` | `array` | Categories `1Q`, `2Q`, `Toffoli` with detailed gate counts |
| `vendors` | `object` | Map of vendor name to estimate result |

**Vendor `status` values**

| Status | Meaning |
|---|---|
| `success` | Estimation completed successfully |
| `above_threshold` | A physical error rate exceeds the vendor QEC threshold |
| `error` | Spec invalid or estimator failed |
| `not_available` | Reserved status in schema (unavailable built-ins are currently excluded from `/analyze`) |

**Common vendor fields**

| Field | Type |
|---|---|
| `status` | `string` |
| `processor` | `string` |
| `technology` | `string` |
| `year` | `int \| null` |
| `source` | `string` |

**`success` fields (selected)**

| Field | Type |
|---|---|
| `qec_scheme` | `string` |
| `runtime` | `string` |
| `runtime_seconds` | `float` |
| `physical_qubits` | `int` |
| `logical_error_rate` | `float` |
| `rqops` | `float` |
| `clock_frequency` | `float` |
| `code_distance` | `int` |
| `physical_qubits_for_algorithm` | `int` |
| `physical_qubits_for_tfactories` | `int` |
| `formatted` | `object` |

Additional enriched fields are also returned (for example algorithmic logical depth, T-factory metrics, required logical error rates).

**`above_threshold` fields**

| Field | Type |
|---|---|
| `detail` | `string` |
| `failing_field` | `string` |
| `failing_value` | `float` |

**`error` fields**

| Field | Type |
|---|---|
| `detail` | `string` |

---

### `POST /api/v1/qasm/analyze/stream`

Streaming variant of `/analyze` using Server-Sent Events (SSE).

- Same request body as `POST /api/v1/qasm/analyze`.
- Returns `text/event-stream` and emits progress as each vendor completes.
- Event types: `stage`, `circuit_metadata`, `vendor_result`, `complete`, `error`.

Useful when the frontend wants incremental progress instead of waiting for the full vendor map.

---

### `GET /api/v1/qasm/limits`

Return backend-enforced input caps so clients can pre-validate before hitting rate-limited endpoints.

Response fields:

| Field | Type | Description |
|---|---|---|
| `max_qasm_bytes` | `int` | Maximum request QASM size in bytes |
| `max_qubits` | `int` | Maximum allowed circuit qubits |
| `max_gate_count` | `int` | Maximum allowed circuit gate count |
| `max_circuit_depth` | `int` | Maximum allowed circuit depth |

When `validate`/`analyze` exceed structural caps, the API returns HTTP `413` with structured detail.

---

### `GET /api/v1/qasm/vendor-defaults`

Return raw vendor defaults (the `vendors.json` source of truth), used by clients to seed override UIs.

Response type: `dict[str, dict]`

---

### `GET /health`

Service health/version probe.

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

## Local Development

### Prerequisites

- Python 3.13
- `pip`
- Docker (only for local Lambda image testing)

### Setup

```bash
git clone <repo-url>
cd QRE-Backend

python3 -m venv qre-env
source qre-env/bin/activate

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Run API (hot reload)

```bash
uvicorn app.main:app --reload
```

Or via Make target:

```bash
make dev
```

---

## Testing

Run Python tests:

```bash
pytest
```

Run a subset:

```bash
pytest tests/test_qasm_validation.py
pytest -k "bell"
```

Run Dockerized Lambda smoke test (`/health`, `/validate`, `/analyze`):

```bash
make test
```

---

## Deployment

GitHub Actions workflow: `.github/workflows/deploy.yml`

Current deployment trigger:
- Manual run only (`workflow_dispatch`)

The workflow:
- Builds and pushes an `linux/amd64` image to ECR.
- Creates or updates the Lambda function as image-based runtime.
- Applies memory/timeout config.
- Re-attaches API Gateway invoke permission idempotently.

### Operational hardening

- Security headers are attached to all API responses (`CSP`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`; `HSTS` on HTTPS).
- Per-client rate limiting is enforced for:
  - `POST /api/v1/qasm/validate`
  - `POST /api/v1/qasm/analyze`

Environment-tunable settings:

```bash
RATE_LIMIT_ENABLED=true
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_VALIDATE_REQUESTS=500
RATE_LIMIT_ANALYZE_REQUESTS=200

# Input-size and structural circuit caps
MAX_QASM_BYTES=10000000
MAX_QUBITS=200
MAX_GATE_COUNT=2000000
MAX_CIRCUIT_DEPTH=500000
```

---

## Project Layout

```text
app/
  api/v1/routes/qasm.py         # /validate, /analyze, /analyze/stream, /limits, /vendor-defaults
  core/config.py                # pydantic settings (CORS, app name/version, debug, rate limits)
  core/rate_limit.py            # in-memory per-client endpoint throttling
  core/vendors.json             # vendor hardware and QEC source-of-truth
  models/qasm.py                # request/response schemas
  services/qasm_validator.py    # parse/validate and gate analysis
  services/quantum_estimator.py # Azure QRE vendor estimation engine
  main.py                       # FastAPI app wiring + CORS + /health
handler.py                      # AWS Lambda Mangum adapter entrypoint
tests/                          # API and service tests
docs/adr/                       # architecture decision records
```

---

## Notes

- Vendor cache keys are based on `hash(vendor_config + circuit_string)`.
- Circuit preprocessing includes unrolling, barrier removal, and gate decomposition.
- Vendor feasibility checks run before Q# to catch above-threshold error-rate configs early.
- Release notes are tracked in `CHANGELOG.md`; architectural decisions are tracked in `docs/adr/`.
