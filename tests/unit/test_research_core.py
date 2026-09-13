"""Stage 2P.2 Research Core orchestration tests."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import inspect
import json
import subprocess
import sys

from apps.api.senti_next.activity_diagnostics import analyze_review_activity
from apps.api.senti_next.population_validity import compare_populations
from apps.api.senti_next.rate_inference import calculate_recommendation_rate, compare_recommendation_rates
from apps.api.senti_next.research_core import (
    build_comparison_research_report,
    build_snapshot_research_report,
)
from apps.api.senti_next.standardization import standardize_populations
from apps.api.senti_next.window_robustness import matched_window_robustness


REFERENCE_ANCHOR = 1_700_000_000.0
COMPARISON_ANCHOR = 1_700_100_000.0


def _metadata(anchor: float, *, complete: bool = True) -> dict:
    return {
        "collection_complete": complete,
        "truncated_by_max_reviews": False,
        "stop_reason": "end_of_results" if complete else "api_failure",
        "coverage_start_time": anchor - 14 * 86_400,
        "coverage_end_time": anchor + 14 * 86_400,
        "coverage_status": "complete" if complete else "incomplete",
        "coverage_end_inclusive": False,
        "sampling_contract": {
            "app_id": 123,
            "start_time": anchor - 14 * 86_400,
            "end_time": anchor + 14 * 86_400,
            "languages": ["english", "schinese"],
            "max_reviews": 100,
        },
    }


def _population(anchor: float, prefix: str) -> list[dict]:
    rows = []
    outcomes = [True, False, True, False]
    languages = ["english", "schinese", "english", "schinese"]
    playtime = [30, 180, 1_200, 4_000]
    for index, (day, voted_up, language, minutes) in enumerate(zip((0, 1, 5, 10), outcomes, languages, playtime)):
        rows.append(
            {
                "recommendationid": f"{prefix}-{index}",
                "review": f"{prefix} review with enough distinct text {index}",
                "timestamp_created": anchor + day * 86_400,
                "timestamp_updated": anchor + day * 86_400,
                "voted_up": voted_up,
                "language": language,
                "steam_purchase": index % 2 == 0,
                "received_for_free": index == 3,
                "written_during_early_access": index == 0,
                "primarily_steam_deck": index == 2,
                "author": {
                    "steamid": f"author-{prefix}-{index}",
                    "playtime_at_review": minutes,
                    "playtime_forever": minutes + 500,
                },
            }
        )
    return rows


def test_snapshot_report_schema_and_unavailable_comparison_sections():
    population = _population(REFERENCE_ANCHOR, "snapshot")
    report = build_snapshot_research_report(population, metadata=_metadata(REFERENCE_ANCHOR))
    assert report["schema_version"] == "research-report-v1"
    assert report["mode"] == "snapshot"
    assert report["population"]["review_count"] == len(population)
    assert report["comparability"] == {"status": "unavailable", "reason": "comparison_required"}
    assert report["standardization"] == {"status": "unavailable", "reason": "comparison_required"}
    assert report["window_robustness"] == {"status": "unavailable", "reason": "comparison_required"}
    assert report["orchestration"]["stages_executed"] == ["2B", "2E"]
    assert report["orchestration"]["stages_unavailable"]["2A"] == "comparison_required"


def test_snapshot_direct_stage_parity():
    population = _population(REFERENCE_ANCHOR, "snapshot")
    metadata = _metadata(REFERENCE_ANCHOR)
    report = build_snapshot_research_report(population, metadata=metadata, activity_grain="day")
    assert report["recommendation"] == calculate_recommendation_rate(population, metadata=metadata, confidence_level=0.95)
    assert report["activity"] == analyze_review_activity(population, grain="day")


def test_comparison_report_schema_and_direct_stage_parity():
    reference = _population(REFERENCE_ANCHOR, "reference")
    comparison = _population(COMPARISON_ANCHOR, "comparison")
    reference_metadata = _metadata(REFERENCE_ANCHOR)
    comparison_metadata = _metadata(COMPARISON_ANCHOR)
    report = build_comparison_research_report(
        reference,
        comparison,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        reference_anchor=REFERENCE_ANCHOR,
        comparison_anchor=COMPARISON_ANCHOR,
        standardization_variables=("language",),
        standardization_target="reference",
        windows_days=(3, 7, 14),
    )
    direct_2a = compare_populations(reference, comparison, reference_metadata, comparison_metadata)
    direct_2b = compare_recommendation_rates(
        reference,
        comparison,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        confidence_level=0.95,
        comparability_report=direct_2a,
    )
    direct_2c = standardize_populations(
        reference,
        comparison,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        comparability_report=direct_2a,
        variables=("language",),
        target="reference",
    )
    direct_2d = matched_window_robustness(
        reference,
        comparison,
        REFERENCE_ANCHOR,
        COMPARISON_ANCHOR,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        comparability_report=direct_2a,
        windows_days=(3, 7, 14),
        standardization_variables=("language",),
        events=None,
    )
    assert report["schema_version"] == "research-report-v1"
    assert report["mode"] == "comparison"
    assert report["comparability"] == direct_2a
    assert report["recommendation"] == direct_2b
    assert report["standardization"] == direct_2c
    assert report["window_robustness"] == direct_2d
    assert report["activity"]["reference"] == analyze_review_activity(reference, grain="day")
    assert report["activity"]["comparison"] == analyze_review_activity(comparison, grain="day")
    assert report["orchestration"]["stages_executed"] == ["2A", "2B", "2C", "2D", "2E"]
    assert report["orchestration"]["configuration"]["standardization_variables"] == ["language"]


def test_non_default_confidence_is_propagated_to_every_window_and_matches_direct_stage_2d():
    reference = _population(REFERENCE_ANCHOR, "reference")
    comparison = _population(COMPARISON_ANCHOR, "comparison")
    reference_metadata = _metadata(REFERENCE_ANCHOR)
    comparison_metadata = _metadata(COMPARISON_ANCHOR)
    report = build_comparison_research_report(
        reference,
        comparison,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        reference_anchor=REFERENCE_ANCHOR,
        comparison_anchor=COMPARISON_ANCHOR,
        confidence_level=0.90,
        standardization_variables=("language",),
        windows_days=(3, 7, 14),
    )
    direct = matched_window_robustness(
        reference,
        comparison,
        REFERENCE_ANCHOR,
        COMPARISON_ANCHOR,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        windows_days=(3, 7, 14),
        standardization_variables=("language",),
        standardization_target="reference",
        confidence_level=0.90,
    )
    assert report["window_robustness"] == direct
    assert report["orchestration"]["configuration"]["confidence_level"] == 0.90
    for window in report["window_robustness"]["windows"].values():
        if window["recommendation"]["reference_wilson_interval"] is not None:
            assert window["recommendation"]["reference_wilson_interval"]["confidence_level"] == 0.90
            assert window["recommendation"]["comparison_wilson_interval"]["confidence_level"] == 0.90
            assert window["recommendation"]["newcombe_difference_interval"]["confidence_level"] == 0.90


def test_pooled_standardization_target_is_visible_in_top_level_and_each_window():
    report = build_comparison_research_report(
        _population(REFERENCE_ANCHOR, "reference"),
        _population(COMPARISON_ANCHOR, "comparison"),
        reference_metadata=_metadata(REFERENCE_ANCHOR),
        comparison_metadata=_metadata(COMPARISON_ANCHOR),
        reference_anchor=REFERENCE_ANCHOR,
        comparison_anchor=COMPARISON_ANCHOR,
        standardization_variables=("language",),
        standardization_target="pooled",
        windows_days=(3, 7),
    )
    assert report["standardization"]["standardization"]["target"] == "pooled"
    assert report["window_robustness"]["configuration"]["standardization_target"] == "pooled"
    for window in report["window_robustness"]["windows"].values():
        assert window["standardization"]["target"] == "pooled"


def test_research_core_resolves_stage_2c_default_variables_for_stage_2d():
    report = build_comparison_research_report(
        _population(REFERENCE_ANCHOR, "reference"),
        _population(COMPARISON_ANCHOR, "comparison"),
        reference_metadata=_metadata(REFERENCE_ANCHOR),
        comparison_metadata=_metadata(COMPARISON_ANCHOR),
        reference_anchor=REFERENCE_ANCHOR,
        comparison_anchor=COMPARISON_ANCHOR,
        standardization_variables=None,
        windows_days=(3, 7),
    )
    configuration = report["orchestration"]["configuration"]
    assert configuration["requested_standardization_variables"] is None
    assert configuration["effective_standardization_variables"] == ["language"]
    assert report["window_robustness"]["configuration"]["standardization_variables"] == ["language"]
    assert report["window_robustness"]["robustness"]["standardized"] is not None


def test_combined_non_default_configuration_has_exact_stage_2d_parity():
    reference = _population(REFERENCE_ANCHOR, "reference")
    comparison = _population(COMPARISON_ANCHOR, "comparison")
    reference_metadata = _metadata(REFERENCE_ANCHOR)
    comparison_metadata = _metadata(COMPARISON_ANCHOR)
    variables = ("language", "playtime_cohort")
    report = build_comparison_research_report(
        reference,
        comparison,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        reference_anchor=REFERENCE_ANCHOR,
        comparison_anchor=COMPARISON_ANCHOR,
        confidence_level=0.90,
        standardization_variables=variables,
        standardization_target="pooled",
        windows_days=(3, 7),
    )
    direct = matched_window_robustness(
        reference,
        comparison,
        REFERENCE_ANCHOR,
        COMPARISON_ANCHOR,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        windows_days=(3, 7),
        standardization_variables=variables,
        standardization_target="pooled",
        confidence_level=0.90,
    )
    assert report["window_robustness"] == direct
    configuration = report["orchestration"]["configuration"]
    assert configuration["confidence_level"] == 0.90
    assert configuration["requested_standardization_variables"] == list(variables)
    assert configuration["effective_standardization_variables"] == list(variables)
    assert configuration["standardization_target"] == "pooled"
    assert configuration["windows_days"] == [3, 7]


def test_missing_anchors_are_explicitly_unavailable():
    report = build_comparison_research_report(
        _population(REFERENCE_ANCHOR, "reference"),
        _population(COMPARISON_ANCHOR, "comparison"),
        reference_metadata=_metadata(REFERENCE_ANCHOR),
        comparison_metadata=_metadata(COMPARISON_ANCHOR),
    )
    assert report["window_robustness"] == {"status": "unavailable", "reason": "lifecycle_anchors_required"}
    assert report["orchestration"]["stages_unavailable"] == {"2D": "lifecycle_anchors_required"}
    assert report["orchestration"]["stages_executed"] == ["2A", "2B", "2C", "2E"]


def test_incomplete_acquisition_is_not_upgraded():
    reference = _population(REFERENCE_ANCHOR, "reference")
    comparison = _population(COMPARISON_ANCHOR, "comparison")
    report = build_comparison_research_report(
        reference,
        comparison,
        reference_metadata=_metadata(REFERENCE_ANCHOR, complete=False),
        comparison_metadata=_metadata(COMPARISON_ANCHOR),
        reference_anchor=REFERENCE_ANCHOR,
        comparison_anchor=COMPARISON_ANCHOR,
    )
    assert report["recommendation"]["reference"]["recommendation_rate"] is not None
    assert report["recommendation"]["inference_validity"]["reference"]["inference_eligibility"] == "limited"
    assert report["limitations"]["acquisition_limited"] is True
    assert all(window["status"] != "complete" for window in report["window_robustness"]["windows"].values())


def test_empty_snapshot_is_json_safe_and_has_no_fake_comparison():
    report = build_snapshot_research_report([], metadata=None)
    encoded = json.dumps(report, sort_keys=True, allow_nan=False)
    assert encoded
    assert report["population"]["review_count"] == 0
    assert report["recommendation"]["population"]["recommendation_rate"] is None
    assert report["comparability"]["status"] == "unavailable"


def test_comparison_with_empty_population_preserves_stage_semantics():
    report = build_comparison_research_report(
        [],
        _population(COMPARISON_ANCHOR, "comparison"),
        reference_metadata=None,
        comparison_metadata=_metadata(COMPARISON_ANCHOR),
    )
    assert report["recommendation"]["reference"]["recommendation_rate"] is None
    assert report["recommendation"]["difference"]["difference"] is None


def test_input_populations_are_not_mutated_and_report_is_deterministic():
    reference = _population(REFERENCE_ANCHOR, "reference")
    comparison = _population(COMPARISON_ANCHOR, "comparison")
    before_reference = deepcopy(reference)
    before_comparison = deepcopy(comparison)
    kwargs = {
        "reference_metadata": _metadata(REFERENCE_ANCHOR),
        "comparison_metadata": _metadata(COMPARISON_ANCHOR),
        "reference_anchor": REFERENCE_ANCHOR,
        "comparison_anchor": COMPARISON_ANCHOR,
        "standardization_variables": ("language",),
    }
    first = build_comparison_research_report(reference, comparison, **kwargs)
    second = build_comparison_research_report(reference, comparison, **kwargs)
    assert reference == before_reference
    assert comparison == before_comparison
    assert json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(second, sort_keys=True, allow_nan=False)


def test_no_dataframe_semantic_or_llm_dependencies():
    import apps.api.senti_next.research_core as research_core

    source = inspect.getsource(research_core)
    assert "build_reviews_dataframe" not in source
    assert ".llm" not in source
    assert ".providers" not in source
    assert ".routes" not in source
    assert "prepare_insights" not in source
    report = build_snapshot_research_report(_population(REFERENCE_ANCHOR, "snapshot"))
    encoded = json.dumps(report, sort_keys=True, allow_nan=False)
    assert encoded
    keys: set[str] = set()

    def collect_keys(value):
        if isinstance(value, dict):
            keys.update(str(key).lower() for key in value)
            for child in value.values():
                collect_keys(child)
        elif isinstance(value, list):
            for child in value:
                collect_keys(child)

    collect_keys(report)
    assert not keys.intersection({"semantic", "topic", "issue", "request", "top_issues", "aspect_sentiment", "llm"})


def test_research_core_import_does_not_load_forbidden_modules():
    code = (
        "import sys; import apps.api.senti_next.research_core; "
        "print([name for name in sys.modules if name.startswith('apps.api.senti_next.') "
        "and (name.endswith('.llm') or name.endswith('.providers') or name.endswith('.routes'))])"
    )
    completed = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert completed.stdout.strip() == "[]"
