"""P0.0A migration/backup foundation tests."""
from __future__ import annotations

import sqlite3
import shutil
from uuid import uuid4
from pathlib import Path

import pytest

from apps.api.senti_next.migrations import (
    apply_ordered_migrations,
    backup_database,
    current_version,
    restore_database,
)


@pytest.fixture
def p0_tmp_path():
    path = Path.cwd() / ".p0-test-tmp" / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _create_base(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO settings VALUES ('mode', 'baseline')")


def _add_marker(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE marker (value TEXT NOT NULL)")
    conn.execute("INSERT INTO marker VALUES ('migrated')")


def test_fresh_database_applies_ordered_migration(p0_tmp_path: Path) -> None:
    tmp_path = p0_tmp_path
    db_path = tmp_path / "fresh.db"
    version = apply_ordered_migrations(db_path, [(1, "bootstrap marker", _add_marker)])

    assert version == 1
    with sqlite3.connect(db_path) as conn:
        assert current_version(conn) == 1
        assert conn.execute("SELECT value FROM marker").fetchone()[0] == "migrated"


def test_existing_database_is_preserved_and_migrated(p0_tmp_path: Path) -> None:
    tmp_path = p0_tmp_path
    db_path = tmp_path / "existing.db"
    _create_base(db_path)

    apply_ordered_migrations(db_path, [(1, "bootstrap marker", _add_marker)])

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT value FROM settings WHERE key='mode'").fetchone()[0] == "baseline"
        assert conn.execute("SELECT value FROM marker").fetchone()[0] == "migrated"


def test_repeated_startup_is_idempotent(p0_tmp_path: Path) -> None:
    tmp_path = p0_tmp_path
    db_path = tmp_path / "repeat.db"
    migrations = [(1, "bootstrap marker", _add_marker)]

    assert apply_ordered_migrations(db_path, migrations) == 1
    assert apply_ordered_migrations(db_path, migrations) == 1
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1


def test_backup_and_restore_preserve_source_state(p0_tmp_path: Path) -> None:
    tmp_path = p0_tmp_path
    db_path = tmp_path / "source.db"
    backup_path = tmp_path / "source.backup.db"
    _create_base(db_path)

    backup_database(db_path, backup_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE settings SET value='changed' WHERE key='mode'")
        conn.commit()
    restore_database(backup_path, db_path)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT value FROM settings WHERE key='mode'").fetchone()[0] == "baseline"
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute("SELECT value FROM settings WHERE key='mode'").fetchone()[0] == "baseline"


def test_failed_migration_restores_database(p0_tmp_path: Path) -> None:
    tmp_path = p0_tmp_path
    db_path = tmp_path / "failed.db"
    backup_path = tmp_path / "failed.backup.db"
    _create_base(db_path)

    def fail(conn: sqlite3.Connection) -> None:
        conn.execute("ALTER TABLE settings ADD COLUMN transient TEXT")
        raise RuntimeError("simulated migration failure")

    with pytest.raises(RuntimeError, match="simulated migration failure"):
        apply_ordered_migrations(
            db_path,
            [(1, "failing migration", fail)],
            backup_path=backup_path,
            restore_on_error=True,
        )

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(settings)")}
        assert "transient" not in columns
        assert conn.execute("SELECT value FROM settings WHERE key='mode'").fetchone()[0] == "baseline"


def test_application_db_initialization_records_stable_bootstrap_version(monkeypatch) -> None:
    """The real SQLAlchemy lifecycle records bootstrap version exactly once."""
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    from apps.api.senti_next import db as db_module

    db_module.close_engine()
    db_module._engine = None
    db_module.init_db()
    db_module.init_db()
    with db_module.get_connection() as conn:
        from sqlalchemy import text

        versions = conn.execute(text("SELECT version, description FROM schema_migrations")).fetchall()
    db_module.close_engine()
    db_module._engine = None

    assert versions == [
        (1, "legacy schema bootstrap"),
        (2, "canonical external-content review FTS"),
            (3, "generalized analysis_runs schema"),
            (4, "general analysis lifecycle columns"),
                (5, "immutable general analysis run results"),
                (6, "review label provenance and cache identity"),
            (7, "immutable chat evidence metadata"),
            (8, "durable LLM physical-call cost ledger"),
            (10, "adaptive analysis design snapshots"),
                (11, "Steam review enrichment canonical fields and raw-payload backfill"),
                (12, "Web MVP UX population counters and authoritative ETA"),
                (13, "first-class Research Core result persistence"),
                            ]
