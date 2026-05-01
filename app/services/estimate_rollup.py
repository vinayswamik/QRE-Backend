"""Aggregate vendor estimate outcomes for API responses (REST + SSE)."""

from typing import Any, Mapping


def rollup_analyze_vendor_results(
    vendors: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return counts and optional banner when no vendor succeeded.

    ``vendors`` values match the flat dict produced by QuantumEstimator /
    VendorEstimateResult (status, detail, reason, ...).
    """
    vals = list(vendors.values())
    successful_vendor_count = sum(1 for v in vals if v.get("status") == "success")
    failed_vendor_count = len(vals) - successful_vendor_count
    estimate_failure_banner: str | None = None
    if successful_vendor_count == 0 and vals:
        messages: list[str] = []
        for v in vals:
            st = v.get("status")
            if st == "success":
                continue
            if st == "not_available":
                raw = (v.get("reason") or "").strip()
            else:
                raw = (v.get("detail") or v.get("reason") or "").strip()
            if raw:
                messages.append(raw)
        if not messages:
            estimate_failure_banner = "No vendor returned a successful estimate."
        else:
            unique = list(dict.fromkeys(messages))
            estimate_failure_banner = (
                unique[0]
                if len(unique) == 1
                else (
                    f"{unique[0]} Additional vendors reported other failures;"
                    " see per-vendor results."
                )
            )
    return {
        "successful_vendor_count": successful_vendor_count,
        "failed_vendor_count": failed_vendor_count,
        "estimate_failure_banner": estimate_failure_banner,
    }
