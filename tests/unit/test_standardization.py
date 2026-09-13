from __future__ import annotations

import json

import pytest

from apps.api.senti_next.standardization import (
    SUPPORTED_VARIABLES,
    build_single_dimension_sensitivity,
    standardize_populations,
)


def row(voted_up: bool | None, *, language: str | None = "english", playtime: int | None = 60, **flags: bool | None) -> dict:
    result = {
        "voted_up": voted_up,
        "language": language,
        "author": {"playtime_at_review": playtime},
    }
    result.update(flags)
    return result


def metadata(complete: bool = True) -> dict:
    return {
        "collection_complete": complete,
        "truncated_by_max_reviews": False,
        "stop_reason": "end_of_results" if complete else "api_failure",
    }


def test_identical_composition_preserves_raw_delta() -> None:
    reference = [row(True), row(False)]
    comparison = [row(True), row(False)]
    report = standardize_populations(reference, comparison, variables=["language"])
    assert report["raw"]["difference"] == 0.0
    assert report["standardization"]["standardized_difference"] == 0.0
    assert report["standardization"]["composition_standardization_shift"] == 0.0
    assert report["standardization"]["status"] == "complete"


def test_language_composition_changes_standardized_delta() -> None:
    reference = [row(True, language="english") for _ in range(8)] + [row(False, language="schinese") for _ in range(2)]
    comparison = [row(True, language="english") for _ in range(2)] + [row(False, language="schinese") for _ in range(8)]
    report = standardize_populations(reference, comparison, variables=["language"])
    standardization = report["standardization"]
    assert report["raw"]["difference"] == pytest.approx(-0.6)
    assert standardization["reference_standardized_rate"] == pytest.approx(0.8)
    assert standardization["comparison_standardized_rate"] == pytest.approx(0.8)
    assert standardization["standardized_difference"] == pytest.approx(0.0)
    assert standardization["composition_standardization_shift"] == pytest.approx(0.6)


def test_playtime_composition_uses_stage_2a_cohorts() -> None:
    reference = [row(True, playtime=60) for _ in range(8)] + [row(False, playtime=6000) for _ in range(2)]
    comparison = [row(True, playtime=60) for _ in range(2)] + [row(False, playtime=6000) for _ in range(8)]
    report = standardize_populations(reference, comparison, variables=["playtime_cohort"])
    assert report["standardization"]["status"] == "complete"
    assert report["standardization"]["variables"] == ["playtime_cohort"]
    assert {item["stratum"] for item in report["standardization"]["strata"]} == {"0–2h", "100h+"}
    assert report["standardization"]["standardized_difference"] == pytest.approx(0.0)
    assert report["standardization"]["composition_standardization_shift"] == pytest.approx(0.6)


def test_reference_target_reproduces_reference_raw_rate() -> None:
    reference = [row(True, language="english"), row(False, language="schinese")]
    comparison = [row(True, language="english"), row(True, language="schinese")]
    report = standardize_populations(reference, comparison, variables=["language"], target="reference")
    standardization = report["standardization"]
    assert standardization["reference_standardized_rate"] == report["raw"]["reference_rate"]


def test_pooled_target_is_separate_from_reference_target() -> None:
    reference = [row(True, language="english") for _ in range(3)] + [row(False, language="schinese")]
    comparison = [row(False, language="english")] + [row(True, language="schinese") for _ in range(3)]
    reference_target = standardize_populations(reference, comparison, variables=["language"], target="reference")
    pooled_target = standardize_populations(reference, comparison, variables=["language"], target="pooled")
    assert reference_target["standardization"]["target"] == "reference"
    assert pooled_target["standardization"]["target"] == "pooled"
    assert pooled_target["standardization"]["standardized_difference"] == 0.0
    assert reference_target["standardization"]["standardized_difference"] != pooled_target["standardization"]["standardized_difference"]


def test_single_dimension_sensitivity_contains_all_supported_dimensions() -> None:
    report = standardize_populations([row(True)], [row(False)])
    table = report["single_dimension_sensitivity"]
    assert [item["dimension"] for item in table] == list(SUPPORTED_VARIABLES)
    assert all("status" in item for item in table)
    assert table[0]["status"] == "complete"


def test_explicit_joint_standardization_records_requested_variables() -> None:
    reference = [row(True, language="english", playtime=60), row(False, language="schinese", playtime=6000)]
    comparison = [row(False, language="english", playtime=60), row(True, language="schinese", playtime=6000)]
    report = standardize_populations(reference, comparison, variables=["language", "playtime_cohort"])
    assert report["standardization"]["variables"] == ["language", "playtime_cohort"]
    assert all("reference_n" in item and "comparison_n" in item for item in report["standardization"]["strata"])


def test_unsupported_target_stratum_is_not_renormalized() -> None:
    reference = [row(True, language="english"), row(False, language="schinese")]
    comparison = [row(False, language="english"), row(False, language="english")]
    report = standardize_populations(reference, comparison, variables=["language"])
    standardization = report["standardization"]
    assert standardization["status"] == "incomplete_support"
    assert standardization["support"]["unsupported_target_mass"] == 0.5
    assert "schinese" in standardization["support"]["unsupported_strata"]
    assert standardization["comparison_standardized_rate"] is None
    assert standardization["common_support_only"]["target_mass"] == 0.5


def test_missing_covariate_is_explicit_stratum_and_reported() -> None:
    report = standardize_populations(
        [row(True, language=None), row(False, language="english")],
        [row(False, language=None), row(True, language="english")],
        variables=["language"],
    )
    standardization = report["standardization"]
    assert "__missing__" in {item["stratum"] for item in standardization["strata"]}
    assert standardization["missing_covariate"]["reference"]["missing_covariate_n"] == 1
    assert standardization["missing_covariate"]["comparison"]["missing_covariate_share"] == 0.5
    assert "missing-not-at-random" in standardization["missing_covariate"]["limitation"]


def test_missing_outcome_with_target_mass_is_unsupported() -> None:
    report = standardize_populations(
        [row(True, language="english")],
        [row(None, language="english")],
        variables=["language"],
    )
    assert report["standardization"]["status"] == "incomplete_support"
    assert report["standardization"]["comparison_standardized_rate"] is None
    assert report["standardization"]["strata"][0]["comparison_outcome_valid_n"] == 0


def test_outcome_changes_do_not_change_weights() -> None:
    reference = [row(True, language="english"), row(False, language="schinese")]
    comparison = [row(True, language="english"), row(False, language="english"), row(True, language="schinese")]
    changed = [row(False, language="english"), row(True, language="english"), row(False, language="schinese")]
    first = standardize_populations(reference, comparison, variables=["language"])
    second = standardize_populations(reference, changed, variables=["language"])
    assert first["weights"] == second["weights"]


def test_raw_difference_uses_comparison_minus_reference() -> None:
    report = standardize_populations([row(True)], [row(False)], variables=["language"])
    assert report["raw"]["difference"] == -1.0
    assert report["raw"]["difference_percentage_points"] == -100.0


def test_direction_reversal_is_detected_without_causal_language() -> None:
    reference = [row(True, language="english") for _ in range(4)] + [row(False, language="english") for _ in range(4)] + [row(True, language="schinese") for _ in range(2)]
    comparison = [row(False, language="english") for _ in range(2)] + [row(True, language="schinese") for _ in range(7)] + [row(False, language="schinese")]
    report = standardize_populations(reference, comparison, variables=["language"])
    assert report["standardization"]["direction_reversal_after_standardization"] is True
    assert report["interpretation"]["descriptive_sensitivity_only"] is True
    assert report["interpretation"]["not_causal_adjustment"] is True


def test_direction_reversal_fixture() -> None:
    reference = [row(True, language="english") for _ in range(4)] + [row(False, language="english") for _ in range(4)] + [row(True, language="schinese") for _ in range(2)]
    comparison = [row(False, language="english") for _ in range(2)] + [row(True, language="schinese") for _ in range(7)] + [row(False, language="schinese")]
    report = standardize_populations(reference, comparison, variables=["language"])
    assert report["raw"]["difference"] == pytest.approx(0.1)
    assert report["standardization"]["standardized_difference"] == pytest.approx(-0.425)
    assert report["standardization"]["direction_reversal_after_standardization"] is True


def test_incomplete_acquisition_is_propagated() -> None:
    report = standardize_populations(
        [row(True)],
        [row(False)],
        comparison_metadata=metadata(complete=False),
        variables=["language"],
    )
    assert report["acquisition_limited"] is True
    assert report["standardization"]["acquisition_limited"] is True


def test_reviewer_selection_limitation_is_explicit() -> None:
    report = standardize_populations([row(True)], [row(False)], variables=["language"])
    assert report["interpretation"]["reviewer_selection_bias"] is True
    assert report["comparison_context"]["reviewer_selection_bias"] is True
    assert "self-selected" in report["interpretation"]["limitation"]


def test_unavailable_adjustment_dimension_does_not_fabricate_result() -> None:
    report = standardize_populations(
        [row(True, language=None)],
        [row(False, language=None)],
        variables=["language"],
    )
    assert report["standardization"]["status"] == "unavailable"
    assert report["standardization"]["standardized_difference"] is None


def test_standardized_interval_is_not_borrowed_from_raw_interval() -> None:
    report = standardize_populations([row(True)], [row(False)], variables=["language"])
    assert report["standardized_interval"] is None
    assert report["uncertainty_status"] == "uncertainty_not_implemented_for_standardized_estimator"


def test_report_is_deterministic_and_json_serializable() -> None:
    reference = [row(True, language="english"), row(False, language="schinese")]
    comparison = [row(False, language="english"), row(True, language="schinese")]
    first = json.dumps(standardize_populations(reference, comparison, variables=["language"]), sort_keys=True)
    second = json.dumps(standardize_populations(reference, comparison, variables=["language"]), sort_keys=True)
    assert first == second
