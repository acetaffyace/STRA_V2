from __future__ import annotations

from apps.api.senti_next.dashboard_presentation import build_dashboard_presentation
from apps.api.senti_next.research_core import build_snapshot_research_report


def _report():
    population = [
        {"recommendationid": f"r-{index}", "review": f"synthetic review {index} with enough text", "voted_up": index < 70,
         "timestamp_created": 1_700_000_000 + index, "timestamp_updated": 1_700_000_000 + index,
         "language": "english", "steam_purchase": True, "author": {"playtime_at_review": 10, "playtime_forever": 100}}
        for index in range(80)
    ]
    metadata = {
        "collection_complete": False, "truncated_by_max_reviews": True, "stop_reason": "max_reviews_reached",
        "coverage_start_time": 1_700_000_000, "coverage_end_time": 1_700_000_079, "coverage_status": "incomplete",
        "sampling_contract": {"app_id": 553850, "start_time": None, "end_time": None, "languages": ["english"],
                              "review_type": "all", "purchase_type": "all", "collection_order": "recent",
                              "include_offtopic_activity": False, "max_reviews": 80},
    }
    return build_snapshot_research_report(population, metadata=metadata)


def _semantic():
    return {
        "claim_status": "PROVISIONAL",
        "population_n": 80,
        "classified_n": 80,
        "classification_coverage": 1.0,
        "coverage_status": "FULL",
        "provenance": {
            "measurement_status": "PROVISIONAL",
            "validation_status": "UNAVAILABLE",
            "taxonomy_version": "sentinext-taxonomy-v1",
            "classifier_provider": "deepseek",
            "classifier_model_id": "deepseek-v4-flash",
            "classifier_prompt_version": "prompt-v1",
            "classifier_schema_version": "schema-v1",
            "population_fingerprint": "population-fp",
        },
        "topics": [
            {"taxonomy_key": "other/meme", "topic_n": 23, "topic_share": 0.2875, "topic_validation": {"status": "PROVISIONAL"}},
            {"taxonomy_key": "other/general", "topic_n": 15, "topic_share": 0.1875, "topic_validation": {"status": "PROVISIONAL"}},
            {"taxonomy_key": "gameplay/balance", "topic_n": 7, "topic_share": 0.0875, "issue_n": 7, "issue_share": 0.0875, "request_n": 0, "topic_validation": {"status": "PROVISIONAL"}, "issue_validation": {"status": "PROVISIONAL"}, "request_validation": {"status": "INSUFFICIENT"}},
        ],
        "semantic_measurement_result_fingerprint": "semantic-fp",
    }


def test_projection_owns_canonical_metrics_and_separates_context() -> None:
    presentation = build_dashboard_presentation(
        app_id=553850,
        run={"run_id": "run-1", "status": "completed"},
        result={"run_id": "run-1", "research_report": _report(), "semantic_measurement_result": _semantic()},
    )
    assert presentation["schema_version"] == "dashboard-presentation-v1"
    assert presentation["research_snapshot"]["recommendation_rate"] == 0.875
    assert presentation["research_snapshot"]["valid_n"] == 80
    assert presentation["research_snapshot"]["recommended_n"] == 70
    assert presentation["research_snapshot"]["not_recommended_n"] == 10
    assert presentation["research_snapshot"]["collection_complete"] is False
    assert presentation["research_snapshot"]["truncated_by_max_reviews"] is True
    assert presentation["research_snapshot"]["stop_reason"] == "max_reviews_reached"
    assert presentation["research_snapshot"]["collection_status"] == "limited"
    assert presentation["research_snapshot"]["collection_scope"]["languages"] == ["english"]
    assert [row["taxonomy_key"] for row in presentation["player_voice"]["actionable_topics"]["items"]] == ["gameplay/balance"]
    assert [(row["taxonomy_key"], row["n"]) for row in presentation["player_voice"]["context_topics"]["items"]] == [("other/meme", 23), ("other/general", 15)]
    assert presentation["semantic"]["claim_status"] == "PROVISIONAL"
    assert presentation["semantic"]["classified_n"] == 80


def test_quantitative_only_and_partial_coverage_are_explicit() -> None:
    quantitative = build_dashboard_presentation(
        app_id=1,
        run={"run_id": "run-q", "status": "completed"},
        result={"run_id": "run-q", "research_report": _report(), "semantic_status": {"status": "unavailable", "reason": "no_provider"}},
    )
    assert quantitative["research_snapshot"]["recommended_n"] == 70
    assert quantitative["semantic"]["available"] is False
    partial = _semantic() | {"classified_n": 80, "population_n": 100, "classification_coverage": 0.8, "coverage_status": "PARTIAL"}
    projection = build_dashboard_presentation(app_id=1, run={"run_id": "run-p", "status": "completed"}, result={"semantic_measurement_result": partial})
    assert projection["semantic"]["classified_n"] == 80
    assert projection["semantic"]["population_n"] == 100
