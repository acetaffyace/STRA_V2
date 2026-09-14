"""Exact-run read projections shared by Agent and Reports.

This module is intentionally boring: it only loads persisted canonical
results and frozen run inputs.  It does not classify, aggregate mutable
labels, or derive a second set of research metrics.
"""
from __future__ import annotations

from typing import Any, Mapping

from . import storage
from .classification_materialization import get_materialization_for_run
from .dashboard_presentation import build_dashboard_presentation
from .research_population_snapshot import get_analysis_run_population


def resolve_completed_general_run(app_id: int, requested_run_id: str | None = None) -> str | None:
    """Resolve one run once; callers must pin the returned ID for a turn."""
    if requested_run_id:
        run = storage.get_analysis_run(str(requested_run_id))
        if (
            run
            and run.get("run_type") == "general_analysis"
            and run.get("status") == "completed"
            and int(run.get("target_app_id")) == int(app_id)
            and storage.get_analysis_run_result(str(requested_run_id)) is not None
        ):
            return str(requested_run_id)
        return None
    for run in storage.list_analysis_runs(int(app_id)):
        if run.get("run_type") != "general_analysis" or run.get("status") != "completed":
            continue
        run_id = str(run.get("run_id") or "")
        if run_id and storage.get_analysis_run_result(run_id) is not None:
            return run_id
    return None


def load_exact_run(app_id: int, run_id: str | None = None) -> dict[str, Any] | None:
    resolved = resolve_completed_general_run(app_id, run_id)
    if not resolved:
        return None
    run = storage.get_analysis_run(resolved)
    result = storage.get_analysis_run_result(resolved)
    if not run or not result:
        return None
    if int(run.get("target_app_id")) != int(app_id):
        return None
    population = get_analysis_run_population(resolved)
    materialization = get_materialization_for_run(resolved)
    return {
        "run": run,
        "result": result,
        "population": population,
        "materialization": materialization,
        "run_id": resolved,
    }


def build_exact_presentation(exact: Mapping[str, Any]) -> dict[str, Any]:
    run = exact["run"]
    result = exact["result"]
    return build_dashboard_presentation(
        app_id=int(run["target_app_id"]),
        run=run,
        result=result,
    )


def semantic_rows(exact: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    result = exact["result"].get("semantic_measurement_result")
    if not isinstance(result, Mapping):
        return None
    return [dict(row) for row in (result.get("topics") or []) if isinstance(row, Mapping)]


def review_labels_for_run(exact: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    materialization = exact.get("materialization")
    if not materialization:
        return {}
    labels: dict[str, dict[str, Any]] = {}
    for item in materialization.get("items") or []:
        review_id = str(item.get("review_id") or "")
        if review_id:
            labels[review_id] = dict(item.get("payload") or {})
    return labels


def canonical_review_search(
    exact: Mapping[str, Any],
    *,
    query: str = "",
    subcategory: str | None = None,
    metric_type: str = "topic",
    sentiment: str | None = None,
    language: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """Search only the exact frozen population and frozen labels."""
    reviews = list((exact.get("population") or {}).get("reviews") or [])
    labels = review_labels_for_run(exact)
    term = str(query or "").strip().lower()
    wanted = str(subcategory or "").strip().lower()
    valid_metrics = {"topic": "subcategories", "issue": "issue_subcategories", "request": "request_subcategories"}
    label_key = valid_metrics.get(metric_type, "subcategories")
    matched: list[dict[str, Any]] = []
    for review in reviews:
        review_id = str(review.get("recommendationid") or review.get("review_id") or "")
        payload = labels.get(review_id, {})
        values = [str(value) for value in (payload.get(label_key) or [])]
        text = str(review.get("review") or "")
        if term and term not in text.lower():
            continue
        if wanted and wanted not in {value.lower() for value in values}:
            continue
        if sentiment == "positive" and review.get("voted_up") is not True:
            continue
        if sentiment == "negative" and review.get("voted_up") is not False:
            continue
        if language and str(review.get("language") or "").lower() != str(language).lower():
            continue
        matched.append({
            **dict(review),
            "review_id": review_id,
            "taxonomy_labels": list(payload.get("subcategories") or []),
            "issue_labels": list(payload.get("issue_subcategories") or []),
            "request_labels": list(payload.get("request_subcategories") or []),
            "verified_evidence": list(payload.get("evidence") or []),
            "source": "exact_frozen_run",
            "verified_evidence_available": bool(payload.get("evidence")),
        })
    safe_offset = max(0, int(offset or 0))
    safe_limit = max(1, min(int(limit or 10), 50))
    return {
        "run_id": exact["run_id"],
        "app_id": int(exact["run"]["target_app_id"]),
        "total_found": len(matched),
        "offset": safe_offset,
        "limit": safe_limit,
        "reviews": matched[safe_offset : safe_offset + safe_limit],
        "population_scope": "exact_frozen_research_population",
        "classification_scope": "exact_frozen_classification_materialization",
        "metric_type": metric_type,
        "verified_evidence_count": sum(1 for item in matched if item["verified_evidence_available"]),
    }


__all__ = [
    "build_exact_presentation",
    "canonical_review_search",
    "load_exact_run",
    "resolve_completed_general_run",
    "review_labels_for_run",
    "semantic_rows",
]
