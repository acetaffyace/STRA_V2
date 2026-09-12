"""Deterministic acquisition provenance helpers shared by Research Core and routes."""
from __future__ import annotations

from typing import Any

from .sampling import SamplingContract


def derive_acquisition_coverage(
    sampling_contract: SamplingContract,
    fetch_stats: dict[str, Any],
) -> dict[str, Any]:
    """Derive authoritative temporal coverage from contract and fetch state.

    Contract timestamps are Unix seconds and the SamplingContract defines both
    boundaries as inclusive for review selection.  Observed review timestamps
    are intentionally not used here: they describe what was seen, not what
    the crawler covered.
    """

    start = sampling_contract.start_time
    end = sampling_contract.end_time
    complete = fetch_stats.get("collection_complete")
    if not isinstance(complete, bool):
        complete = fetch_stats.get("scope_complete")
    truncated = bool(fetch_stats.get("truncated_by_max_reviews"))
    if truncated or complete is False:
        return {
            "coverage_start_time": None,
            "coverage_end_time": None,
            "coverage_status": "incomplete",
            "coverage_end_inclusive": True if end is not None else None,
            "coverage_reason": "acquisition_incomplete_or_truncated",
        }
    if complete is True and start is not None and end is not None:
        return {
            "coverage_start_time": float(start),
            "coverage_end_time": float(end),
            "coverage_status": "complete",
            "coverage_end_inclusive": True,
            "coverage_reason": "sampling_contract_boundaries",
        }
    return {
        "coverage_start_time": None,
        "coverage_end_time": None,
        "coverage_status": "unknown",
        "coverage_end_inclusive": True if end is not None else None,
        "coverage_reason": "acquisition_temporal_coverage_unknown",
    }


__all__ = ["derive_acquisition_coverage"]
