"""
quantum_estimator.py
====================
Single-file quantum resource estimator across multiple hardware vendors.

Public API
----------
    estimator = QuantumEstimator()
    results = estimator.estimate(qasm_str)  -> dict[str, dict]

    Access/modify vendors:
        estimator.vendors["My Vendor"] = {...}   # add
        del estimator.vendors["PsiQuantum"]       # remove

Vendor data is loaded from vendors.json (same directory as this file).

Return schema (per vendor key)
------------------------------
    status="success"
        processor, technology, year, source, qec_scheme,
        runtime, physical_qubits, total_logical_gates, logical_error_rate

    status="not_available"
        processor, technology, year, source, reason

    status="above_threshold" | status="error"
        processor, technology, year, source, qec_scheme, detail
"""

from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pyqasm
from qsharp.estimator import EstimatorParams
from qsharp.openqasm import estimate as _qsharp_estimate

_VENDORS_FILE = Path(__file__).resolve().parent.parent / "core" / "vendors.json"


class QuantumEstimator:
    """
    Quantum resource estimator across multiple hardware vendors.

    Attributes
    ----------
    vendors : dict[str, dict]
        Vendor configuration map loaded from vendors.json.
        Add, remove, or edit entries to change the vendor set.
        Unavailable vendors use {"available": false, "reason": "..."}.
    """

    _ERROR_RATE_KEYS = (
        "one_qubit_gate_error_rate",
        "two_qubit_gate_error_rate",
        "one_qubit_measurement_error_rate",
        "t_gate_error_rate",
        "idle_error_rate",
    )

    _GATE_KEYS = (
        "tCount",
        "rotationCount",
        "rotationDepth",
        "cczCount",
        "ccixCount",
        "measurementCount",
    )

    def __init__(self, vendors_file: Path | str = _VENDORS_FILE):
        """
        Parameters
        ----------
        vendors_file : Path or str, optional
            Path to the vendors JSON file. Defaults to vendors.json
            in the same directory as this module.
        """
        with Path(vendors_file).open(encoding="utf-8") as f:
            self.vendors: dict[str, dict[str, Any]] = json.load(f)
        self._cache: dict[str, dict] = {}
        self._preprocess_cache: dict[str, str] = {}
        self._params_cache: dict[str, EstimatorParams] = {
            name: self._build_params(info)
            for name, info in self.vendors.items()
            if info.get("available", True) and self._is_below_threshold(info)
        }

    @staticmethod
    def _cache_key(vendor_info: dict, qasm_str: str) -> str:
        payload = json.dumps(vendor_info, sort_keys=True) + qasm_str
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _is_below_threshold(vendor_info: dict) -> bool:
        qp = vendor_info.get("qubit_params", {})
        threshold = vendor_info.get("qec_scheme", {}).get(
            "error_correction_threshold", 0
        )
        return all(qp.get(k, 0) < threshold for k in QuantumEstimator._ERROR_RATE_KEYS)

    @staticmethod
    def _build_params(vendor_info: dict) -> EstimatorParams:
        qp = vendor_info["qubit_params"]
        qec = vendor_info["qec_scheme"]
        params = EstimatorParams()
        params.error_budget = 0.01
        for attr in (
            "name",
            "instruction_set",
            "one_qubit_gate_time",
            "two_qubit_gate_time",
            "one_qubit_measurement_time",
            "one_qubit_gate_error_rate",
            "two_qubit_gate_error_rate",
            "one_qubit_measurement_error_rate",
            "t_gate_time",
            "t_gate_error_rate",
            "idle_error_rate",
        ):
            setattr(params.qubit_params, attr, qp[attr])
        for attr in (
            "name",
            "crossing_prefactor",
            "error_correction_threshold",
            "distance_coefficient_power",
            "logical_cycle_time",
            "physical_qubits_per_logical_qubit",
        ):
            setattr(params.qec_scheme, attr, qec[attr])
        params.qec_scheme.max_code_distance = vendor_info.get("max_code_distance", 50)
        return params

    # ------------------------------------------------------------------
    # CIRCUIT PREPROCESSING  (private)
    # ------------------------------------------------------------------

    @staticmethod
    def _decompose_gate(line: str) -> str:
        """Decompose or remove a single unrolled QASM gate line."""
        s = line.strip()

        # Drop global phase and no-ops — not physical gates
        if s.startswith(("gphase(", "nop ")):
            return ""

        # swap → 3 CNOTs
        m = re.match(r"swap (q\[\d+\]), (q\[\d+\]);", s)
        if m:
            a, b = m.group(1), m.group(2)
            return f"cx {a}, {b};\ncx {b}, {a};\ncx {a}, {b};"

        # sx / sxdg → rx(±π/2)
        m = re.match(r"sx (q\[\d+\]);", s)
        if m:
            return f"rx(1.5707963267948966) {m.group(1)};"

        m = re.match(r"sxdg (q\[\d+\]);", s)
        if m:
            return f"rx(-1.5707963267948966) {m.group(1)};"

        return line

    def _preprocess(self, qasm_str: str) -> str:
        """Unroll, remove barriers, and decompose gates. Returns a clean QASM string."""
        circuit = pyqasm.loads(qasm_str)
        circuit.unroll()
        circuit.remove_barriers()
        unrolled = str(circuit)
        return "\n".join(
            decomposed
            for line in unrolled.splitlines()
            for decomposed in [self._decompose_gate(line)]
            if decomposed
        )

    # ------------------------------------------------------------------
    # ESTIMATION ENGINE  (private)
    # ------------------------------------------------------------------

    def _parse_raw_result(self, raw: dict) -> dict:
        """Extract the success metrics from a raw Azure QRE result."""
        lc = raw.get("logicalCounts", {})
        return {
            "runtime": raw["physicalCountsFormatted"]["runtime"],
            "physical_qubits": raw["physicalCounts"]["physicalQubits"],
            "total_logical_gates": sum(lc.get(k, 0) for k in self._GATE_KEYS),
            "logical_error_rate": raw["logicalQubit"]["logicalErrorRate"],
        }

    def _run_vendor_estimate(self, vendor_info: dict, qasm_str: str) -> dict:
        """
        Execute Azure QRE for one vendor. Returns a flat result dict with a
        'status' key of 'success', 'above_threshold', or 'error'.
        """
        key = self._cache_key(vendor_info, qasm_str)
        if key in self._cache:
            return self._cache[key]

        qp = vendor_info["qubit_params"]
        qec = vendor_info["qec_scheme"]

        base = {
            "processor": vendor_info["processor"],
            "technology": vendor_info["technology"],
            "year": vendor_info["year"],
            "source": vendor_info["source"],
            "qec_scheme": qec["name"],
        }

        # Pre-check: all physical error rates must be below the QEC threshold
        threshold = qec["error_correction_threshold"]
        over = [f"{k}={qp[k]}" for k in self._ERROR_RATE_KEYS if qp[k] >= threshold]
        if over:
            return {
                **base,
                "status": "above_threshold",
                "detail": f"ABOVE QEC THRESHOLD ({threshold}): {', '.join(over)}",
            }

        params = self._params_cache.get(
            vendor_info["processor"], self._build_params(vendor_info)
        )

        try:
            raw = _qsharp_estimate(qasm_str, params=params).data()
        except (RuntimeError, ValueError, OSError) as exc:
            return {**base, "status": "error", "detail": str(exc)}

        result = {**base, **self._parse_raw_result(raw), "status": "success"}
        self._cache[key] = result
        return result

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def estimate(self, qasm_str: str) -> dict[str, dict]:
        """
        Run quantum resource estimation for all vendors in self.vendors.

        Parameters
        ----------
        qasm_str : str
            OpenQASM 2.0 circuit string to estimate.

        Returns
        -------
        dict[str, dict]
            Keyed by vendor name. Each value contains:

            Always present:
                status        — "success" | "not_available" | "above_threshold"
                                | "error"
                processor     — hardware description string
                technology    — qubit modality
                year          — int or None
                source        — citation string

            When status == "success":
                qec_scheme          — QEC code name
                runtime             — human-readable runtime string
                physical_qubits     — int
                total_logical_gates — int
                logical_error_rate  — float

            When status == "not_available":
                reason              — explanation string

            When status in ("above_threshold", "error"):
                qec_scheme          — QEC code name
                detail              — error description string
        """
        processed = self._preprocess_cache.get(
            qasm_str
        ) or self._preprocess_cache.setdefault(qasm_str, self._preprocess(qasm_str))
        active = {
            name: info
            for name, info in self.vendors.items()
            if info.get("available", True)
        }

        with ThreadPoolExecutor(max_workers=len(active) or 1) as pool:
            futures = {
                name: pool.submit(self._run_vendor_estimate, info, processed)
                for name, info in active.items()
            }

        # Resolve in original vendor order, not completion order
        return {name: fut.result() for name, fut in futures.items()}

    def pause_vendor(self, *names: str) -> None:
        """
        Exclude one or more vendors from future estimate() calls by setting
        available=False. Their data remains intact in self.vendors.

        Parameters
        ----------
        *names : str
            One or more vendor keys exactly as they appear in self.vendors.
        """
        for name in names:
            if name not in self.vendors:
                raise KeyError(f"Unknown vendor: {name!r}")
            self.vendors[name]["available"] = False

    def resume_vendor(self, *names: str) -> None:
        """
        Re-include previously paused vendors in estimate() calls by setting
        available=True.

        Parameters
        ----------
        *names : str
            One or more vendor keys to resume.
        """
        for name in names:
            if name not in self.vendors:
                raise KeyError(f"Unknown vendor: {name!r}")
            self.vendors[name]["available"] = True


# ---------------------------------------------------------------------------
# CLI  (python quantum_estimator.py <circuit.qasm>)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pprint
    import sys

    if len(sys.argv) < 2:
        print("Usage: python quantum_estimator.py <circuit.qasm>", file=sys.stderr)
        sys.exit(1)

    qasm_input = Path(sys.argv[1]).read_text(encoding="utf-8")
    estimator = QuantumEstimator()
    results = estimator.estimate(qasm_input)
    pprint.pprint(results, sort_dicts=False)
