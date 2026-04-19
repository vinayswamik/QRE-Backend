"""
Tests for POST /api/v1/qasm/validate

Covers:
  1. Valid QASM 2.0 / 3.0 programs
  2. Syntax errors (garbage input)
  3. Semantic errors (undeclared registers, type mismatches)
  4. Edge cases (empty body, missing field, whitespace-only code)
"""
# pylint: disable=duplicate-code

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ENDPOINT = "/api/v1/qasm/validate"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_BELL_STATE = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
h q[0];
cx q[0], q[1];
measure q -> c;
"""

VALID_BELL_V3 = """\
OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q; bit[2] c;
h q[0]; cx q[0],q[1];
c = measure q;
"""

VALID_GHZ_5Q = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[5]; creg c[5];
h q[0]; cx q[0],q[1]; cx q[1],q[2]; cx q[2],q[3]; cx q[3],q[4];
measure q -> c;
"""

VALID_SINGLE_QUBIT = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[1]; creg c[1];
h q[0]; t q[0]; s q[0];
measure q -> c;
"""

INVALID_SYNTAX = "this is not valid qasm code !!!"

INVALID_SEMANTIC = """\
OPENQASM 2.0;
include "qelib1.inc";
h q[0];
"""

INVALID_PARTIAL_HEADER = """\
OPENQASM 2.0;
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def post_validate(code: str):
    """Send QASM code to the validate endpoint and return the response."""
    return client.post(ENDPOINT, json={"code": code})


# ---------------------------------------------------------------------------
# Valid QASM
# ---------------------------------------------------------------------------


class TestValidQasm:
    """Well-formed QASM programs should return valid=True."""

    def test_bell_state_v2_returns_valid(self):
        """QASM 2.0 Bell state should validate successfully."""
        resp = post_validate(VALID_BELL_STATE)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert "valid" in data["message"].lower()
        assert data["error_type"] is None

    def test_bell_state_v3_returns_valid(self):
        """QASM 3.0 Bell state should validate successfully."""
        resp = post_validate(VALID_BELL_V3)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["error_type"] is None

    def test_ghz_5q_returns_valid(self):
        """5-qubit GHZ state should validate successfully."""
        resp = post_validate(VALID_GHZ_5Q)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_single_qubit_returns_valid(self):
        """Single-qubit H-T-S circuit should validate successfully."""
        resp = post_validate(VALID_SINGLE_QUBIT)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_response_has_all_fields(self):
        """Response must contain valid, message, and error_type keys."""
        resp = post_validate(VALID_BELL_STATE)
        data = resp.json()
        assert "valid" in data
        assert "message" in data
        assert "error_type" in data


# ---------------------------------------------------------------------------
# Invalid QASM — syntax errors
# ---------------------------------------------------------------------------


class TestSyntaxErrors:
    """Syntactically broken QASM should return valid=False."""

    def test_garbage_input_returns_invalid(self):
        """Non-QASM text should return valid=False with an error type."""
        resp = post_validate(INVALID_SYNTAX)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["message"]  # non-empty
        assert data["error_type"] is not None

    def test_partial_header_only(self):
        """A bare OPENQASM header with no body should return a valid response shape."""
        resp = post_validate(INVALID_PARTIAL_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        # A bare header with no gates/registers may pass or fail
        # depending on pyqasm — just check the shape is correct
        assert isinstance(data["valid"], bool)
        assert isinstance(data["message"], str)


# ---------------------------------------------------------------------------
# Invalid QASM — semantic errors
# ---------------------------------------------------------------------------


class TestSemanticErrors:
    """Semantically invalid QASM (e.g. undeclared registers) should fail."""

    def test_undeclared_register(self):
        """Using an undeclared register should return valid=False."""
        resp = post_validate(INVALID_SEMANTIC)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["message"]
        assert data["error_type"] is not None
        assert "q" in data["message"]


# ---------------------------------------------------------------------------
# Edge cases — request validation (Pydantic)
# ---------------------------------------------------------------------------


class TestRequestValidation:
    """Pydantic request validation edge cases (empty body, wrong types)."""

    def test_empty_code_returns_422(self):
        """min_length=1 on the code field should reject empty strings."""
        resp = client.post(ENDPOINT, json={"code": ""})
        assert resp.status_code == 422

    def test_missing_code_field_returns_422(self):
        """Omitting the code field entirely should return 422."""
        resp = client.post(ENDPOINT, json={})
        assert resp.status_code == 422

    def test_no_body_returns_422(self):
        """Request with no body should return 422."""
        resp = client.post(ENDPOINT)
        assert resp.status_code == 422

    def test_wrong_content_type_returns_422(self):
        """Non-JSON content type should return 422."""
        resp = client.post(
            ENDPOINT, content="not json", headers={"Content-Type": "text/plain"}
        )
        assert resp.status_code == 422

    def test_code_must_be_string(self):
        """Non-string code value should be coerced or rejected."""
        resp = client.post(ENDPOINT, json={"code": 12345})
        # Pydantic coerces int to str or rejects — either way shape is valid
        assert resp.status_code in (200, 422)

    def test_code_exceeding_max_length_returns_422(self):
        """Code strings longer than MAX_QASM_BYTES should be rejected by Pydantic."""
        from app.core.config import settings

        resp = client.post(ENDPOINT, json={"code": "x" * (settings.MAX_QASM_BYTES + 1)})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Rich error diagnostics — line / column / snippet / hint
# ---------------------------------------------------------------------------


OUT_OF_RANGE_QUBIT = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
h q[5];
"""

MISSING_SEMICOLON = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2]
h q[0];
"""

UNDECLARED_GATE = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
foo q[0];
"""


class TestRichErrorDiagnostics:
    """Failed validation should return structured line/snippet/hint fields."""

    def test_semantic_error_has_line_and_snippet(self):
        """Out-of-range qubit index should surface the offending line."""
        resp = post_validate(OUT_OF_RANGE_QUBIT)
        data = resp.json()
        assert data["valid"] is False
        assert data["line"] == 4
        assert data["snippet"] == "h q[5];"
        assert data["hint"]
        assert "5" in data["message"] and "2" in data["message"]

    def test_syntax_error_has_line_from_antlr_token(self):
        """Missing semicolon should still produce a line number via the ANTLR token."""
        resp = post_validate(MISSING_SEMICOLON)
        data = resp.json()
        assert data["valid"] is False
        assert data["line"] is not None
        assert data["snippet"] is not None
        assert data["hint"] is not None
        assert data["error_type"]

    def test_garbage_input_has_location(self):
        """Garbage input should produce a non-empty message and hint, not a dangling colon."""
        resp = post_validate(INVALID_SYNTAX)
        data = resp.json()
        assert data["valid"] is False
        assert data["message"]
        assert not data["message"].endswith(":")
        assert data["hint"] is not None

    def test_undeclared_gate_names_the_gate(self):
        """An unsupported gate should name the gate and give line info."""
        resp = post_validate(UNDECLARED_GATE)
        data = resp.json()
        assert data["valid"] is False
        assert "foo" in data["message"]
        assert data["line"] == 4
        assert data["snippet"] == "foo q[0];"
