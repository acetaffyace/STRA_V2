"""P0.2c immutable general-analysis result contract tests."""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import db, storage


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def running_run(app_id: int) -> str:
    run_id = uuid4().hex
    storage.create_general_analysis_run(run_id, app_id, config={"review_count": 2})
    storage.transition_general_analysis_run(run_id, "running", phase="classifying")
    return run_id


def finalize(run_id: str, app_id: int, marker: str) -> None:
    storage.finalize_general_analysis_run(
        run_id, app_id, {"marker": marker}, {"marker": marker}, [{"marker": marker}],
        snapshot_hash=f"snapshot-{marker}", context_hash=f"context-{marker}",
        counts={"retrieved_count": 1, "valid_review_count": 1, "classified_count": 1},
    )


def test_successful_runs_are_historical_and_latest_points_to_newest():
    run_a = running_run(101)
    finalize(run_a, 101, "A")
    run_b = running_run(101)
    finalize(run_b, 101, "B")

    assert storage.get_analysis_run_result(run_a)["insights"] == {"marker": "A"}
    assert storage.get_analysis_run_result(run_b)["insights"] == {"marker": "B"}
    assert storage.load_analysis_result(101)["run_id"] == run_b
    assert storage.load_analysis_result(101)["insights"] == {"marker": "B"}


def test_failed_and_cancelled_runs_have_no_immutable_result():
    failed = running_run(102)
    storage.transition_general_analysis_run(failed, "failed", error="boom")
    assert storage.get_analysis_run_result(failed) is None

    cancelled = running_run(103)
    storage.transition_general_analysis_run(cancelled, "cancelled", error="cancel")
    assert storage.get_analysis_run_result(cancelled) is None


def test_result_is_insert_once_and_not_updateable():
    run_id = running_run(104)
    finalize(run_id, 104, "first")
    with pytest.raises(ValueError):
        finalize(run_id, 104, "second")
    assert storage.get_analysis_run_result(run_id)["metadata"] == {"marker": "first"}


def test_finalization_rolls_back_result_latest_and_completion_on_latest_failure():
    run_id = running_run(105)
    storage.save_analysis_result(105, {"old": True}, {"old": True}, [], status="running", run_id=run_id)
    with db.get_connection() as conn:
        conn.exec_driver_sql(
            """CREATE TRIGGER fail_latest_result_update
               BEFORE UPDATE ON analysis_results
               BEGIN SELECT RAISE(ABORT, 'forced latest failure'); END"""
        )
    with pytest.raises(Exception, match="forced latest failure"):
        finalize(run_id, 105, "rollback")
    with db.get_connection() as conn:
        assert conn.exec_driver_sql(
            "SELECT COUNT(*) FROM analysis_run_results WHERE run_id=?", (run_id,)
        ).fetchone()[0] == 0
    assert storage.get_analysis_run(run_id)["status"] == "running"
    assert storage.load_analysis_result(105)["metadata"] == {"old": True}


def test_schema_v5_is_present_without_legacy_backfill():
    with db.get_connection() as conn:
        assert conn.exec_driver_sql(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()[0] >= 5
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(analysis_run_results)")}
    assert {"run_id", "app_id", "metadata", "insights", "reviews", "completed_at"} <= columns
