"""Unit tests for the QuEra Aquila surface code resource estimator."""

import math

import pytest

from app.services.quera_estimator import (
    CODE_DISTANCE,
    FACTORY_QUBITS,
    PHYSICAL_QUBITS_PER_LOGICAL,
    ROUTING_OVERHEAD,
    T_GATES_PER_TOFFOLI,
    T_STATES_PER_FACTORY,
    estimate_quera_resources,
)


class TestConstants:
    """Verify surface code constants for QuEra."""

    def test_code_distance(self):
        assert CODE_DISTANCE == 7

    def test_physical_qubits_per_logical(self):
        assert PHYSICAL_QUBITS_PER_LOGICAL == 97  # 2*7^2 - 1

    def test_routing_overhead(self):
        assert ROUTING_OVERHEAD == 1.2  # Lower than fixed-grid (1.5)

    def test_factory_qubits(self):
        assert FACTORY_QUBITS == 1078  # 11 * 2 * 49


class TestEstimateQuEraResources:
    """Test the main estimation function."""

    def test_single_qubit_no_t_gates(self):
        result = estimate_quera_resources(n_logical=1, n_t=0, n_toffoli=0)
        expected_data = math.ceil(1 * 97 * 1.2)  # 117
        assert result["data_qubits"] == expected_data
        assert result["distillation_qubits"] == 0
        assert result["physical_qubits"] == expected_data

    def test_two_qubits(self):
        result = estimate_quera_resources(n_logical=2, n_t=0, n_toffoli=0)
        expected_data = math.ceil(2 * 97 * 1.2)  # 233
        assert result["data_qubits"] == expected_data

    def test_with_t_gates(self):
        result = estimate_quera_resources(n_logical=5, n_t=10, n_toffoli=0)
        assert result["num_t_gates"] == 10
        assert result["num_factories"] == 1
        assert result["distillation_qubits"] == 1078

    def test_toffoli_decomposition(self):
        result = estimate_quera_resources(n_logical=3, n_t=0, n_toffoli=5)
        assert result["num_t_gates"] == 35

    def test_total_equals_data_plus_factory(self):
        for n_t in (0, 50, 200):
            result = estimate_quera_resources(n_logical=8, n_t=n_t, n_toffoli=0)
            assert result["physical_qubits"] == (
                result["data_qubits"] + result["distillation_qubits"]
            )

    def test_error_correction_code_name(self):
        result = estimate_quera_resources(n_logical=1, n_t=0, n_toffoli=0)
        assert result["error_correction_code"] == "Rotated Surface Code"

    def test_routing_lower_than_fixed_grid(self):
        """QuEra's routing overhead (1.2) is less than Google/Rigetti (1.5)."""
        result_quera = estimate_quera_resources(n_logical=10, n_t=0, n_toffoli=0)
        from app.services.google_estimator import estimate_google_resources
        result_google = estimate_google_resources(n_logical=10, n_t=0, n_toffoli=0)
        assert result_quera["data_qubits"] < result_google["data_qubits"]

    def test_zero_logical_clamped_to_one(self):
        result = estimate_quera_resources(n_logical=0, n_t=0, n_toffoli=0)
        assert result["physical_qubits"] > 0
