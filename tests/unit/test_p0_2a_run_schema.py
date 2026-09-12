"""P0.2a generalized analysis_runs schema contract tests."""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

import pytest

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import db, storage
from senti_next.migrations import apply_ordered_migrations
from senti_next.run_schema import migrate_analysis_runs


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def columns() -> set[str]:
    with db.get_connection() as conn:
        return {str(row[1]) for row in conn.exec_driver_sql("PRAGMA table_info(analysis_runs)").fetchall()}


def test_fresh_database_has_generalized_schema_and_version_three():
    expected = {
        "run_type", "started_at", "completed_at", "data_cutoff", "window_start",
        "window_end", "requested_languages", "requested_review_count",
        "retrieved_count", "valid_review_count", "classified_count",
        "fallback_count", "enriched_count", "scope_fingerprint",
        "taxonomy_version", "prompt_version", "analysis_version", "provider", "model_id",
    }
    assert expected <= columns()
    with db.get_connection() as conn:
        versions = conn.exec_driver_sql("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        assert [row[0] for row in versions] == [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13]


def test_existing_version_review_storage_and_api_shape_still_work():
    event = storage.create_version_event({
        "event_id": uuid4().hex, "app_id": 42, "event_name": "Patch",
        "event_date": "2026-08-01", "event_type": "patch", "manual_verified": True,
        "event_description": None, "source": "manual", "source_url": None,
    })
    run = storage.create_analysis_run({
        "run_id": uuid4().hex, "target_app_id": 42, "event_id": event["event_id"],
        "config": {"analysis_goal": "version_review"}, "status": "created",
    })
    assert run["run_id"]
    assert storage.get_analysis_run(run["run_id"])["event_id"] == event["event_id"]
    with db.get_connection() as conn:
        row = conn.exec_driver_sql("SELECT run_type FROM analysis_runs WHERE run_id=?", (run["run_id"],)).fetchone()
    assert row[0] == "version_review"


def test_general_run_can_leave_version_scope_null_and_provenance_unknown():
    with db.get_connection() as conn:
        conn.exec_driver_sql(
            """INSERT INTO analysis_runs
               (run_id,user_id,target_app_id,event_id,run_type,config,status,
                requested_languages,requested_review_count,model_id)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            ("general-1", "default", 42, None, "general_analysis", "{}", "created", "[]", 10, None),
        )
        row = conn.exec_driver_sql(
            "SELECT event_id, run_type, requested_review_count, model_id FROM analysis_runs WHERE run_id='general-1'"
        ).fetchone()
    assert tuple(row) == (None, "general_analysis", 10, None)


def test_legacy_migration_preserves_data_and_classifies_version_runs():
    fresh_columns = columns()
    root = Path.cwd() / ".p0_2a-parity-fixture"
    root.mkdir(exist_ok=True)
    legacy = root / "legacy.db"
    if legacy.exists():
        legacy.unlink()
    try:
        with sqlite3.connect(legacy) as conn:
            conn.executescript(
                """CREATE TABLE version_events(event_id TEXT PRIMARY KEY);
                CREATE TABLE analysis_runs(
                    run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    target_app_id INTEGER NOT NULL, event_id TEXT NOT NULL,
                    config TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'created',
                    metrics TEXT, error TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY(event_id) REFERENCES version_events(event_id)
                );
                INSERT INTO version_events VALUES('event-1');
                INSERT INTO analysis_runs(run_id,user_id,target_app_id,event_id,config)
                VALUES('legacy-1','default',7,'event-1','{\"x\":1}');
                """
            )
        db3 = [(3, "generalized analysis_runs schema", migrate_analysis_runs)]
        apply_ordered_migrations(legacy, db3)
        with sqlite3.connect(legacy) as conn:
            conn.execute("ALTER TABLE analysis_runs ADD COLUMN phase TEXT")
            conn.execute("ALTER TABLE analysis_runs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
            row = conn.execute("SELECT run_id,event_id,run_type,config FROM analysis_runs").fetchone()
            final_columns = {item[1] for item in conn.execute("PRAGMA table_info(analysis_runs)")}
        assert row == ("legacy-1", "event-1", "version_review", '{"x":1}')
        assert final_columns == fresh_columns
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_migration_failure_restores_existing_runs():
    root = Path.cwd() / ".p0_2a-failure-fixture"
    root.mkdir(exist_ok=True)
    legacy = root / "legacy.db"
    backup = root / "legacy.bak"
    for item in (legacy, backup):
        if item.exists():
            item.unlink()
    try:
        with sqlite3.connect(legacy) as conn:
            conn.executescript(
                """CREATE TABLE version_events(event_id TEXT PRIMARY KEY);
                CREATE TABLE analysis_runs(
                    run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    target_app_id INTEGER NOT NULL, event_id TEXT NOT NULL,
                    config TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'created',
                    metrics TEXT, error TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                INSERT INTO analysis_runs(run_id,user_id,target_app_id,event_id,config)
                VALUES('keep','default',7,'event-1','{}');
                """
            )

        def fail(conn):
            migrate_analysis_runs(conn)
            raise RuntimeError("forced P0.2a failure")

        with pytest.raises(RuntimeError, match="forced P0.2a failure"):
            apply_ordered_migrations(legacy, [(3, "failing run migration", fail)], backup_path=backup, restore_on_error=True)
        with sqlite3.connect(legacy) as conn:
            cols = {item[1] for item in conn.execute("PRAGMA table_info(analysis_runs)")}
            assert "run_type" not in cols
            assert conn.execute("SELECT run_id FROM analysis_runs").fetchone()[0] == "keep"
    finally:
        shutil.rmtree(root, ignore_errors=True)
