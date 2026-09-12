"""Deterministic planning primitives for Version Review Autopilot.

This module deliberately stops at planning and sampling. Existing Adaptive
Analysis, evidence, and label-cache implementations remain the execution
authority.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

EVENT_TYPES = {
    "launch", "major_patch", "season", "expansion", "content_drop",
    "balance_patch", "hotfix", "technical_patch", "event_liveops",
    "pricing", "outage", "controversy", "other",
}
COMPARABLE_TYPES = {"launch", "major_patch", "season", "expansion", "content_drop"}


def _iso_day(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def classify_event_type(title: str, raw_type: str | None = None) -> str:
    text = f"{title} {raw_type or ''}".lower()
    if any(x in text for x in ("hotfix", "quick fix")):
        return "hotfix"
    if any(x in text for x in ("season", "operation", "chapter")):
        return "season"
    if any(x in text for x in ("expansion", "dlc", "major update", "version 2", "version 3")):
        return "expansion" if "expansion" in text or "dlc" in text else "major_patch"
    if any(x in text for x in ("balance", "tuning", "weapon")):
        return "balance_patch"
    if any(x in text for x in ("server", "performance", "crash", "technical")):
        return "technical_patch"
    if any(x in text for x in ("content", "new map", "new mission")):
        return "content_drop"
    if any(x in text for x in ("patch", "update", "version")):
        return "major_patch"
    return raw_type if raw_type in EVENT_TYPES else "other"


def resolve_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve an event without making manual verification a prerequisite."""
    result = dict(event)
    result["event_type"] = classify_event_type(str(event.get("event_name") or event.get("title") or ""), event.get("event_type"))
    effective = event.get("effective_at") or event.get("event_date")
    start = _iso_day(event.get("effective_at_start"))
    end = _iso_day(event.get("effective_at_end"))
    anchor = _iso_day(effective)
    source = str(event.get("source") or "")
    source_url = str(event.get("source_url") or "")
    official = source.startswith("steam_news:") or "steamcommunity.com" in source_url or "steampowered.com" in source_url
    if str(event.get("event_status") or "").lower() in {"conflicted", "insufficient", "unresolved"} and not event.get("effective_at"):
        status, precision = "CONFLICTED", "unresolved"
        result["effective_at"] = None
        result["effective_at_range"] = None
    elif start and end and start != end:
        status, precision = "AMBIGUOUS", "range"
        result["effective_at"] = None
        result["effective_at_range"] = [start.isoformat(), end.isoformat()]
    elif anchor:
        status = "SOURCE_CONFIRMED" if official else ("AUTO_CONFIRMED" if event.get("manual_verified") else "INFERRED")
        precision = str(event.get("anchor_precision") or "day")
        result["effective_at"] = anchor.isoformat()
        result["effective_at_range"] = None
    else:
        status, precision = "CONFLICTED", "unresolved"
        result["effective_at"] = None
        result["effective_at_range"] = None
    result["resolution_status"] = status
    result["anchor_precision"] = precision
    result["source_type"] = "steam_official" if official else ("manual" if source == "manual" else "discovered")
    result["discovery_method"] = event.get("discovery_method") or ("steam_news_title_date" if source.startswith("steam_news:") else "existing_catalog")
    result["can_start"] = True
    result["analysis_safety"] = "strict_event_impact" if status in {"AUTO_CONFIRMED", "SOURCE_CONFIRMED", "INFERRED"} and anchor else "descriptive_only"
    return result


def choose_previous_comparable(events: Sequence[Mapping[str, Any]], selected: Mapping[str, Any]) -> dict[str, Any] | None:
    anchor = _iso_day(selected.get("effective_at") or selected.get("event_date"))
    if not anchor:
        return None
    candidates = []
    for event in events:
        resolved = resolve_event(event)
        if str(event.get("event_id")) == str(selected.get("event_id")):
            continue
        event_day = _iso_day(resolved.get("effective_at") or resolved.get("event_date"))
        if event_day and event_day < anchor and resolved["event_type"] in COMPARABLE_TYPES:
            candidates.append((event_day, resolved))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def lifecycle_interval(event: Mapping[str, Any], start_day: int = 0, end_day: int = 7) -> dict[str, Any]:
    anchor = _iso_day(event.get("effective_at") or event.get("event_date"))
    if not anchor:
        return {"start": None, "end": None, "status": "descriptive_only", "event_id": event.get("event_id")}
    # Contract is half-open: [effective_at + start_day, effective_at + end_day).
    return {"start": (anchor + timedelta(days=start_day)).isoformat(), "end": (anchor + timedelta(days=end_day)).isoformat(), "start_day": start_day, "end_day": end_day, "status": "lifecycle_matched", "event_id": event.get("event_id")}


def merge_intervals(intervals: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    parsed = sorted(((_iso_day(x.get("start")), _iso_day(x.get("end"))) for x in intervals), key=lambda pair: pair[0] or date.max)
    merged: list[tuple[date, date]] = []
    for start, end in parsed:
        if not start or not end:
            continue
        if merged and start <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return [{"start": start.isoformat(), "end": end.isoformat()} for start, end in merged]


def _coverage_for_interval(reviews: Sequence[Mapping[str, Any]], interval: Mapping[str, Any]) -> int:
    start, end = _iso_day(interval.get("start")), _iso_day(interval.get("end"))
    if not start or not end:
        return 0
    return sum(1 for review in reviews if (created := review.get("timestamp_created")) and start <= datetime.fromtimestamp(int(created), tz=timezone.utc).date() <= end)


def deterministic_stratified_sample(reviews: Sequence[Mapping[str, Any]], limit: int, seed: str) -> list[dict[str, Any]]:
    if limit <= 0 or len(reviews) <= limit:
        return [dict(item) for item in reviews]
    buckets: dict[tuple[Any, Any, Any], list[Mapping[str, Any]]] = {}
    for review in reviews:
        created = int(review.get("timestamp_created") or 0)
        day = datetime.fromtimestamp(created, tz=timezone.utc).date().isoformat() if created else "unknown"
        bucket = (day, bool(review.get("voted_up")), str(review.get("language") or "unknown"))
        buckets.setdefault(bucket, []).append(review)
    ranked = sorted((int(hashlib.sha256(f"{seed}:{review.get('recommendationid') or review.get('review_id') or json.dumps(review, sort_keys=True)}".encode()).hexdigest()[:12], 16), review) for review in reviews)
    selected = [review for _, review in ranked[:limit]]
    return [dict(item) for item in selected]


def build_review_acquisition_plan(app_id: int, selected_event: Mapping[str, Any], comparison_event: Mapping[str, Any] | None, cached_reviews: Sequence[Mapping[str, Any]], semantic_limit: int = 1000, mode: str = "version_comparison", window_days: int = 7) -> dict[str, Any]:
    events = [selected_event] + ([comparison_event] if comparison_event else [])
    intervals = [lifecycle_interval(event, end_day=window_days) for event in events]
    required = merge_intervals(intervals)
    cached = [{**interval, "cached_count": _coverage_for_interval(cached_reviews, interval)} for interval in required]
    cached_intervals = [item for item in cached if item["cached_count"] > 0]
    missing_intervals = [item for item in cached if item["cached_count"] == 0]
    windows = []
    for event, interval in zip(events, intervals):
        count = _coverage_for_interval(cached_reviews, interval)
        windows.append({"event_id": event.get("event_id"), "start": interval["start"], "end": interval["end"], "raw_window_count": count, "semantic_sample_limit": semantic_limit, "semantic_sample_count": min(count, semantic_limit), "sampling_method": "all_reviews" if count < semantic_limit else "deterministic_stratified_sha256", "all_reviews_when_under_limit": count < semantic_limit, "sampling_seed": f"{app_id}:{event.get('event_id')}"})
    return {"app_id": app_id, "mode": mode, "window_days": window_days, "required_intervals": required, "cached_intervals": cached_intervals, "missing_intervals": missing_intervals, "crawl_plan": {"cache_first": True, "page_backward_until": min((x["start"] for x in required), default=None), "persist_intermediate_reviews": True}, "semantic_sample_plan": {"per_window_limit": semantic_limit, "windows": windows, "under_limit_uses_all_reviews": True}, "analysis_design": {"comparison_basis": "lifecycle_matched", "window_days": window_days, "raw_metrics_use_full_window": True, "semantic_analysis_is_bounded": True, "under_limit_uses_all_reviews": True}}
