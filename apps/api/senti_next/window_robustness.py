"""Matched lifecycle-window robustness for already acquired review populations.

Each window compares the same lifecycle exposure after separate release anchors.
The result is an observational sensitivity analysis; it does not establish that
one version caused a recommendation-rate change.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from math import isfinite
from typing import Any, Iterable, Mapping, Optional

from .population_validity import compare_populations
from .rate_inference import compare_recommendation_rates
from .standardization import standardize_populations


DEFAULT_WINDOWS_DAYS = (3, 7, 14)
WINDOW_SENSITIVITY_THRESHOLDS = {
    "stable_max_range": 0.03,
    "moderate_max_range": 0.07,
}
_DAY_SECONDS = 86_400.0
_FLOAT_TOLERANCE = 1e-12
_SCHEMA_VERSION = "matched-window-robustness-v1"
_REQUIRED_EVENT_FIELDS = ("side", "timestamp")


def _as_timestamp(value: Any, *, end_boundary: bool = False) -> Optional[float]:
    """Parse Unix seconds or ISO values; naive values are UTC.

    Date-only start values mean 00:00:00 UTC.  Date-only end values mean the
    exclusive boundary at 00:00:00 UTC on the following day.  Full ISO
    datetimes are never shifted or rounded.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if isfinite(number) else None
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    if isinstance(value, date):
        parsed = datetime.combine(value, time.min, tzinfo=timezone.utc)
        return parsed.timestamp() + (_DAY_SECONDS if end_boundary else 0.0)
    if isinstance(value, str):
        text = value.strip()
        try:
            number = float(text)
            return number if isfinite(number) else None
        except ValueError:
            pass
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            try:
                parsed_date = date.fromisoformat(text)
            except ValueError:
                return None
            parsed = datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
            return parsed.timestamp() + (_DAY_SECONDS if end_boundary else 0.0)
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            try:
                parsed_date = date.fromisoformat(text[:10])
            except ValueError:
                return None
            parsed = datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
            return parsed.timestamp() + (_DAY_SECONDS if end_boundary else 0.0)
    return None


def _metadata_mapping(metadata: Any) -> Mapping[str, Any]:
    if isinstance(metadata, Mapping):
        return metadata
    if hasattr(metadata, "model_dump"):
        dumped = metadata.model_dump(mode="json")
        return dumped if isinstance(dumped, Mapping) else {}
    return {}


def _metadata_value(metadata: Any, key: str) -> Any:
    data = _metadata_mapping(metadata)
    if key in data:
        return data[key]
    for container_key in ("population_provenance", "active_filters"):
        container = data.get(container_key)
        if isinstance(container, Mapping) and key in container:
            return container[key]
    return None


def _coverage_bounds(metadata: Any) -> tuple[Optional[float], Optional[float], Optional[bool], Optional[str]]:
    data = _metadata_mapping(metadata)
    contract = data.get("sampling_contract")
    contract = contract if isinstance(contract, Mapping) else {}
    acquisition_coverage = data.get("acquisition_coverage")
    acquisition_coverage = acquisition_coverage if isinstance(acquisition_coverage, Mapping) else {}
    provenance = data.get("population_provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    nested_coverage = provenance.get("acquisition_coverage")
    nested_coverage = nested_coverage if isinstance(nested_coverage, Mapping) else {}
    active_filters = data.get("active_filters")
    active_filters = active_filters if isinstance(active_filters, Mapping) else {}
    start_value = next(
        (
            value
            for value in (
                data.get("coverage_start_time"),
                acquisition_coverage.get("start_time"),
                provenance.get("coverage_start_time"),
                nested_coverage.get("start_time"),
                active_filters.get("coverage_start_time"),
                data.get("acquisition_start_time"),
                data.get("window_start_time"),
            )
            if value is not None
        ),
        None,
    )
    end_value = next(
        (
            value
            for value in (
                data.get("coverage_end_time"),
                acquisition_coverage.get("end_time"),
                provenance.get("coverage_end_time"),
                nested_coverage.get("end_time"),
                active_filters.get("coverage_end_time"),
                data.get("acquisition_end_time"),
                data.get("window_end_time"),
            )
            if value is not None
        ),
        None,
    )
    start_value = start_value if start_value is not None else contract.get("start_time")
    end_value = end_value if end_value is not None else contract.get("end_time")
    start = _as_timestamp(start_value)
    end = _as_timestamp(end_value, end_boundary=True)
    complete = _metadata_value(metadata, "collection_complete")
    if not isinstance(complete, bool):
        complete = _metadata_value(metadata, "scope_complete")
    stop_reason = _metadata_value(metadata, "stop_reason")
    truncated = bool(_metadata_value(metadata, "truncated_by_max_reviews"))
    coverage_status = (
        data.get("coverage_status")
        or acquisition_coverage.get("status")
        or provenance.get("coverage_status")
        or nested_coverage.get("status")
        or active_filters.get("coverage_status")
    )
    if coverage_status == "incomplete":
        complete = False
    elif coverage_status == "unknown":
        complete = None
    if truncated or stop_reason == "max_reviews_reached":
        complete = False
    reason = None
    if complete is False:
        reason = "acquisition_incomplete"
    elif complete is None:
        reason = "acquisition_provenance_unknown"
    elif start is None or end is None:
        reason = "acquisition_temporal_coverage_unknown"
    if complete is not True:
        # Requested contract bounds are not acquisition evidence after an
        # incomplete/truncated/unknown run.  Only a future explicit partial
        # coverage provenance record may safely provide a narrower interval.
        return None, None, complete, reason
    return start, end, complete, reason


def _normalise_windows(windows_days: Iterable[int | float]) -> list[int]:
    values: set[int] = set()
    for value in windows_days:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("window days must be positive numbers") from exc
        if not isfinite(number) or number <= 0 or not number.is_integer():
            raise ValueError("window days must be positive whole numbers")
        values.add(int(number))
    if not values:
        raise ValueError("at least one matched lifecycle window is required")
    return sorted(values)


def _slice_population(
    population: list[Mapping[str, Any]],
    anchor: float,
    window_days: int,
) -> tuple[list[Mapping[str, Any]], int, list[Any], float, float]:
    start = anchor
    end = anchor + window_days * _DAY_SECONDS
    selected: list[Mapping[str, Any]] = []
    missing_timestamp_n = 0
    for row in population:
        timestamp = _as_timestamp(row.get("timestamp_created"))
        if timestamp is None:
            missing_timestamp_n += 1
        elif start <= timestamp < end:
            selected.append(row)
    review_ids = [row.get("recommendationid") for row in selected]
    return selected, missing_timestamp_n, review_ids, start, end


def _coverage_for_window(metadata: Any, start: float, end: float) -> dict[str, Any]:
    source_start, source_end, complete, reason = _coverage_bounds(metadata)
    sufficient = bool(
        complete is True
        and source_start is not None
        and source_end is not None
        and source_start <= start + _FLOAT_TOLERANCE
        and source_end >= end - _FLOAT_TOLERANCE
    )
    if sufficient:
        status = "complete"
        reason = None
    else:
        status = "incomplete_coverage"
        if reason is None:
            if source_start is not None and source_start > start:
                reason = "source_starts_after_requested_window"
            elif source_end is not None and source_end < end:
                reason = "source_ends_before_requested_window"
            else:
                reason = "insufficient_temporal_coverage"
    return {
        "status": status,
        "sufficient": sufficient,
        "source_start_time": source_start,
        "source_end_time": source_end,
        "required_start_time": start,
        "required_end_time": end,
        "reason": reason,
    }


def _window_metadata(metadata: Any, coverage: Mapping[str, Any], window_days: int) -> dict[str, Any]:
    result = dict(_metadata_mapping(metadata))
    result["window_start"] = coverage["required_start_time"]
    result["window_end"] = coverage["required_end_time"]
    result["coverage_start_time"] = coverage["required_start_time"] if coverage["sufficient"] else None
    result["coverage_end_time"] = coverage["required_end_time"] if coverage["sufficient"] else None
    result["coverage_status"] = "complete" if coverage["sufficient"] else "incomplete"
    result["coverage_end_inclusive"] = False
    result["acquisition_coverage"] = {
        "start_time": result["coverage_start_time"],
        "end_time": result["coverage_end_time"],
        "status": result["coverage_status"],
        "end_inclusive": False,
    }
    result["window_days"] = window_days
    result["collection_complete"] = bool(coverage["sufficient"])
    result["truncated_by_max_reviews"] = False
    result["stop_reason"] = "end_of_results" if coverage["sufficient"] else coverage["reason"]
    return result


def _event_windows(events: Iterable[Mapping[str, Any]], side: str, start: float, end: float) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping) or event.get("side") != side:
            continue
        timestamp = _as_timestamp(event.get("timestamp"))
        if timestamp is not None and start <= timestamp < end:
            selected.append(dict(event))
    selected.sort(key=lambda event: (float(_as_timestamp(event.get("timestamp")) or 0), str(event.get("type", "")), str(event.get("label", ""))))
    return selected


def _sign(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    if abs(value) <= _FLOAT_TOLERANCE:
        return "zero"
    return "positive" if value > 0 else "negative"


def _robustness_summary(deltas: Mapping[str, Optional[float]], windows: list[int]) -> dict[str, Any]:
    usable = [(window, deltas.get(str(window))) for window in windows if deltas.get(str(window)) is not None]
    values = [float(value) for _, value in usable]
    directions = [_sign(value) for _, value in usable]
    non_null_directions = [value for value in directions if value is not None]
    unique_directions = set(non_null_directions)
    reversal = "positive" in unique_directions and "negative" in unique_directions
    reversal_windows = [window for window, value in usable if reversal and _sign(value) in {"positive", "negative"}]
    adjacent_changes = [
        abs(values[index] - values[index - 1])
        for index in range(1, len(values))
    ]
    delta_min = min(values) if values else None
    delta_max = max(values) if values else None
    delta_range = delta_max - delta_min if values else None
    return {
        "deltas": {str(window): deltas.get(str(window)) for window in windows},
        "direction_consistent": len(unique_directions) <= 1 if values else None,
        "direction_reversal": reversal if values else None,
        "direction_reversal_windows": reversal_windows,
        "min": delta_min,
        "max": delta_max,
        "range": delta_range,
        "range_percentage_points": delta_range * 100.0 if delta_range is not None else None,
        "largest_window_to_window_change": max(adjacent_changes) if adjacent_changes else None,
        "largest_window_to_window_change_percentage_points": max(adjacent_changes) * 100.0 if adjacent_changes else None,
        "valid_window_count": len(values),
    }


def _heuristic(raw: Mapping[str, Any]) -> str:
    if raw.get("direction_reversal") or raw.get("range") is None:
        return "high" if raw.get("direction_reversal") else "unknown"
    if raw["range"] <= WINDOW_SENSITIVITY_THRESHOLDS["stable_max_range"]:
        return "stable"
    if raw["range"] <= WINDOW_SENSITIVITY_THRESHOLDS["moderate_max_range"]:
        return "moderate"
    return "high"


def matched_window_robustness(
    reference_population: Iterable[Mapping[str, Any]],
    comparison_population: Iterable[Mapping[str, Any]],
    reference_anchor: Any,
    comparison_anchor: Any,
    *,
    reference_metadata: Any = None,
    comparison_metadata: Any = None,
    comparability_report: Any = None,
    windows_days: Iterable[int | float] = DEFAULT_WINDOWS_DAYS,
    standardization_variables: Optional[Iterable[str]] = None,
    standardization_target: str = "reference",
    confidence_level: float = 0.95,
    events: Optional[Iterable[Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    """Compare equal lifecycle windows anchored to two release timestamps."""
    reference_anchor_timestamp = _as_timestamp(reference_anchor)
    comparison_anchor_timestamp = _as_timestamp(comparison_anchor)
    if reference_anchor_timestamp is None or comparison_anchor_timestamp is None:
        raise ValueError("reference_anchor and comparison_anchor must be valid timestamps")
    windows = _normalise_windows(windows_days)
    reference = [dict(row) for row in reference_population]
    comparison = [dict(row) for row in comparison_population]
    event_rows = [dict(event) for event in (events or []) if isinstance(event, Mapping)]
    standardization_variables_list = list(standardization_variables) if standardization_variables is not None else None
    standardization_requested = bool(standardization_variables_list)
    raw_deltas: dict[str, Optional[float]] = {}
    standardized_deltas: dict[str, Optional[float]] = {}
    window_reports: dict[str, dict[str, Any]] = {}

    for window_days in windows:
        reference_subset, reference_missing_timestamps, reference_ids, reference_start, reference_end = _slice_population(reference, reference_anchor_timestamp, window_days)
        comparison_subset, comparison_missing_timestamps, comparison_ids, comparison_start, comparison_end = _slice_population(comparison, comparison_anchor_timestamp, window_days)
        reference_coverage = _coverage_for_window(reference_metadata, reference_start, reference_end)
        comparison_coverage = _coverage_for_window(comparison_metadata, comparison_start, comparison_end)
        reference_window_metadata = _window_metadata(reference_metadata, reference_coverage, window_days)
        comparison_window_metadata = _window_metadata(comparison_metadata, comparison_coverage, window_days)

        population_comparability = compare_populations(
            reference_subset,
            comparison_subset,
            reference_metadata=reference_window_metadata,
            comparison_metadata=comparison_window_metadata,
        )
        recommendation_report = compare_recommendation_rates(
            reference_subset,
            comparison_subset,
            reference_metadata=reference_window_metadata,
            comparison_metadata=comparison_window_metadata,
            confidence_level=confidence_level,
        )
        recommendation_difference = recommendation_report["difference"]
        raw_difference = recommendation_difference.get("difference")
        standardization_report = None
        if standardization_requested:
            standardization_report = standardize_populations(
                reference_subset,
                comparison_subset,
                reference_metadata=reference_window_metadata,
                comparison_metadata=comparison_window_metadata,
                comparability_report=population_comparability,
                variables=standardization_variables_list,
                target=standardization_target,
            )

        if reference_coverage["status"] != "complete" or comparison_coverage["status"] != "complete":
            window_status = "incomplete_coverage"
        elif raw_difference is None:
            window_status = "insufficient_outcome_data"
        else:
            window_status = "complete"
        raw_deltas[str(window_days)] = raw_difference if window_status == "complete" else None
        standardized_deltas[str(window_days)] = (
            standardization_report["standardization"]["standardized_difference"]
            if window_status == "complete" and standardization_report is not None
            else None
        )
        reference_events = _event_windows(event_rows, "reference", reference_start, reference_end)
        comparison_events = _event_windows(event_rows, "comparison", comparison_start, comparison_end)
        window_reports[str(window_days)] = {
            "window_days": window_days,
            "status": window_status,
            "window_status": window_status,
            "reference_population": {
                "start_time": reference_start,
                "end_time": reference_end,
                "review_count": len(reference_subset),
                "review_ids": reference_ids,
                "missing_timestamp_n": reference_missing_timestamps,
                "coverage": reference_coverage,
            },
            "comparison_population": {
                "start_time": comparison_start,
                "end_time": comparison_end,
                "review_count": len(comparison_subset),
                "review_ids": comparison_ids,
                "missing_timestamp_n": comparison_missing_timestamps,
                "coverage": comparison_coverage,
            },
            "comparability": {
                "composition_comparability": population_comparability["composition_comparability"],
                "acquisition_validity": population_comparability["acquisition_validity"],
                "review_activity": population_comparability["review_activity"],
            },
            "recommendation": {
                "reference_rate": recommendation_report["reference"]["recommendation_rate"],
                "comparison_rate": recommendation_report["comparison"]["recommendation_rate"],
                "raw_difference": raw_difference,
                "difference_percentage_points": recommendation_difference.get("difference_percentage_points"),
                "reference_wilson_interval": recommendation_report["reference_model_based_interval"],
                "comparison_wilson_interval": recommendation_report["comparison_model_based_interval"],
                "newcombe_difference_interval": recommendation_difference,
                "interval_contains_zero": recommendation_difference.get("interval_contains_zero"),
            },
            "standardization": (
                {
                    "variables": standardization_report["standardization"]["variables"],
                    "target": standardization_report["standardization"]["target"],
                    "raw_difference": standardization_report["raw"]["difference"],
                    "reference_standardized_rate": standardization_report["standardization"]["reference_standardized_rate"],
                    "comparison_standardized_rate": standardization_report["standardization"]["comparison_standardized_rate"],
                    "standardized_difference": standardization_report["standardization"]["standardized_difference"],
                    "composition_standardization_shift": standardization_report["standardization"]["composition_standardization_shift"],
                    "support_status": standardization_report["standardization"]["status"],
                    "standardized_interval": standardization_report["standardized_interval"],
                }
                if standardization_report is not None
                else None
            ),
            "events": {
                "reference": {"events_inside_window": reference_events, "event_count": len(reference_events)},
                "comparison": {"events_inside_window": comparison_events, "event_count": len(comparison_events)},
            },
        }

    raw_summary = _robustness_summary(raw_deltas, windows)
    standardized_summary = _robustness_summary(standardized_deltas, windows) if standardization_requested else None
    return {
        "schema_version": _SCHEMA_VERSION,
        "anchors": {"reference": reference_anchor_timestamp, "comparison": comparison_anchor_timestamp},
        "window_definition": "anchor <= timestamp_created < anchor + window_days * 86400",
        "requested_windows_days": windows,
        "configuration": {
            "confidence_level": confidence_level,
            "standardization_variables": list(standardization_variables_list) if standardization_variables_list is not None else None,
            "standardization_target": standardization_target,
        },
        "reference_missing_timestamp_n": sum(_as_timestamp(row.get("timestamp_created")) is None for row in reference),
        "comparison_missing_timestamp_n": sum(_as_timestamp(row.get("timestamp_created")) is None for row in comparison),
        "windows": window_reports,
        "robustness": {
            "valid_window_count": raw_summary["valid_window_count"],
            "raw": {
                "direction_consistent": raw_summary["direction_consistent"],
                "direction_reversal": raw_summary["direction_reversal"],
                "deltas": raw_summary["deltas"],
                "raw_delta_by_window": raw_summary["deltas"],
                "min": raw_summary["min"],
                "max": raw_summary["max"],
                "range": raw_summary["range"],
                "raw_delta_min": raw_summary["min"],
                "raw_delta_max": raw_summary["max"],
                "raw_delta_range": raw_summary["range"],
                "range_percentage_points": raw_summary["range_percentage_points"],
                "largest_window_to_window_change": raw_summary["largest_window_to_window_change"],
                "largest_window_to_window_change_percentage_points": raw_summary["largest_window_to_window_change_percentage_points"],
                "direction_reversal_windows": raw_summary["direction_reversal_windows"],
            },
            "standardized": (
                {
                    **standardized_summary,
                    "standardized_delta_by_window": standardized_summary["deltas"],
                    "standardized_delta_min": standardized_summary["min"],
                    "standardized_delta_max": standardized_summary["max"],
                    "standardized_delta_range": standardized_summary["range"],
                }
                if standardized_summary is not None
                else None
            ),
            "raw_direction_consistent": raw_summary["direction_consistent"],
            "standardized_direction_consistent": standardized_summary["direction_consistent"] if standardized_summary is not None else None,
            "heuristic": {
                "window_sensitivity": _heuristic(raw_summary),
                "thresholds": WINDOW_SENSITIVITY_THRESHOLDS,
                "threshold_semantics": "heuristic based on raw delta range, not statistical significance",
            },
        },
        "limitations": {
            "observational_comparison": True,
            "reviewer_selection_bias": True,
            "matched_windows_do_not_establish_causality": True,
            "longer_windows_are_not_automatically_better": True,
            "standardized_uncertainty_not_implemented": standardization_requested,
            "limitation": "Matched lifecycle windows are sensitivity specifications and do not establish a causal version effect.",
        },
    }


build_window_robustness_report = matched_window_robustness


__all__ = [
    "DEFAULT_WINDOWS_DAYS",
    "WINDOW_SENSITIVITY_THRESHOLDS",
    "build_window_robustness_report",
    "matched_window_robustness",
]
