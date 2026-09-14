from __future__ import annotations

from apps.api.senti_next.research_comparison import (
    build_comparison_side,
    build_research_comparison,
    build_research_comparison_for_runs,
    build_version_window_comparison,
)


def _report(rate: float, population: int, *, languages=None, review_type="all", purchase_type="all", start=None, end=None):
    valid = population
    recommended = round(population * rate)
    return {
        "population": {
            "review_count": population,
            "sampling_contract": {
                "start_time": start,
                "end_time": end,
                "languages": languages or ["english"],
                "review_type": review_type,
                "purchase_type": purchase_type,
                "collection_order": "recent",
                "include_offtopic_activity": False,
                "max_reviews": population,
            },
            "coverage_status": "complete",
        },
        "recommendation": {
            "population": {
                "valid_n": valid,
                "recommended_n": recommended,
                "not_recommended_n": valid - recommended,
                "recommendation_rate": rate,
            }
        },
    }


def _semantic(*, bundle="bundle-1", taxonomy="tax-fp", provider="deepseek", model="model-1", prompt="prompt-1", schema="schema-1", claim="PROVISIONAL"):
    return {
        "claim_status": claim,
        "population_n": 100,
        "classified_n": 80,
        "classification_coverage": 0.8,
        "provenance": {
            "measurement_bundle_id": bundle,
            "taxonomy_fingerprint": taxonomy,
            "classifier_provider": provider,
            "classifier_model_id": model,
            "classifier_prompt_version": prompt,
            "classifier_schema_version": schema,
            "measurement_status": claim,
            "validation_status": "PASS" if claim == "VALIDATED" else "UNAVAILABLE",
        },
        "topics": [
            {"taxonomy_key": "gameplay/balance", "topic_n": 20, "topic_share": 0.25, "issue_n": 10, "issue_share": 0.125, "request_n": 4, "request_share": 0.05, "primary_n": 12, "primary_share": 0.15},
        ],
        "semantic_measurement_result_fingerprint": "semantic-fp",
    }


def _side(run_id: str, rate: float, *, report=None, semantic=None, **provenance):
    return build_comparison_side(
        source_kind="analysis_run",
        source_id=run_id,
        app_id=553850,
        research_report=report or _report(rate, 100),
        semantic_result=semantic,
        provenance=provenance,
    )


def test_exact_quantitative_sides_and_percentage_point_delta():
    result = build_research_comparison(_side("left", 0.70), _side("right", 0.75))
    assert result["schema_version"] == "research-comparison-v1"
    assert result["left"]["quantitative"]["recommendation_rate"] == 0.70
    assert result["right"]["quantitative"]["recommendation_rate"] == 0.75
    assert result["quantitative"]["recommendation_rate_delta_pp"] == 5.0


def test_raw_input_is_not_an_official_metric_source():
    left = _side("left", 0.70)
    right = _side("right", 0.75)
    first = build_research_comparison(left, right)
    left["legacy_reviews"] = [{"voted_up": False}] * 1000
    right["legacy_reviews"] = [{"voted_up": True}] * 1000
    second = build_research_comparison(left, right)
    assert second["quantitative"] == first["quantitative"]


def test_semantic_delta_requires_full_identity_equivalence():
    base = dict(bundle="bundle-1", taxonomy="tax-1", provider="p", model="m", prompt="pr", schema="s")
    same = build_research_comparison(_side("a", 0.7, semantic=_semantic(**base)), _side("b", 0.75, semantic=_semantic(**base)))
    assert same["compatibility"]["semantic_delta_comparable"] is True
    assert same["semantic"]["delta"]["topics"][0]["delta_pp"] == 0.0
    for key, value in (("bundle", "bundle-2"), ("taxonomy", "tax-2"), ("provider", "other"), ("model", "other-model"), ("prompt", "prompt-2"), ("schema", "schema-2")):
        changed = dict(base)
        changed[key] = value
        result = build_research_comparison(_side("a", 0.7, semantic=_semantic(**base)), _side("b", 0.75, semantic=_semantic(**changed)))
        assert result["compatibility"]["semantic_delta_comparable"] is False
        assert result["semantic"]["delta"] is None


def test_missing_semantic_side_keeps_quantitative_comparison_available():
    result = build_research_comparison(_side("a", 0.7, semantic=_semantic()), _side("b", 0.75))
    assert result["compatibility"]["quantitative_comparable"] is True
    assert result["compatibility"]["semantic_side_by_side_available"] is True
    assert result["compatibility"]["semantic_delta_comparable"] is False
    assert "semantic_missing_one_side" in result["compatibility"]["reasons"]


def test_sampling_mismatch_and_version_window_difference_are_distinct():
    same_method = build_research_comparison(
        _side("a", 0.7, report=_report(0.7, 100, start="2026-01-01", end="2026-01-07")),
        _side("b", 0.75, report=_report(0.75, 100, start="2026-02-01", end="2026-02-07")),
    )
    assert same_method["compatibility"]["sampling_method_equivalent"] is True
    assert same_method["compatibility"]["scope_equivalent"] is False
    assert "time_window_different_by_design" in same_method["compatibility"]["reasons"]
    mismatch = build_research_comparison(
        _side("a", 0.7, report=_report(0.7, 100, languages=["english"])),
        _side("b", 0.75, report=_report(0.75, 100, languages=["japanese"])),
    )
    assert mismatch["compatibility"]["sampling_method_equivalent"] is False
    assert "sampling_languages_mismatch" in mismatch["compatibility"]["reasons"]


def test_semantic_denominators_are_side_specific():
    left_semantic = _semantic() | {"population_n": 100, "classified_n": 80}
    right_semantic = _semantic() | {"population_n": 200, "classified_n": 100}
    left_semantic["topics"][0] = {"taxonomy_key": "gameplay/balance", "topic_n": 20, "topic_share": 0.25}
    right_semantic["topics"][0] = {"taxonomy_key": "gameplay/balance", "topic_n": 30, "topic_share": 0.30}
    result = build_research_comparison(
        _side("a", 0.7, report=_report(0.7, 100), semantic=left_semantic),
        _side("b", 0.75, report=_report(0.75, 200), semantic=right_semantic),
    )
    row = result["semantic"]["delta"]["topics"][0]
    assert row["left_n"] == 20 and row["right_n"] == 30
    assert row["left_share"] == 0.25 and row["right_share"] == 0.30
    assert row["delta_pp"] == 5.0


def test_version_window_adapter_uses_persisted_values_and_shared_shape():
    result = build_version_window_comparison(
        run_id="version-run",
        app_id=42,
        left={"reviews": 100, "recommendation_rate": 0.70, "coverage_status": "COMPLETE"},
        right={"reviews": 100, "recommendation_rate": 0.75, "coverage_status": "COMPLETE"},
    )
    assert result["schema_version"] == "research-comparison-v1"
    assert result["left"]["source_kind"] == "version_window"
    assert result["quantitative"]["recommendation_rate_delta_pp"] == 5.0


def test_exact_run_side_isolation_never_reads_latest_mutable_result(monkeypatch):
    runs = {
        "run-a": {"target_app_id": 1, "provider": "p", "model_id": "m", "prompt_version": "pr", "analysis_version": "s"},
        "run-b": {"target_app_id": 2, "provider": "p", "model_id": "m", "prompt_version": "pr", "analysis_version": "s"},
        "run-c": {"target_app_id": 3, "provider": "p", "model_id": "m", "prompt_version": "pr", "analysis_version": "s"},
    }
    results = {
        "run-a": {"app_id": 1, "research_report": _report(0.70, 100), "metadata": {"population_fingerprint": "a"}},
        "run-b": {"app_id": 2, "research_report": _report(0.75, 100), "metadata": {"population_fingerprint": "b"}},
        "run-c": {"app_id": 3, "research_report": _report(0.01, 100), "metadata": {"population_fingerprint": "c"}},
    }
    monkeypatch.setattr("apps.api.senti_next.research_comparison.storage.get_analysis_run", lambda run_id: runs.get(run_id))
    monkeypatch.setattr("apps.api.senti_next.research_comparison.storage.get_analysis_run_result", lambda run_id: results.get(run_id))
    first = build_research_comparison_for_runs("run-a", "run-b")
    results["run-c"]["research_report"] = _report(0.99, 100)
    second = build_research_comparison_for_runs("run-a", "run-b")
    assert second == first
    assert second["left"]["source_id"] == "run-a"
    assert second["right"]["source_id"] == "run-b"
