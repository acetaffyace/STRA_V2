"""Read-only canonical comparison projections.

Comparison is deliberately kept separate from the research engines.  This
module only reads persisted run/window results, checks whether the two sides
can be compared, and formats deltas whose ownership remains in the canonical
result contracts.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from . import storage


COMPARISON_SCHEMA_VERSION = "research-comparison-v1"
_SAMPLING_KEYS = (
    "languages",
    "review_type",
    "purchase_type",
    "collection_order",
    "include_offtopic_activity",
    "max_reviews",
)
_IDENTITY_KEYS = (
    "measurement_bundle_id",
    "taxonomy_snapshot_id",
    "taxonomy_fingerprint",
    "provider",
    "model_id",
    "prompt_version",
    "schema_version",
    "measurement_status",
    "claim_status",
    "validation_status",
)
_REQUIRED_IDENTITY_KEYS = _IDENTITY_KEYS


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    """Parse non-contract row counts used for ranking and display."""
    return _optional_int(value) or 0


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quantitative(report: Mapping[str, Any] | None) -> dict[str, Any]:
    report = report or {}
    population = report.get("population") or {}
    recommendation = report.get("recommendation") or {}
    rec_population = recommendation.get("population") or {}
    rate = _float(rec_population.get("recommendation_rate"))
    sampling = population.get("sampling_contract") or {}
    return {
        "available": bool(report),
        "population_n": _optional_int(population.get("review_count")),
        "valid_n": _optional_int(rec_population.get("valid_n")),
        "recommended_n": _optional_int(rec_population.get("recommended_n")),
        "not_recommended_n": _optional_int(rec_population.get("not_recommended_n")),
        "recommendation_rate": rate,
        "confidence_interval": recommendation.get("model_based_interval") or recommendation.get("confidence_interval"),
        "scope": {
            "start_time": sampling.get("start_time"),
            "end_time": sampling.get("end_time"),
            "languages": list(sampling.get("languages") or []),
            "review_type": sampling.get("review_type"),
            "purchase_type": sampling.get("purchase_type"),
            "collection_order": sampling.get("collection_order"),
            "include_offtopic_activity": sampling.get("include_offtopic_activity"),
            "max_reviews": sampling.get("max_reviews"),
        },
        "collection_complete": population.get("collection_complete"),
        "truncated_by_max_reviews": population.get("truncated_by_max_reviews"),
        "stop_reason": population.get("stop_reason"),
        "coverage": population.get("coverage_status"),
    }


def _semantic(result: Mapping[str, Any] | None, provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = result or {}
    if not result:
        return {"available": False, "topics": [], "issues": [], "requests": [], "primary_topics": [], "identity": {}}
    result_provenance = result.get("provenance") or {}
    provenance = {**dict(provenance or {}), **dict(result_provenance)}

    def rows(count_key: str, share_key: str, validation_key: str) -> list[dict[str, Any]]:
        output = []
        for row in result.get("topics") or []:
            count = _int(row.get(count_key))
            if count <= 0:
                continue
            output.append({
                "taxonomy_key": str(row.get("taxonomy_key") or ""),
                "n": count,
                "share": _float(row.get(share_key)),
                "validation": deepcopy(row.get(validation_key)),
            })
        return sorted(output, key=lambda item: (-(_float(item.get("share")) or 0.0), item["taxonomy_key"]))

    identity = {
        "measurement_bundle_id": provenance.get("measurement_bundle_id"),
        "taxonomy_snapshot_id": provenance.get("taxonomy_snapshot_id"),
        "taxonomy_fingerprint": provenance.get("taxonomy_fingerprint"),
        "provider": provenance.get("classifier_provider") or provenance.get("provider"),
        "model_id": provenance.get("classifier_model_id") or provenance.get("model_id"),
        "prompt_version": provenance.get("classifier_prompt_version") or provenance.get("prompt_version"),
        "schema_version": provenance.get("classifier_schema_version") or provenance.get("schema_version"),
        "measurement_status": provenance.get("measurement_status") or result.get("measurement_status"),
        "claim_status": result.get("claim_status"),
        "validation_status": provenance.get("validation_status") or result.get("validation_status"),
    }
    return {
        "available": True,
        "population_n": _optional_int(result.get("population_n")),
        "classified_n": _optional_int(result.get("classified_n")),
        "coverage": _float(result.get("classification_coverage")),
        "claim_status": result.get("claim_status"),
        "measurement_status": identity["measurement_status"],
        "topics": rows("topic_n", "topic_share", "topic_validation"),
        "issues": rows("issue_n", "issue_share", "issue_validation"),
        "requests": rows("request_n", "request_share", "request_validation"),
        "primary_topics": rows("primary_n", "primary_share", "topic_validation"),
        "identity": identity,
        "semantic_result_fingerprint": result.get("semantic_measurement_result_fingerprint"),
    }


def build_comparison_side(
    *,
    source_kind: str,
    source_id: str,
    app_id: int,
    research_report: Mapping[str, Any] | None,
    semantic_result: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    extra_scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one side from already-persisted canonical data.

    Callers must provide exact persisted data.  This function never fetches,
    classifies, embeds, clusters, or falls back to mutable game rows.
    """
    quantitative = _quantitative(research_report)
    if extra_scope:
        quantitative["scope"].update(dict(extra_scope))
    identity = dict(provenance or {})
    semantic = _semantic(semantic_result, identity)
    return {
        "source_kind": source_kind,
        "source_id": str(source_id),
        "app_id": int(app_id),
        "scope": deepcopy(quantitative["scope"]),
        "quantitative": quantitative,
        "semantic": semantic,
        "availability": {
            "quantitative": bool(quantitative["available"]),
            "semantic": bool(semantic["available"]),
        },
        "internal_provenance": {
            "population_fingerprint": identity.get("population_fingerprint"),
            "measurement_bundle_id": identity.get("measurement_bundle_id") or semantic["identity"].get("measurement_bundle_id"),
            "taxonomy_snapshot_id": identity.get("taxonomy_snapshot_id") or semantic["identity"].get("taxonomy_snapshot_id"),
            "taxonomy_fingerprint": identity.get("taxonomy_fingerprint") or semantic["identity"].get("taxonomy_fingerprint"),
            "provider": identity.get("provider") or semantic["identity"].get("provider"),
            "model_id": identity.get("model_id") or semantic["identity"].get("model_id"),
            "prompt_version": identity.get("prompt_version") or semantic["identity"].get("prompt_version"),
            "schema_version": identity.get("schema_version") or semantic["identity"].get("schema_version"),
            "measurement_status": identity.get("measurement_status") or semantic["identity"].get("measurement_status"),
            "validation_status": identity.get("validation_status") or semantic["identity"].get("validation_status"),
            "semantic_result_fingerprint": semantic.get("semantic_result_fingerprint"),
        },
    }


def _side_from_run(run_id: str) -> dict[str, Any]:
    run = storage.get_analysis_run(run_id)
    if not run:
        raise ValueError("comparison_run_not_found")
    result = storage.get_analysis_run_result(run_id)
    if not result:
        raise ValueError("comparison_run_result_unavailable")
    semantic = result.get("semantic_measurement_result")
    return build_comparison_side(
        source_kind="analysis_run",
        source_id=run_id,
        app_id=int(run.get("target_app_id") or result.get("app_id") or 0),
        research_report=result.get("research_report"),
        semantic_result=semantic,
        provenance={
            "population_fingerprint": (result.get("metadata") or {}).get("population_fingerprint"),
            "measurement_bundle_id": run.get("measurement_bundle_id"),
            "taxonomy_snapshot_id": run.get("taxonomy_snapshot_id"),
            "taxonomy_fingerprint": run.get("taxonomy_fingerprint"),
            "provider": run.get("provider"),
            "model_id": run.get("model_id"),
            "prompt_version": run.get("prompt_version"),
            "schema_version": run.get("analysis_version"),
            "measurement_status": run.get("measurement_status"),
            "validation_status": run.get("validation_status"),
        },
    )


def _sampling_value(side: Mapping[str, Any], key: str) -> Any:
    return (side.get("quantitative") or {}).get("scope", {}).get(key)


def _sampling_equivalence(left: Mapping[str, Any], right: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for key in _SAMPLING_KEYS:
        l_value, r_value = _sampling_value(left, key), _sampling_value(right, key)
        if key == "languages":
            l_value, r_value = sorted(l_value or []), sorted(r_value or [])
        if l_value != r_value:
            reasons.append(f"sampling_{key}_mismatch")
    return not reasons, reasons


def _semantic_identity(left: Mapping[str, Any], right: Mapping[str, Any]) -> tuple[bool, list[str]]:
    if not (left.get("available") and right.get("available")):
        return False, ["semantic_missing_one_side"]
    left_identity, right_identity = left.get("identity") or {}, right.get("identity") or {}
    reasons: list[str] = []
    for key in _REQUIRED_IDENTITY_KEYS:
        if not left_identity.get(key):
            reasons.append(f"semantic_identity_incomplete_{key}")
        if not right_identity.get(key):
            right_reason = f"semantic_identity_incomplete_{key}"
            if right_reason not in reasons:
                reasons.append(right_reason)
    if reasons:
        return False, reasons
    for key in _IDENTITY_KEYS:
        if left_identity.get(key) != right_identity.get(key):
            reasons.append(f"semantic_{key}_mismatch")
    return not reasons, reasons


def _delta_rows(left_rows: list[Mapping[str, Any]], right_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    left_by_key = {str(row.get("taxonomy_key")): row for row in left_rows}
    right_by_key = {str(row.get("taxonomy_key")): row for row in right_rows}
    rows = []
    for key in sorted(set(left_by_key) | set(right_by_key)):
        left, right = left_by_key.get(key) or {}, right_by_key.get(key) or {}
        left_share, right_share = _float(left.get("share")), _float(right.get("share"))
        rows.append({
            "taxonomy_key": key,
            "left_n": _int(left.get("n")),
            "right_n": _int(right.get("n")),
            "left_share": left_share,
            "right_share": right_share,
            "delta_pp": round((right_share - left_share) * 100, 6) if left_share is not None and right_share is not None else None,
        })
    return sorted(rows, key=lambda row: (-abs(row["delta_pp"] or 0), row["taxonomy_key"]))


def build_research_comparison(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    """Build the shared ``research-comparison-v1`` read projection."""
    left = deepcopy(dict(left))
    right = deepcopy(dict(right))
    left_q, right_q = left.get("quantitative") or {}, right.get("quantitative") or {}
    quantitative_comparable = bool(left_q.get("available") and right_q.get("available"))
    sampling_equivalent, sampling_reasons = _sampling_equivalence(left, right)
    left_scope, right_scope = left.get("scope") or {}, right.get("scope") or {}
    scope_equivalent = left_scope == right_scope
    reasons = list(sampling_reasons)
    if not scope_equivalent and not sampling_reasons:
        reasons.append("time_window_different_by_design")

    left_semantic, right_semantic = left.get("semantic") or {}, right.get("semantic") or {}
    semantic_side_by_side = bool(left_semantic.get("available") or right_semantic.get("available"))
    semantic_delta_comparable, semantic_reasons = _semantic_identity(left_semantic, right_semantic)
    reasons.extend(reason for reason in semantic_reasons if reason not in reasons)

    left_rate, right_rate = _float(left_q.get("recommendation_rate")), _float(right_q.get("recommendation_rate"))
    quantitative_delta = {
        "recommendation_rate_delta_pp": round((right_rate - left_rate) * 100, 6) if quantitative_comparable and left_rate is not None and right_rate is not None else None,
    }
    semantic_delta = None
    if semantic_delta_comparable:
        semantic_delta = {
            "topics": _delta_rows(left_semantic.get("topics") or [], right_semantic.get("topics") or []),
            "issues": _delta_rows(left_semantic.get("issues") or [], right_semantic.get("issues") or []),
            "requests": _delta_rows(left_semantic.get("requests") or [], right_semantic.get("requests") or []),
            "primary_topics": _delta_rows(left_semantic.get("primary_topics") or [], right_semantic.get("primary_topics") or []),
        }
    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "left": left,
        "right": right,
        "compatibility": {
            "quantitative_comparable": quantitative_comparable,
            "sampling_method_equivalent": sampling_equivalent,
            "scope_equivalent": scope_equivalent,
            "semantic_side_by_side_available": semantic_side_by_side,
            "semantic_delta_comparable": semantic_delta_comparable,
            "reasons": reasons,
        },
        "quantitative": quantitative_delta,
        "semantic": {
            "delta_comparable": semantic_delta_comparable,
            "delta": semantic_delta,
        },
    }


def build_research_comparison_for_runs(left_run_id: str, right_run_id: str) -> dict[str, Any]:
    """Load two exact persisted general-analysis runs and compare them."""
    return build_research_comparison(_side_from_run(left_run_id), _side_from_run(right_run_id))


def build_version_window_comparison(
    *,
    run_id: str,
    app_id: int,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, Any]:
    """Adapt persisted Version Review V2 windows to the shared contract.

    Version Review windows are already persisted by its V2 executor.  The
    adapter does not inspect raw reviews or recompute rates; it only maps the
    stored window metrics into two ``version_window`` sides.
    """
    def side(label: str, value: Mapping[str, Any]) -> dict[str, Any]:
        reviews = _optional_int(value.get("reviews"))
        rate = _float(value.get("recommendation_rate"))
        # Version Review V2 calculates this rate over every persisted review
        # in the window, so the denominator is exact.  It does not persist
        # the positive/negative split, which must remain unknown rather than
        # being reconstructed from a rounded rate.
        report = {
            "population": {
                "review_count": reviews,
                "sampling_contract": value.get("sampling_contract") or {},
                "collection_complete": value.get("collection_complete"),
                "truncated_by_max_reviews": value.get("truncated_by_max_reviews"),
                "stop_reason": value.get("stop_reason"),
                "coverage_status": value.get("coverage_status"),
            },
            "recommendation": {"population": {"valid_n": reviews, "recommended_n": None, "not_recommended_n": None, "recommendation_rate": rate}},
        }
        return build_comparison_side(source_kind="version_window", source_id=f"{run_id}:{label}", app_id=app_id, research_report=report, provenance={})

    return build_research_comparison(side("left", left), side("right", right))


__all__ = [
    "COMPARISON_SCHEMA_VERSION",
    "build_comparison_side",
    "build_research_comparison",
    "build_research_comparison_for_runs",
    "build_version_window_comparison",
]
