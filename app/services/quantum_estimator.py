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
        runtime, runtime_seconds, physical_qubits, logical_error_rate,
        rqops, code_distance, clock_frequency,
        algorithmic_logical_qubits,
        num_tstates, num_tfactories, num_tfactory_runs,
        physical_qubits_for_algorithm, physical_qubits_for_tfactories,
        required_logical_qubit_error_rate, required_logical_tstate_error_rate,
        tfactory_physical_qubits, tfactory_runtime_seconds

    status="not_available"
        processor, technology, year, source, reason

    status="above_threshold"
        processor, technology, year, source, qec_scheme, detail,
        failing_field, failing_value

    status="error"
        processor, technology, year, source, qec_scheme, detail
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterator

import pyqasm

from app.services.estimate_rollup import rollup_analyze_vendor_results
from qsharp.estimator import EstimatorParams
from qsharp.estimator._estimator import EstimatorError
from qsharp.openqasm import QasmError, estimate as _qsharp_estimate

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
    def _merge_override(base: dict, override: dict) -> dict:
        """Deep-merge an override dict into a fresh copy of the vendor info."""
        merged = copy.deepcopy(base)
        for section in ("qubit_params", "qec_scheme"):
            patch = override.get(section)
            if patch:
                merged.setdefault(section, {}).update(patch)
        if override.get("max_code_distance") is not None:
            merged["max_code_distance"] = override["max_code_distance"]
        for field in ("processor", "technology", "year", "source"):
            if override.get(field) is not None:
                merged[field] = override[field]
        return merged

    @staticmethod
    def _cache_key(vendor_info: dict, qasm_str: str) -> str:
        payload = json.dumps(vendor_info, sort_keys=True) + qasm_str
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _failing_error_rate(vendor_info: dict) -> tuple[str, float] | None:
        """Return the first error-rate field that is >= the QEC threshold,
        or None if the vendor passes the pre-check.
        """
        qp = vendor_info.get("qubit_params", {})
        threshold = vendor_info.get("qec_scheme", {}).get(
            "error_correction_threshold", 0
        )
        for k in QuantumEstimator._ERROR_RATE_KEYS:
            value = qp.get(k, 0)
            if value >= threshold:
                return k, value
        return None

    @staticmethod
    def _is_below_threshold(vendor_info: dict) -> bool:
        return QuantumEstimator._failing_error_rate(vendor_info) is None

    _REQUIRED_QUBIT_FIELDS = (
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
    )

    _REQUIRED_QEC_FIELDS = (
        "name",
        "crossing_prefactor",
        "error_correction_threshold",
        "distance_coefficient_power",
        "logical_cycle_time",
        "physical_qubits_per_logical_qubit",
    )

    @staticmethod
    # Guard-style early returns keep validation readable and specific.
    # pylint: disable=too-many-return-statements
    def _validate_vendor_spec(vendor_info: dict) -> str | None:
        """Validate a user-provided vendor spec. Returns a human-readable
        reason string if the spec is invalid, or None if it passes.
        """
        qp = vendor_info.get("qubit_params")
        if not isinstance(qp, dict):
            return "Missing qubit_params section."
        for key in QuantumEstimator._REQUIRED_QUBIT_FIELDS:
            if key not in qp:
                return f"qubit_params is missing required field '{key}'."
        for key in QuantumEstimator._ERROR_RATE_KEYS:
            value = qp[key]
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                return f"{key} must be a number in [0, 1] (got {value!r})."

        qec = vendor_info.get("qec_scheme")
        if not isinstance(qec, dict):
            return "Missing qec_scheme section."
        for key in QuantumEstimator._REQUIRED_QEC_FIELDS:
            if key not in qec:
                return f"qec_scheme is missing required field '{key}'."
        threshold = qec["error_correction_threshold"]
        if not isinstance(threshold, (int, float)) or not 0 < threshold < 1:
            return (
                f"qec_scheme.error_correction_threshold must be a number in (0, 1) "
                f"(got {threshold!r})."
            )
        return None

    @staticmethod
    def _build_params(vendor_info: dict) -> EstimatorParams:
        qp = vendor_info["qubit_params"]
        qec = vendor_info["qec_scheme"]
        params = EstimatorParams()
        params.error_budget = 0.01
        for attr in QuantumEstimator._REQUIRED_QUBIT_FIELDS:
            setattr(params.qubit_params, attr, qp[attr])
        for attr in QuantumEstimator._REQUIRED_QEC_FIELDS:
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
        """Extract the success metrics from a raw Azure QRE result.

        Pulls every field the frontend currently renders, plus the vendor-
        differentiating fields used by the new charts and detail popover.
        Nanosecond durations are converted to seconds for chart axes; the
        pre-formatted strings from `physicalCountsFormatted` are forwarded so
        the frontend can reuse Azure's own human-readable labels.
        """
        pc = raw["physicalCounts"]
        pcf = raw["physicalCountsFormatted"]
        breakdown = pc["breakdown"]
        lq = raw["logicalQubit"]
        tf = raw.get("tfactory") or {}

        return {
            # --- already rendered ---
            "runtime": pcf["runtime"],
            "runtime_seconds": pc["runtime"] / 1e9,
            "physical_qubits": pc["physicalQubits"],
            "logical_error_rate": lq["logicalErrorRate"],
            # --- throughput (new ThroughputChart) ---
            "rqops": pc["rqops"],
            "clock_frequency": breakdown["clockFrequency"],
            # --- code distance (new CodeDistanceChart) ---
            "code_distance": lq["codeDistance"],
            # --- qubit budget split (new QubitBudgetChart) ---
            "physical_qubits_for_algorithm": breakdown["physicalQubitsForAlgorithm"],
            "physical_qubits_for_tfactories": breakdown["physicalQubitsForTfactories"],
            # --- extra fields for the detail popover ---
            "algorithmic_logical_qubits": breakdown["algorithmicLogicalQubits"],
            "algorithmic_logical_depth": breakdown["algorithmicLogicalDepth"],
            "logical_depth": breakdown["logicalDepth"],
            "num_tstates": breakdown["numTstates"],
            "num_tfactories": breakdown["numTfactories"],
            "num_tfactory_runs": breakdown["numTfactoryRuns"],
            "required_logical_qubit_error_rate": breakdown[
                "requiredLogicalQubitErrorRate"
            ],
            "required_logical_tstate_error_rate": breakdown[
                "requiredLogicalTstateErrorRate"
            ],
            "clifford_error_rate": breakdown["cliffordErrorRate"],
            "logical_cycle_time_ns": lq["logicalCycleTime"],
            "tfactory_physical_qubits": tf.get("physicalQubits"),
            "tfactory_runtime_seconds": (
                (tf["runtime"] / 1e9) if "runtime" in tf else None
            ),
            "tfactory_num_rounds": tf.get("numRounds"),
            # pre-formatted strings (opaque display passthroughs)
            "formatted": {
                "runtime": pcf["runtime"],
                "rqops": pcf["rqops"],
                "physical_qubits": pcf["physicalQubits"],
                "algorithmic_logical_qubits": pcf["algorithmicLogicalQubits"],
                "algorithmic_logical_depth": pcf.get("algorithmicLogicalDepth"),
                "logical_depth": pcf.get("logicalDepth"),
                "num_tstates": pcf["numTstates"],
                "num_tfactories": pcf["numTfactories"],
                "num_tfactory_runs": pcf["numTfactoryRuns"],
                "physical_qubits_for_algorithm": pcf["physicalQubitsForAlgorithm"],
                "physical_qubits_for_tfactories": pcf["physicalQubitsForTfactories"],
                "physical_qubits_for_tfactories_percentage": pcf[
                    "physicalQubitsForTfactoriesPercentage"
                ],
                "required_logical_qubit_error_rate": pcf[
                    "requiredLogicalQubitErrorRate"
                ],
                "required_logical_tstate_error_rate": pcf[
                    "requiredLogicalTstateErrorRate"
                ],
                "logical_cycle_time": pcf["logicalCycleTime"],
                "clock_frequency": pcf["clockFrequency"],
                "logical_error_rate": pcf["logicalErrorRate"],
                "tfactory_runtime": pcf.get("tfactoryRuntime"),
                "tfactory_physical_qubits": pcf.get("tfactoryPhysicalQubits"),
            },
        }

    # This method intentionally assembles a rich result payload from many
    # vendor/runtime fields in one place.
    # pylint: disable=too-many-locals
    def _run_vendor_estimate(
        self,
        vendor_name: str,
        vendor_info: dict,
        qasm_str: str,
        is_default: bool,
    ) -> dict:
        """
        Execute Azure QRE for one vendor. Returns a flat result dict with a
        'status' key of 'success', 'above_threshold', or 'error'.

        `is_default` indicates whether `vendor_info` is the unmodified
        vendors.json entry — used to decide whether the precomputed
        `_params_cache` entry can be reused.
        """
        key = self._cache_key(vendor_info, qasm_str)
        if key in self._cache:
            return self._cache[key]

        # Validate user-supplied specs before touching Q#.
        spec_error = self._validate_vendor_spec(vendor_info)
        base_static = {
            "processor": vendor_info.get("processor", vendor_name),
            "technology": vendor_info.get("technology", "Unknown"),
            "year": vendor_info.get("year"),
            "source": vendor_info.get("source", ""),
        }
        if spec_error is not None:
            return {
                **base_static,
                "qec_scheme": vendor_info.get("qec_scheme", {}).get("name", ""),
                "status": "error",
                "detail": f"Invalid vendor spec: {spec_error}",
            }

        qec = vendor_info["qec_scheme"]
        base = {**base_static, "qec_scheme": qec["name"]}

        # Pre-check: all physical error rates must be below the QEC threshold.
        # Report the specific failing field so the user knows what to fix.
        failing = self._failing_error_rate(vendor_info)
        if failing is not None:
            failing_field, failing_value = failing
            threshold = qec["error_correction_threshold"]
            return {
                **base,
                "status": "above_threshold",
                "detail": (
                    f"{failing_field} ({failing_value:.2e}) exceeds "
                    f"{qec['name']} threshold ({threshold:.2e})"
                ),
                "failing_field": failing_field,
                "failing_value": float(failing_value),
            }

        if is_default:
            params = self._params_cache.get(
                vendor_name, self._build_params(vendor_info)
            )
        else:
            params = self._build_params(vendor_info)

        try:
            raw = _qsharp_estimate(qasm_str, params=params).data()
        except EstimatorError as exc:
            return {
                **base,
                "status": "error",
                "detail": exc.message or "Azure QRE rejected this circuit.",
            }
        except QasmError as exc:
            # Native Q#/OpenQASM lowering failures (inherits BaseException).
            detail = str(exc).strip()
            return {
                **base,
                "status": "error",
                "detail": detail or "OpenQASM could not be lowered for estimation.",
            }
        except (RuntimeError, ValueError, OSError) as exc:
            msg = str(exc)
            return {
                **base,
                "status": "error",
                "detail": (
                    f"Estimation failed: {msg}"
                    if msg
                    else "Estimation failed. Check circuit validity and try again."
                ),
            }

        result = {**base, **self._parse_raw_result(raw), "status": "success"}
        self._cache[key] = result
        return result

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def estimate(
        self,
        qasm_str: str,
        overrides: dict[str, dict] | None = None,
        custom_vendors: dict[str, dict] | None = None,
    ) -> dict[str, dict]:
        """
        Run quantum resource estimation for all vendors in self.vendors plus
        any user-supplied custom vendors.

        Parameters
        ----------
        qasm_str : str
            OpenQASM 2.0 circuit string to estimate.
        overrides : dict[str, dict] | None
            Optional per-vendor parameter overrides. Keyed by the vendor name
            exactly as it appears in `self.vendors`. Each value may contain
            `qubit_params`, `qec_scheme`, and/or `max_code_distance`; only the
            fields supplied are merged over the defaults. The base
            vendors.json data is never mutated.
        custom_vendors : dict[str, dict] | None
            Optional user-supplied vendors to estimate alongside the built-in
            ones. Each value must be a full vendor spec (same shape as
            vendors.json entries). Names that collide with built-in vendors
            are rejected with a ValueError so custom vendors cannot silently
            shadow the defaults. Invalid specs are not raised here — they
            propagate to `_run_vendor_estimate` which returns a structured
            error result with the reason.

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
                runtime_seconds     — float (seconds)
                physical_qubits     — int
                logical_error_rate  — float
                (plus the enriched Q# fields documented in the module header)

            When status == "not_available":
                reason              — explanation string

            When status in ("above_threshold", "error"):
                qec_scheme          — QEC code name
                detail              — error description string
                (above_threshold also carries failing_field + failing_value)
        """
        if qasm_str not in self._preprocess_cache:
            self._preprocess_cache[qasm_str] = self._preprocess(qasm_str)
        processed = self._preprocess_cache[qasm_str]
        overrides = overrides or {}
        custom_vendors = custom_vendors or {}

        collisions = set(custom_vendors) & set(self.vendors)
        if collisions:
            raise ValueError(
                "Custom vendor names collide with built-in vendors: "
                + ", ".join(sorted(collisions))
            )

        active: list[tuple[str, dict, bool]] = []
        for name, info in self.vendors.items():
            if not info.get("available", True):
                continue
            if name in overrides:
                merged = self._merge_override(info, overrides[name])
                active.append((name, merged, False))
            else:
                active.append((name, info, True))
        for name, info in custom_vendors.items():
            # Custom vendors always run the uncached params path (is_default=False)
            # so _params_cache isn't consulted for an unknown name.
            active.append((name, info, False))

        with ThreadPoolExecutor(max_workers=len(active) or 1) as pool:
            futures = {
                name: pool.submit(
                    self._run_vendor_estimate, name, info, processed, is_default
                )
                for name, info, is_default in active
            }

        # Resolve in original vendor order, not completion order
        return {name: fut.result() for name, fut in futures.items()}

    def estimate_streaming(
        self,
        qasm_str: str,
        overrides: dict[str, dict] | None = None,
        custom_vendors: dict[str, dict] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield progress events for a streaming resource estimation.

        Event shapes (all dicts, suitable for JSON serialization):

            {"type": "stage", "stage": "preprocessing"}
            {"type": "stage", "stage": "estimating", "total_vendors": N}
            {"type": "vendor_result", "vendor": name, "completed": k,
             "total": N, "result": {...}}
            {"type": "complete", "vendors": {name: {...}, ...}}

        Events arrive as each vendor's future resolves, so the consumer sees
        progress well before the full response is ready.
        """
        yield {"type": "stage", "stage": "preprocessing"}
        if qasm_str not in self._preprocess_cache:
            self._preprocess_cache[qasm_str] = self._preprocess(qasm_str)
        processed = self._preprocess_cache[qasm_str]
        overrides = overrides or {}
        custom_vendors = custom_vendors or {}

        collisions = set(custom_vendors) & set(self.vendors)
        if collisions:
            raise ValueError(
                "Custom vendor names collide with built-in vendors: "
                + ", ".join(sorted(collisions))
            )

        active: list[tuple[str, dict, bool]] = []
        for name, info in self.vendors.items():
            if not info.get("available", True):
                continue
            if name in overrides:
                merged = self._merge_override(info, overrides[name])
                active.append((name, merged, False))
            else:
                active.append((name, info, True))
        for name, info in custom_vendors.items():
            active.append((name, info, False))

        total = len(active)
        yield {"type": "stage", "stage": "estimating", "total_vendors": total}

        vendor_results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=total or 1) as pool:
            future_to_name = {
                pool.submit(
                    self._run_vendor_estimate, name, info, processed, is_default
                ): name
                for name, info, is_default in active
            }
            completed = 0
            for fut in as_completed(future_to_name):
                name = future_to_name[fut]
                result = fut.result()
                vendor_results[name] = result
                completed += 1
                yield {
                    "type": "vendor_result",
                    "vendor": name,
                    "completed": completed,
                    "total": total,
                    "result": result,
                }

        # Preserve the original vendor ordering on the final payload so the
        # frontend can render a stable list regardless of completion order.
        ordered = {
            name: vendor_results[name]
            for name, _, _ in active
            if name in vendor_results
        }
        yield {
            "type": "complete",
            "vendors": ordered,
            **rollup_analyze_vendor_results(ordered),
        }

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
    cli_results = estimator.estimate(qasm_input)
    pprint.pprint(cli_results, sort_dicts=False)
