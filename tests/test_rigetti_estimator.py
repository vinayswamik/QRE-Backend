"""Unit tests for the Rigetti Ankaa-3 surface code resource estimator."""

import math

import pytest

from app.services.rigetti_estimator import (
    CODE_DISTANCE,
    FACTORY_QUBITS,
    PHYSICAL_QUBITS_PER_LOGICAL,
    ROUTING_OVERHEAD,
    T_GATES_PER_TOFFOLI,
    T_STATES_PER_FACTORY,
    estimate_rigetti_resources,
)


class TestConstants:
    """Verify surface code constants for Rigetti."""

    def test_code_distance(self):
        assert CODE_DISTANCE == 3

    def test_physical_qubits_per_logical(self):
        assert PHYSICAL_QUBITS_PER_LOGICAL == 17  # 2*3^2 - 1

    def test_factory_qubits(self):
        assert FACTORY_QUBITS == 198  # 11 * 2 * 9


class TestEstimateRigettiResources:
    """Test the main estimation function."""

    def test_single_qubit_no_t_gates(self):
        result = estimate_rigetti_resources(n_logical=1, n_t=0, n_toffoli=0)
        expected_data = math.ceil(1 * 17 * ROUTING_OVERHEAD)  # 26
        assert result["data_qubits"] == expected_data
        assert result["distillation_qubits"] == 0
        assert result["physical_qubits"] == expected_data

    def test_two_qubits(self):
        result = estimate_rigetti_resources(n_logical=2, n_t=0, n_toffoli=0)
        expected_data = math.ceil(2 * 17 * ROUTING_OVERHEAD)  # 51
        assert result["data_qubits"] == expected_data

    def test_with_t_gates(self):
        result = estimate_rigetti_resources(n_logical=5, n_t=10, n_toffoli=0)
        assert result["num_t_gates"] == 10
        assert result["num_factories"] == 1
        assert result["distillation_qubits"] == 198

    def test_toffoli_decomposition(self):
        result = estimate_rigetti_resources(n_logical=3, n_t=0, n_toffoli=5)
        assert result["num_t_gates"] == 35

    def test_total_equals_data_plus_factory(self):
        for n_t in (0, 50, 200):
            result = estimate_rigetti_resources(n_logical=8, n_t=n_t, n_toffoli=0)
            assert result["physical_qubits"] == (
                result["data_qubits"] + result["distillation_qubits"]
            )

    def test_error_correction_code_name(self):
        result = estimate_rigetti_resources(n_logical=1, n_t=0, n_toffoli=0)
        assert result["error_correction_code"] == "Rotated Surface Code"

    def test_logical_error_rate_higher_than_google(self):
        """Rigetti's higher physical error rate means higher logical error."""
        result = estimate_rigetti_resources(n_logical=1, n_t=0, n_toffoli=0)
        assert result["logical_error_rate"] == pytest.approx(7.5e-3, rel=0.1)

    def test_new_breakdown_fields(self):
        """New fields for frontend breakdown modal."""
        result = estimate_rigetti_resources(n_logical=2, n_t=10, n_toffoli=0)
        assert result["physical_qubits_per_logical"] == 17
        assert result["routing_overhead"] == 1.5
        assert result["factory_qubits_each"] == 198
        assert result["t_states_per_factory"] == 100
        assert isinstance(result["references"], list)
        assert len(result["references"]) > 0
        assert all("key" in r and "citation" in r for r in result["references"])

    def test_zero_logical_clamped_to_one(self):
        result = estimate_rigetti_resources(n_logical=0, n_t=0, n_toffoli=0)
        assert result["physical_qubits"] > 0
