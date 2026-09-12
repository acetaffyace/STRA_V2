from __future__ import annotations

import json

from apps.api.senti_next.rate_inference import (
    MODEL_ASSUMPTIONS,
    calculate_recommendation_rate,
    compare_recommendation_rates,
)


def rows(values: list[bool | None]) -> list[dict]:
    return [{"voted_up": value} for value in values]


def complete_metadata(**overrides: object) -> dict:
    result = {
        "collection_complete": True,
        "truncated_by_max_reviews": False,
        "stop_reason": "end_of_results",
    }
    result.update(overrides)
    return result


def test_recommendation_numerator_denominator_and_missing_values() -> None:
    report = calculate_recommendation_rate(rows([True, False, True, None]))
    assert report["population"] == {
        "valid_n": 3,
        "recommended_n": 2,
        "not_recommended_n": 1,
        "missing_n": 1,
        "recommendation_rate": 2 / 3,
        "observed_population_metric": True,
        "observed_metric_status": "exact_for_observed_reviews",
    }


def test_wilson_interval_uses_explicit_method() -> None:
    report = calculate_recommendation_rate(rows([True, True, False, False]))
    interval = report["model_based_interval"]
    assert interval["method"] == "wilson"
    assert interval["estimate"] == 0.5
    assert interval["lower"] < 0.5 < interval["upper"]
    assert interval["confidence_level"] == 0.95
    assert interval["interval_width"] == interval["upper"] - interval["lower"]
    assert interval["assumptions"] == MODEL_ASSUMPTIONS


def test_zero_and_all_recommended_counts_have_valid_wilson_intervals() -> None:
    zero = calculate_recommendation_rate(rows([False] * 10))["model_based_interval"]
    all_recommended = calculate_recommendation_rate(rows([True] * 10))["model_based_interval"]
    assert zero["lower"] == 0.0
    assert zero["upper"] > 0.0
    assert all_recommended["lower"] < 1.0
    assert all_recommended["upper"] == 1.0


def test_zero_observations_return_null_inference() -> None:
    report = calculate_recommendation_rate(rows([None, None]))
    interval = report["model_based_interval"]
    assert report["population"]["recommendation_rate"] is None
    assert interval["estimate"] is None
    assert interval["lower"] is None
    assert interval["upper"] is None
    assert interval["unavailable_reason"] == "no_valid_recommendation_observations"


def test_difference_sign_is_comparison_minus_reference() -> None:
    report = compare_recommendation_rates(
        rows([True, False, False, False]),
        rows([True, True, False, False]),
    )
    difference = report["difference"]
    assert difference["difference"] == 0.5 - 0.25
    assert difference["difference_percentage_points"] == 25.0
    assert difference["sign_convention"] == "comparison - reference"


def test_newcombe_interval_is_returned_for_two_proportions() -> None:
    report = compare_recommendation_rates(rows([True] * 6 + [False] * 4), rows([True] * 7 + [False] * 3))
    difference = report["difference"]
    assert difference["method"] == "newcombe"
    assert difference["lower"] < difference["difference"] < difference["upper"]
    assert difference["interval_contains_zero"] is True


def test_unequal_n_is_handled_and_small_n_is_wider() -> None:
    unequal = compare_recommendation_rates(rows([True] * 3 + [False] * 2), rows([True] * 60 + [False] * 40))
    assert unequal["reference"]["valid_n"] == 5
    assert unequal["comparison"]["valid_n"] == 100
    small = calculate_recommendation_rate(rows([True] * 6 + [False] * 4))["model_based_interval"]
    large = calculate_recommendation_rate(rows([True] * 3000 + [False] * 2000))["model_based_interval"]
    assert small["interval_width"] > large["interval_width"]


def test_rate_difference_does_not_make_causal_or_significance_claim() -> None:
    report = compare_recommendation_rates(rows([False]), rows([True]))
    encoded = json.dumps(report, sort_keys=True).lower()
    assert "caused" not in encoded
    assert "statistically significant" not in encoded
    assert "interval_contains_zero" in encoded


def test_complete_acquisition_is_exact_for_observed_population() -> None:
    report = calculate_recommendation_rate(rows([True, False]), metadata=complete_metadata())
    validity = report["inference_validity"]
    assert validity["acquisition_complete"] is True
    assert validity["observed_metric_status"] == "exact_for_observed_population"
    assert validity["inference_eligibility"] == "model_based_only"


def test_chronological_max_review_truncation_is_limited() -> None:
    report = calculate_recommendation_rate(
        rows([True, False]),
        metadata=complete_metadata(
            collection_complete=False,
            truncated_by_max_reviews=True,
            stop_reason="max_reviews_reached",
        ),
    )
    validity = report["inference_validity"]
    assert validity["inference_eligibility"] == "limited"
    assert validity["reason"] == "non_random_chronological_truncation"
    assert validity["observed_metric_status"] == "exact_for_observed_reviews"


def test_incomplete_acquisition_and_reviewer_selection_are_explicit() -> None:
    report = calculate_recommendation_rate(rows([True]), metadata={"collection_complete": False})
    assert report["inference_validity"]["reason"] == "incomplete_acquisition"
    assert report["external_validity"]["reviewer_selection_bias"] is True
    assert "self-selected" in report["external_validity"]["limitation"]


def test_comparability_context_can_be_attached_without_recalculation() -> None:
    context = {
        "acquisition_validity": {"level": "high"},
        "composition_comparability": {"level": "moderate"},
        "external_validity": {"reviewer_selection_bias": True, "limitation": "limited"},
    }
    report = compare_recommendation_rates(rows([True]), rows([False]), comparability_report=context)
    assert report["comparison_context"]["composition_comparability"]["level"] == "moderate"
    assert report["comparison_context"]["reviewer_selection_bias"] is True


def test_rate_report_is_deterministically_json_serializable() -> None:
    first = json.dumps(compare_recommendation_rates(rows([True, False]), rows([True])), sort_keys=True)
    second = json.dumps(compare_recommendation_rates(rows([True, False]), rows([True])), sort_keys=True)
    assert first == second
