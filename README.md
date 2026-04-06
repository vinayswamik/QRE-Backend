# QRE Backend

**Quantum Resource Estimator** — a REST API for validating and analyzing OpenQASM quantum circuits. Submit a QASM 2.0 or 3.0 program and receive validated syntax plus fault-tolerant physical resource estimates across real quantum hardware vendors, each modeled with its own error correction scheme and published hardware parameters.

---

## Supported Vendors

| Vendor | Processor | Technology | QEC Scheme |
|---|---|---|---|
| Google | Willow (105 qubits) | Superconducting (transmon) | Rotated Surface Code |
| IBM | Heron R3 (156 qubits) | Superconducting (transmon, tunable coupler) | Bivariate Bicycle (QLDPC) |
| IonQ | Tempo (64 qubits, all-to-all) | Trapped Ion (Yb-171) | Surface Code |
| Quantinuum | Helios (96 qubits) | Trapped Ion (QCCD, Yb-171) | Color Code |
| Rigetti | Ankaa-3 (36 qubits) | Superconducting | Surface Code |
| Atom Computing | AC1000 (>1200 qubits) | Neutral Atom (Yb-171) | Surface Code |
| QuEra | Gemini (260 qubits) | Neutral Atom (Rb-87, Rydberg) | Surface Code |

---

## Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| QASM Parsing | pyqasm |
| Resource Estimation | Azure Quantum Resource Estimator (Q#) |
| Runtime | Python 3.13 |
| Deployment | AWS Lambda via Mangum |

---

## API Reference

Base URL (local): `http://localhost:8000`

Interactive docs: `/docs` (Swagger UI) · `/redoc` (ReDoc)

---

### `POST /api/v1/qasm/validate`

Validates an OpenQASM 2.0 or 3.0 program for syntax and semantic correctness.

**Request**
```json
{
  "code": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[2];\nh q[0];\ncx q[0],q[1];"
}
```

**Response — valid**
```json
{
  "valid": true,
  "message": "QASM code is valid",
  "error_type": null
}
```

**Response — invalid**
```json
{
  "valid": false,
  "message": "Qubit index out of range on line 5",
  "error_type": "SemanticError"
}
```

| Field | Type | Description |
|---|---|---|
| `valid` | `bool` | Whether the QASM code passed validation |
| `message` | `string` | Human-readable result or error description |
| `error_type` | `string \| null` | Exception class name when validation fails (e.g. `QasmParsingError`, `SemanticError`) |

---

### `POST /api/v1/qasm/analyze`

Analyzes a circuit and returns per-vendor fault-tolerant physical resource estimates via Azure Quantum Resource Estimator.

> Tip: run `/validate` first — this endpoint assumes the QASM is syntactically valid.

**Request**
```json
{
  "code": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[2];\nh q[0];\ncx q[0],q[1];"
}
```

**Response**
```json
{
  "circuit_qubits": 2,
  "circuit_gates": 2,
  "circuit_depth": 2,
  "gate_breakdown": [
    {
      "name": "1Q",
      "value": 1,
      "percentage": 50.0,
      "gates": [
        { "name": "h", "count": 1, "percentage": 50.0 }
      ]
    },
    {
      "name": "2Q",
      "value": 1,
      "percentage": 50.0,
      "gates": [
        { "name": "cx", "count": 1, "percentage": 50.0 }
      ]
    },
    {
      "name": "Toffoli",
      "value": 0,
      "percentage": 0.0,
      "gates": []
    }
  ],
  "vendors": {
    // One entry for each of the 7 supported vendors (Google Willow, IBM Heron R3, IonQ Tempo,
    // Quantinuum Helios, Rigetti Ankaa-3, Atom Computing, QuEra Gemini). Shown truncated below.
    "Google Willow": {
      "status": "success",
      "processor": "Willow (105 qubits)",
      "technology": "Superconducting (transmon)",
      "year": 2024,
      "source": "Acharya et al., Nature 638 (2025)",
      "qec_scheme": "surface_code",
      "runtime": "10 microsecs",
      "physical_qubits": 3750,
      "total_logical_gates": 12,
      "logical_error_rate": 2.3e-8
    },
    "IBM Heron R3": {
      "status": "success",
      "processor": "Heron R3 / ibm_boston (156 qubits)",
      "technology": "Superconducting (transmon, tunable coupler)",
      "year": 2025,
      "source": "IBM QDC 2025",
      "qec_scheme": "ibm_qldpc_bivariate_bicycle",
      "runtime": "8 microsecs",
      "physical_qubits": 2100,
      "total_logical_gates": 12,
      "logical_error_rate": 1.1e-8
    },
  }
}
```

#### Circuit Metadata Fields

| Field | Type | Description |
|---|---|---|
| `circuit_qubits` | `int` | Number of logical qubits in the circuit |
| `circuit_gates` | `int` | Total gate count (excluding measurements and barriers) |
| `circuit_depth` | `int` | Critical path length of the circuit |
| `gate_breakdown` | `array` | Gate counts grouped into `1Q`, `2Q`, and `Toffoli` categories |

#### Vendor Result Fields

| Field | Type | Description |
|---|---|---|
| `status` | `string` | One of `success`, `not_available`, `above_threshold`, `error` |
| `processor` | `string` | Vendor chip name and qubit count |
| `technology` | `string` | Underlying qubit technology |
| `year` | `int \| null` | Year of the hardware specification |
| `source` | `string` | Primary literature or spec sheet reference |
| `qec_scheme` | `string \| null` | Error correction scheme used *(success only)* |
| `runtime` | `string \| null` | Estimated fault-tolerant wall-clock runtime *(success only)* |
| `physical_qubits` | `int \| null` | Total physical qubits required including ancilla *(success only)* |
| `total_logical_gates` | `int \| null` | Total logical gate operations after QEC compilation *(success only)* |
| `logical_error_rate` | `float \| null` | Achieved logical error rate per operation *(success only)* |
| `reason` | `string \| null` | Why estimation is unavailable *(not_available only)* |
| `detail` | `string \| null` | Error message or threshold exceeded detail *(above_threshold / error only)* |

#### Vendor Status Values

| Status | Meaning |
|---|---|
| `success` | Estimation completed; full resource breakdown returned |
| `not_available` | Vendor not supported (e.g. photonic, pre-release hardware) |
| `above_threshold` | Physical error rate exceeds the QEC threshold for this vendor |
| `error` | Estimation failed due to an unexpected error |

---

### `GET /health`

Returns the service health and version.

```json
{ "status": "ok", "version": "1.0.0" }
```

---

## Local Development

**Prerequisites:** Python 3.13

```bash
git clone <repo-url>
cd QRE-Backend

python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

pip install -r requirements.txt

uvicorn app.main:app --reload
```

API available at `http://localhost:8000`
Swagger UI at `http://localhost:8000/docs`

---

## Running Tests

```bash
pytest
```

The test suite covers:
- QASM 2.0 and 3.0 validation (syntax errors, semantic errors, edge cases)
- Circuit analysis for 17+ canonical circuits (Bell state, GHZ, QFT, Grover, VQE, QAOA, teleportation, and more)
- Gate breakdown correctness and percentage sums
- Per-vendor resource estimation fields and schema
- Health check, CORS headers, and Lambda handler import

---

## Deployment

CI/CD is automated via GitHub Actions on push to `main`.
