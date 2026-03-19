# QRE Backend

REST API for validating and analyzing OpenQASM quantum circuits. Given a QASM 2.0 or 3.0 program, it validates syntax and semantics, then estimates physical resource requirements (qubits, gates, success probability, runtime) across six quantum hardware vendors: Google, IBM, IonQ, Quantinuum, Rigetti, and Atom Computing.

## API Reference

### `POST /api/v1/qasm/validate`

Validates an OpenQASM 2.0/3.0 program using pyqasm.

**Request**
```json
{ "code": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[2];\nh q[0];\ncx q[0],q[1];" }
```

**Response**
```json
{ "valid": true, "message": "QASM code is valid", "error_type": null }
```

On failure: `"valid": false` with `"message"` and `"error_type"` populated.

---

### `POST /api/v1/qasm/analyze`

Analyzes a valid circuit and returns per-vendor physical resource estimates. Assumes the circuit is already valid — run `/validate` first.

**Request**
```json
{ "code": "OPENQASM 2.0;\n..." }
```

**Response**
```json
{
  "circuit_qubits": 2,
  "circuit_gates": 2,
  "gate_breakdown": [
    { "name": "1Q", "value": 1, "percentage": 50.0, "gates": [{ "name": "h", "count": 1, "percentage": 50.0 }] },
    { "name": "2Q", "value": 1, "percentage": 50.0, "gates": [{ "name": "cx", "count": 1, "percentage": 50.0 }] },
    { "name": "Toffoli", "value": 0, "percentage": 0.0, "gates": [] }
  ],
  "vendors": [
    {
      "name": "Google",
      "physical_qubits": 202,
      "physical_gates": 628,
      "success_probability": 99.45,
      "runtime_seconds": 0.000000045
    }
  ]
}
```

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

cp .env.example .env            # edit as needed

uvicorn app.main:app --reload
```

API available at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

## Running Tests

```bash
pytest
```

## Deployment (AWS Lambda)

The app uses [Mangum](https://mangum.fastapiexpert.com/) as an ASGI adapter for AWS Lambda + API Gateway.

Lambda handler entrypoint: `handler.lambda_handler`

Set the following environment variables in your Lambda function configuration (see `.env.example` for reference):

| Variable | Required |
|----------|----------|
| `APP_NAME` | No — defaults to `QRE Backend` |
| `APP_VERSION` | No — defaults to `0.1.0` |
| `DEBUG` | No — defaults to `false` |
| `CORS_ORIGINS` | Yes — JSON array of allowed origins |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `QRE Backend` | Application name shown in docs |
| `APP_VERSION` | `0.1.0` | Version string returned by `/health` |
| `DEBUG` | `false` | Enables DEBUG-level logging |
| `CORS_ORIGINS` | `["http://localhost:5173", ...]` | JSON array of allowed CORS origins |

## Architecture

Stateless request/response — no database.

```
API Gateway → Lambda
    → Mangum (ASGI adapter)       [handler.py]
    → FastAPI app                 [app/main.py]
    → Route handler               [app/api/v1/routes/qasm.py]
    → Service layer               [app/services/qasm_validator.py]
    → pyqasm (parsing/validation)
    → JSON response
```

Vendor hardware specs live in [`app/core/vendors.json`](app/core/vendors.json) and are loaded once at startup. To update specs, edit that file — no Python changes needed.
