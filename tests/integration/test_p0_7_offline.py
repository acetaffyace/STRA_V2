from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from apps.api.senti_next import cost_ledger, db
from apps.api.senti_next.five_questions import build_five_question_contract
from apps.api.senti_next.insights import prepare_insights
from apps.api.senti_next.offline import run_offline_fixture
from apps.api.senti_next.providers.config import validate_provider_configuration


def test_unknown_pricing_never_raises_on_none_snapshot():
    assert cost_ledger.estimate_cost({"input": None, "output": None}, 10, 2) is None


def test_new_deepseek_calls_reject_obsolete_model_identity():
    ok, error = validate_provider_configuration("deepseek", "deepseek-chat")
    assert ok is False
    assert "deepseek-v4-flash" in str(error)
    assert validate_provider_configuration("deepseek", "deepseek-v4-flash")[0] is True


def test_five_questions_refuse_missing_comparison_and_mark_heuristics():
    insights = {
        "metric_provenance": {
            "review_count": {"value": 4},
            "recommendation_rate": {"value": 0.5, "numerator": 2, "denominator": 4},
            "technical_issue_rate": {"value": 0.5, "numerator": 1, "denominator": 2},
            "feature_request_rate": {"value": 0.5, "numerator": 1, "denominator": 2},
            "classification_coverage": {"value": 0.5, "denominator": 4},
        },
        "subcategory_insights": [{
            "subcategory": "technical/bugs", "count": 2, "not_recommended": 2,
            "issue_count": 2, "request_count": 0, "issue_evidence": [],
        }],
        "player_segments": {"language": []},
    }
    contract = build_five_question_contract(insights)
    assert contract["what_changed"]["status"] == "unavailable"
    assert contract["what_matters"]["is_heuristic"] is True
    assert contract["recommended_actions"][0]["action_class"] == "FIX"


def test_offline_fixture_reaches_immutable_result_without_llm_calls(tmp_path, monkeypatch):
    db.close_engine()
    db._engine = None
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'offline.db'}")
    rows = [
        {"review_id": "r1", "language": "english", "voted_up": False, "review": "Bug crash. Please add saves."},
        {"review_id": "r2", "language": "german", "voted_up": True, "review": "Great soundtrack."},
    ]
    source = tmp_path / "reviews.jsonl"
    source.write_text("\n".join(__import__("json").dumps(row) for row in rows), encoding="utf-8")
    result = run_offline_fixture(app_id=99001, reviews_path=source)
    assert result["mode"] == "codex_offline_fixture"
    assert result["insights"]["five_questions"]["mode"] == "codex_offline_fixture"
    with db.get_connection() as conn:
        run = conn.exec_driver_sql("SELECT status FROM analysis_runs WHERE run_id=?", (result["run_id"],)).fetchone()
        calls = conn.exec_driver_sql("SELECT COUNT(*) FROM llm_calls").scalar()
        labels = conn.exec_driver_sql("SELECT label_origin FROM review_labels WHERE app_id=99001").fetchall()
    assert run == ("completed",)
    assert calls == 0
    assert {row[0] for row in labels} == {"offline_fixture"}
    second = run_offline_fixture(app_id=99001, reviews_path=source)
    assert second["metadata"]["counters"]["cache_reused_count"] == 2
    assert second["metadata"]["counters"]["cache_miss_count"] == 0
    db.close_engine()
    db._engine = None
