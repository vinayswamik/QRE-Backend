"""Unit tests for the IonQ Forte Enterprise BB5 code resource estimator."""

import math

import pytest

from app.services.ionq_estimator import (
    CODE_BLOCK_QUBITS,
    CODE_DISTANCE,
    FACTORY_QUBITS,
    LOGICALS_PER_BLOCK,
    PHYSICAL_PER_LOGICAL,
    T_GATES_PER_TOFFOLI,
    T_STATES_PER_FACTORY,
    estimate_ionq_resources,
)


class TestConstants:
    """Verify BB5 [[48,4,7]] constants."""

    def test_code_distance(self):
        assert CODE_DISTANCE == 7

    def test_code_block_qubits(self):
        assert CODE_BLOCK_QUBITS == 48

    def test_logicals_per_block(self):
        assert LOGICALS_PER_BLOCK == 4

    def test_physical_per_logical(self):
        assert PHYSICAL_PER_LOGICAL == 12  # 48 / 4

    def test_factory_qubits(self):
        assert FACTORY_QUBITS == 48  # One code block


class TestEstimateIonQResources:
    """Test the main estimation function."""

    def test_single_qubit_no_t_gates(self):
        result = estimate_ionq_resources(n_logical=1, n_t=0, n_toffoli=0)
        # 1 logical -> ceil(1/4) = 1 block -> 48 data qubits
        assert result["data_qubits"] == 48
        assert result["distillation_qubits"] == 0
        assert result["physical_qubits"] == 48
        assert result["num_factories"] == 0

    def test_four_qubits_one_block(self):
        """4 logicals fit exactly in one code block."""
        result = estimate_ionq_resources(n_logical=4, n_t=0, n_toffoli=0)
        assert result["data_qubits"] == 48

    def test_five_qubits_two_blocks(self):
        """5 logicals require 2 code blocks."""
        result = estimate_ionq_resources(n_logical=5, n_t=0, n_toffoli=0)
        assert result["data_qubits"] == 2 * 48

    def test_with_t_gates(self):
        result = estimate_ionq_resources(n_logical=3, n_t=10, n_toffoli=0)
        assert result["num_t_gates"] == 10
        assert result["num_factories"] == 1
        assert result["distillation_qubits"] == 48

    def test_toffoli_decomposition(self):
        result = estimate_ionq_resources(n_logical=3, n_t=0, n_toffoli=5)
        assert result["num_t_gates"] == 35

    def test_many_t_gates_multiple_factories(self):
        result = estimate_ionq_resources(n_logical=10, n_t=250, n_toffoli=0)
        assert result["num_factories"] == 3
        assert result["distillation_qubits"] == 3 * 48

    def test_total_equals_data_plus_factory(self):
        for n_t in (0, 50, 200):
            result = estimate_ionq_resources(n_logical=8, n_t=n_t, n_toffoli=0)
            assert result["physical_qubits"] == (
                result["data_qubits"] + result["distillation_qubits"]
            )

    def test_error_correction_code_name(self):
        result = estimate_ionq_resources(n_logical=1, n_t=0, n_toffoli=0)
        assert result["error_correction_code"] == "BB5 [[48,4,7]]"

    def test_zero_logical_clamped_to_one(self):
        result = estimate_ionq_resources(n_logical=0, n_t=0, n_toffoli=0)
        assert result["physical_qubits"] > 0
