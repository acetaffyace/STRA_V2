"""Authoritative Web dashboard readiness contract.

This deliberately separates review ingestion from semantic analysis.  The
dashboard must never turn an absent result into analytical zeros.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from . import storage


def build_dashboard_payload(app_id: int, requested_run_id: Optional[str] = None) -> Dict[str, Any]:
    if requested_run_id:
        run = storage.get_analysis_run(requested_run_id)
        if not run or int(run.get("target_app_id")) != int(app_id):
            raise KeyError("该分析运行不存在或当前数据库不包含该运行。")
        result = storage.get_analysis_run_result(requested_run_id)
        if not result and run.get("run_type") == "version_review":
            result = {
                "run_id": requested_run_id,
                "app_id": app_id,
                "metadata": (run.get("config") or {}).get("metadata") or {},
                "insights": run.get("metrics"),
                "reviews": [],
                "status": run.get("status"),
                "error": run.get("error"),
            }
        if not result and run.get("status") == "completed":
            raise KeyError("该分析运行已完成，但 immutable result 不可用。")
    else:
        result = storage.load_analysis_result(app_id)
    review_count = storage.count_reviews(app_id)
    active_run = None if requested_run_id else storage.get_active_general_analysis(app_id)
    # An active immutable run outranks the compatibility/latest row.  The
    # latter may still contain a previous failure or completed result while a
    # fresh Web Analyze is classifying the same app.
    run_id = requested_run_id or (active_run or {}).get("run_id") or (result or {}).get("run_id")
    run = run if requested_run_id else (active_run or (storage.get_analysis_run(run_id) if run_id else None))
    try:
        immutable_result = storage.get_analysis_run_result(run_id) if run_id else None
    except Exception:
        # Compatibility-contract unit tests and legacy databases may not yet
        # expose the immutable result table; readiness remains conservative.
        immutable_result = None
    effective_result = None if active_run else result
    status = str((result or {}).get("status") or (run or {}).get("status") or "")
    metadata = (effective_result or {}).get("metadata") or {}
    insights = (effective_result or {}).get("insights")
    if run_id:
        metadata = dict(metadata)
        metadata.setdefault("run_id", run_id)

    provenance = (insights or {}).get("metric_provenance") or {}
    coverage = provenance.get("classification_coverage") or {}
    classified_count = coverage.get("numerator")
    if classified_count is None:
        classified_count = (run or {}).get("classified_count")
    if classified_count is None:
        classified_count = metadata.get("classification_population")
    classified_count = int(classified_count or 0)
    population = int(
        (run or {}).get("analysis_population_count")
        or metadata.get("analysis_population_count")
        or metadata.get("classification_population")
        or review_count
        or metadata.get("retrieved")
        or 0
    )
    exact_run_review_count = int(
        (run or {}).get("analysis_population_count")
        or metadata.get("analysis_population_count")
        or (run or {}).get("deduplicated_count")
        or metadata.get("deduplicated_count")
        or metadata.get("retrieved")
        or review_count
    )
    coverage_rate = (classified_count / population) if population else 0.0
    five_questions = (insights or {}).get("five_questions")
    design = storage.get_analysis_design(run_id) if run_id else None

    if status == "running":
        state = "ANALYSIS_RUNNING"
    elif status == "failed":
        state = "ANALYSIS_FAILED"
    elif result is None:
        state = "REVIEWS_READY" if review_count else "ANALYSIS_NOT_STARTED"
    elif status == "completed":
        # A completed compatibility row is not enough.  The semantic layer
        # must have validated classifications attached to the same run.
        state = "ANALYSIS_READY" if immutable_result and insights and five_questions and classified_count > 0 else "ANALYSIS_INCOMPATIBLE"
    else:
        state = "ANALYSIS_NOT_STARTED" if review_count else "ANALYSIS_INCOMPATIBLE"

    return {
        "app_id": app_id,
        "readiness": {
            "state": state,
            "review_count": exact_run_review_count,
            "classified_count": classified_count,
            "classification_coverage": round(coverage_rate, 6),
            "run_id": run_id,
            "run_status": status or None,
            "result_available": bool(status == "completed" and insights and immutable_result),
            "analysis_mode": metadata.get("mode"),
            "result_source": metadata.get("source"),
            "analysis_window": {"start": metadata.get("window_start"), "end": metadata.get("window_end")},
            "analysis_design_available": bool(design),
            "five_questions_available": bool(five_questions),
            "evidence_available": bool(status == "completed" and classified_count),
            "semantic_engine": {
                "available": bool(classified_count),
                "mode": metadata.get("mode"),
                "reason": None if classified_count else "No validated semantic classifications are attached to this run.",
            },
        },
        "metadata": metadata or None,
        "insights": insights,
        "reviews": (effective_result or {}).get("reviews") or [],
        "error": (effective_result or {}).get("error"),
    }
