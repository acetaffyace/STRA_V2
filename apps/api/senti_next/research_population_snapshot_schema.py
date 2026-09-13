"""Migration 24 for immutable Research Population snapshots."""
from __future__ import annotations

DESCRIPTION = "immutable research population snapshots"
RESEARCH_POPULATION_SNAPSHOT_MIGRATION_VERSION = 24


def migrate_research_population_snapshots(conn) -> None:
    """Create additive, idempotent tables for exact per-run populations."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS analysis_run_populations (
            run_id TEXT PRIMARY KEY,
            app_id INTEGER NOT NULL,
            population_fingerprint TEXT NOT NULL,
            population_n INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS analysis_run_population_items (
            run_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            review_id TEXT NOT NULL,
            review_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(run_id, review_id),
            UNIQUE(run_id, ordinal),
            FOREIGN KEY(run_id) REFERENCES analysis_run_populations(run_id)
        )"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_analysis_run_population_items_ordinal
           ON analysis_run_population_items(run_id, ordinal)"""
    )
