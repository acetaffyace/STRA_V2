from __future__ import annotations

import json

import pytest

from apps.api.senti_next.window_robustness import matched_window_robustness
from apps.api.senti_next.window_robustness import _as_timestamp, _coverage_bounds


REFERENCE_ANCHOR = 1_000_000.0
COMPARISON_ANCHOR = 2_000_000.0
DAY = 86_400.0


def review(review_id: str, timestamp: float | None, voted_up: bool | None, *, language: str = "english", playtime: int = 60) -> dict:
    return {
        "recommendationid": review_id,
        "timestamp_created": timestamp,
        "voted_up": voted_up,
        "language": language,
        "author": {"playtime_at_review": playtime},
    }


def metadata(anchor: float, days: int = 14, complete: bool = True) -> dict:
    return {
        "collection_complete": complete,
        "coverage_start_time": anchor,
        "coverage_end_time": anchor + days * DAY,
        "stop_reason": "end_of_results" if complete else "api_failure",
    }


def basic_populations() -> tuple[list[dict], list[dict]]:
    reference = [review("r0", REFERENCE_ANCHOR, False), review("r1", REFERENCE_ANCHOR + 2 * DAY, False), review("r2", REFERENCE_ANCHOR + 8 * DAY, False)]
    comparison = [review("c0", COMPARISON_ANCHOR, True), review("c1", COMPARISON_ANCHOR + 2 * DAY, True), review("c2", COMPARISON_ANCHOR + 8 * DAY, True)]
    return reference, comparison


def test_exact_default_matched_3_7_14_day_slicing_and_own_anchors() -> None:
    reference = [review("r3", REFERENCE_ANCHOR + 3 * DAY, False), review("r7", REFERENCE_ANCHOR + 7 * DAY, False), review("r14", REFERENCE_ANCHOR + 14 * DAY, False)]
    comparison = [review("c3", COMPARISON_ANCHOR + 3 * DAY, True), review("c7", COMPARISON_ANCHOR + 7 * DAY, True), review("c14", COMPARISON_ANCHOR + 14 * DAY, True)]
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR, 14), comparison_metadata=metadata(COMPARISON_ANCHOR, 14))
    assert report["requested_windows_days"] == [3, 7, 14]
    assert report["windows"]["3"]["reference_population"]["review_count"] == 0
    assert report["windows"]["3"]["comparison_population"]["review_count"] == 0
    assert report["windows"]["14"]["reference_population"]["review_count"] == 2
    assert report["windows"]["14"]["reference_population"]["review_ids"] == ["r3", "r7"]
    assert report["windows"]["14"]["reference_population"]["start_time"] == REFERENCE_ANCHOR
    assert report["windows"]["14"]["comparison_population"]["start_time"] == COMPARISON_ANCHOR


def test_end_boundary_is_exclusive() -> None:
    reference = [review("inside", REFERENCE_ANCHOR + 3 * DAY - 1, False), review("boundary", REFERENCE_ANCHOR + 3 * DAY, False)]
    comparison = [review("inside-c", COMPARISON_ANCHOR + 3 * DAY - 1, True), review("boundary-c", COMPARISON_ANCHOR + 3 * DAY, True)]
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR), comparison_metadata=metadata(COMPARISON_ANCHOR))
    assert report["windows"]["3"]["reference_population"]["review_ids"] == ["inside"]
    assert report["windows"]["3"]["comparison_population"]["review_ids"] == ["inside-c"]


def test_missing_timestamps_are_excluded_and_counted() -> None:
    reference = [review("missing", None, True), review("valid", REFERENCE_ANCHOR, False)]
    comparison = [review("missing-c", None, True), review("valid-c", COMPARISON_ANCHOR, True)]
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR), comparison_metadata=metadata(COMPARISON_ANCHOR))
    assert report["reference_missing_timestamp_n"] == 1
    assert report["comparison_missing_timestamp_n"] == 1
    assert report["windows"]["3"]["reference_population"]["missing_timestamp_n"] == 1
    assert report["windows"]["3"]["reference_population"]["review_count"] == 1


def test_unequal_review_counts_are_preserved_without_downsampling() -> None:
    reference = [review(f"r{i}", REFERENCE_ANCHOR + i, False) for i in range(2)]
    comparison = [review(f"c{i}", COMPARISON_ANCHOR + i, True) for i in range(20)]
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR), comparison_metadata=metadata(COMPARISON_ANCHOR))
    assert report["windows"]["3"]["reference_population"]["review_count"] == 2
    assert report["windows"]["3"]["comparison_population"]["review_count"] == 20


def test_stage_2a_comparability_and_stage_2b_recommendation_are_attached() -> None:
    reference, comparison = basic_populations()
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR), comparison_metadata=metadata(COMPARISON_ANCHOR))
    window = report["windows"]["3"]
    assert "composition_comparability" in window["comparability"]
    assert "acquisition_validity" in window["comparability"]
    assert "review_activity" in window["comparability"]
    assert window["recommendation"]["raw_difference"] == 1.0
    assert window["recommendation"]["reference_wilson_interval"]["method"] == "wilson"
    assert window["recommendation"]["newcombe_difference_interval"]["method"] == "newcombe"


def test_stage_2c_standardized_sensitivity_is_optional_and_has_no_ci() -> None:
    reference, comparison = basic_populations()
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR), comparison_metadata=metadata(COMPARISON_ANCHOR), standardization_variables=["language"])
    assert report["windows"]["3"]["standardization"]["standardized_interval"] is None
    assert report["windows"]["3"]["standardization"]["support_status"] == "complete"
    assert report["robustness"]["standardized"] is not None


def test_same_sign_deltas_are_direction_consistent() -> None:
    reference = [review("r0", REFERENCE_ANCHOR, False), review("r1", REFERENCE_ANCHOR + 5 * DAY, False)]
    comparison = [review("c0", COMPARISON_ANCHOR, True), review("c1", COMPARISON_ANCHOR + 5 * DAY, True)]
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR), comparison_metadata=metadata(COMPARISON_ANCHOR))
    assert report["robustness"]["raw"]["direction_consistent"] is True
    assert report["robustness"]["raw"]["direction_reversal"] is False


def test_sign_reversal_is_detected_and_windows_are_reported() -> None:
    reference = [review("r0", REFERENCE_ANCHOR, False)] + [review(f"r{i}", REFERENCE_ANCHOR + 4 * DAY + i, True) for i in range(9)]
    comparison = [review("c0", COMPARISON_ANCHOR, True)] + [review(f"c{i}", COMPARISON_ANCHOR + 4 * DAY + i, False) for i in range(9)]
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR), comparison_metadata=metadata(COMPARISON_ANCHOR))
    assert report["robustness"]["raw"]["direction_reversal"] is True
    assert report["robustness"]["raw"]["direction_consistent"] is False
    assert report["robustness"]["raw"]["direction_reversal_windows"] == [3, 7, 14]


def test_magnitude_range_and_largest_window_change_are_reported() -> None:
    reference = [review("r0", REFERENCE_ANCHOR, False), review("r1", REFERENCE_ANCHOR + 5 * DAY, False), review("r2", REFERENCE_ANCHOR + 9 * DAY, False)]
    comparison = [review("c0", COMPARISON_ANCHOR, True), review("c1", COMPARISON_ANCHOR + 5 * DAY, True), review("c2", COMPARISON_ANCHOR + 9 * DAY, False)]
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR), comparison_metadata=metadata(COMPARISON_ANCHOR))
    raw = report["robustness"]["raw"]
    assert raw["range"] == pytest.approx(1 / 3)
    assert raw["range_percentage_points"] == pytest.approx(100 / 3)
    assert raw["largest_window_to_window_change"] == pytest.approx(1 / 3)


def test_incomplete_temporal_coverage_invalidates_only_long_window() -> None:
    reference, comparison = basic_populations()
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR, 10), comparison_metadata=metadata(COMPARISON_ANCHOR, 14))
    assert report["windows"]["3"]["status"] == "complete"
    assert report["windows"]["7"]["status"] == "complete"
    assert report["windows"]["14"]["status"] == "incomplete_coverage"
    assert report["robustness"]["valid_window_count"] == 2


def test_external_events_are_included_only_in_matching_windows() -> None:
    reference, comparison = basic_populations()
    events = [
        {"side": "comparison", "timestamp": COMPARISON_ANCHOR + 7 * DAY, "type": "sale", "label": "boundary"},
        {"side": "comparison", "timestamp": COMPARISON_ANCHOR + 5 * DAY, "type": "patch", "label": "inside"},
    ]
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR), comparison_metadata=metadata(COMPARISON_ANCHOR), events=events)
    assert report["windows"]["3"]["events"]["comparison"]["event_count"] == 0
    assert report["windows"]["7"]["events"]["comparison"]["event_count"] == 1
    assert report["windows"]["7"]["events"]["comparison"]["events_inside_window"][0]["label"] == "inside"


def test_custom_windows_are_supported_and_default_does_not_choose_standardization_variables() -> None:
    reference, comparison = basic_populations()
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR, 30), comparison_metadata=metadata(COMPARISON_ANCHOR, 30), windows_days=[30, 7, 3])
    assert report["requested_windows_days"] == [3, 7, 30]
    assert report["configuration"] == {
        "confidence_level": 0.95,
        "standardization_variables": None,
        "standardization_target": "reference",
    }
    assert report["windows"]["3"]["standardization"] is None
    assert report["robustness"]["standardized"] is None


def test_explicit_stage_2d_configuration_is_exposed_without_changing_slicing() -> None:
    reference, comparison = basic_populations()
    report = matched_window_robustness(
        reference,
        comparison,
        REFERENCE_ANCHOR,
        COMPARISON_ANCHOR,
        reference_metadata=metadata(REFERENCE_ANCHOR),
        comparison_metadata=metadata(COMPARISON_ANCHOR),
        windows_days=(3,),
        standardization_variables=("language",),
        standardization_target="pooled",
        confidence_level=0.90,
    )
    assert report["configuration"] == {
        "confidence_level": 0.90,
        "standardization_variables": ["language"],
        "standardization_target": "pooled",
    }
    window = report["windows"]["3"]
    assert window["standardization"]["target"] == "pooled"
    assert window["standardization"]["variables"] == ["language"]
    assert window["recommendation"]["reference_wilson_interval"]["confidence_level"] == 0.90


def test_incomplete_acquisition_propagates_limitation() -> None:
    reference, comparison = basic_populations()
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR, complete=False), comparison_metadata=metadata(COMPARISON_ANCHOR))
    assert report["windows"]["3"]["status"] == "incomplete_coverage"
    assert report["windows"]["3"]["comparability"]["acquisition_validity"]["level"] == "low"


def test_selection_bias_and_noncausal_limitations_are_explicit() -> None:
    reference, comparison = basic_populations()
    report = matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, reference_metadata=metadata(REFERENCE_ANCHOR), comparison_metadata=metadata(COMPARISON_ANCHOR))
    assert report["limitations"]["reviewer_selection_bias"] is True
    assert report["limitations"]["matched_windows_do_not_establish_causality"] is True
    assert "causal" in report["limitations"]["limitation"].lower()


def test_report_is_deterministic_and_json_serializable() -> None:
    reference, comparison = basic_populations()
    kwargs = {"reference_metadata": metadata(REFERENCE_ANCHOR), "comparison_metadata": metadata(COMPARISON_ANCHOR), "standardization_variables": ["language"]}
    first = json.dumps(matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, **kwargs), sort_keys=True)
    second = json.dumps(matched_window_robustness(reference, comparison, REFERENCE_ANCHOR, COMPARISON_ANCHOR, **kwargs), sort_keys=True)
    assert first == second


def test_complete_contract_coverage_does_not_follow_observed_review_bounds() -> None:
    metadata_with_contract = {
        "collection_complete": True,
        "sampling_contract": {"start_time": REFERENCE_ANCHOR, "end_time": REFERENCE_ANCHOR + 14 * DAY},
        "window_start": "1970-01-02",
        "window_end": "1970-01-03",
    }
    start, end, complete, reason = _coverage_bounds(metadata_with_contract)
    assert start == REFERENCE_ANCHOR
    assert end == REFERENCE_ANCHOR + 14 * DAY
    assert complete is True
    assert reason is None


def test_legacy_observed_only_window_range_is_unknown_coverage() -> None:
    start, end, complete, reason = _coverage_bounds(
        {
            "collection_complete": True,
            "window_start": "2026-09-01",
            "window_end": "2026-09-14",
        }
    )
    assert start is None
    assert end is None
    assert complete is True
    assert reason == "acquisition_temporal_coverage_unknown"


def test_stage_2d_does_not_treat_legacy_observed_range_as_window_coverage() -> None:
    reference, comparison = basic_populations()
    legacy = {"collection_complete": True, "window_start": "1970-01-12", "window_end": "1970-01-20"}
    report = matched_window_robustness(
        reference,
        comparison,
        REFERENCE_ANCHOR,
        COMPARISON_ANCHOR,
        reference_metadata=legacy,
        comparison_metadata=legacy,
    )
    assert report["windows"]["3"]["status"] == "incomplete_coverage"
    assert report["windows"]["7"]["status"] == "incomplete_coverage"
    assert report["windows"]["14"]["status"] == "incomplete_coverage"


def test_truncated_and_incomplete_contracts_do_not_claim_full_coverage() -> None:
    metadata_incomplete = {
        "collection_complete": False,
        "truncated_by_max_reviews": True,
        "sampling_contract": {"start_time": REFERENCE_ANCHOR, "end_time": REFERENCE_ANCHOR + 14 * DAY},
    }
    start, end, complete, reason = _coverage_bounds(metadata_incomplete)
    assert start is None and end is None
    assert complete is False
    assert reason == "acquisition_incomplete"


def test_date_only_and_full_datetime_parsing_are_explicit_and_deterministic() -> None:
    assert _as_timestamp("2026-09-14") == _as_timestamp("2026-09-14T00:00:00Z")
    assert _as_timestamp("2026-09-14", end_boundary=True) == _as_timestamp("2026-09-15T00:00:00Z")
    assert _as_timestamp("2026-09-14T12:34:56Z") == _as_timestamp("2026-09-14T12:34:56+00:00")


def test_complete_contract_coverage_survives_zero_review_interior_day() -> None:
    reference = [review("r0", REFERENCE_ANCHOR, False), review("r7", REFERENCE_ANCHOR + 7 * DAY, False)]
    comparison = [review("c0", COMPARISON_ANCHOR, True), review("c7", COMPARISON_ANCHOR + 7 * DAY, True)]
    report = matched_window_robustness(
        reference,
        comparison,
        REFERENCE_ANCHOR,
        COMPARISON_ANCHOR,
        reference_metadata={"collection_complete": True, "sampling_contract": {"start_time": REFERENCE_ANCHOR, "end_time": REFERENCE_ANCHOR + 14 * DAY}},
        comparison_metadata={"collection_complete": True, "sampling_contract": {"start_time": COMPARISON_ANCHOR, "end_time": COMPARISON_ANCHOR + 14 * DAY}},
    )
    assert report["windows"]["14"]["status"] == "complete"


def test_observed_first_and_last_review_do_not_shift_contract_coverage() -> None:
    reference = [review("r", REFERENCE_ANCHOR + 2 * DAY, False)]
    comparison = [review("c", COMPARISON_ANCHOR + 10 * DAY, True)]
    report = matched_window_robustness(
        reference,
        comparison,
        REFERENCE_ANCHOR,
        COMPARISON_ANCHOR,
        reference_metadata={"collection_complete": True, "sampling_contract": {"start_time": REFERENCE_ANCHOR, "end_time": REFERENCE_ANCHOR + 14 * DAY}},
        comparison_metadata={"collection_complete": True, "sampling_contract": {"start_time": COMPARISON_ANCHOR, "end_time": COMPARISON_ANCHOR + 14 * DAY}},
    )
    reference_coverage = report["windows"]["14"]["reference_population"]["coverage"]
    comparison_coverage = report["windows"]["14"]["comparison_population"]["coverage"]
    assert reference_coverage["source_start_time"] == REFERENCE_ANCHOR
    assert comparison_coverage["source_end_time"] == COMPARISON_ANCHOR + 14 * DAY
