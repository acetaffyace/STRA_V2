from datetime import datetime, timezone

from senti_next.comparative_intelligence import (
    build_comparative_result,
    evaluate_window_coverage,
    lifecycle_window,
    reviews_in_window,
    discover_residual_candidates,
)


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())


def _event(event_id: str, day: str) -> dict:
    return {"event_id": event_id, "effective_at": day}


def _reviews(prefix: str, day: str, count: int, voted_up: bool = True) -> list[dict]:
    return [{"recommendationid": f"{prefix}-{i}", "timestamp_created": _ts(day), "voted_up": voted_up, "review": f"review {prefix} {i}"} for i in range(count)]


def test_lifecycle_window_is_half_open_and_uses_effective_date():
    event = {"event_id": "a", "event_date": "2026-05-01", "effective_at": "2026-05-02T23:00:00+00:00"}
    window = lifecycle_window(event, 3)
    assert window["start"] == "2026-05-02"
    assert window["end"] == "2026-05-05"
    assert len(reviews_in_window(_reviews("a", "2026-05-04", 1), window)) == 1
    assert not reviews_in_window(_reviews("a", "2026-05-05", 1), window)


def test_incomplete_window_blocks_comparison_even_with_large_count():
    event = _event("a", "2026-05-28")
    gate = evaluate_window_coverage(_reviews("a", "2026-05-28", 100), event, 7, crawl_complete_for_window=False, coverage_source="steam_recent_partial")
    assert gate["coverage_status"] == "PARTIAL"
    result = build_comparative_result(event, _event("b", "2026-08-12"), _reviews("a", "2026-05-28", 100), _reviews("b", "2026-08-12", 100), {}, coverage_a=gate, coverage_b={"coverage_status": "COMPLETE"})
    assert result["comparison_status"] == "BLOCKED"
    assert result["topic_comparisons"] == []


def test_complete_but_seventeen_reviews_is_truthfully_insufficient():
    a_event, b_event = _event("a", "2026-05-28"), _event("b", "2026-08-12")
    a, b = _reviews("a", "2026-05-28", 100), _reviews("b", "2026-08-12", 17)
    a_gate = evaluate_window_coverage(a, a_event, 7, crawl_complete_for_window=True, coverage_source="steam_recent_complete")
    b_gate = evaluate_window_coverage(b, b_event, 7, crawl_complete_for_window=True, coverage_source="steam_recent_complete")
    assert b_gate["coverage_status"] == "INSUFFICIENT_REAL_VOLUME"
    result = build_comparative_result(a_event, b_event, a, b, {}, coverage_a=a_gate, coverage_b=b_gate)
    assert result["comparison_status"] == "BLOCKED"


def test_raw_metrics_are_first_class():
    a_event, b_event = _event("a", "2026-05-28"), _event("b", "2026-08-12")
    a, b = _reviews("a", "2026-05-28", 100, True), _reviews("b", "2026-08-12", 100, False)
    ready = {"coverage_status": "COMPLETE"}
    result = build_comparative_result(a_event, b_event, a, b, {}, coverage_a=ready, coverage_b=ready)
    assert result["comparison_status"] == "READY"
    assert result["raw_metrics_a"]["reviews_per_day"] == 14.29
    assert result["raw_metric_deltas"]["recommendation_rate_pp"] == -100.0


def test_paired_evidence_only_uses_reviews_with_the_topic():
    a_event, b_event = _event("a", "2026-05-28"), _event("b", "2026-08-12")
    a = _reviews("a", "2026-05-28", 60)
    b = _reviews("b", "2026-08-12", 60)
    labels = {
        "a-0": {"payload": {"subcategories": ["technical/networking"], "evidence": {"technical/networking": ["network A"]}}},
        "b-0": {"payload": {"subcategories": ["technical/networking"], "evidence": {"technical/networking": ["network B"]}}},
    }
    ready = {"coverage_status": "COMPLETE"}
    result = build_comparative_result(a_event, b_event, a, b, labels, coverage_a=ready, coverage_b=ready)
    pair = next(item for item in result["paired_evidence"] if item["topic_id"] == "technical/networking")
    assert [item["snippet"] for item in pair["a"]] == ["network A"]
    assert [item["snippet"] for item in pair["b"]] == ["network B"]


def test_emerging_candidates_only_use_residual_reviews_and_suppress_noise():
    reviews = [
        {"recommendationid": "1", "review": "The stutterstorm effect is unbearable", "voted_up": False},
        {"recommendationid": "2", "review": "Stutterstorm appears again", "voted_up": False},
        {"recommendationid": "3", "review": "play weapons community", "voted_up": False},
    ]
    labels = {str(i): {"payload": {"subcategories": ["other/general"]}} for i in (1, 2, 3)}
    candidates = discover_residual_candidates(reviews, [], labels)
    assert candidates[0]["candidate_label"] == "stutterstorm"
    assert all(item["candidate_label"] not in {"play", "weapons", "community"} for item in candidates)
    assert candidates[0]["review_status"] == "CANDIDATE"
