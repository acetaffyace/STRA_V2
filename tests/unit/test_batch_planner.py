from senti_next.batch_planner import (
    BatchLane,
    BatchPlannerConfig,
    DynamicBatchPlanner,
    classify_provider_error,
    lane_for_length,
    validate_batch_results,
)
from senti_next.providers.errors import ProviderFailure


def test_lane_boundaries():
    config = BatchPlannerConfig()
    assert lane_for_length(80, config) is BatchLane.SHORT
    assert lane_for_length(81, config) is BatchLane.MEDIUM
    assert lane_for_length(300, config) is BatchLane.MEDIUM
    assert lane_for_length(301, config) is BatchLane.LONG
    assert lane_for_length(1200, config) is BatchLane.LONG
    assert lane_for_length(1201, config) is BatchLane.VERY_LONG


def test_planner_isolates_lanes_and_enforces_review_and_char_budgets():
    planner = DynamicBatchPlanner(BatchPlannerConfig(short_max_reviews=2, max_total_chars=10))
    items = [
        {"review_id": "s1", "review_text_for_model": "a"},
        {"review_id": "s2", "review_text_for_model": "bb"},
        {"review_id": "s3", "review_text_for_model": "ccc"},
        {"review_id": "m1", "review_text_for_model": "x" * 81},
    ]
    batches = planner.plan(items)
    assert [batch.lane for batch in batches] == [BatchLane.SHORT, BatchLane.SHORT, BatchLane.MEDIUM]
    assert all(batch.review_count <= 2 for batch in batches if batch.lane is BatchLane.SHORT)
    assert batches[0].total_processed_chars <= 10


def test_partial_validation_only_retries_bad_ids():
    result = validate_batch_results(
        ["a", "b", "c", "d"],
        [("a", {"ok": 1}), ("b", {"ok": 1}), ("c", None), ("x", {"ok": 1})],
    )
    assert set(result.valid_results) == {"a", "b"}
    assert result.invalid_ids == ("c",)
    assert result.missing_ids == ("d",)
    assert result.unexpected_ids == ("x",)
    assert set(result.retry_ids) == {"c", "d"}


def test_duplicate_return_ids_are_not_silently_accepted():
    result = validate_batch_results(["a", "b"], [("a", {"ok": 1}), ("a", {"ok": 2}), ("b", {"ok": 1})])
    assert result.duplicate_return_ids == ("a",)
    assert result.retry_ids == ("a",)


def test_provider_errors_are_not_content_split_signals():
    assert classify_provider_error(ProviderFailure("RATE_LIMIT", "busy")) == "RATE_LIMIT"
    assert classify_provider_error(ProviderFailure("PROVIDER_SERVER", "down")) == "PROVIDER_SERVER_ERROR"
    assert classify_provider_error(ProviderFailure("TIMEOUT", "slow")) == "TIMEOUT"
