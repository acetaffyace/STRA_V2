"""P0.3b metric definitions and denominator-safe observations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional

import pandas as pd


SOURCE_RAW_STEAM = "raw_steam"
SOURCE_DETERMINISTIC = "deterministic_derived"
SOURCE_LLM = "llm_derived"
SOURCE_HEURISTIC = "heuristic"

DENOM_POPULATION = "population"
DENOM_VALIDATED_CLASSIFIED = "validated_classified"
DENOM_EVIDENCE = "evidence_population"
DENOM_NONE = "not_applicable"


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    description: str
    source_type: str
    denominator_type: str
    is_sampled: bool = False
    formula_version: str = "p0.3b-v1"
    sampling_semantics: Optional[str] = None


@dataclass
class MetricObservation:
    metric_id: str
    value: Optional[float | int]
    numerator: Optional[int]
    denominator: Optional[int]
    population_count: int
    eligible_count: Optional[int]
    classified_count: Optional[int]
    coverage: Optional[float]
    source_type: str
    denominator_type: str
    is_sampled: bool
    run_id: Optional[str]
    formula_version: str
    sampling_semantics: Optional[str] = None
    status: str = "available"
    unavailable_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "value": self.value,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "population_count": self.population_count,
            "eligible_count": self.eligible_count,
            "classified_count": self.classified_count,
            "coverage": self.coverage,
            "source_type": self.source_type,
            "denominator_type": self.denominator_type,
            "is_sampled": self.is_sampled,
            "run_id": self.run_id,
            "formula_version": self.formula_version,
            "sampling_semantics": self.sampling_semantics,
            "status": self.status,
            "unavailable_reason": self.unavailable_reason,
        }


METRIC_REGISTRY: Dict[str, MetricDefinition] = {
    "review_count": MetricDefinition("review_count", "Reviews in the current run population", SOURCE_RAW_STEAM, DENOM_NONE),
    "recommendation_rate": MetricDefinition("recommendation_rate", "Steam recommended reviews share", SOURCE_RAW_STEAM, DENOM_POPULATION),
    "negative_review_rate": MetricDefinition("negative_review_rate", "Steam non-recommended reviews share", SOURCE_RAW_STEAM, DENOM_POPULATION),
    "technical_issue_rate": MetricDefinition("technical_issue_rate", "Validated classified reviews mentioning a technical issue", SOURCE_LLM, DENOM_VALIDATED_CLASSIFIED),
    "feature_request_rate": MetricDefinition("feature_request_rate", "Validated classified reviews containing a feature request", SOURCE_LLM, DENOM_VALIDATED_CLASSIFIED),
    "classification_coverage": MetricDefinition("classification_coverage", "Validated LLM classifications over population", SOURCE_LLM, DENOM_POPULATION),
    "evidence_coverage": MetricDefinition(
        "evidence_coverage", "Enriched/evidence-selected reviews over population", SOURCE_LLM,
        DENOM_POPULATION, is_sampled=True, sampling_semantics="Selected enrichment/evidence subset; not representative.",
    ),
}


def metric_definition(metric_id: str, **overrides: Any) -> MetricDefinition:
    base = METRIC_REGISTRY.get(metric_id)
    if base is not None and not overrides:
        return base
    if base is None:
        return MetricDefinition(metric_id=metric_id, **overrides)
    return MetricDefinition(
        metric_id=base.metric_id,
        description=overrides.get("description", base.description),
        source_type=overrides.get("source_type", base.source_type),
        denominator_type=overrides.get("denominator_type", base.denominator_type),
        is_sampled=overrides.get("is_sampled", base.is_sampled),
        formula_version=overrides.get("formula_version", base.formula_version),
        sampling_semantics=overrides.get("sampling_semantics", base.sampling_semantics),
    )


def _ratio(numerator: Optional[int], denominator: Optional[int]) -> Optional[float]:
    if denominator is None or denominator <= 0:
        return None
    return round(float(numerator or 0) / denominator, 6)


def build_metric_observation(
    definition: MetricDefinition,
    *,
    value: Optional[float | int],
    numerator: Optional[int],
    denominator: Optional[int],
    population_count: int,
    eligible_count: Optional[int] = None,
    classified_count: Optional[int] = None,
    run_id: Optional[str] = None,
    unavailable_reason: Optional[str] = None,
) -> Dict[str, Any]:
    coverage = _ratio(eligible_count, population_count) if eligible_count is not None else None
    status = "available" if value is not None else "unavailable"
    if value is None and unavailable_reason is None:
        unavailable_reason = "denominator_zero"
    return MetricObservation(
        metric_id=definition.metric_id,
        value=value,
        numerator=numerator,
        denominator=denominator,
        population_count=int(population_count),
        eligible_count=None if eligible_count is None else int(eligible_count),
        classified_count=None if classified_count is None else int(classified_count),
        coverage=coverage,
        source_type=definition.source_type,
        denominator_type=definition.denominator_type,
        is_sampled=definition.is_sampled,
        run_id=run_id,
        formula_version=definition.formula_version,
        sampling_semantics=definition.sampling_semantics,
        status=status,
        unavailable_reason=unavailable_reason,
    ).to_dict()


def _valid_classified_mask(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=bool)
    origin = df.get("llm_label_origin", pd.Series([None] * len(df), index=df.index))
    validated = df.get("llm_validated", pd.Series([False] * len(df), index=df.index))
    return origin.isin(["llm", "offline_fixture"]) & (validated == True)  # noqa: E712


def _has_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def build_metric_provenance(df: pd.DataFrame, run_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Build core observations from one already-loaded analysis frame."""
    population = int(len(df)) if df is not None else 0
    classified_mask = _valid_classified_mask(df)
    classified_count = int(classified_mask.sum()) if population else 0
    classified = df[classified_mask] if population else df
    evidence_mask = classified_mask & df.get("llm_has_aspects", pd.Series([False] * population, index=getattr(df, "index", None))) if population else classified_mask
    evidence_count = int(evidence_mask.sum()) if population else 0
    recommended = int(df["voted_up"].sum()) if population and "voted_up" in df.columns else 0
    issue_count = int(classified["llm_issue_subcategories"].apply(_has_list).sum()) if classified_count and "llm_issue_subcategories" in classified.columns else 0
    request_count = int(classified["llm_request_subcategories"].apply(_has_list).sum()) if classified_count and "llm_request_subcategories" in classified.columns else 0

    observations: Dict[str, Dict[str, Any]] = {}
    observations["review_count"] = build_metric_observation(
        metric_definition("review_count"), value=population, numerator=population,
        denominator=None, population_count=population, eligible_count=population,
        run_id=run_id,
    )
    observations["recommendation_rate"] = build_metric_observation(
        metric_definition("recommendation_rate"), value=_ratio(recommended, population),
        numerator=recommended, denominator=population, population_count=population,
        eligible_count=population, run_id=run_id,
    )
    observations["negative_review_rate"] = build_metric_observation(
        metric_definition("negative_review_rate"), value=_ratio(population - recommended, population),
        numerator=population - recommended, denominator=population, population_count=population,
        eligible_count=population, run_id=run_id,
    )
    observations["classification_coverage"] = build_metric_observation(
        metric_definition("classification_coverage"), value=_ratio(classified_count, population),
        numerator=classified_count, denominator=population, population_count=population,
        eligible_count=classified_count, classified_count=classified_count, run_id=run_id,
    )
    observations["technical_issue_rate"] = build_metric_observation(
        metric_definition("technical_issue_rate"), value=_ratio(issue_count, classified_count),
        numerator=issue_count, denominator=classified_count, population_count=population,
        eligible_count=classified_count, classified_count=classified_count, run_id=run_id,
    )
    observations["feature_request_rate"] = build_metric_observation(
        metric_definition("feature_request_rate"), value=_ratio(request_count, classified_count),
        numerator=request_count, denominator=classified_count, population_count=population,
        eligible_count=classified_count, classified_count=classified_count, run_id=run_id,
    )
    observations["evidence_coverage"] = build_metric_observation(
        metric_definition("evidence_coverage"), value=_ratio(evidence_count, population),
        numerator=evidence_count, denominator=population, population_count=population,
        eligible_count=evidence_count, classified_count=classified_count, run_id=run_id,
    )

    if classified_count and "llm_issue_subcategories" in classified.columns:
        categories = sorted({
            str(value).split("/", 1)[0]
            for values in classified["llm_issue_subcategories"]
            if isinstance(values, list)
            for value in values
            if value
        })
        for category in categories:
            numerator = int(classified["llm_issue_subcategories"].apply(
                lambda values: isinstance(values, list) and any(str(value).startswith(f"{category}/") for value in values)
            ).sum())
            metric_id = f"{category}_issue_rate"
            definition = MetricDefinition(metric_id, f"Validated classified {category} issue rate", SOURCE_LLM, DENOM_VALIDATED_CLASSIFIED)
            observations[metric_id] = build_metric_observation(
                definition, value=_ratio(numerator, classified_count), numerator=numerator,
                denominator=classified_count, population_count=population,
                eligible_count=classified_count, classified_count=classified_count, run_id=run_id,
            )
    return observations


def build_cohort_metric_observation(
    df: pd.DataFrame,
    cohort_id: str,
    cohort_mask: pd.Series,
    *,
    metric_id: str = "technical_issue_rate",
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a subgroup observation with a subgroup denominator."""
    subset = df[cohort_mask] if df is not None else pd.DataFrame()
    population = len(subset)
    classified_mask = _valid_classified_mask(subset)
    classified = subset[classified_mask] if population else subset
    numerator = int(classified["llm_issue_subcategories"].apply(_has_list).sum()) if len(classified) and "llm_issue_subcategories" in classified.columns else 0
    definition = metric_definition(metric_id)
    definition = MetricDefinition(
        metric_id=f"{metric_id}:{cohort_id}",
        description=f"{definition.description} for cohort {cohort_id}",
        source_type=definition.source_type,
        denominator_type=definition.denominator_type,
        is_sampled=definition.is_sampled,
        formula_version=definition.formula_version,
        sampling_semantics=definition.sampling_semantics,
    )
    classified_count = len(classified)
    return build_metric_observation(
        definition, value=_ratio(numerator, classified_count), numerator=numerator,
        denominator=classified_count, population_count=population,
        eligible_count=classified_count, classified_count=classified_count, run_id=run_id,
    )


def build_metric_contract(
    metric_id: str,
    *,
    numerator: int,
    denominator: int,
    population_count: int,
    classified_count: Optional[int] = None,
    source_type: str = SOURCE_DETERMINISTIC,
    run_id: Optional[str] = None,
    coverage: Optional[float] = None,
) -> Dict[str, Any]:
    """Compatibility constructor for one explicit metric observation."""
    definition = METRIC_REGISTRY.get(metric_id) or MetricDefinition(
        metric_id, metric_id, source_type, DENOM_POPULATION
    )
    result = build_metric_observation(
        definition, value=_ratio(numerator, denominator), numerator=numerator,
        denominator=denominator, population_count=population_count,
        eligible_count=classified_count if classified_count is not None else population_count,
        classified_count=classified_count, run_id=run_id,
    )
    if coverage is not None:
        result["coverage"] = coverage
    return result


def formal_metric_denominator(labels: list[Mapping[str, Any]]) -> int:
    """Count only validated LLM labels for formal classification metrics."""
    return sum(1 for label in labels if label.get("label_origin") == "llm" and label.get("validated") is True)
