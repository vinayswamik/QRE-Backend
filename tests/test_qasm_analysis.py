"""
Tests for POST /api/v1/qasm/analyze

Covers the full range of circuits used in the manual integration test:
  - Standard quantum algorithms (Bell, GHZ, QFT, Grover, BV, QPE, …)
  - Gate-type specific circuits (1Q-only, 2Q-only, Toffoli-only, T-heavy)
  - QASM 2.0 and QASM 3.0 dialects
  - Edge cases (single qubit, 20-qubit wide, deep circuit)

Each parameterized case asserts:
  1. HTTP 200 and well-formed response shape
  2. Correct qubit count
  3. Gate categories are exactly {"1Q", "2Q", "Toffoli"}
  4. Category gate counts sum to total_gates
  5. All percentages are in [0, 100] and sum to ~100%
  6. Circuit-specific gate-type expectations (1Q/2Q/Toffoli non-zero or zero)
  7. Vendor list is non-empty with valid physical resource fields
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ENDPOINT = "/api/v1/qasm/analyze"


def post_analyze(code: str) -> dict:
    response = client.post(ENDPOINT, json={"code": code})
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    return response.json()


# ---------------------------------------------------------------------------
# Circuit corpus
# ---------------------------------------------------------------------------

CIRCUITS = [
    # (id, code, expected_qubits, has_1q, has_2q, has_toffoli)
    (
        "bell_state_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2]; creg c[2];
h q[0]; cx q[0],q[1];
measure q -> c;
""",
        2, True, True, False,
    ),
    (
        "ghz_5q_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[5]; creg c[5];
h q[0]; cx q[0],q[1]; cx q[1],q[2]; cx q[2],q[3]; cx q[3],q[4];
measure q -> c;
""",
        5, True, True, False,
    ),
    (
        "qft_4q_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[4]; creg c[4];
h q[0]; cp(pi/2) q[1],q[0]; cp(pi/4) q[2],q[0]; cp(pi/8) q[3],q[0];
h q[1]; cp(pi/2) q[2],q[1]; cp(pi/4) q[3],q[1];
h q[2]; cp(pi/2) q[3],q[2];
h q[3];
swap q[0],q[3]; swap q[1],q[2];
measure q -> c;
""",
        4, True, True, False,
    ),
    (
        "grover_3q_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[3]; creg c[3];
h q[0]; h q[1]; h q[2];
x q[2]; h q[2]; ccx q[0],q[1],q[2]; h q[2]; x q[2];
h q[0]; h q[1]; h q[2];
x q[0]; x q[1]; x q[2];
h q[2]; ccx q[0],q[1],q[2]; h q[2];
x q[0]; x q[1]; x q[2];
h q[0]; h q[1]; h q[2];
measure q -> c;
""",
        3, True, False, True,
    ),
    (
        "bernstein_vazirani_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[5]; creg c[4];
x q[4];
h q[0]; h q[1]; h q[2]; h q[3]; h q[4];
cx q[0],q[4]; cx q[2],q[4]; cx q[3],q[4];
h q[0]; h q[1]; h q[2]; h q[3];
measure q[0]->c[0]; measure q[1]->c[1]; measure q[2]->c[2]; measure q[3]->c[3];
""",
        5, True, True, False,
    ),
    (
        "teleportation_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[3]; creg c[2]; creg d[1];
h q[1]; cx q[1],q[2]; cx q[0],q[1]; h q[0];
measure q[0]->c[0]; measure q[1]->c[1];
if(c==1) z q[2];
if(c==2) x q[2];
if(c==3) y q[2];
measure q[2]->d[0];
""",
        3, True, True, False,
    ),
    (
        "vqe_ry_cnot_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[4]; creg c[4];
ry(0.3) q[0]; ry(0.7) q[1]; ry(1.2) q[2]; ry(0.5) q[3];
cx q[0],q[1]; cx q[1],q[2]; cx q[2],q[3];
ry(0.9) q[0]; ry(0.4) q[1]; ry(1.1) q[2]; ry(0.2) q[3];
measure q -> c;
""",
        4, True, True, False,
    ),
    (
        "qaoa_maxcut_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[3]; creg c[3];
h q[0]; h q[1]; h q[2];
rzz(0.5) q[0],q[1]; rzz(0.5) q[1],q[2]; rzz(0.5) q[0],q[2];
rx(0.7) q[0]; rx(0.7) q[1]; rx(0.7) q[2];
measure q -> c;
""",
        3, True, True, False,
    ),
    (
        "phase_estimation_4q_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[5]; creg c[4];
h q[0]; h q[1]; h q[2]; h q[3]; x q[4];
cp(pi/8) q[3],q[4]; cp(pi/4) q[2],q[4]; cp(pi/2) q[1],q[4]; cp(pi) q[0],q[4];
h q[0];
cp(-pi/2) q[1],q[0]; h q[1];
cp(-pi/4) q[2],q[0]; cp(-pi/2) q[2],q[1]; h q[2];
cp(-pi/8) q[3],q[0]; cp(-pi/4) q[3],q[1]; cp(-pi/2) q[3],q[2]; h q[3];
measure q[0]->c[0]; measure q[1]->c[1]; measure q[2]->c[2]; measure q[3]->c[3];
""",
        5, True, True, False,
    ),
    (
        "swap_test_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[5]; creg c[1];
h q[0];
cswap q[0],q[1],q[3]; cswap q[0],q[2],q[4];
h q[0];
measure q[0]->c[0];
""",
        5, True, True, False,
    ),
    (
        "random_clifford_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[4]; creg c[4];
h q[0]; s q[1]; sdg q[2]; x q[3];
cx q[0],q[1]; cz q[1],q[2]; cy q[2],q[3];
sx q[0]; sxdg q[1]; z q[2]; y q[3];
swap q[0],q[2]; iswap q[1],q[3];
measure q -> c;
""",
        4, True, True, False,
    ),
    (
        "t_gate_ccx_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[3]; creg c[3];
h q[0];
t q[0]; t q[1]; t q[2];
cx q[0],q[1]; tdg q[0]; t q[1]; cx q[2],q[1];
t q[0]; tdg q[1]; t q[2]; cx q[0],q[1];
tdg q[1]; cx q[2],q[1]; cx q[2],q[0]; tdg q[0]; cx q[2],q[0];
measure q -> c;
""",
        3, True, True, False,
    ),
    (
        "toffoli_variants_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[4]; creg c[4];
ccx q[0],q[1],q[2];
ccx q[1],q[2],q[3];
ccnot q[0],q[2],q[3];
measure q -> c;
""",
        4, False, False, True,
    ),
    (
        "quantum_adder_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg a[2]; qreg b[2]; qreg carry[1]; creg c[5];
x a[0]; x b[0];
ccx a[0],b[0],carry[0];
cx a[0],b[0];
ccx a[1],b[1],carry[0];
cx a[1],b[1];
cx a[0],b[0];
measure a[0]->c[0]; measure a[1]->c[1];
measure b[0]->c[2]; measure b[1]->c[3];
measure carry[0]->c[4];
""",
        5, True, True, True,
    ),
    (
        "deutsch_jozsa_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[4]; creg c[3];
x q[3];
h q[0]; h q[1]; h q[2]; h q[3];
cx q[0],q[3]; cx q[1],q[3]; cx q[2],q[3];
h q[0]; h q[1]; h q[2];
measure q[0]->c[0]; measure q[1]->c[1]; measure q[2]->c[2];
""",
        4, True, True, False,
    ),
    (
        "simons_algorithm_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[6]; creg c[3];
h q[0]; h q[1]; h q[2];
cx q[0],q[3]; cx q[1],q[4]; cx q[2],q[5];
cx q[0],q[4];
h q[0]; h q[1]; h q[2];
measure q[0]->c[0]; measure q[1]->c[1]; measure q[2]->c[2];
""",
        6, True, True, False,
    ),
    (
        "cnot_ladder_10q_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[10]; creg c[10];
h q[0];
cx q[0],q[1]; cx q[1],q[2]; cx q[2],q[3]; cx q[3],q[4];
cx q[4],q[5]; cx q[5],q[6]; cx q[6],q[7]; cx q[7],q[8]; cx q[8],q[9];
measure q -> c;
""",
        10, True, True, False,
    ),
    (
        "bell_state_v3",
        """\
OPENQASM 3.0;
qubit[2] q; bit[2] c;
h q[0]; cx q[0],q[1];
c = measure q;
""",
        2, True, True, False,
    ),
    (
        "parameterized_rotations_v3",
        """\
OPENQASM 3.0;
qubit[3] q; bit[3] c;
rx(1.5707963) q[0];
ry(0.7853981) q[1];
rz(3.1415926) q[2];
cx q[0],q[1]; cx q[1],q[2];
c = measure q;
""",
        3, True, True, False,
    ),
    (
        "ghz_8q_v3",
        """\
OPENQASM 3.0;
qubit[8] q; bit[8] c;
h q[0];
cx q[0],q[1]; cx q[1],q[2]; cx q[2],q[3];
cx q[3],q[4]; cx q[4],q[5]; cx q[5],q[6]; cx q[6],q[7];
c = measure q;
""",
        8, True, True, False,
    ),
    (
        "toffoli_3q_v3",
        """\
OPENQASM 3.0;
qubit[3] q; bit[3] c;
x q[0]; x q[1];
ccx q[0],q[1],q[2];
c = measure q;
""",
        3, True, False, True,
    ),
    (
        "vqe_hardware_efficient_v3",
        """\
OPENQASM 3.0;
qubit[4] q; bit[4] c;
ry(0.1) q[0]; ry(0.2) q[1]; ry(0.3) q[2]; ry(0.4) q[3];
rz(0.5) q[0]; rz(0.6) q[1]; rz(0.7) q[2]; rz(0.8) q[3];
cx q[0],q[1]; cx q[2],q[3]; cx q[1],q[2];
ry(0.9) q[0]; ry(1.0) q[1]; ry(1.1) q[2]; ry(1.2) q[3];
rz(1.3) q[0]; rz(1.4) q[1]; rz(1.5) q[2]; rz(1.6) q[3];
c = measure q;
""",
        4, True, True, False,
    ),
    (
        "single_qubit_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[1]; creg c[1];
h q[0]; t q[0]; s q[0];
measure q -> c;
""",
        1, True, False, False,
    ),
    (
        "wide_20q_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[20]; creg c[20];
h q[0]; cx q[0],q[19];
measure q -> c;
""",
        20, True, True, False,
    ),
    (
        "deep_1q_only_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[1]; creg c[1];
h q[0]; t q[0]; s q[0]; z q[0]; x q[0]; y q[0];
rx(0.1) q[0]; ry(0.2) q[0]; rz(0.3) q[0];
t q[0]; tdg q[0]; s q[0]; sdg q[0]; h q[0];
measure q -> c;
""",
        1, True, False, False,
    ),
    (
        "only_2q_gates_v2",
        # iswap unrolls into 1Q+2Q primitives, so has_1q=True after unroll
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[4]; creg c[4];
cx q[0],q[1]; cx q[1],q[2]; cx q[2],q[3];
cz q[0],q[2]; swap q[1],q[3]; iswap q[0],q[3];
measure q -> c;
""",
        4, True, True, False,
    ),
    (
        "only_toffoli_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[4]; creg c[4];
ccx q[0],q[1],q[2];
ccx q[1],q[2],q[3];
measure q -> c;
""",
        4, False, False, True,
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_category(breakdown: list[dict], name: str) -> dict | None:
    return next((c for c in breakdown if c["name"] == name), None)


# ---------------------------------------------------------------------------
# Parameterized tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "circuit_id,code,expected_qubits,has_1q,has_2q,has_toffoli",
    CIRCUITS,
    ids=[c[0] for c in CIRCUITS],
)
class TestQasmAnalysis:
    def test_returns_200_and_valid_shape(self, circuit_id, code, expected_qubits, has_1q, has_2q, has_toffoli):
        data = post_analyze(code)
        assert "circuit_qubits" in data
        assert "circuit_gates" in data
        assert "gate_breakdown" in data
        assert "vendors" in data

    def test_qubit_count(self, circuit_id, code, expected_qubits, has_1q, has_2q, has_toffoli):
        data = post_analyze(code)
        assert data["circuit_qubits"] == expected_qubits

    def test_gate_categories_are_correct_set(self, circuit_id, code, expected_qubits, has_1q, has_2q, has_toffoli):
        data = post_analyze(code)
        names = {c["name"] for c in data["gate_breakdown"]}
        assert names == {"1Q", "2Q", "Toffoli"}

    def test_gate_counts_sum_to_total(self, circuit_id, code, expected_qubits, has_1q, has_2q, has_toffoli):
        data = post_analyze(code)
        total = data["circuit_gates"]
        category_sum = sum(c["value"] for c in data["gate_breakdown"])
        assert category_sum == total

    def test_percentages_in_range_and_sum_to_100(self, circuit_id, code, expected_qubits, has_1q, has_2q, has_toffoli):
        data = post_analyze(code)
        for cat in data["gate_breakdown"]:
            assert 0.0 <= cat["percentage"] <= 100.0
            for gate in cat["gates"]:
                assert 0.0 <= gate["percentage"] <= 100.0
        total_pct = sum(c["percentage"] for c in data["gate_breakdown"])
        assert abs(total_pct - 100.0) < 0.1

    def test_1q_category_presence(self, circuit_id, code, expected_qubits, has_1q, has_2q, has_toffoli):
        data = post_analyze(code)
        cat = get_category(data["gate_breakdown"], "1Q")
        if has_1q:
            assert cat["value"] > 0, "Expected 1Q gates but found none"
        else:
            assert cat["value"] == 0, "Expected no 1Q gates but found some"

    def test_2q_category_presence(self, circuit_id, code, expected_qubits, has_1q, has_2q, has_toffoli):
        data = post_analyze(code)
        cat = get_category(data["gate_breakdown"], "2Q")
        if has_2q:
            assert cat["value"] > 0, "Expected 2Q gates but found none"
        else:
            assert cat["value"] == 0, "Expected no 2Q gates but found some"

    def test_toffoli_category_presence(self, circuit_id, code, expected_qubits, has_1q, has_2q, has_toffoli):
        data = post_analyze(code)
        cat = get_category(data["gate_breakdown"], "Toffoli")
        if has_toffoli:
            assert cat["value"] > 0, "Expected Toffoli gates but found none"
        else:
            assert cat["value"] == 0, "Expected no Toffoli gates but found some"

    def test_vendors_non_empty_with_valid_fields(self, circuit_id, code, expected_qubits, has_1q, has_2q, has_toffoli):
        data = post_analyze(code)
        assert len(data["vendors"]) > 0
        for v in data["vendors"]:
            assert v["physical_qubits"] > 0
            assert v["physical_gates"] > 0
            assert 0.0 <= v["success_probability"] <= 100.0
            assert v["runtime_seconds"] >= 0.0
