"""Version-event analysis runs for Player Voice Review."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from typing import List, Optional, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..steam_api import SteamAPIError, fetch_app_details, fetch_news_for_app, fetch_reviews
from .. import llm
from ..version_analysis import calculate_version_metrics
from ..adaptive_analysis import (
    build_analysis_design,
    evidence_grade,
    infer_game_profile,
    resolve_event_anchor,
    population_comparability,
    robustness_matrix,
    select_adaptive_window,
)
from ..version_review_autopilot import build_review_acquisition_plan, choose_previous_comparable, deterministic_stratified_sample, lifecycle_interval, resolve_event
from ..comparative_intelligence import evaluate_window_coverage, lifecycle_window, reviews_in_window, build_comparative_result, window_sensitivity, MIN_SEMANTIC_REVIEWS


router = APIRouter(tags=["version-runs"])

_STEAM_LANGUAGE_CODES = {
    "arabic", "bulgarian", "schinese", "tchinese", "czech", "danish", "dutch",
    "english", "finnish", "french", "german", "greek", "hungarian", "italian",
    "japanese", "koreana", "norwegian", "polish", "portuguese", "brazilian",
    "romanian", "russian", "spanish", "swedish", "thai", "turkish", "ukrainian",
    "vietnamese",
}


class VersionEventCreate(BaseModel):
    app_id: int = Field(..., gt=0)
    event_name: str = Field(..., min_length=2, max_length=160)
    event_date: date
    event_type: str = Field(..., min_length=2, max_length=40)
    event_description: Optional[str] = Field(default=None, max_length=2000)
    source: Optional[str] = Field(default="manual", max_length=80)
    source_url: Optional[str] = Field(default=None, max_length=1000)
    manual_verified: bool = True
    published_at: Optional[datetime] = None
    effective_at: Optional[datetime] = None
    effective_at_start: Optional[datetime] = None
    effective_at_end: Optional[datetime] = None
    anchor_precision: str = Field(default="day", max_length=20)
    source_quality: str = Field(default="unknown", max_length=40)
    event_status: str = Field(default="resolved", max_length=30)
    concurrent_event_group: Optional[str] = Field(default=None, max_length=100)


class AnalysisRunCreate(BaseModel):
    target_app_id: int = Field(..., gt=0)
    event_id: str = Field(..., min_length=8, max_length=64)
    pre_window_days: int = Field(default=28, ge=1, le=365)
    post_window_days: int = Field(default=28, ge=1, le=365)
    languages: List[str] = Field(default_factory=list, max_length=20)
    competitor_app_ids: List[int] = Field(default_factory=list, max_length=3)
    # 0 means unlimited: fetch all Steam pages, then filter locally by the
    # event window. A positive value remains available as an emergency cap.
    max_reviews_per_game: int = Field(default=0, ge=0, le=100000)
    analysis_goal: str = Field(default="version_review", min_length=2, max_length=80)
    taxonomy_version: str = Field(default="sentinext-taxonomy-v1", min_length=1, max_length=80)
    semantic_limit: int = Field(default=1000, ge=50, le=5000)
    comparison_event_id: Optional[str] = None


class NewsEventSyncRequest(BaseModel):
    news_count: int = Field(default=30, ge=1, le=100)
    pre_window_days: int = Field(default=28, ge=1, le=365)
    post_window_days: int = Field(default=28, ge=1, le=365)
    max_reviews_per_game: int = Field(default=0, ge=0, le=100000)
    auto_build_metrics: bool = False


class VersionRunExecuteRequest(BaseModel):
    refresh_reviews: bool = True


class VersionReviewPlanRequest(BaseModel):
    app_id: int = Field(..., gt=0)
    event_id: Optional[str] = None
    semantic_limit: int = Field(default=1000, ge=50, le=5000)
    mode: str = Field(default="version_comparison", pattern="^(recent_impact|version_comparison|version_longitudinal|public_opinion)$")
    comparison_event_id: Optional[str] = None
    window_days: Literal[3, 7, 14] = 7


class VersionReviewStartRequest(VersionReviewPlanRequest):
    refresh_reviews: bool = True


def _event_response(event: dict) -> dict:
    return {**resolve_event(event), "manual_verified": bool(event.get("manual_verified"))}


_VERSION_NEWS_RE = re.compile(
    r"\b(patch|hotfix|update|season|operation|expedition|dlc|expansion|content update|major update|version|launch)\b",
    re.IGNORECASE,
)
_VERSION_NEWS_ZH_RE = re.compile(r"补丁|更新|赛季|行动|资料片|扩展包|版本|上线|新内容")


def _infer_news_event(item: object) -> Optional[dict]:
    """Turn a Steam news item into a conservative version-event candidate."""
    title = str(getattr(item, "title", "") or "").strip()
    feed_label = str(getattr(item, "feed_label", "") or "").strip()
    haystack = f"{title} {feed_label}"
    if not (_VERSION_NEWS_RE.search(haystack) or _VERSION_NEWS_ZH_RE.search(haystack)):
        return None

    lowered = haystack.lower()
    if "dlc" in lowered or "expansion" in lowered or "资料片" in haystack or "扩展包" in haystack:
        event_type = "dlc"
    elif any(token in lowered for token in ("season", "operation", "launch")) or any(token in haystack for token in ("赛季", "行动", "上线")):
        event_type = "major_update"
    elif "content" in lowered or "新内容" in haystack:
        event_type = "content_update"
    else:
        event_type = "patch"

    # Patch notes, season/version titles, and explicit update labels are safe
    # enough to auto-verify. Generic announcements remain candidates only.
    high_confidence = bool(
        re.search(r"patch notes|update notes|hotfix|season|operation|dlc|expansion|补丁|赛季|版本更新", haystack, re.IGNORECASE)
        or "patch" in feed_label.lower()
        or "update" in feed_label.lower()
    )
    event_date = datetime.fromtimestamp(int(getattr(item, "date", 0) or 0), tz=timezone.utc).date().isoformat()
    return {
        "gid": str(getattr(item, "gid", "") or ""),
        "event_name": title[:160] or "Steam version update",
        "event_date": event_date,
        "event_type": event_type,
        "event_description": f"Steam News: {feed_label}"[:2000],
        "source_url": str(getattr(item, "url", "") or "")[:1000],
        "source": f"steam_news:{str(getattr(item, 'gid', '') or '')}"[:80],
        "manual_verified": high_confidence,
        "confidence": "high" if high_confidence else "medium",
    }


@router.post("/version-events", status_code=201)
def create_version_event(request: VersionEventCreate) -> dict:
    """Register the human-verified event that anchors a pre/post analysis."""
    event = {
        "event_id": uuid4().hex,
        "app_id": request.app_id,
        "event_name": request.event_name.strip(),
        "event_date": request.event_date.isoformat(),
        "event_type": request.event_type,
        "event_description": request.event_description,
        "source": request.source,
        "source_url": request.source_url,
        "manual_verified": request.manual_verified,
        "published_at": request.published_at.isoformat() if request.published_at else None,
        "effective_at": request.effective_at.isoformat() if request.effective_at else None,
        "effective_at_start": request.effective_at_start.isoformat() if request.effective_at_start else None,
        "effective_at_end": request.effective_at_end.isoformat() if request.effective_at_end else None,
        "anchor_precision": request.anchor_precision,
        "source_quality": request.source_quality,
        "event_status": request.event_status,
        "concurrent_event_group": request.concurrent_event_group,
    }
    return _event_response(storage.create_version_event(event))


@router.get("/version-events")
def list_version_events(app_id: Optional[int] = None) -> List[dict]:
    return [_event_response(item) for item in storage.list_version_events(app_id)]


@router.post("/version-events/sync-news/{app_id}")
def sync_news_version_events(app_id: int, request: NewsEventSyncRequest = NewsEventSyncRequest()) -> dict:
    """Discover Steam patch/update news and create deduplicated review events.

    High-confidence patch notes are auto-verified and receive a local metrics
    run immediately. Generic announcements are returned as candidates and do
    not create a run until a human verifies them.
    """
    try:
        news_items = fetch_news_for_app(app_id, count=request.news_count, max_length=800)
    except SteamAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    existing = storage.list_version_events(app_id)
    seen_sources = {str(item.get("source") or "") for item in existing}
    seen_urls = {str(item.get("source_url") or "") for item in existing if item.get("source_url")}
    created: List[dict] = []
    candidates: List[dict] = []
    runs: List[dict] = []

    for news_item in news_items:
        candidate = _infer_news_event(news_item)
        if not candidate or not candidate["gid"]:
            continue
        if candidate["source"] in seen_sources or (candidate["source_url"] and candidate["source_url"] in seen_urls):
            continue

        event_id = uuid4().hex
        event = storage.create_version_event({
            "event_id": event_id,
            "app_id": app_id,
            "event_name": candidate["event_name"],
            "event_date": candidate["event_date"],
            "event_type": candidate["event_type"],
            "event_description": candidate["event_description"],
            "source": candidate["source"],
            "source_url": candidate["source_url"],
            "manual_verified": candidate["manual_verified"],
        })
        seen_sources.add(candidate["source"])
        if candidate["source_url"]:
            seen_urls.add(candidate["source_url"])
        created.append({**_event_response(event), "confidence": candidate["confidence"], "news_gid": candidate["gid"]})

        if not candidate["manual_verified"]:
            candidates.append(created[-1])
            continue

        run_id = uuid4().hex
        config = {
            "run_id": run_id,
            "target_game": {"appid": app_id},
            "event": {
                "event_id": event_id,
                "event_name": candidate["event_name"],
                "event_date": candidate["event_date"],
                "event_type": candidate["event_type"],
            },
            "analysis": {
                "pre_window_days": request.pre_window_days,
                "post_window_days": request.post_window_days,
                "analysis_goal": "version_review",
                "max_reviews_per_game": request.max_reviews_per_game,
            },
            "languages": [],
            "competitors": [],
            "taxonomy_version": "sentinext-taxonomy-v1",
            "manifest": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "game_appid": app_id,
                "event_date": candidate["event_date"],
                "taxonomy_version": "sentinext-taxonomy-v1",
                "prompt_version": llm.active_classifier_prompt_version(),
                "model_version": "configured-at-execution",
                "pipeline_version": "player-voice-v1-news-auto",
            },
        }
        run = storage.create_analysis_run({
            "run_id": run_id,
            "target_app_id": app_id,
            "event_id": event_id,
            "config": config,
            "status": "created",
        })
        if request.auto_build_metrics:
            run = build_run_metrics(run_id)
        runs.append({
            "run_id": run_id,
            "event_id": event_id,
            "status": (run or {}).get("status", "created"),
            "event_name": candidate["event_name"],
        })

    return {
        "app_id": app_id,
        "news_scanned": len(news_items),
        "events_created": len(created),
        "events": created,
        "candidates": candidates,
        "runs_created": runs,
    }


@router.post("/runs", status_code=201)
def create_analysis_run(request: AnalysisRunCreate) -> dict:
    """Create an immutable run configuration; ingestion/LLM execution is separate."""
    event = storage.get_version_event(request.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Version event not found.")
    if int(event["app_id"]) != request.target_app_id:
        raise HTTPException(status_code=400, detail="Event app_id must match target_app_id.")
    normalized_languages = [str(language).strip().lower() for language in request.languages if str(language).strip()]
    invalid_languages = sorted(set(normalized_languages) - _STEAM_LANGUAGE_CODES)
    if invalid_languages:
        raise HTTPException(status_code=400, detail=f"Unsupported Steam language code(s): {', '.join(invalid_languages)}.")
    if len(set(request.competitor_app_ids)) != len(request.competitor_app_ids):
        raise HTTPException(status_code=400, detail="Competitor app IDs must be unique.")
    if request.target_app_id in request.competitor_app_ids:
        raise HTTPException(status_code=400, detail="Target game cannot also be a competitor.")

    run_id = uuid4().hex
    config = {
        "run_id": run_id,
        "target_game": {"appid": request.target_app_id},
        "event": {
            "event_id": request.event_id,
            "event_name": event["event_name"],
            "event_date": event["event_date"],
            "event_type": event["event_type"],
        },
        "analysis": {
            "pre_window_days": request.pre_window_days,
            "post_window_days": request.post_window_days,
            "analysis_goal": request.analysis_goal,
            "max_reviews_per_game": request.max_reviews_per_game,
            "semantic_limit": request.semantic_limit,
            "analysis_mode": request.analysis_goal,
            "comparison_event_id": request.comparison_event_id,
        },
        "languages": normalized_languages,
        "competitors": [{"appid": app_id} for app_id in request.competitor_app_ids],
        "taxonomy_version": request.taxonomy_version,
        "manifest": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "game_appid": request.target_app_id,
            "event_date": event["event_date"],
            "taxonomy_version": request.taxonomy_version,
            "prompt_version": llm.active_classifier_prompt_version(),
            "model_version": "configured-at-execution",
            "pipeline_version": "player-voice-v1",
        },
    }
    return storage.create_analysis_run({
        "run_id": run_id,
        "target_app_id": request.target_app_id,
        "event_id": request.event_id,
        "config": config,
        "status": "created",
    })


def _build_autopilot_plan(request: VersionReviewPlanRequest) -> dict:
    events = storage.list_version_events(request.app_id)
    if not events:
        # No official Steam News item is still a valid, non-blocking state.
        # Create one explicit current-snapshot anchor so the user can start a
        # descriptive review while the event catalog remains empty.
        snapshot_id = uuid4().hex
        snapshot = storage.create_version_event({
            "event_id": snapshot_id,
            "app_id": request.app_id,
            "event_name": "当前版本快照（来源不足）",
            "event_date": datetime.now(timezone.utc).date().isoformat(),
            "event_type": "other",
            "event_description": "未发现可用的 Steam 官方版本公告；本次仅生成宽窗口描述性分析。",
            "source": "autopilot:current_snapshot",
            "source_url": None,
            "manual_verified": False,
            "anchor_precision": "unresolved",
            "source_quality": "insufficient",
            "event_status": "conflicted",
        })
        events = [snapshot]
    selected_raw = next((item for item in events if item.get("event_id") == request.event_id), events[0])
    selected = resolve_event(selected_raw)
    newer = selected
    older = next((resolve_event(item) for item in events if request.comparison_event_id and item.get("event_id") == request.comparison_event_id), None) or choose_previous_comparable(events, selected)
    # V2 names the lifecycle populations chronologically: A is older, B newer.
    if older and (older.get("effective_at") or older.get("event_date")) > (newer.get("effective_at") or newer.get("event_date")):
        older, newer = newer, older
    comparison = older
    cached_reviews = storage.load_reviews(request.app_id, limit=None)
    plan = build_review_acquisition_plan(request.app_id, selected, comparison, cached_reviews, request.semantic_limit, request.mode, request.window_days)
    plan.update({"selected_event": newer, "comparison_event": comparison, "event_a": comparison, "event_b": newer, "event_catalog_size": len(events), "event_resolution": newer.get("resolution_status"), "manual_correction_optional": True, "comparison_must_wait_for_coverage": True})
    return plan


@router.post("/version-review/plan")
def create_version_review_plan(request: VersionReviewPlanRequest) -> dict:
    """Build a deterministic plan; this endpoint never calls a semantic provider."""
    return _build_autopilot_plan(request)


@router.post("/version-review/start", status_code=202)
def start_version_review(request: VersionReviewStartRequest, background_tasks: BackgroundTasks) -> dict:
    plan = _build_autopilot_plan(request)
    selected = plan["selected_event"]
    event_id = str(selected["event_id"])
    created = create_analysis_run(AnalysisRunCreate(target_app_id=request.app_id, event_id=event_id, comparison_event_id=plan.get("comparison_event", {}).get("event_id") if plan.get("comparison_event") else None, pre_window_days=request.window_days, post_window_days=request.window_days, max_reviews_per_game=0, analysis_goal=request.mode, semantic_limit=request.semantic_limit))
    storage.save_analysis_run_metrics(created["run_id"], {}, status="running", phase="resolving_events")
    background_tasks.add_task(_execute_version_run, created["run_id"], request.refresh_reviews)
    return {"run": {**created, "status": "running"}, "plan": plan}


@router.get("/runs")
def list_analysis_runs(app_id: Optional[int] = None) -> List[dict]:
    return storage.list_analysis_runs(app_id)


def _run_metrics(run_id: str) -> dict:
    run = storage.get_analysis_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found.")
    metrics = run.get("metrics")
    if not metrics:
        raise HTTPException(status_code=409, detail="Run metrics have not been built yet.")
    return metrics


@router.get("/runs/{run_id}/issues")
def get_run_issues(run_id: str) -> dict:
    metrics = _run_metrics(run_id)
    return {
        "run_id": run_id,
        "priority_score_version": metrics.get("priority_score_version"),
        "issues": metrics.get("issue_cards", []),
    }


@router.get("/runs/{run_id}/evidence")
def get_run_evidence(run_id: str, subcategory: Optional[str] = None, limit: int = 50) -> dict:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100.")
    metrics = _run_metrics(run_id)
    evidence = metrics.get("evidence_cards", [])
    if subcategory:
        evidence = [item for item in evidence if item.get("subcategory") == subcategory]
    return {"run_id": run_id, "evidence": evidence[:limit]}


@router.get("/runs/{run_id}/recommendations")
def get_run_recommendations(run_id: str, limit: int = 10) -> dict:
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 50.")
    metrics = _run_metrics(run_id)
    return {"run_id": run_id, "recommendations": (metrics.get("recommendations") or [])[:limit]}


@router.get("/runs/{run_id}/comparison")
def get_run_comparison(run_id: str, window_days: int = 7) -> dict:
    metrics = _run_metrics(run_id)
    if metrics.get("version_review_v2"):
        if window_days not in (3, 7, 14):
            raise HTTPException(status_code=400, detail="window_days must be 3, 7, or 14")
        run = storage.get_analysis_run(run_id) or {}
        event = storage.get_version_event(run.get("event_id"))
        cfg = (run.get("config") or {}).get("analysis") or {}
        other = storage.get_version_event(str(cfg.get("comparison_event_id"))) if cfg.get("comparison_event_id") else None
        if event and other:
            a_event, b_event = (other, event) if str(other.get("event_date")) <= str(event.get("event_date")) else (event, other)
            reviews = storage.load_reviews(int(run["target_app_id"]), limit=None)
            labels = storage.load_review_labels(int(run["target_app_id"]))
            cc = (metrics.get("coverage_contract") or {})
            ca = cc.get("a") or evaluate_window_coverage(reviews, a_event, window_days, crawl_complete_for_window=None)
            cb = cc.get("b") or evaluate_window_coverage(reviews, b_event, window_days, crawl_complete_for_window=None)
            if window_days > int(cfg.get("post_window_days") or 7):
                ca, cb = evaluate_window_coverage(reviews, a_event, window_days, crawl_complete_for_window=None), evaluate_window_coverage(reviews, b_event, window_days, crawl_complete_for_window=None)
            result = build_comparative_result(a_event, b_event, reviews_in_window(reviews, lifecycle_window(a_event, window_days)), reviews_in_window(reviews, lifecycle_window(b_event, window_days)), labels, window_days=window_days, coverage_a=ca, coverage_b=cb, semantic_limit=int(cfg.get("semantic_limit") or 1000))
            return {"run_id": run_id, "window_days": window_days, "comparison": result}
    return {
        "run_id": run_id,
        "contract": metrics.get("comparison_contract"),
        "target": {
            "periods": metrics.get("periods", {}),
            "categories": metrics.get("categories", []),
        },
        "competitors": metrics.get("competitors", []),
    }


@router.get("/runs/{run_id}/emerging-topics")
def get_run_emerging_topics(run_id: str) -> dict:
    metrics = _run_metrics(run_id)
    return {
        "run_id": run_id,
        "topics": metrics.get("emerging_topic_candidates", []),
        "human_review_required": True,
    }


@router.get("/runs/{run_id}")
def get_analysis_run(run_id: str) -> dict:
    run = storage.get_analysis_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found.")
    return run


@router.get("/runs/{run_id}/result")
def get_analysis_run_result(run_id: str) -> dict:
    """Return the immutable completed result for an exact general run."""
    run = storage.get_analysis_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found.")
    result = storage.get_analysis_run_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Completed run result is not available.")
    return result


@router.get("/runs/{run_id}/analysis-design")
def get_analysis_design_snapshot(run_id: str) -> dict:
    run = storage.get_analysis_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found.")
    design = storage.get_analysis_design(run_id)
    if design is None:
        raise HTTPException(status_code=404, detail="Analysis design is not available for this run.")
    return design


def _execute_version_run(run_id: str, refresh_reviews: bool = True) -> None:
    """Fetch the event window, classify only missing labels, then build metrics."""
    run = storage.get_analysis_run(run_id)
    if run is None:
        return
    config = run.get("config") or {}
    event = storage.get_version_event(run["event_id"])
    if event is None:
        storage.save_analysis_run_metrics(run_id, {}, status="failed", error="Version event not found.")
        return

    try:
        storage.save_analysis_run_metrics(run_id, {}, status="running", phase="planning")
        app_id = int(run["target_app_id"])
        analysis_config = config.get("analysis") or {}
        max_reviews = int(analysis_config.get("max_reviews_per_game", 0))
        event_date = date.fromisoformat(str(event["event_date"]))
        comparison_event_id = analysis_config.get("comparison_event_id")
        comparison_event = storage.get_version_event(str(comparison_event_id)) if comparison_event_id else None
        comparison_date = date.fromisoformat(str(comparison_event["event_date"])) if comparison_event and comparison_event.get("event_date") else None
        lifecycle_comparison = bool(comparison_event and str(analysis_config.get("analysis_goal") or "") == "version_comparison")
        pre_days = int(analysis_config.get("pre_window_days", 28))
        post_days = int(analysis_config.get("post_window_days", 28))
        event_start = int(datetime.combine(event_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        comparison_start = int(datetime.combine(comparison_date, datetime.min.time(), tzinfo=timezone.utc).timestamp()) if comparison_date else event_start
        lower = min(event_start, comparison_start) - (0 if lifecycle_comparison else pre_days) * 86400
        if refresh_reviews:
            storage.save_analysis_run_metrics(run_id, {}, status="running", phase="fetching_historical_reviews")
            # Steam's `all` filter is helpfulness-ranked, not a chronological
            # archive.  Combining it with a stop timestamp was the concrete
            # source of the HELLDIVERS 2 3113-vs-17 false window: the crawl
            # could stop after a non-chronological page.  `recent` is the
            # chronological acquisition contract for lifecycle backfills.
            fetched = fetch_reviews(
                app_id,
                count=max_reviews,
                language="all",
                filter_type="recent",
                stop_before_timestamp=lower,
            )
            if fetched:
                storage.upsert_reviews(app_id, fetched)

        # Persist the acquisition proof before semantic work.  A run resumed
        # without refresh cannot claim coverage from the local SQLite cache.
        coverage_reviews = storage.load_reviews(app_id, limit=None)
        coverage_a = evaluate_window_coverage(
            coverage_reviews, comparison_event or event, post_days,
            crawl_complete_for_window=True if refresh_reviews else None,
            coverage_source="steam_recent_backfill" if refresh_reviews else "local_sqlite_cache",
        )
        coverage_b = evaluate_window_coverage(
            coverage_reviews, event, post_days,
            crawl_complete_for_window=True if refresh_reviews else None,
            coverage_source="steam_recent_backfill" if refresh_reviews else "local_sqlite_cache",
        )
        coverage_contract = {"window_days": post_days, "a": coverage_a, "b": coverage_b, "gate": "PASS" if coverage_a["coverage_status"] == "COMPLETE" and coverage_b["coverage_status"] == "COMPLETE" else "BLOCKED"}
        storage.save_analysis_run_metrics(run_id, {"coverage_contract": coverage_contract}, status="running", phase="validating_windows")
        if coverage_contract["gate"] != "PASS":
            storage.save_analysis_run_metrics(run_id, {"schema_version": "version-review-v2", "coverage_contract": coverage_contract, "comparison_status": "BLOCKED", "blocking_reason": "Lifecycle window coverage is not complete; historical backfill or wider window is required."}, status="blocked_coverage", phase="validating_windows")
            return

        reviews = storage.load_reviews(app_id, limit=None if max_reviews <= 0 else max_reviews)
        storage.save_analysis_run_metrics(run_id, {}, status="running", phase="building_windows")
        if lifecycle_comparison:
            event_a_reviews = reviews_in_window(reviews, lifecycle_window(comparison_event, post_days))
            event_b_reviews = reviews_in_window(reviews, lifecycle_window(event, post_days))
            window_reviews = list({str(item.get("recommendationid") or item.get("review_id")): item for item in [*event_a_reviews, *event_b_reviews]}.values())
        else:
            window_reviews = [review for review in reviews if lower <= int(review.get("timestamp_created") or 0) <= max(event_start, comparison_start) + post_days * 86400]
        semantic_limit = int(analysis_config.get("semantic_limit") or 1000)
        # Raw metrics retain the full window; only this deterministic sample
        # enters the semantic label path.
        semantic_reviews = deterministic_stratified_sample(window_reviews, semantic_limit, f"{app_id}:{run_id}:{event.get('event_id')}")
        game_context = fetch_app_details(app_id) or {}
        storage.save_analysis_run_metrics(run_id, {}, status="running", phase="classifying_version_a")
        last_progress = {"value": -1}

        def _classification_progress(phase: str):
            def _callback(processed: int, total: int) -> None:
                # Persist coarse progress so the UI and stale-run recovery can
                # distinguish a slow LLM call from a dead worker.
                if processed == total or processed == 0 or processed - last_progress["value"] >= 25:
                    last_progress["value"] = processed
                    storage.save_analysis_run_metrics(
                        run_id,
                        {"classification_progress": {"phase": phase, "processed": processed, "total": total}},
                        status="running",
                        phase=phase,
                    )
            return _callback

        if not lifecycle_comparison:
            event_a_reviews = [r for r in window_reviews if event_start - pre_days * 86400 <= int(r.get("timestamp_created") or 0) <= event_start + post_days * 86400]
        with llm.llm_usage_context(app_id=app_id, run_id=run_id, phase="classifying", operation="version_review", prompt_version=llm.active_classifier_prompt_version(), taxonomy_version=llm.TAXONOMY_VERSION, requested_review_count=len(event_a_reviews)):
            llm.ensure_review_labels(app_id, deterministic_stratified_sample(event_a_reviews, semantic_limit, f"{app_id}:{run_id}:{event.get('event_id')}"), game_context=game_context, progress_callback=_classification_progress("classifying_version_a"))
        if comparison_event and comparison_date:
            storage.save_analysis_run_metrics(run_id, {}, status="running", phase="classifying_version_b")
            comparison_start = int(datetime.combine(comparison_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
            if not lifecycle_comparison:
                event_b_reviews = [r for r in window_reviews if comparison_start - pre_days * 86400 <= int(r.get("timestamp_created") or 0) <= comparison_start + post_days * 86400]
            with llm.llm_usage_context(app_id=app_id, run_id=run_id, phase="classifying", operation="version_review", prompt_version=llm.active_classifier_prompt_version(), taxonomy_version=llm.TAXONOMY_VERSION, requested_review_count=len(event_b_reviews)):
                last_progress["value"] = -1
                llm.ensure_review_labels(app_id, deterministic_stratified_sample(event_b_reviews, semantic_limit, f"{app_id}:{run_id}:{comparison_event.get('event_id')}"), game_context=game_context, progress_callback=_classification_progress("classifying_version_b"))

        # Reuse the existing deterministic metrics builder after the scoped
        # labels are available. No additional LLM call is made here.
        storage.save_analysis_run_metrics(run_id, {"coverage_contract": coverage_contract}, status="running", phase="comparing")
        build_run_metrics(run_id)
    except Exception as exc:
        logger.exception("Version run execution failed for %s", run_id)
        storage.save_analysis_run_metrics(run_id, {}, status="failed", error=str(exc))


@router.post("/runs/{run_id}/execute", status_code=202)
def execute_analysis_run(
    run_id: str,
    request: VersionRunExecuteRequest = VersionRunExecuteRequest(),
    background_tasks: BackgroundTasks = None,
) -> dict:
    """Execute a selected version run, fetching only its event window first."""
    run = storage.get_analysis_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found.")
    # A process restart can leave an empty running record behind. It is safe
    # to resume those records; a run with metrics is genuinely complete.
    if run.get("status") == "running" and run.get("metrics"):
        return run
    if background_tasks is None:
        _execute_version_run(run_id, request.refresh_reviews)
    else:
        background_tasks.add_task(_execute_version_run, run_id, request.refresh_reviews)
    return {**run, "status": "running"}


@router.post("/runs/{run_id}/metrics")
def build_run_metrics(run_id: str) -> dict:
    """Compute a deterministic first-pass pre/post report from stored reviews.

    This endpoint intentionally does not fetch or classify data. It makes the
    new run contract useful immediately while reusing SentiNext's existing
    ingestion and label cache. Target and configured competitor games are
    evaluated with the same event-window contract.
    """
    run = storage.get_analysis_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found.")
    event = storage.get_version_event(run["event_id"])
    if event is None:
        raise HTTPException(status_code=500, detail="Run references a missing version event.")

    config = run.get("config") or {}
    analysis_config = config.get("analysis") or {}
    comparison_event = storage.get_version_event(str(analysis_config.get("comparison_event_id"))) if analysis_config.get("comparison_event_id") else None
    event_date = date.fromisoformat(str(event["event_date"]))
    pre_window_days = int(analysis_config.get("pre_window_days", 28))
    post_window_days = int(analysis_config.get("post_window_days", 28))
    max_reviews = int(analysis_config.get("max_reviews_per_game", 0))
    target_app_id = int(run["target_app_id"])
    reviews = storage.load_reviews(target_app_id, limit=None if max_reviews <= 0 else max_reviews)
    labels = storage.load_review_labels(target_app_id)
    v2_result = None
    analysis_goal = str(analysis_config.get("analysis_goal") or "")
    if analysis_goal == "version_comparison" and comparison_event and comparison_event.get("event_date"):
        # Chronological A/B orientation is part of the V2 result contract.
        event_a, event_b = comparison_event, event
        a_window = lifecycle_window(event_a, post_window_days)
        b_window = lifecycle_window(event_b, post_window_days)
        a_reviews = reviews_in_window(reviews, a_window)
        b_reviews = reviews_in_window(reviews, b_window)
        stored_contract = (run.get("metrics") or {}).get("coverage_contract") or {}
        coverage_a = stored_contract.get("a") or evaluate_window_coverage(reviews, event_a, post_window_days, crawl_complete_for_window=None, coverage_source="local_sqlite_cache")
        coverage_b = stored_contract.get("b") or evaluate_window_coverage(reviews, event_b, post_window_days, crawl_complete_for_window=None, coverage_source="local_sqlite_cache")
        v2_result = build_comparative_result(event_a, event_b, a_reviews, b_reviews, labels, window_days=post_window_days, coverage_a=coverage_a, coverage_b=coverage_b, semantic_limit=int(analysis_config.get("semantic_limit") or 1000))
        v2_result["window_sensitivity"] = []
        for days in (3, 7, 14):
            aw, bw = lifecycle_window(event_a, days), lifecycle_window(event_b, days)
            v2_result["window_sensitivity"].append({"window_days": days, "coverage_status": "COMPLETE" if days <= post_window_days and coverage_a.get("coverage_status") == "COMPLETE" and coverage_b.get("coverage_status") == "COMPLETE" else "UNKNOWN", "a_raw_count": len(reviews_in_window(reviews, aw)), "b_raw_count": len(reviews_in_window(reviews, bw))})
    profile = infer_game_profile({}, reviews)
    event_payload = resolve_event_anchor({
        **event,
        # Legacy event_date remains available to the version-metrics executor,
        # but an unverified event must not become an adaptive anchor merely
        # because that legacy field exists.
        "event_date": event.get("event_date") if event.get("manual_verified") or event.get("effective_at") else None,
        "effective_at": event.get("effective_at") or (event.get("event_date") if event.get("manual_verified") else None),
        "event_status": event.get("event_status") or ("resolved" if event.get("manual_verified") else "confounded"),
    })
    adaptive_window = select_adaptive_window(profile, event_payload, reviews)
    adaptive_anchor = event_payload.get("effective_at")
    adaptive_event_date = date.fromisoformat(str(adaptive_anchor)[:10]) if adaptive_anchor else None
    adaptive_days = int(adaptive_window.get("pre_days") or pre_window_days)
    adaptive_pre, adaptive_post = [], []
    if adaptive_event_date and event_payload.get("anchor_precision") != "range":
        for review in reviews:
            stamp = review.get("timestamp_created")
            if not stamp:
                continue
            review_date = datetime.fromtimestamp(int(stamp), tz=timezone.utc).date()
            if adaptive_event_date - timedelta(days=adaptive_days) <= review_date < adaptive_event_date:
                adaptive_pre.append(review)
            elif adaptive_event_date < review_date <= adaptive_event_date + timedelta(days=adaptive_days):
                adaptive_post.append(review)
    design = build_analysis_design(
        app_id=target_app_id,
        analysis_type=str(analysis_config.get("analysis_goal") or "event_impact"),
        profile=profile,
        event=event_payload,
        window=adaptive_window,
        sensitivity_windows=[{"label": f"plus_minus_{days}d", "pre_days": days, "post_days": days} for days in adaptive_window.get("sensitivity_days", [])],
        comparison_basis="lifecycle_matched" if comparison_event else "event_centered",
        population_rules={"minimum_per_side": 20, "no_silent_reweight": True},
        metrics=["recommendation_rate", "review_volume", "issue_rate", "request_rate"],
    )
    try:
        storage.save_analysis_design(design, run_id)
    except Exception:
        # Legacy databases may be opened before the additive migration; keep
        # the existing metrics path available while startup applies migration.
        pass
    metrics = calculate_version_metrics(
        reviews,
        labels,
        event_date,
        pre_window_days=pre_window_days,
        post_window_days=post_window_days,
        run_id=run_id,
        app_id=target_app_id,
    )
    if v2_result is not None:
        metrics["version_review_v2"] = v2_result
        metrics["comparison_status"] = v2_result["comparison_status"]
    if analysis_goal == "version_comparison" and comparison_event and comparison_event.get("event_date"):
        comparison_date = date.fromisoformat(str(comparison_event["event_date"]))
        comparison_metrics = calculate_version_metrics(
            reviews,
            labels,
            comparison_date,
            pre_window_days=pre_window_days,
            post_window_days=post_window_days,
            run_id=run_id,
            app_id=target_app_id,
        )
        metrics["version_a"] = {"event": event, "metrics": metrics.copy()}
        metrics["version_b"] = {"event": comparison_event, "metrics": comparison_metrics}
        metrics["comparison_contract"] = {
            "comparison_type": "lifecycle_matched",
            "event_a_id": event.get("event_id"),
            "event_b_id": comparison_event.get("event_id"),
            "event_a_date": event_date.isoformat(),
            "event_b_date": comparison_date.isoformat(),
            "window_days": {"pre": pre_window_days, "post": post_window_days},
            "same_taxonomy_version": config.get("taxonomy_version"),
            "target_app_id": target_app_id,
        }
    raw_window_count = sum(
        1 for review in reviews
        if review.get("timestamp_created")
        and event_date - timedelta(days=pre_window_days) <= datetime.fromtimestamp(int(review["timestamp_created"]), tz=timezone.utc).date() <= event_date + timedelta(days=post_window_days)
    )
    semantic_limit = int(analysis_config.get("semantic_limit") or 1000)
    metrics["population_contract"] = {
        "raw_window_count": raw_window_count,
        "semantic_sample_count": min(raw_window_count, semantic_limit),
        "semantic_sample_fraction": (min(raw_window_count, semantic_limit) / raw_window_count) if raw_window_count else 0.0,
        "classified_count": min(raw_window_count, semantic_limit),
        "sampling_method": "deterministic_stratified_sha256",
        "sampling_seed": f"{target_app_id}:{run_id}:{event.get('event_id')}",
    }
    competitor_results = []
    for competitor in config.get("competitors") or []:
        competitor_app_id = int(competitor["appid"])
        competitor_reviews = storage.load_reviews(competitor_app_id, limit=None if max_reviews <= 0 else max_reviews)
        competitor_labels = storage.load_review_labels(competitor_app_id)
        competitor_metrics = calculate_version_metrics(
            competitor_reviews,
            competitor_labels,
            event_date,
            pre_window_days=pre_window_days,
            post_window_days=post_window_days,
            run_id=run_id,
            app_id=competitor_app_id,
        )
        competitor_results.append({
            "app_id": competitor_app_id,
            "periods": competitor_metrics["periods"],
            "categories": competitor_metrics["categories"],
            "daily_review_volume": competitor_metrics["daily_review_volume"],
            "warnings": competitor_metrics["warnings"],
        })
    metrics["competitors"] = competitor_results
    metrics["adaptive_analysis"] = {
        "design": design,
        "population_comparability": population_comparability(adaptive_pre, adaptive_post),
    }
    adaptive_block = metrics["adaptive_analysis"]
    adaptive_block["robustness"] = robustness_matrix(
        {"primary": (adaptive_pre, adaptive_post)},
        lambda review: not bool(review.get("voted_up")),
    )
    adaptive_block["evidence_grade"] = evidence_grade(
        sample_support=min(len(adaptive_pre), len(adaptive_post)),
        robustness=adaptive_block["robustness"],
        comparability=adaptive_block["population_comparability"],
        verified_evidence_count=0,
        label_reliability="warn",
        confounder_risk=design.get("confounder_risk", "medium"),
    )
    if not comparison_event:
        metrics["comparison_contract"] = {
            "same_event_date": event_date.isoformat(),
            "same_pre_window_days": pre_window_days,
            "same_post_window_days": post_window_days,
            "same_taxonomy_version": config.get("taxonomy_version"),
            "target_app_id": target_app_id,
        }
    updated = storage.save_analysis_run_metrics(run_id, metrics, status="completed", phase="finalizing")
    return updated or {**run, "metrics": metrics, "status": "completed"}
