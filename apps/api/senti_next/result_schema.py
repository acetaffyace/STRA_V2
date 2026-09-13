"""General-analysis result schema and additive Research Core migration."""
from __future__ import annotations

import json
from typing import Any


# Migration 12 is already used by the Web MVP UX schema in this repository.
# Keep this migration additive and use the next ledger version rather than
# colliding with that existing migration.
RESEARCH_RESULT_MIGRATION_VERSION = 13


def migrate_analysis_run_results(conn: Any) -> None:
    """Create the immutable result table; do not backfill unverifiable history."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS analysis_run_results (
            run_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            app_id INTEGER NOT NULL,
            metadata TEXT,
            insights TEXT,
            reviews TEXT,
            research_report TEXT,
            semantic_status TEXT,
            snapshot_hash TEXT,
            context_hash TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
        )"""
    )


def migrate_research_result_fields(conn: Any) -> None:
    """Add first-class Research Core fields and backfill only exact envelopes.

    Stage 2P.3 temporarily stored these values under ``insights``.  Migration
    13 copies those exact keys when present, without trying to reconstruct a
    report from older semantic metrics.  The operation is intentionally
    additive and idempotent.
    """
    for table in ("analysis_results", "analysis_run_results"):
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if not columns:
            continue
        if "research_report" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN research_report TEXT")
        if "semantic_status" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN semantic_status TEXT")

        rows = conn.execute(
            f"SELECT rowid, insights, research_report, semantic_status FROM {table}"
        ).fetchall()
        for rowid, raw_insights, existing_report, existing_status in rows:
            if not isinstance(raw_insights, str):
                continue
            try:
                insights = json.loads(raw_insights)
            except (TypeError, ValueError):
                continue
            if not isinstance(insights, dict):
                continue
            updates = {}
            if existing_report is None and "research_report" in insights:
                updates["research_report"] = json.dumps(insights["research_report"])
            if existing_status is None and "semantic_status" in insights:
                updates["semantic_status"] = json.dumps(insights["semantic_status"])
            if updates:
                assignments = ", ".join(f"{key} = ?" for key in updates)
                conn.execute(
                    f"UPDATE {table} SET {assignments} WHERE rowid = ?",
                    (*updates.values(), rowid),
                )
