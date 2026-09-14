"""Deterministic compatibility decisions for reusable review populations."""
from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field

from .research_contracts import canonical_sampling_contract


class PopulationCompatibilityResult(BaseModel):
    decision: str = Field(pattern="^(EXACT|SAFE_SUBSET|INCOMPATIBLE)$")
    source_population_snapshot_id: str | None = None
    requested_contract: dict[str, Any]
    derived_review_snapshot_ids: list[str] = Field(default_factory=list)
    reasons: list[dict[str, str]] = Field(default_factory=list)
    materialization_required: bool = False


def _value(contract: Mapping[str, Any], key: str, default: Any = None) -> Any:
    value = contract.get(key, default)
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value]
    return value


def _contains_language(existing: Any, requested: Any) -> bool:
    left = set(_value({"value": existing}, "value", []) or [])
    right = set(_value({"value": requested}, "value", []) or [])
    return "all" in left or right <= left


def _bound_contains(existing: Any, requested: Any, *, lower: bool) -> bool:
    if requested is None:
        return existing is None
    if existing is None:
        return True if lower else True
    return int(existing) <= int(requested) if lower else int(existing) >= int(requested)


def check_population_compatibility(*, existing_population: Mapping[str, Any], requested_contract: Mapping[str, Any]) -> PopulationCompatibilityResult:
    """Return an auditable reuse decision without changing stored data."""
    existing_contract = canonical_sampling_contract(existing_population.get("sampling_contract") or {})
    requested = canonical_sampling_contract(requested_contract)
    reasons: list[dict[str, str]] = []
    exact_mismatches: list[str] = []
    subset_blockers: list[str] = []

    if int(existing_population.get("app_id") or existing_contract.get("app_id") or 0) != int(requested.get("app_id") or 0):
        reasons.append({"code": "APP_MISMATCH", "detail": "Stored and requested app IDs differ."})
        subset_blockers.append("app_id")

    comparable_fields = ("start_time", "end_time", "languages", "review_type", "purchase_type", "collection_order", "include_offtopic_activity", "max_reviews")
    for field in comparable_fields:
        if _value(existing_contract, field) != _value(requested, field):
            exact_mismatches.append(field)

    complete = bool((existing_population.get("acquisition_provenance") or {}).get("collection_complete", (existing_population.get("acquisition_provenance") or {}).get("complete", False)))
    truncated = bool((existing_population.get("acquisition_provenance") or {}).get("truncated_by_max_reviews", False))
    if not complete or truncated:
        reasons.append({"code": "INCOMPLETE_SOURCE", "detail": "Stored population is not proven complete for reuse."})
        subset_blockers.append("coverage")

    if not _contains_language(existing_contract.get("languages", ["all"]), requested.get("languages", ["all"])):
        reasons.append({"code": "LANGUAGE_NOT_COVERED", "detail": "Stored language set does not contain the requested set."})
        subset_blockers.append("languages")
    if _value(existing_contract, "review_type", "all") not in {"all", _value(requested, "review_type", "all")}:
        reasons.append({"code": "REVIEW_TYPE_NOT_COVERED", "detail": "Stored review type is narrower than requested."})
        subset_blockers.append("review_type")
    if _value(existing_contract, "purchase_type", "all") not in {"all", _value(requested, "purchase_type", "all")}:
        reasons.append({"code": "PURCHASE_TYPE_NOT_COVERED", "detail": "Stored purchase type is narrower than requested."})
        subset_blockers.append("purchase_type")
    if bool(_value(requested, "include_offtopic_activity", False)) and not bool(_value(existing_contract, "include_offtopic_activity", False)):
        reasons.append({"code": "OFFTOPIC_NOT_COVERED", "detail": "Requested off-topic activity is absent from the stored population."})
        subset_blockers.append("include_offtopic_activity")
    if _value(existing_contract, "collection_order", "recent") != _value(requested, "collection_order", "recent"):
        reasons.append({"code": "COLLECTION_ORDER_MISMATCH", "detail": "Collection order changes capped membership semantics."})
        subset_blockers.append("collection_order")

    existing_start = existing_contract.get("start_time")
    existing_end = existing_contract.get("end_time")
    requested_start = requested.get("start_time")
    requested_end = requested.get("end_time")
    if not _bound_contains(existing_start, requested_start, lower=True) or not _bound_contains(existing_end, requested_end, lower=False):
        reasons.append({"code": "TIME_WINDOW_NOT_CONTAINED", "detail": "Requested absolute window is not contained by the stored window."})
        subset_blockers.append("time_window")

    existing_max = int(existing_contract.get("max_reviews") or 0)
    requested_max = int(requested.get("max_reviews") or 0)
    if existing_max and (not requested_max or requested_max > existing_max):
        reasons.append({"code": "CAP_NOT_COVERED", "detail": "Stored capped population cannot prove the requested larger/unlimited population."})
        subset_blockers.append("max_reviews")

    source_ids = [str(item) for item in (existing_population.get("ordered_review_snapshot_ids") or [])]
    if not reasons and not exact_mismatches:
        return PopulationCompatibilityResult(decision="EXACT", source_population_snapshot_id=existing_population.get("population_snapshot_id"), requested_contract=requested, derived_review_snapshot_ids=source_ids, reasons=[{"code": "EXACT_MATCH", "detail": "Stored population exactly satisfies the requested contract."}])

    if not subset_blockers:
        derived = source_ids
        if requested_max:
            derived = derived[:requested_max]
        return PopulationCompatibilityResult(decision="SAFE_SUBSET", source_population_snapshot_id=existing_population.get("population_snapshot_id"), requested_contract=requested, derived_review_snapshot_ids=derived, reasons=reasons + [{"code": "SAFE_SUBSET", "detail": "Stored ordered membership is a deterministic superset of the request."}], materialization_required=True)

    if not reasons:
        reasons.append({"code": "CONTRACT_MISMATCH", "detail": ", ".join(exact_mismatches)})
    return PopulationCompatibilityResult(decision="INCOMPATIBLE", source_population_snapshot_id=existing_population.get("population_snapshot_id"), requested_contract=requested, reasons=reasons)


__all__ = ["PopulationCompatibilityResult", "check_population_compatibility"]
