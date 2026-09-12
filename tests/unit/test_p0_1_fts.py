"""P0.1 canonical FTS integrity and legacy repair tests."""
from __future__ import annotations

import json
import sqlite3
import sys
import shutil
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import db, storage
from senti_next.fts import migrate_legacy_fts, rebuild_fts, verify_fts_integrity
from senti_next.migrations import apply_ordered_migrations


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def review(rid: str, text: str, app_id: int = 1) -> dict:
    return {"recommendationid": rid, "review": text, "language": "english", "app_id": app_id}


def fts_count() -> int:
    with db.get_connection() as conn:
        return int(conn.exec_driver_sql("SELECT COUNT(*) FROM reviews_fts").fetchone()[0])


def test_insert_and_repeated_upsert_have_one_searchable_document():
    storage.upsert_reviews(1, [review("r1", "stable searchable text")])
    storage.upsert_reviews(1, [review("r1", "stable searchable text")] * 100)
    assert fts_count() == 1
    assert storage.search_review_ids(1, "searchable") == ["r1"]
    assert verify_fts_integrity()["ok"]


def test_update_delete_rebuild_and_multiple_apps():
    storage.upsert_reviews(1, [review("r1", "old phrase")])
    storage.upsert_reviews(2, [review("r2", "other app phrase", 2)])
    storage.upsert_reviews(1, [review("r1", "new phrase")])
    assert storage.search_review_ids(1, "old") == []
    assert storage.search_review_ids(1, "new") == ["r1"]
    assert storage.search_review_ids(2, "other") == ["r2"]

    storage.delete_all_game_data(1)
    assert storage.search_review_ids(1, "new") == []
    rebuild_fts()
    assert verify_fts_integrity()["ok"]
    assert fts_count() == 1


def test_integrity_detects_actual_index_corruption_and_rebuilds():
    storage.upsert_reviews(1, [review("r1", "index corruption sentinel")])
    with db.get_connection() as conn:
        conn.exec_driver_sql("INSERT INTO reviews_fts(reviews_fts) VALUES ('delete-all')")
    result = verify_fts_integrity()
    assert result["ok"] is False
    assert result["missing"] == [1]
    assert result["probe_failures"] == [1]

    rebuild_fts()
    assert verify_fts_integrity()["ok"] is True
    assert storage.search_review_ids(1, "sentinel") == ["r1"]


def test_review_text_projection_drift_is_detected_and_repaired():
    storage.upsert_reviews(1, [review("r1", "projection source")])
    assert verify_fts_integrity()["projection_drift"] == []
    with db.get_connection() as conn:
        conn.exec_driver_sql("UPDATE reviews SET review_text='drifted text' WHERE review_id='r1'")
    result = verify_fts_integrity()
    assert result["ok"] is False
    assert result["projection_drift"] == [1]

    storage.upsert_reviews(1, [review("r1", "projection source")])
    assert verify_fts_integrity()["ok"] is True


def test_legacy_duplicate_state_is_repaired():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """CREATE TABLE reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, app_id INTEGER NOT NULL,
            review_id TEXT NOT NULL UNIQUE, data TEXT NOT NULL,
            timestamp_created INTEGER, timestamp_updated INTEGER
        );
        CREATE VIRTUAL TABLE reviews_fts USING fts5(review_id, review_text);
        """
    )
    rows = [(1, "a", "updated alpha"), (2, "b", "bravo beta")]
    for app_id, rid, txt in rows:
        payload = json.dumps({"recommendationid": rid, "review": txt})
        conn.execute("INSERT INTO reviews(app_id,review_id,data) VALUES(?,?,?)", (app_id, rid, payload))
        for _ in range(3):
            conn.execute("INSERT INTO reviews_fts(review_id,review_text) VALUES(?,?)", (rid, txt))
    # A stale legacy row has no canonical review.
    conn.execute("INSERT INTO reviews_fts(review_id,review_text) VALUES('deleted','gone')")
    conn.commit()

    migrate_legacy_fts(conn)
    result = verify_fts_integrity(conn)
    assert result["ok"]
    assert result["canonical_count"] == 2
    assert conn.execute("SELECT COUNT(*) FROM reviews_fts").fetchone()[0] == 2
    assert conn.execute("SELECT review_text FROM reviews WHERE review_id='a'").fetchone()[0] == "updated alpha"
    conn.close()


def test_repeated_migration_is_idempotent():
    with db.get_connection() as conn:
        before = conn.exec_driver_sql("SELECT COUNT(*) FROM reviews_fts").fetchone()[0]
        raw = conn.connection.driver_connection
        migrate_legacy_fts(raw)
        after = conn.exec_driver_sql("SELECT COUNT(*) FROM reviews_fts").fetchone()[0]
    assert before == after == 0
    assert verify_fts_integrity()["ok"]


def test_migration_failure_restores_canonical_reviews():
    root = Path.cwd() / ".p0_1-failure-fixture"
    root.mkdir(exist_ok=True)
    path = root / "legacy.db"
    backup = root / "legacy.bak"
    for item in (path, backup):
        if item.exists():
            item.unlink()
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """CREATE TABLE reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT, app_id INTEGER NOT NULL,
                review_id TEXT NOT NULL UNIQUE, data TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE reviews_fts USING fts5(review_id, review_text);
            INSERT INTO reviews(app_id, review_id, data)
            VALUES (1, 'keep', '{\"recommendationid\":\"keep\",\"review\":\"keep me\"}');
            """
        )

    def failing_migration(conn):
        migrate_legacy_fts(conn)
        raise RuntimeError("forced P0.1 failure")

    with pytest.raises(RuntimeError, match="forced P0.1 failure"):
        apply_ordered_migrations(
            path,
            [(2, "failing FTS migration", failing_migration)],
            backup_path=backup,
            restore_on_error=True,
        )
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(reviews)")}
        assert "review_text" not in columns
        assert conn.execute("SELECT review_id FROM reviews").fetchone()[0] == "keep"
    shutil.rmtree(root, ignore_errors=True)
