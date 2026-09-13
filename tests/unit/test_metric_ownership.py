"""Stage 2P.1 ownership-audit compatibility checks."""
from __future__ import annotations

import json

from apps.api.senti_next.analysis import build_reviews_dataframe, recommendation_rate, summarize_sentiment
from apps.api.senti_next.metric_ownership import (
    CANONICAL_SOURCE_CHECKS,
    DEPRECATED_CANDIDATE,
    LEGACY_COMPAT,
    METRIC_OWNERSHIP_REGISTRY,
    RESEARCH_REPORT_CONTRACT,
    RESEARCH_CORE,
    SEMANTIC_LAYER,
    validate_canonical_sources,
    validate_ownership_registry,
)
from apps.api.senti_next.population_validity import PLAYTIME_COHORTS


def _by_id() -> dict[str, dict]:
    return {entry["metric_id"]: entry for entry in METRIC_OWNERSHIP_REGISTRY}


def test_registry_is_deterministic_and_valid():
    first = json.dumps(list(METRIC_OWNERSHIP_REGISTRY), ensure_ascii=False, sort_keys=True)
    second = json.dumps(list(METRIC_OWNERSHIP_REGISTRY), ensure_ascii=False, sort_keys=True)
    assert first == second
    assert validate_ownership_registry() == []


def test_registry_entries_have_required_fields():
    required = {"metric_id", "current_source", "future_owner", "status", "canonical_name", "semantic_definition", "notes"}
    assert METRIC_OWNERSHIP_REGISTRY
    assert all(required <= set(entry) for entry in METRIC_OWNERSHIP_REGISTRY)


def test_recommendation_rate_is_research_core_and_legacy_positive_is_compat():
    entries = _by_id()
    assert entries["stage2b.recommendation_rate"]["future_owner"] == RESEARCH_CORE
    assert entries["stage2b.recommendation_rate"]["canonical_name"] == "recommendation_rate"
    assert entries["legacy.share_positive"]["future_owner"] == LEGACY_COMPAT
    assert entries["legacy.share_positive"]["replacement_metric"] == "stage2b.recommendation_rate"
    assert "text sentiment" in entries["legacy.share_positive"]["semantic_definition"]


def test_legacy_playtime_buckets_are_not_canonical():
    entries = _by_id()
    assert [label for label, _, _ in PLAYTIME_COHORTS] == ["0–2h", "2–10h", "10–30h", "30–100h", "100h+"]
    assert entries["legacy.playtime_buckets"]["future_owner"] == LEGACY_COMPAT
    assert entries["legacy.playtime_buckets"]["replacement_metric"] == "stage2a.playtime_at_review_composition"


def test_playtime_at_review_and_playtime_forever_are_distinct():
    entries = _by_id()
    at_review = entries["stage2a.playtime_at_review_composition"]
    lifetime = entries["legacy.playtime_forever_summary"]
    assert at_review["future_owner"] == RESEARCH_CORE
    assert at_review["canonical_name"] == "playtime_at_review_cohort_composition"
    assert lifetime["status"] == LEGACY_COMPAT
    assert lifetime["future_owner"] == RESEARCH_CORE
    assert lifetime["replacement_metric"] is None
    assert entries["presentation.playtime"]["replacement_metric"] is None
    assert "Do not substitute" in lifetime["notes"]


def test_version_legacy_migration_directions_are_correct():
    entries = _by_id()
    for metric_id, replacement in (
        ("version.playtime_buckets", "stage2a.playtime_at_review_composition"),
        ("version.purchase_segmentation", "stage2a.purchase_composition"),
    ):
        assert entries[metric_id]["status"] == LEGACY_COMPAT
        assert entries[metric_id]["future_owner"] == RESEARCH_CORE
        assert entries[metric_id]["replacement_metric"] == replacement


def test_negative_recommendation_rate_is_canonical_and_preserves_units():
    entries = _by_id()
    rate = entries["stage2b.not_recommended_rate"]
    assert rate["future_owner"] == RESEARCH_CORE
    assert rate["canonical_name"] == "not_recommended_rate"
    assert "not_recommended_n / valid_n" in rate["formula"]
    assert entries["legacy.share_negative"]["replacement_metric"] == "stage2b.not_recommended_rate"
    assert entries["legacy.share_negative"]["replacement_metric"] != "stage2b.not_recommended_n"


def test_heuristic_risk_and_core_fan_are_deprecated_candidates():
    entries = _by_id()
    for metric_id in ("heuristic.refund_risk_index", "heuristic.core_fan_disappointment"):
        assert entries[metric_id]["future_owner"] == DEPRECATED_CANDIDATE
        assert entries[metric_id]["empirical_validation"] == "none; requires validated player-segment ground truth" or entries[metric_id]["empirical_validation"] == "none; requires refund-linked ground truth"
        assert entries[metric_id]["formula"]
        assert entries[metric_id]["inputs"]


def test_stage2_precedence_and_layer_ownership():
    entries = _by_id()
    assert entries["presentation.recommendation"]["replacement_metric"] == "stage2b.recommendation_rate"
    assert entries["presentation.metric_provenance"]["future_owner"] == RESEARCH_CORE
    assert entries["stage2c.composition_standardization"]["future_owner"] == RESEARCH_CORE
    assert entries["stage2d.window_robustness"]["future_owner"] == RESEARCH_CORE
    assert entries["stage2e.coordinated_expression"]["future_owner"] == RESEARCH_CORE
    assert entries["stage2d.window_robustness"]["current_source"] == "window_robustness.matched_window_robustness"
    for metric_id in ("semantic.topic", "semantic.issue", "semantic.request"):
        assert entries[metric_id]["future_owner"] == SEMANTIC_LAYER


def test_source_integrity_checks_resolve():
    assert CANONICAL_SOURCE_CHECKS
    assert validate_canonical_sources() == []


def test_source_integrity_rejects_registry_source_mismatch():
    registry = [dict(entry) for entry in METRIC_OWNERSHIP_REGISTRY]
    target = next(entry for entry in registry if entry["metric_id"] == "stage2d.window_robustness")
    target["current_source"] = "window_robustness.some_wrong_function"
    errors = validate_canonical_sources(registry)
    assert any("stage2d.window_robustness registry source mismatch" in error for error in errors)


def test_player_segments_are_mixed_not_one_research_core_block():
    entries = _by_id()
    assert "presentation.player_segments" not in entries
    assert entries["presentation.player_segments.population_counts"]["future_owner"] == RESEARCH_CORE
    assert entries["presentation.player_segments.recommendation_rates"]["future_owner"] == RESEARCH_CORE
    assert entries["presentation.player_segments.issue_counts"]["future_owner"] == SEMANTIC_LAYER
    assert entries["presentation.player_segments.top_issues"]["future_owner"] == SEMANTIC_LAYER


def test_known_semantic_fields_cannot_be_research_core_owned():
    entries = _by_id()
    for metric_id in ("semantic.issue_count", "semantic.top_issues", "semantic.topic", "semantic.request", "semantic.evidence", "semantic.aspect_sentiment"):
        assert entries[metric_id]["future_owner"] == SEMANTIC_LAYER


def test_legacy_version_temporal_outputs_are_transitional():
    entries = _by_id()
    for metric_id in ("version.period_assignment", "version.recommendation_rate", "version.daily_review_volume"):
        assert entries[metric_id]["status"] == LEGACY_COMPAT
        assert entries[metric_id]["future_owner"] == RESEARCH_CORE
    assert entries["version.period_assignment"]["replacement_metric"] == "stage2d.window_robustness"
    assert entries["version.daily_review_volume"]["replacement_metric"] == "stage2e.review_activity"


def test_comparison_contract_distinguishes_limited_descriptive_metrics():
    comparison = RESEARCH_REPORT_CONTRACT["comparison"]
    assert "may be reported" in comparison["descriptive_observed_population"]
    assert "sufficient verified" in comparison["coverage_dependent"]
    assert "never" in comparison["incomplete_provenance"]


def test_audit_does_not_change_existing_stage1_numerical_behavior():
    frame = build_reviews_dataframe([
        {"recommendationid": "r1", "review": "up", "voted_up": True, "timestamp_created": 1, "timestamp_updated": 1, "author": {}},
        {"recommendationid": "r2", "review": "down", "voted_up": False, "timestamp_created": 2, "timestamp_updated": 2, "author": {}},
    ])
    assert recommendation_rate(frame) == 0.5
    summary = summarize_sentiment(frame)
    assert summary["share_positive"] == 0.5
    assert summary["share_negative"] == 0.5
    # The audit is declarative: importing the registry cannot change the frame.
    assert list(frame["review_id"]) == ["r1", "r2"]
