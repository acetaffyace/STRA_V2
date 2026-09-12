"""Deterministic, read-only presentation projections.

These helpers intentionally refuse to widen an exact run scope.  The API
layer can therefore return an explicit unavailable state when the current
immutable result does not contain enough provenance for a projection.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from . import storage

PROJECTION_VERSION = "presentation-projections-v1"


def _unavailable(projection: str, reason: str, *, run_id: str | None = None, app_id: int | None = None) -> dict[str, Any]:
    return {
        "projection": projection,
        "projection_version": PROJECTION_VERSION,
        "available": False,
        "run_id": run_id,
        "app_id": app_id,
        "points": [],
        "unavailable_reason": reason,
    }


def _exact_general_result(run_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    run = storage.get_analysis_run(run_id)
    if not run:
        return None, None, None
    if run.get("run_type") != "general_analysis" or run.get("status") != "completed":
        return run, None, None
    result = storage.get_analysis_run_result(run_id)
    return run, result, (result or {}).get("metadata") or {}


def _review_timestamp(review: dict[str, Any]) -> datetime | None:
    raw = review.get("timestamp_created")
    if raw is None:
        raw = review.get("created_at")
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        text = str(raw).strip()
        if text.isdigit():
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _complete_temporal_source(result: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, str | None]:
    metadata = result.get("metadata") or {}
    provenance = metadata.get("population_provenance")
    if not isinstance(provenance, dict):
        return None, "historical_run_population_provenance_unavailable"
    if provenance.get("schema_version") != "general-population-temporal-v1":
        return None, "population_provenance_schema_unknown"
    rows = provenance.get("rows")
    expected = provenance.get("population_count")
    if provenance.get("complete") is not True or not isinstance(rows, list) or not isinstance(expected, int):
        return None, "population_provenance_incomplete"
    if expected != len(rows):
        return None, "population_provenance_count_mismatch"
    normalized: list[dict[str, Any]] = []
    review_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            return None, "population_provenance_invalid_row"
        review_id = str(row.get("review_id") or "")
        timestamp = row.get("timestamp_created")
        voted_up = row.get("voted_up")
        if not review_id or review_id in review_ids or not isinstance(timestamp, int) or not isinstance(voted_up, bool):
            return None, "population_provenance_invalid_row"
        review_ids.add(review_id)
        normalized.append({"review_id": review_id, "timestamp_created": timestamp, "voted_up": voted_up})
    return normalized, None


def _periods(rows: Iterable[dict[str, Any]], start: date | None, end: date | None) -> list[date]:
    observed = {_review_timestamp(row).date() for row in rows if _review_timestamp(row) is not None}
    if start is None or end is None or end < start:
        return sorted(observed)
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def daily_review_volume(run_id: str, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    run, result, _ = _exact_general_result(run_id)
    projection = "daily_review_volume"
    if not run:
        return _unavailable(projection, "run_not_found", run_id=run_id)
    if not result:
        return _unavailable(projection, "immutable_result_not_available", run_id=run_id, app_id=run.get("target_app_id"))
    rows, reason = _complete_temporal_source(result)
    if rows is None:
        return _unavailable(projection, reason or "exact_population_unavailable", run_id=run_id, app_id=run.get("target_app_id"))
    counts: dict[date, int] = {}
    for row in rows:
        timestamp = _review_timestamp(row)
        if timestamp is not None:
            counts[timestamp.date()] = counts.get(timestamp.date(), 0) + 1
    periods = _periods(rows, start, end)
    return {
        "projection": projection,
        "projection_version": PROJECTION_VERSION,
        "available": True,
        "run_id": run_id,
        "app_id": run["target_app_id"],
        "bucket": "day",
        "bucket_timezone": "UTC",
        "population_scope": "exact_immutable_run_result",
        "population_count": len(rows),
        "window": {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
        "points": [{"period": period.isoformat(), "review_count": counts.get(period, 0)} for period in periods],
        "unavailable_reason": None,
    }


def daily_recommendation_rate(run_id: str, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    run, result, _ = _exact_general_result(run_id)
    projection = "daily_recommendation_rate"
    if not run:
        return _unavailable(projection, "run_not_found", run_id=run_id)
    if not result:
        return _unavailable(projection, "immutable_result_not_available", run_id=run_id, app_id=run.get("target_app_id"))
    rows, reason = _complete_temporal_source(result)
    if rows is None:
        return _unavailable(projection, reason or "exact_population_unavailable", run_id=run_id, app_id=run.get("target_app_id"))
    buckets: dict[date, dict[str, int]] = {}
    for row in rows:
        timestamp = _review_timestamp(row)
        if timestamp is None:
            continue
        bucket = buckets.setdefault(timestamp.date(), {"review_count": 0, "recommended_count": 0})
        bucket["review_count"] += 1
        if row.get("voted_up") is True:
            bucket["recommended_count"] += 1
    periods = _periods(rows, start, end)
    points = []
    for period in periods:
        bucket = buckets.get(period, {"review_count": 0, "recommended_count": 0})
        total = bucket["review_count"]
        points.append({
            "period": period.isoformat(),
            "review_count": total,
            "recommended_count": bucket["recommended_count"],
            "recommendation_rate": bucket["recommended_count"] / total if total else None,
        })
    return {
        "projection": projection,
        "projection_version": PROJECTION_VERSION,
        "available": True,
        "run_id": run_id,
        "app_id": run["target_app_id"],
        "bucket": "day",
        "bucket_timezone": "UTC",
        "population_scope": "exact_immutable_run_result",
        "population_count": len(rows),
        "window": {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
        "points": points,
        "unavailable_reason": None,
    }


def _recommendation_rate(result: dict[str, Any]) -> float | None:
    insights = result.get("insights") or {}
    observation = (insights.get("metric_provenance") or {}).get("recommendation_rate") or {}
    value = observation.get("value")
    if isinstance(value, (int, float)):
        return float(value)
    value = insights.get("recommendation")
    return float(value) if isinstance(value, (int, float)) else None


def recent_analysis_summary(limit: int = 20) -> dict[str, Any]:
    games = {int(game["app_id"]): game for game in storage.load_starred_games() if game.get("app_id") is not None}
    items: list[dict[str, Any]] = []
    for history in storage.list_analysis_history(limit=max(1, min(limit, 100))):
        if history.get("run_type") != "general_analysis" or history.get("status") != "completed":
            continue
        run_id = str(history["run_id"])
        run = storage.get_analysis_run(run_id) or {}
        result = storage.get_analysis_run_result(run_id) or {}
        game = games.get(int(history["app_id"])) or {}
        metadata = result.get("metadata") or {}
        game_metadata = game.get("metadata") or {}
        items.append({
            "app_id": int(history["app_id"]),
            "run_id": run_id,
            "game_title": game.get("name") or metadata.get("app_name") or None,
            "artwork": metadata.get("header_image") or game_metadata.get("header_image") or None,
            "run_type": history.get("run_type"),
            "analysis_mode": (run.get("config") or {}).get("analysis_mode") or metadata.get("mode"),
            "status": history.get("status"),
            "completed_at": run.get("completed_at") or history.get("completed_at"),
            "requested_count": run.get("requested_review_count") or metadata.get("requested"),
            "retrieved_count": run.get("retrieved_count") or metadata.get("retrieved_count") or metadata.get("retrieved"),
            "analysis_population_count": run.get("analysis_population_count") if run.get("analysis_population_count") is not None else metadata.get("analysis_population_count"),
            "classified_count": run.get("classified_count"),
            "recommendation_rate": _recommendation_rate(result),
            "reopen_url": f"/dashboard?game={int(history['app_id'])}&run={run_id}",
        })
    return {"projection": "recent_analysis_summary", "projection_version": PROJECTION_VERSION, "items": items}


def _event_summary(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not event:
        return None
    return {"event_id": event.get("event_id"), "event_date": event.get("event_date"), "event_name": event.get("event_name")}


def version_comparison_population_strip(run_id: str) -> dict[str, Any]:
    run = storage.get_analysis_run(run_id)
    projection = "version_comparison_population_strip"
    if not run:
        return _unavailable(projection, "run_not_found", run_id=run_id)
    if run.get("run_type") != "version_review" or run.get("status") != "completed":
        return _unavailable(projection, "completed_version_review_run_required", run_id=run_id, app_id=run.get("target_app_id"))
    metrics = run.get("metrics") or {}
    v2 = metrics.get("version_review_v2")
    if not isinstance(v2, dict):
        return _unavailable(projection, "version_review_v2_result_required", run_id=run_id, app_id=run.get("target_app_id"))
    raw_a = v2.get("raw_metrics_a") or {}
    raw_b = v2.get("raw_metrics_b") or {}
    deltas = v2.get("raw_metric_deltas") or {}
    cfg = (run.get("config") or {}).get("analysis") or {}
    event_a = storage.get_version_event(str(v2.get("event_a_id"))) if v2.get("event_a_id") else None
    event_b = storage.get_version_event(str(v2.get("event_b_id"))) if v2.get("event_b_id") else None
    def safe_count(value: Any) -> int | None:
        return int(value) if isinstance(value, int) and value > 0 else None
    gate = v2.get("coverage_gate") or {}
    return {
        "projection": projection,
        "projection_version": PROJECTION_VERSION,
        "available": True,
        "run_id": run_id,
        "app_id": int(run["target_app_id"]),
        "previous_event": _event_summary(event_a),
        "current_event": _event_summary(event_b),
        "window_days": v2.get("window_days") or cfg.get("post_window_days"),
        "raw_count_a": raw_a.get("reviews"),
        "raw_count_b": raw_b.get("reviews"),
        "reviews_per_day_a": raw_a.get("reviews_per_day"),
        "reviews_per_day_b": raw_b.get("reviews_per_day"),
        "recommendation_rate_a": raw_a.get("recommendation_rate"),
        "recommendation_rate_b": raw_b.get("recommendation_rate"),
        "recommendation_delta_pp": deltas.get("recommendation_rate_pp"),
        "semantic_sample_a": v2.get("a_semantic_sample_count"),
        "semantic_sample_b": v2.get("b_semantic_sample_count"),
        "classified_count_a": safe_count(v2.get("a_classified_count")),
        "classified_count_b": safe_count(v2.get("b_classified_count")),
        "coverage_status_a": v2.get("a_coverage_status") or "UNKNOWN",
        "coverage_status_b": v2.get("b_coverage_status") or "UNKNOWN",
        "coverage_gate": gate.get("status") or "UNKNOWN",
        "comparison_status": v2.get("comparison_status") or "UNKNOWN",
        "unavailable_reason": None,
    }


def provenance_strip(run_id: str) -> dict[str, Any]:
    run = storage.get_analysis_run(run_id)
    projection = "provenance_strip"
    if not run:
        return _unavailable(projection, "run_not_found", run_id=run_id)
    result = storage.get_analysis_run_result(run_id) or {}
    metadata = result.get("metadata") or {}
    config = run.get("config") or {}
    manifest = config.get("manifest") or {}
    design = storage.get_analysis_design(run_id)
    metrics = run.get("metrics") or {}
    schema_version = "version-review-v2" if isinstance(metrics.get("version_review_v2"), dict) else (metadata.get("schema_version") or "general-analysis")
    return {
        "projection": projection,
        "projection_version": PROJECTION_VERSION,
        "available": True,
        "run_id": run_id,
        "app_id": int(run["target_app_id"]),
        "source": metadata.get("source") or config.get("source"),
        "analysis_mode": (config.get("analysis") or {}).get("analysis_mode") or metadata.get("mode"),
        "analysis_window": {"start": run.get("window_start") or metadata.get("window_start"), "end": run.get("window_end") or metadata.get("window_end"), "data_cutoff": run.get("data_cutoff") or metadata.get("data_cutoff")},
        "run_type": run.get("run_type"),
        "result_schema_version": schema_version,
        "taxonomy_version": run.get("taxonomy_version") or manifest.get("taxonomy_version"),
        "prompt_version": run.get("prompt_version") or manifest.get("prompt_version"),
        "provider": run.get("provider") or manifest.get("provider"),
        "model_id": run.get("model_id") or manifest.get("model_version"),
        "analysis_design_id": (design or {}).get("design_id"),
        "requested_count": run.get("requested_review_count") or metadata.get("requested"),
        "retrieved_count": run.get("retrieved_count") or metadata.get("retrieved_count") or metadata.get("retrieved"),
        "analysis_population_count": run.get("analysis_population_count") if run.get("analysis_population_count") is not None else metadata.get("analysis_population_count"),
        "classified_count": run.get("classified_count"),
        "fallback_count": run.get("fallback_count"),
        "completed_at": run.get("completed_at"),
        "snapshot_hash": result.get("snapshot_hash"),
        "context_hash": result.get("context_hash"),
        "unavailable_reason": None,
    }
