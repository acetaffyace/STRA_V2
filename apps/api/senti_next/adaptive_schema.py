"""Schema migration for immutable Adaptive Analysis Design snapshots."""
from __future__ import annotations

from typing import Any


ADAPTIVE_SCHEMA_VERSION = 10


def migrate_adaptive_analysis(conn: Any) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS analysis_designs (
            design_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL UNIQUE,
            app_id INTEGER NOT NULL,
            schema_version TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_designs_app ON analysis_designs(app_id, created_at DESC)")

    # Additive event provenance fields.  Keep event_date for legacy callers;
    # these columns make the adaptive layer explicit about precision and
    # uncertainty without creating a parallel event catalog.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(version_events)").fetchall()}
    additions = {
        "published_at": "TEXT",
        "effective_at": "TEXT",
        "effective_at_start": "TEXT",
        "effective_at_end": "TEXT",
        "anchor_precision": "TEXT NOT NULL DEFAULT 'day'",
        "source_quality": "TEXT NOT NULL DEFAULT 'unknown'",
        "event_status": "TEXT NOT NULL DEFAULT 'unresolved'",
        "concurrent_event_group": "TEXT",
    }
    for name, declaration in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE version_events ADD COLUMN {name} {declaration}")
