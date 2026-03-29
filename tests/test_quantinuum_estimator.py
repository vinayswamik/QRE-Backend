"""Unit tests for the Quantinuum Helios color code resource estimator."""

import math

import pytest

from app.services.quantinuum_estimator import (
    CODE_DISTANCE,
    DATA_QUBITS_PER_LOGICAL,
    FACTORY_QUBITS,
    PHYSICAL_PER_LOGICAL,
    T_GATES_PER_TOFFOLI,
    T_STATES_PER_FACTORY,
    estimate_quantinuum_resources,
)


class TestConstants:
    """Verify Color Code [[7,1,3]] constants."""

    def test_code_distance(self):
        assert CODE_DISTANCE == 3

    def test_data_qubits_per_logical(self):
        assert DATA_QUBITS_PER_LOGICAL == 7

    def test_physical_per_logical(self):
        assert PHYSICAL_PER_LOGICAL == 11  # 7 data + 4 ancilla

    def test_factory_qubits(self):
        assert FACTORY_QUBITS == 28  # 15 + 7 + 6


class TestEstimateQuantinuumResources:
    """Test the main estimation function."""

    def test_single_qubit_no_t_gates(self):
        result = estimate_quantinuum_resources(n_logical=1, n_t=0, n_toffoli=0)
        assert result["data_qubits"] == 11
        assert result["distillation_qubits"] == 0
        assert result["physical_qubits"] == 11
        assert result["num_factories"] == 0

    def test_two_qubits(self):
        result = estimate_quantinuum_resources(n_logical=2, n_t=0, n_toffoli=0)
        assert result["data_qubits"] == 22

    def test_with_t_gates(self):
        result = estimate_quantinuum_resources(n_logical=5, n_t=10, n_toffoli=0)
        assert result["num_t_gates"] == 10
        assert result["num_factories"] == 1
        assert result["distillation_qubits"] == 28

    def test_toffoli_decomposition(self):
        result = estimate_quantinuum_resources(n_logical=3, n_t=0, n_toffoli=5)
        assert result["num_t_gates"] == 35

    def test_many_t_gates_multiple_factories(self):
        result = estimate_quantinuum_resources(n_logical=10, n_t=250, n_toffoli=0)
        assert result["num_factories"] == 3
        assert result["distillation_qubits"] == 3 * 28

    def test_total_equals_data_plus_factory(self):
        for n_t in (0, 50, 200):
            result = estimate_quantinuum_resources(n_logical=8, n_t=n_t, n_toffoli=0)
            assert result["physical_qubits"] == (
                result["data_qubits"] + result["distillation_qubits"]
            )

    def test_error_correction_code_name(self):
        result = estimate_quantinuum_resources(n_logical=1, n_t=0, n_toffoli=0)
        assert result["error_correction_code"] == "Color Code [[7,1,3]] + Reed-Muller [[15,1,3]]"

    def test_zero_logical_clamped_to_one(self):
        result = estimate_quantinuum_resources(n_logical=0, n_t=0, n_toffoli=0)
        assert result["physical_qubits"] > 0
        assert result["data_qubits"] == 11
