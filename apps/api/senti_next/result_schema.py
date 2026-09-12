"""P0.2c immutable general-analysis result schema migration."""
from __future__ import annotations

from typing import Any


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
            snapshot_hash TEXT,
            context_hash TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
        )"""
    )
