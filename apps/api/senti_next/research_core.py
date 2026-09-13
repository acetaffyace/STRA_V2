"""Deterministic Research Core orchestration for raw Steam review populations.

This module is intentionally a coordinator.  It calls the validated Stage 2A
through Stage 2E implementations and preserves their report structures rather
than reimplementing any statistical, activity, or composition logic.  It does
not import the semantic/LLM layer, routes, persistence, or DataFrame helpers.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping, Optional

from .activity_diagnostics import analyze_review_activity
from .population_validity import REVIEWER_SELECTION_LIMITATION, compare_populations
from .rate_inference import calculate_recommendation_rate, compare_recommendation_rates
from .standardization import standardize_populations
from .window_robustness import matched_window_robustness


RESEARCH_CORE_VERSION = "2p2-v1"
REPORT_SCHEMA_VERSION = "research-report-v1"


def _json_compatible(value: Any) -> Any:
    """Convert metadata containers to deterministic JSON-compatible values."""
    if value is None or isinstance(value, (str, int, bool, float)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, set):
        return [_json_compatible(item) for item in sorted(value, key=repr)]
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _json_compatible(model_dump(mode="json"))
        except TypeError:
            return _json_compatible(model_dump())
    # Do not invent provenance from an unsupported object representation.
    return None


def _metadata_mapping(metadata: Any) -> dict[str, Any]:
    if metadata is None:
        return {}
    if isinstance(metadata, Mapping):
        return {str(key): _json_compatible(value) for key, value in metadata.items()}
    model_dump = getattr(metadata, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json")
        except TypeError:
            dumped = model_dump()
        return dict(_json_compatible(dumped)) if isinstance(dumped, Mapping) else {}
    return {}


def _metadata_value(metadata: Any, key: str) -> Any:
    data = _metadata_mapping(metadata)
    if key in data:
        return data[key]
    for container_key in ("population_provenance", "acquisition_coverage", "active_filters"):
        container = data.get(container_key)
        if isinstance(container, Mapping) and key in container:
            return container[key]
    return None


def _population_projection(population: list[Mapping[str, Any]], metadata: Any) -> dict[str, Any]:
    """Project identity/provenance without inferring a window from observed rows."""
    return {
        "review_count": len(population),
        "sampling_contract": _metadata_value(metadata, "sampling_contract"),
        "collection_complete": _metadata_value(metadata, "collection_complete")
        if _metadata_value(metadata, "collection_complete") is not None
        else _metadata_value(metadata, "scope_complete"),
        "truncated_by_max_reviews": _metadata_value(metadata, "truncated_by_max_reviews"),
        "stop_reason": _metadata_value(metadata, "stop_reason"),
        "coverage_start_time": _metadata_value(metadata, "coverage_start_time"),
        "coverage_end_time": _metadata_value(metadata, "coverage_end_time"),
        "coverage_status": _metadata_value(metadata, "coverage_status"),
        "coverage_end_inclusive": _metadata_value(metadata, "coverage_end_inclusive"),
    }


def _unavailable(reason: str) -> dict[str, str]:
    return {"status": "unavailable", "reason": reason}


def _orchestration(
    stages_executed: list[str],
    stages_unavailable: Mapping[str, str],
    *,
    confidence_level: float | None = None,
    requested_standardization_variables: Optional[Iterable[str]] = None,
    effective_standardization_variables: Optional[Iterable[str]] = None,
    standardization_target: str | None = None,
    windows_days: Optional[Iterable[int | float]] = None,
    activity_grain: str = "day",
) -> dict[str, Any]:
    requested_variables = None if requested_standardization_variables is None else list(requested_standardization_variables)
    effective_variables = None if effective_standardization_variables is None else list(effective_standardization_variables)
    requested_windows = None if windows_days is None else list(windows_days)
    return {
        "research_core_version": RESEARCH_CORE_VERSION,
        "stages_executed": list(stages_executed),
        "stages_unavailable": dict(stages_unavailable),
        "configuration": {
            "confidence_level": confidence_level,
            "standardization_variables": requested_variables,
            "requested_standardization_variables": requested_variables,
            "effective_standardization_variables": effective_variables,
            "standardization_target": standardization_target,
            "windows_days": requested_windows,
            "activity_grain": activity_grain,
        },
    }


def _limitations(*, comparison: bool, acquisition_limited: bool = False, window_available: bool = False) -> dict[str, Any]:
    limitations: dict[str, Any] = {
        "steam_reviewer_selection": True,
        "not_all_players": True,
        "recommendation_is_not_text_sentiment": True,
        "observational_not_causal": True,
        "reviewer_selection_limitation": REVIEWER_SELECTION_LIMITATION,
    }
    if comparison:
        limitations.update(
            {
                "acquisition_limited": bool(acquisition_limited),
                "window_robustness_available": bool(window_available),
            }
        )
    else:
        limitations["no_version_change_claim_from_snapshot"] = True
    return limitations


def _acquisition_limited(*metadata_values: Any, comparability_report: Mapping[str, Any] | None = None) -> bool:
    report = comparability_report or {}
    acquisition = report.get("acquisition_validity")
    if isinstance(acquisition, Mapping) and acquisition.get("level") != "high":
        return True
    for metadata in metadata_values:
        complete = _metadata_value(metadata, "collection_complete")
        if complete is None:
            complete = _metadata_value(metadata, "scope_complete")
        if complete is not True:
            return True
        if _metadata_value(metadata, "truncated_by_max_reviews") is True:
            return True
        if _metadata_value(metadata, "stop_reason") == "max_reviews_reached":
            return True
    return False


def build_snapshot_research_report(
    population: Iterable[Mapping[str, Any]],
    *,
    metadata: Any = None,
    confidence_level: float = 0.95,
    activity_grain: str = "day",
) -> dict[str, Any]:
    """Build a one-population Research Core snapshot from raw review mappings."""
    reviews = list(population)
    recommendation = calculate_recommendation_rate(
        reviews,
        metadata=metadata,
        confidence_level=confidence_level,
    )
    activity = analyze_review_activity(reviews, grain=activity_grain)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "mode": "snapshot",
        "population": _population_projection(reviews, metadata),
        "recommendation": recommendation,
        "activity": activity,
        "comparability": _unavailable("comparison_required"),
        "standardization": _unavailable("comparison_required"),
        "window_robustness": _unavailable("comparison_required"),
        "limitations": _limitations(comparison=False),
        "orchestration": _orchestration(
            ["2B", "2E"],
            {"2A": "comparison_required", "2C": "comparison_required", "2D": "comparison_required"},
            confidence_level=confidence_level,
            activity_grain=activity_grain,
        ),
    }


def build_comparison_research_report(
    reference_population: Iterable[Mapping[str, Any]],
    comparison_population: Iterable[Mapping[str, Any]],
    *,
    reference_metadata: Any = None,
    comparison_metadata: Any = None,
    reference_anchor: Any = None,
    comparison_anchor: Any = None,
    confidence_level: float = 0.95,
    standardization_variables: Optional[Iterable[str]] = None,
    standardization_target: str = "reference",
    windows_days: Iterable[int | float] = (3, 7, 14),
    activity_grain: str = "day",
    events: Optional[Iterable[Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    """Build a comparison Research Core report from two raw populations."""
    reference = list(reference_population)
    comparison = list(comparison_population)
    variables = None if standardization_variables is None else tuple(standardization_variables)
    requested_windows = tuple(windows_days)
    event_rows = None if events is None else list(events)

    comparability = compare_populations(
        reference,
        comparison,
        reference_metadata,
        comparison_metadata,
    )
    recommendation = compare_recommendation_rates(
        reference,
        comparison,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        confidence_level=confidence_level,
        comparability_report=comparability,
    )
    standardization = standardize_populations(
        reference,
        comparison,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        comparability_report=comparability,
        variables=variables,
        target=standardization_target,
    )
    # Stage 2C is the source of truth for defaults (currently language).  Pass
    # its effective variables to Stage 2D rather than duplicating that policy.
    effective_variables = tuple(
        standardization.get("standardization", {}).get("variables") or ()
    )
    activity_reference = analyze_review_activity(reference, grain=activity_grain)
    activity_comparison = analyze_review_activity(comparison, grain=activity_grain)

    stages_unavailable: dict[str, str] = {}
    if reference_anchor is None or comparison_anchor is None:
        window_robustness: dict[str, Any] = _unavailable("lifecycle_anchors_required")
        stages_unavailable["2D"] = "lifecycle_anchors_required"
        stages_executed = ["2A", "2B", "2C", "2E"]
    else:
        window_robustness = matched_window_robustness(
            reference,
            comparison,
            reference_anchor,
            comparison_anchor,
            reference_metadata=reference_metadata,
            comparison_metadata=comparison_metadata,
            comparability_report=comparability,
            windows_days=requested_windows,
            standardization_variables=effective_variables,
            standardization_target=standardization_target,
            confidence_level=confidence_level,
            events=event_rows,
        )
        stages_executed = ["2A", "2B", "2C", "2D", "2E"]

    window_available = (
        isinstance(window_robustness, Mapping)
        and window_robustness.get("status") != "unavailable"
        and int(((window_robustness.get("robustness") or {}).get("valid_window_count") or 0)) > 0
    )
    acquisition_limited = _acquisition_limited(
        reference_metadata,
        comparison_metadata,
        comparability_report=comparability,
    ) or bool(standardization.get("acquisition_limited"))
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "mode": "comparison",
        "population": {
            "reference": _population_projection(reference, reference_metadata),
            "comparison": _population_projection(comparison, comparison_metadata),
        },
        "comparability": comparability,
        "recommendation": recommendation,
        "standardization": standardization,
        "window_robustness": window_robustness,
        "activity": {
            "reference": activity_reference,
            "comparison": activity_comparison,
        },
        "limitations": _limitations(
            comparison=True,
            acquisition_limited=acquisition_limited,
            window_available=window_available,
        ),
        "orchestration": _orchestration(
            stages_executed,
            stages_unavailable,
            confidence_level=confidence_level,
            requested_standardization_variables=variables,
            effective_standardization_variables=effective_variables,
            standardization_target=standardization_target,
            windows_days=requested_windows,
            activity_grain=activity_grain,
        ),
    }


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "RESEARCH_CORE_VERSION",
    "build_comparison_research_report",
    "build_snapshot_research_report",
]
