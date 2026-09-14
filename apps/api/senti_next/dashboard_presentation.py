"""Canonical, read-only presentation projection for the dashboard.

This module deliberately formats persisted research results without deriving a
second set of research metrics.  It is the boundary between immutable result
storage and the product UI.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


PRESENTATION_SCHEMA_VERSION = "dashboard-presentation-v1"


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _share(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sorted(rows: Sequence[Mapping[str, Any]], share_key: str, count_key: str) -> list[dict[str, Any]]:
    return sorted(
        (dict(row) for row in rows if _number(row.get(count_key)) > 0),
        key=lambda row: (-(_share(row.get(share_key)) or 0.0), str(row.get("taxonomy_key") or "")),
    )


def _metric_row(row: Mapping[str, Any], *, count_key: str, share_key: str, validation_key: str) -> dict[str, Any]:
    count = _number(row.get(count_key))
    return {
        "taxonomy_key": str(row.get("taxonomy_key") or ""),
        "n": count,
        "share": _share(row.get(share_key)),
        "validation": row.get(validation_key),
        "denominator": "classified reviews",
    }


def _research_snapshot(report: Mapping[str, Any] | None) -> dict[str, Any]:
    report = report or {}
    population = report.get("population") or {}
    recommendation = report.get("recommendation") or {}
    rec_population = recommendation.get("population") or {}
    # research-report-v1 owns recommendation metrics under the recommendation
    # population object.  Do not fall back to a guessed/root-level field: a
    # missing canonical value must remain missing in the presentation layer.
    rate = rec_population.get("recommendation_rate")
    interval = recommendation.get("model_based_interval") or recommendation.get("confidence_interval")
    sampling = population.get("sampling_contract") or {}
    complete = population.get("collection_complete")
    truncated = population.get("truncated_by_max_reviews")
    collection_status = "complete" if complete is True else ("limited" if truncated is True else "unknown")
    return {
        "population_n": _number(population.get("review_count") or report.get("population_n")),
        "valid_n": _number(rec_population.get("valid_n")),
        "recommended_n": _number(rec_population.get("recommended_n")),
        "not_recommended_n": _number(rec_population.get("not_recommended_n")),
        "recommendation_rate": rate,
        "confidence_interval": interval,
        "collection_scope": {
            "start_time": sampling.get("start_time"),
            "end_time": sampling.get("end_time"),
            "languages": list(sampling.get("languages") or []),
            "review_type": sampling.get("review_type"),
            "purchase_type": sampling.get("purchase_type"),
            "collection_order": sampling.get("collection_order"),
            "include_offtopic_activity": sampling.get("include_offtopic_activity"),
            "max_reviews": sampling.get("max_reviews"),
            # Compatibility display fields are intentionally derived from the
            # explicit contract, never used as the canonical source.
            "language": sampling.get("languages"),
            "filter": sampling.get("review_type"),
            "review_order": sampling.get("collection_order"),
        },
        "acquisition_coverage": population.get("coverage_status"),
        "collection_complete": population.get("collection_complete"),
        "truncated_by_max_reviews": population.get("truncated_by_max_reviews"),
        "collection_status": collection_status,
        "stop_reason": population.get("stop_reason"),
        "coverage_start_time": population.get("coverage_start_time"),
        "coverage_end_time": population.get("coverage_end_time"),
        "language_distribution": report.get("language_distribution") or {},
        "stage2e_activity": report.get("stage2e_activity") or report.get("activity") or {},
    }


def _semantic_projection(result: Mapping[str, Any] | None, semantic_status: Mapping[str, Any] | None) -> dict[str, Any]:
    if not result:
        return {
            "available": False,
            "status": (semantic_status or {}).get("status") or "unavailable",
            "reason": (semantic_status or {}).get("reason") or "Semantic analysis is unavailable for this run.",
            "claim_status": None,
            "measurement_status": None,
            "classification_coverage": None,
            "classified_n": None,
            "population_n": None,
            "denominator": None,
            "limitations": [],
        }
    provenance = result.get("provenance") or {}
    coverage = result.get("classification_coverage")
    return {
        "available": True,
        "status": "available",
        "reason": None,
        "claim_status": result.get("claim_status"),
        "measurement_status": provenance.get("measurement_status") or result.get("measurement_status"),
        "validation_status": provenance.get("validation_status"),
        "classification_coverage": coverage,
        "coverage_status": result.get("coverage_status"),
        "classified_n": _number(result.get("classified_n")),
        "population_n": _number(result.get("population_n")),
        "denominator": result.get("denominators") or {"topic": "classified_n", "issue": "classified_n", "request": "classified_n"},
        "taxonomy_version": provenance.get("taxonomy_version"),
        "provider": provenance.get("classifier_provider") or provenance.get("provider"),
        "model": provenance.get("classifier_model_id") or provenance.get("model_id"),
        "prompt_version": provenance.get("classifier_prompt_version") or provenance.get("prompt_version"),
        "schema_version": provenance.get("classifier_schema_version") or provenance.get("schema_version"),
        "limitations": list(result.get("limitations") or []),
        "measurement_result_fingerprint": result.get("semantic_measurement_result_fingerprint"),
    }


def _discovery_projection(discovery: Mapping[str, Any] | None) -> dict[str, Any]:
    if not discovery:
        return {"available": False, "status": "unavailable", "reason": "No persisted discovery sidecar is attached to this run."}
    audit = discovery.get("taxonomy_audit") or {}
    regions = discovery.get("regions") or []
    return {
        "available": True,
        "status": discovery.get("status") or "completed",
        "materialization_id": discovery.get("materialization_id"),
        "discovery_fingerprint": discovery.get("discovery_fingerprint"),
        "dense_region_n": _number(discovery.get("dense_region_n")),
        "rare_region_n": _number(discovery.get("rare_region_n")),
        "outlier_review_n": _number(discovery.get("outlier_review_n")),
        "clustered_review_share": discovery.get("clustered_review_share"),
        "unclustered_review_share": discovery.get("unclustered_review_share"),
        "stability_distribution": discovery.get("stability_distribution") or {},
        "taxonomy_audit": audit,
        "regions": [
            {
                "region_id": region.get("region_id"),
                "discovery_type": region.get("discovery_type"),
                "support_reviews": region.get("support_reviews"),
                "support_units": region.get("support_units"),
                "cohesion": region.get("cohesion"),
                "stability": region.get("stability"),
                "taxonomy_coverage_status": region.get("taxonomy_coverage_status"),
                "representative_review_ids": list(region.get("representative_review_ids") or []),
            }
            for region in regions
        ],
        "interpretation": discovery.get("interpretation") or {
            "status": "unavailable",
            "reason": "No interpretation result is attached to this discovery materialization.",
        },
    }


def _segments_projection(report: Mapping[str, Any] | None) -> dict[str, Any]:
    segments = report.get("segments") if isinstance(report, Mapping) else None
    if not isinstance(segments, Mapping):
        return {
            "available": False,
            "schema_version": "research-segments-v1",
            "population_scope": "exact_research_run_population",
            "population_n": 0,
            "dimensions": {},
            "unavailable_reason": "research_segments_unavailable",
        }
    return {
        "available": True,
        "schema_version": segments.get("schema_version") or "research-segments-v1",
        "population_scope": segments.get("population_scope") or "exact_research_run_population",
        "population_n": _number(segments.get("population_n")),
        "dimensions": segments.get("dimensions") or {},
        "unavailable_reason": None,
    }


def build_dashboard_presentation(
    *,
    app_id: int,
    run: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    discovery: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project exact persisted values into the ``dashboard-presentation-v1`` contract."""
    result = result or {}
    run = run or {}
    metadata = result.get("metadata") or {}
    semantic_result = result.get("semantic_measurement_result")
    semantic_status = result.get("semantic_status")
    report = result.get("research_report")
    topics = list((semantic_result or {}).get("topics") or [])
    topic_rows = _sorted(topics, "topic_share", "topic_n")
    issue_rows = _sorted(topics, "issue_share", "issue_n")
    request_rows = _sorted(topics, "request_share", "request_n")
    primary_rows = _sorted(topics, "primary_share", "primary_n")
    actionable = [row for row in topic_rows if not str(row.get("taxonomy_key") or "").startswith("other/")]
    context = [row for row in topic_rows if str(row.get("taxonomy_key") or "").startswith("other/")]
    semantic = _semantic_projection(semantic_result, semantic_status if isinstance(semantic_status, Mapping) else None)
    population_fp = ((semantic_result or {}).get("provenance") or {}).get("population_fingerprint") or metadata.get("population_fingerprint")
    limitations = list((report or {}).get("limitations") or []) if isinstance(report, Mapping) else []
    limitations.extend(semantic.get("limitations") or [])
    if semantic.get("claim_status") == "PROVISIONAL":
        limitations.append("Production classification completed, but this semantic measurement has not yet passed formal classifier validation.")
    return {
        "schema_version": PRESENTATION_SCHEMA_VERSION,
        "run": {
            "run_id": run.get("run_id") or result.get("run_id"),
            "app_id": int(app_id),
            "status": run.get("status") or result.get("status") or "completed",
            "created_at": run.get("created_at") or result.get("created_at"),
            "completed_at": run.get("completed_at") or result.get("completed_at"),
            "stale": bool(result.get("stale")),
            "stale_reason": result.get("stale_reason"),
        },
        "readiness": {
            "research_ready": bool(report),
            "semantic_ready": bool(semantic_result),
            "status": "ready" if report else "unavailable",
        },
        "research_snapshot": _research_snapshot(report if isinstance(report, Mapping) else None),
        "segments": _segments_projection(report if isinstance(report, Mapping) else None),
        "semantic": semantic,
        "player_voice": {
            "actionable_topics": {"items": [_metric_row(row, count_key="topic_n", share_key="topic_share", validation_key="topic_validation") for row in actionable[:5]], "total_count": len(actionable)},
            "issues": {"items": [_metric_row(row, count_key="issue_n", share_key="issue_share", validation_key="issue_validation") for row in issue_rows[:5]], "total_count": len(issue_rows)},
            "requests": {"items": [_metric_row(row, count_key="request_n", share_key="request_share", validation_key="request_validation") for row in request_rows[:5]], "total_count": len(request_rows)},
            "context_topics": {"items": [_metric_row(row, count_key="topic_n", share_key="topic_share", validation_key="topic_validation") for row in context], "total_count": len(context)},
            "primary_topics": [_metric_row(row, count_key="primary_n", share_key="primary_share", validation_key="topic_validation") for row in primary_rows[:10]],
        },
        "discovery": _discovery_projection(discovery),
        "evidence": {
            "run_id": run.get("run_id") or result.get("run_id"),
            "endpoint": f"/analysis/{app_id}/evidence",
            "verified_evidence_available": None,
            "verified_evidence_count": None,
            "source_reviews_are_frozen": bool(run.get("run_id") or result.get("run_id")),
        },
        "provenance": {
            "run_id": run.get("run_id") or result.get("run_id"),
            "population_fingerprint": population_fp,
            "measurement_bundle_id": run.get("measurement_bundle_id") or ((semantic_result or {}).get("provenance") or {}).get("measurement_bundle_id"),
            "materialization_id": run.get("classification_materialization_id") or (semantic_result or {}).get("classification_materialization_id"),
            "semantic_result_fingerprint": (semantic_result or {}).get("semantic_measurement_result_fingerprint"),
            "taxonomy_version": semantic.get("taxonomy_version"),
            "provider": semantic.get("provider"),
            "model": semantic.get("model"),
            "prompt_version": semantic.get("prompt_version"),
            "schema_version": semantic.get("schema_version"),
            "measurement_status": semantic.get("measurement_status"),
            "validation_status": semantic.get("validation_status"),
        },
        "limitations": list(dict.fromkeys(str(item) for item in limitations if item)),
        "legacy": {"available": bool(result.get("insights") or result.get("reviews"))},
    }


__all__ = ["PRESENTATION_SCHEMA_VERSION", "build_dashboard_presentation"]
