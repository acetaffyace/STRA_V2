"""Seed synthetic, no-raw-review browser fixtures for Stage 4D.1 QA.

The fixture is intentionally local-only.  It reuses the Stage 4C fixture for
the left HELLDIVERS 2 run, adds a second exact general run, and creates a
persisted Version Review V2 compatibility payload.  No Steam review text or
credentials are included.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.api.senti_next import db, storage
from apps.api.senti_next.research_core import build_snapshot_research_report
from apps.api.senti_next.research_population_snapshot import freeze_analysis_run_population
from tooling.vertical_slice.stage4c_dashboard_fixture import APP_ID, RUN_ID as LEFT_RUN, seed as seed_stage4c


RIGHT_RUN = "stage4d-right-run"
VERSION_RUN = "stage4d-version-run"


def _reviews(prefix: str, count: int, recommended: int) -> list[dict]:
    return [
        {
            "recommendationid": f"{prefix}-{index:03d}",
            "review_id": f"{prefix}-{index:03d}",
            "review": f"Synthetic comparison fixture review {index}.",
            "language": "english",
            "voted_up": index < recommended,
            "timestamp_created": 1700000000 - index,
            "steam_purchase": True,
        }
        for index in range(count)
    ]


def _report(app_id: int, reviews: list[dict], recommended: int) -> dict:
    metadata = {
        "collection_complete": False,
        "truncated_by_max_reviews": True,
        "stop_reason": "max_reviews_reached",
        "coverage_status": "incomplete",
        "sampling_contract": {
            "app_id": app_id,
            "start_time": None,
            "end_time": None,
            "languages": ["english"],
            "review_type": "all",
            "purchase_type": "all",
            "collection_order": "recent",
            "include_offtopic_activity": False,
            "max_reviews": len(reviews),
        },
    }
    report = build_snapshot_research_report(reviews, metadata=metadata)
    population = report["recommendation"]["population"]
    population.update({
        "valid_n": len(reviews),
        "recommended_n": recommended,
        "not_recommended_n": len(reviews) - recommended,
        "recommendation_rate": round(recommended / len(reviews), 6) if reviews else None,
    })
    return report


def _semantic(run_id: str, count: int, population_fingerprint: str) -> dict:
    return {
        "schema_version": "semantic-measurement-result-v1",
        "run_id": run_id,
        "claim_status": "PROVISIONAL",
        "population_n": count,
        "materialized_n": count,
        "classified_n": count,
        "classification_coverage": 1.0,
        "coverage_status": "FULL",
        "topics": [{
            "taxonomy_key": "gameplay/balance",
            "topic_n": max(1, count // 4),
            "topic_share": max(1, count // 4) / count,
            "issue_n": max(1, count // 8),
            "issue_share": max(1, count // 8) / count,
            "request_n": max(1, count // 10),
            "request_share": max(1, count // 10) / count,
            "primary_n": max(1, count // 4),
            "primary_share": max(1, count // 4) / count,
            "topic_validation": {"status": "PROVISIONAL"},
            "issue_validation": {"status": "PROVISIONAL"},
            "request_validation": {"status": "PROVISIONAL"},
        }],
        "provenance": {
            "measurement_bundle_id": "stage4d-shared-bundle",
            "measurement_status": "PROVISIONAL",
            "validation_status": "UNAVAILABLE",
            "taxonomy_version": "sentinext-taxonomy-v1",
            "taxonomy_fingerprint": "stage4d-taxonomy-fp",
            "classifier_provider": "fixture-provider",
            "classifier_model_id": "fixture-model",
            "classifier_prompt_version": "fixture-prompt-v1",
            "classifier_schema_version": "fixture-schema-v1",
            "population_fingerprint": population_fingerprint,
        },
        "semantic_measurement_result_fingerprint": f"{run_id}-semantic-fp",
    }


def _seed_right() -> None:
    reviews = _reviews("right", 80, 60)
    storage.create_general_analysis_run(
        RIGHT_RUN,
        730,
        config={"analysis": {"analysis_mode": "current_snapshot"}},
        requested_languages=["english"],
        requested_review_count=80,
        provider="fixture-provider",
        model_id="fixture-model",
        prompt_version="fixture-prompt-v1",
        taxonomy_version="sentinext-taxonomy-v1",
        analysis_version="stage4d-fixture",
    )
    storage.transition_general_analysis_run(RIGHT_RUN, "running", phase="research_core")
    snapshot = freeze_analysis_run_population(run_id=RIGHT_RUN, app_id=730, reviews=reviews)
    report = _report(730, reviews, 60)
    semantic = _semantic(RIGHT_RUN, len(reviews), snapshot["population_fingerprint"])
    storage.finalize_general_analysis_run(
        RIGHT_RUN,
        730,
        {"run_id": RIGHT_RUN, "app_id": 730, "name": "Synthetic Game B", "population_fingerprint": snapshot["population_fingerprint"]},
        {"five_questions": {}},
        [],
        counts={"available_matching_reviews": 500, "retrieved_count": 80, "deduplicated_count": 80, "analysis_population_count": 80, "valid_review_count": 80, "classified_count": 80},
        research_report=report,
        semantic_status={"status": "available"},
        semantic_measurement_result=semantic,
        unified_research_result={"schema_version": "unified-research-result-v1", "run_id": RIGHT_RUN, "quantitative": report, "semantic": semantic},
    )
    storage.save_starred_game(
        730,
        "Synthetic Game B",
        {"app_id": 730, "requested": 80, "retrieved": 80, "language": "english", "header_image": None},
        {"recommendation": 0.75, "metric_provenance": {"recommendation_rate": {"run_id": RIGHT_RUN, "value": 0.75, "status": "available"}}},
        reviews[:20],
        ["Action"],
        ["Multiplayer"],
    )


def _seed_version() -> None:
    for event_id, name, event_date in (("stage4d-before", "Before update", "2026-08-01"), ("stage4d-after", "After update", "2026-08-08")):
        storage.create_version_event({"event_id": event_id, "app_id": APP_ID, "event_name": name, "event_date": event_date, "event_type": "patch", "event_description": None, "source": "fixture", "source_url": None, "manual_verified": True})
    storage.create_analysis_run({
        "run_id": VERSION_RUN,
        "target_app_id": APP_ID,
        "event_id": "stage4d-after",
        "config": {"analysis": {"analysis_goal": "version_comparison", "comparison_event_id": "stage4d-before", "post_window_days": 7}},
        "status": "completed",
    })
    topic = {"topic_id": "gameplay/balance", "display_name": "balance", "family": "problem", "a_support": 7, "a_rate": 0.20, "b_support": 10, "b_rate": 0.25, "delta_pp": 5.0, "state": "INCREASED", "direction": "up"}
    v2 = {
        "schema_version": "version-review-v2", "window_days": 7,
        "event_a_id": "stage4d-before", "event_b_id": "stage4d-after",
        "a_coverage_status": "COMPLETE", "b_coverage_status": "COMPLETE", "comparison_status": "READY",
        "coverage_gate": {"status": "PASS", "reason": None},
        "raw_metrics_a": {"reviews": 35, "reviews_per_day": 5.0, "recommendation_rate": 0.70},
        "raw_metrics_b": {"reviews": 40, "reviews_per_day": 5.71, "recommendation_rate": 0.75},
        "raw_metric_deltas": {"reviews_per_day": 0.71, "recommendation_rate_pp": 5.0},
        "a_semantic_sample_count": 35, "b_semantic_sample_count": 40, "a_classified_count": 35, "b_classified_count": 40,
        "topic_comparisons": [topic], "request_comparisons": [], "positive_comparisons": [], "paired_evidence": [], "window_sensitivity": [], "emerging_topic_candidates": [],
    }
    storage.save_analysis_run_metrics(VERSION_RUN, {"version_review_v2": v2, "issue_cards": [], "evidence_cards": [], "recommendations": [], "emerging_topic_candidates": [], "warnings": []}, status="completed", phase="completed")


def seed() -> None:
    db.init_db()
    seed_stage4c()
    # Give the existing left fixture an exact run identity for Compare.
    left_reviews = _reviews("left", 80, 70)
    storage.save_starred_game(
        APP_ID,
        "HELLDIVERS 2",
        {"app_id": APP_ID, "requested": 80, "retrieved": 80, "language": "english", "header_image": None},
        {"recommendation": 0.875, "metric_provenance": {"recommendation_rate": {"run_id": LEFT_RUN, "value": 0.875, "status": "available"}}},
        left_reviews[:20],
        ["Action"],
        ["Multiplayer"],
    )
    _seed_right()
    _seed_version()
    print({"left_run": LEFT_RUN, "right_run": RIGHT_RUN, "version_run": VERSION_RUN})


if __name__ == "__main__":
    seed()
