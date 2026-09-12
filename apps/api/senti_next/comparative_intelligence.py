"""Version Review V2 comparative intelligence primitives.

This module is deliberately deterministic and provider-free.  It owns the
validity gate and the immutable A/B result shape; the existing label cache and
adaptive-analysis design remain the execution/provenance authorities.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import re
from typing import Any, Mapping, Sequence

MIN_SEMANTIC_REVIEWS = 50
SUPPORTED_WINDOWS = (3, 7, 14)


def _day(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return (value.astimezone(timezone.utc) if value.tzinfo else value).date()
    if isinstance(value, date):
        return value
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(int(value), tz=timezone.utc).date()
        return date.fromisoformat(str(value).replace("Z", "+00:00")[:10])
    except (TypeError, ValueError, OverflowError):
        return None


def lifecycle_window(event: Mapping[str, Any], window_days: int = 7) -> dict[str, Any]:
    """Return the documented half-open lifecycle interval [effective, effective+N)."""
    anchor = _day(event.get("effective_at") or event.get("event_date"))
    if not anchor:
        return {"event_id": event.get("event_id"), "window_days": window_days, "start": None, "end": None}
    return {"event_id": event.get("event_id"), "window_days": window_days,
            "start": anchor.isoformat(), "end": (anchor + timedelta(days=window_days)).isoformat()}


def _review_day(review: Mapping[str, Any]) -> date | None:
    return _day(review.get("timestamp_created") or review.get("created_at"))


def reviews_in_window(reviews: Sequence[Mapping[str, Any]], window: Mapping[str, Any]) -> list[dict[str, Any]]:
    start, end = _day(window.get("start")), _day(window.get("end"))
    if not start or not end:
        return []
    return [dict(review) for review in reviews if (day := _review_day(review)) and start <= day < end]


def evaluate_window_coverage(
    reviews: Sequence[Mapping[str, Any]],
    event: Mapping[str, Any],
    window_days: int = 7,
    *,
    crawl_complete_for_window: bool | None = None,
    coverage_source: str = "unknown",
    oldest_cached_review: Any = None,
    newest_cached_review: Any = None,
) -> dict[str, Any]:
    """Gate comparison on an explicit acquisition contract, never count alone."""
    window = lifecycle_window(event, window_days)
    scoped = reviews_in_window(reviews, window)
    if not window["start"]:
        status = "UNKNOWN"
    elif crawl_complete_for_window is False:
        status = "PARTIAL"
    elif crawl_complete_for_window is not True:
        status = "UNKNOWN"
    elif len(scoped) < MIN_SEMANTIC_REVIEWS:
        status = "INSUFFICIENT_REAL_VOLUME"
    else:
        status = "COMPLETE"
    days = [_review_day(item) for item in scoped]
    return {
        "event_id": event.get("event_id"), "event_effective_at": window["start"],
        "window_days": window_days, "window_start": window["start"], "window_end": window["end"],
        "raw_window_count": len(scoped), "coverage_status": status, "coverage_source": coverage_source,
        "oldest_cached_review": (min(days).isoformat() if days else _day(oldest_cached_review)),
        "newest_cached_review": (max(days).isoformat() if days else _day(newest_cached_review)),
        "crawl_complete_for_window": crawl_complete_for_window,
        "semantic_sample_count": min(len(scoped), 1000), "classification_coverage": None,
    }


def _payload(labels: Mapping[str, Mapping[str, Any]], review: Mapping[str, Any]) -> Mapping[str, Any]:
    key = str(review.get("recommendationid") or review.get("review_id") or "")
    raw = labels.get(key, {}) or {}
    payload = raw.get("payload", raw) if isinstance(raw, Mapping) else {}
    return payload if isinstance(payload, Mapping) else {}


def _values(payload: Mapping[str, Any], key: str) -> set[str]:
    values = payload.get(key) or []
    if isinstance(values, str): values = [values]
    return {str(value).strip() for value in values if str(value).strip()}


def _id(review: Mapping[str, Any]) -> str:
    return str(review.get("recommendationid") or review.get("review_id") or "")


def _rate(values: Sequence[Mapping[str, Any]], predicate) -> float | None:
    if not values: return None
    return round(sum(1 for item in values if predicate(item)) / len(values), 6)


def _topic_family(topic: str, issues: set[str], requests: set[str]) -> str:
    if topic in requests: return "request"
    if topic in issues: return "problem"
    return "positive"


def _state(a: float, b: float, support: int, threshold: float = 0.03) -> str:
    if support < MIN_SEMANTIC_REVIEWS: return "INSUFFICIENT"
    if a < 0.01 and b >= threshold: return "NEW"
    if a >= threshold and b < 0.01: return "RESOLVED_OR_REDUCED"
    if b - a >= threshold: return "INCREASED"
    if a - b >= threshold: return "DECREASED"
    if a >= threshold and b >= threshold: return "PERSISTENT"
    return "STABLE"


def _topic_comparisons(a_reviews: Sequence[Mapping[str, Any]], b_reviews: Sequence[Mapping[str, Any]], labels: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    topics: set[str] = set()
    families: dict[str, str] = {}
    for review in [*a_reviews, *b_reviews]:
        payload = _payload(labels, review)
        issues, requests = _values(payload, "issue_subcategories"), _values(payload, "request_subcategories")
        for topic in _values(payload, "subcategories") | issues | requests:
            if topic.startswith("other/"): continue
            topics.add(topic); families[topic] = _topic_family(topic, issues, requests)
    rows = []
    for topic in sorted(topics):
        a_support = sum(topic in (_values(_payload(labels, r), "subcategories") | _values(_payload(labels, r), "issue_subcategories") | _values(_payload(labels, r), "request_subcategories")) for r in a_reviews)
        b_support = sum(topic in (_values(_payload(labels, r), "subcategories") | _values(_payload(labels, r), "issue_subcategories") | _values(_payload(labels, r), "request_subcategories")) for r in b_reviews)
        a_rate = round(a_support / len(a_reviews), 6) if a_reviews else None
        b_rate = round(b_support / len(b_reviews), 6) if b_reviews else None
        delta = round((b_rate or 0) - (a_rate or 0), 6) if a_rate is not None and b_rate is not None else None
        rows.append({"topic_id": topic, "display_name": topic.split("/", 1)[-1], "family": families[topic], "a_support": a_support, "a_rate": a_rate, "b_support": b_support, "b_rate": b_rate, "delta_pp": round((delta or 0) * 100, 2) if delta is not None else None, "direction": "up" if (delta or 0) > 0 else "down" if (delta or 0) < 0 else "stable", "state": _state(a_rate or 0, b_rate or 0, min(len(a_reviews), len(b_reviews))), "robustness": "primary_window_only", "semantic_reliability": "observed_label_rate"})
    return sorted(rows, key=lambda row: abs(row.get("delta_pp") or 0), reverse=True)


def _dedupe_pair(topic: str, period: str, reviews: Sequence[Mapping[str, Any]], labels: Mapping[str, Mapping[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set(); result = []
    for review in reviews:
        review_id = _id(review); text = str(review.get("review") or "").strip()
        if not review_id or not text: continue
        key = (review_id, text)
        if key in seen: continue
        payload = _payload(labels, review)
        # Evidence must come from a review that actually carries this topic.
        # Falling back to arbitrary window reviews makes every topic display
        # the same snippets when a label payload has no quote for the topic.
        topics = (_values(payload, "subcategories")
                  | _values(payload, "issue_subcategories")
                  | _values(payload, "request_subcategories"))
        if topic not in topics:
            continue
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), Mapping) else {}
        snippets = evidence.get(topic) if isinstance(evidence, Mapping) else []
        snippet = str(snippets[0] if isinstance(snippets, list) and snippets else text[:240]).strip()
        if not snippet: continue
        seen.add(key)
        result.append({"evidence_id": sha256(f"{topic}|{period}|{review_id}|{snippet}".encode()).hexdigest()[:20], "topic_id": topic, "period": period, "review_id": review_id, "snippet": snippet})
        if len(result) >= limit: break
    return result


def build_paired_evidence(topics: Sequence[Mapping[str, Any]], a_reviews: Sequence[Mapping[str, Any]], b_reviews: Sequence[Mapping[str, Any]], labels: Mapping[str, Mapping[str, Any]], limit_topics: int = 8) -> list[dict[str, Any]]:
    result = []
    for topic in list(topics)[:limit_topics]:
        topic_id = str(topic["topic_id"])
        result.append({"topic_id": topic_id, "a": _dedupe_pair(topic_id, "A", a_reviews, labels), "b": _dedupe_pair(topic_id, "B", b_reviews, labels)})
    return result


_RESIDUAL_STOPWORDS = {"play", "played", "playing", "game", "games", "they", "them", "their", "we", "you", "keep", "keeps", "community", "weapon", "weapons", "good", "bad", "make", "made", "want", "really", "just", "like", "this", "that", "with", "from", "have", "been", "after", "before"}


def discover_residual_candidates(a_reviews: Sequence[Mapping[str, Any]], b_reviews: Sequence[Mapping[str, Any]], labels: Mapping[str, Mapping[str, Any]], minimum_support: int = 2) -> list[dict[str, Any]]:
    """Find candidate signals only in taxonomy-gap/general residual reviews."""
    counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"a": set(), "b": set(), "examples": []})
    for period, reviews in (("A", a_reviews), ("B", b_reviews)):
        for review in reviews:
            payload = _payload(labels, review)
            labels_set = _values(payload, "subcategories")
            if labels_set and not any(item.startswith("other/") for item in labels_set) and not payload.get("taxonomy_gap"):
                continue
            review_id, text = _id(review), str(review.get("review") or "").lower()
            tokens = set(re.findall(r"[a-z][a-z0-9_-]{4,}", text)) - _RESIDUAL_STOPWORDS
            for token in tokens:
                counts[token][period.lower()].add(review_id)
                if review_id and review_id not in counts[token]["examples"] and len(counts[token]["examples"]) < 3:
                    counts[token]["examples"].append(review_id)
    result = []
    for token, value in counts.items():
        total = len(value["a"] | value["b"])
        if total < minimum_support: continue
        result.append({"candidate_label": token, "candidate_name": token, "version_a_support": len(value["a"]), "version_b_support": len(value["b"]), "delta": len(value["b"]) - len(value["a"]), "sample_review_ids": value["examples"], "reason_not_in_taxonomy": "residual_general_or_taxonomy_gap", "confidence_status": "CANDIDATE", "review_status": "CANDIDATE", "discovery_method": "residual_semantic_v1"})
    return sorted(result, key=lambda item: abs(item["delta"]), reverse=True)[:20]


def build_comparative_result(a_event: Mapping[str, Any], b_event: Mapping[str, Any], a_reviews: Sequence[Mapping[str, Any]], b_reviews: Sequence[Mapping[str, Any]], labels: Mapping[str, Mapping[str, Any]], *, window_days: int = 7, coverage_a: Mapping[str, Any] | None = None, coverage_b: Mapping[str, Any] | None = None, semantic_limit: int = 1000) -> dict[str, Any]:
    gate_a, gate_b = dict(coverage_a or {}), dict(coverage_b or {})
    valid = gate_a.get("coverage_status") == "COMPLETE" and gate_b.get("coverage_status") == "COMPLETE"
    a_sample, b_sample = list(a_reviews)[:semantic_limit], list(b_reviews)[:semantic_limit]
    raw_a = {"reviews": len(a_reviews), "reviews_per_day": round(len(a_reviews) / window_days, 2), "recommendation_rate": _rate(a_reviews, lambda r: bool(r.get("voted_up")))}
    raw_b = {"reviews": len(b_reviews), "reviews_per_day": round(len(b_reviews) / window_days, 2), "recommendation_rate": _rate(b_reviews, lambda r: bool(r.get("voted_up")))}
    result = {"schema_version": "version-review-v2", "window_days": window_days, "event_a_id": a_event.get("event_id"), "event_b_id": b_event.get("event_id"), "a_coverage_status": gate_a.get("coverage_status", "UNKNOWN"), "b_coverage_status": gate_b.get("coverage_status", "UNKNOWN"), "coverage_gate": {"status": "PASS" if valid else "BLOCKED", "reason": None if valid else "Both lifecycle windows must be COMPLETE before comparison."}, "raw_metrics_a": raw_a, "raw_metrics_b": raw_b, "raw_metric_deltas": {"reviews_per_day": round(raw_b["reviews_per_day"] - raw_a["reviews_per_day"], 2), "recommendation_rate_pp": round(((raw_b["recommendation_rate"] or 0) - (raw_a["recommendation_rate"] or 0)) * 100, 2) if raw_a["recommendation_rate"] is not None and raw_b["recommendation_rate"] is not None else None}, "a_semantic_sample_count": len(a_sample), "b_semantic_sample_count": len(b_sample), "a_classified_count": 0, "b_classified_count": 0, "topic_comparisons": [], "request_comparisons": [], "positive_comparisons": [], "paired_evidence": [], "window_sensitivity": [], "emerging_topic_candidates": []}
    if not valid or min(len(a_sample), len(b_sample)) < MIN_SEMANTIC_REVIEWS:
        result["comparison_status"] = "INSUFFICIENT" if valid else "BLOCKED"
        return result
    topics = _topic_comparisons(a_sample, b_sample, labels)
    result["comparison_status"] = "READY"
    result["a_classified_count"] = sum(1 for r in a_sample if _payload(labels, r))
    result["b_classified_count"] = sum(1 for r in b_sample if _payload(labels, r))
    result["topic_comparisons"] = topics
    result["request_comparisons"] = [r for r in topics if r["family"] == "request"]
    result["positive_comparisons"] = [r for r in topics if r["family"] == "positive"]
    result["topic_comparisons"] = [r for r in topics if r["family"] == "problem"]
    result["paired_evidence"] = build_paired_evidence(topics, a_sample, b_sample, labels)
    result["emerging_topic_candidates"] = discover_residual_candidates(a_sample, b_sample, labels)
    return result


def window_sensitivity(a_event: Mapping[str, Any], b_event: Mapping[str, Any], reviews: Sequence[Mapping[str, Any]], labels: Mapping[str, Mapping[str, Any]], coverage_by_days: Mapping[int, tuple[Mapping[str, Any], Mapping[str, Any]]], semantic_limit: int = 1000) -> list[dict[str, Any]]:
    rows = []
    for days in SUPPORTED_WINDOWS:
        aw, bw = lifecycle_window(a_event, days), lifecycle_window(b_event, days)
        a, b = reviews_in_window(reviews, aw), reviews_in_window(reviews, bw)
        result = build_comparative_result(a_event, b_event, a, b, labels, window_days=days, coverage_a=coverage_by_days[days][0], coverage_b=coverage_by_days[days][1], semantic_limit=semantic_limit)
        rows.append({"window_days": days, "comparison_status": result["comparison_status"], "recommendation_rate_delta_pp": result["raw_metric_deltas"]["recommendation_rate_pp"], "reviews_per_day_delta": result["raw_metric_deltas"]["reviews_per_day"]})
    return rows
