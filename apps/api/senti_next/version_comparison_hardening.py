"""Runtime correctness guards for Version Comparison V3.

This module intentionally sits beside the stable deterministic core. It contains
validation/aggregation behavior that depends on persisted event and LLM-label
metadata, so the base comparison primitives stay easy to audit and reuse.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .version_comparison import COHORTS, cohort_windows, event_anchor

_MAJOR_CONFOUNDER_TYPES = {
    "launch", "major_patch", "major_update", "season", "expansion", "dlc",
    "content_update", "content_drop", "pricing", "outage", "controversy",
}


def event_is_usable(event: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Reject event anchors whose timestamp/date is not safe for cohort slicing."""
    status = str(event.get("event_status") or "").strip().lower()
    if status in {"conflicted", "insufficient", "unresolved"} and not event.get("effective_at"):
        return False, f"event_status={status}"
    start = event.get("effective_at_start")
    end = event.get("effective_at_end")
    if start and end and str(start) != str(end) and not event.get("effective_at"):
        return False, "ambiguous_effective_at_range"
    try:
        event_anchor(event)
    except (TypeError, ValueError):
        return False, "missing_event_anchor"
    return True, None


def cohort_overlap_report(
    event_a: Mapping[str, Any], event_b: Mapping[str, Any], window_days: int
) -> dict[str, Any]:
    """Return any time overlap among the four PRE/POST cohorts."""
    windows = cohort_windows(event_a, event_b, window_days)
    overlaps: list[dict[str, Any]] = []
    labels = list(COHORTS)
    for index, left in enumerate(labels):
        for right in labels[index + 1 :]:
            a, b = windows[left], windows[right]
            start = max(int(a["start_time"]), int(b["start_time"]))
            end = min(int(a["end_time_exclusive"]), int(b["end_time_exclusive"]))
            if start < end:
                overlaps.append({
                    "cohort_a": left,
                    "cohort_b": right,
                    "start_time": start,
                    "end_time_exclusive": end,
                    "overlap_seconds": end - start,
                })
    return {"status": "overlap" if overlaps else "disjoint", "overlaps": overlaps}


def normalize_semantic_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Expose requested and actually-realized stratum distributions separately."""
    result = dict(manifest)
    requested = dict(result.get("target_distribution") or {})
    quotas = {str(k): int(v) for k, v in (result.get("quotas") or {}).items()}
    quota_total = sum(quotas.values())
    realized = {
        key: round(value / quota_total, 8)
        for key, value in sorted(quotas.items())
        if quota_total > 0 and value > 0
    }
    result["requested_target_distribution"] = requested
    result["realized_target_distribution"] = realized
    result["target_distribution"] = realized
    return result


def _review_id(review: Mapping[str, Any]) -> str:
    return str(review.get("recommendationid") or review.get("review_id") or "")


def _valid_payload(
    labels: Mapping[str, Mapping[str, Any]], review: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    raw = labels.get(_review_id(review))
    if not isinstance(raw, Mapping):
        return None
    if raw.get("label_origin") != "llm" or raw.get("validated") is not True:
        return None
    payload = raw.get("payload")
    return payload if isinstance(payload, Mapping) and payload else None


def _values(payload: Mapping[str, Any], key: str) -> set[str]:
    values = payload.get(key) or payload.get(f"llm_{key}") or []
    if isinstance(values, str):
        values = [values]
    return {
        str(value).strip()
        for value in values
        if str(value).strip() and not str(value).startswith("other/")
    }


def _general_topics(payload: Mapping[str, Any]) -> set[str]:
    return (
        _values(payload, "subcategories")
        - _values(payload, "issue_subcategories")
        - _values(payload, "request_subcategories")
    )


def _pp(value: float | None) -> float | None:
    return round(value * 100, 2) if value is not None else None


def _aggregate_family(
    valid_samples: Mapping[str, Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]]],
    selector,
) -> list[dict[str, Any]]:
    topic_sets: dict[str, dict[str, set[str]]] = {cohort: {} for cohort in COHORTS}
    topics: set[str] = set()
    denominators = {cohort: len(valid_samples[cohort]) for cohort in COHORTS}
    for cohort in COHORTS:
        for review, payload in valid_samples[cohort]:
            rid = _review_id(review)
            for topic in selector(payload):
                topics.add(topic)
                topic_sets[cohort].setdefault(topic, set()).add(rid)

    rows: list[dict[str, Any]] = []
    for topic in sorted(topics):
        support = {cohort: len(topic_sets[cohort].get(topic, set())) for cohort in COHORTS}
        rates = {
            cohort: support[cohort] / denominators[cohort] if denominators[cohort] else None
            for cohort in COHORTS
        }
        da = (
            rates["A_POST"] - rates["A_PRE"]
            if rates["A_POST"] is not None and rates["A_PRE"] is not None else None
        )
        db = (
            rates["B_POST"] - rates["B_PRE"]
            if rates["B_POST"] is not None and rates["B_PRE"] is not None else None
        )
        did = db - da if da is not None and db is not None else None
        rows.append({
            "topic_id": topic,
            "display_name": topic.split("/", 1)[-1],
            "support": support,
            "rates": rates,
            "a_change_pp": _pp(da),
            "b_change_pp": _pp(db),
            "difference_in_differences_pp": _pp(did),
        })
    rows.sort(key=lambda row: abs(row.get("difference_in_differences_pp") or 0), reverse=True)
    return rows


def semantic_comparison(
    cohorts: Mapping[str, Sequence[Mapping[str, Any]]],
    labels: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Aggregate only validated LLM labels over the exact manifest IDs."""
    selected = manifest.get("selected_review_ids") or {}
    selected_sets = {cohort: set(selected.get(cohort) or []) for cohort in COHORTS}
    samples = {
        cohort: [row for row in cohorts.get(cohort, []) if _review_id(row) in selected_sets[cohort]]
        for cohort in COHORTS
    }
    valid_samples: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {
        cohort: [] for cohort in COHORTS
    }
    for cohort in COHORTS:
        for row in samples[cohort]:
            payload = _valid_payload(labels, row)
            if payload is not None:
                valid_samples[cohort].append((row, payload))

    sample_counts = {cohort: len(samples[cohort]) for cohort in COHORTS}
    classified_counts = {cohort: len(valid_samples[cohort]) for cohort in COHORTS}
    coverage = {
        cohort: classified_counts[cohort] / sample_counts[cohort] if sample_counts[cohort] else 0.0
        for cohort in COHORTS
    }
    if manifest.get("status") != "ready":
        status = "insufficient_common_support"
    elif not all(classified_counts.values()):
        status = "classification_failed"
    elif min(coverage.values()) < 0.95:
        status = "partial_classification"
    else:
        status = "ready"

    issues = _aggregate_family(valid_samples, lambda payload: _values(payload, "issue_subcategories"))
    requests = _aggregate_family(valid_samples, lambda payload: _values(payload, "request_subcategories"))
    general = _aggregate_family(valid_samples, _general_topics)

    # The UI labels this family as positive themes. Make that statement true:
    # only validated reviews that Steam marks recommended contribute, and the
    # denominator is the validated recommended sample in each cohort.
    positive_samples = {
        cohort: [
            pair for pair in valid_samples[cohort]
            if pair[0].get("voted_up") is True
        ]
        for cohort in COHORTS
    }
    positives = _aggregate_family(positive_samples, _general_topics)

    return {
        "status": status,
        "sample_counts": sample_counts,
        "classified_counts": classified_counts,
        "classification_coverage": coverage,
        "invalid_label_counts": {
            cohort: sample_counts[cohort] - classified_counts[cohort] for cohort in COHORTS
        },
        "topics": issues + requests + general,
        "problems": issues,
        "requests": requests,
        "general": general,
        "positives": positives,
        "rate_denominator": "validated_llm_labels_only",
        "positive_topic_denominator": "validated_llm_labels_on_recommended_reviews_only",
    }


def confounder_events(
    catalog: Sequence[Mapping[str, Any]],
    event_a: Mapping[str, Any],
    event_b: Mapping[str, Any],
    *,
    window_days: int,
) -> list[dict[str, Any]]:
    """Flag only catalog events falling inside one of the actual cohort windows."""
    selected_ids = {str(event_a.get("event_id")), str(event_b.get("event_id"))}
    windows = cohort_windows(event_a, event_b, window_days)
    ranges = [
        (int(item["start_time"]), int(item["end_time_exclusive"]))
        for item in windows.values()
    ]
    result: list[dict[str, Any]] = []
    for event in catalog:
        if str(event.get("event_id")) in selected_ids:
            continue
        try:
            stamp = int(event_anchor(event)["timestamp"].timestamp())
        except (TypeError, ValueError):
            continue
        if not any(start <= stamp < end for start, end in ranges):
            continue
        event_type = str(event.get("event_type") or "other").lower()
        result.append({
            "event_id": event.get("event_id"),
            "event_name": event.get("event_name") or event.get("title"),
            "event_type": event_type,
            "event_date": event.get("effective_at") or event.get("event_date"),
            "severity": "major" if event_type in _MAJOR_CONFOUNDER_TYPES else "minor",
        })
    return sorted(result, key=lambda item: str(item.get("event_date") or ""))


__all__ = [
    "event_is_usable",
    "cohort_overlap_report",
    "normalize_semantic_manifest",
    "semantic_comparison",
    "confounder_events",
]
