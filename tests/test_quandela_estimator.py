"""Unit tests for the Quandela Belenos Honeycomb Floquet code resource estimator."""

import math

import pytest

from app.services.quandela_estimator import (
    CODE_DISTANCE,
    FACTORY_QUBITS,
    PHYSICAL_QUBITS_PER_LOGICAL,
    ROUTING_OVERHEAD,
    T_GATES_PER_TOFFOLI,
    T_STATES_PER_FACTORY,
    estimate_quandela_resources,
)


class TestConstants:
    """Verify Honeycomb Floquet code constants for Quandela."""

    def test_code_distance(self):
        assert CODE_DISTANCE == 5

    def test_physical_qubits_per_logical(self):
        assert PHYSICAL_QUBITS_PER_LOGICAL == 50  # 2*5^2

    def test_routing_overhead(self):
        assert ROUTING_OVERHEAD == 1.0  # All-to-all photonic

    def test_factory_qubits(self):
        assert FACTORY_QUBITS == 550  # 11 * 50


class TestEstimateQuandelaResources:
    """Test the main estimation function."""

    def test_single_qubit_no_t_gates(self):
        result = estimate_quandela_resources(n_logical=1, n_t=0, n_toffoli=0)
        assert result["data_qubits"] == 50
        assert result["distillation_qubits"] == 0
        assert result["physical_qubits"] == 50

    def test_two_qubits(self):
        result = estimate_quandela_resources(n_logical=2, n_t=0, n_toffoli=0)
        assert result["data_qubits"] == 100

    def test_with_t_gates(self):
        result = estimate_quandela_resources(n_logical=5, n_t=10, n_toffoli=0)
        assert result["num_t_gates"] == 10
        assert result["num_factories"] == 1
        assert result["distillation_qubits"] == 550

    def test_toffoli_decomposition(self):
        result = estimate_quandela_resources(n_logical=3, n_t=0, n_toffoli=5)
        assert result["num_t_gates"] == 35

    def test_many_t_gates_multiple_factories(self):
        result = estimate_quandela_resources(n_logical=10, n_t=250, n_toffoli=0)
        assert result["num_factories"] == 3
        assert result["distillation_qubits"] == 3 * 550

    def test_total_equals_data_plus_factory(self):
        for n_t in (0, 50, 200):
            result = estimate_quandela_resources(n_logical=8, n_t=n_t, n_toffoli=0)
            assert result["physical_qubits"] == (
                result["data_qubits"] + result["distillation_qubits"]
            )

    def test_error_correction_code_name(self):
        result = estimate_quandela_resources(n_logical=1, n_t=0, n_toffoli=0)
        assert result["error_correction_code"] == "Honeycomb Floquet Code"

    def test_zero_logical_clamped_to_one(self):
        result = estimate_quandela_resources(n_logical=0, n_t=0, n_toffoli=0)
        assert result["physical_qubits"] > 0
