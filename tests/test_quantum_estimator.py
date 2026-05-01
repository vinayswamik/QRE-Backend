"""
Unit tests for app.services.quantum_estimator.QuantumEstimator

Tests the estimator class directly (not via the HTTP endpoint):
  1. Initialization and vendor loading
  2. Vendor management (pause/resume)
  3. Preprocessing (gate decomposition)
  4. Estimation output schema for each status type
  5. Caching behaviour
  6. Threshold detection
"""

# pylint: disable=missing-function-docstring

import json
from pathlib import Path

import pytest

from app.services.quantum_estimator import QuantumEstimator
from tests.conftest import (
    BELL_STATE_V2 as BELL_STATE,
    GHZ_5Q_V2 as GHZ_5Q,
    UNAVAILABLE_VENDORS,
)

VENDORS_FILE = Path(__file__).resolve().parent.parent / "app" / "core" / "vendors.json"


# ---------------------------------------------------------------------------
# 1. Initialization
# ---------------------------------------------------------------------------


class TestInit:
    """Verify estimator initialization and vendor loading."""

    def test_loads_vendors_from_file(self):
        """Estimator should load at least one vendor from the default file."""
        est = QuantumEstimator()
        assert len(est.vendors) > 0

    def test_vendors_match_json_file(self):
        """Loaded vendor keys should match the JSON file exactly."""
        with VENDORS_FILE.open() as f:
            expected = json.load(f)
        est = QuantumEstimator()
        assert set(est.vendors.keys()) == set(expected.keys())

    def test_params_cache_built_for_available_below_threshold(self):
        """Params cache should be populated for available below-threshold vendors."""
        est = QuantumEstimator()
        # params_cache should have entries for available vendors
        # that are below threshold
        assert len(est._params_cache) > 0  # pylint: disable=protected-access

    def test_custom_vendors_file(self, tmp_path):
        """Estimator should accept a custom vendors JSON file path."""
        custom = tmp_path / "custom.json"
        custom.write_text(
            json.dumps(
                {
                    "TestVendor": {
                        "processor": "Test (1 qubit)",
                        "technology": "Test",
                        "year": 2025,
                        "source": "test",
                        "available": False,
                        "reason": "Just a test",
                    }
                }
            )
        )
        est = QuantumEstimator(vendors_file=custom)
        assert "TestVendor" in est.vendors


# ---------------------------------------------------------------------------
# 2. Vendor management
# ---------------------------------------------------------------------------


class TestVendorManagement:
    """Test pause/resume vendor controls."""

    def test_pause_vendor_excludes_from_results(self):
        """Paused vendor should not appear in estimation results."""
        est = QuantumEstimator()
        est.pause_vendor("Google Willow")
        results = est.estimate(BELL_STATE)
        assert "Google Willow" not in results

    def test_resume_vendor_includes_again(self):
        """Resumed vendor should reappear in estimation results."""
        est = QuantumEstimator()
        est.pause_vendor("Google Willow")
        est.resume_vendor("Google Willow")
        results = est.estimate(BELL_STATE)
        assert "Google Willow" in results

    def test_pause_unknown_vendor_raises(self):
        """Pausing a non-existent vendor should raise KeyError."""
        est = QuantumEstimator()
        with pytest.raises(KeyError, match="Unknown vendor"):
            est.pause_vendor("NonExistent Corp")

    def test_resume_unknown_vendor_raises(self):
        """Resuming a non-existent vendor should raise KeyError."""
        est = QuantumEstimator()
        with pytest.raises(KeyError, match="Unknown vendor"):
            est.resume_vendor("NonExistent Corp")

    def test_unavailable_vendors_not_in_results(self):
        """Vendors marked unavailable in JSON should never appear in results."""
        est = QuantumEstimator()
        results = est.estimate(BELL_STATE)
        for name in UNAVAILABLE_VENDORS:
            assert name not in results


# ---------------------------------------------------------------------------
# 3. Preprocessing / gate decomposition
# ---------------------------------------------------------------------------


class TestPreprocessing:  # pylint: disable=protected-access
    """Test QASM gate decomposition and preprocessing."""

    def test_decompose_swap_to_3_cx(self):
        """SWAP gate should decompose into 3 CNOT gates."""
        result = QuantumEstimator._decompose_gate("swap q[0], q[1];")
        assert result.count("cx") == 3

    def test_decompose_sx_to_rx(self):
        """SX gate should decompose to RX(pi/2)."""
        result = QuantumEstimator._decompose_gate("sx q[0];")
        assert "rx(" in result

    def test_decompose_sxdg_to_rx_negative(self):
        """SXdg gate should decompose to RX(-pi/2)."""
        result = QuantumEstimator._decompose_gate("sxdg q[0];")
        assert "rx(-" in result

    def test_gphase_removed(self):
        """Global phase instructions should be removed."""
        result = QuantumEstimator._decompose_gate("gphase(0.5) q[0];")
        assert result == ""

    def test_nop_removed(self):
        """No-op instructions should be removed."""
        result = QuantumEstimator._decompose_gate("nop q[0];")
        assert result == ""

    def test_regular_gate_unchanged(self):
        """Standard gates like H should pass through unchanged."""
        result = QuantumEstimator._decompose_gate("h q[0];")
        assert result == "h q[0];"

    def test_cx_unchanged(self):
        """CNOT gates should pass through unchanged."""
        result = QuantumEstimator._decompose_gate("cx q[0], q[1];")
        assert result == "cx q[0], q[1];"

    def test_preprocess_returns_valid_qasm(self):
        """Preprocessed output should still contain a valid OPENQASM header."""
        est = QuantumEstimator()
        processed = est._preprocess(BELL_STATE)
        assert "OPENQASM" in processed
        assert len(processed) > 0


# ---------------------------------------------------------------------------
# 4. Estimation output schema
# ---------------------------------------------------------------------------


class TestEstimationOutput:
    """Verify the structure of estimation results for each status type."""

    def test_returns_dict_keyed_by_vendor_name(self):
        """Results should be a non-empty dict with string keys."""
        est = QuantumEstimator()
        results = est.estimate(BELL_STATE)
        assert isinstance(results, dict)
        assert len(results) > 0
        for key in results:
            assert isinstance(key, str)

    def test_only_active_vendors_returned(self):
        """Only vendors with available=True should appear in results."""
        est = QuantumEstimator()
        results = est.estimate(BELL_STATE)
        for name in results:
            vendor_info = est.vendors[name]
            assert vendor_info.get("available", True) is True

    def test_success_result_schema(self):
        """Successful results must have all estimation fields with correct types."""
        est = QuantumEstimator()
        results = est.estimate(BELL_STATE)
        successes = [v for v in results.values() if v["status"] == "success"]
        assert len(successes) > 0, "At least one vendor should succeed for Bell state"
        for r in successes:
            assert r["status"] == "success"
            assert isinstance(r["processor"], str)
            assert isinstance(r["technology"], str)
            assert isinstance(r["source"], str)
            assert isinstance(r["qec_scheme"], str)
            assert isinstance(r["runtime"], str)
            assert isinstance(r["physical_qubits"], int)
            assert r["physical_qubits"] > 0
            assert isinstance(r["logical_error_rate"], float)

    def test_above_threshold_result_schema(self):
        """Above-threshold results must have a detail string mentioning THRESHOLD."""
        est = QuantumEstimator()
        results = est.estimate(BELL_STATE)
        above = [v for v in results.values() if v["status"] == "above_threshold"]
        for r in above:
            assert isinstance(r["detail"], str)
            assert "THRESHOLD" in r["detail"].upper()
            assert isinstance(r["qec_scheme"], str)
            assert isinstance(r["processor"], str)


# ---------------------------------------------------------------------------
# 5. Caching
# ---------------------------------------------------------------------------


class TestCaching:  # pylint: disable=protected-access
    """Verify that estimation and preprocessing results are cached."""

    def test_second_call_uses_cache(self):
        """Repeated estimation should return cached result objects."""
        est = QuantumEstimator()
        results1 = est.estimate(BELL_STATE)
        # Cache should now be populated
        assert len(est._cache) > 0
        results2 = est.estimate(BELL_STATE)
        # Results should be identical (same references from cache)
        for name in results1:
            if results1[name]["status"] == "success":
                assert results1[name] is results2[name]

    def test_preprocess_cache_populated(self):
        """Preprocessing cache should store the QASM string after estimation."""
        est = QuantumEstimator()
        est.estimate(BELL_STATE)
        assert BELL_STATE in est._preprocess_cache

    def test_different_circuits_cached_separately(self):
        """Different circuits should each get their own cache entry."""
        est = QuantumEstimator()
        est.estimate(BELL_STATE)
        est.estimate(GHZ_5Q)
        assert BELL_STATE in est._preprocess_cache
        assert GHZ_5Q in est._preprocess_cache


# ---------------------------------------------------------------------------
# 6. Threshold detection
# ---------------------------------------------------------------------------


class TestThresholdDetection:  # pylint: disable=protected-access
    """Test QEC threshold checking and cache key generation."""

    def test_is_below_threshold_for_good_vendor(self):
        """Google Willow's error rates should be below the QEC threshold."""
        with VENDORS_FILE.open() as f:
            vendors = json.load(f)
        # Google Willow should be below threshold
        assert QuantumEstimator._is_below_threshold(vendors["Google Willow"]) is True

    def test_is_below_threshold_returns_false_for_bad_rates(self):
        """Vendor with error rates above threshold should be detected."""
        bad_vendor = {
            "qubit_params": {
                "one_qubit_gate_error_rate": 0.5,
                "two_qubit_gate_error_rate": 0.5,
                "one_qubit_measurement_error_rate": 0.5,
                "t_gate_error_rate": 0.5,
                "idle_error_rate": 0.5,
            },
            "qec_scheme": {
                "error_correction_threshold": 0.01,
            },
        }
        assert QuantumEstimator._is_below_threshold(bad_vendor) is False

    def test_cache_key_deterministic(self):
        """Same inputs should always produce the same cache key."""
        vendor_info = {"a": 1, "b": 2}
        qasm = "test"
        k1 = QuantumEstimator._cache_key(vendor_info, qasm)
        k2 = QuantumEstimator._cache_key(vendor_info, qasm)
        assert k1 == k2

    def test_cache_key_differs_for_different_input(self):
        """Different circuit strings should produce different cache keys."""
        vendor_info = {"a": 1}
        k1 = QuantumEstimator._cache_key(vendor_info, "circuit_a")
        k2 = QuantumEstimator._cache_key(vendor_info, "circuit_b")
        assert k1 != k2


# ---------------------------------------------------------------------------
# 7. Vendor parameter overrides
# ---------------------------------------------------------------------------


class TestVendorOverrides:
    # These tests intentionally probe private helpers to verify merge/hash behavior.
    # pylint: disable=protected-access
    """Per-call overrides should merge cleanly without mutating vendors.json."""

    def test_merge_override_does_not_mutate_base(self):
        """_merge_override should deep-copy so the base dict is untouched."""
        base = {
            "qubit_params": {"one_qubit_gate_error_rate": 1e-4},
            "qec_scheme": {"error_correction_threshold": 0.01},
            "max_code_distance": 50,
        }
        override = {"qubit_params": {"one_qubit_gate_error_rate": 5e-4}}
        merged = QuantumEstimator._merge_override(base, override)
        assert merged["qubit_params"]["one_qubit_gate_error_rate"] == 5e-4
        assert base["qubit_params"]["one_qubit_gate_error_rate"] == 1e-4

    def test_merge_override_updates_max_code_distance(self):
        """max_code_distance override should propagate to the merged dict."""
        base = {
            "qubit_params": {},
            "qec_scheme": {},
            "max_code_distance": 50,
        }
        merged = QuantumEstimator._merge_override(base, {"max_code_distance": 25})
        assert merged["max_code_distance"] == 25
        assert base["max_code_distance"] == 50

    def test_override_produces_different_cache_key(self):
        """Overridden vendor info must hash to a different cache key than the default."""
        est = QuantumEstimator()
        vendor_name = "Google Willow"
        default_info = est.vendors[vendor_name]
        overridden = QuantumEstimator._merge_override(
            default_info,
            {"qubit_params": {"two_qubit_gate_error_rate": 1e-3}},
        )
        k_default = QuantumEstimator._cache_key(default_info, BELL_STATE)
        k_override = QuantumEstimator._cache_key(overridden, BELL_STATE)
        assert k_default != k_override

    def test_estimate_accepts_overrides_and_respects_threshold(self):
        """Pushing a vendor's error rate above threshold via override must flip its status."""
        est = QuantumEstimator()
        bad = {"qubit_params": {"two_qubit_gate_error_rate": 0.99}}
        results = est.estimate(BELL_STATE, overrides={"Google Willow": bad})
        g = results["Google Willow"]
        assert g["status"] == "above_threshold"
        # Other vendors should still run normally
        other_statuses = {
            r["status"] for k, r in results.items() if k != "Google Willow"
        }
        assert "success" in other_statuses or "error" in other_statuses

    def test_estimate_runtime_seconds_field_present(self):
        """runtime_seconds should be a positive float on successful runs."""
        est = QuantumEstimator()
        results = est.estimate(BELL_STATE)
        success = [r for r in results.values() if r["status"] == "success"]
        assert success, "expected at least one successful vendor for bell state"
        for r in success:
            assert isinstance(r["runtime_seconds"], float)
            assert r["runtime_seconds"] > 0


# ---------------------------------------------------------------------------
# 8. Enriched Q# estimate fields
# ---------------------------------------------------------------------------


_T_CIRCUIT = """OPENQASM 3.0;
include "stdgates.inc";
qubit[3] q;
bit[3] c;
h q[0];
cx q[0], q[1];
t q[2];
ccx q[0], q[1], q[2];
c[0] = measure q[0];
c[1] = measure q[1];
c[2] = measure q[2];
"""


class TestEnrichedEstimateFields:
    """The Q# raw result contains many vendor-differentiating fields beyond
    the original four. _parse_raw_result should surface them all.
    """

    _REQUIRED_ENRICHED_FIELDS = (
        "rqops",
        "clock_frequency",
        "code_distance",
        "physical_qubits_for_algorithm",
        "physical_qubits_for_tfactories",
        "algorithmic_logical_qubits",
        "algorithmic_logical_depth",
        "logical_depth",
        "num_tstates",
        "num_tfactories",
        "num_tfactory_runs",
        "required_logical_qubit_error_rate",
        "required_logical_tstate_error_rate",
        "clifford_error_rate",
        "logical_cycle_time_ns",
        "tfactory_physical_qubits",
        "tfactory_runtime_seconds",
        "tfactory_num_rounds",
        "formatted",
    )

    def test_all_enriched_fields_present_on_success(self):
        est = QuantumEstimator()
        results = est.estimate(_T_CIRCUIT)
        success = [r for r in results.values() if r["status"] == "success"]
        assert success, "expected at least one vendor to succeed on T-circuit"
        for r in success:
            for field in self._REQUIRED_ENRICHED_FIELDS:
                assert field in r, f"{field} missing from success result"

    def test_code_distance_differs_across_vendors(self):
        est = QuantumEstimator()
        results = est.estimate(_T_CIRCUIT)
        distances = {
            name: r["code_distance"]
            for name, r in results.items()
            if r["status"] == "success"
        }
        assert len(distances) >= 2
        assert len(set(distances.values())) > 1, (
            "expected code_distance to vary across vendors, " f"got {distances}"
        )

    def test_qubit_budget_split_adds_up(self):
        est = QuantumEstimator()
        results = est.estimate(_T_CIRCUIT)
        for r in results.values():
            if r["status"] != "success":
                continue
            assert (
                r["physical_qubits_for_algorithm"] + r["physical_qubits_for_tfactories"]
                == r["physical_qubits"]
            )

    def test_formatted_dict_is_populated(self):
        est = QuantumEstimator()
        results = est.estimate(_T_CIRCUIT)
        for r in results.values():
            if r["status"] != "success":
                continue
            assert isinstance(r["formatted"], dict)
            assert "runtime" in r["formatted"]
            assert "rqops" in r["formatted"]


# ---------------------------------------------------------------------------
# 9. Failure reasons: above_threshold reports the specific failing field
# ---------------------------------------------------------------------------


class TestAboveThresholdReason:
    """When hardware error rates exceed the QEC threshold, the result must
    name the specific offending field so the user knows what to fix.
    """

    def test_above_threshold_includes_failing_field(self):
        est = QuantumEstimator()
        results = est.estimate(
            BELL_STATE,
            overrides={
                "Google Willow": {"qubit_params": {"two_qubit_gate_error_rate": 0.5}}
            },
        )
        r = results["Google Willow"]
        assert r["status"] == "above_threshold"
        assert r["failing_field"] == "two_qubit_gate_error_rate"
        assert r["failing_value"] == 0.5
        assert "two_qubit_gate_error_rate" in r["detail"]
        assert "surface_code" in r["detail"]

    def test_first_failing_field_wins(self):
        """If multiple error rates are over threshold, the first one
        encountered in _ERROR_RATE_KEYS order is reported.
        """
        est = QuantumEstimator()
        results = est.estimate(
            BELL_STATE,
            overrides={
                "Google Willow": {
                    "qubit_params": {
                        "one_qubit_gate_error_rate": 0.5,
                        "two_qubit_gate_error_rate": 0.5,
                    }
                }
            },
        )
        r = results["Google Willow"]
        assert r["failing_field"] == "one_qubit_gate_error_rate"


# ---------------------------------------------------------------------------
# 10. Custom vendors
# ---------------------------------------------------------------------------


def _valid_custom_spec(**overrides):
    spec = {
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
            "one_qubit_gate_error_rate": 1e-4,
            "two_qubit_gate_error_rate": 1e-3,
            "one_qubit_measurement_error_rate": 1e-3,
            "t_gate_time": "10 ns",
            "t_gate_error_rate": 1e-4,
            "idle_error_rate": 1e-5,
        },
        "qec_scheme": {
            "name": "surface_code",
            "crossing_prefactor": 0.03,
            "error_correction_threshold": 0.01,
            "distance_coefficient_power": 0,
            "logical_cycle_time": (
                "(4 * twoQubitGateTime + 2 * oneQubitMeasurementTime) * codeDistance"
            ),
            "physical_qubits_per_logical_qubit": "2 * codeDistance * codeDistance",
        },
        "max_code_distance": 500,
    }
    spec.update(overrides)
    return spec


class TestCustomVendors:
    """Custom vendors flow through the same estimation pipeline as built-ins."""

    def test_custom_vendor_round_trip(self):
        est = QuantumEstimator()
        results = est.estimate(
            _T_CIRCUIT,
            custom_vendors={"MyLab QPU": _valid_custom_spec()},
        )
        assert "MyLab QPU" in results
        r = results["MyLab QPU"]
        assert r["status"] == "success"
        assert r["processor"] == "Lab 9000"
        assert r["code_distance"] > 0

    def test_custom_vendor_name_collision_raises(self):
        est = QuantumEstimator()
        with pytest.raises(ValueError, match="collide"):
            est.estimate(
                BELL_STATE,
                custom_vendors={"Google Willow": _valid_custom_spec()},
            )

    def test_custom_vendor_with_bad_rate_reports_above_threshold(self):
        est = QuantumEstimator()
        bad_spec = _valid_custom_spec()
        bad_spec["qubit_params"]["two_qubit_gate_error_rate"] = 0.5
        results = est.estimate(BELL_STATE, custom_vendors={"BadLab": bad_spec})
        r = results["BadLab"]
        assert r["status"] == "above_threshold"
        assert r["failing_field"] == "two_qubit_gate_error_rate"

    def test_custom_vendor_missing_field_reports_error_with_reason(self):
        est = QuantumEstimator()
        spec = _valid_custom_spec()
        del spec["qubit_params"]["one_qubit_gate_time"]
        results = est.estimate(BELL_STATE, custom_vendors={"Broken": spec})
        r = results["Broken"]
        assert r["status"] == "error"
        assert "one_qubit_gate_time" in r["detail"]

    def test_custom_vendor_out_of_range_error_rate(self):
        est = QuantumEstimator()
        spec = _valid_custom_spec()
        spec["qubit_params"]["one_qubit_gate_error_rate"] = 2.0
        results = est.estimate(BELL_STATE, custom_vendors={"OutOfRange": spec})
        r = results["OutOfRange"]
        assert r["status"] == "error"
        assert "one_qubit_gate_error_rate" in r["detail"]

    def test_custom_vendors_do_not_mutate_self_vendors(self):
        est = QuantumEstimator()
        before = set(est.vendors)
        est.estimate(BELL_STATE, custom_vendors={"Transient": _valid_custom_spec()})
        assert set(est.vendors) == before
