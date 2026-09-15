"""Version Comparison V3 routes: four raw cohorts plus optional semantic layer."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..acquisition import ensure_reviews
from ..steam_api import fetch_app_details
from ..version_comparison import (
    COHORTS,
    build_sampling_contracts,
    build_semantic_sample_manifest,
    chronological_events,
    cohort_windows,
    comparability_matrix,
    confounder_events,
    primary_cohorts,
    raw_comparison,
    semantic_comparison,
    semantic_reviews_from_manifest,
    standardization_sensitivity,
    window_sensitivity,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/version-comparison", tags=["version-comparison-v3"])


class VersionComparisonRequest(BaseModel):
    app_id: int = Field(..., gt=0)
    event_a_id: str = Field(..., min_length=8, max_length=64)
    event_b_id: str = Field(..., min_length=8, max_length=64)
    window_days: Literal[3, 7, 14] = 7
    languages: list[str] = Field(default_factory=lambda: ["all"], min_length=1, max_length=20)
    max_reviews_per_cohort: int = Field(default=10_000, ge=500, le=10_000)
    analysis_mode: Literal["raw_only", "semantic"] = "semantic"
    semantic_budget: int = Field(default=4_000, ge=0, le=10_000)


def _events(request: VersionComparisonRequest) -> tuple[dict, dict]:
    event_a = storage.get_version_event(request.event_a_id)
    event_b = storage.get_version_event(request.event_b_id)
    if event_a is None or event_b is None:
        raise HTTPException(status_code=404, detail="One or both version events were not found.")
    if int(event_a.get("app_id") or 0) != request.app_id or int(event_b.get("app_id") or 0) != request.app_id:
        raise HTTPException(status_code=400, detail="Both version events must belong to the selected game.")
    if request.event_a_id == request.event_b_id:
        raise HTTPException(status_code=400, detail="Choose two different version events.")
    return chronological_events(event_a, event_b)


def _plan(request: VersionComparisonRequest) -> dict:
    older, newer = _events(request)
    acquisition_days = max(14, request.window_days)
    primary = cohort_windows(older, newer, request.window_days)
    acquisition = cohort_windows(older, newer, acquisition_days)
    confounders = confounder_events(storage.list_version_events(request.app_id), older, newer, window_days=acquisition_days)
    return {
        "schema_version": "version-comparison-plan-v3",
        "app_id": request.app_id,
        "event_a": older,
        "event_b": newer,
        "orientation": "A=older,B=newer",
        "window_days": request.window_days,
        "acquisition_window_days": acquisition_days,
        "cohorts": primary,
        "acquisition_cohorts": acquisition,
        "analysis_mode": request.analysis_mode,
        "max_reviews_per_cohort": request.max_reviews_per_cohort,
        "languages": request.languages,
        "semantic_sampling": {
            "enabled": request.analysis_mode == "semantic" and request.semantic_budget > 0,
            "total_budget": request.semantic_budget,
            "dimensions": ["language", "relative_day_bucket"],
            "target": "pooled_common_support",
            "equal_cohort_size": True,
            "balances_recommendation_outcome": False,
            "classifier_is_cohort_blind": True,
        },
        "raw_metrics": [
            "review_count", "recommendation_rate", "recommendation_ci95",
            "A_pre_post_delta", "B_pre_post_delta", "B_post_minus_A_post",
            "difference_in_differences", "population_comparability",
            "composition_standardization_sensitivity", "3_7_14_day_window_sensitivity",
        ],
        "confounders": confounders,
        "confounder_risk": "major" if any(item["severity"] == "major" for item in confounders) else "minor" if confounders else "clean",
    }


@router.post("/plan")
def plan_version_comparison(request: VersionComparisonRequest) -> dict:
    """Build the four-cohort contract. This endpoint never invokes an LLM."""
    return _plan(request)


def _execute(run_id: str) -> None:
    run = storage.get_analysis_run(run_id)
    if run is None:
        return
    config = run.get("config") or {}
    request_payload = config.get("version_comparison_request") or {}
    try:
        request = VersionComparisonRequest(**request_payload)
        older, newer = _events(request)
        acquisition_days = max(14, request.window_days)
        contracts = build_sampling_contracts(
            request.app_id, older, newer, window_days=acquisition_days,
            languages=request.languages, max_reviews_per_cohort=request.max_reviews_per_cohort,
        )

        acquired: dict[str, list[dict]] = {}
        acquisition_report: dict[str, dict] = {}
        for index, cohort in enumerate(COHORTS, start=1):
            storage.save_analysis_run_metrics(
                run_id,
                {"schema_version": "version-comparison-v3", "progress": {"stage": "acquisition", "cohort": cohort, "completed": index - 1, "total": 4}},
                status="running", phase=f"acquiring_{cohort.lower()}",
            )
            result = ensure_reviews(contracts[cohort])
            acquired[cohort] = result.reviews
            acquisition_report[cohort] = {"contract": contracts[cohort].to_dict(), **result.to_dict()}

        primary = primary_cohorts(acquired, older, newer, request.window_days)
        raw = raw_comparison(primary)
        comparability = comparability_matrix(primary)
        standardization = standardization_sensitivity(primary)
        sensitivity = window_sensitivity(acquired, older, newer)
        confounders = confounder_events(storage.list_version_events(request.app_id), older, newer, window_days=acquisition_days)
        all_complete = all(bool(acquisition_report[c].get("collection_complete")) and not bool(acquisition_report[c].get("truncated_by_max_reviews")) for c in COHORTS)

        metrics: dict = {
            "schema_version": "version-comparison-v3",
            "event_a": older,
            "event_b": newer,
            "orientation": "A=older,B=newer",
            "window_days": request.window_days,
            "acquisition_window_days": acquisition_days,
            "analysis_mode": request.analysis_mode,
            "acquisition": acquisition_report,
            "coverage_status": "COMPLETE" if all_complete else "PARTIAL",
            "raw": raw,
            "comparability": comparability,
            "standardization_sensitivity": standardization,
            "window_sensitivity": sensitivity,
            "confounders": confounders,
            "confounder_risk": "major" if any(item["severity"] == "major" for item in confounders) else "minor" if confounders else "clean",
            "semantic": None,
            "semantic_sample_manifest": None,
            "warnings": [
                "Steam reviews are self-selected observational data and do not establish causality.",
                *([] if all_complete else ["At least one acquisition window is capped or incomplete; raw population metrics should be interpreted as partial coverage."]),
            ],
        }

        if request.analysis_mode == "semantic" and request.semantic_budget > 0:
            storage.save_analysis_run_metrics(run_id, metrics, status="running", phase="building_semantic_sample")
            manifest = build_semantic_sample_manifest(
                primary, older, newer, total_budget=request.semantic_budget,
                seed=f"{request.app_id}:{older.get('event_id')}:{newer.get('event_id')}:semantic-v1",
            )
            metrics["semantic_sample_manifest"] = manifest
            if manifest.get("status") == "ready":
                selected_reviews = semantic_reviews_from_manifest(primary, manifest)
                storage.save_analysis_run_metrics(run_id, metrics, status="running", phase="classifying_semantic_sample")
                from .. import llm
                game_context = fetch_app_details(request.app_id) or {}
                with llm.llm_usage_context(
                    app_id=request.app_id, run_id=run_id, phase="classifying", operation="version_comparison_v3",
                    prompt_version=llm.active_classifier_prompt_version(), taxonomy_version=llm.TAXONOMY_VERSION,
                    requested_review_count=len(selected_reviews),
                ):
                    llm.ensure_review_labels(request.app_id, selected_reviews, game_context=game_context)
                labels = storage.load_review_labels(request.app_id)
                metrics["semantic"] = semantic_comparison(primary, labels, manifest)
            else:
                metrics["semantic"] = {"status": "insufficient_common_support", "topics": [], "problems": [], "requests": [], "positives": []}
                metrics["warnings"].append("Semantic comparison could not form common language × lifecycle-day support across all four cohorts.")

        metrics["progress"] = {"stage": "completed", "completed": 4, "total": 4}
        storage.save_analysis_run_metrics(run_id, metrics, status="completed", phase="finalizing")
    except Exception as exc:
        logger.exception("Version comparison V3 failed for run %s", run_id)
        storage.save_analysis_run_metrics(run_id, {"schema_version": "version-comparison-v3"}, status="failed", error=str(exc), phase="failed")


@router.post("/start", status_code=202)
def start_version_comparison(request: VersionComparisonRequest, background_tasks: BackgroundTasks) -> dict:
    plan = _plan(request)
    run_id = uuid4().hex
    config = {
        "run_id": run_id,
        "run_type": "version_comparison_v3",
        "target_game": {"appid": request.app_id},
        "analysis": {"analysis_goal": "version_comparison_v3", "window_days": request.window_days, "analysis_mode": request.analysis_mode, "semantic_budget": request.semantic_budget},
        "version_comparison_request": request.model_dump(mode="json"),
        "manifest": {"created_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": "version-comparison-v3", "sampling_method": "pooled_common_support_language_relative_day_v1"},
    }
    created = storage.create_analysis_run({"run_id": run_id, "target_app_id": request.app_id, "event_id": plan["event_b"].get("event_id"), "config": config, "status": "created"})
    storage.save_analysis_run_metrics(run_id, {"schema_version": "version-comparison-v3", "plan": plan}, status="running", phase="planning")
    background_tasks.add_task(_execute, run_id)
    return {"run": {**created, "status": "running"}, "plan": plan}


@router.get("/runs/{run_id}")
def get_version_comparison_run(run_id: str) -> dict:
    run = storage.get_analysis_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Version comparison run not found.")
    config = run.get("config") or {}
    if config.get("run_type") != "version_comparison_v3" and (config.get("analysis") or {}).get("analysis_goal") != "version_comparison_v3":
        raise HTTPException(status_code=404, detail="Run is not a Version Comparison V3 run.")
    return run


@router.get("/runs")
def list_version_comparison_runs(app_id: int | None = None, limit: int = 20) -> list[dict]:
    runs = storage.list_analysis_runs(app_id)
    selected = []
    for run in runs:
        config = run.get("config") or {}
        if config.get("run_type") == "version_comparison_v3" or (config.get("analysis") or {}).get("analysis_goal") == "version_comparison_v3":
            selected.append(run)
        if len(selected) >= max(1, min(limit, 100)):
            break
    return selected
