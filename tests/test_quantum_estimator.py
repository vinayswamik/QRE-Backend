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
            assert isinstance(r["total_logical_gates"], int)
            assert r["total_logical_gates"] >= 0
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
