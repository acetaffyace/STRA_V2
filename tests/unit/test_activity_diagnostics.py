"""Regression tests for the descriptive Stage 2E activity diagnostics."""

from __future__ import annotations

import inspect
import json
import random

from apps.api.senti_next.activity_diagnostics import (
    analyze_review_activity,
    normalize_review_text,
)


DAY = 1_704_067_200  # 2024-01-01T00:00:00Z


def row(review_id: str, text: str, day: int = 0, *, voted_up: bool | None = True, author: str | None = None, hour: int = 0) -> dict:
    return {
        "recommendationid": review_id,
        "review": text,
        "timestamp_created": DAY + day * 86_400 + hour * 3_600,
        "voted_up": voted_up,
        "language": "english",
        "author": {"steamid": author} if author else {},
    }


def report(rows: list[dict], **kwargs):
    return analyze_review_activity(rows, **kwargs)


def test_identical_text_different_ids_remain_population_events():
    result = report([row("1", "same long expression for the population", author="a"), row("2", "same long expression for the population", author="b")])
    assert result["population"]["raw_review_count"] == 2
    assert result["population"]["unique_review_id_count"] == 2


def test_exact_duplicates_form_one_exact_cluster():
    result = report([row("1", "same long expression for the population"), row("2", "same long expression for the population")])
    assert len(result["clusters"]["exact"]) == 1
    assert result["clusters"]["exact"][0]["cluster_type"] == "exact"
    assert result["clusters"]["exact"][0]["review_count"] == 2


def test_short_repeated_good_is_not_strong_near_copy_signal():
    result = report([row("1", "good"), row("2", "GOOD"), row("3", " good ")])
    repetition = result["text_repetition"]
    assert repetition["exact_duplicate_review_count"] == 3
    assert repetition["short_text_exact_duplicate_review_count"] == 3
    assert repetition["near_copy_additional_review_count"] == 0
    assert repetition["coordinated_expression_review_count"] == 0


def test_obvious_templated_near_copies_are_clustered():
    rows = [
        row("1", "the new update makes the game much better and more enjoyable", author="a"),
        row("2", "the new update makes the game much better and more enjoyable!", author="b"),
        row("3", "the new update makes this game much better and more enjoyable", author="c"),
    ]
    result = report(rows)
    assert result["text_repetition"]["near_copy_additional_review_count"] == 3
    assert len(result["clusters"]["near_copy"]) == 1


def test_clearly_different_texts_are_not_clustered():
    result = report([
        row("1", "the controller support is excellent and responsive"),
        row("2", "the soundtrack is beautiful but the tutorial is confusing"),
    ])
    assert result["clusters"]["near_copy"] == []


def test_shuffled_input_has_same_cluster_membership():
    rows = [
        row("1", "a templated sentence about a very useful feature", author="a"),
        row("2", "a templated sentence about a very useful feature!", author="b"),
        row("3", "a completely independent review of the soundtrack", author="c"),
    ]
    shuffled = list(rows)
    random.Random(7).shuffle(shuffled)
    first = report(rows)["clusters"]["near_copy"]
    second = report(shuffled)["clusters"]["near_copy"]
    assert [item["unique_review_ids"] for item in first] == [item["unique_review_ids"] for item in second]


def test_exact_reviews_are_not_counted_as_additional_near_copy():
    result = report([row("1", "a repeated but informative review phrase"), row("2", "a repeated but informative review phrase")])
    assert result["text_repetition"]["exact_duplicate_review_count"] == 2
    assert result["text_repetition"]["near_copy_additional_review_count"] == 0
    assert result["text_repetition"]["coordinated_expression_review_count"] == 2


def test_unique_text_share_uses_raw_population_denominator():
    result = report([row("1", "same long expression"), row("2", "same long expression"), row("3", "different long expression")])
    assert result["text_repetition"]["unique_normalized_text_count"] == 2
    assert result["text_repetition"]["unique_text_share"] == 2 / 3


def test_coordinated_share_uses_raw_population_denominator():
    result = report([row("1", "same long expression here"), row("2", "same long expression here"), row("3", "an independent review with different words")])
    assert result["text_repetition"]["coordinated_expression_share"] == 2 / 3


def test_daily_bins_are_deterministic_utc_bins():
    result = report([row("1", "first review", day=0), row("2", "second review", day=1)])
    bins = result["time_series"]["bins"]
    assert result["time_series"]["timezone"] == "UTC"
    assert [item["start_time"] for item in bins] == ["2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"]
    assert [item["review_count"] for item in bins] == [1, 1]


def test_hourly_binning_works():
    result = report([row("1", "first review", hour=0), row("2", "second review", hour=2)], grain="hour")
    assert result["time_series"]["grain"] == "hour"
    assert len(result["time_series"]["bins"]) == 3
    assert result["time_series"]["bins"][1]["review_count"] == 0


def test_missing_timestamps_are_excluded_from_bins_and_counted():
    missing = row("missing", "no timestamp")
    missing["timestamp_created"] = None
    result = report([missing, row("1", "dated review")])
    assert result["population"]["missing_timestamp_n"] == 1
    assert sum(item["review_count"] for item in result["time_series"]["bins"]) == 1


def test_constant_activity_does_not_create_fake_spikes():
    result = report([row(str(day), f"independent review {day}", day=day) for day in range(8)])
    assert result["spikes"]["spike_bin_count"] == 0


def test_obvious_volume_spike_is_detected():
    rows = [row(str(day), f"independent review {day}", day=day) for day in range(3)]
    rows.extend(row(f"spike-{index}", f"independent spike review {index}", day=3) for index in range(6))
    result = report(rows)
    assert result["summary"]["activity_spike_detected"] is True
    assert result["spikes"]["bins"][0]["review_count"] == 6


def test_mad_zero_fallback_is_safe_and_transparent():
    rows = [row(str(day), f"independent review {day}", day=day) for day in range(3)]
    rows.extend(row(f"spike-{index}", f"independent spike review {index}", day=3) for index in range(4))
    result = report(rows)
    spike = result["spikes"]["bins"][0]
    assert spike["baseline_mad"] == 0.0
    assert spike["robust_spike_score"] == 3.0
    assert "MAD > 0" in result["methodology"]["spike_formula"]


def test_spike_can_occur_without_coordinated_text():
    baseline_texts = ["controller feedback is precise and responsive", "the soundtrack has memorable orchestration", "tutorial explanations need more clarity"]
    spike_texts = ["performance is stable on older hardware", "the level design rewards careful exploration", "multiplayer matchmaking feels fair today", "accessibility options cover many needs", "the visual effects are colorful and readable", "save slots are convenient for long sessions"]
    rows = [row(str(day), baseline_texts[day], day=day) for day in range(3)]
    rows.extend(row(f"spike-{index}", text, day=3) for index, text in enumerate(spike_texts))
    result = report(rows)
    assert result["summary"]["activity_spike_detected"] is True
    assert result["summary"]["coordinated_expression_detected"] is False


def test_coordinated_text_can_occur_without_volume_spike():
    rows = [row(str(day), "the same informative expression appears here", day=day) for day in range(8)]
    result = report(rows)
    assert result["summary"]["coordinated_expression_detected"] is True
    assert result["summary"]["activity_spike_detected"] is False


def test_spike_plus_concentrated_repeated_text_exposes_both_signals():
    rows = [row(str(day), f"different baseline review {day}", day=day) for day in range(3)]
    rows.extend(row(f"spike-{index}", "the same informative expression appears here", day=3, hour=index) for index in range(6))
    result = report(rows)
    assert result["summary"]["activity_spike_detected"] is True
    assert result["summary"]["coordinated_expression_detected"] is True
    assert result["summary"]["spike_and_coordinated_expression"] is True
    assert result["clusters"]["exact"][0]["share_within_24h"] == 1.0


def test_cluster_temporal_concentration_is_calculated():
    rows = [row(str(index), "same informative expression appears here", day=0, hour=index) for index in range(3)]
    result = report(rows)
    cluster = result["clusters"]["exact"][0]
    assert cluster["duration_seconds"] == 7_200
    assert cluster["share_within_1h"] == 2 / 3
    assert cluster["share_within_6h"] == 1.0
    assert cluster["share_within_24h"] == 1.0


def test_unique_author_count_excludes_missing_author_ids():
    result = report([row("1", "same informative expression appears here", author="a"), row("2", "same informative expression appears here"), row("3", "same informative expression appears here", author="a")])
    cluster = result["clusters"]["exact"][0]
    assert cluster["unique_author_count"] == 1
    assert cluster["missing_author_n"] == 1
    assert cluster["reviews_per_unique_author"] == 3.0


def test_cluster_recommendation_composition_is_correct():
    result = report([row("1", "same informative expression appears here", voted_up=True), row("2", "same informative expression appears here", voted_up=False), row("3", "same informative expression appears here", voted_up=None)])
    cluster = result["clusters"]["exact"][0]
    assert cluster["recommended_n"] == 1
    assert cluster["not_recommended_n"] == 1
    assert cluster["valid_outcome_n"] == 2
    assert cluster["recommendation_rate"] == 0.5


def test_population_recommendation_denominator_is_unchanged_by_diagnostics():
    rows = [row("1", "same informative expression appears here", voted_up=True), row("2", "same informative expression appears here", voted_up=False), row("3", "independent review", voted_up=None)]
    result = report(rows)
    assert result["population"]["valid_n"] == 2
    assert result["population"]["recommended_n"] == 1
    assert result["population"]["not_recommended_n"] == 1
    assert result["population"]["recommendation_rate"] == 0.5
    assert len(rows) == 3


def test_neutral_terminology_has_no_automatic_spam_or_bot_label():
    result = report([row("1", "same informative expression appears here"), row("2", "same informative expression appears here")])
    assert result["clusters"]["exact"][0]["cluster_type"] == "exact"
    assert "spam" not in {item["cluster_type"] for item in result["clusters"]["all"]}
    assert "bot" not in {item["cluster_type"] for item in result["clusters"]["all"]}
    assert "review_bomb" not in {item["cluster_type"] for item in result["clusters"]["all"]}


def test_method_and_threshold_provenance_is_present():
    result = report([])
    methodology = result["methodology"]
    assert methodology["normalization_version"]
    assert methodology["similarity_method"]
    assert methodology["thresholds"]["minimum_normalized_characters"] == 20
    assert "candidate_pairs_examined" in methodology["candidate_diagnostics"]
    assert methodology["candidate_diagnostics"]["candidate_generation_complete"] is True


def test_oversized_lsh_bucket_exposes_incomplete_candidate_generation():
    rows = [
        row("1", "the same long templated expression for bucket diagnostics", author="a"),
        row("2", "the same long templated expression for bucket diagnostics!", author="b"),
    ]
    result = report(rows, config={"max_lsh_bucket_size": 1})
    diagnostics = result["methodology"]["candidate_diagnostics"]
    assert diagnostics["oversized_bucket_count"] > 0
    assert diagnostics["oversized_bucket_member_count"] == 2
    assert diagnostics["max_observed_bucket_size"] == 2
    assert diagnostics["candidate_generation_complete"] is False
    assert result["limitations"]["near_copy_detection_may_be_underestimated_due_to_oversized_lsh_buckets"] is True
    assert result["population"]["raw_review_count"] == 2
    assert result["population"]["recommended_n"] == 2


def test_report_is_json_serializable_and_empty_population_is_valid():
    result = report([])
    json.dumps(result, sort_keys=True)
    assert result["population"]["raw_review_count"] == 0
    assert result["time_series"]["bins"] == []
    assert result["spikes"]["bins"] == []


def test_candidate_diagnostics_show_blocking_reduction_for_thousands_of_rows():
    rows = [row(str(index), f"independent review with unique words {index} and details", day=index % 3) for index in range(3000)]
    result = report(rows)
    diagnostics = result["methodology"]["candidate_diagnostics"]
    assert diagnostics["possible_all_pairs"] == 3000 * 2999 // 2
    assert diagnostics["candidate_pairs_examined"] < diagnostics["possible_all_pairs"]
    assert diagnostics["candidate_reduction_ratio"] > 0.0


def test_normalization_preserves_meaningful_punctuation_and_unicode():
    normalized = normalize_review_text("  Caf\u00e9\n\u5f88\u597d!  ")
    assert normalized.startswith("caf")
    assert " " in normalized
    assert normalized.endswith("!")


def test_module_has_no_live_steam_or_llm_dependency():
    import apps.api.senti_next.activity_diagnostics as module

    source = inspect.getsource(module)
    assert "requests.get" not in source
    assert "steam_api" not in source
    assert "import requests" not in source
    assert "from .steam_api" not in source
