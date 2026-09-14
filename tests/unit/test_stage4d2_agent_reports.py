from __future__ import annotations

from apps.api.senti_next.canonical_agent_reports import canonical_review_search
from apps.api.senti_next.chat_agent import AgentContext
from apps.api.senti_next.chat_tools import _make_cache_key, _execute_get_game_overview, _execute_get_top_issues
from apps.api.senti_next.reports import create_canonical_report_html


def _exact() -> dict:
    return {
        "run_id": "run-a",
        "run": {"target_app_id": 10, "run_id": "run-a", "status": "completed"},
        "population": {"reviews": [
            {"recommendationid": "r1", "review": "great balance", "voted_up": True, "language": "english"},
            {"recommendationid": "r2", "review": "bad balance", "voted_up": False, "language": "english"},
        ]},
        "materialization": {"items": [
            {"review_id": "r1", "payload": {"subcategories": ["gameplay/balance"], "issue_subcategories": [], "request_subcategories": []}},
            {"review_id": "r2", "payload": {"subcategories": ["gameplay/balance"], "issue_subcategories": ["gameplay/balance"], "request_subcategories": []}},
        ]},
    }


def test_exact_review_search_is_run_scoped_and_metric_specific() -> None:
    result = canonical_review_search(_exact(), subcategory="gameplay/balance", metric_type="issue", limit=10)
    assert result["run_id"] == "run-a"
    assert [item["review_id"] for item in result["reviews"]] == ["r2"]
    assert result["population_scope"] == "exact_frozen_research_population"


def test_agent_cache_key_includes_exact_run_identity() -> None:
    params = {"app_id": 10}
    assert _make_cache_key("overview", params, "10:run-a") != _make_cache_key("overview", params, "10:run-b")


def test_agent_overview_preserves_canonical_unknown_counts(monkeypatch) -> None:
    exact = _exact()
    monkeypatch.setattr("apps.api.senti_next.chat_tools._exact_context_for_app", lambda params, context: (10, exact))
    monkeypatch.setattr("apps.api.senti_next.canonical_agent_reports.build_exact_presentation", lambda value: {"research_snapshot": {
        "population_n": 2, "valid_n": 2, "recommended_n": None, "not_recommended_n": None,
        "recommendation_rate": 0.5, "collection_scope": {}, "collection_complete": None,
        "truncated_by_max_reviews": None, "stop_reason": None,
    }})
    result = _execute_get_game_overview({}, AgentContext(session_id="s", app_ids=[10]))
    assert result.data["recommended_n"] is None
    assert result.data["not_recommended_n"] is None


def test_agent_issue_tool_reads_3f_rows(monkeypatch) -> None:
    exact = _exact()
    exact["result"] = {"semantic_measurement_result": {"population_n": 2, "classified_n": 2, "classification_coverage": 1.0, "claim_status": "PROVISIONAL", "provenance": {"measurement_status": "PROVISIONAL", "validation_status": "UNAVAILABLE"}}}
    monkeypatch.setattr("apps.api.senti_next.chat_tools._canonical_semantic_rows", lambda params, context: (10, exact, [{
        "taxonomy_key": "gameplay/balance", "issue_n": 1, "issue_share": 0.5, "issue_validation": {"status": "PROVISIONAL"}
    }]))
    result = _execute_get_top_issues({}, AgentContext(session_id="s", app_ids=[10]))
    assert result.data["issues"][0]["complaint_count"] == 1
    assert result.data["classified_n"] == 2
    assert result.data["claim_status"] == "PROVISIONAL"


def test_canonical_report_html_contains_exact_qualification_and_scope() -> None:
    report = {
        "run": {"run_id": "run-a"},
        "research_snapshot": {"population_n": 80, "recommended_n": 70, "recommendation_rate": 0.875, "truncated_by_max_reviews": True, "collection_scope": {"languages": ["english"], "collection_order": "recent", "max_reviews": 80}},
        "semantic": {"claim_status": "PROVISIONAL", "available": True, "classified_n": 80, "population_n": 80},
        "player_voice": {"actionable_topics": {"items": []}, "issues": {"items": []}, "requests": {"items": []}, "context_topics": {"items": []}},
        "evidence": {"source_review_count": 80, "verified_evidence_count": 0}, "provenance": {"population_fingerprint": "fp"},
    }
    html = create_canonical_report_html(report, "Test Game")
    assert "87.5%" in html
    assert "PROVISIONAL" in html
    assert "80 / 80 classified reviews" in html
    assert "Limited by the configured review maximum" in html
