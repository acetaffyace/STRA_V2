from __future__ import annotations

import json

from apps.api.senti_next import db, storage
from apps.api.senti_next.offline import run_offline_fixture


def test_mvp_golden_path_closes_without_provider_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'mvp.db'}")
    db.close_engine(); db._engine = None
    source = tmp_path / "ninja_fixture.jsonl"
    rows = [
        {
            "review_id": "ng4-1", "language": "english", "voted_up": False,
            "review": "The controller crashes after the patch. Please add remapping.",
            "timestamp_created": 1700000000, "steam_purchase": True,
            "received_for_free": False, "primarily_steam_deck": False,
            "developer_response": "We are investigating this.", "timestamp_dev_responded": 1700000100,
        },
        {
            "review_id": "ng4-2", "language": "english", "voted_up": True,
            "review": "Combat is excellent and responsive.", "timestamp_created": 1700001000,
        },
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    result = run_offline_fixture(app_id=2627260, reviews_path=source, game_context={"name": "NINJA GAIDEN 4"})
    run_id = result["run_id"]
    five = result["insights"]["five_questions"]
    assert result["mode"] == "codex_offline_fixture"
    assert result["metadata"]["crawl_quality"]["complete"] is True
    assert result["insights"]["adaptive_analysis"]["mode"] == "current_snapshot"
    assert storage.get_analysis_design(run_id)["snapshot"]["analysis_type"] == "current_snapshot"
    assert five["what_changed"]["status"] == "unavailable"
    assert five["recommended_actions"]
    assert result["offline_chat"]["mode"] == "codex_offline_fixture"
    assert result["offline_chat"]["citations"]
    assert all(c["verification_status"] == "verified" for c in result["offline_chat"]["citations"])

    immutable = storage.get_analysis_run_result(run_id)
    assert immutable is not None
    assert storage.get_analysis_run(run_id)["status"] == "completed"
    with db.get_connection() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM llm_calls").scalar() == 0
        row = conn.exec_driver_sql(
            "SELECT developer_response, steam_purchase, received_for_free, primarily_steam_deck FROM reviews WHERE review_id=?",
            ("ng4-1",),
        ).fetchone()
    assert row == ("We are investigating this.", 1, 0, 0)
    db.close_engine(); db._engine = None
