from datetime import datetime, timezone

from senti_next.version_review_autopilot import (
    build_review_acquisition_plan,
    choose_previous_comparable,
    deterministic_stratified_sample,
    resolve_event,
)


def event(event_id, day, name, event_type="major_patch", verified=False):
    return {"event_id": event_id, "event_date": day, "event_name": name, "event_type": event_type, "manual_verified": verified, "source": "steam_news:1", "source_url": "https://steamcommunity.com/news/1"}


def test_unverified_event_is_startable_and_resolved():
    resolved = resolve_event(event("b", "2026-08-12", "Major Update", verified=False))
    assert resolved["can_start"] is True
    assert resolved["resolution_status"] == "SOURCE_CONFIRMED"


def test_previous_comparable_skips_hotfix():
    selected = event("c", "2026-08-12", "Major B")
    events = [selected, event("h", "2026-08-01", "Hotfix", "hotfix"), event("a", "2026-03-05", "Major A")]
    assert choose_previous_comparable(events, selected)["event_id"] == "a"


def test_plan_separates_raw_windows_and_semantic_budget():
    reviews = [{"recommendationid": str(i), "timestamp_created": int(datetime(2026, 8, 12, tzinfo=timezone.utc).timestamp()) + i} for i in range(1200)]
    plan = build_review_acquisition_plan(1, event("b", "2026-08-12", "B"), event("a", "2026-03-05", "A"), reviews, 1000)
    assert len(plan["required_intervals"]) == 2
    assert plan["semantic_sample_plan"]["per_window_limit"] == 1000
    assert plan["semantic_sample_plan"]["windows"][0]["raw_window_count"] == 1200
    assert plan["semantic_sample_plan"]["windows"][0]["semantic_sample_count"] == 1000


def test_sampling_is_deterministic_and_bounded():
    reviews = [{"recommendationid": str(i), "timestamp_created": 1, "voted_up": i % 2, "language": "english"} for i in range(100)]
    a = deterministic_stratified_sample(reviews, 20, "seed")
    b = deterministic_stratified_sample(reviews, 20, "seed")
    assert [x["recommendationid"] for x in a] == [x["recommendationid"] for x in b]
    assert len(a) == 20


def test_selected_lifecycle_window_is_shared_and_under_limit_uses_all_reviews():
    reviews = [{"recommendationid": str(i), "timestamp_created": int(datetime(2026, 8, 12, tzinfo=timezone.utc).timestamp()) + i} for i in range(17)]
    plan = build_review_acquisition_plan(553850, event("b", "2026-08-12", "B"), event("a", "2026-05-28", "A"), reviews, 1000, window_days=3)
    assert plan["window_days"] == 3
    assert {item["end"] for item in plan["required_intervals"]} == {"2026-05-31", "2026-08-15"}
    assert all(item["semantic_sample_count"] == item["raw_window_count"] for item in plan["semantic_sample_plan"]["windows"])
    assert all(item["all_reviews_when_under_limit"] for item in plan["semantic_sample_plan"]["windows"])
