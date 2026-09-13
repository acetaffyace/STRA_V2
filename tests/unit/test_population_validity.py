from __future__ import annotations

import json

from apps.api.senti_next.population_validity import compare_populations


def review(
    review_id: str,
    *,
    language: str = "english",
    playtime_minutes: int | None = 60,
    steam_purchase: bool | None = True,
    received_for_free: bool | None = False,
    early_access: bool | None = False,
    steam_deck: bool | None = False,
    voted_up: bool = True,
) -> dict:
    return {
        "recommendationid": review_id,
        "language": language,
        "timestamp_created": 1735689600,
        "voted_up": voted_up,
        "steam_purchase": steam_purchase,
        "received_for_free": received_for_free,
        "written_during_early_access": early_access,
        "primarily_steam_deck": steam_deck,
        "author": {"playtime_at_review": playtime_minutes},
    }


def metadata(
    *,
    complete: bool = True,
    languages: list[str] | None = None,
    language_stats: dict | None = None,
    start: str = "2025-01-01",
    end: str = "2025-01-02",
) -> dict:
    languages = languages or ["english"]
    return {
        "window_start": start,
        "window_end": end,
        "collection_complete": complete,
        "truncated_by_max_reviews": False,
        "stop_reason": "end_of_results" if complete else "max_reviews_reached",
        "sampling_contract": {"languages": languages},
        "language_stats": language_stats,
    }


def test_identical_populations_are_highly_comparable() -> None:
    rows = [review("a", playtime_minutes=60), review("b", playtime_minutes=600)]
    report = compare_populations(rows, rows, reference_metadata=metadata(), comparison_metadata=metadata())
    assert report["comparability"]["level"] == "high"
    assert report["dimensions"]["language"]["total_variation_distance"] == 0.0
    assert report["dimensions"]["playtime"]["composition_distance"] == 0.0


def test_large_language_shift_is_detected() -> None:
    report = compare_populations(
        [review("a", language="english"), review("b", language="english")],
        [review("c", language="schinese"), review("d", language="schinese")],
        reference_metadata=metadata(),
        comparison_metadata=metadata(languages=["schinese"]),
    )
    assert report["dimensions"]["language"]["total_variation_distance"] == 1.0
    assert report["dimensions"]["language"]["level"] == "low"


def test_large_playtime_shift_is_detected() -> None:
    report = compare_populations(
        [review("a", playtime_minutes=60)],
        [review("b", playtime_minutes=12_000)],
        reference_metadata=metadata(),
        comparison_metadata=metadata(),
    )
    assert report["dimensions"]["playtime"]["composition_distance"] == 1.0
    assert report["dimensions"]["playtime"]["level"] == "low"


def test_purchase_source_shift_is_detected() -> None:
    report = compare_populations(
        [review("a", steam_purchase=True)],
        [review("b", steam_purchase=False)],
        reference_metadata=metadata(),
        comparison_metadata=metadata(),
    )
    dimension = report["dimensions"]["purchase_source"]
    assert dimension["absolute_percentage_point_difference"] == 1.0
    assert dimension["reference"]["valid_n"] == dimension["comparison"]["valid_n"] == 1


def test_missingness_shift_is_reported() -> None:
    report = compare_populations(
        [review("a")],
        [review("b", language="", playtime_minutes=None, steam_purchase=None, received_for_free=None, early_access=None, steam_deck=None)],
        reference_metadata=metadata(),
        comparison_metadata=metadata(),
    )
    missingness = report["dimensions"]["missingness"]
    assert "language" in missingness["warning_fields"]
    assert "playtime_at_review" in missingness["warning_fields"]
    assert "steam_purchase" in missingness["warning_fields"]
    assert "missingness_shift" in report["comparability"]["warnings"]


def test_unequal_counts_with_equal_composition_can_remain_high() -> None:
    reference = [review("a"), review("b"), review("c", playtime_minutes=600), review("d", playtime_minutes=600)]
    comparison = [
        review("e"), review("f"), review("g"), review("h"),
        review("i", playtime_minutes=600), review("j", playtime_minutes=600),
        review("k", playtime_minutes=600), review("l", playtime_minutes=600),
    ]
    report = compare_populations(
        reference,
        comparison,
        reference_metadata=metadata(start="2025-01-01", end="2025-01-02"),
        comparison_metadata=metadata(start="2025-01-01", end="2025-01-04"),
    )
    assert report["acquisition"]["reference"]["population_count"] == 4
    assert report["acquisition"]["comparison"]["population_count"] == 8
    assert report["dimensions"]["review_volume"]["absolute_volume_difference"] == 4
    assert report["comparability"]["level"] == "high"


def test_equal_counts_with_different_composition_are_not_high() -> None:
    report = compare_populations(
        [review("a", language="english")],
        [review("b", language="schinese")],
        reference_metadata=metadata(),
        comparison_metadata=metadata(languages=["schinese"]),
    )
    assert report["acquisition"]["reference"]["population_count"] == report["acquisition"]["comparison"]["population_count"]
    assert report["comparability"]["level"] == "low"


def test_different_window_lengths_compare_reviews_per_day() -> None:
    report = compare_populations(
        [review("a"), review("b")],
        [review("c"), review("d"), review("e"), review("f")],
        reference_metadata=metadata(start="2025-01-01", end="2025-01-02"),
        comparison_metadata=metadata(start="2025-01-01", end="2025-01-08"),
    )
    volume = report["dimensions"]["review_volume"]
    assert volume["reference"]["reviews_per_day"] == 1.0
    assert volume["comparison"]["reviews_per_day"] == 0.5
    assert volume["reviews_per_day_ratio"] == 0.5


def test_incomplete_acquisition_triggers_validity_warning() -> None:
    report = compare_populations(
        [review("a")],
        [review("b")],
        reference_metadata=metadata(),
        comparison_metadata=metadata(complete=False),
    )
    assert report["comparability"]["level"] == "low"
    assert "comparison_acquisition_incomplete" in report["comparability"]["warnings"]


def test_failed_language_is_explicit_and_prevents_high_comparability() -> None:
    stats = {
        "english": {"status": "complete", "collection_complete": True},
        "schinese": {"status": "failed", "collection_complete": False, "error": "timeout"},
    }
    report = compare_populations(
        [review("a")],
        [review("b", language="schinese")],
        reference_metadata=metadata(),
        comparison_metadata=metadata(languages=["english", "schinese"], language_stats=stats),
    )
    acquisition = report["acquisition"]["comparison"]
    assert acquisition["failed_languages"] == ["schinese"]
    assert acquisition["language_stats"]["schinese"]["error"] == "timeout"
    assert report["comparability"]["level"] == "low"


def test_recommendation_difference_does_not_change_composition_comparability() -> None:
    reference = [review("a", voted_up=True), review("b", voted_up=True)]
    comparison = [review("c", voted_up=False), review("d", voted_up=False)]
    report = compare_populations(reference, comparison, reference_metadata=metadata(), comparison_metadata=metadata())
    assert report["comparability"]["level"] == "high"
    assert "recommendation" not in report["comparability"]["dimensions"]


def test_reviewer_selection_limitation_is_always_present() -> None:
    report = compare_populations([], [], reference_metadata=metadata(), comparison_metadata=metadata())
    assert report["external_validity"]["reviewer_selection_bias"] is True
    assert "self-selected reviewers" in report["external_validity"]["limitation"]


def test_missing_provenance_is_unknown_rather_than_claiming_high() -> None:
    report = compare_populations([review("a")], [review("b")])
    assert report["dimensions"]["acquisition"]["level"] == "unknown"
    assert report["comparability"]["level"] == "unknown"


def test_report_is_deterministically_json_serializable() -> None:
    report = compare_populations([review("a")], [review("b")], reference_metadata=metadata(), comparison_metadata=metadata())
    first = json.dumps(report, sort_keys=True)
    second = json.dumps(compare_populations([review("a")], [review("b")], reference_metadata=metadata(), comparison_metadata=metadata()), sort_keys=True)
    assert first == second


def test_missing_playtime_in_both_populations_is_unknown_not_zero_distance() -> None:
    report = compare_populations(
        [review("a", playtime_minutes=None)],
        [review("b", playtime_minutes=None)],
        reference_metadata=metadata(),
        comparison_metadata=metadata(),
    )
    playtime = report["dimensions"]["playtime"]
    assert playtime["reference"]["valid_n"] == playtime["comparison"]["valid_n"] == 0
    assert playtime["reference"]["coverage"] == playtime["comparison"]["coverage"] == 0.0
    assert playtime["observability"] == "none"
    assert playtime["reason"] == "insufficient_observed_data"
    assert playtime["composition_distance"] is None
    assert playtime["level"] == "unknown"


def timestamp_metadata(start: int, end: int, **extra: object) -> dict:
    return {
        "coverage_start_time": start,
        "coverage_end_time": end,
        "coverage_end_inclusive": False,
        "coverage_status": "complete",
        "collection_complete": True,
        "truncated_by_max_reviews": False,
        "stop_reason": "end_of_results",
        **extra,
    }


def test_half_open_timestamp_interval_is_exactly_fourteen_days() -> None:
    start = 1_754_956_800
    end = start + 14 * 86_400
    report = compare_populations(
        [review("a"), review("b")],
        [review("c"), review("d")],
        reference_metadata=timestamp_metadata(start, end),
        comparison_metadata=timestamp_metadata(start, end),
    )
    activity = report["review_activity"]
    assert activity["reference"]["window_days"] == 14.0
    assert activity["comparison"]["window_days"] == 14.0


def test_half_open_reviews_per_day_uses_fourteen_not_fifteen_days() -> None:
    start = 1_754_956_800
    end = start + 14 * 86_400
    reference = [review(f"r-{index}") for index in range(331)]
    comparison = [review(f"c-{index}") for index in range(421)]
    report = compare_populations(
        reference,
        comparison,
        reference_metadata=timestamp_metadata(start, end),
        comparison_metadata=timestamp_metadata(start, end),
    )
    activity = report["review_activity"]
    assert activity["reference"]["reviews_per_day"] == 331 / 14
    assert activity["comparison"]["reviews_per_day"] == 421 / 14
    assert activity["reviews_per_day_ratio"] == (421 / 14) / (331 / 14)


def test_half_open_twelve_hour_timestamp_interval_is_half_day() -> None:
    start = 1_754_956_800
    end = start + 12 * 3_600
    report = compare_populations(
        [review("a")],
        [review("b")],
        reference_metadata=timestamp_metadata(start, end),
        comparison_metadata=timestamp_metadata(start, end),
    )
    assert report["review_activity"]["reference"]["window_days"] == 0.5


def test_explicit_legacy_inclusive_calendar_dates_remain_two_days() -> None:
    report = compare_populations(
        [review("a"), review("b")],
        [review("c"), review("d")],
        reference_metadata=metadata(start="2025-01-01", end="2025-01-02"),
        comparison_metadata=metadata(start="2025-01-01", end="2025-01-02"),
    )
    assert report["review_activity"]["reference"]["window_days"] == 2.0


def test_explicit_window_days_overrides_temporal_bounds() -> None:
    start = 1_754_956_800
    end = start + 14 * 86_400
    report = compare_populations(
        [review("a"), review("b")],
        [review("c"), review("d")],
        reference_metadata=timestamp_metadata(start, end, window_days=7),
        comparison_metadata=timestamp_metadata(start, end, window_days=7),
    )
    assert report["review_activity"]["reference"]["window_days"] == 7.0
    assert report["review_activity"]["reference"]["reviews_per_day"] == 2 / 7


def test_unknown_timestamp_boundary_semantics_do_not_fabricate_duration() -> None:
    start = "2026-08-15T12:00:00Z"
    end = "2026-08-16T00:00:00Z"
    report = compare_populations(
        [review("a")],
        [review("b")],
        reference_metadata={"window_start": start, "window_end": end, "collection_complete": True},
        comparison_metadata={"window_start": start, "window_end": end, "collection_complete": True},
    )
    assert report["review_activity"]["reference"]["window_days"] is None
    assert report["review_activity"]["reference"]["reviews_per_day"] is None


def test_exposure_fix_does_not_change_composition_comparability() -> None:
    start = 1_754_956_800
    end = start + 14 * 86_400
    reference = [review("a", language="english"), review("b", language="schinese")]
    comparison = [review("c", language="english"), review("d", language="schinese")]
    timestamp_report = compare_populations(
        reference,
        comparison,
        reference_metadata=timestamp_metadata(start, end),
        comparison_metadata=timestamp_metadata(start, end),
    )
    legacy_report = compare_populations(
        reference,
        comparison,
        reference_metadata=metadata(start="2025-01-01", end="2025-01-14"),
        comparison_metadata=metadata(start="2025-01-01", end="2025-01-14"),
    )
    assert timestamp_report["composition_comparability"] == legacy_report["composition_comparability"]


def test_missing_playtime_in_one_population_is_unknown() -> None:
    report = compare_populations(
        [review("a", playtime_minutes=None)],
        [review("b", playtime_minutes=60)],
        reference_metadata=metadata(),
        comparison_metadata=metadata(),
    )
    playtime = report["dimensions"]["playtime"]
    assert playtime["observability"] == "partial"
    assert playtime["level"] == "unknown"
    assert playtime["distance"] is None


def test_identical_observed_playtime_remains_high() -> None:
    report = compare_populations(
        [review("a", playtime_minutes=60)],
        [review("b", playtime_minutes=60)],
        reference_metadata=metadata(),
        comparison_metadata=metadata(),
    )
    assert report["dimensions"]["playtime"]["observability"] == "both"
    assert report["dimensions"]["playtime"]["level"] == "high"


def test_fully_missing_optional_metadata_is_unknown_but_missingness_shift_is_low() -> None:
    reference = [review("a", steam_purchase=None, received_for_free=None, early_access=None, steam_deck=None)]
    comparison = [review("b", steam_purchase=None, received_for_free=None, early_access=None, steam_deck=None)]
    report = compare_populations(reference, comparison, reference_metadata=metadata(), comparison_metadata=metadata())
    assert report["dimensions"]["purchase_source"]["level"] == "unknown"
    assert report["dimensions"]["free_copy"]["level"] == "unknown"
    assert report["dimensions"]["early_access"]["level"] == "unknown"
    assert report["dimensions"]["steam_deck"]["level"] == "unknown"
    assert report["dimensions"]["missingness"]["shift_level"] == "low"
    assert report["data_quality"]["observability"]["purchase_source"] == "none"


def test_activity_shift_is_reported_without_downgrading_composition() -> None:
    report = compare_populations(
        [review("a")],
        [review(str(index)) for index in range(10)],
        reference_metadata=metadata(start="2025-01-01", end="2025-01-01"),
        comparison_metadata=metadata(start="2025-01-01", end="2025-01-01"),
    )
    activity = report["review_activity"]
    assert activity["reviews_per_day_ratio"] == 10.0
    assert activity["shift_level"] == "large"
    assert report["composition_comparability"]["level"] == "high"
    assert report["comparability"]["level"] == "high"
    assert "review_activity_shift" in report["comparability"]["warnings"]


def test_unavailable_steam_deck_does_not_invalidate_other_dimensions() -> None:
    reference = [review("a", steam_deck=None)]
    comparison = [review("b", steam_deck=None)]
    report = compare_populations(reference, comparison, reference_metadata=metadata(), comparison_metadata=metadata())
    assert report["dimensions"]["steam_deck"]["level"] == "unknown"
    assert report["dimensions"]["language"]["level"] == "high"
    assert report["dimensions"]["playtime"]["level"] == "high"
    assert report["composition_comparability"]["level"] == "high"


def test_incomplete_acquisition_blocks_strong_top_level_claim_but_not_observed_composition() -> None:
    report = compare_populations(
        [review("a")],
        [review("b")],
        reference_metadata=metadata(),
        comparison_metadata=metadata(complete=False),
    )
    assert report["composition_comparability"]["level"] == "high"
    assert report["comparability"]["level"] == "low"
    assert report["acquisition_validity"]["level"] == "low"


def test_empty_populations_have_unknown_composition_and_null_distributions() -> None:
    report = compare_populations([], [], reference_metadata=metadata(), comparison_metadata=metadata())
    assert report["dimensions"]["language"]["reference_distribution"] is None
    assert report["dimensions"]["language"]["comparison_distribution"] is None
    assert report["dimensions"]["language"]["reason"] == "insufficient_observed_data"
    assert report["composition_comparability"]["level"] == "unknown"


def test_equal_complete_missingness_is_not_called_high_data_quality() -> None:
    report = compare_populations(
        [review("a", steam_purchase=None)],
        [review("b", steam_purchase=None)],
        reference_metadata=metadata(),
        comparison_metadata=metadata(),
    )
    assert report["dimensions"]["purchase_source"]["observability"] == "none"
    assert report["data_quality"]["missingness_shift_level"] == "low"
    assert report["data_quality"]["level"] == "low"
    assert report["data_quality"]["level_semantics"] == "missingness_pattern_similarity"
