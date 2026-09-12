"""Stage 2P.1 ownership-audit compatibility checks."""
from __future__ import annotations

import json

import pandas as pd

from apps.api.senti_next.analysis import build_reviews_dataframe, recommendation_rate, summarize_sentiment
from apps.api.senti_next.metric_ownership import (
    DEPRECATED_CANDIDATE,
    LEGACY_COMPAT,
    METRIC_OWNERSHIP_REGISTRY,
    RESEARCH_CORE,
    SEMANTIC_LAYER,
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
    assert entries["legacy.playtime_buckets"]["replacement_metric"] == "stage2a.playtime_cohort"


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
    for metric_id in ("semantic.topic", "semantic.issue", "semantic.request"):
        assert entries[metric_id]["future_owner"] == SEMANTIC_LAYER


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
