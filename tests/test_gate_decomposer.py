"""Unit tests for the gate decomposition service."""

from collections import Counter

import pytest

from app.services.gate_decomposer import (
    VENDOR_2Q_COSTS,
    VENDOR_NATIVE_2Q_GATE,
    VIRTUAL_GATES,
    DecompositionResult,
    decompose_for_vendor,
    get_native_2q_gate,
)


class TestConstants:
    """Verify decomposition constants are consistent."""

    def test_all_vendors_have_2q_costs(self):
        expected = {
            "Google", "IBM", "IonQ", "Quantinuum", "Rigetti",
            "Atom Computing", "QuEra", "Quandela",
        }
        assert set(VENDOR_2Q_COSTS.keys()) == expected

    def test_all_vendors_have_native_2q_gate_name(self):
        assert set(VENDOR_NATIVE_2Q_GATE.keys()) == set(VENDOR_2Q_COSTS.keys())

    def test_all_vendors_define_cx(self):
        for vendor, costs in VENDOR_2Q_COSTS.items():
            assert "cx" in costs, f"{vendor} missing cx cost"

    def test_virtual_gates_include_standard_set(self):
        for gate in ("rz", "s", "sdg", "t", "tdg", "z", "id", "gphase"):
            assert gate in VIRTUAL_GATES


class TestDecomposeForVendor:
    """Test decomposition logic for various vendors and gate mixes."""

    def test_virtual_gates_have_zero_cost(self):
        counter = Counter({"rz": 10, "t": 5, "s": 3, "id": 1})
        qubit_map = {"rz": 1, "t": 1, "s": 1, "id": 1}
        result = decompose_for_vendor("Google", counter, qubit_map)
        assert result.native_1q == 0
        assert result.native_2q == 0
        assert result.total == 0

    def test_physical_1q_gates_count_one_each(self):
        counter = Counter({"h": 5, "x": 3, "rx": 2})
        qubit_map = {"h": 1, "x": 1, "rx": 1}
        result = decompose_for_vendor("IBM", counter, qubit_map)
        assert result.native_1q == 10
        assert result.native_2q == 0

    def test_google_cx_costs_2_native_2q(self):
        counter = Counter({"cx": 10})
        qubit_map = {"cx": 2}
        result = decompose_for_vendor("Google", counter, qubit_map)
        assert result.native_2q == 20  # 10 × 2 √iSWAP
        assert result.native_1q == 40  # 10 × 4 extra rotations

    def test_ibm_cx_costs_1_native_2q(self):
        counter = Counter({"cx": 10})
        qubit_map = {"cx": 2}
        result = decompose_for_vendor("IBM", counter, qubit_map)
        assert result.native_2q == 10  # 10 × 1 CZ
        assert result.native_1q == 20  # 10 × 2 Hadamards

    def test_ibm_cz_is_native(self):
        counter = Counter({"cz": 5})
        qubit_map = {"cz": 2}
        result = decompose_for_vendor("IBM", counter, qubit_map)
        assert result.native_2q == 5
        assert result.native_1q == 0  # CZ is native, no extra 1Q

    def test_ionq_cx_costs_1_ms_plus_4_rotations(self):
        counter = Counter({"cx": 4})
        qubit_map = {"cx": 2}
        result = decompose_for_vendor("IonQ", counter, qubit_map)
        assert result.native_2q == 4  # 4 × 1 MS
        assert result.native_1q == 16  # 4 × 4 rotations

    def test_rigetti_cx_costs_2_iswap(self):
        counter = Counter({"cx": 3})
        qubit_map = {"cx": 2}
        result = decompose_for_vendor("Rigetti", counter, qubit_map)
        assert result.native_2q == 6  # 3 × 2 iSWAP
        assert result.native_1q == 12  # 3 × 4 rotations

    def test_toffoli_decomposition(self):
        """Toffoli = 6 CNOT + 9 1Q. Each CNOT then decomposes per vendor."""
        counter = Counter({"ccx": 2})
        qubit_map = {"ccx": 3}

        # Google: each CX = 2 √iSWAP + 4 1Q
        google = decompose_for_vendor("Google", counter, qubit_map)
        assert google.native_2q == 2 * 6 * 2  # 24 √iSWAP
        assert google.native_1q == 2 * (9 + 6 * 4)  # 66

        # IBM: each CX = 1 CZ + 2 1Q
        ibm = decompose_for_vendor("IBM", counter, qubit_map)
        assert ibm.native_2q == 2 * 6 * 1  # 12 CZ
        assert ibm.native_1q == 2 * (9 + 6 * 2)  # 42

    def test_mixed_circuit(self):
        counter = Counter({"h": 5, "t": 8, "cx": 10, "ccx": 1})
        qubit_map = {"h": 1, "t": 1, "cx": 2, "ccx": 3}

        result = decompose_for_vendor("Google", counter, qubit_map)
        # h: 5 native 1Q
        # t: virtual → 0
        # cx: 10 × 2 = 20 native 2Q, 10 × 4 = 40 native 1Q
        # ccx: 1 × 6×2 = 12 native 2Q, 1 × (9 + 6×4) = 33 native 1Q
        assert result.native_1q == 5 + 0 + 40 + 33  # 78
        assert result.native_2q == 0 + 0 + 20 + 12  # 32
        assert result.total == 78 + 32  # 110

    def test_per_gate_breakdown_populated(self):
        counter = Counter({"h": 3, "cx": 2, "t": 1})
        qubit_map = {"h": 1, "cx": 2, "t": 1}
        result = decompose_for_vendor("IBM", counter, qubit_map)
        assert len(result.per_gate) == 3
        gate_names = {g.gate for g in result.per_gate}
        assert gate_names == {"h", "cx", "t"}

    def test_total_equals_1q_plus_2q(self):
        counter = Counter({"h": 10, "cx": 5, "ccx": 2})
        qubit_map = {"h": 1, "cx": 2, "ccx": 3}
        for vendor in VENDOR_2Q_COSTS:
            result = decompose_for_vendor(vendor, counter, qubit_map)
            assert result.total == result.native_1q + result.native_2q

    def test_empty_circuit(self):
        result = decompose_for_vendor("Google", Counter(), {})
        assert result.native_1q == 0
        assert result.native_2q == 0
        assert result.total == 0

    def test_cz_native_vendors_zero_extra_1q(self):
        """CZ-native vendors (IBM, Atom, QuEra, Quandela) need 0 extra 1Q for CZ."""
        counter = Counter({"cz": 5})
        qubit_map = {"cz": 2}
        for vendor in ("IBM", "Atom Computing", "QuEra", "Quandela"):
            result = decompose_for_vendor(vendor, counter, qubit_map)
            assert result.native_1q == 0, f"{vendor} should have 0 extra 1Q for CZ"
            assert result.native_2q == 5


class TestGetNative2qGate:

    def test_known_vendors(self):
        assert get_native_2q_gate("Google") == "√iSWAP"
        assert get_native_2q_gate("IBM") == "CZ"
        assert get_native_2q_gate("IonQ") == "MS"
        assert get_native_2q_gate("Rigetti") == "iSWAP"

    def test_unknown_vendor_returns_cx(self):
        assert get_native_2q_gate("Unknown") == "CX"
