"""Deterministic Adaptive Analysis Design Engine.

The engine designs and audits an analysis before Five Questions consumes it.
It deliberately does not call an LLM or infer causality from review aggregates.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4


SCHEMA_VERSION = "adaptive-analysis-v1"
ALGORITHM_VERSION = "adaptive-analysis-engine-v1"
ARCHETYPES = {
    "live_service_competitive", "live_service_pve_mmo", "gacha_liveops",
    "single_player_progression", "strategy_roguelike_systemic",
    "early_access_sandbox", "hybrid_unknown",
}


@dataclass(frozen=True)
class GameAnalysisProfile:
    archetype: str
    reason_codes: tuple[str, ...]
    ambiguity_flags: tuple[str, ...]
    recommended_protocols: tuple[str, ...]
    algorithm_version: str = ALGORITHM_VERSION


@dataclass(frozen=True)
class GameEvent:
    event_id: str
    app_id: int
    event_type: str
    title: str
    published_at: str | None
    effective_at: str | None
    effective_at_range: tuple[str, str] | None
    anchor_precision: str
    source_type: str
    source_ref: str | None
    source_quality: str
    event_status: str
    concurrent_event_group: str | None = None


@dataclass(frozen=True)
class WindowSpec:
    label: str
    pre_days: int
    post_days: int
    reason_codes: tuple[str, ...]
    sensitivity_days: tuple[int, ...]
    status: str = "selected"


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _ts(review: Mapping[str, Any]) -> datetime | None:
    value = review.get("timestamp_created") or review.get("created_at")
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(float(value), timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def infer_game_profile(metadata: Mapping[str, Any] | None, reviews: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Classify game archetype using transparent metadata and velocity rules."""
    metadata = metadata or {}
    genres = {str(x).lower() for x in (metadata.get("genres") or [])}
    categories = {str(x).lower() for x in (metadata.get("categories") or [])}
    reasons: list[str] = []
    flags: list[str] = []
    if any(x in categories for x in {"multi-player", "online pvp", "online multiplayer"}):
        reasons.append("multiplayer")
    if any(x in genres for x in {"free to play", "action", "sports"}) or metadata.get("is_free"):
        reasons.append("live_service_candidate")
    if metadata.get("early_access") or "early access" in categories:
        reasons.append("early_access")
    dates = sorted(item for item in (_ts(r) for r in reviews) if item)
    velocity = len(reviews) / max(1, (dates[-1] - dates[0]).days + 1) if len(dates) >= 2 else 0.0
    if velocity >= 20:
        reasons.append("high_review_velocity")
    if "multi-player" in categories or "online multiplayer" in categories:
        archetype = "live_service_competitive"
        protocols = ("event_impact", "version_longitudinal", "public_opinion_event")
    elif metadata.get("early_access") or "early access" in categories:
        archetype = "early_access_sandbox"
        protocols = ("event_impact", "version_longitudinal", "public_opinion_event")
    elif any(x in genres for x in {"strategy", "indie"}) and velocity < 20:
        archetype = "strategy_roguelike_systemic"
        protocols = ("event_impact", "version_longitudinal")
    else:
        archetype = "hybrid_unknown"
        flags.append("insufficient_profile_metadata")
        protocols = ("current_snapshot", "event_impact")
    return asdict(GameAnalysisProfile(archetype, tuple(sorted(set(reasons))), tuple(flags), protocols))


def resolve_event_anchor(event: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize single/range anchors without silently choosing a date."""
    effective = event.get("effective_at") or event.get("event_date")
    start, end = event.get("effective_at_start"), event.get("effective_at_end")
    if start or end:
        return {**dict(event), "effective_at": None, "effective_at_range": [start, end], "anchor_precision": "range", "event_status": "confounded"}
    if effective:
        return {**dict(event), "effective_at": str(effective), "effective_at_range": None, "anchor_precision": event.get("anchor_precision", "day"), "event_status": event.get("event_status", "resolved")}
    return {**dict(event), "effective_at": None, "effective_at_range": None, "anchor_precision": "unresolved", "event_status": "confounded"}


def select_adaptive_window(profile: Mapping[str, Any], event: Mapping[str, Any], reviews: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or event.get("type") or "other").lower()
    archetype = str(profile.get("archetype") or "hybrid_unknown")
    target = 7 if archetype == "live_service_competitive" else 14
    if event_type in {"hotfix", "outage"}:
        target = 3
    if event_type in {"season", "major_patch", "major_update", "launch"}:
        target = 7 if archetype == "live_service_competitive" else 14
    anchor = str(event.get("effective_at") or event.get("event_date") or "")[:10]
    try:
        anchor_date = date.fromisoformat(anchor)
    except ValueError:
        return asdict(WindowSpec("descriptive_only", target, target, ("unresolved_event_anchor",), (3, 7, 14), "descriptive_only"))
    pre = sum(1 for r in reviews if _ts(r) and anchor_date - timedelta(days=target) <= _ts(r).date() < anchor_date)
    post = sum(1 for r in reviews if _ts(r) and anchor_date < _ts(r).date() <= anchor_date + timedelta(days=target))
    reasons = [f"archetype:{archetype}", f"event_type:{event_type}", "full_week_cycle" if target >= 7 else "short_incident_window"]
    if min(pre, post) < 20:
        reasons.append("support_below_minimum; consider_expanding")
        if target < 28:
            target = 28
    return asdict(WindowSpec(f"plus_minus_{target}d", target, target, tuple(reasons), tuple(x for x in (3, 7, 14, 28) if x != target)))


def _distribution(reviews: Sequence[Mapping[str, Any]], key: str) -> dict[str, float]:
    counts = Counter(str((r.get(key) or "unknown")).lower() for r in reviews)
    total = sum(counts.values()) or 1
    return {k: round(v / total, 6) for k, v in sorted(counts.items())}


def population_comparability(pre: Sequence[Mapping[str, Any]], post: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def rate(items: Sequence[Mapping[str, Any]]) -> float | None:
        vals = [bool(r.get("voted_up")) for r in items if r.get("voted_up") is not None]
        return sum(vals) / len(vals) if vals else None
    pre_lang, post_lang = _distribution(pre, "language"), _distribution(post, "language")
    drift = sum(abs(pre_lang.get(k, 0) - post_lang.get(k, 0)) for k in set(pre_lang) | set(post_lang)) / 2
    status = "fail" if drift >= 0.35 else "warn" if drift >= 0.15 else "pass"
    return {"overall": status, "review_count": {"pre": len(pre), "post": len(post)}, "recommendation_rate": {"pre": rate(pre), "post": rate(post)}, "language_distribution": {"pre": pre_lang, "post": post_lang}, "language_drift": round(drift, 6), "warnings": ["language_drift"] if status != "pass" else []}


def proportion_observation(items: Sequence[Mapping[str, Any]], predicate) -> dict[str, Any]:
    values = [1 if predicate(r) else 0 for r in items]
    n, x = len(values), sum(values)
    if not n:
        return {"rate": None, "support": 0, "ci95": None}
    p = x / n
    z = 1.96
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {"rate": round(p, 6), "support": n, "numerator": x, "ci95": [round(max(0, center - spread), 6), round(min(1, center + spread), 6)]}


def event_impact(pre: Sequence[Mapping[str, Any]], post: Sequence[Mapping[str, Any]], *, topic_predicate=None) -> dict[str, Any]:
    predicate = topic_predicate or (lambda r: not bool(r.get("voted_up")))
    before, after = proportion_observation(pre, predicate), proportion_observation(post, predicate)
    delta = None if before["rate"] is None or after["rate"] is None else round(after["rate"] - before["rate"], 6)
    return {"pre": before, "post": after, "delta": delta, "delta_pp": None if delta is None else round(delta * 100, 3), "comparison_valid": bool(pre and post), "effect_size": delta}


def lifecycle_compare(version_a: Sequence[Mapping[str, Any]], version_b: Sequence[Mapping[str, Any]], *, day_ranges: Sequence[tuple[int, int]] = ((1, 7), (8, 14))) -> dict[str, Any]:
    """Compare matched lifecycle days, never end-of-A against start-of-B."""
    def day(value: Mapping[str, Any]) -> int:
        return _as_int(value.get("lifecycle_day"), 0)
    rows = []
    for start, end in day_ranges:
        a = [r for r in version_a if start <= day(r) <= end]
        b = [r for r in version_b if start <= day(r) <= end]
        rows.append({"lifecycle_days": [start, end], "version_a": proportion_observation(a, lambda r: not bool(r.get("voted_up"))), "version_b": proportion_observation(b, lambda r: not bool(r.get("voted_up"))), "comparison_valid": bool(a and b), "support": {"a": len(a), "b": len(b)}})
    return {"comparison_basis": "lifecycle_matched", "rows": rows}


def longitudinal_series(reviews: Sequence[Mapping[str, Any]], start: date, end: date) -> dict[str, Any]:
    by_day: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for review in reviews:
        stamp = _ts(review)
        if stamp and start <= stamp.date() <= end:
            by_day[stamp.date().isoformat()].append(review)
    points = []
    cursor = start
    while cursor <= end:
        items = by_day.get(cursor.isoformat(), [])
        obs = proportion_observation(items, lambda r: not bool(r.get("voted_up")))
        points.append({"date": cursor.isoformat(), "reviews": len(items), "negative_rate": obs["rate"], "support": obs["support"]})
        cursor += timedelta(days=1)
    return {"start": start.isoformat(), "end": end.isoformat(), "granularity": "daily", "points": points, "descriptive_only": sum(p["reviews"] for p in points) < 30}


def public_opinion_events(daily: Sequence[Mapping[str, Any]], *, min_support: int = 20) -> list[dict[str, Any]]:
    """Detect candidate anomalies from two independent signals; cause stays unknown."""
    volumes = [float(item.get("reviews") or 0) for item in daily]
    rates = [item.get("negative_rate") for item in daily if item.get("negative_rate") is not None]
    if len(volumes) < 7 or len(rates) < 7:
        return []
    med_volume = statistics.median(volumes)
    mad = statistics.median(abs(x - med_volume) for x in volumes) or 1.0
    med_rate = statistics.median(rates)
    events = []
    for item in daily:
        volume = float(item.get("reviews") or 0)
        rate = item.get("negative_rate")
        volume_signal = volume >= med_volume + 3 * mad and volume >= min_support
        rate_signal = rate is not None and float(rate) >= med_rate + 0.15
        if volume_signal and rate_signal:
            events.append({"event_type": "public_opinion_event", "onset": item.get("date"), "peak": item.get("date"), "recovery": None, "signal_bundle": ["volume_burst", "negative_rate_shift"], "cause": "unknown", "status": "candidate"})
    return events


def robustness_matrix(windows: Mapping[str, tuple[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]]], predicate) -> dict[str, Any]:
    rows = []
    for label, (pre, post) in windows.items():
        effect = event_impact(pre, post, topic_predicate=predicate)
        rows.append({"check": label, "direction": "up" if (effect.get("delta") or 0) > 0.01 else "down" if (effect.get("delta") or 0) < -0.01 else "flat", "effect": effect.get("delta"), "support": min(len(pre), len(post)), "contaminated": False})
    directions = {row["direction"] for row in rows if row["support"]}
    return {"rows": rows, "signal_stability": "unstable" if len(directions) > 1 else "stable" if rows else "unavailable"}


def competing_mechanisms(topic: str, event: Mapping[str, Any], comparability: Mapping[str, Any]) -> list[dict[str, Any]]:
    names = ["direct_version_effect", "composition_shift", "concurrent_event", "operational_incident", "controversy_or_review_bombing", "seasonality", "platform_or_collection_change"]
    return [{"mechanism": name, "topic": topic, "supporting_evidence": [], "falsifying_evidence": [], "data_still_needed": ["verified source evidence", "matched window data"], "status": "unassessed"} for name in names]


def evidence_grade(*, sample_support: int, robustness: Mapping[str, Any], comparability: Mapping[str, Any], verified_evidence_count: int, label_reliability: str = "warn", confounder_risk: str = "medium") -> dict[str, Any]:
    components = {"sample_adequacy": "pass" if sample_support >= 100 else "warn" if sample_support >= 20 else "fail", "temporal_robustness": "pass" if robustness.get("signal_stability") == "stable" else "warn", "cohort_robustness": "pass" if comparability.get("overall") == "pass" else "warn", "evidence_verification": "pass" if verified_evidence_count > 0 else "fail", "label_reliability": label_reliability, "confounder_risk": confounder_risk}
    if "fail" in components.values() or confounder_risk == "high": grade = "D"
    elif components["sample_adequacy"] == "warn" or label_reliability == "warn" or components["cohort_robustness"] == "warn": grade = "C"
    elif components["temporal_robustness"] == "warn": grade = "B"
    else: grade = "A"
    return {"grade": grade, "label": {"A": "Strong observational evidence", "B": "Moderate observational evidence", "C": "Exploratory", "D": "Insufficient"}[grade], "components": components, "causal_claim": False}


def build_analysis_design(*, app_id: int, analysis_type: str, profile: Mapping[str, Any], event: Mapping[str, Any], window: Mapping[str, Any], sensitivity_windows: Sequence[Mapping[str, Any]], comparison_basis: str, population_rules: Mapping[str, Any], metrics: Sequence[str], concurrent_events: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    return {"design_id": uuid4().hex, "app_id": app_id, "analysis_type": analysis_type, "schema_version": SCHEMA_VERSION, "algorithm_version": ALGORITHM_VERSION, "game_profile": dict(profile), "anchor_event": resolve_event_anchor(event), "primary_window": dict(window), "sensitivity_windows": list(sensitivity_windows), "comparison_basis": comparison_basis, "population_rules": dict(population_rules), "metrics": list(metrics), "concurrent_events": list(concurrent_events), "confounder_risk": "high" if event.get("event_status") == "confounded" else "medium", "window_selection_reason": list(window.get("reason_codes", [])), "minimum_support_rules": {"per_side": 20, "verified_evidence_required": True}}
