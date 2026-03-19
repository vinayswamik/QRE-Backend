"""
Tests for POST /api/v1/qasm/validate

Each test targets a distinct behaviour category:
  1. Syntactically + semantically valid QASM  → valid=True
  2. Syntactically invalid QASM               → valid=False with a parse error
  3. Semantic error (undeclared register)     → valid=False with a semantic error
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ENDPOINT = "/api/v1/qasm/validate"

# ---------------------------------------------------------------------------
# Fixtures / helpers
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

INVALID_SYNTAX = "this is not valid qasm code !!!"

INVALID_SEMANTIC = """\
OPENQASM 2.0;
include "qelib1.inc";
h q[0];
"""


def post_validate(code: str) -> dict:
    """Helper that POSTs to the validate endpoint and returns the JSON body."""
    response = client.post(ENDPOINT, json={"code": code})
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    return response.json()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestQasmValidation:
    def test_valid_qasm_returns_valid_true(self):
        """A well-formed Bell-state circuit must pass validation."""
        data = post_validate(VALID_BELL_STATE)

        assert data["valid"] is True
        assert "valid" in data["message"].lower()
        assert data["error_type"] is None

    def test_syntax_error_returns_valid_false(self):
        """Garbage input must fail with valid=False and a non-empty message."""
        data = post_validate(INVALID_SYNTAX)

        assert data["valid"] is False
        assert data["message"]           # non-empty error description
        assert data["error_type"] is not None

    def test_semantic_error_undeclared_register_returns_valid_false(self):
        """
        A gate applied to a qubit register that was never declared is a
        semantic error; pyqasm should catch it and we must propagate it.
        """
        data = post_validate(INVALID_SEMANTIC)

        assert data["valid"] is False
        assert data["message"]
        assert data["error_type"] is not None
        # pyqasm surfaces this as a ValidationError mentioning the register
        assert "q" in data["message"]
