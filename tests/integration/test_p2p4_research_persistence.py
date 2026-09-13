"""Stage 2P.4 first-class Research Report persistence contract tests."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

API_DIR = Path(__file__).resolve().parents[1]
import sys
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import db, result_schema, storage
from senti_next.routes import analysis as analysis_route


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def test_migration_backfills_only_exact_transitional_fields_and_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE analysis_results (
            id INTEGER PRIMARY KEY,
            insights TEXT,
            metadata TEXT
        );
        CREATE TABLE analysis_run_results (
            run_id TEXT PRIMARY KEY,
            insights TEXT
        );
        """
    )
    report = {"schema_version": "research-report-v1", "mode": "snapshot"}
    status = {"status": "unavailable", "reason": "no_provider"}
    conn.execute(
        "INSERT INTO analysis_results(id, insights) VALUES (?, ?)",
        (1, json.dumps({"research_report": report, "semantic_status": status})),
    )
    conn.execute(
        "INSERT INTO analysis_results(id, insights) VALUES (?, ?)",
        (2, json.dumps({"recommendation": 0.71, "metrics": {"n": 4}})),
    )
    conn.execute(
        "INSERT INTO analysis_run_results(run_id, insights) VALUES (?, ?)",
        ("run-1", json.dumps({"research_report": report, "semantic_status": status})),
    )

    result_schema.migrate_research_result_fields(conn)
    result_schema.migrate_research_result_fields(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(analysis_results)")}
    assert {"research_report", "semantic_status"} <= cols
    row = conn.execute(
        "SELECT research_report, semantic_status FROM analysis_results WHERE id=1"
    ).fetchone()
    assert json.loads(row[0]) == report
    assert json.loads(row[1]) == status
    assert conn.execute(
        "SELECT research_report, semantic_status FROM analysis_results WHERE id=2"
    ).fetchone() == (None, None)
    row = conn.execute(
        "SELECT research_report, semantic_status FROM analysis_run_results WHERE run_id='run-1'"
    ).fetchone()
    assert json.loads(row[0]) == report
    assert json.loads(row[1]) == status


def test_latest_result_round_trip_and_sentinel_clear_semantics():
    report = {"schema_version": "research-report-v1", "mode": "snapshot"}
    status = {"status": "unavailable", "reason": "no_provider"}
    storage.save_analysis_result(
        501, {"app_id": 501}, {"legacy": True}, [], "completed",
        research_report=report, semantic_status=status,
    )
    loaded = storage.load_analysis_result(501)
    assert loaded["research_report"] == report
    assert loaded["semantic_status"] == status
    assert loaded["insights"] == {"legacy": True}

    # Omitted fields preserve the prior first-class values.
    storage.save_analysis_result(501, {"app_id": 501}, None, [], "running")
    loaded = storage.load_analysis_result(501)
    assert loaded["research_report"] == report
    assert loaded["semantic_status"] == status

    # Explicit None clears them.
    storage.save_analysis_result(
        501, {"app_id": 501}, None, [], "running",
        research_report=None, semantic_status=None,
    )
    loaded = storage.load_analysis_result(501)
    assert loaded["research_report"] is None
    assert loaded["semantic_status"] is None


def test_immutable_result_round_trip_keeps_semantic_insights_separate():
    run_id = uuid4().hex
    storage.create_general_analysis_run(run_id, 502, config={"review_count": 1})
    storage.transition_general_analysis_run(run_id, "running", phase="research_core")
    report = {"schema_version": "research-report-v1", "mode": "snapshot"}
    status = {"status": "available", "reason": None}
    storage.finalize_general_analysis_run(
        run_id, 502, {"app_id": 502}, {"legacy_metric": 1}, [],
        research_report=report, semantic_status=status,
    )
    immutable = storage.get_analysis_run_result(run_id)
    latest = storage.load_analysis_result(502)
    assert immutable["research_report"] == latest["research_report"] == report
    assert immutable["semantic_status"] == latest["semantic_status"] == status
    assert immutable["insights"] == latest["insights"] == {"legacy_metric": 1}


def test_analysis_get_marks_changed_review_pool_stale_without_recomputing(monkeypatch):
    report = {"schema_version": "research-report-v1", "mode": "snapshot"}
    stored = {
        "status": "completed",
        "metadata": {
            "app_id": 503, "requested": 1, "retrieved": 1,
            "language": "all", "review_fingerprint": "old",
        },
        "insights": None,
        "research_report": report,
        "semantic_status": {"status": "unavailable", "reason": "no_provider"},
        "reviews": [], "error": None, "run_id": "run-503",
        "snapshot_hash": None, "stale": False, "stale_reason": None,
    }
    monkeypatch.setattr(analysis_route.storage, "load_analysis_result", lambda app_id: dict(stored))
    monkeypatch.setattr(analysis_route.storage, "get_reviews_fingerprint", lambda app_id: "new")
    monkeypatch.setattr(analysis_route, "fetch_app_details", lambda app_id: {})
    monkeypatch.setattr(analysis_route, "build_reviews_dataframe", lambda *a, **k: (_ for _ in ()).throw(AssertionError("GET must not recompute")))
    monkeypatch.setattr(analysis_route, "prepare_insights", lambda *a, **k: (_ for _ in ()).throw(AssertionError("GET must not recompute")))
    monkeypatch.setattr(analysis_route.llm, "apply_review_labels", lambda *a, **k: (_ for _ in ()).throw(AssertionError("GET must not recompute")))

    response = analysis_route.get_analysis_result(503)

    assert response.research_report == report
    assert response.stale is True
    assert response.stale_reason == "Review pool changed since analysis run"
    assert response.data_refreshed is False
