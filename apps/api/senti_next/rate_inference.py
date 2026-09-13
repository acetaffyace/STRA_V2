"""Recommendation-rate measurement and model-based uncertainty.

The exact rate is descriptive for the reviews STRA actually observed.  The
intervals in this module are conditional on an independent Bernoulli/binomial
process model; they do not correct Steam-reviewer self-selection, composition
imbalance, causal confounding, or non-random truncation.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from statsmodels.stats.proportion import confint_proportions_2indep, proportion_confint


SCHEMA_VERSION = "recommendation-rate-inference-v1"
DEFAULT_CONFIDENCE_LEVEL = 0.95
REVIEWER_SELECTION_LIMITATION = (
    "Steam reviews represent self-selected reviewers, not all players. "
    "Recommendation-rate intervals do not correct reviewer self-selection."
)
MODEL_ASSUMPTIONS = [
    "reviews treated as independent Bernoulli observations",
    "observed reviewers are not assumed representative of all players",
    "interval does not correct self-selection bias",
    "interval does not establish causal version impact",
]


def _clamp_probability(value: float) -> float:
    value = max(0.0, min(1.0, float(value)))
    if value < 1e-15:
        return 0.0
    if value > 1.0 - 1e-15:
        return 1.0
    return value


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"true", "1", "yes"}:
            return True
        if value in {"false", "0", "no"}:
            return False
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, Mapping) else {}
    return {}


def _metadata_value(metadata: Any, key: str) -> Any:
    data = _mapping(metadata)
    if key in data:
        return data[key]
    for container_key in ("population_provenance", "active_filters"):
        container = data.get(container_key)
        if isinstance(container, Mapping) and key in container:
            return container[key]
    return None


def _population_metrics(population: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(population)
    valid = [_as_bool(row.get("voted_up")) for row in rows]
    valid = [value for value in valid if value is not None]
    recommended_n = sum(value is True for value in valid)
    not_recommended_n = sum(value is False for value in valid)
    valid_n = len(valid)
    rate = recommended_n / valid_n if valid_n else None
    return {
        "valid_n": valid_n,
        "recommended_n": recommended_n,
        "not_recommended_n": not_recommended_n,
        "missing_n": len(rows) - valid_n,
        "recommendation_rate": rate,
        "observed_population_metric": True,
    }


def _validate_confidence_level(confidence_level: float) -> tuple[float, float]:
    try:
        confidence_level = float(confidence_level)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence_level must be between 0 and 1") from exc
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between 0 and 1")
    return confidence_level, 1.0 - confidence_level


def _wilson_interval(valid_n: int, recommended_n: int, confidence_level: float) -> dict[str, Any]:
    confidence_level, alpha = _validate_confidence_level(confidence_level)
    estimate = recommended_n / valid_n if valid_n else None
    result: dict[str, Any] = {
        "estimate": estimate,
        "lower": None,
        "upper": None,
        "method": "wilson",
        "confidence_level": confidence_level,
        "alpha": alpha,
        "interval_width": None,
        "assumptions": list(MODEL_ASSUMPTIONS),
    }
    if not valid_n:
        result["unavailable_reason"] = "no_valid_recommendation_observations"
        return result
    lower, upper = proportion_confint(
        count=recommended_n,
        nobs=valid_n,
        alpha=alpha,
        method="wilson",
    )
    lower = _clamp_probability(lower)
    upper = _clamp_probability(upper)
    result["lower"] = lower
    result["upper"] = upper
    result["interval_width"] = upper - lower
    return result


def _difference_interval(
    reference: Mapping[str, Any],
    comparison: Mapping[str, Any],
    confidence_level: float,
) -> dict[str, Any]:
    confidence_level, alpha = _validate_confidence_level(confidence_level)
    reference_rate = reference.get("recommendation_rate")
    comparison_rate = comparison.get("recommendation_rate")
    difference = (
        float(comparison_rate) - float(reference_rate)
        if reference_rate is not None and comparison_rate is not None
        else None
    )
    result: dict[str, Any] = {
        "difference": difference,
        "difference_percentage_points": difference * 100.0 if difference is not None else None,
        "lower": None,
        "upper": None,
        "method": "newcombe",
        "confidence_level": confidence_level,
        "alpha": alpha,
        "interval_width": None,
        "interval_contains_zero": None,
        "assumptions": list(MODEL_ASSUMPTIONS),
        "sign_convention": "comparison - reference",
    }
    if not reference.get("valid_n") or not comparison.get("valid_n"):
        result["unavailable_reason"] = "both_populations_require_valid_recommendation_observations"
        return result

    # statsmodels defines the difference as count1/nobs1 - count2/nobs2.
    # Pass comparison first so STRA's public contract remains comparison minus
    # reference, including the interval endpoints.
    lower, upper = confint_proportions_2indep(
        count1=int(comparison["recommended_n"]),
        nobs1=int(comparison["valid_n"]),
        count2=int(reference["recommended_n"]),
        nobs2=int(reference["valid_n"]),
        compare="diff",
        method="newcomb",
        alpha=alpha,
    )
    lower = max(-1.0, min(1.0, float(lower)))
    upper = max(-1.0, min(1.0, float(upper)))
    result["lower"] = lower
    result["upper"] = upper
    result["interval_width"] = upper - lower
    result["interval_contains_zero"] = bool(lower <= 0 <= upper)
    return result


def _inference_validity(metadata: Any) -> dict[str, Any]:
    collection_complete = _metadata_value(metadata, "collection_complete")
    if not isinstance(collection_complete, bool):
        collection_complete = _metadata_value(metadata, "scope_complete")
    if not isinstance(collection_complete, bool):
        collection_complete = None
    truncated = _metadata_value(metadata, "truncated_by_max_reviews")
    truncated = bool(truncated) if truncated is not None else False
    stop_reason = _metadata_value(metadata, "stop_reason")
    chronological_truncation = truncated or stop_reason == "max_reviews_reached"

    if chronological_truncation:
        eligibility = "limited"
        reason = "non_random_chronological_truncation"
    elif collection_complete is True:
        eligibility = "model_based_only"
        reason = "complete_requested_population"
    elif collection_complete is False:
        eligibility = "limited"
        reason = "incomplete_acquisition"
    else:
        eligibility = "unknown"
        reason = "acquisition_provenance_unknown"

    return {
        "acquisition_complete": collection_complete,
        "truncated_by_max_reviews": truncated,
        "stop_reason": stop_reason,
        "inference_eligibility": eligibility,
        "reason": reason,
        "observed_metric_status": (
            "exact_for_observed_population"
            if collection_complete is True and not chronological_truncation
            else "exact_for_observed_reviews"
        ),
        "model_based_interval_status": "assumption_sensitive_not_design_based",
    }


def _comparison_context(comparability_report: Any) -> dict[str, Any]:
    report = _mapping(comparability_report)
    acquisition = report.get("acquisition_validity")
    if not isinstance(acquisition, Mapping):
        dimensions = report.get("dimensions")
        acquisition = dimensions.get("acquisition") if isinstance(dimensions, Mapping) else None
    composition = report.get("composition_comparability")
    if not isinstance(composition, Mapping):
        composition = report.get("comparability")
    external = report.get("external_validity")
    external = external if isinstance(external, Mapping) else {}
    return {
        "acquisition_validity": dict(acquisition) if isinstance(acquisition, Mapping) else None,
        "composition_comparability": dict(composition) if isinstance(composition, Mapping) else None,
        "reviewer_selection_bias": external.get("reviewer_selection_bias", True),
        "external_validity": external.get("limitation", REVIEWER_SELECTION_LIMITATION),
    }


def calculate_recommendation_rate(
    population: Iterable[Mapping[str, Any]],
    *,
    metadata: Any = None,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    comparability_report: Any = None,
) -> dict[str, Any]:
    """Calculate exact observed metrics and a conditional Wilson interval."""
    metrics = _population_metrics(population)
    validity = _inference_validity(metadata)
    interval = _wilson_interval(metrics["valid_n"], metrics["recommended_n"], confidence_level)
    metrics["observed_metric_status"] = validity["observed_metric_status"]
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_population_metric": True,
        "observed_metric_status": validity["observed_metric_status"],
        "population": metrics,
        "model_based_interval": interval,
        "inference_validity": validity,
        "comparison_context": _comparison_context(comparability_report),
        "external_validity": {
            "reviewer_selection_bias": True,
            "limitation": REVIEWER_SELECTION_LIMITATION,
        },
    }


def compare_recommendation_rates(
    reference_population: Iterable[Mapping[str, Any]],
    comparison_population: Iterable[Mapping[str, Any]],
    *,
    reference_metadata: Any = None,
    comparison_metadata: Any = None,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    comparability_report: Any = None,
) -> dict[str, Any]:
    """Compare two observed recommendation rates using comparison-reference."""
    reference = _population_metrics(reference_population)
    comparison = _population_metrics(comparison_population)
    reference_validity = _inference_validity(reference_metadata)
    comparison_validity = _inference_validity(comparison_metadata)
    reference["observed_metric_status"] = reference_validity["observed_metric_status"]
    comparison["observed_metric_status"] = comparison_validity["observed_metric_status"]
    difference = _difference_interval(reference, comparison, confidence_level)
    context = _comparison_context(comparability_report)
    context["reference_acquisition_validity"] = reference_validity
    context["comparison_acquisition_validity"] = comparison_validity
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_population_metric": {
            "reference": True,
            "comparison": True,
        },
        "observed_metric_status": {
            "reference": reference_validity["observed_metric_status"],
            "comparison": comparison_validity["observed_metric_status"],
        },
        "reference": reference,
        "comparison": comparison,
        "reference_model_based_interval": _wilson_interval(
            reference["valid_n"], reference["recommended_n"], confidence_level
        ),
        "comparison_model_based_interval": _wilson_interval(
            comparison["valid_n"], comparison["recommended_n"], confidence_level
        ),
        "difference": difference,
        "inference_validity": {
            "reference": reference_validity,
            "comparison": comparison_validity,
            "reviewer_selection_bias": True,
            "limitation": REVIEWER_SELECTION_LIMITATION,
        },
        "comparison_context": context,
        "external_validity": {
            "reviewer_selection_bias": True,
            "limitation": REVIEWER_SELECTION_LIMITATION,
        },
    }


build_rate_inference_report = compare_recommendation_rates
build_recommendation_rate_report = calculate_recommendation_rate


__all__ = [
    "DEFAULT_CONFIDENCE_LEVEL",
    "MODEL_ASSUMPTIONS",
    "REVIEWER_SELECTION_LIMITATION",
    "build_rate_inference_report",
    "build_recommendation_rate_report",
    "calculate_recommendation_rate",
    "compare_recommendation_rates",
]
