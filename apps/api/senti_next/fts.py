"""Canonical SQLite FTS5 maintenance for reviews."""
from __future__ import annotations

from typing import Any
import re

from sqlalchemy import text


FTS_MIGRATION_VERSION = 2


def _execute(conn: Any, sql: str, params: tuple[Any, ...] = ()):
    """Execute SQL against either sqlite3 or a SQLAlchemy connection."""
    if hasattr(conn, "exec_driver_sql"):
        return conn.exec_driver_sql(sql, params)
    return conn.execute(sql, params)


def _searchable_token(value: str) -> str:
    """Return a conservative unicode61-compatible probe token."""
    tokens = re.findall(r"[^\W_]+", value or "", flags=re.UNICODE)
    return tokens[0] if tokens else ""


def migrate_legacy_fts(conn: Any) -> None:
    """Convert legacy standalone FTS rows into canonical external-content FTS."""
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(reviews)").fetchall()}
    if "review_text" not in columns:
        conn.execute("ALTER TABLE reviews ADD COLUMN review_text TEXT NOT NULL DEFAULT ''")

    conn.execute(
        "UPDATE reviews SET review_text = COALESCE(json_extract(data, '$.review'), '')"
    )
    conn.execute("DROP TABLE IF EXISTS reviews_fts")
    conn.execute(
        """CREATE VIRTUAL TABLE reviews_fts USING fts5(
            review_text,
            content='reviews',
            content_rowid='id',
            tokenize='unicode61'
        )"""
    )
    _create_triggers(conn)
    conn.execute(
        "INSERT INTO reviews_fts(rowid, review_text) SELECT id, review_text FROM reviews"
    )


def _create_triggers(conn: Any) -> None:
    _execute(conn, "DROP TRIGGER IF EXISTS reviews_fts_ai")
    _execute(conn, "DROP TRIGGER IF EXISTS reviews_fts_au")
    _execute(conn, "DROP TRIGGER IF EXISTS reviews_fts_ad")
    _execute(
        conn,
        """CREATE TRIGGER reviews_fts_ai AFTER INSERT ON reviews BEGIN
            INSERT INTO reviews_fts(rowid, review_text)
            VALUES (new.id, new.review_text);
        END""",
    )
    _execute(
        conn,
        """CREATE TRIGGER reviews_fts_au AFTER UPDATE OF review_text ON reviews BEGIN
            INSERT INTO reviews_fts(reviews_fts, rowid, review_text)
            VALUES ('delete', old.id, old.review_text);
            INSERT INTO reviews_fts(rowid, review_text)
            VALUES (new.id, new.review_text);
        END""",
    )
    _execute(
        conn,
        """CREATE TRIGGER reviews_fts_ad AFTER DELETE ON reviews BEGIN
            INSERT INTO reviews_fts(reviews_fts, rowid, review_text)
            VALUES ('delete', old.id, old.review_text);
        END""",
    )


def _drop_triggers(conn: Any) -> None:
    for name in ("reviews_fts_ai", "reviews_fts_au", "reviews_fts_ad"):
        _execute(conn, f"DROP TRIGGER IF EXISTS {name}")


def _recreate_external_fts(conn: Any) -> None:
    """Recreate only the derived FTS object after unrecoverable drift."""
    _execute(conn, "DROP TABLE IF EXISTS reviews_fts")
    _execute(conn,
        """CREATE VIRTUAL TABLE reviews_fts USING fts5(
            review_text,
            content='reviews',
            content_rowid='id',
            tokenize='unicode61'
        )"""
    )


def repair_review_text_projection(conn: Any) -> int:
    """Restore the searchable projection from ``reviews.data.review``."""
    result = _execute(
        conn,
        "UPDATE reviews SET review_text = COALESCE(json_extract(data, '$.review'), '')",
    )
    return int(result.rowcount or 0)


def rebuild_fts(conn: Any | None = None) -> None:
    """Repair the canonical projection, then rebuild FTS5 postings."""
    if conn is None:
        from . import db
        with db.get_connection() as owned:
            rebuild_fts(owned)
        return
    _drop_triggers(conn)
    try:
        repair_review_text_projection(conn)
        try:
            _execute(conn, "INSERT INTO reviews_fts(reviews_fts) VALUES ('rebuild')")
        except Exception:
            # A damaged FTS5 segment can reject even the canonical rebuild
            # command. Recreate only the derived index, never review rows.
            _recreate_external_fts(conn)
            _execute(conn, "INSERT INTO reviews_fts(reviews_fts) VALUES ('rebuild')")
    finally:
        _create_triggers(conn)


def repair_fts_integrity(conn: Any | None = None) -> dict[str, Any]:
    """Repair projection and postings, then return the verified result."""
    if conn is None:
        from . import db
        with db.get_connection() as owned:
            return repair_fts_integrity(owned)
    rebuild_fts(conn)
    return verify_fts_integrity(conn)


def verify_fts_integrity(conn: Any | None = None) -> dict[str, Any]:
    """Return a detailed integrity result without repairing the index.

    External-content SELECTs can read the content table even when the
    inverted index is empty.  The temporary fts5vocab(instance) table below
    reads the actual index postings, and MATCH probes validate that each
    non-empty canonical review has a posting for a token from its text.
    """
    if conn is None:
        from . import db
        with db.get_connection() as owned:
            return verify_fts_integrity(owned)

    rows = _execute(conn, "SELECT id, review_text, data FROM reviews").fetchall()
    canonical = len(rows)
    projection_drift = [int(row[0]) for row in rows if str(row[1] or "") != str(
        _execute(conn, "SELECT COALESCE(json_extract(?, '$.review'), '')", (row[2],)).fetchone()[0] or ""
    )]
    _execute(conn, "DROP TABLE IF EXISTS temp.reviews_fts_vocab")
    _execute(conn, "CREATE VIRTUAL TABLE temp.reviews_fts_vocab USING fts5vocab('main', 'reviews_fts', 'instance')")
    vocab_docs = {int(row[0]) for row in _execute(
        conn, "SELECT DISTINCT doc FROM temp.reviews_fts_vocab"
    ).fetchall()}
    expected_docs = {int(row[0]) for row in rows if _searchable_token(str(row[1] or ""))}
    indexed = len(vocab_docs)
    # Use actual posting doc IDs rather than SELECT * from external content.
    missing = sorted(expected_docs - vocab_docs)
    orphaned = sorted(vocab_docs - {int(row[0]) for row in rows})
    duplicate_rows = []
    probe_failures = []
    for row in rows:
        review_id, review_text = int(row[0]), str(row[1] or "")
        token = _searchable_token(review_text)
        if not token:
            continue
        quoted = '"' + token.replace('"', '""') + '"'
        found = _execute(conn,
            "SELECT 1 FROM reviews_fts WHERE rowid=? AND reviews_fts MATCH ? LIMIT 1",
            (review_id, quoted),
        ).fetchone()
        if found is None:
            probe_failures.append(review_id)
    result = {
        "ok": not missing and not orphaned and not duplicate_rows and not probe_failures and not projection_drift,
        "canonical_count": canonical,
        "indexed_count": indexed,
        "missing": missing,
        "orphaned": orphaned,
        "duplicates": duplicate_rows,
        "probe_failures": probe_failures,
        "projection_drift": projection_drift,
        "expected_searchable_count": len(expected_docs),
    }
    return result
