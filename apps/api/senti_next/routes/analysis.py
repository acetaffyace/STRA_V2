"""Analysis-related endpoints: /analyze, /progress/*, /analysis/*, /reanalyze, /summarize/*."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from .. import storage, llm, db as db_module, dialect as d
from ..steam_api import fetch_app_details, fetch_news_for_app, SteamAPIError
from ..sampling import SamplingContract
from ..acquisition_provenance import derive_acquisition_coverage as _derive_acquisition_coverage
from ..insights import prepare_insights
from ..analysis import recommended_share_over_time
from ..adaptive_analysis import build_analysis_design, infer_game_profile
from ..five_questions import build_five_question_contract
from ..research_core import build_snapshot_research_report
from .. import (
    fetch_reviews,
    fetch_reviews_multi_language,
    build_reviews_dataframe,
)
from ._shared import (
    AnalyzeMetadata,
    SAMPLE_LIMIT,
    FETCH_LIMIT,
    REVIEW_EXPORT_COLUMNS,
)
from ..web_contract import build_dashboard_payload

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    app_id: int = Field(..., gt=0)
    review_count: int = Field(FETCH_LIMIT, ge=0, le=10000, description="Legacy alias for sampling.max_reviews; 0 means unlimited")
    language: str = Field("all", min_length=2, max_length=32)
    languages: Optional[List[str]] = Field(None, description="List of language codes for multi-language analysis")
    filter: str = Field("recent")
    day_range: Optional[int] = Field(None, ge=1, le=365)
    persist: bool = Field(True)
    refresh: bool = Field(False)
    refresh_days: Optional[int] = Field(None, ge=1, le=365, description="Only fetch reviews from the last N days")
    output_language: str = Field("zh", min_length=2, max_length=8, description="Language for generated summaries: zh, en, or ja")
    sampling: Optional[SamplingContract] = Field(default=None, description="Explicit Steam research population contract")


class LabelReuseEstimate(BaseModel):
    total_reviews: int
    cached_reviews: int
    llm_reviews: int
    needs_refresh_reviews: int
    empty_reviews: int
    short_reviews: int
    reasons: Dict[str, int] = Field(default_factory=dict)


class AnalyzeResponse(BaseModel):
    metadata: AnalyzeMetadata
    insights: Optional[dict]
    reviews: List[dict]
    label_estimate: Optional[LabelReuseEstimate] = None
    run_id: Optional[str] = None


class AnalyzeEstimateResponse(BaseModel):
    app_id: int
    will_fetch: bool
    will_persist: bool
    review_count_requested: int
    reviews_considered: int
    cached_labels_total: int
    cached_reviews: int
    needs_refresh_reviews: int
    empty_reviews: int
    short_reviews: int
    llm_reviews: int
    prompt_version: str
    model_id: str
    labeling_strategy: str
    reasons: Dict[str, int] = Field(default_factory=dict)


class AnalysisStatusResponse(BaseModel):
    status: str
    metadata: Optional[AnalyzeMetadata] = None
    insights: Optional[dict] = None
    research_report: Optional[dict] = None
    semantic_status: Optional[dict] = None
    reviews: List[dict] = Field(default_factory=list)
    error: Optional[str] = None
    run_id: Optional[str] = None
    snapshot_hash: Optional[str] = None
    stale: bool = False
    stale_reason: Optional[str] = None
    data_refreshed: bool = False


class DashboardPayloadResponse(BaseModel):
    app_id: int
    readiness: Dict[str, Any]
    metadata: Optional[dict] = None
    insights: Optional[dict] = None
    research_report: Optional[dict] = None
    semantic_status: Optional[dict] = None
    reviews: List[dict] = Field(default_factory=list)
    error: Optional[str] = None


class EvidenceResponse(BaseModel):
    run_id: Optional[str] = None
    app_id: int
    taxonomy_key: str
    matched_review_count: int
    verified_evidence_count: int
    page_count: int
    page_size: int
    offset: int
    items: List[dict] = Field(default_factory=list)


class ReviewItem(BaseModel):
    review_id: str
    review: str
    voted_up: Optional[bool] = None


class SummarizeSubcategoryRequest(BaseModel):
    app_id: int = Field(..., gt=0)
    subcategory: str = Field(..., min_length=3)
    reviews: List[ReviewItem] = Field(..., min_length=1, max_length=100)
    summary_type: str = Field(default="general", pattern="^(issue|request|general)$")
    output_language: str = Field(
        default="zh",
        pattern="^(zh|en|ja)$",
        description="Language for the generated summary.",
    )
    summary_context: Optional[str] = Field(
        default=None,
        description="Optional scope/filter context shown in the UI (e.g., language, date range, segment).",
        max_length=1200,
    )


class SummarizeSubcategoryResponse(BaseModel):
    summary: str
    pros: List[str]
    cons: List[str]


class SummarizeWidgetRequest(BaseModel):
    app_id: int = Field(..., gt=0)
    widget_kind: str = Field(..., pattern="^(trend_week|segment|top_issues|top_requests)$")
    widget_label: str = Field(..., min_length=1, max_length=160)
    context: Dict[str, Any] = Field(default_factory=dict)
    reviews: List[dict] = Field(..., min_length=1, max_length=100)
    output_language: str = Field("zh", min_length=2, max_length=8)
    run_id: Optional[str] = None


class SummarizeWidgetResponse(BaseModel):
    summary: str
    key_points: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    output_language: str = "zh"
    generated_language: Optional[dict] = None


class SummarizeRecentReviewsRequest(BaseModel):
    app_id: int = Field(..., gt=0)
    count: int = Field(default=500, ge=10, le=1000)
    filter_context: Optional[str] = Field(default=None, description="Description of active filters for context")
    output_language: str = Field("zh", min_length=2, max_length=8, description="Language for generated summaries: zh, en, or ja")


class SummarizeRecentReviewsResponse(BaseModel):
    summary: str
    key_points: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    health_score: Optional[int] = None
    sentiment_trend: Optional[str] = None
    top_strengths: List[str] = Field(default_factory=list)
    review_count: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class SummarizeNewsRequest(BaseModel):
    app_id: int
    news_count: int = Field(default=10, ge=1, le=30)
    include_sentiment: bool = Field(default=True)
    output_language: str = Field(
        default="zh",
        pattern="^(zh|en|ja)$",
        description="Language for the generated summary: zh, en, or ja",
    )


class SummarizeNewsResponse(BaseModel):
    summary: str
    key_updates: List[str] = Field(default_factory=list)
    potential_impacts: List[str] = Field(default_factory=list)
    correlation_insights: Optional[str] = None
    news_count: int


# ---------------------------------------------------------------------------
# Background analysis job
# ---------------------------------------------------------------------------

def _sampling_contract_for_request(request: AnalyzeRequest) -> SamplingContract:
    """Resolve the explicit contract, retaining the legacy request path."""
    if request.sampling is not None:
        if request.sampling.app_id != request.app_id:
            raise HTTPException(status_code=422, detail="sampling.app_id must match app_id")
        return request.sampling

    legacy_filter = (request.filter or "recent").lower()
    collection_order = {
        "recent": "recent",
        "recent_created": "recent",
        "updated": "updated",
        "all": "helpful",
        "best": "helpful",
    }.get(legacy_filter, "recent")
    languages = request.languages or ([request.language] if request.language and request.language != "all" else ["all"])
    return SamplingContract(
        app_id=request.app_id,
        languages=languages,
        collection_order=collection_order,
        max_reviews=request.review_count,
    )

def _build_population_provenance(all_reviews: List[dict], metadata: Optional[AnalyzeMetadata] = None) -> dict:
    """Build the immutable temporal source contract before sampling."""
    rows = []
    for review in all_reviews:
        if not (review.get("recommendationid") or review.get("review_id")):
            continue
        try:
            timestamp_created = int(review.get("timestamp_created"))
        except (TypeError, ValueError):
            continue
        rows.append({
            "review_id": str(review.get("recommendationid") or review.get("review_id") or ""),
            "timestamp_created": timestamp_created,
            "voted_up": review.get("voted_up") is True,
        })
    active_filters = (metadata.active_filters or {}) if metadata is not None else {}
    observed_timestamps = [row["timestamp_created"] for row in rows]
    observed_start = min(observed_timestamps) if observed_timestamps else None
    observed_end = max(observed_timestamps) if observed_timestamps else None
    coverage_start = metadata.coverage_start_time if metadata is not None else None
    coverage_end = metadata.coverage_end_time if metadata is not None else None
    coverage_status = metadata.coverage_status if metadata is not None else None
    coverage_end_inclusive = metadata.coverage_end_inclusive if metadata is not None else None
    return {
        "schema_version": "research-population-v1",
        "sampling_contract": metadata.sampling_contract if metadata is not None else None,
        "available_matching_reviews": metadata.available_matching_reviews if metadata is not None else None,
        "retrieved_reviews": metadata.retrieved_reviews if metadata is not None else None,
        "population_reviews_after_scope": metadata.population_reviews_after_scope if metadata is not None else None,
        "scope_complete": active_filters.get("scope_complete"),
        "collection_complete": active_filters.get("collection_complete"),
        "truncated_by_max_reviews": active_filters.get("truncated_by_max_reviews"),
        "stop_reason": active_filters.get("stop_reason"),
        "language_stats": active_filters.get("language_stats"),
        "lower_boundary_reached": active_filters.get("lower_boundary_reached"),
        "coverage_start_time": coverage_start,
        "coverage_end_time": coverage_end,
        "coverage_status": coverage_status,
        "coverage_end_inclusive": coverage_end_inclusive,
        "acquisition_coverage": {
            "start_time": coverage_start,
            "end_time": coverage_end,
            "status": coverage_status,
            "end_inclusive": coverage_end_inclusive,
        },
        "observed_review_start_time": observed_start,
        "observed_review_end_time": observed_end,
        "observed_review_range": {
            "first_review_timestamp": observed_start,
            "last_review_timestamp": observed_end,
        },
        "deduplication_policy": "transport review-id duplicates only; duplicate text is retained",
        "population_count": len(all_reviews),
        "complete": len(rows) == len(all_reviews),
        "rows": rows,
    }


def _resolve_semantic_runtime() -> dict[str, Any]:
    """Resolve semantic availability without making it an analysis gate.

    Research Core is provider-agnostic and remains the minimum product.  This
    helper only describes whether the optional legacy semantic layer can run;
    it never returns credentials or raw runtime configuration.
    """
    try:
        from ..providers import get_active_provider
        from ..providers.config import SUGGESTED_MODELS, _provider_has_key, validate_live_runtime

        provider_name, active_model = get_active_provider()
    except Exception:
        return {
            "status": "unavailable",
            "reason": "invalid_configuration",
            "provider": None,
            "model_id": None,
        }

    provider_name = str(provider_name or "").strip() or None
    model_id = str(active_model or "").strip() or None
    if provider_name is None:
        return {
            "status": "unavailable",
            "reason": "no_provider",
            "provider": None,
            "model_id": None,
        }
    if provider_name not in SUGGESTED_MODELS:
        return {
            "status": "unavailable",
            "reason": "invalid_configuration",
            "provider": provider_name,
            "model_id": model_id,
        }
    try:
        if not _provider_has_key(provider_name):
            return {
                "status": "unavailable",
                "reason": "no_api_key",
                "provider": provider_name,
                "model_id": model_id,
            }
        config_ok, _config_error = validate_live_runtime(provider_name, model_id or "")
    except Exception:
        config_ok = False
    if not config_ok:
        return {
            "status": "unavailable",
            "reason": "invalid_configuration",
            "provider": provider_name,
            "model_id": model_id,
        }
    return {
        "status": "available",
        "reason": None,
        "provider": provider_name,
        "model_id": model_id,
    }


def _run_analysis_job(
    run_id: str,
    app_id: int,
    all_reviews: List[dict],
    metadata: AnalyzeMetadata,
    game_context: Optional[dict],
    output_language: str = "zh",
    semantic_runtime: Optional[dict] = None,
) -> None:
    total_reviews = len(all_reviews)
    snapshot_hash: Optional[str] = None
    context_hash: Optional[str] = None
    runtime = dict(semantic_runtime or _resolve_semantic_runtime())

    # Keep the exact raw population scope separate from the sampled review
    # payload.  This is deliberately minimal immutable provenance for
    # deterministic temporal projections; it does not alter classification
    # or any analytical denominator.
    population_provenance = _build_population_provenance(all_reviews, metadata)
    metadata_payload = metadata.dict()
    metadata_payload["population_provenance"] = population_provenance

    try:
        snapshot_hash = hashlib.sha256(",".join(sorted(str(r.get("recommendationid", "")) for r in all_reviews)).encode()).hexdigest()[:16]
        context_hash = hashlib.sha256(json.dumps(game_context or {}, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    except Exception as exc:
        logger.warning("Failed to compute analysis hashes: %s", exc)

    try:
        current = storage.get_analysis_run(run_id) or {}
        if current.get("status") == "cancelled":
            return
        if current.get("status") != "running":
            storage.transition_general_analysis_run(run_id, "failed", error="background started before run entered running")
            return
        if storage.is_general_analysis_cancel_requested(run_id):
            storage.transition_general_analysis_run(run_id, "cancelled", phase="research_core", error="Analysis cancelled by user")
            storage.clear_progress(app_id)
            return
    except Exception as exc:
        logger.exception("Failed to start general analysis run %s", run_id)
        try:
            storage.transition_general_analysis_run(run_id, "failed", error=str(exc))
        except Exception:
            logger.exception("Failed to persist start failure for run %s", run_id)
        return

    try:
        storage.reset_progress(app_id, total_reviews, phase="research_core")
    except Exception as exc:
        logger.error("Failed to reset progress to research_core: %s", exc)

    def _progress_callback(processed: int, total: int) -> None:
        if storage.is_cancelled(app_id) or storage.is_general_analysis_cancel_requested(run_id):
            raise InterruptedError("Analysis cancelled by user")
        try:
            storage.update_progress(app_id, processed, total)
        except Exception as exc:
            logger.warning("Progress update failed: %s", exc)

    def _save_starred_snapshot(insights_payload: Optional[dict], sample_payload: List[dict]) -> None:
        """Best-effort server-side persistence of completed analysis for starred games."""
        try:
            # Only update existing starred entries — don't auto-star every analyzed game.
            existing = storage.load_starred_games()
            if not any(g.get("app_id") == app_id for g in existing):
                return
            game_name = (game_context or {}).get("name") or str(app_id)
            genres = (game_context or {}).get("genres") or []
            categories = (game_context or {}).get("categories") or []
            storage.save_starred_game(
                app_id=app_id,
                name=game_name,
                metadata=metadata.dict(),
                insights=insights_payload,
                sample=sample_payload,
                genres=genres if isinstance(genres, list) else [],
                categories=categories if isinstance(categories, list) else [],
            )
        except Exception as exc:
            logger.warning("Failed to persist starred snapshot for app %s: %s", app_id, exc)

    def _research_counts(research_report: dict, *, classified_count: int = 0, valid_review_count: Optional[int] = None) -> dict:
        if valid_review_count is None:
            valid_review_count = int(
                ((research_report.get("recommendation") or {}).get("population") or {}).get("valid_n") or 0
            )
        return {
            "available_matching_reviews": metadata.available_matching_reviews,
            "retrieved_count": metadata.retrieved_count or total_reviews,
            "deduplicated_count": metadata.deduplicated_count,
            "analysis_population_count": total_reviews,
            "valid_review_count": valid_review_count,
            "classified_count": classified_count,
        }

    def _semantic_status(status: str, reason: Optional[str]) -> dict:
        return {
            "status": status,
            "reason": reason,
            "provider": runtime.get("provider"),
            "model_id": runtime.get("model_id"),
        }

    def _finalize_quantitative_only(research_report: dict, status: dict) -> None:
        try:
            storage.update_progress_phase(app_id, "finalizing")
            storage.update_progress(app_id, total_reviews, total_reviews)
        except Exception:
            logger.debug("Failed to mark quantitative-only finalization for %s", run_id, exc_info=True)
        storage.finalize_general_analysis_run(
            run_id,
            app_id,
            metadata_payload,
            None,
            [],
            snapshot_hash=snapshot_hash,
            context_hash=context_hash,
            counts=_research_counts(research_report),
            research_report=research_report,
            semantic_status=status,
        )

    # Research Core is the canonical minimum analytical product.  Any failure
    # here is a run failure and must prevent all semantic/provider work.
    try:
        research_report = build_snapshot_research_report(
            all_reviews,
            metadata=metadata_payload,
        )
    except Exception as exc:
        logger.exception("Research Core failed for analysis %s", run_id)
        try:
            storage.save_analysis_result(
                app_id=app_id,
                metadata=metadata_payload,
                insights=None,
                reviews=[],
                status="failed",
                error=f"Research Core failed: {exc}",
                run_id=run_id,
                snapshot_hash=snapshot_hash,
                context_hash=context_hash,
                research_report=None,
                semantic_status=None,
            )
            storage.transition_general_analysis_run(run_id, "failed", phase="research_core", error=f"Research Core failed: {exc}")
        except Exception:
            logger.exception("Failed to persist Research Core failure for %s", run_id)
        storage.clear_progress(app_id)
        return

    if not all_reviews:
        semantic_state = _semantic_status("unavailable", "no_reviews")
    elif runtime.get("status") != "available":
        semantic_state = _semantic_status("unavailable", runtime.get("reason") or "invalid_configuration")
    else:
        semantic_state = _semantic_status("pending", None)

    # Materialize the deterministic result in its dedicated persistence fields
    # before attempting optional semantic work.  Legacy ``insights`` remains
    # reserved for semantic/presentation compatibility output.
    base_insights = None
    try:
        storage.save_analysis_result(
            app_id=app_id,
            metadata=metadata_payload,
            insights=base_insights,
            reviews=[],
            status="running",
            run_id=run_id,
            snapshot_hash=snapshot_hash,
            context_hash=context_hash,
            research_report=research_report,
            semantic_status=semantic_state,
        )
    except Exception as exc:
        logger.exception("Failed to persist Research Core result for %s", run_id)
        try:
            storage.transition_general_analysis_run(run_id, "failed", phase="research_core", error=str(exc))
        except Exception:
            logger.exception("Failed to persist Research Core persistence failure for %s", run_id)
        storage.clear_progress(app_id)
        return

    if semantic_state["status"] == "unavailable":
        try:
            _finalize_quantitative_only(research_report, semantic_state)
        except Exception as exc:
            logger.exception("Failed to finalize quantitative-only analysis %s", run_id)
            try:
                storage.save_analysis_result(
                    app_id=app_id,
                    metadata=metadata_payload,
                    insights=base_insights,
                    reviews=[],
                    status="failed",
                    error=str(exc),
                    run_id=run_id,
                    snapshot_hash=snapshot_hash,
                    context_hash=context_hash,
                )
                storage.transition_general_analysis_run(run_id, "failed", error=str(exc))
            except Exception:
                logger.exception("Failed to persist quantitative-only finalization failure for %s", run_id)
        finally:
            storage.clear_progress(app_id)
        return

    try:
        storage.update_progress_phase(app_id, "classifying")
        storage.transition_general_analysis_run(run_id, "running", phase="classifying")
        storage.reset_progress(app_id, total_reviews, phase="classifying")
        with llm.llm_usage_context(
            app_id=app_id,
            run_id=run_id,
            phase="classifying",
            operation="classify",
            prompt_version=llm.active_classifier_prompt_version(),
            taxonomy_version=llm.TAXONOMY_VERSION,
            requested_review_count=len(all_reviews),
        ):
            llm.ensure_review_labels(
                app_id,
                all_reviews,
                progress_callback=_progress_callback if total_reviews > 0 else None,
                game_context=game_context,
            )
            # `ensure_review_labels` returns flat prediction payloads for
            # callers, while `apply_review_labels` also needs the canonical
            # storage envelope (label_origin/validated/provider/input hash).
            llm_labels = storage.load_review_labels(app_id)

        if storage.is_general_analysis_cancel_requested(run_id):
            raise InterruptedError("Analysis cancelled by user")

        df = build_reviews_dataframe(all_reviews)
        df = llm.apply_review_labels(df, llm_labels)

        if df is None or df.empty:
            semantic_state = _semantic_status("unavailable", "no_classifiable_reviews")
            _finalize_quantitative_only(research_report, semantic_state)
            return

        storage.update_progress_phase(app_id, "building_insights")
        storage.transition_general_analysis_run(run_id, "running", phase="aggregating")

        insights = prepare_insights(df, run_id=run_id, app_id=app_id)
        design_snapshot = storage.get_analysis_design(run_id)
        if design_snapshot:
            adaptive_payload = dict(insights.get("adaptive_analysis") or {})
            adaptive_payload["design"] = design_snapshot
            adaptive_payload["analysis_type"] = "current_snapshot"
            adaptive_payload["descriptive_only"] = True
            insights["adaptive_analysis"] = adaptive_payload
            # Rebuild after attaching the immutable design so Five Questions
            # carries the exact run's methodology rather than a null shell.
            insights["five_questions"] = build_five_question_contract(
                insights, run_id=run_id, mode="production"
            )
        validated_classified_count = int(
            ((df.get("llm_label_origin") == "llm") & (df.get("llm_validated") == True)).sum()  # noqa: E712
        ) if df is not None and not df.empty else 0

        export_columns = [col for col in REVIEW_EXPORT_COLUMNS if col in df.columns]
        if export_columns:
            sample_limit = min(SAMPLE_LIMIT, df.shape[0])
            reviews_payload = json.loads(
                df[export_columns]
                .head(sample_limit)
                .to_json(orient="records", date_format="iso", date_unit="s")
            )
        else:
            reviews_payload = []

        # Auto-generate health overview.  This remains non-fatal and does not
        # alter the semantic availability status when it fails.
        try:
            baseline = None
            try:
                prev_result = storage.load_analysis_result(app_id)
                if prev_result:
                    prev_insights = prev_result.get("insights") or {}
                    prev_metadata = prev_result.get("metadata") or {}
                    prev_date = prev_metadata.get("fetched_at") or ""
                    if not prev_date and prev_result.get("updated_at"):
                        try:
                            prev_date = datetime.fromtimestamp(prev_result["updated_at"], tz=timezone.utc).strftime("%Y-%m-%d")
                        except Exception:
                            prev_date = ""
                    if prev_insights:
                        baseline = {
                            "date": prev_date,
                            "recommendation_rate": prev_insights.get("recommendation"),
                            "issue_rate": (prev_insights.get("llm") or {}).get("issue_rate"),
                            "request_rate": (prev_insights.get("llm") or {}).get("feature_request_rate"),
                        }
            except Exception:
                pass
            with llm.llm_usage_context(
                app_id=app_id,
                run_id=run_id,
                phase="aggregating",
                operation="health_overview",
                prompt_version=llm.ACTIVE_PROMPT_VERSION,
                taxonomy_version=llm.TAXONOMY_VERSION,
            ):
                health_overview = llm.generate_health_overview(
                    reviews=reviews_payload,
                    game_context=game_context,
                    baseline=baseline,
                    output_language=output_language,
                )
            if insights is not None:
                insights["health_overview"] = health_overview
        except Exception as exc:
            logger.warning("Health overview generation failed (non-fatal): %s", exc)
            if insights is not None:
                insights["health_overview"] = None

        # Store review fingerprint so auto-refresh can detect changes.
        metadata.review_fingerprint = storage.get_reviews_fingerprint(app_id)
        metadata_payload = metadata.dict()
        metadata_payload["population_provenance"] = population_provenance
        semantic_status = _semantic_status("available", None)

        storage.finalize_general_analysis_run(
            run_id=run_id,
            app_id=app_id,
            metadata=metadata_payload,
            insights=insights,
            reviews=reviews_payload,
            snapshot_hash=snapshot_hash,
            context_hash=context_hash,
            counts=_research_counts(
                research_report,
                classified_count=validated_classified_count,
                valid_review_count=int(len(df)) if df is not None else 0,
            ),
            research_report=research_report,
            semantic_status=semantic_status,
        )
        _save_starred_snapshot(insights, reviews_payload)
    except InterruptedError as exc:
        logger.info(f"Analysis cancelled for app {app_id}: {exc}")
        try:
            storage.save_analysis_result(
                app_id=app_id, metadata=metadata.dict(), insights=None, reviews=[],
                status="cancelled", error="Analysis cancelled by user", run_id=run_id,
                snapshot_hash=snapshot_hash, context_hash=context_hash,
            )
        except Exception:
            logger.exception("Failed to persist cancelled analysis result for %s", run_id)
        try:
            storage.transition_general_analysis_run(run_id, "cancelled", phase="classifying", error="Analysis cancelled by user")
        except Exception:
            logger.exception("Failed to persist cancelled run %s", run_id)
    except Exception as exc:
        # Semantic failures cannot erase an already materialized Research Core
        # result.  They produce a completed quantitative run with an explicit
        # semantic failure state rather than a globally failed analysis.
        logger.exception("Semantic analysis failed after Research Core: %s", exc)
        failed_status = _semantic_status("failed", "runtime_error")
        try:
            _finalize_quantitative_only(research_report, failed_status)
        except Exception as finalize_exc:
            logger.exception("Failed to finalize semantic failure for %s", run_id)
            try:
                storage.save_analysis_result(
                    app_id=app_id,
                    metadata=metadata_payload,
                    insights=None,
                    reviews=[],
                    status="failed",
                    error=str(finalize_exc),
                    run_id=run_id,
                    snapshot_hash=snapshot_hash,
                    context_hash=context_hash,
                    research_report=research_report,
                    semantic_status=failed_status,
                )
                storage.transition_general_analysis_run(run_id, "failed", error=str(finalize_exc))
            except Exception:
                logger.exception("Failed to persist semantic finalization failure for %s", run_id)
    finally:
        try:
            storage.update_progress_phase(app_id, "finalizing")
            storage.update_progress(app_id, total_reviews, total_reviews)
        except Exception:
            logger.debug("Failed to finalize progress state for %s", run_id, exc_info=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
def analyze(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> AnalyzeResponse:
    sampling_contract = _sampling_contract_for_request(request)
    filter_type = sampling_contract.collection_order
    # LLM availability is semantic-layer provenance, not an analysis-wide
    # preflight gate.  Steam acquisition and Research Core remain available
    # when this optional runtime cannot execute.
    semantic_runtime = _resolve_semantic_runtime()

    # Clean up any analyses stuck in 'running' state for > 5 minutes
    cleared = storage.clear_stale_running_analyses(max_age_seconds=300)
    if cleared:
        logger.info("Cleared stale running analyses for app_ids: %s", cleared)

    active_same = storage.get_active_general_analysis(request.app_id)
    if active_same is not None:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "An analysis for this app is already in progress.",
                "run_id": active_same.get("run_id"),
            },
        )
    active_other = storage.get_active_general_analysis()
    if active_other is not None and int(active_other.get("target_app_id")) != request.app_id:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "You already have an analysis in progress. Please wait for it to finish or cancel it before starting a new one.",
                "running_app_id": active_other.get("target_app_id"),
            },
        )

    existing_result = storage.load_analysis_result(request.app_id)
    if existing_result and existing_result.get("status") == "running":
        progress = storage.load_progress(request.app_id)
        if progress is not None:
            updated_ts = progress.get("updated_at", 0)
            age_seconds = (datetime.now(timezone.utc) - datetime.fromtimestamp(updated_ts, tz=timezone.utc)).total_seconds() if updated_ts else float("inf")
            if age_seconds < 300:
                processed = progress.get("processed", 0)
                total = progress.get("total", 0)
                logger.info(f"Analysis already running for app {request.app_id} ({processed}/{total}), age {age_seconds:.0f}s")
                return AnalyzeResponse(
                    metadata=AnalyzeMetadata(**existing_result.get("metadata", {})),
                    insights=None,
                    reviews=[],
                    run_id=(storage.get_active_general_analysis(request.app_id) or {}).get("run_id"),
                )
            else:
                logger.warning(f"Clearing stale 'running' analysis for app {request.app_id} (no progress for {age_seconds:.0f}s)")
                storage.save_analysis_result(
                    app_id=request.app_id,
                    metadata=existing_result.get("metadata", {}),
                    insights=None,
                    reviews=[],
                    status="failed",
                    error="Analysis timed out (stale running state)",
                )
                storage.clear_progress(request.app_id)

    run_id = uuid4().hex
    languages_to_fetch = sampling_contract.languages
    runtime_available = semantic_runtime.get("status") == "available"
    storage.create_general_analysis_run(
        run_id,
        request.app_id,
        config={
            "review_count": request.review_count, "language": request.language,
            "languages": languages_to_fetch or [], "filter": filter_type,
            "day_range": request.day_range, "refresh_days": request.refresh_days,
            "persist": request.persist, "output_language": request.output_language,
            "sampling_contract": sampling_contract.to_dict(),
            "semantic_runtime": semantic_runtime,
        },
        requested_languages=sampling_contract.languages,
        requested_review_count=sampling_contract.max_reviews,
        provider=semantic_runtime.get("provider") if runtime_available else None,
        model_id=semantic_runtime.get("model_id") if runtime_available else None,
        prompt_version=llm.active_classifier_prompt_version() if runtime_available else None,
        analysis_version="general-analysis-v1",
    )
    # The request handler performs the existing synchronous ingestion path.
    # Mark the first real work before reading/fetching so queued never covers
    # execution time and started_at includes the full user-visible run.
    storage.transition_general_analysis_run(run_id, "running", phase="ingesting")

    stored_reviews: List[dict] = []
    if request.persist:
        stored_reviews = storage.load_reviews(request.app_id)

    fetched_reviews: List[dict] = []
    fetch_stats: Dict[str, Any] = {
        "available_matching_reviews": None,
        "retrieved_count": 0,
        "retrieved_reviews": 0,
        "population_reviews_after_scope": 0,
        "scope_complete": None,
        "collection_complete": None,
        "truncated_by_max_reviews": False,
        "stop_reason": None,
        "language_stats": None,
        "lower_boundary_reached": None,
        "steam_num_reviews": None,
        "steam_total_reviews": None,
    }
    def _fetch_progress_callback(fetched_count: int) -> None:
        try:
            if storage.is_general_analysis_cancel_requested(run_id) or storage.is_cancelled(request.app_id):
                raise InterruptedError("Analysis cancelled by user")
            storage.update_fetch_progress(request.app_id, fetched_count)
        except InterruptedError:
            raise
        except Exception as exc:
            logger.warning("Fetch progress update failed: %s", exc)

    def _fetch_stats_callback(stats: dict) -> None:
        for key in fetch_stats:
            if key in stats:
                value = stats.get(key)
                if key in {"retrieved_count", "retrieved_reviews", "population_reviews_after_scope", "steam_num_reviews", "steam_total_reviews"}:
                    fetch_stats[key] = None if value is None else int(value)
                elif key in {"truncated_by_max_reviews"}:
                    fetch_stats[key] = bool(value)
                else:
                    fetch_stats[key] = value

    # Always fetch latest Steam reviews for every analysis run.
    storage.reset_progress(request.app_id, total=0, phase="fetching")

    try:
        if len(sampling_contract.languages) > 1:
            fetched_reviews = fetch_reviews_multi_language(
                request.app_id,
                count=sampling_contract.max_reviews,
                languages=sampling_contract.languages,
                filter_type=filter_type,
                day_range=request.refresh_days or request.day_range,
                progress_callback=_fetch_progress_callback,
                stats_callback=_fetch_stats_callback,
                sampling_contract=sampling_contract,
            )
        else:
            fetched_reviews = fetch_reviews(
                request.app_id,
                count=sampling_contract.max_reviews,
                language=sampling_contract.languages[0],
                filter_type=filter_type,
                day_range=request.refresh_days or request.day_range,
                progress_callback=_fetch_progress_callback,
                stats_callback=_fetch_stats_callback,
                sampling_contract=sampling_contract,
            )
    except SteamAPIError as exc:
        storage.transition_general_analysis_run(run_id, "failed", error=str(exc))
        storage.clear_progress(request.app_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except InterruptedError as exc:
        storage.transition_general_analysis_run(run_id, "cancelled", error=str(exc))
        storage.clear_progress(request.app_id)
        raise HTTPException(status_code=409, detail="Analysis cancelled by user") from exc
    except Exception as exc:
        storage.transition_general_analysis_run(run_id, "failed", error=str(exc))
        storage.clear_progress(request.app_id)
        raise HTTPException(status_code=500, detail="Analysis ingestion failed.") from exc

    if request.persist:
        storage.upsert_reviews(request.app_id, fetched_reviews)
        storage.enforce_review_limit(request.app_id)
        # A run's population is the canonical set fetched for this request;
        # do not silently replace it with older rows from the app cache.
        stored_reviews = fetched_reviews
    else:
        stored_reviews = fetched_reviews

    all_reviews = fetched_reviews

    if sampling_contract.max_reviews > 0 and len(all_reviews) > sampling_contract.max_reviews:
        all_reviews = all_reviews[: sampling_contract.max_reviews]

    all_reviews.sort(key=lambda r: (r.get("language", "english"), -(r.get("timestamp_created") or 0)))

    label_estimate = None
    if semantic_runtime.get("status") == "available" and all_reviews:
        try:
            estimate = llm.estimate_review_labeling(request.app_id, all_reviews)
            label_estimate = LabelReuseEstimate(
                total_reviews=int(estimate.get("total_reviews", len(all_reviews)) or 0),
                cached_reviews=int(estimate.get("cached_reviews", 0) or 0),
                llm_reviews=int(estimate.get("llm_reviews", 0) or 0),
                needs_refresh_reviews=int(estimate.get("needs_refresh_reviews", 0) or 0),
                empty_reviews=int(estimate.get("empty_reviews", 0) or 0),
                short_reviews=int(estimate.get("short_reviews", 0) or 0),
                reasons={str(key): int(value) for key, value in (estimate.get("reasons") or {}).items() if key},
            )
        except Exception as exc:
            logger.warning("Failed to estimate cached labels for app %s: %s", request.app_id, exc)

    with db_module.get_connection() as conn:
        lock_acquired = d.try_advisory_lock(conn, request.app_id + 1_000_000_000)
        if lock_acquired:
            d.advisory_unlock(conn, request.app_id + 1_000_000_000)
    if not lock_acquired:
        storage.transition_general_analysis_run(run_id, "failed", error="Analysis lock unavailable")
        return AnalyzeResponse(
            metadata=AnalyzeMetadata(
                app_id=request.app_id,
                requested=sampling_contract.max_reviews,
                retrieved=0,
                requested_limit=sampling_contract.max_reviews,
                retrieved_count=0,
                deduplicated_count=0,
                analysis_population_count=0,
                language=sampling_contract.languages[0],
                languages=sampling_contract.languages,
                collection_complete=False,
                truncated_by_max_reviews=False,
                stop_reason="api_failure",
                sampling_contract=sampling_contract.to_dict(),
                fetched_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            ),
            insights=None,
            reviews=[],
            run_id=run_id,
        )

    game_context = fetch_app_details(request.app_id)
    header_image = None
    if game_context:
        header_image = game_context.get("header_image")

    review_timestamps = [int(review.get("timestamp_created") or 0) for review in all_reviews if review.get("timestamp_created")]
    window_start = datetime.fromtimestamp(min(review_timestamps), tz=timezone.utc).date().isoformat() if review_timestamps else None
    window_end = datetime.fromtimestamp(max(review_timestamps), tz=timezone.utc).date().isoformat() if review_timestamps else None
    acquisition_coverage = _derive_acquisition_coverage(sampling_contract, fetch_stats)
    metadata = AnalyzeMetadata(
        app_id=request.app_id,
        requested=sampling_contract.max_reviews,
        retrieved=len(all_reviews),
        requested_limit=sampling_contract.max_reviews,
        available_matching_reviews=fetch_stats.get("available_matching_reviews"),
        retrieved_reviews=fetch_stats.get("retrieved_reviews") or fetch_stats.get("retrieved_count") or len(fetched_reviews),
        population_reviews_after_scope=len(all_reviews),
        retrieved_count=fetch_stats.get("retrieved_count") or len(fetched_reviews),
        deduplicated_count=len(all_reviews),
        analysis_population_count=len(all_reviews),
        language=sampling_contract.languages[0],
        languages=sampling_contract.languages,
        fetched_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        header_image=header_image,
        mode="live_provider",
        source="steam_reviews",
        run_id=run_id,
        coverage_start_time=acquisition_coverage["coverage_start_time"],
        coverage_end_time=acquisition_coverage["coverage_end_time"],
        coverage_status=acquisition_coverage["coverage_status"],
        coverage_end_inclusive=acquisition_coverage["coverage_end_inclusive"],
        observed_review_start_time=float(min(review_timestamps)) if review_timestamps else None,
        observed_review_end_time=float(max(review_timestamps)) if review_timestamps else None,
        window_start=window_start,
        window_end=window_end,
        classification_population=len(all_reviews),
        evidence_population=0,
        collection_complete=fetch_stats.get("collection_complete"),
        truncated_by_max_reviews=fetch_stats.get("truncated_by_max_reviews"),
        stop_reason=fetch_stats.get("stop_reason"),
        language_stats=fetch_stats.get("language_stats"),
        sampling_contract=sampling_contract.to_dict(),
        active_filters={
            "collection_order": sampling_contract.collection_order,
            "review_type": sampling_contract.review_type,
            "purchase_type": sampling_contract.purchase_type,
            "include_offtopic_activity": sampling_contract.include_offtopic_activity,
            "scope_complete": fetch_stats.get("scope_complete"),
            "collection_complete": fetch_stats.get("collection_complete"),
            "truncated_by_max_reviews": fetch_stats.get("truncated_by_max_reviews"),
            "stop_reason": fetch_stats.get("stop_reason"),
            "language_stats": fetch_stats.get("language_stats"),
            "lower_boundary_reached": fetch_stats.get("lower_boundary_reached"),
            "coverage_start_time": acquisition_coverage["coverage_start_time"],
            "coverage_end_time": acquisition_coverage["coverage_end_time"],
            "coverage_status": acquisition_coverage["coverage_status"],
            "coverage_end_inclusive": acquisition_coverage["coverage_end_inclusive"],
            "coverage_reason": acquisition_coverage["coverage_reason"],
            "observed_review_start_time": float(min(review_timestamps)) if review_timestamps else None,
            "observed_review_end_time": float(max(review_timestamps)) if review_timestamps else None,
            "steam_num_reviews": fetch_stats.get("steam_num_reviews"),
            "steam_total_reviews": fetch_stats.get("steam_total_reviews"),
            "deduplication_policy": "transport review-id duplicates only; duplicate text retained",
        },
    )

    # Persist the intended methodology before the provider is invoked.  A
    # current-snapshot run has no defensible before/after claim, but its
    # descriptive design remains auditable even when classification fails.
    try:
        profile = infer_game_profile(game_context or {}, all_reviews)
        design = build_analysis_design(
            app_id=request.app_id,
            analysis_type="current_snapshot",
            profile=profile,
            event={"event_status": "unresolved", "effective_at": None, "event_name": None},
            window={"pre_days": 0, "post_days": 0, "sensitivity_days": [], "reason_codes": ["current_snapshot_no_baseline"]},
            sensitivity_windows=[],
            comparison_basis="descriptive_snapshot",
            population_rules={"minimum_support": 1, "no_silent_reweight": True},
            metrics=["recommendation_rate", "review_volume", "issue_rate", "request_rate"],
        )
        design["descriptive_only"] = True
        design["what_changed"] = "unavailable"
        storage.save_analysis_design(design, run_id)
    except Exception as exc:
        logger.exception("Failed to persist current-snapshot analysis design for %s", run_id)
        storage.transition_general_analysis_run(run_id, "failed", error=f"Analysis design unavailable: {exc}")
        raise HTTPException(status_code=500, detail="Analysis design could not be persisted.") from exc

    storage.save_analysis_result(
        app_id=request.app_id,
        metadata=metadata.dict(),
        insights=None,
        reviews=[],
        status="running",
        run_id=run_id,
        snapshot_hash=None,
        stale=False,
        research_report=None,
        semantic_status={
            "status": "pending" if runtime_available else "unavailable",
            "reason": None if runtime_available else (semantic_runtime.get("reason") or "invalid_configuration"),
            "provider": semantic_runtime.get("provider") if runtime_available else None,
            "model_id": semantic_runtime.get("model_id") if runtime_available else None,
        },
    )
    storage.transition_general_analysis_run(run_id, "running", phase="research_core")
    storage.reset_progress(request.app_id, total=len(all_reviews), phase="research_core")

    if game_context:
        logger.info(f"Fetched game context for {game_context.get('name', request.app_id)}")

    try:
        background_tasks.add_task(
            _run_analysis_job,
            run_id,
            request.app_id,
            all_reviews,
            metadata,
            game_context,
            request.output_language,
            semantic_runtime,
        )
    except Exception as exc:
        logger.exception("Failed to schedule general analysis run %s", run_id)
        storage.transition_general_analysis_run(run_id, "failed", error=f"schedule failed: {exc}")
        storage.save_analysis_result(
            app_id=request.app_id,
            metadata=metadata.dict(),
            insights=None,
            reviews=[],
            status="failed",
            error=f"schedule failed: {exc}",
            run_id=run_id,
        )
        raise HTTPException(status_code=500, detail="Failed to schedule analysis.") from exc

    return AnalyzeResponse(metadata=metadata, insights=None, reviews=[], label_estimate=label_estimate, run_id=run_id)


@router.post("/analyze/estimate", response_model=AnalyzeEstimateResponse)
def analyze_estimate(request: AnalyzeRequest) -> AnalyzeEstimateResponse:
    sampling_contract = _sampling_contract_for_request(request)
    filter_type = sampling_contract.collection_order

    stored_reviews: List[dict] = []
    if request.persist:
        stored_reviews = storage.load_reviews(request.app_id)

    fetched_reviews: List[dict] = []
    try:
        if len(sampling_contract.languages) > 1:
            fetched_reviews = fetch_reviews_multi_language(
                request.app_id,
                count=sampling_contract.max_reviews,
                languages=sampling_contract.languages,
                filter_type=filter_type,
                day_range=request.refresh_days or request.day_range,
                sampling_contract=sampling_contract,
            )
        else:
            fetched_reviews = fetch_reviews(
                request.app_id,
                count=sampling_contract.max_reviews,
                language=sampling_contract.languages[0],
                filter_type=filter_type,
                day_range=request.refresh_days or request.day_range,
                sampling_contract=sampling_contract,
            )
    except SteamAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    all_reviews = fetched_reviews if fetched_reviews else stored_reviews
    if sampling_contract.max_reviews > 0 and len(all_reviews) > sampling_contract.max_reviews:
        all_reviews = all_reviews[: sampling_contract.max_reviews]

    cached_labels = storage.load_review_labels(request.app_id)
    estimate = llm.estimate_review_labeling(
        request.app_id,
        all_reviews,
    )

    return AnalyzeEstimateResponse(
        app_id=request.app_id,
        will_fetch=True,
        will_persist=bool(request.persist),
        review_count_requested=int(sampling_contract.max_reviews or 0),
        reviews_considered=len(all_reviews),
        cached_labels_total=len(cached_labels),
        cached_reviews=int(estimate.get("cached_reviews", 0) or 0),
        needs_refresh_reviews=int(estimate.get("needs_refresh_reviews", 0) or 0),
        empty_reviews=int(estimate.get("empty_reviews", 0) or 0),
        short_reviews=int(estimate.get("short_reviews", 0) or 0),
        llm_reviews=int(estimate.get("llm_reviews", 0) or 0),
        prompt_version=str(estimate.get("prompt_version") or ""),
        model_id=str(estimate.get("model_id") or ""),
        labeling_strategy=str(estimate.get("labeling_strategy") or ""),
        reasons={str(key): int(value) for key, value in (estimate.get("reasons") or {}).items() if key},
    )


@router.get("/analysis/{app_id}/evidence", response_model=EvidenceResponse)
def get_analysis_evidence(
    app_id: int,
    taxonomy_key: str,
    date_filter: str = "all",
    sentiment: str = "all",
    language: str = "all",
    limit: int = 20,
    offset: int = 0,
) -> EvidenceResponse:
    """Return reconciled matched population plus quote-gated evidence.

    The matched population is deliberately separate from the number of
    verified quotes shown on the page.  Both are evaluated under the same
    taxonomy/filter scope.
    """
    result = storage.load_analysis_result(app_id)
    if not result:
        raise HTTPException(status_code=404, detail="No analysis result available for this app.")
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    all_matches = storage.get_reviews_by_subcategory(
        app_id, taxonomy_key, date_filter=date_filter, limit=100000, offset=0,
        sentiment=sentiment, language=language,
    )
    page = all_matches[offset:offset + limit]
    items: list[dict[str, Any]] = []
    label_rows = storage.load_review_labels(app_id)
    for review in page:
        text_value = str(review.get("review") or "")
        review_id = str(review.get("review_id") or review.get("recommendationid") or "")
        label_payload = (label_rows.get(review_id) or {}).get("payload") or {}
        quotes = (
            (review.get("llm_subcategory_evidence") or {}).get(taxonomy_key)
            or (label_payload.get("evidence") or {}).get(taxonomy_key)
            or []
        )
        verified_quotes = []
        from ..evidence import verify_evidence
        for quote in quotes:
            verified = verify_evidence(text_value, str(quote), review_id=str(review.get("review_id") or review.get("recommendationid") or ""))
            if verified.get("verification_status") == "verified":
                verified_quotes.append(verified)
        items.append({
            "review_id": review_id,
            "review": text_value,
            "voted_up": review.get("voted_up"),
            "evidence": verified_quotes,
        })
    verified_count = sum(len(item["evidence"]) for item in items)
    return EvidenceResponse(
        run_id=result.get("run_id"), app_id=app_id, taxonomy_key=taxonomy_key,
        matched_review_count=len(all_matches), verified_evidence_count=verified_count,
        page_count=(len(all_matches) + limit - 1) // limit if all_matches else 0,
        page_size=limit, offset=offset, items=items,
    )


@router.get("/analysis/{app_id}", response_model=AnalysisStatusResponse)
def get_analysis_result(app_id: int) -> AnalysisStatusResponse:

    result = storage.load_analysis_result(app_id)
    if not result:
        raise HTTPException(status_code=404, detail="No analysis result available for this app.")

    # If the previous run failed due to a config issue (no LLM provider),
    # clear the failed status so the user isn't stuck seeing a stale error.
    # They can simply re-analyze after fixing their settings.
    if result.get("status") == "failed":
        error_msg = (result.get("error") or "").lower()
        if "no llm provider" in error_msg or "not configured" in error_msg or "no api key" in error_msg:
            raise HTTPException(status_code=404, detail="Previous analysis failed due to missing LLM configuration. Please configure a provider in Settings and re-analyze.")

    metadata_payload = result.get("metadata")
    if metadata_payload and not metadata_payload.get("header_image"):
        details = fetch_app_details(app_id)
        if details and details.get("header_image"):
            metadata_payload["header_image"] = details["header_image"]
    if metadata_payload:
        # Historical rows predate the current metadata contract.  Preserve
        # unknown provenance as null; never replace it with now().
        metadata_payload = dict(metadata_payload)
        metadata_payload.setdefault("run_id", result.get("run_id"))
        metadata_payload.setdefault("mode", metadata_payload.get("mode") or "legacy_result")
        metadata_payload.setdefault("source", "immutable_run" if result.get("run_id") else "legacy_cache")
    metadata = AnalyzeMetadata(**metadata_payload) if metadata_payload else None
    stale_reason = result.get("stale_reason")
    if metadata and metadata.fetched_at:
        try:
            fetched_dt = datetime.fromisoformat(metadata.fetched_at.replace("Z", "+00:00"))
            max_age_days = int(os.getenv("SENTINEXT_STALE_DAYS", "30"))
            age_days = (datetime.now(timezone.utc) - fetched_dt).days
            if age_days > max_age_days:
                result["stale"] = True
                stale_reason = f"Analysis older than {max_age_days} days"
        except Exception:
            pass
    try:
        app_details = fetch_app_details(app_id) or {}
        current_ctx_hash = hashlib.sha256(json.dumps(app_details, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        stored_hash = result.get("context_hash")
        if stored_hash and current_ctx_hash != stored_hash:
            result["stale"] = True
            stale_reason = stale_reason or "App details changed since last run"
    except Exception:
        logger.warning("Failed to compare app context hash for %s", app_id)

    # Read endpoints are analytically side-effect free.  A changed review pool
    # invalidates the stored run for freshness purposes, but never triggers a
    # silent semantic or Research Core recomputation.
    data_refreshed = False
    stored_fingerprint = (metadata_payload or {}).get("review_fingerprint")
    if stored_fingerprint and result.get("status") == "completed":
        try:
            current_fingerprint = storage.get_reviews_fingerprint(app_id)
            if current_fingerprint and current_fingerprint != stored_fingerprint:
                result["stale"] = True
                stale_reason = stale_reason or "Review pool changed since analysis run"
        except Exception:
            logger.warning("Failed to compare review fingerprint for app %s", app_id)

    return AnalysisStatusResponse(
        status=result.get("status", "unknown"),
        metadata=metadata,
        insights=result.get("insights"),
        research_report=result.get("research_report"),
        semantic_status=result.get("semantic_status"),
        reviews=result.get("reviews") or [],
        error=result.get("error"),
        run_id=result.get("run_id"),
        snapshot_hash=result.get("snapshot_hash"),
        stale=bool(result.get("stale")),
        stale_reason=stale_reason,
        data_refreshed=data_refreshed,
    )


@router.get("/analysis/{app_id}/dashboard", response_model=DashboardPayloadResponse)
def get_dashboard_payload(app_id: int, run: Optional[str] = None) -> DashboardPayloadResponse:
    """Return the one Web payload used to decide whether analysis is renderable."""
    try:
        return DashboardPayloadResponse(**build_dashboard_payload(app_id, requested_run_id=run))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/analysis-runs/recent")
def recent_analysis_runs(limit: int = 30) -> list[dict]:
    return storage.list_analysis_history(limit=max(1, min(limit, 100)))


@router.get("/analysis-runs/active")
def active_analysis_runs() -> list[dict]:
    return storage.list_analysis_history(limit=100, active_only=True)


@router.post("/analysis/{app_id}/rebuild-insights")
def rebuild_insights(app_id: int) -> dict:

    result = storage.load_analysis_result(app_id)
    if not result:
        raise HTTPException(status_code=404, detail="No analysis result found for this app.")

    stored_reviews = storage.load_reviews(app_id)
    if not stored_reviews:
        raise HTTPException(status_code=404, detail="No stored reviews found for this app.")

    df = build_reviews_dataframe(stored_reviews)
    if df is None or df.empty:
        raise HTTPException(status_code=400, detail="Could not build DataFrame from stored reviews.")

    llm_labels = storage.load_review_labels(app_id)
    df = llm.apply_review_labels(df, llm_labels)

    insights = prepare_insights(df)

    metadata = result.get("metadata", {})

    export_columns = [col for col in REVIEW_EXPORT_COLUMNS if col in df.columns]
    if export_columns:
        sample_limit = min(SAMPLE_LIMIT, df.shape[0])
        reviews_payload = json.loads(
            df[export_columns]
            .head(sample_limit)
            .to_json(orient="records", date_format="iso", date_unit="s")
        )
    else:
        reviews_payload = []

    storage.save_analysis_result(
        app_id=app_id,
        metadata=metadata,
        insights=insights,
        reviews=reviews_payload,
        status="completed",
        run_id=result.get("run_id"),
        snapshot_hash=result.get("snapshot_hash"),
        context_hash=result.get("context_hash"),
    )

    starred_games = storage.load_starred_games()
    starred = next((entry for entry in starred_games if entry.get("app_id") == app_id), None)
    if starred:
        storage.save_starred_game(
            app_id=app_id,
            name=starred.get("name") or str(app_id),
            metadata=starred.get("metadata") or {},
            insights=insights,
            sample=starred.get("sample") or [],
            genres=starred.get("genres") or [],
            categories=starred.get("categories") or [],
        )

    return {"status": "ok", "message": "Insights rebuilt successfully", "app_id": app_id}


@router.post("/analysis/{app_id}/rebuild-trends")
def rebuild_trends(app_id: int) -> dict:

    result = storage.load_analysis_result(app_id)
    if not result:
        raise HTTPException(status_code=404, detail="No analysis result found for this app.")

    stored_reviews = storage.load_reviews(app_id)
    if not stored_reviews:
        raise HTTPException(status_code=404, detail="No stored reviews found for this app.")

    df = build_reviews_dataframe(stored_reviews)
    if df is None or df.empty:
        raise HTTPException(status_code=400, detail="Could not build DataFrame from stored reviews.")

    trend_df = recommended_share_over_time(df, freq="W-SUN", fill_missing=True)
    trend_payload = (
        json.loads(trend_df.to_json(orient="records", date_format="iso", date_unit="s"))
        if trend_df is not None and not trend_df.empty
        else []
    )

    insights = result.get("insights") or {}
    insights["trend"] = trend_payload

    storage.save_analysis_result(
        app_id=app_id,
        metadata=result.get("metadata", {}),
        insights=insights,
        reviews=result.get("reviews") or [],
        status="completed",
        run_id=result.get("run_id"),
        snapshot_hash=result.get("snapshot_hash"),
        context_hash=result.get("context_hash"),
        stale=result.get("stale", False),
        stale_reason=result.get("stale_reason"),
    )

    starred_games = storage.load_starred_games()
    starred = next((entry for entry in starred_games if entry.get("app_id") == app_id), None)
    if starred:
        storage.save_starred_game(
            app_id=app_id,
            name=starred.get("name") or str(app_id),
            metadata=starred.get("metadata") or {},
            insights=insights,
            sample=starred.get("sample") or [],
            genres=starred.get("genres") or [],
            categories=starred.get("categories") or [],
        )

    return {"status": "ok", "message": "Trends rebuilt successfully", "app_id": app_id}


@router.post("/summarize/subcategory", response_model=SummarizeSubcategoryResponse)
def summarize_subcategory(request: SummarizeSubcategoryRequest) -> SummarizeSubcategoryResponse:

    game_context = fetch_app_details(request.app_id)
    try:
        with llm.llm_usage_context(app_id=request.app_id, operation="summarize"):
            result = llm.summarize_subcategory_reviews(
                reviews=[r.dict() for r in request.reviews],
                subcategory=request.subcategory,
                game_context=game_context,
                summary_type=request.summary_type,
                summary_context=request.summary_context,
                output_language=request.output_language,
            )
        return SummarizeSubcategoryResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Summarize failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate summary.") from exc


@router.post("/summarize/widget", response_model=SummarizeWidgetResponse)
def summarize_widget(request: SummarizeWidgetRequest) -> SummarizeWidgetResponse:

    game_context = fetch_app_details(request.app_id)
    try:
        with llm.llm_usage_context(app_id=request.app_id, operation="summarize"):
            result = llm.summarize_widget_reviews(
                reviews=request.reviews,
                widget_kind=request.widget_kind,
                widget_label=request.widget_label,
                widget_context=request.context,
                game_context=game_context,
                output_language=request.output_language,
            )
        provider_name, active_model = get_active_provider()
        result["generated_language"] = {
            "requested_output_language": request.output_language,
            "actual_output_language": result.get("output_language", request.output_language),
            "provider": provider_name,
            "model": active_model,
            "run_id": request.run_id,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        return SummarizeWidgetResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Widget summarize failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate widget summary.") from exc


@router.post("/summarize/recent-reviews", response_model=SummarizeRecentReviewsResponse)
def summarize_recent_reviews(request: SummarizeRecentReviewsRequest) -> SummarizeRecentReviewsResponse:

    stored_reviews = storage.load_reviews(request.app_id, limit=int(request.count or 100))
    if not stored_reviews:
        raise HTTPException(status_code=404, detail="No stored reviews found for this app.")

    game_context = fetch_app_details(request.app_id)

    df = build_reviews_dataframe(stored_reviews)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No review data available for this app.")

    try:
        llm_labels = storage.load_review_labels(request.app_id)
        df = llm.apply_review_labels(df, llm_labels)
    except Exception as exc:
        logger.warning("Failed to apply cached labels for app %s: %s", request.app_id, exc)

    if "created_at" in df.columns:
        try:
            df = df.sort_values(by="created_at", ascending=False)
        except Exception:
            pass
    df = df.head(int(request.count or 100))

    start_date = None
    end_date = None
    try:
        if "created_at" in df.columns and not df["created_at"].dropna().empty:
            start_dt = df["created_at"].min()
            end_dt = df["created_at"].max()
            if start_dt is not None and hasattr(start_dt, "date"):
                start_date = start_dt.date().isoformat()
            if end_dt is not None and hasattr(end_dt, "date"):
                end_date = end_dt.date().isoformat()
    except Exception:
        pass

    baseline = None
    try:
        result = storage.load_analysis_result(request.app_id) or {}
        prev_insights = result.get("insights") or {}
        prev_metadata = result.get("metadata") or {}
        prev_date = prev_metadata.get("fetched_at") or ""
        if not prev_date and result.get("updated_at"):
            try:
                prev_date = datetime.fromtimestamp(result["updated_at"], tz=timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                prev_date = ""
        if prev_insights:
            baseline = {
                "date": prev_date,
                "recommendation_rate": prev_insights.get("recommendation"),
                "issue_rate": (prev_insights.get("llm") or {}).get("issue_rate"),
                "request_rate": (prev_insights.get("llm") or {}).get("feature_request_rate"),
            }
    except Exception:
        baseline = None

    export_columns = [
        "review_id", "review", "language", "created_at", "voted_up",
        "votes_up", "votes_funny", "comment_count",
        "llm_subcategories", "llm_issue_subcategories",
        "llm_request_subcategories", "llm_subcategory_evidence",
    ]
    export_columns = [col for col in export_columns if col in df.columns]
    reviews_payload = (
        json.loads(
            df[export_columns].to_json(orient="records", date_format="iso", date_unit="s")
        )
        if export_columns
        else []
    )

    widget_context: Dict[str, Any] = {
        "date_range": f"{start_date} -> {end_date}" if start_date and end_date else None,
        "baseline": baseline,
        "filters": request.filter_context if request.filter_context else None,
    }

    try:
        with llm.llm_usage_context(app_id=request.app_id, operation="health_overview"):
            result = llm.generate_health_overview(
                reviews=reviews_payload,
                game_context=game_context,
                baseline=baseline,
                widget_context=widget_context,
                output_language=request.output_language,
            )
        return SummarizeRecentReviewsResponse(
            **result,
            review_count=len(reviews_payload),
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Recent reviews summarize failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate recent reviews summary.") from exc


@router.post("/summarize/news", response_model=SummarizeNewsResponse)
def summarize_news(request: SummarizeNewsRequest) -> SummarizeNewsResponse:

    try:
        news_items = fetch_news_for_app(request.app_id, count=request.news_count, max_length=500)
    except SteamAPIError as exc:
        logger.error("Failed to fetch news for app %s: %s", request.app_id, exc)
        raise HTTPException(status_code=502, detail=f"Failed to fetch news: {str(exc)}") from exc

    if not news_items:
        return SummarizeNewsResponse(
            summary=(
                "该游戏近期没有新闻或更新。"
                if request.output_language == "zh"
                else "No recent news or updates available for this game."
            ),
            key_updates=[],
            potential_impacts=[],
            correlation_insights=None,
            news_count=0,
        )

    game_context = fetch_app_details(request.app_id)

    recent_sentiment = None
    if request.include_sentiment:
        try:
            result = storage.load_analysis_result(request.app_id)
            if result:
                insights = result.get("insights") or {}
                llm_insights = insights.get("llm") or {}
                recent_sentiment = {
                    "recommendation_rate": insights.get("recommendation"),
                    "trend": insights.get("trend_direction"),
                    "top_issues": [
                        item.get("subcategory")
                        for item in (llm_insights.get("top_issue_subcategories") or [])[:3]
                    ],
                    "top_requests": [
                        item.get("subcategory")
                        for item in (llm_insights.get("top_request_subcategories") or [])[:3]
                    ],
                }
        except Exception as exc:
            logger.warning("Failed to load sentiment data for news summary: %s", exc)

    news_dicts = [
        {
            "title": item.title,
            "contents": item.contents,
            "date": item.date,
            "feed_label": item.feed_label,
        }
        for item in news_items
    ]

    try:
        with llm.llm_usage_context(app_id=request.app_id, operation="summarize_news"):
            result = llm.summarize_news_updates(
                news_items=news_dicts,
                game_name=game_context.get("name") if game_context else None,
                game_context=game_context,
                recent_sentiment=recent_sentiment,
                output_language=request.output_language,
            )
        return SummarizeNewsResponse(
            **result,
            news_count=len(news_items),
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("News summarize failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate news summary.") from exc


# ---------------------------------------------------------------------------
# Progress endpoints
# ---------------------------------------------------------------------------

@router.get("/progress/{app_id}")
def classification_progress(app_id: int) -> dict:
    active_run = storage.get_active_general_analysis(app_id)
    result = storage.load_analysis_result(app_id)
    run_id = (active_run or {}).get("run_id") or (result or {}).get("run_id")
    run = active_run or (storage.get_analysis_run(run_id) if run_id else None)
    immutable_result_available = bool(run_id and storage.get_analysis_run_result(run_id))
    progress = storage.load_progress(app_id)
    if not progress:
        result = storage.load_analysis_result(app_id)
        if result and result.get("status") == "running":
            return {
                "app_id": app_id,
                "total": 0,
                "processed": 0,
                "active": True,
                "updated_at": None,
                "phase": "fetching",
                "fetched_count": 0,
                "run_id": run_id,
                "run_status": (run or {}).get("status", "running"),
                "run_phase": (run or {}).get("phase", "ingesting"),
                "immutable_result_available": immutable_result_available,
                "analysis_population_count": (run or {}).get("analysis_population_count"),
            }
        return {
            "app_id": app_id,
            "total": 0,
            "processed": 0,
            "active": False,
            "updated_at": None,
            "phase": "idle",
            "fetched_count": 0,
            "run_id": run_id,
            "run_status": (run or {}).get("status", "idle"),
            "run_phase": (run or {}).get("phase"),
            "immutable_result_available": immutable_result_available,
            "analysis_population_count": (run or {}).get("analysis_population_count"),
        }

    total = int(progress.get("total", 0))
    processed = int(progress.get("processed", 0))
    phase = progress.get("phase", "classifying")
    fetched_count = int(progress.get("fetched_count", 0))
    timestamp = progress.get("updated_at")
    updated_at = (
        datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        if timestamp
        else None
    )

    if phase == "fetching":
        active = True
    elif phase == "building_insights":
        result = storage.load_analysis_result(app_id)
        if result and result.get("status") in ("completed", "failed"):
            active = False
        else:
            active = True
    else:
        active = processed < total

    return {
        "app_id": app_id,
        "total": total,
        "processed": processed,
        "active": active,
        "updated_at": updated_at,
        "phase": phase,
        "fetched_count": fetched_count,
        "eta_seconds": progress.get("eta_seconds"),
        "run_id": run_id,
        "run_status": (run or {}).get("status"),
        "run_phase": (run or {}).get("phase"),
        "immutable_result_available": immutable_result_available,
        "analysis_population_count": (run or {}).get("analysis_population_count"),
    }


@router.get("/progress/{app_id}/stream")
async def progress_stream(app_id: int):


    async def event_generator():
        last_processed = -1
        last_fetched = -1
        idle_count = 0
        max_idle = 200

        while True:
            try:
                progress = storage.load_progress(app_id)

                if not progress:
                    result = storage.load_analysis_result(app_id)
                    if result:
                        status = result.get("status", "unknown")
                        if status == "completed":
                            yield f"event: completed\ndata: {json.dumps({'status': 'completed'})}\n\n"
                            return
                        elif status == "failed":
                            error = result.get("error", "Analysis failed")
                            yield f"event: error\ndata: {json.dumps({'status': 'failed', 'error': error})}\n\n"
                            return
                        elif status == "running":
                            yield f"event: progress\ndata: {json.dumps({'processed': 0, 'total': 0, 'active': True, 'phase': 'fetching', 'fetched_count': 0, 'run_status': 'running', 'run_phase': 'ingesting', 'immutable_result_available': False})}\n\n"
                            idle_count += 1
                            await asyncio.sleep(1.5)
                            continue

                    yield f"event: progress\ndata: {json.dumps({'processed': 0, 'total': 0, 'active': False, 'phase': 'idle', 'fetched_count': 0, 'run_status': 'idle', 'immutable_result_available': False})}\n\n"
                    idle_count += 1
                else:
                    total = int(progress.get("total", 0))
                    processed = int(progress.get("processed", 0))
                    phase = progress.get("phase", "classifying")
                    fetched_count = int(progress.get("fetched_count", 0))

                    if phase in ("fetching", "building_insights"):
                        active = True
                    else:
                        active = processed < total

                    active_run = storage.get_active_general_analysis(app_id)
                    run_id = (active_run or {}).get('run_id')
                    run = active_run or (storage.get_analysis_run(run_id) if run_id else None)
                    yield f"event: progress\ndata: {json.dumps({'processed': processed, 'total': total, 'active': active, 'phase': phase, 'fetched_count': fetched_count, 'eta_seconds': progress.get('eta_seconds'), 'run_id': run_id, 'run_status': (run or {}).get('status'), 'run_phase': (run or {}).get('phase'), 'immutable_result_available': bool(run_id and storage.get_analysis_run_result(run_id))})}\n\n"

                    if phase == "fetching":
                        if fetched_count == last_fetched:
                            idle_count += 1
                        else:
                            idle_count = 0
                            last_fetched = fetched_count
                    elif phase == "building_insights":
                        idle_count += 1
                    else:
                        if processed == last_processed:
                            idle_count += 1
                        else:
                            idle_count = 0
                            last_processed = processed

                    if total > 0 and (not active or processed >= total):
                        result = storage.load_analysis_result(app_id)
                        if result:
                            status = result.get("status", "unknown")
                            if status == "completed":
                                yield f"event: completed\ndata: {json.dumps({'status': 'completed'})}\n\n"
                                return
                            elif status == "failed":
                                error = result.get("error", "Analysis failed")
                                yield f"event: error\ndata: {json.dumps({'status': 'failed', 'error': error})}\n\n"
                                return

                if idle_count >= max_idle:
                    yield f"event: timeout\ndata: {json.dumps({'status': 'timeout'})}\n\n"
                    return

                await asyncio.sleep(1.5)

            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("SSE progress stream error: %s", exc)
                yield f"event: error\ndata: {json.dumps({'status': 'error', 'error': str(exc)})}\n\n"
                return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/progress/{app_id}/cancel")
def cancel_analysis(app_id: int) -> dict:
    run = storage.request_general_analysis_cancel(app_id)
    cancelled = storage.cancel_progress(app_id)
    if run is not None:
        logger.info(f"Analysis cancelled for app {app_id}")
    return {"cancelled": bool(cancelled or run), "app_id": app_id, "run_status": (run or {}).get("status")}
