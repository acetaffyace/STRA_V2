"""Deterministic diagnostics for comparing two Steam review populations.

This module describes population composition and acquisition validity only.  It
does not use recommendation outcomes to decide comparability and it does not
perform weighting, significance testing, or causal adjustment.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from math import isfinite
import re
from typing import Any, Iterable, Mapping, Optional


# One centralized, descriptive cohort definition.  Steam playtime fields are
# minutes; reports expose hours so these labels remain readable.
PLAYTIME_COHORTS = (
    ("0–2h", 0.0, 2.0),
    ("2–10h", 2.0, 10.0),
    ("10–30h", 10.0, 30.0),
    ("30–100h", 30.0, 100.0),
    ("100h+", 100.0, None),
)


# These are interpretation heuristics, not statistical significance thresholds.
# Keep all heuristic cutoffs in one place so future methodology work can review
# them without hunting through dimension-specific code.
COMPARABILITY_THRESHOLDS = {
    "language_tvd": {"moderate_shift": 0.10, "large_shift": 0.25},
    "playtime_tvd": {"moderate_shift": 0.10, "large_shift": 0.25},
    "percentage_point_difference": {"moderate_shift": 0.10, "large_shift": 0.25},
    "missingness_difference": {"moderate_shift": 0.10, "large_shift": 0.25},
    "review_rate_relative_difference": {"moderate_shift": 0.25, "large_shift": 1.00},
}


REVIEWER_SELECTION_LIMITATION = (
    "Steam reviews represent self-selected reviewers, not all players. "
    "STRA cannot infer the characteristics or opinions of players who did not write reviews."
)

_METADATA_FIELDS = (
    ("purchase_source", "steam_purchase"),
    ("free_copy", "received_for_free"),
    ("early_access", "written_during_early_access"),
    ("steam_deck", "primarily_steam_deck"),
)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _as_number(value: Any) -> Optional[float]:
    if _is_missing(value) or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _review_value(review: Mapping[str, Any], key: str) -> Any:
    """Read raw fields and the normalized top-level aliases used by STRA."""
    if key in review:
        return review.get(key)
    if key.startswith("author."):
        author = review.get("author")
        if isinstance(author, Mapping):
            return author.get(key.split(".", 1)[1])
        alias = "author_" + key.split(".", 1)[1]
        return review.get(alias)
    return review.get(key)


_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_temporal_bound(value: Any) -> Optional[dict[str, Any]]:
    """Parse a bound without discarding timestamp precision.

    The returned ``kind`` is ``timestamp`` for elapsed-time semantics and
    ``calendar_date`` for legacy date-only metadata.  Naive datetimes are
    interpreted as UTC, matching the rest of the provenance model.
    """
    if isinstance(value, datetime):
        current = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return {"kind": "timestamp", "seconds": float(current.astimezone(timezone.utc).timestamp())}
    if isinstance(value, date):
        current = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        return {"kind": "calendar_date", "seconds": float(current.timestamp())}
    number = _as_number(value)
    if number is not None:
        return {"kind": "timestamp", "seconds": number}
    if isinstance(value, str):
        text = value.strip()
        if _DATE_ONLY_RE.fullmatch(text):
            try:
                current = date.fromisoformat(text)
            except ValueError:
                return None
            return {
                "kind": "calendar_date",
                "seconds": float(datetime(current.year, current.month, current.day, tzinfo=timezone.utc).timestamp()),
            }
        try:
            normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
            current = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return {"kind": "timestamp", "seconds": float(current.astimezone(timezone.utc).timestamp())}
    return None


def _format_temporal_bound(bound: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not bound:
        return None
    seconds = float(bound["seconds"])
    if bound.get("kind") == "calendar_date":
        return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _metadata_value(metadata: Mapping[str, Any], key: str) -> Any:
    value = metadata.get(key)
    if value is not None:
        return value
    for container_key in ("active_filters", "population_provenance", "acquisition_coverage"):
        container = metadata.get(container_key)
        if isinstance(container, Mapping) and container.get(key) is not None:
            return container.get(key)
    return None


def _temporal_pair(metadata: Mapping[str, Any], start_key: str, end_key: str) -> tuple[Any, Any]:
    return _metadata_value(metadata, start_key), _metadata_value(metadata, end_key)


def _window_duration(metadata: Mapping[str, Any]) -> tuple[Optional[float], Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Return explicit or safely inferred duration and its parsed bounds.

    Preference order is explicit ``window_days``, exact timestamp bounds with
    known semantics, then legacy inclusive calendar-date bounds.  Observed
    review timestamps are never used as an exposure-duration fallback.
    """
    candidates: list[tuple[str, Any, Any]] = [
        ("coverage", *_temporal_pair(metadata, "coverage_start_time", "coverage_end_time")),
        ("window", *_temporal_pair(metadata, "window_start", "window_end")),
    ]
    contract = metadata.get("sampling_contract")
    if isinstance(contract, Mapping):
        candidates.append(("contract", contract.get("start_time"), contract.get("end_time")))

    explicit_days = _as_number(_metadata_value(metadata, "window_days"))
    if explicit_days is not None and explicit_days > 0:
        for _, start_value, end_value in candidates:
            start = _parse_temporal_bound(start_value) if start_value is not None else None
            end = _parse_temporal_bound(end_value) if end_value is not None else None
            if start is not None and end is not None and end["seconds"] >= start["seconds"]:
                return float(explicit_days), start, end
        return float(explicit_days), None, None

    for source, start_value, end_value in candidates:
        if start_value is None or end_value is None:
            continue
        start = _parse_temporal_bound(start_value)
        end = _parse_temporal_bound(end_value)
        if start is None or end is None or end["seconds"] < start["seconds"]:
            continue
        end_inclusive = _metadata_value(metadata, "coverage_end_inclusive") if source == "coverage" else _metadata_value(metadata, "window_end_inclusive") if source == "window" else True
        if source == "window" and start["kind"] == "calendar_date" and end["kind"] == "calendar_date" and end_inclusive is not False:
            # Date-only window_start/window_end is the explicitly retained
            # legacy inclusive-calendar-date representation.
            return float((end["seconds"] - start["seconds"]) / 86400.0 + 1.0), start, end
        if start["kind"] == "timestamp" and end["kind"] == "timestamp" and isinstance(end_inclusive, bool):
            # Timestamp endpoints have zero measure; inclusive versus
            # exclusive changes event selection, not elapsed exposure time.
            return float((end["seconds"] - start["seconds"]) / 86400.0), start, end
    return None, None, None


def _requested_languages(metadata: Mapping[str, Any], population: list[Mapping[str, Any]]) -> list[str]:
    contract = metadata.get("sampling_contract")
    languages: Any = contract.get("languages") if isinstance(contract, Mapping) else None
    languages = languages or metadata.get("requested_languages") or metadata.get("languages")
    if isinstance(languages, str):
        languages = [languages]
    if not languages:
        languages = sorted({str(_review_value(row, "language")).strip().lower() for row in population if not _is_missing(_review_value(row, "language"))})
    return [str(language).strip().lower() for language in languages if not _is_missing(language)]


def _acquisition_summary(population: list[Mapping[str, Any]], metadata: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if metadata is not None and not isinstance(metadata, Mapping) and hasattr(metadata, "model_dump"):
        metadata = metadata.model_dump(mode="json")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    window_days, start_bound, end_bound = _window_duration(metadata)

    contract_complete = _metadata_value(metadata, "collection_complete")
    if contract_complete is None:
        contract_complete = _metadata_value(metadata, "scope_complete")
    collection_complete = contract_complete if isinstance(contract_complete, bool) else None
    truncated = _metadata_value(metadata, "truncated_by_max_reviews")
    truncated = bool(truncated) if truncated is not None else False
    stop_reason = _metadata_value(metadata, "stop_reason")
    language_stats = _metadata_value(metadata, "language_stats")
    if not isinstance(language_stats, Mapping):
        language_stats = {}

    requested = _requested_languages(metadata, population)
    explicit_successful = _metadata_value(metadata, "successful_languages")
    explicit_failed = _metadata_value(metadata, "failed_languages")
    if isinstance(explicit_successful, str):
        explicit_successful = [explicit_successful]
    if isinstance(explicit_failed, str):
        explicit_failed = [explicit_failed]
    if isinstance(explicit_successful, list):
        successful = [str(language).strip().lower() for language in explicit_successful if not _is_missing(language)]
    else:
        successful = []
    if isinstance(explicit_failed, list):
        failed = [str(language).strip().lower() for language in explicit_failed if not _is_missing(language)]
    else:
        failed = []
    incomplete: list[str] = []
    for language in requested:
        status = language_stats.get(language)
        if isinstance(status, Mapping):
            if status.get("status") == "complete" or status.get("collection_complete") is True:
                successful.append(language)
            elif status.get("status") == "failed":
                failed.append(language)
            else:
                incomplete.append(language)
    if requested and not language_stats and collection_complete is True:
        successful = list(requested)

    return {
        "population_count": len(population),
        "window_start": _format_temporal_bound(start_bound),
        "window_end": _format_temporal_bound(end_bound),
        "coverage_start_time": _metadata_value(metadata, "coverage_start_time"),
        "coverage_end_time": _metadata_value(metadata, "coverage_end_time"),
        "coverage_status": _metadata_value(metadata, "coverage_status"),
        "coverage_end_inclusive": _metadata_value(metadata, "coverage_end_inclusive"),
        "observed_review_start_time": _metadata_value(metadata, "observed_review_start_time"),
        "observed_review_end_time": _metadata_value(metadata, "observed_review_end_time"),
        "window_days": int(window_days) if window_days is not None and window_days.is_integer() else window_days,
        "collection_complete": collection_complete,
        "truncated_by_max_reviews": truncated,
        "stop_reason": stop_reason,
        "requested_languages": requested,
        "successful_languages": sorted(set(successful)),
        "failed_languages": sorted(set(failed)),
        "incomplete_languages": sorted(set(incomplete)),
        "language_stats": {str(key): dict(value) for key, value in sorted(language_stats.items()) if isinstance(value, Mapping)},
    }


def _distribution(values: Iterable[str]) -> dict[str, float]:
    counts: dict[str, int] = {}
    total = 0
    for value in values:
        key = str(value).strip().lower()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        total += 1
    if total == 0:
        return {}
    return {key: counts[key] / total for key in sorted(counts)}


def _coverage(valid_n: int, population_count: int) -> Optional[float]:
    return valid_n / population_count if population_count else None


def _observability(valid_a: int, valid_b: int) -> tuple[str, Optional[str]]:
    if valid_a == 0 and valid_b == 0:
        return "none", "insufficient_observed_data"
    if valid_a == 0 or valid_b == 0:
        return "partial", "insufficient_observed_data"
    return "both", None


def _tvd(a: Optional[Mapping[str, float]], b: Optional[Mapping[str, float]]) -> Optional[float]:
    if a is None or b is None or (not a and not b):
        return None
    keys = set(a) | set(b)
    return 0.5 * sum(abs(float(a.get(key, 0.0)) - float(b.get(key, 0.0))) for key in keys)


def _level_from_shift(shift: Optional[float], threshold_key: str) -> str:
    if shift is None:
        return "unknown"
    thresholds = COMPARABILITY_THRESHOLDS[threshold_key]
    if shift <= thresholds["moderate_shift"]:
        return "high"
    if shift <= thresholds["large_shift"]:
        return "moderate"
    return "low"


def _language_dimension(a: list[Mapping[str, Any]], b: list[Mapping[str, Any]]) -> dict[str, Any]:
    values_a = [_review_value(row, "language") for row in a if not _is_missing(_review_value(row, "language"))]
    values_b = [_review_value(row, "language") for row in b if not _is_missing(_review_value(row, "language"))]
    valid_a, valid_b = len(values_a), len(values_b)
    distribution_a = _distribution(values_a) if valid_a else None
    distribution_b = _distribution(values_b) if valid_b else None
    distance = _tvd(distribution_a, distribution_b)
    observability, reason = _observability(valid_a, valid_b)
    return {
        "reference_distribution": distribution_a,
        "comparison_distribution": distribution_b,
        "reference": {
            "valid_n": valid_a,
            "missing_n": len(a) - valid_a,
            "coverage": _coverage(valid_a, len(a)),
        },
        "comparison": {
            "valid_n": valid_b,
            "missing_n": len(b) - valid_b,
            "coverage": _coverage(valid_b, len(b)),
        },
        "total_variation_distance": distance,
        "distance": distance,
        "observability": observability,
        "reason": reason,
        "level": _level_from_shift(distance, "language_tvd") if reason is None else "unknown",
    }


def _playtime_value(row: Mapping[str, Any]) -> Optional[float]:
    value = _review_value(row, "author.playtime_at_review")
    number = _as_number(value)
    return number / 60.0 if number is not None and number >= 0 else None


def _quantiles(values: list[float]) -> dict[str, Optional[float]]:
    if not values:
        return {"median": None, "p25": None, "p75": None}
    values = sorted(values)
    def percentile(q: float) -> float:
        position = (len(values) - 1) * q
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        weight = position - lower
        return values[lower] * (1 - weight) + values[upper] * weight
    return {"median": percentile(0.5), "p25": percentile(0.25), "p75": percentile(0.75)}


def _playtime_dimension(a: list[Mapping[str, Any]], b: list[Mapping[str, Any]]) -> dict[str, Any]:
    values = {
        "reference": [value for row in a if (value := _playtime_value(row)) is not None],
        "comparison": [value for row in b if (value := _playtime_value(row)) is not None],
    }
    shares: dict[str, Optional[dict[str, float]]] = {}
    for key, cohort_values in values.items():
        counts = {label: 0 for label, _, _ in PLAYTIME_COHORTS}
        for value in cohort_values:
            for label, lower, upper in PLAYTIME_COHORTS:
                if value >= lower and (upper is None or value < upper):
                    counts[label] += 1
                    break
        denominator = len(cohort_values)
        shares[key] = (
            {label: count / denominator for label, count in counts.items()}
            if denominator
            else None
        )
    distance = _tvd(shares["reference"], shares["comparison"])
    observability, reason = _observability(len(values["reference"]), len(values["comparison"]))
    return {
        "source_field": "author.playtime_at_review",
        "source_unit": "minutes",
        "reported_unit": "hours",
        "reference": {
            "valid_n": len(values["reference"]),
            "missing_n": len(a) - len(values["reference"]),
            "coverage": _coverage(len(values["reference"]), len(a)),
            **_quantiles(values["reference"]),
        },
        "comparison": {
            "valid_n": len(values["comparison"]),
            "missing_n": len(b) - len(values["comparison"]),
            "coverage": _coverage(len(values["comparison"]), len(b)),
            **_quantiles(values["comparison"]),
        },
        "cohort_definition": [label for label, _, _ in PLAYTIME_COHORTS],
        "reference_cohort_share": shares["reference"],
        "comparison_cohort_share": shares["comparison"],
        "composition_distance": distance,
        "distance": distance,
        "observability": observability,
        "reason": reason,
        "level": _level_from_shift(distance, "playtime_tvd") if reason is None else "unknown",
    }


def _boolean_dimension(a: list[Mapping[str, Any]], b: list[Mapping[str, Any]], field: str) -> dict[str, Any]:
    def summarize(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
        values = [_as_bool(_review_value(row, field)) for row in rows]
        valid = [value for value in values if value is not None]
        true_share = sum(value is True for value in valid) / len(valid) if valid else None
        false_share = sum(value is False for value in valid) / len(valid) if valid else None
        return {
            "valid_n": len(valid),
            "missing_n": len(rows) - len(valid),
            "coverage": _coverage(len(valid), len(rows)),
            "share_true": true_share,
            "share_false": false_share,
        }
    reference = summarize(a)
    comparison = summarize(b)
    difference = (
        abs(reference["share_true"] - comparison["share_true"])
        if reference["share_true"] is not None and comparison["share_true"] is not None
        else None
    )
    observability, reason = _observability(reference["valid_n"], comparison["valid_n"])
    return {
        "field": field,
        "reference": reference,
        "comparison": comparison,
        "absolute_percentage_point_difference": difference,
        "observability": observability,
        "reason": reason,
        "level": _level_from_shift(difference, "percentage_point_difference") if reason is None else "unknown",
    }


def _missingness_dimension(a: list[Mapping[str, Any]], b: list[Mapping[str, Any]]) -> dict[str, Any]:
    fields = [
        ("language", "language"),
        ("playtime_at_review", "author.playtime_at_review"),
        *[(field, field) for _, field in _METADATA_FIELDS],
    ]
    reference: dict[str, float] = {}
    comparison: dict[str, float] = {}
    differences: dict[str, Optional[float]] = {}
    warnings: list[str] = []
    for output_field, source_field in fields:
        rate_a = sum(_is_missing(_review_value(row, source_field)) or (source_field == "author.playtime_at_review" and _playtime_value(row) is None) or (source_field != "author.playtime_at_review" and source_field != "language" and _as_bool(_review_value(row, source_field)) is None) for row in a) / len(a) if a else None
        rate_b = sum(_is_missing(_review_value(row, source_field)) or (source_field == "author.playtime_at_review" and _playtime_value(row) is None) or (source_field != "author.playtime_at_review" and source_field != "language" and _as_bool(_review_value(row, source_field)) is None) for row in b) / len(b) if b else None
        reference[output_field] = rate_a if rate_a is not None else 0.0
        comparison[output_field] = rate_b if rate_b is not None else 0.0
        differences[output_field] = abs(rate_a - rate_b) if rate_a is not None and rate_b is not None else None
        if differences[output_field] is not None and differences[output_field] > COMPARABILITY_THRESHOLDS["missingness_difference"]["moderate_shift"]:
            warnings.append(output_field)
    max_difference = max((value for value in differences.values() if value is not None), default=None)
    missingness_level = _level_from_shift(max_difference, "missingness_difference")
    # This is a shift in missingness, not a claim that the underlying field is
    # observable. Two entirely missing fields can have zero missingness shift.
    shift_level = (
        "unknown"
        if max_difference is None
        else "low"
        if max_difference <= COMPARABILITY_THRESHOLDS["missingness_difference"]["moderate_shift"]
        else "moderate"
        if max_difference <= COMPARABILITY_THRESHOLDS["missingness_difference"]["large_shift"]
        else "large"
    )
    return {
        "reference_missing_rate": reference,
        "comparison_missing_rate": comparison,
        "absolute_difference": differences,
        "warning_fields": sorted(warnings),
        "level": missingness_level,
        "missingness_shift": shift_level,
        "shift_level": shift_level,
    }


def _volume_dimension(acquisition_a: Mapping[str, Any], acquisition_b: Mapping[str, Any]) -> dict[str, Any]:
    count_a = int(acquisition_a["population_count"])
    count_b = int(acquisition_b["population_count"])
    days_a = acquisition_a.get("window_days")
    days_b = acquisition_b.get("window_days")
    rate_a = count_a / float(days_a) if days_a and float(days_a) > 0 else None
    rate_b = count_b / float(days_b) if days_b and float(days_b) > 0 else None
    ratio = rate_b / rate_a if rate_a and rate_b is not None else None
    relative_difference = max(ratio, 1 / ratio) - 1 if ratio and ratio > 0 else None
    level = _level_from_shift(relative_difference, "review_rate_relative_difference")
    shift_level = (
        "unknown"
        if relative_difference is None
        else "low"
        if relative_difference <= COMPARABILITY_THRESHOLDS["review_rate_relative_difference"]["moderate_shift"]
        else "moderate"
        if relative_difference <= COMPARABILITY_THRESHOLDS["review_rate_relative_difference"]["large_shift"]
        else "large"
    )
    return {
        "reference": {"review_count": count_a, "window_days": days_a, "reviews_per_day": rate_a},
        "comparison": {"review_count": count_b, "window_days": days_b, "reviews_per_day": rate_b},
        "absolute_volume_difference": abs(count_b - count_a),
        "reviews_per_day_ratio": ratio,
        "relative_rate_difference": relative_difference,
        "activity_shift": shift_level,
        "shift_level": shift_level,
        "level": level,
    }


def _aggregate_composition_level(dimensions: Mapping[str, Mapping[str, Any]]) -> tuple[str, list[str]]:
    """Aggregate only observed composition dimensions.

    Unknown/partial optional fields are surfaced to callers but do not become
    evidence of a composition shift. A composition claim is unknown only when
    no composition dimension has usable observations in both populations.
    """
    levels = {name: value.get("level", "unknown") for name, value in dimensions.items()}
    observed = {name: level for name, level in levels.items() if level != "unknown"}
    unknown = sorted(name for name, level in levels.items() if level == "unknown")
    if not observed:
        return "unknown", unknown
    if any(level == "low" for level in observed.values()):
        return "low", unknown
    if any(level == "moderate" for level in observed.values()):
        return "moderate", unknown
    return "high", unknown


def compare_populations(
    reference_population: Iterable[Mapping[str, Any]],
    comparison_population: Iterable[Mapping[str, Any]],
    reference_metadata: Optional[Mapping[str, Any]] = None,
    comparison_metadata: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return a deterministic, JSON-serializable population comparability report."""
    reference = [dict(row) for row in reference_population]
    comparison = [dict(row) for row in comparison_population]
    acquisition = {
        "reference": _acquisition_summary(reference, reference_metadata),
        "comparison": _acquisition_summary(comparison, comparison_metadata),
    }
    warnings: list[str] = []
    for label, summary in acquisition.items():
        if summary["collection_complete"] is False:
            warnings.append(f"{label}_acquisition_incomplete")
        elif summary["collection_complete"] is None:
            warnings.append(f"{label}_acquisition_unknown")
        if summary["failed_languages"]:
            warnings.append(f"{label}_language_acquisition_failed")

    acquisition_validity = {
        "level": (
            "low"
            if any(item["collection_complete"] is False for item in acquisition.values())
            else "unknown"
            if any(item["collection_complete"] is None for item in acquisition.values())
            else "high"
        ),
        "warnings": sorted(set(warnings)),
    }
    review_activity = _volume_dimension(acquisition["reference"], acquisition["comparison"])
    composition_dimensions: dict[str, Any] = {
        "language": _language_dimension(reference, comparison),
        "playtime": _playtime_dimension(reference, comparison),
    }
    for dimension_name, field in _METADATA_FIELDS:
        composition_dimensions[dimension_name] = _boolean_dimension(reference, comparison, field)

    missingness = _missingness_dimension(reference, comparison)
    observability = {
        name: dimension.get("observability", "unknown")
        for name, dimension in composition_dimensions.items()
    }
    data_quality = {
        "missingness": missingness,
        "observability": observability,
        # Backward-compatible alias: this is similarity of missingness
        # patterns, not a claim that the data are complete or high quality.
        "level": missingness["shift_level"],
        "level_semantics": "missingness_pattern_similarity",
        "missingness_shift_level": missingness["shift_level"],
        "coverage_summary": {
            name: {
                "reference": composition_dimensions[name]["reference"].get("coverage"),
                "comparison": composition_dimensions[name]["comparison"].get("coverage"),
            }
            for name in composition_dimensions
        },
        "warnings": ["missingness_shift"] if missingness["warning_fields"] else [],
    }
    composition_level, unknown_composition = _aggregate_composition_level(composition_dimensions)

    # Keep the original dimensions surface for existing API consumers while
    # adding explicit report sections with non-overlapping meanings.
    dimensions: dict[str, Any] = {
        "acquisition": acquisition_validity,
        "review_volume": review_activity,
        "review_activity": review_activity,
        **composition_dimensions,
    }
    dimensions["missingness"] = missingness

    if missingness["warning_fields"]:
        warnings.append("missingness_shift")
    if review_activity["shift_level"] in {"moderate", "large"}:
        warnings.append("review_activity_shift")

    # Acquisition validity gates strong top-level interpretation. Review
    # activity and missingness are reported separately and never downgrade a
    # composition result by themselves.
    acquisition_level = acquisition_validity["level"]
    if acquisition_level == "low":
        overall_level = "low"
    elif acquisition_level == "unknown":
        overall_level = "unknown"
    else:
        overall_level = composition_level

    comparability_dimensions = {
        "acquisition": acquisition_level,
        **{name: value.get("level", "unknown") for name, value in composition_dimensions.items()},
        "review_activity": review_activity["level"],
        "data_quality": data_quality["level"],
    }

    return {
        "schema_version": "population-comparability-v1",
        "acquisition": acquisition,
        "acquisition_validity": acquisition_validity,
        "composition_comparability": {
            "level": composition_level,
            "dimensions": {name: value.get("level", "unknown") for name, value in composition_dimensions.items()},
            "unknown_dimensions": unknown_composition,
            "observability": observability,
        },
        "review_activity": review_activity,
        "data_quality": data_quality,
        "dimensions": dimensions,
        "comparability": {
            "level": overall_level,
            "dimensions": comparability_dimensions,
            "warnings": sorted(set(warnings)),
            "heuristic_thresholds": COMPARABILITY_THRESHOLDS,
        },
        "external_validity": {
            "reviewer_selection_bias": True,
            "limitation": REVIEWER_SELECTION_LIMITATION,
        },
    }


# Descriptive alias for callers that prefer the report-oriented name.
build_population_comparability_report = compare_populations


__all__ = [
    "COMPARABILITY_THRESHOLDS",
    "PLAYTIME_COHORTS",
    "REVIEWER_SELECTION_LIMITATION",
    "build_population_comparability_report",
    "compare_populations",
]
