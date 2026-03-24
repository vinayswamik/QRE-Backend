"""Unit tests for the Google Willow surface-code resource estimator."""

import math

import pytest

from app.services.google_estimator import (
    CODE_DISTANCE,
    FACTORY_QUBITS,
    PHYSICAL_QUBITS_PER_LOGICAL,
    ROUTING_OVERHEAD,
    T_GATES_PER_TOFFOLI,
    T_STATES_PER_FACTORY,
    estimate_google_resources,
)


class TestConstants:
    """Verify hard-coded constants match surface-code theory for d=7."""

    def test_code_distance(self):
        assert CODE_DISTANCE == 7

    def test_physical_qubits_per_logical(self):
        # Rotated surface code: 2d^2 - 1
        assert PHYSICAL_QUBITS_PER_LOGICAL == 2 * 7**2 - 1  # 97

    def test_factory_qubits(self):
        # 11 tiles * 2 * d^2
        assert FACTORY_QUBITS == 11 * 2 * 7**2  # 1078


class TestEstimateGoogleResources:
    """Test the main estimation function."""

    def test_single_qubit_no_t_gates(self):
        result = estimate_google_resources(n_logical=1, n_t=0, n_toffoli=0)
        expected_data = math.ceil(1 * 97 * ROUTING_OVERHEAD)  # 146
        assert result["physical_qubits"] == expected_data
        assert result["data_qubits"] == expected_data
        assert result["distillation_qubits"] == 0
        assert result["num_factories"] == 0
        assert result["num_t_gates"] == 0
        assert result["code_distance"] == 7

    def test_two_qubits_no_t_gates(self):
        """Bell state: 2 logical qubits, 0 T-gates."""
        result = estimate_google_resources(n_logical=2, n_t=0, n_toffoli=0)
        expected_data = math.ceil(2 * 97 * ROUTING_OVERHEAD)  # 291
        assert result["physical_qubits"] == expected_data
        assert result["distillation_qubits"] == 0
        assert result["num_factories"] == 0

    def test_with_t_gates(self):
        """Circuit with explicit T-gates triggers factory allocation."""
        result = estimate_google_resources(n_logical=5, n_t=10, n_toffoli=0)
        expected_data = math.ceil(5 * 97 * ROUTING_OVERHEAD)
        n_factories = max(1, math.ceil(10 / T_STATES_PER_FACTORY))  # 1
        expected_factory = n_factories * FACTORY_QUBITS
        assert result["data_qubits"] == expected_data
        assert result["distillation_qubits"] == expected_factory
        assert result["physical_qubits"] == expected_data + expected_factory
        assert result["num_t_gates"] == 10
        assert result["num_factories"] == 1

    def test_toffoli_decomposition(self):
        """Toffoli gates contribute 7 T-gates each."""
        result = estimate_google_resources(n_logical=3, n_t=0, n_toffoli=5)
        assert result["num_t_gates"] == 5 * T_GATES_PER_TOFFOLI  # 35
        assert result["num_factories"] == max(1, math.ceil(35 / T_STATES_PER_FACTORY))

    def test_mixed_t_and_toffoli(self):
        result = estimate_google_resources(n_logical=4, n_t=20, n_toffoli=10)
        total_t = 20 + 10 * 7  # 90
        assert result["num_t_gates"] == total_t
        assert result["num_factories"] == max(1, math.ceil(90 / T_STATES_PER_FACTORY))

    def test_many_t_gates_multiple_factories(self):
        """More than 100 T-gates should yield multiple factories."""
        result = estimate_google_resources(n_logical=10, n_t=250, n_toffoli=0)
        assert result["num_t_gates"] == 250
        assert result["num_factories"] == math.ceil(250 / T_STATES_PER_FACTORY)  # 3
        assert result["distillation_qubits"] == 3 * FACTORY_QUBITS

    def test_total_equals_data_plus_factory(self):
        """Total physical qubits = data + distillation."""
        for n_t in (0, 50, 200):
            result = estimate_google_resources(n_logical=8, n_t=n_t, n_toffoli=0)
            assert result["physical_qubits"] == (
                result["data_qubits"] + result["distillation_qubits"]
            )

    def test_logical_error_rate_returned(self):
        result = estimate_google_resources(n_logical=1, n_t=0, n_toffoli=0)
        assert result["logical_error_rate"] == pytest.approx(0.00143, abs=1e-5)

    def test_zero_logical_clamped_to_one(self):
        """n_logical=0 should be clamped to 1."""
        result = estimate_google_resources(n_logical=0, n_t=0, n_toffoli=0)
        assert result["physical_qubits"] > 0
        assert result["data_qubits"] == math.ceil(1 * 97 * ROUTING_OVERHEAD)
