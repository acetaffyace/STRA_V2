"""Version Comparison V3 API.

The V3 path keeps raw population acquisition deterministic and provider-free.
LLM classification is imported lazily only after a comparable semantic sample
manifest has been built.
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from .. import acquisition, storage
from ..version_comparison import (
    COHORTS,
    SENSITIVITY_WINDOWS,
    build_sampling_contracts,
    build_semantic_sample_manifest,
    chronological_events,
    cohort_overlap_report,
    cohort_windows,
    comparability_matrix,
    confounder_events,
    event_is_usable,
    primary_cohorts,
    raw_comparison,
    semantic_comparison,
    semantic_reviews_from_manifest,
    standardization_sensitivity,
)

router = APIRouter(prefix="/version-comparison", tags=["version-comparison-v3"])


class VersionComparisonRequest(BaseModel):
    app_id: int = Field(..., gt=0)
    event_a_id: str = Field(..., min_length=8, max_length=64)
    event_b_id: str = Field(..., min_length=8, max_length=64)
    window_days: Literal[3, 7, 14] = 7
    languages: list[str] = Field(default_factory=lambda: ["all"], min_length=1, max_length=20)
    max_reviews_per_cohort: int = Field(default=2000, ge=500, le=10000)
    analysis_mode: Literal["raw_only", "semantic"] = "semantic"
    semantic_budget: int = Field(default=4000, ge=0, le=10000)


def _event_for_response(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "app_id": event.get("app_id"),
        "event_name": event.get("event_name"),
        "event_date": str(event.get("event_date") or ""),
        "event_type": event.get("event_type"),
        "effective_at": event.get("effective_at"),
        "anchor_precision": event.get("anchor_precision"),
        "manual_verified": bool(event.get("manual_verified")),
        "event_status": event.get("event_status"),
    }


def _events(request: VersionComparisonRequest) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_a = storage.get_version_event(request.event_a_id)
    raw_b = storage.get_version_event(request.event_b_id)
    if raw_a is None or raw_b is None:
        raise HTTPException(status_code=404, detail="Version event not found.")
    if request.event_a_id == request.event_b_id:
        raise HTTPException(status_code=400, detail="Choose two different version events.")
    if int(raw_a.get("app_id") or 0) != request.app_id or int(raw_b.get("app_id") or 0) != request.app_id:
        raise HTTPException(status_code=400, detail="Both version events must belong to the selected game.")
    for event in (raw_a, raw_b):
        usable, reason = event_is_usable(event)
        if not usable:
            raise HTTPException(status_code=400, detail=f"Version event {event.get('event_id')} is not safe to anchor: {reason}.")
    return chronological_events(raw_a, raw_b)


def _request_guard(request: VersionComparisonRequest) -> None:
    if request.analysis_mode == "semantic" and request.semantic_budget < 4:
        raise HTTPException(status_code=400, detail="Semantic mode requires a total semantic budget of at least 4 reviews.")


def _event_warnings(event_a: dict[str, Any], event_b: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for label, event in (("A", event_a), ("B", event_b)):
        if not bool(event.get("manual_verified")):
            warnings.append(f"event_{label.lower()}_not_manually_verified")
    return warnings


def _plan(request: VersionComparisonRequest) -> dict[str, Any]:
    _request_guard(request)
    event_a, event_b = _events(request)
    primary = cohort_windows(event_a, event_b, request.window_days)
    overlap = cohort_overlap_report(event_a, event_b, request.window_days)
    catalog = storage.list_version_events(request.app_id)
    confounders = confounder_events(catalog, event_a, event_b, window_days=request.window_days)
    return {
        "schema_version": "version-comparison-plan-v3",
        "app_id": request.app_id,
        "event_a": _event_for_response(event_a),
        "event_b": _event_for_response(event_b),
        "orientation": "A=older,B=newer",
        "window_days": request.window_days,
        "acquisition_window_days": request.window_days,
        "sensitivity_windows": list(SENSITIVITY_WINDOWS),
        "cohorts": primary,
        "acquisition_cohorts": primary,
        "cohort_overlap": overlap,
        "analysis_mode": request.analysis_mode,
        "max_reviews_per_cohort": request.max_reviews_per_cohort,
        "languages": request.languages,
        "semantic_sampling": {
            "enabled": request.analysis_mode == "semantic",
            "total_budget": request.semantic_budget if request.analysis_mode == "semantic" else 0,
            "dimensions": ["language", "relative_day_bucket"],
            "target": "pooled_common_support",
            "equal_cohort_size": True,
            "balances_recommendation_outcome": False,
            "classifier_is_cohort_blind": True,
        },
        "raw_metrics": ["review_count", "recommendation_rate", "wilson_95_ci", "delta_a", "delta_b", "post_gap", "descriptive_delta_delta"],
        "confounders": confounders,
        "confounder_risk": "major" if any(item["severity"] == "major" for item in confounders) else "minor" if confounders else "clean",
        "warnings": _event_warnings(event_a, event_b),
    }


def _update_running(run_id: str, phase: str, progress: Optional[dict[str, Any]] = None) -> None:
    storage.save_analysis_run_metrics(run_id, {"schema_version": "version-comparison-v3-progress", "progress": progress or {}}, status="running", phase=phase)


def _reports_complete(reports: dict[str, dict[str, Any]]) -> bool:
    return all(bool(item.get("collection_complete")) and not bool(item.get("truncated_by_max_reviews")) for item in reports.values())


def _acquire_window(request: VersionComparisonRequest, event_a: dict[str, Any], event_b: dict[str, Any], days: int, *, run_id: str | None = None, phase_prefix: str = "acquiring") -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    contracts = build_sampling_contracts(
        request.app_id,
        event_a,
        event_b,
        window_days=days,
        languages=request.languages,
        max_reviews_per_cohort=request.max_reviews_per_cohort,
    )
    acquired: dict[str, list[dict[str, Any]]] = {}
    reports: dict[str, dict[str, Any]] = {}
    for index, cohort in enumerate(COHORTS, start=1):
        if run_id:
            _update_running(run_id, f"{phase_prefix}_{cohort.lower()}", {"stage": phase_prefix, "window_days": days, "cohort": cohort, "completed": index - 1, "total": len(COHORTS)})
        result = acquisition.ensure_reviews(contracts[cohort])
        acquired[cohort] = result.reviews
        report = result.to_dict()
        if (
            result.source == "cache"
            and contracts[cohort].max_reviews > 0
            and len(result.reviews) >= contracts[cohort].max_reviews
            and report.get("collection_complete")
            and not report.get("truncated_by_max_reviews")
        ):
            report["collection_complete"] = False
            report["truncated_by_max_reviews"] = True
            report["stop_reason"] = "cache_cap_boundary_ambiguous"
            report.setdefault("stats", {})["cache_cap_boundary_ambiguous"] = True
        reports[cohort] = report
    cohorts = primary_cohorts(acquired, event_a, event_b, days)
    return cohorts, reports


def _sensitivity_row(days: int, cohorts: dict[str, list[dict[str, Any]]], reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    comparison = raw_comparison(cohorts)
    return {
        "window_days": days,
        **comparison["deltas"],
        "counts": {cohort: len(cohorts.get(cohort, [])) for cohort in COHORTS},
        "coverage_status": "COMPLETE" if _reports_complete(reports) else "PARTIAL",
        "truncated_cohorts": [cohort for cohort, report in reports.items() if report.get("truncated_by_max_reviews")],
    }


def _execute(run_id: str, request_payload: dict[str, Any]) -> None:
    request = VersionComparisonRequest(**request_payload)
    try:
        event_a, event_b = _events(request)
        overlap = cohort_overlap_report(event_a, event_b, request.window_days)
        if overlap["status"] != "disjoint":
            raise ValueError("Selected version windows overlap; choose a shorter window or more separated events.")

        primary, primary_reports = _acquire_window(request, event_a, event_b, request.window_days, run_id=run_id, phase_prefix="acquiring_primary")
        raw = raw_comparison(primary)
        comparability = comparability_matrix(primary)
        standardization = standardization_sensitivity(primary)

        sensitivity: list[dict[str, Any]] = []
        sensitivity_reports: dict[str, Any] = {}
        for days in SENSITIVITY_WINDOWS:
            if days == request.window_days:
                cohorts, reports = primary, primary_reports
            else:
                cohorts, reports = _acquire_window(request, event_a, event_b, days, run_id=run_id, phase_prefix=f"acquiring_sensitivity_{days}d")
            sensitivity.append(_sensitivity_row(days, cohorts, reports))
            sensitivity_reports[str(days)] = reports

        catalog = storage.list_version_events(request.app_id)
        confounders = confounder_events(catalog, event_a, event_b, window_days=request.window_days)
        semantic_manifest = None
        semantic = None
        warnings = _event_warnings(event_a, event_b)
        primary_complete = _reports_complete(primary_reports)
        if not primary_complete:
            warnings.append("primary_acquisition_incomplete_or_capped: raw rates describe the observed bounded sample, not a complete Steam window.")
        incomplete_sensitivity = [str(row["window_days"]) for row in sensitivity if row["coverage_status"] != "COMPLETE"]
        if incomplete_sensitivity:
            warnings.append("sensitivity_windows_partial:" + ",".join(incomplete_sensitivity))

        if request.analysis_mode == "semantic":
            _update_running(run_id, "building_semantic_sample", {"stage": "semantic_sample"})
            semantic_manifest = build_semantic_sample_manifest(primary, event_a, event_b, total_budget=request.semantic_budget, seed=f"version-comparison:{request.app_id}:{event_a.get('event_id')}:{event_b.get('event_id')}:{request.window_days}")
            if semantic_manifest["status"] == "ready":
                selected_reviews = semantic_reviews_from_manifest(primary, semantic_manifest)
                if selected_reviews:
                    _update_running(run_id, "classifying_semantic_sample", {"stage": "semantic_classification", "completed": 0, "total": len(selected_reviews)})
                    from .. import llm
                    game_context = {}
                    try:
                        from ..steam_api import fetch_app_details
                        game_context = fetch_app_details(request.app_id) or {}
                    except Exception:
                        game_context = {}

                    def progress(processed: int, total: int) -> None:
                        _update_running(run_id, "classifying_semantic_sample", {"stage": "semantic_classification", "completed": processed, "total": total})

                    llm.ensure_review_labels(request.app_id, selected_reviews, progress_callback=progress, game_context=game_context)
                    labels = storage.load_review_labels(request.app_id)
                    semantic = semantic_comparison(primary, labels, semantic_manifest)
                    if semantic.get("status") != "ready":
                        warnings.append(f"semantic_status:{semantic.get('status')}")
            else:
                warnings.append("semantic_sample_insufficient_common_support")

        _update_running(run_id, "finalizing", {"stage": "finalizing"})
        metrics = {
            "schema_version": "version-comparison-v3",
            "event_a": _event_for_response(event_a),
            "event_b": _event_for_response(event_b),
            "orientation": "A=older,B=newer",
            "window_days": request.window_days,
            "acquisition_window_days": request.window_days,
            "analysis_mode": request.analysis_mode,
            "coverage_status": "COMPLETE" if primary_complete else "PARTIAL",
            "acquisition_report": {"primary": primary_reports, "sensitivity": sensitivity_reports},
            "raw": raw,
            "comparability": comparability,
            "standardization_sensitivity": standardization,
            "window_sensitivity": sensitivity,
            "cohort_overlap": overlap,
            "confounders": confounders,
            "confounder_risk": "major" if any(item["severity"] == "major" for item in confounders) else "minor" if confounders else "clean",
            "semantic_sample_manifest": semantic_manifest,
            "semantic": semantic,
            "warnings": warnings,
        }
        storage.save_analysis_run_metrics(run_id, metrics, status="completed", phase="completed")
    except Exception as exc:
        storage.save_analysis_run_metrics(run_id, {"schema_version": "version-comparison-v3", "warnings": [f"execution_failed:{type(exc).__name__}"]}, status="failed", error=str(exc), phase="failed")


@router.post("/plan")
def plan_version_comparison(request: VersionComparisonRequest) -> dict[str, Any]:
    return _plan(request)


@router.post("/start", status_code=202)
def start_version_comparison(request: VersionComparisonRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    plan = _plan(request)
    if plan["cohort_overlap"]["status"] != "disjoint":
        raise HTTPException(status_code=400, detail="Selected version windows overlap. Choose a shorter window or more separated version events.")
    run_id = uuid4().hex
    config = {
        "run_type": "version_comparison_v3",
        "analysis": {
            "analysis_mode": request.analysis_mode,
            "window_days": request.window_days,
            "semantic_budget": request.semantic_budget,
            "max_reviews_per_cohort": request.max_reviews_per_cohort,
            "languages": request.languages,
            "event_a_id": plan["event_a"]["event_id"],
            "event_b_id": plan["event_b"]["event_id"],
        },
        "comparison_plan": plan,
    }
    run = storage.create_analysis_run({"run_id": run_id, "target_app_id": request.app_id, "event_id": plan["event_b"]["event_id"], "config": config, "status": "created"})
    background_tasks.add_task(_execute, run_id, request.model_dump())
    return {"run": run, "plan": plan}


@router.get("/runs/{run_id}")
def get_version_comparison_run(run_id: str) -> dict[str, Any]:
    run = storage.get_analysis_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Version comparison run not found.")
    if (run.get("config") or {}).get("run_type") != "version_comparison_v3":
        raise HTTPException(status_code=404, detail="Version comparison run not found.")
    return run


@router.get("/runs")
def list_version_comparison_runs(app_id: Optional[int] = None, limit: int = 20) -> list[dict[str, Any]]:
    runs = storage.list_analysis_runs(app_id=app_id)
    filtered = [item for item in runs if (item.get("config") or {}).get("run_type") == "version_comparison_v3"]
    return filtered[: max(1, min(limit, 100))]
