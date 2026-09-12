"""Small SQLite migration/backup foundation for the local-first desktop app.

P0.0A establishes the version ledger and recovery primitives used by the FTS
migration without adding Alembic to the PyInstaller bundle.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 7


def ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now')),
            description TEXT NOT NULL
        )
        """
    )


def current_version(conn: sqlite3.Connection) -> int:
    ensure_version_table(conn)
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
    return int(row[0] or 0)


def record_version(conn: sqlite3.Connection, version: int, description: str) -> None:
    conn.execute(
        """
        INSERT INTO schema_migrations(version, description)
        VALUES (?, ?)
        """,
        (int(version), description),
    )


def backup_database(database_path: str | Path, backup_path: str | Path) -> Path:
    """Create a consistent SQLite backup using SQLite's backup API."""
    source = Path(database_path).expanduser().resolve()
    target = Path(backup_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target == source:
        raise ValueError("Backup path must differ from source database path")

    src_conn = sqlite3.connect(str(source))
    dst_conn = sqlite3.connect(str(target))
    try:
        src_conn.backup(dst_conn)
        dst_conn.commit()
    finally:
        dst_conn.close()
        src_conn.close()
    logger.info("SQLite backup created: %s -> %s", source, target)
    return target


def restore_database(backup_path: str | Path, database_path: str | Path) -> Path:
    """Restore a database file from a previously-created backup."""
    backup = Path(backup_path).expanduser().resolve()
    target = Path(database_path).expanduser().resolve()
    if not backup.is_file():
        raise FileNotFoundError(f"SQLite backup does not exist: {backup}")
    if backup == target:
        raise ValueError("Restore source and destination must differ")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, target)
    logger.warning("SQLite database restored from backup: %s -> %s", backup, target)
    return target


Migration = tuple[int, str, Callable[[sqlite3.Connection], None]]


def apply_ordered_migrations(
    database_path: str | Path,
    migrations: Iterable[Migration],
    *,
    backup_path: str | Path | None = None,
    restore_on_error: bool = False,
) -> int:
    """Apply ordered migrations with optional backup/restore protection.

    Migrations are committed one at a time. A failed migration rolls back its
    transaction and, when requested, restores the pre-run backup.
    """
    database = Path(database_path).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    migration_list = sorted(migrations, key=lambda item: item[0])
    if any(version <= 0 for version, _, _ in migration_list):
        raise ValueError("Migration versions must be positive")
    if [version for version, _, _ in migration_list] != sorted({version for version, _, _ in migration_list}):
        raise ValueError("Migration versions must be unique and ordered")

    if backup_path is not None and database.is_file():
        backup = backup_database(database, backup_path)

    conn = sqlite3.connect(str(database))
    try:
        ensure_version_table(conn)
        conn.commit()
        version = current_version(conn)
        for target_version, description, migration in migration_list:
            if target_version <= version:
                continue
            logger.info("Applying SQLite migration %s: %s", target_version, description)
            try:
                conn.execute("BEGIN")
                migration(conn)
                record_version(conn, target_version, description)
                conn.commit()
            except Exception:
                conn.rollback()
                logger.exception("SQLite migration %s failed", target_version)
                if restore_on_error and backup is not None:
                    conn.close()
                    restore_database(backup, database)
                raise
            version = target_version
        return version
    finally:
        conn.close()
