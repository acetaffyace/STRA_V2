"""Deterministic metrics for version-event player voice reviews.

This module intentionally does not call an LLM. It turns the existing stored
Steam reviews and labels into auditable pre/event/post metrics. LLM-derived
aspect sentiment can be added later without changing the run contract.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from hashlib import sha256
import re
from statistics import median
from typing import Any, Dict, Iterable, Mapping, Optional

from .evidence import build_evidence


PERIODS = ("pre", "event_day", "post")

_ACTIONABILITY = {
    "technical": 1.0,
    "gameplay": 0.9,
    "ui_ux_accessibility": 0.85,
    "developer_updates": 0.8,
    "content_design": 0.75,
    "monetization_value": 0.7,
    "online_community": 0.65,
    "presentation": 0.55,
    "other": 0.4,
}


def _coerce_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).date()
    raw = str(value).strip()
    if raw.isdigit():
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).date()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def assign_period(
    timestamp: Any,
    event_date: date,
    pre_window_days: int,
    post_window_days: int,
) -> Optional[str]:
    """Assign a review to pre/event_day/post, or None outside the window."""
    review_date = _coerce_date(timestamp)
    if review_date is None:
        return None
    delta = (review_date - event_date).days
    if -pre_window_days <= delta < 0:
        return "pre"
    if delta == 0:
        return "event_day"
    if 0 < delta <= post_window_days:
        return "post"
    return None


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "recommended", "positive"}:
            return True
        if normalized in {"false", "0", "no", "not recommended", "negative"}:
            return False
    return None


def _review_id(review: Mapping[str, Any]) -> str:
    return str(review.get("recommendationid") or review.get("review_id") or "")


def _review_summary(reviews: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    values = [_coerce_bool(item.get("voted_up")) for item in reviews]
    values = [value for value in values if value is not None]
    recommended = sum(1 for value in values if value)
    total = len(values)
    return {
        "reviews": total,
        "recommended": recommended,
        "not_recommended": total - recommended,
        "recommendation_rate": round(recommended / total, 6) if total else None,
    }


def _label_payload(labels: Mapping[str, Mapping[str, Any]], review: Mapping[str, Any]) -> Mapping[str, Any]:
    label = labels.get(_review_id(review), {}) or {}
    payload = label.get("payload", label)
    return payload if isinstance(payload, Mapping) else {}


def _values(payload: Mapping[str, Any], key: str) -> set[str]:
    values = payload.get(key) or payload.get(f"llm_{key}") or []
    if isinstance(values, str):
        values = [values]
    return {str(value).strip() for value in values if str(value).strip()}


def _aspects(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = payload.get("aspects") or payload.get("aspect_sentiments") or []
    return [item for item in values if isinstance(item, Mapping)] if isinstance(values, list) else []


def _author_value(review: Mapping[str, Any], key: str, default: Any = None) -> Any:
    author = review.get("author")
    if isinstance(author, Mapping) and key in author:
        return author.get(key)
    return review.get(key, default)


def _playtime_bucket(review: Mapping[str, Any]) -> str:
    try:
        hours = float(_author_value(review, "playtime_at_review", 0) or 0) / 60
    except (TypeError, ValueError):
        hours = 0
    if hours < 2:
        return "0-2h"
    if hours < 10:
        return "2-10h"
    if hours < 30:
        return "10-30h"
    return "30h+"


def _experience_bucket(review: Mapping[str, Any]) -> str:
    try:
        games = int(_author_value(review, "num_games_owned", 0) or 0)
        reviews = int(_author_value(review, "num_reviews", 0) or 0)
    except (TypeError, ValueError):
        games, reviews = 0, 0
    if games < 10 and reviews < 5:
        return "low"
    if games < 50 and reviews < 20:
        return "medium"
    return "high"


def _purchase_bucket(review: Mapping[str, Any]) -> str:
    return "unknown"


def _segment_summary(reviews: Iterable[Mapping[str, Any]], key_fn) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for review in reviews:
        buckets[key_fn(review)].append(review)
    return {
        bucket: {**_review_summary(items), "low_sample": len(items) < 20}
        for bucket, items in sorted(buckets.items())
    }


_EMERGING_STOPWORDS = {
    "about", "after", "again", "also", "been", "but", "cant", "could", "game", "good",
    "have", "into", "just", "like", "more", "only", "really", "this", "very", "what",
    "when", "with", "would", "you", "your", "the", "and", "for", "that", "was", "are",
}


def _discover_emerging_topics(
    period_reviews: Mapping[str, list[Mapping[str, Any]]],
    labels: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Produce reviewable lexical candidates without silently changing taxonomy.

    This is intentionally a deterministic V1 candidate queue. Embedding/HDBSCAN
    clustering can replace the candidate generator later while preserving the
    queue contract and human-review gate.
    """
    candidates: dict[str, dict[str, Any]] = {}
    for period, reviews in period_reviews.items():
        for review in reviews:
            if _coerce_bool(review.get("voted_up")) is not False:
                continue
            payload = _label_payload(labels, review)
            subcategories = _values(payload, "subcategories")
            if not any(item.startswith("other/") for item in subcategories):
                continue
            text = str(review.get("review") or "")
            tokens = [token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{3,}", text.lower()) if token not in _EMERGING_STOPWORDS]
            counts = Counter(tokens)
            review_id = _review_id(review)
            review_date = _coerce_date(review.get("timestamp_created"))
            for token, count in counts.most_common(5):
                if count < 1:
                    continue
                candidate = candidates.setdefault(token, {
                    "candidate_name": token,
                    "example_reviews": [],
                    "mention_count": 0,
                    "period_counts": defaultdict(int),
                    "first_seen": review_date.isoformat() if review_date else None,
                    "suggested_parent_topic": "other",
                    "review_status": "pending_review",
                    "discovery_method": "lexical_v1",
                })
                candidate["mention_count"] += 1
                candidate["period_counts"][period] += 1
                if review_date and (not candidate["first_seen"] or review_date.isoformat() < candidate["first_seen"]):
                    candidate["first_seen"] = review_date.isoformat()
                if review_id and review_id not in candidate["example_reviews"] and len(candidate["example_reviews"]) < 3:
                    candidate["example_reviews"].append(review_id)
    results = []
    for candidate in candidates.values():
        pre_count = candidate["period_counts"].get("pre", 0)
        post_count = candidate["period_counts"].get("post", 0)
        candidate["growth_rate"] = round((post_count - pre_count) / pre_count, 6) if pre_count else (1.0 if post_count else 0.0)
        candidate.pop("period_counts", None)
        results.append(candidate)
    return sorted(results, key=lambda item: (item["mention_count"], item["growth_rate"]), reverse=True)[:20]


def _actionability(subcategory: str) -> float:
    return _ACTIONABILITY.get(subcategory.split("/", 1)[0], 0.5)


def _confidence(mentions: int, min_sample_size: int) -> tuple[str, float]:
    if mentions < min_sample_size:
        return "low", 0.5
    if mentions < 50:
        return "medium", 0.75
    return "high", min(1.0, round(mentions / 200, 6))


def _evidence_values(payload: Mapping[str, Any], subcategory: str) -> list[str]:
    evidence = payload.get("evidence") or payload.get("llm_subcategory_evidence") or {}
    if isinstance(evidence, Mapping):
        values = evidence.get(subcategory) or []
    else:
        values = evidence
    if isinstance(values, str):
        values = [values]
    return [str(value).strip() for value in values if str(value).strip()]


def _build_priority_and_evidence(
    category_metrics: list[dict[str, Any]],
    period_reviews: Mapping[str, list[Mapping[str, Any]]],
    labels: Mapping[str, Mapping[str, Any]],
    min_sample_size: int,
    *,
    run_id: str | None = None,
    app_id: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for period, reviews in period_reviews.items():
        for review in reviews:
            review_id = _review_id(review)
            payload = _label_payload(labels, review)
            voted_up = _coerce_bool(review.get("voted_up"))
            for subcategory in _values(payload, "subcategories") | _values(payload, "issue_subcategories") | _values(payload, "request_subcategories"):
                for snippet in _evidence_values(payload, subcategory):
                    evidence_id = sha256(f"{review_id}|{subcategory}|{snippet}".encode("utf-8")).hexdigest()[:16]
                    verified = build_evidence(
                        review.get("review"), snippet,
                        review_id=review_id, app_id=app_id, run_id=run_id,
                        subcategory=subcategory, period=period,
                        voted_up=voted_up, timestamp_created=review.get("timestamp_created"),
                        source="llm_label_evidence",
                    )
                    if verified["verification_status"] != "verified":
                        continue
                    evidence_by_category[subcategory].append({
                        "evidence_id": evidence_id,
                        "snippet": verified["quote"],
                        **verified,
                    })
            for aspect in _aspects(payload):
                subcategory = str(aspect.get("aspect") or aspect.get("subcategory") or "").strip()
                snippet = str(aspect.get("evidence_span") or "").strip()
                if not subcategory or not snippet:
                    continue
                evidence_id = sha256(f"{review_id}|{subcategory}|{snippet}".encode("utf-8")).hexdigest()[:16]
                verified = build_evidence(
                    review.get("review"), snippet,
                    review_id=review_id, app_id=app_id, run_id=run_id,
                    subcategory=subcategory, period=period,
                    voted_up=voted_up, timestamp_created=review.get("timestamp_created"),
                    source="aspect_sentiment", sentiment=aspect.get("sentiment"),
                    confidence=aspect.get("confidence"),
                )
                if verified["verification_status"] != "verified":
                    continue
                evidence_by_category[subcategory].append({
                    "evidence_id": evidence_id,
                    "snippet": verified["quote"],
                    **verified,
                })

    evidence_cards: list[dict[str, Any]] = []
    issue_cards: list[dict[str, Any]] = []
    for category in category_metrics:
        mentions = int(category["mentions"])
        confidence, sample_multiplier = _confidence(mentions, min_sample_size)
        label_confidence = category.get("classification_confidence")
        multiplier = round(sample_multiplier * (label_confidence if label_confidence is not None else 1.0), 6)
        reach = min(1.0, max(category["pre_mention_rate"], category["post_mention_rate"]) / 0.25)
        severity = category["post_negative_rate"] if category["sentiment_available"] else category["post_issue_rate"]
        delta_severity = category["delta_negative_rate"] if category["sentiment_available"] else category["delta_issue_rate"]
        deterioration = min(1.0, max(0.0, category["delta_mention_rate"]) / 0.10 * 0.5 + max(0.0, delta_severity) / 0.20 * 0.5)
        actionability = _actionability(category["subcategory"])
        score = round(100 * (0.30 * reach + 0.30 * severity + 0.20 * deterioration + 0.20 * actionability) * multiplier, 1)
        category.update({
            "reach": round(reach, 6),
            "severity": round(severity, 6),
            "deterioration": round(deterioration, 6),
            "actionability": actionability,
            "confidence": confidence,
            "confidence_multiplier": multiplier,
            "priority_score": score,
            "priority_score_is_proxy": True,
            "priority_note": "Uses aspect negative rate when available; otherwise issue labels are the severity proxy.",
        })
        cards = evidence_by_category.get(category["subcategory"], [])
        cards = sorted(cards, key=lambda item: (item["voted_up"] is True, item["timestamp_created"] or 0), reverse=True)[:5]
        evidence_cards.extend(cards)
        is_actionable_issue = bool(category["issue_count"] or category["request_count"] or category["post_negative_rate"] > 0)
        if not is_actionable_issue:
            continue
        issue_cards.append({
            "issue_id": sha256(category["subcategory"].encode("utf-8")).hexdigest()[:16],
            "subcategory": category["subcategory"],
            "priority_score": score,
            "score_components": {"reach": category["reach"], "severity": category["severity"], "deterioration": category["deterioration"], "actionability": actionability},
            "confidence": confidence,
            "evidence_ids": [item["evidence_id"] for item in cards],
            "issue_count": category["issue_count"],
            "request_count": category["request_count"],
            "post_negative_rate": category["post_negative_rate"],
            "limitation": "Observational proxy; validate with aspect sentiment and product metrics.",
            "action_class": "BUILD" if category["request_count"] > category["issue_count"] and category["request_count"] > 0 else ("FIX" if category["issue_count"] > 0 and category["severity"] >= 0.5 else "IMPROVE"),
            "hypothesis": "玩家在该主题上的体验或需求可能影响推荐行为；这是待验证机制，不是因果结论。",
            "alternative_explanations": ["样本自选择", "窗口内版本/活动构成变化", "分类标签误差"],
            "validation_plan": ["复现证据中的具体场景", "对比后续窗口同主题率与推荐率", "结合产品/客服指标"],
        })
    issue_cards.sort(key=lambda item: item["priority_score"], reverse=True)
    return issue_cards, evidence_cards


def _recommendation_for_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    subcategory = str(issue.get("subcategory") or "")
    main = subcategory.split("/", 1)[0]
    if main in {"technical", "gameplay", "ui_ux_accessibility", "onboarding"}:
        action_type = "product"
        action = "Reproduce the issue using the evidence spans, identify the affected platform or flow, and add a fix candidate to the next triage review."
        validation = ["issue negative rate", "crash/performance telemetry", "support or bug-ticket volume"]
    elif main in {"developer_updates", "online_community"}:
        action_type = "community"
        action = "Publish a scoped status update with the known impact, workaround, owner, and next checkpoint; monitor follow-up feedback."
        validation = ["repeat mention rate", "follow-up sentiment", "community/support volume"]
    elif main in {"content_design", "presentation"}:
        action_type = "content"
        action = "Review the affected content or presentation slice and test a focused improvement with representative players before broad rollout."
        validation = ["aspect negative rate", "content engagement", "repeat positive mentions"]
    else:
        action_type = "product_and_community"
        action = "Validate the issue with the responsible team, then choose a product fix or an evidence-backed communication response."
        validation = ["aspect negative rate", "mention rate", "support volume"]
    return {
        "recommendation_id": sha256(f"recommendation|{subcategory}".encode("utf-8")).hexdigest()[:16],
        "issue_id": issue["issue_id"],
        "subcategory": subcategory,
        "action_type": action_type,
        "hypothesis": "The observed post-event change reflects a player-experienced issue in this topic; causality remains unconfirmed.",
        "action": action,
        "validation_metrics": validation,
        "evidence_ids": issue.get("evidence_ids", []),
        "priority_score": issue.get("priority_score", 0),
        "confidence": issue.get("confidence"),
        "limitation": issue.get("limitation"),
    }


def calculate_version_metrics(
    reviews: Iterable[Mapping[str, Any]],
    labels: Optional[Mapping[str, Mapping[str, Any]]],
    event_date: date,
    pre_window_days: int = 28,
    post_window_days: int = 28,
    min_sample_size: int = 20,
    run_id: str | None = None,
    app_id: int | None = None,
) -> Dict[str, Any]:
    """Build auditable event-window metrics from stored reviews and labels.

    ``issue_rate`` is deliberately named separately from sentiment. Legacy
    labels without aspect entries use it as an explicit proxy; newer labels
    contribute aspect-level negative/positive rates.
    """
    labels = labels or {}
    period_reviews: dict[str, list[Mapping[str, Any]]] = {period: [] for period in PERIODS}
    categorized: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {
            "mentions": 0,
            "issues": 0,
            "requests": 0,
            "sentiment_mentions": 0,
            "negative_sentiments": 0,
            "neutral_sentiments": 0,
            "positive_sentiments": 0,
            "sentiment_confidence_sum": 0.0,
            "sentiment_confidence_count": 0,
        })
    )
    excluded = 0

    for review in reviews:
        period = assign_period(
            review.get("timestamp_created"),
            event_date,
            pre_window_days,
            post_window_days,
        )
        if period is None:
            excluded += 1
            continue
        period_reviews[period].append(review)
        payload = _label_payload(labels, review)
        subcategories = _values(payload, "subcategories")
        issues = _values(payload, "issue_subcategories")
        requests = _values(payload, "request_subcategories")
        for subcategory in subcategories | issues | requests:
            stats = categorized["all"][subcategory]
            stats["mentions"] += 1
            if subcategory in issues:
                stats["issues"] += 1
            if subcategory in requests:
                stats["requests"] += 1
            period_stats = categorized[period][subcategory]
            period_stats["mentions"] += 1
            if subcategory in issues:
                period_stats["issues"] += 1
            if subcategory in requests:
                period_stats["requests"] += 1
        for aspect in _aspects(payload):
            subcategory = str(aspect.get("aspect") or aspect.get("subcategory") or "").strip()
            try:
                sentiment = int(aspect.get("sentiment"))
            except (TypeError, ValueError):
                continue
            if not subcategory or sentiment < -2 or sentiment > 2:
                continue
            for scope in (categorized["all"], categorized[period]):
                scope_stats = scope[subcategory]
                if subcategory not in subcategories:
                    scope_stats["mentions"] += 1
                scope_stats["sentiment_mentions"] += 1
                if sentiment < 0:
                    scope_stats["negative_sentiments"] += 1
                elif sentiment > 0:
                    scope_stats["positive_sentiments"] += 1
                else:
                    scope_stats["neutral_sentiments"] += 1
                try:
                    confidence = float(aspect.get("confidence"))
                except (TypeError, ValueError):
                    confidence = 0.0
                scope_stats["sentiment_confidence_sum"] += max(0.0, min(1.0, confidence))
                scope_stats["sentiment_confidence_count"] += 1

    periods = {}
    for period in PERIODS:
        summary = _review_summary(period_reviews[period])
        summary["low_sample"] = summary["reviews"] < min_sample_size
        summary["segments"] = {
            "playtime_at_review": _segment_summary(period_reviews[period], _playtime_bucket),
            "reviewer_experience": _segment_summary(period_reviews[period], _experience_bucket),
            "purchase_type": _segment_summary(period_reviews[period], _purchase_bucket),
            "platform": _segment_summary(period_reviews[period], lambda item: "unknown"),
            "language": _segment_summary(period_reviews[period], lambda item: str(item.get("language") or "unknown")),
        }
        periods[period] = summary

    def rate(stats: Mapping[str, int], key: str, denominator: int) -> float:
        return round(stats.get(key, 0) / denominator, 6) if denominator else 0.0

    category_metrics = []
    for subcategory in sorted(categorized["all"]):
        all_stats = categorized["all"][subcategory]
        pre_stats = categorized["pre"].get(subcategory, {})
        post_stats = categorized["post"].get(subcategory, {})
        pre_total = periods["pre"]["reviews"]
        post_total = periods["post"]["reviews"]
        pre_mention_rate = rate(pre_stats, "mentions", pre_total)
        post_mention_rate = rate(post_stats, "mentions", post_total)
        pre_issue_rate = rate(pre_stats, "issues", pre_stats.get("mentions", 0))
        post_issue_rate = rate(post_stats, "issues", post_stats.get("mentions", 0))
        pre_sentiment_mentions = pre_stats.get("sentiment_mentions", 0)
        post_sentiment_mentions = post_stats.get("sentiment_mentions", 0)
        pre_negative_rate = rate(pre_stats, "negative_sentiments", pre_sentiment_mentions)
        post_negative_rate = rate(post_stats, "negative_sentiments", post_sentiment_mentions)
        pre_positive_rate = rate(pre_stats, "positive_sentiments", pre_sentiment_mentions)
        post_positive_rate = rate(post_stats, "positive_sentiments", post_sentiment_mentions)
        sentiment_available = bool(pre_sentiment_mentions or post_sentiment_mentions)
        confidence_values = [
            pre_stats.get("sentiment_confidence_sum", 0.0),
            post_stats.get("sentiment_confidence_sum", 0.0),
        ]
        confidence_count = pre_stats.get("sentiment_confidence_count", 0) + post_stats.get("sentiment_confidence_count", 0)
        category_metrics.append({
            "subcategory": subcategory,
            "mentions": all_stats["mentions"],
            "issue_count": all_stats["issues"],
            "request_count": all_stats["requests"],
            "pre_mention_rate": pre_mention_rate,
            "post_mention_rate": post_mention_rate,
            "delta_mention_rate": round(post_mention_rate - pre_mention_rate, 6),
            "pre_issue_rate": pre_issue_rate,
            "post_issue_rate": post_issue_rate,
            "delta_issue_rate": round(post_issue_rate - pre_issue_rate, 6),
            "sentiment_mentions": pre_sentiment_mentions + post_sentiment_mentions,
            "classification_confidence": round(sum(confidence_values) / confidence_count, 6) if confidence_count else None,
            "pre_negative_rate": pre_negative_rate,
            "post_negative_rate": post_negative_rate,
            "delta_negative_rate": round(post_negative_rate - pre_negative_rate, 6),
            "pre_positive_rate": pre_positive_rate,
            "post_positive_rate": post_positive_rate,
            "delta_positive_rate": round(post_positive_rate - pre_positive_rate, 6),
            "negative_burden": round(post_mention_rate * post_negative_rate, 6),
            "low_sample": all_stats["mentions"] < min_sample_size,
            "sentiment_available": sentiment_available,
            "sentiment_note": "Aspect-level sentiment from classification labels." if sentiment_available else "Uses issue labels as a proxy until aspect-level sentiment is available.",
        })

    issue_cards, evidence_cards = _build_priority_and_evidence(
        category_metrics, period_reviews, labels, min_sample_size,
        run_id=run_id, app_id=app_id,
    )
    recommendations = [_recommendation_for_issue(issue) for issue in issue_cards[:10]]
    emerging_topics = _discover_emerging_topics(period_reviews, labels)
    daily_volume: dict[str, int] = defaultdict(int)
    for period_reviews_list in period_reviews.values():
        for review in period_reviews_list:
            review_date = _coerce_date(review.get("timestamp_created"))
            if review_date:
                daily_volume[review_date.isoformat()] += 1
    pre_daily = [count for day, count in daily_volume.items() if day < event_date.isoformat()]
    post_daily = [count for day, count in daily_volume.items() if day > event_date.isoformat()]
    baseline = median(pre_daily) if pre_daily else None
    volume_index = round((sum(post_daily) / len(post_daily)) / baseline, 6) if baseline else None
    has_aspect_sentiment = any(item["sentiment_available"] for item in category_metrics)
    warnings = ["Steam reviews are observational and do not establish causality."]
    if not has_aspect_sentiment:
        warnings.insert(0, "Aspect-level sentiment is not available; issue_rate is used as a proxy.")
    else:
        warnings.insert(0, "Aspect sentiment is model-derived and should be reviewed against evidence spans.")
    return {
        "event_date": event_date.isoformat(),
        "pre_window_days": pre_window_days,
        "post_window_days": post_window_days,
        "periods": periods,
        "categories": category_metrics,
        "priority_score_version": "ips-v1-proxy",
        "issue_cards": issue_cards,
        "evidence_cards": evidence_cards,
        "recommendations": recommendations,
        "emerging_topic_candidates": emerging_topics,
        "daily_review_volume": dict(sorted(daily_volume.items())),
        "post_vs_pre_volume_index": volume_index,
        "reviews_in_window": sum(item["reviews"] for item in periods.values()),
        "reviews_excluded": excluded,
        "min_sample_size": min_sample_size,
        "warnings": warnings,
        "decision_memo": {
            "interpretation": "Version Review reports pre/post observations around an event; it does not establish that the event caused the change.",
            "observed_changes": [
                {
                    "subcategory": item["subcategory"],
                    "observed_change": item["delta_mention_rate"],
                    "possible_mechanism": item.get("hypothesis"),
                    "supporting_evidence_ids": [e["evidence_id"] for e in evidence_cards if e.get("subcategory") == item["subcategory"]],
                    "alternative_explanations": item.get("alternative_explanations", []),
                    "additional_data_needed": item.get("validation_plan", []),
                    "recommended_follow_up": item.get("action_class"),
                }
                for item in category_metrics
                if item.get("delta_mention_rate") or item.get("delta_issue_rate")
            ],
            "comparison_discipline": {
                "pre_window_days": pre_window_days,
                "post_window_days": post_window_days,
                "event_date": event_date.isoformat(),
                "sample_counts": {key: value.get("reviews", 0) for key, value in periods.items()},
                "coverage_differences_visible": True,
            },
        },
    }
