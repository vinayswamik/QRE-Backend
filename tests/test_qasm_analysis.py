"""
Tests for POST /api/v1/qasm/analyze

The API returns:
  - circuit_qubits, circuit_gates, circuit_depth  (int)
  - gate_breakdown: list of { name, value, percentage, gates[] }
  - vendors: dict[str, VendorEstimateResult]

Each vendor result has:
  - Always: status, processor, technology, year (nullable), source
  - success: qec_scheme, runtime, physical_qubits, total_logical_gates,
    logical_error_rate
  - not_available: reason
  - above_threshold / error: qec_scheme, detail

Test categories:
  1. Response shape and HTTP status
  2. Gate breakdown (circuit metadata + pie chart data)
  3. Vendor coverage (available vs unavailable)
  4. Success vendor field validation
  5. Unavailable vendor field validation
  6. Above-threshold / error vendor handling
  7. Parameterized circuit corpus (algorithms, gate types, scales, QASM versions)
  8. Request validation edge cases
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import AVAILABLE_VENDORS, UNAVAILABLE_VENDORS

client = TestClient(app)
ENDPOINT = "/api/v1/qasm/analyze"

VALID_STATUSES = {"success", "not_available", "above_threshold", "error"}


def post_analyze(code: str):
    """Send a QASM circuit to the analyze endpoint and return the response."""
    return client.post(ENDPOINT, json={"code": code})


# ---------------------------------------------------------------------------
# Circuit corpus — (id, code)
# ---------------------------------------------------------------------------

CIRCUITS = [
    (
        "bell_state_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2]; creg c[2];
h q[0]; cx q[0],q[1];
measure q -> c;
""",
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
    ),
    (
        "toffoli_3q_v2",
        """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[3]; creg c[3];
x q[0]; x q[1];
ccx q[0],q[1],q[2];
measure q -> c;
""",
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
    ),
    (
        "bell_state_v3",
        """\
OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q; bit[2] c;
h q[0]; cx q[0],q[1];
c = measure q;
""",
    ),
    (
        "ghz_8q_v3",
        """\
OPENQASM 3.0;
include "stdgates.inc";
qubit[8] q; bit[8] c;
h q[0];
cx q[0],q[1]; cx q[1],q[2]; cx q[2],q[3];
cx q[3],q[4]; cx q[4],q[5]; cx q[5],q[6]; cx q[6],q[7];
c = measure q;
""",
    ),
    (
        "toffoli_3q_v3",
        """\
OPENQASM 3.0;
include "stdgates.inc";
qubit[3] q; bit[3] c;
x q[0]; x q[1];
ccx q[0],q[1],q[2];
c = measure q;
""",
    ),
]


# ---------------------------------------------------------------------------
# 1. Response shape
# ---------------------------------------------------------------------------


EXPECTED_TOP_LEVEL_KEYS = {
    "circuit_qubits",
    "circuit_gates",
    "circuit_depth",
    "gate_breakdown",
    "vendors",
}
GATE_CATEGORIES = {"1Q", "2Q", "Toffoli"}


class TestResponseShape:
    """Verify the top-level structure of analyze responses."""

    def test_returns_200_with_vendors_dict(self):
        """Analyze should return HTTP 200 with a non-empty vendors dict."""
        resp = post_analyze(CIRCUITS[0][1])  # bell state
        assert resp.status_code == 200
        data = resp.json()
        assert "vendors" in data
        assert isinstance(data["vendors"], dict)
        assert len(data["vendors"]) > 0

    def test_response_has_expected_top_level_keys(self):
        """Response JSON should contain exactly the expected top-level keys."""
        data = post_analyze(CIRCUITS[0][1]).json()
        assert set(data.keys()) == EXPECTED_TOP_LEVEL_KEYS

    def test_circuit_metadata_fields_are_positive_ints(self):
        """circuit_qubits, circuit_gates, circuit_depth must be positive integers."""
        data = post_analyze(CIRCUITS[0][1]).json()
        for field in ("circuit_qubits", "circuit_gates", "circuit_depth"):
            assert isinstance(data[field], int), f"{field} must be int"
            assert data[field] > 0, f"{field} must be > 0"


# ---------------------------------------------------------------------------
# 2. Gate breakdown (circuit metadata + pie chart data)
# ---------------------------------------------------------------------------


class TestGateBreakdown:
    """Validate the gate_breakdown field used for the frontend pie chart."""

    def test_gate_breakdown_has_three_categories(self):
        """gate_breakdown must contain exactly the 1Q, 2Q, and Toffoli categories."""
        data = post_analyze(CIRCUITS[0][1]).json()
        names = {entry["name"] for entry in data["gate_breakdown"]}
        assert names == GATE_CATEGORIES

    def test_gate_breakdown_category_fields(self):
        """Each category must have name, value (int), percentage (float), and gates list."""
        data = post_analyze(CIRCUITS[0][1]).json()
        for cat in data["gate_breakdown"]:
            assert cat["name"] in GATE_CATEGORIES
            assert isinstance(cat["value"], int)
            assert isinstance(cat["percentage"], float)
            assert isinstance(cat["gates"], list)

    def test_gate_breakdown_percentages_sum_to_100(self):
        """Category percentages must sum to 100 (within floating-point tolerance)."""
        data = post_analyze(CIRCUITS[0][1]).json()
        total = sum(cat["percentage"] for cat in data["gate_breakdown"])
        assert abs(total - 100.0) < 0.1, f"Percentages sum to {total}, expected ~100"

    def test_gate_detail_fields(self):
        """Individual gate entries must have name (str), count (int), percentage (float)."""
        data = post_analyze(CIRCUITS[0][1]).json()
        for cat in data["gate_breakdown"]:
            for gate in cat["gates"]:
                assert isinstance(gate["name"], str) and gate["name"]
                assert isinstance(gate["count"], int) and gate["count"] > 0
                assert isinstance(gate["percentage"], float) and gate["percentage"] > 0

    def test_bell_state_has_h_and_cx(self):
        """Bell state contains H (1Q) and CX (2Q) gates — both must appear in breakdown."""
        data = post_analyze(CIRCUITS[0][1]).json()
        cat_map = {cat["name"]: cat for cat in data["gate_breakdown"]}
        gate_names_1q = {g["name"] for g in cat_map["1Q"]["gates"]}
        gate_names_2q = {g["name"] for g in cat_map["2Q"]["gates"]}
        assert "h" in gate_names_1q, "H gate missing from 1Q category"
        assert "cx" in gate_names_2q, "CX gate missing from 2Q category"

    def test_toffoli_circuit_has_toffoli_category(self):
        """Toffoli (ccx) circuit must report gates in the Toffoli category."""
        toffoli_code = next(c for name, c in CIRCUITS if name == "toffoli_3q_v2")
        data = post_analyze(toffoli_code).json()
        cat_map = {cat["name"]: cat for cat in data["gate_breakdown"]}
        assert cat_map["Toffoli"]["value"] > 0, "Expected Toffoli gates in breakdown"

    def test_single_qubit_circuit_has_no_2q_or_toffoli(self):
        """Single-qubit circuit should have 0 value for 2Q and Toffoli categories."""
        single_code = next(c for name, c in CIRCUITS if name == "single_qubit_v2")
        data = post_analyze(single_code).json()
        cat_map = {cat["name"]: cat for cat in data["gate_breakdown"]}
        assert cat_map["2Q"]["value"] == 0
        assert cat_map["Toffoli"]["value"] == 0

    def test_circuit_gates_equals_sum_of_category_values(self):
        """circuit_gates must equal the sum of all category values in gate_breakdown."""
        data = post_analyze(CIRCUITS[0][1]).json()
        breakdown_total = sum(cat["value"] for cat in data["gate_breakdown"])
        assert data["circuit_gates"] == breakdown_total

    def test_circuit_qubits_matches_register_size(self):
        """Bell state has 2 qubits — circuit_qubits must be 2."""
        data = post_analyze(CIRCUITS[0][1]).json()
        assert data["circuit_qubits"] == 2

    def test_larger_circuit_has_more_gates(self):
        """GHZ 5q circuit should have more gates than the Bell state circuit."""
        bell_data = post_analyze(CIRCUITS[0][1]).json()
        ghz_data = post_analyze(CIRCUITS[1][1]).json()  # ghz_5q_v2
        assert ghz_data["circuit_gates"] > bell_data["circuit_gates"]

    @pytest.mark.parametrize(
        "circuit_id,code",
        CIRCUITS,
        ids=[c[0] for c in CIRCUITS],
    )
    def test_gate_breakdown_present_for_all_circuits(self, circuit_id, code):
        """gate_breakdown with 3 categories must be returned for every circuit."""
        data = post_analyze(code).json()
        assert "gate_breakdown" in data, f"{circuit_id}: gate_breakdown missing"
        names = {cat["name"] for cat in data["gate_breakdown"]}
        assert names == GATE_CATEGORIES, f"{circuit_id}: unexpected categories {names}"

    @pytest.mark.parametrize(
        "circuit_id,code",
        CIRCUITS,
        ids=[c[0] for c in CIRCUITS],
    )
    def test_circuit_metadata_positive_for_all_circuits(self, circuit_id, code):
        """circuit_qubits, circuit_gates, circuit_depth must be > 0 for every circuit."""
        data = post_analyze(code).json()
        assert data["circuit_qubits"] > 0, f"{circuit_id}: circuit_qubits not > 0"
        assert data["circuit_gates"] > 0, f"{circuit_id}: circuit_gates not > 0"
        assert data["circuit_depth"] > 0, f"{circuit_id}: circuit_depth not > 0"


# ---------------------------------------------------------------------------
# 3. Vendor coverage
# ---------------------------------------------------------------------------


class TestVendorCoverage:
    """Ensure available vendors appear and unavailable ones are excluded."""

    def test_all_available_vendors_present(self):
        """Every vendor marked available in vendors.json should appear."""
        data = post_analyze(CIRCUITS[0][1]).json()
        vendor_names = set(data["vendors"].keys())
        # All available vendors should appear (not_available vendors are excluded
        # from estimate() since they are filtered by available=True,
        # BUT the estimator only returns active vendors)
        # The unavailable ones won't appear in the response
        for name in AVAILABLE_VENDORS:
            assert name in vendor_names, f"Expected vendor '{name}' in response"

    def test_unavailable_vendors_excluded(self):
        """Vendors marked unavailable should not appear in results."""
        data = post_analyze(CIRCUITS[0][1]).json()
        vendor_names = set(data["vendors"].keys())
        for name in UNAVAILABLE_VENDORS:
            assert (
                name not in vendor_names
            ), f"Unavailable vendor '{name}' should not appear"

    def test_each_vendor_has_base_fields(self):
        """Every vendor result must include status, processor, technology, source, year."""
        data = post_analyze(CIRCUITS[0][1]).json()
        for name, v in data["vendors"].items():
            assert (
                v["status"] in VALID_STATUSES
            ), f"{name}: invalid status '{v['status']}'"
            assert isinstance(v["processor"], str) and v["processor"]
            assert isinstance(v["technology"], str) and v["technology"]
            assert isinstance(v["source"], str) and v["source"]
            # year can be null for some vendors
            assert v["year"] is None or isinstance(v["year"], int)


# ---------------------------------------------------------------------------
# 4. Success vendor field validation
# ---------------------------------------------------------------------------


class TestSuccessVendors:
    """Validate fields returned by vendors with status='success'."""

    def test_at_least_one_vendor_succeeds_for_bell_state(self):
        """A simple Bell state circuit should succeed on at least one vendor."""
        data = post_analyze(CIRCUITS[0][1]).json()
        successes = {
            k: v for k, v in data["vendors"].items() if v["status"] == "success"
        }
        assert len(successes) > 0, "At least one vendor should succeed for a Bell state"

    def test_success_vendors_have_estimation_fields(self):
        """Successful vendors must include qec_scheme, runtime, qubits, gates, error rate."""
        data = post_analyze(CIRCUITS[0][1]).json()
        for name, v in data["vendors"].items():
            if v["status"] != "success":
                continue
            assert (
                isinstance(v["qec_scheme"], str) and v["qec_scheme"]
            ), f"{name}: missing qec_scheme"
            assert (
                isinstance(v["runtime"], str) and v["runtime"]
            ), f"{name}: missing runtime"
            assert (
                isinstance(v["physical_qubits"], int) and v["physical_qubits"] > 0
            ), f"{name}: bad physical_qubits"
            assert (
                isinstance(v["total_logical_gates"], int)
                and v["total_logical_gates"] >= 0
            ), f"{name}: bad total_logical_gates"
            assert isinstance(
                v["logical_error_rate"], float
            ), f"{name}: bad logical_error_rate"

    def test_physical_qubits_positive_for_successes(self):
        """physical_qubits must be > 0 for every successful vendor."""
        data = post_analyze(CIRCUITS[0][1]).json()
        for name, v in data["vendors"].items():
            if v["status"] == "success":
                assert v["physical_qubits"] > 0, f"{name}: physical_qubits must be > 0"

    def test_logical_error_rate_is_small(self):
        """Logical error rate should be between 0 and 1 for successful vendors."""
        data = post_analyze(CIRCUITS[0][1]).json()
        for name, v in data["vendors"].items():
            if v["status"] == "success":
                # With error_budget=0.01, logical error rate should be small
                assert (
                    0 < v["logical_error_rate"] < 1.0
                ), f"{name}: logical_error_rate out of range"

    def test_runtime_is_human_readable_string(self):
        """Runtime should be a non-empty human-readable string."""
        data = post_analyze(CIRCUITS[0][1]).json()
        for name, v in data["vendors"].items():
            if v["status"] == "success":
                # Azure QRE returns strings like "1 us", "3 ms", "2 secs", etc.
                assert len(v["runtime"]) > 0, f"{name}: runtime should be non-empty"


# ---------------------------------------------------------------------------
# 5. Unavailable / above_threshold / error vendors
# ---------------------------------------------------------------------------


class TestNonSuccessVendors:
    """Validate fields for above_threshold, error, and not_available vendors."""

    def test_above_threshold_has_detail(self):
        """Vendors with above_threshold status must include a detail string."""
        data = post_analyze(CIRCUITS[0][1]).json()
        for name, v in data["vendors"].items():
            if v["status"] == "above_threshold":
                assert (
                    v["detail"] is not None
                ), f"{name}: above_threshold must have detail"
                assert "THRESHOLD" in v["detail"].upper()

    def test_error_status_has_detail(self):
        """Vendors with error status must include a detail string."""
        data = post_analyze(CIRCUITS[0][1]).json()
        for name, v in data["vendors"].items():
            if v["status"] == "error":
                assert v["detail"] is not None, f"{name}: error must have detail"

    def test_non_success_vendors_have_null_estimation_fields(self):
        """Not-available vendors should have null estimation fields."""
        data = post_analyze(CIRCUITS[0][1]).json()
        for v in data["vendors"].values():
            # These fields should be null for non-success statuses
            if v["status"] == "not_available":
                assert v["physical_qubits"] is None
                assert v["runtime"] is None


# ---------------------------------------------------------------------------
# 6. Parameterized circuit corpus — every circuit gets valid vendor results
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "circuit_id,code",
    CIRCUITS,
    ids=[c[0] for c in CIRCUITS],
)
class TestCircuitCorpus:
    """Run every circuit in the corpus through the analyze endpoint."""

    def test_returns_200(self, circuit_id, code):
        """Every circuit should return HTTP 200."""
        resp = post_analyze(code)
        assert resp.status_code == 200, f"{circuit_id}: got {resp.status_code}"

    def test_vendors_dict_non_empty(self, circuit_id, code):
        """Vendors dict must not be empty for any valid circuit."""
        data = post_analyze(code).json()
        assert len(data["vendors"]) > 0, f"{circuit_id}: no vendors returned"

    def test_all_statuses_are_valid(self, circuit_id, code):
        """Every vendor status must be one of the known status values."""
        data = post_analyze(code).json()
        for name, v in data["vendors"].items():
            assert v["status"] in VALID_STATUSES, f"{circuit_id}/{name}: bad status"

    def test_at_least_one_success_or_above_threshold(self, circuit_id, code):
        """At least one vendor should succeed or report above_threshold."""
        data = post_analyze(code).json()
        statuses = {v["status"] for v in data["vendors"].values()}
        assert statuses & {"success", "above_threshold"}, (
            f"{circuit_id}: expected at least one success or "
            f"above_threshold, got {statuses}"
        )

    def test_success_fields_present_when_success(self, circuit_id, code):
        """Successful vendors must have all estimation fields populated."""
        data = post_analyze(code).json()
        for v in data["vendors"].values():
            if v["status"] == "success":
                assert (
                    v["physical_qubits"] is not None and v["physical_qubits"] > 0
                ), f"{circuit_id}: physical_qubits missing or zero"
                assert v["runtime"] is not None, f"{circuit_id}: runtime missing"
                assert (
                    v["total_logical_gates"] is not None
                ), f"{circuit_id}: total_logical_gates missing"
                assert (
                    v["logical_error_rate"] is not None
                ), f"{circuit_id}: logical_error_rate missing"
                assert v["qec_scheme"] is not None, f"{circuit_id}: qec_scheme missing"

    def test_vendor_base_fields_always_present(self, circuit_id, code):
        """Processor, technology, and source must be present for all vendors."""
        data = post_analyze(code).json()
        for v in data["vendors"].values():
            assert "processor" in v, f"{circuit_id}: processor missing"
            assert "technology" in v, f"{circuit_id}: technology missing"
            assert "source" in v, f"{circuit_id}: source missing"


# ---------------------------------------------------------------------------
# 7. Cross-vendor consistency checks
# ---------------------------------------------------------------------------


class TestCrossVendorConsistency:
    """Sanity checks comparing results across vendors for the same circuit."""

    def test_all_vendors_get_same_circuit(self):
        """All successful vendors estimating the same circuit should have
        physical_qubits > 0, but different vendors may return different values."""
        data = post_analyze(CIRCUITS[0][1]).json()
        successes = [v for v in data["vendors"].values() if v["status"] == "success"]
        if len(successes) < 2:
            pytest.skip("Need at least 2 successful vendors for cross-vendor check")
        qubits = [v["physical_qubits"] for v in successes]
        # All should be positive
        assert all(q > 0 for q in qubits)
        # Different vendors typically give different physical qubit counts
        # (just check they're all valid, not necessarily different)

    def test_larger_circuit_needs_more_or_equal_qubits(self):
        """A 10-qubit CNOT ladder should generally need >= physical qubits
        compared to a 2-qubit Bell state for the same vendor."""
        bell_data = post_analyze(CIRCUITS[0][1]).json()  # bell_state_v2
        ladder_data = post_analyze(CIRCUITS[11][1]).json()  # cnot_ladder_10q_v2

        for name in AVAILABLE_VENDORS:
            bell_v = bell_data["vendors"].get(name, {})
            ladder_v = ladder_data["vendors"].get(name, {})
            if (
                bell_v.get("status") == "success"
                and ladder_v.get("status") == "success"
            ):
                assert ladder_v["physical_qubits"] >= bell_v["physical_qubits"], (
                    f"{name}: 10q ladder ({ladder_v['physical_qubits']}) should need "
                    f">= qubits than bell ({bell_v['physical_qubits']})"
                )


# ---------------------------------------------------------------------------
# 8. Request validation
# ---------------------------------------------------------------------------


class TestAnalyzeRequestValidation:
    """Edge cases for analyze request validation (empty body, missing field)."""

    def test_empty_code_returns_422(self):
        """Empty code string should be rejected by Pydantic min_length=1."""
        resp = client.post(ENDPOINT, json={"code": ""})
        assert resp.status_code == 422

    def test_missing_code_returns_422(self):
        """Missing code field in JSON body should return 422."""
        resp = client.post(ENDPOINT, json={})
        assert resp.status_code == 422

    def test_no_body_returns_422(self):
        """Request with no body at all should return 422."""
        resp = client.post(ENDPOINT)
        assert resp.status_code == 422

    def test_code_exceeding_max_length_returns_422(self):
        """Code strings longer than 100,000 chars should be rejected."""
        resp = client.post(ENDPOINT, json={"code": "x" * 100_001})
        assert resp.status_code == 422
