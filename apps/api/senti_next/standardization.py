"""Direct composition-standardization sensitivity for observed review populations.

This module asks how the observed recommendation-rate difference changes when
both review populations are evaluated against a common *observed* composition.
It is descriptive sensitivity analysis, not causal adjustment, bias removal, or
an attempt to make Steam reviewers representative of all players.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from .population_validity import PLAYTIME_COHORTS
from .rate_inference import REVIEWER_SELECTION_LIMITATION, calculate_recommendation_rate


SUPPORTED_VARIABLES = (
    "language",
    "playtime_cohort",
    "steam_purchase",
    "received_for_free",
    "written_during_early_access",
    "primarily_steam_deck",
)
_BOOLEAN_VARIABLES = set(SUPPORTED_VARIABLES[2:])
_MISSING_STRATUM = "__missing__"
_SCHEMA_VERSION = "composition-standardization-v1"


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


def _as_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _value(row: Mapping[str, Any], field: str) -> Any:
    if field in row:
        return row.get(field)
    if field.startswith("author."):
        author = row.get("author")
        if isinstance(author, Mapping):
            return author.get(field.split(".", 1)[1])
        return row.get("author_" + field.split(".", 1)[1])
    return None


def _playtime_cohort(row: Mapping[str, Any]) -> Optional[str]:
    minutes = _as_number(_value(row, "author.playtime_at_review"))
    if minutes is None or minutes < 0:
        return None
    hours = minutes / 60.0
    for label, lower, upper in PLAYTIME_COHORTS:
        if hours >= lower and (upper is None or hours < upper):
            return label
    return None


def _covariate_value(row: Mapping[str, Any], variable: str) -> str:
    if variable == "language":
        value = _value(row, "language")
        return str(value).strip().lower() if value is not None and str(value).strip() else _MISSING_STRATUM
    if variable == "playtime_cohort":
        return _playtime_cohort(row) or _MISSING_STRATUM
    if variable in _BOOLEAN_VARIABLES:
        value = _as_bool(_value(row, variable))
        return str(value).lower() if value is not None else _MISSING_STRATUM
    raise ValueError(f"unsupported adjustment variable: {variable}")


def _stratum_values(row: Mapping[str, Any], variables: tuple[str, ...]) -> dict[str, str]:
    return {variable: _covariate_value(row, variable) for variable in variables}


def _stratum_key(values: Mapping[str, str], variables: tuple[str, ...]) -> str:
    if len(variables) == 1:
        return values[variables[0]]
    return "|".join(f"{variable}={values[variable]}" for variable in variables)


def _outcome(value: Any) -> Optional[bool]:
    return _as_bool(value)


def _summarize_rows(rows: list[Mapping[str, Any]], variables: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for row in rows:
        values = _stratum_values(row, variables)
        key = _stratum_key(values, variables)
        summary = summaries.setdefault(
            key,
            {
                "stratum": key,
                "stratum_values": values,
                "total_n": 0,
                "outcome_valid_n": 0,
                "outcome_missing_n": 0,
                "recommended_n": 0,
                "recommendation_rate": None,
            },
        )
        summary["total_n"] += 1
        outcome = _outcome(row.get("voted_up"))
        if outcome is None:
            summary["outcome_missing_n"] += 1
        else:
            summary["outcome_valid_n"] += 1
            summary["recommended_n"] += int(outcome is True)
    for summary in summaries.values():
        if summary["outcome_valid_n"]:
            summary["recommendation_rate"] = summary["recommended_n"] / summary["outcome_valid_n"]
    return {key: summaries[key] for key in sorted(summaries)}


def _share_summary(summaries: Mapping[str, Mapping[str, Any]], total_n: int) -> dict[str, float]:
    if not total_n:
        return {}
    return {key: summary["total_n"] / total_n for key, summary in sorted(summaries.items())}


def _quantiles(values: list[float]) -> dict[str, Optional[float]]:
    if not values:
        return {"p25": None, "median": None, "p75": None}
    values = sorted(values)

    def percentile(q: float) -> float:
        position = (len(values) - 1) * q
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        weight = position - lower
        return values[lower] * (1 - weight) + values[upper] * weight

    return {"p25": percentile(0.25), "median": percentile(0.5), "p75": percentile(0.75)}


def _weight_diagnostics(target_shares: Mapping[str, float], observed_shares: Mapping[str, float]) -> dict[str, Any]:
    by_stratum: dict[str, Optional[float]] = {}
    defined: list[float] = []
    for stratum, target_share in sorted(target_shares.items()):
        observed_share = observed_shares.get(stratum, 0.0)
        if observed_share > 0:
            weight = target_share / observed_share
            by_stratum[stratum] = weight
            defined.append(weight)
        else:
            # Positive target mass with no observed mass is a support violation,
            # never an infinite weight to apply silently.
            by_stratum[stratum] = None
    quantiles = _quantiles(defined)
    return {
        "by_stratum": by_stratum,
        "min_weight": min(defined) if defined else None,
        "max_weight": max(defined) if defined else None,
        "weight_quantiles": quantiles,
    }


def _validate_variables(variables: Optional[Iterable[str]]) -> tuple[str, ...]:
    selected = tuple(variables) if variables is not None else ("language",)
    if not selected:
        raise ValueError("at least one adjustment variable is required")
    if len(set(selected)) != len(selected):
        raise ValueError("adjustment variables must be unique")
    unsupported = [variable for variable in selected if variable not in SUPPORTED_VARIABLES]
    if unsupported:
        raise ValueError(f"unsupported adjustment variable(s): {', '.join(unsupported)}")
    return selected


def _raw_rates(
    reference: list[Mapping[str, Any]],
    comparison: list[Mapping[str, Any]],
    reference_metadata: Any,
    comparison_metadata: Any,
) -> dict[str, Any]:
    reference_report = calculate_recommendation_rate(reference, metadata=reference_metadata)
    comparison_report = calculate_recommendation_rate(comparison, metadata=comparison_metadata)
    reference_rate = reference_report["population"]["recommendation_rate"]
    comparison_rate = comparison_report["population"]["recommendation_rate"]
    difference = comparison_rate - reference_rate if reference_rate is not None and comparison_rate is not None else None
    return {
        "reference_rate": reference_rate,
        "comparison_rate": comparison_rate,
        "difference": difference,
        "reference_metrics": reference_report["population"],
        "comparison_metrics": comparison_report["population"],
    }


def _provenance_context(
    reference_metadata: Any,
    comparison_metadata: Any,
    comparability_report: Any,
) -> tuple[dict[str, Any], bool]:
    report = comparability_report if isinstance(comparability_report, Mapping) else {}
    acquisition = report.get("acquisition_validity")
    if not isinstance(acquisition, Mapping):
        acquisition = None
    composition = report.get("composition_comparability")
    if not isinstance(composition, Mapping):
        composition = None
    observability = composition.get("observability") if composition else None
    limited = bool(acquisition and acquisition.get("level") != "high")
    for metadata in (reference_metadata, comparison_metadata):
        if hasattr(metadata, "model_dump"):
            metadata = metadata.model_dump(mode="json")
        if isinstance(metadata, Mapping):
            complete = metadata.get("collection_complete", metadata.get("scope_complete"))
            if complete is not True:
                limited = True
            if metadata.get("truncated_by_max_reviews") or metadata.get("stop_reason") == "max_reviews_reached":
                limited = True
    context = {
        "acquisition_validity": dict(acquisition) if acquisition else None,
        "composition_comparability": dict(composition) if composition else None,
        "observability": dict(observability) if isinstance(observability, Mapping) else observability,
        "acquisition_limited": limited,
        "reviewer_selection_bias": True,
        "limitation": REVIEWER_SELECTION_LIMITATION,
    }
    return context, limited


def _standardize_core(
    reference: list[Mapping[str, Any]],
    comparison: list[Mapping[str, Any]],
    raw: Mapping[str, Any],
    variables: tuple[str, ...],
    target: str,
) -> dict[str, Any]:
    reference_summaries = _summarize_rows(reference, variables)
    comparison_summaries = _summarize_rows(comparison, variables)
    reference_shares = _share_summary(reference_summaries, len(reference))
    comparison_shares = _share_summary(comparison_summaries, len(comparison))
    if target == "reference":
        target_summaries, target_shares = reference_summaries, reference_shares
    elif target == "pooled":
        pooled = reference + comparison
        target_summaries = _summarize_rows(pooled, variables)
        target_shares = _share_summary(target_summaries, len(pooled))
    else:
        raise ValueError("target must be 'reference' or 'pooled'")

    reference_n_by_stratum = reference_summaries
    comparison_n_by_stratum = comparison_summaries
    strata: list[dict[str, Any]] = []
    for stratum in sorted(target_shares):
        reference_summary = reference_n_by_stratum.get(stratum, {"total_n": 0, "recommendation_rate": None})
        comparison_summary = comparison_n_by_stratum.get(stratum, {"total_n": 0, "recommendation_rate": None})
        target_values = target_summaries[stratum].get("stratum_values", {})
        strata.append(
            {
                "stratum": stratum,
                "stratum_values": target_values,
                "target_share": target_shares[stratum],
                "reference_n": reference_summary.get("total_n", 0),
                "comparison_n": comparison_summary.get("total_n", 0),
                "reference_rate": reference_summary.get("recommendation_rate"),
                "comparison_rate": comparison_summary.get("recommendation_rate"),
                "reference_outcome_valid_n": reference_summary.get("outcome_valid_n", 0),
                "reference_outcome_missing_n": reference_summary.get("outcome_missing_n", 0),
                "reference_recommended_n": reference_summary.get("recommended_n", 0),
                "comparison_outcome_valid_n": comparison_summary.get("outcome_valid_n", 0),
                "comparison_outcome_missing_n": comparison_summary.get("outcome_missing_n", 0),
                "comparison_recommended_n": comparison_summary.get("recommended_n", 0),
            }
        )

    reference_valid = {stratum for stratum, summary in reference_n_by_stratum.items() if summary.get("recommendation_rate") is not None}
    comparison_valid = {stratum for stratum, summary in comparison_n_by_stratum.items() if summary.get("recommendation_rate") is not None}
    reference_unsupported = [stratum for stratum in sorted(target_shares) if stratum not in reference_valid]
    comparison_unsupported = [stratum for stratum in sorted(target_shares) if stratum not in comparison_valid]
    reference_supported_mass = sum(target_shares[stratum] for stratum in target_shares if stratum not in reference_unsupported)
    comparison_supported_mass = sum(target_shares[stratum] for stratum in target_shares if stratum not in comparison_unsupported)
    unsupported_strata = sorted(set(reference_unsupported) | set(comparison_unsupported))

    # Use explicit group functions so a support failure in either population
    # makes the requested full-target result incomplete rather than silently
    # renormalizing the supported strata.
    reference_standardized_rate = (
        sum(target_shares[stratum] * reference_n_by_stratum[stratum]["recommendation_rate"] for stratum in target_shares)
        if not reference_unsupported
        else None
    )
    comparison_standardized_rate = (
        sum(target_shares[stratum] * comparison_n_by_stratum[stratum]["recommendation_rate"] for stratum in target_shares)
        if not comparison_unsupported
        else None
    )
    standardized_difference = (
        comparison_standardized_rate - reference_standardized_rate
        if reference_standardized_rate is not None and comparison_standardized_rate is not None
        else None
    )
    raw_difference = raw.get("difference")
    shift = standardized_difference - raw_difference if standardized_difference is not None and raw_difference is not None else None
    reversal = (
        bool(raw_difference and standardized_difference and ((raw_difference > 0) != (standardized_difference > 0)))
        if raw_difference is not None and standardized_difference is not None
        else None
    )

    both_supported = set(target_shares) - set(reference_unsupported) - set(comparison_unsupported)
    common_mass = sum(target_shares[stratum] for stratum in both_supported)
    common_support_only = None
    if common_mass > 0:
        common_reference_rate = sum(target_shares[stratum] * reference_n_by_stratum[stratum]["recommendation_rate"] for stratum in both_supported) / common_mass
        common_comparison_rate = sum(target_shares[stratum] * comparison_n_by_stratum[stratum]["recommendation_rate"] for stratum in both_supported) / common_mass
        common_support_only = {
            "status": "available",
            "target_population": "reduced_common_support",
            "target_mass": common_mass,
            "reference_standardized_rate": common_reference_rate,
            "comparison_standardized_rate": common_comparison_rate,
            "standardized_difference": common_comparison_rate - common_reference_rate,
        }

    status = "complete" if not reference_unsupported and not comparison_unsupported else "incomplete_support"
    def observed_covariate_count(rows: list[Mapping[str, Any]]) -> int:
        return sum(
            all(_covariate_value(row, variable) != _MISSING_STRATUM for variable in variables)
            for row in rows
        )

    observability = {
        "reference_nonmissing_n": observed_covariate_count(reference),
        "comparison_nonmissing_n": observed_covariate_count(comparison),
    }
    # A variable with no non-missing observations in either population is not
    # an observable adjustment dimension, even though its missing stratum is
    # retained for auditability.
    missing_only = all(stratum == _MISSING_STRATUM for stratum in target_shares) if len(variables) == 1 else False
    if not target_shares:
        status = "unavailable"
        reference_standardized_rate = comparison_standardized_rate = standardized_difference = shift = None
        common_support_only = None
    elif missing_only:
        status = "unavailable"
        reference_standardized_rate = comparison_standardized_rate = standardized_difference = shift = None
        common_support_only = None

    weights = {
        "reference": _weight_diagnostics(target_shares, reference_shares),
        "comparison": _weight_diagnostics(target_shares, comparison_shares),
    }
    reference_missing_covariate_n = sum(
        summary["total_n"]
        for summary in reference_summaries.values()
        if _MISSING_STRATUM in summary["stratum_values"].values()
    )
    comparison_missing_covariate_n = sum(
        summary["total_n"]
        for summary in comparison_summaries.values()
        if _MISSING_STRATUM in summary["stratum_values"].values()
    )
    support = {
        "supported_target_mass": min(reference_supported_mass, comparison_supported_mass),
        "unsupported_target_mass": 1.0 - min(reference_supported_mass, comparison_supported_mass),
        "unsupported_strata": unsupported_strata,
        "by_population": {
            "reference": {
                "supported_target_mass": reference_supported_mass,
                "unsupported_target_mass": 1.0 - reference_supported_mass,
                "unsupported_strata": reference_unsupported,
            },
            "comparison": {
                "supported_target_mass": comparison_supported_mass,
                "unsupported_target_mass": 1.0 - comparison_supported_mass,
                "unsupported_strata": comparison_unsupported,
            },
        },
    }
    return {
        "target": target,
        "variables": list(variables),
        "status": status,
        "strata": strata,
        "reference_standardized_rate": reference_standardized_rate,
        "comparison_standardized_rate": comparison_standardized_rate,
        "standardized_difference": standardized_difference,
        "composition_standardization_shift": shift,
        "direction_reversal_after_standardization": reversal,
        "support": support,
        "common_support_only": common_support_only,
        "weights": weights,
        "observability": observability,
        "missing_covariate": {
            "reference": {
                "missing_covariate_n": reference_missing_covariate_n,
                "missing_covariate_share": reference_missing_covariate_n / len(reference) if reference else None,
            },
            "comparison": {
                "missing_covariate_n": comparison_missing_covariate_n,
                "missing_covariate_share": comparison_missing_covariate_n / len(comparison) if comparison else None,
            },
            "representation": _MISSING_STRATUM,
            "limitation": "Treating missing as a separate observed category does not solve missing-not-at-random bias.",
        },
    }


def build_single_dimension_sensitivity(
    reference_population: Iterable[Mapping[str, Any]],
    comparison_population: Iterable[Mapping[str, Any]],
    *,
    reference_metadata: Any = None,
    comparison_metadata: Any = None,
    target: str = "reference",
) -> list[dict[str, Any]]:
    """Return one deterministic sensitivity row for every supported dimension."""
    reference = [dict(row) for row in reference_population]
    comparison = [dict(row) for row in comparison_population]
    raw = _raw_rates(reference, comparison, reference_metadata, comparison_metadata)
    result: list[dict[str, Any]] = []
    for variable in SUPPORTED_VARIABLES:
        core = _standardize_core(reference, comparison, raw, (variable,), target)
        result.append(
            {
                "dimension": variable,
                "raw_difference": raw["difference"],
                "standardized_difference": core["standardized_difference"],
                "composition_standardization_shift": core["composition_standardization_shift"],
                "status": core["status"],
                "reason": "no_observed_covariate_values" if core["status"] == "unavailable" else None,
            }
        )
    return result


def standardize_populations(
    reference_population: Iterable[Mapping[str, Any]],
    comparison_population: Iterable[Mapping[str, Any]],
    *,
    reference_metadata: Any = None,
    comparison_metadata: Any = None,
    comparability_report: Any = None,
    variables: Optional[Iterable[str]] = None,
    target: str = "reference",
    include_single_dimension_sensitivity: bool = True,
) -> dict[str, Any]:
    """Run auditable direct standardization for an explicit target and strata."""
    reference = [dict(row) for row in reference_population]
    comparison = [dict(row) for row in comparison_population]
    selected = _validate_variables(variables)
    raw = _raw_rates(reference, comparison, reference_metadata, comparison_metadata)
    context, acquisition_limited = _provenance_context(reference_metadata, comparison_metadata, comparability_report)
    standardization = _standardize_core(reference, comparison, raw, selected, target)
    standardization["acquisition_limited"] = acquisition_limited
    report = {
        "schema_version": _SCHEMA_VERSION,
        "raw": {
            "reference_rate": raw["reference_rate"],
            "comparison_rate": raw["comparison_rate"],
            "difference": raw["difference"],
            "difference_percentage_points": raw["difference"] * 100.0 if raw["difference"] is not None else None,
            "reference_metrics": raw["reference_metrics"],
            "comparison_metrics": raw["comparison_metrics"],
        },
        "standardization": standardization,
        "support": standardization["support"],
        "weights": standardization["weights"],
        "standardized_interval": None,
        "uncertainty_status": "uncertainty_not_implemented_for_standardized_estimator",
        "comparison_context": context,
        "acquisition_limited": acquisition_limited,
        "external_validity": {
            "reviewer_selection_bias": True,
            "limitation": REVIEWER_SELECTION_LIMITATION,
        },
        "single_dimension_sensitivity": (
            build_single_dimension_sensitivity(
                reference,
                comparison,
                reference_metadata=reference_metadata,
                comparison_metadata=comparison_metadata,
                target=target,
            )
            if include_single_dimension_sensitivity
            else None
        ),
        "interpretation": {
            "descriptive_sensitivity_only": True,
            "weights_use_outcomes": False,
            "not_causal_adjustment": True,
            "not_bias_removed": True,
            "standardization_effects_not_necessarily_additive": True,
            "reviewer_selection_bias": True,
            "limitation": REVIEWER_SELECTION_LIMITATION,
        },
    }
    return report


build_composition_standardization_report = standardize_populations


__all__ = [
    "SUPPORTED_VARIABLES",
    "build_composition_standardization_report",
    "build_single_dimension_sensitivity",
    "standardize_populations",
]
