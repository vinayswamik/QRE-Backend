"""
Tests for input size enforcement.

Covers:
  1. GET /qasm/limits returns the configured caps.
  2. Structural caps (qubits, gate count, depth) return 413 with detail.
  3. QASM byte-length over max returns 413 with explicit limits payload.
"""

# pylint: disable=duplicate-code,missing-class-docstring,missing-function-docstring

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.core.config import settings
from app.main import app

client = TestClient(app)

VALIDATE = "/api/v1/qasm/validate"
ANALYZE = "/api/v1/qasm/analyze"
LIMITS = "/api/v1/qasm/limits"


def _large_qubit_circuit(n: int) -> str:
    """Build a QASM 2.0 program with `n` qubits and a single H on each.

    Used to exercise the qubit cap without paying the cost of producing
    enough gates to trip the gate cap.
    """
    body = "\n".join(f"h q[{i}];" for i in range(n))
    return f'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[{n}];\n{body}\n'


class TestLimitsEndpoint:
    def test_returns_configured_caps(self):
        resp = client.get(LIMITS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_qasm_bytes"] == settings.MAX_QASM_BYTES
        assert data["max_qubits"] == settings.MAX_QUBITS
        assert data["max_gate_count"] == settings.MAX_GATE_COUNT
        assert data["max_circuit_depth"] == settings.MAX_CIRCUIT_DEPTH


class TestQubitCap:
    def test_validate_rejects_oversized_qubits_with_413(self, monkeypatch: MonkeyPatch):
        # Shrink the cap for the test so we don't have to build a 300-qubit
        # circuit just to trip it. Restored after the test.
        monkeypatch.setattr(settings, "MAX_QUBITS", 5)
        code = _large_qubit_circuit(10)
        resp = client.post(VALIDATE, json={"code": code})
        assert resp.status_code == 413
        detail = resp.json()["detail"]
        assert detail["error"] == "circuit_too_large"
        assert detail["field"] == "qubits"
        assert detail["value"] == 10
        assert detail["limit"] == 5
        assert detail["limits"]["max_qubits"] == 5

    def test_analyze_rejects_oversized_qubits_with_413(self, monkeypatch: MonkeyPatch):
        monkeypatch.setattr(settings, "MAX_QUBITS", 5)
        code = _large_qubit_circuit(10)
        resp = client.post(ANALYZE, json={"code": code})
        assert resp.status_code == 413
        detail = resp.json()["detail"]
        assert detail["field"] == "qubits"


class TestGateCap:
    def test_rejects_oversized_gate_count(self, monkeypatch: MonkeyPatch):
        monkeypatch.setattr(settings, "MAX_GATE_COUNT", 3)
        code = (
            "OPENQASM 2.0;\n"
            'include "qelib1.inc";\n'
            "qreg q[1];\n"
            "h q[0]; x q[0]; y q[0]; z q[0]; h q[0];\n"
        )
        resp = client.post(VALIDATE, json={"code": code})
        assert resp.status_code == 413
        detail = resp.json()["detail"]
        assert detail["error"] == "circuit_too_large"
        assert detail["field"] == "gate_count"
        assert detail["limit"] == 3


class TestByteLengthCap:
    def test_at_boundary_accepted(self):
        """A payload below MAX_QASM_BYTES reaches the handler (even if the
        QASM itself is garbage, we only need Pydantic to accept)."""
        code = "x" * settings.MAX_QASM_BYTES
        resp = client.post(VALIDATE, json={"code": code})
        # Anything below the Pydantic ceiling should make it past request
        # validation; the response may be 200 (with valid=False) or 413.
        assert resp.status_code != 422

    def test_over_boundary_returns_413_with_limits(self):
        code = "x" * (settings.MAX_QASM_BYTES + 1)
        resp = client.post(VALIDATE, json={"code": code})
        assert resp.status_code == 413
        detail = resp.json()["detail"]
        assert detail["error"] == "qasm_payload_too_large"
        assert detail["field"] == "qasm_byte_length"
        assert detail["limit"] == settings.MAX_QASM_BYTES
        assert detail["limits"]["max_qasm_bytes"] == settings.MAX_QASM_BYTES


class TestStreamingEndpoint:
    def test_stream_bell_state_emits_stages_and_vendor_results(self):
        code = (
            "OPENQASM 2.0;\n"
            'include "qelib1.inc";\n'
            "qreg q[2]; creg c[2];\n"
            "h q[0]; cx q[0],q[1];\n"
            "measure q -> c;\n"
        )
        with client.stream(
            "POST", "/api/v1/qasm/analyze/stream", json={"code": code}
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            body = "".join(resp.iter_text())

        # Stages, circuit metadata, at least one vendor_result, and a
        # terminal complete event should all be present.
        assert "event: stage" in body
        assert "event: circuit_metadata" in body
        assert "event: vendor_result" in body
        assert "event: complete" in body

    def test_stream_oversized_yields_error_event(self, monkeypatch: MonkeyPatch):
        monkeypatch.setattr(settings, "MAX_QUBITS", 1)
        code = _large_qubit_circuit(3)
        with client.stream(
            "POST", "/api/v1/qasm/analyze/stream", json={"code": code}
        ) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())
        assert "event: error" in body
        assert '"status": 413' in body
        assert "circuit_too_large" in body
        assert "max_qubits" in body

    def test_stream_code_over_byte_cap_returns_http_413(self):
        """Oversized body.code never opens SSE — global validation runs first."""
        code = "x" * (settings.MAX_QASM_BYTES + 1)
        resp = client.post("/api/v1/qasm/analyze/stream", json={"code": code})
        assert resp.status_code == 413
        detail = resp.json()["detail"]
        assert detail["error"] == "qasm_payload_too_large"
