"""P0.3b metric denominator and provenance contract tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next.insights import prepare_insights
from senti_next.metric_provenance import (
    build_cohort_metric_observation,
    build_metric_provenance,
    formal_metric_denominator,
)


def make_frame() -> pd.DataFrame:
    rows = []
    for index in range(10):
        rows.append({
            "review_id": str(index),
            "voted_up": index < 7,
            "author_playtime_forever": 60 * (100 if index < 5 else 10),
            "author_playtime_last_two_weeks": 60,
            "author_playtime_at_review": 60,
            "author_num_games_owned": 10,
            "author_num_reviews": 5,
            "steam_purchase": True,
            "received_for_free": False,
            "written_during_early_access": False,
            "primarily_steam_deck": False,
            "language": "english",
            "created_at": pd.Timestamp("2026-01-01") + pd.Timedelta(days=index),
            "votes_up": index,
            "votes_funny": 0,
            "weighted_vote_score": 0.5,
            "comment_count": 0,
            "timestamp_created": 1767225600 + index * 86400,
            "timestamp_updated": 1767225600 + index * 86400,
            "last_played_at": pd.Timestamp("2026-01-01"),
            "author_deck_playtime_at_review": 0,
            "author_last_played": 1767225600,
            "llm_label_origin": "llm" if index < 8 else ("rule_fallback" if index == 8 else "legacy"),
            "llm_validated": index < 8,
            "llm_issue_subcategories": ["technical/bugs"] if index in {0, 1, 2, 3} else [],
            "llm_request_subcategories": ["gameplay/mechanics"] if index in {0, 1} else [],
            "llm_subcategories": ["technical/bugs"] if index in {0, 1, 2, 3} else ["other/general"],
            "llm_subcategory_evidence": {"technical/bugs": ["crash"]} if index == 0 else {},
            "llm_has_aspects": index in {0, 1},
        })
    return pd.DataFrame(rows)


def test_raw_and_llm_metrics_use_their_own_denominators():
    observations = build_metric_provenance(make_frame(), run_id="run-a")
    assert observations["recommendation_rate"]["numerator"] == 7
    assert observations["recommendation_rate"]["denominator"] == 10
    assert observations["recommendation_rate"]["source_type"] == "raw_steam"
    assert observations["technical_issue_rate"]["numerator"] == 4
    assert observations["technical_issue_rate"]["denominator"] == 8
    assert observations["technical_issue_rate"]["value"] == 0.5
    assert observations["classification_coverage"]["value"] == 0.8
    assert observations["technical_issue_rate"]["run_id"] == "run-a"


def test_legacy_and_invalid_labels_are_not_formal_eligible():
    assert formal_metric_denominator([
        {"label_origin": "llm", "validated": True},
        {"label_origin": "legacy", "validated": None},
        {"label_origin": "rule_fallback", "validated": False},
        {"label_origin": "llm", "validated": False},
    ]) == 1


def test_cohort_uses_eligible_subgroup_denominator():
    frame = make_frame()
    observation = build_cohort_metric_observation(
        frame, "high_playtime", frame["author_playtime_forever"] >= 60 * 50, run_id="run-a"
    )
    assert observation["population_count"] == 5
    assert observation["denominator"] == 5
    assert observation["metric_id"] == "technical_issue_rate:high_playtime"


def test_evidence_population_is_explicitly_sampled():
    observation = build_metric_provenance(make_frame())["evidence_coverage"]
    assert observation["numerator"] == 2
    assert observation["population_count"] == 10
    assert observation["coverage"] == 0.2
    assert observation["is_sampled"] is True
    assert "not representative" in observation["sampling_semantics"]


def test_empty_denominator_is_unavailable_not_zero():
    frame = make_frame().iloc[8:9].copy()
    observation = build_metric_provenance(frame)["technical_issue_rate"]
    assert observation["denominator"] == 0
    assert observation["value"] is None
    assert observation["status"] == "unavailable"
    assert observation["unavailable_reason"] == "denominator_zero"


def test_prepare_insights_keeps_legacy_fields_and_adds_run_linked_contract():
    insights = prepare_insights(make_frame(), run_id="run-a")
    assert insights["llm"]["issue_rate"] == 0.5
    assert insights["llm"]["coverage_rate"] == 0.8
    assert insights["metric_provenance"]["recommendation_rate"]["value"] == 0.7
    assert insights["metric_provenance"]["technical_issue_rate"]["run_id"] == "run-a"
