# QRE Backend

**Quantum Resource Estimator** — a REST API for validating and analyzing OpenQASM quantum circuits. Submit a QASM 2.0 or 3.0 program and get back validated syntax plus physical resource estimates across eight real quantum hardware vendors, each modeled with its own error correction code and hardware parameters.

## Supported Vendors

| Vendor | Chip | Error Correction Model |
|---|---|---|
| Google | Willow | Rotated Surface Code |
| IBM | Heron R3 | Bivariate Bicycle (BB) Code |
| IonQ | Forte Enterprise | Bivariate Bicycle 5 (BB5) Code |
| Quantinuum | Helios | Color Code |
| Rigetti | Ankaa-3 | Surface Code |
| Atom Computing | AC1000 | 4D Geometric Code [[96,6,8]] |
| QuEra | Aquila | Surface Code |
| Quandela | Belenos | Honeycomb Floquet Code |

## Stack

- **Framework:** FastAPI
- **QASM parsing:** pyqasm
- **Runtime:** Python 3.13 (AWS Lambda)

---

## API Reference

### `POST /api/v1/qasm/validate`

Validates an OpenQASM 2.0/3.0 program.

**Request**
```json
{
  "code": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[2];\nh q[0];\ncx q[0],q[1];"
}
```

**Response — success**
```json
{ "valid": true, "message": "QASM code is valid", "error_type": null }
```

**Response — failure**
```json
{ "valid": false, "message": "Qubit index out of range", "error_type": "SemanticError" }
```

---

### `POST /api/v1/qasm/analyze`

Analyzes a circuit and returns per-vendor physical resource estimates. Run `/validate` first — this endpoint assumes the QASM is already valid.

**Request**
```json
{ "code": "OPENQASM 2.0;\n..." }
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
      "gates": [{ "name": "h", "count": 1, "percentage": 50.0 }]
    },
    {
      "name": "2Q",
      "value": 1,
      "percentage": 50.0,
      "gates": [{ "name": "cx", "count": 1, "percentage": 50.0 }]
    },
    { "name": "Toffoli", "value": 0, "percentage": 0.0, "gates": [] }
  ],
  "vendors": [
    {
      "name": "Google",
      "physical_qubits": 202,
      "physical_gates": 628,
      "success_probability": 99.45,
      "runtime_seconds": 4.5e-8,
      "native_1q_count": 3,
      "native_2q_count": 1,
      "native_2q_gate": "√iSWAP",
      "fidelity_1q": 0.99965,
      "fidelity_2q": 0.9967,
      "fidelity_readout": 0.9923,
      "gate_time_2q": 3.4e-8,
      "gate_decomposition": [
        { "gate": "h", "count": 1, "native_1q": 2, "native_2q": 0 },
        { "gate": "cx", "count": 1, "native_1q": 1, "native_2q": 1 }
      ],
      "detail": {
        "error_correction_code": "Rotated Surface Code",
        "code_distance": 3,
        "logical_error_rate": 1.2e-6,
        "num_t_gates": 0,
        "num_factories": 0,
        "data_qubits": 202,
        "distillation_qubits": 0,
        "physical_qubits_per_logical": 18,
        "routing_overhead": 1.5,
        "factory_qubits_each": 0,
        "t_states_per_factory": 0,
        "references": [
          {
            "key": "1",
            "citation": "Google Quantum AI, Nature 614 (2023)",
            "url": "https://doi.org/10.1038/s41586-022-05434-1"
          }
        ]
      }
    }
  ]
}
```

**Vendor fields**

| Field | Description |
|---|---|
| `physical_qubits` | Total physical qubits required |
| `physical_gates` | Total physical gate operations |
| `success_probability` | Circuit-level success probability (%) |
| `runtime_seconds` | Estimated wall-clock runtime |
| `native_1q_count` / `native_2q_count` | Gate counts after decomposition to vendor native gates |
| `native_2q_gate` | Vendor's native 2Q gate (e.g. `√iSWAP`, `ZZ`, `MS`) |
| `fidelity_1q` / `fidelity_2q` / `fidelity_readout` | Vendor hardware fidelities |
| `gate_decomposition` | Per-gate breakdown into native 1Q/2Q operations |
| `detail` | Full QEC breakdown: code distance, logical error rate, T-factory counts, and literature references |

---

### `GET /health`

```json
{ "status": "ok", "version": "0.1.0" }
```

Interactive docs available at `/docs` (Swagger UI) and `/redoc` when running locally.

---

## Local Development

**Prerequisites:** Python 3.11+

```bash
git clone <repo-url>
cd QRE-Backend

python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt

cp .env.example .env            # edit CORS_ORIGINS as needed

uvicorn app.main:app --reload
```

API available at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

## Running Tests

```bash
pytest
```
