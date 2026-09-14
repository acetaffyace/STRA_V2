"""Migration 28 for de-duplicated semantic review rollups."""
from __future__ import annotations

SEMANTIC_ROLLUP_MIGRATION_VERSION = 28
DESCRIPTION = "de-duplicated SemanticRun review topic and signal rollups"


def migrate_semantic_rollups(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS semantic_review_topic_rollups (
            rollup_id TEXT PRIMARY KEY,
            semantic_run_id TEXT NOT NULL,
            review_snapshot_id TEXT NOT NULL,
            core_topic_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(semantic_run_id, review_snapshot_id, core_topic_id),
            FOREIGN KEY(semantic_run_id) REFERENCES semantic_runs(semantic_run_id),
            FOREIGN KEY(review_snapshot_id) REFERENCES review_snapshots(review_snapshot_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS semantic_review_signal_rollups (
            rollup_id TEXT PRIMARY KEY,
            semantic_run_id TEXT NOT NULL,
            review_snapshot_id TEXT NOT NULL,
            core_topic_id TEXT NOT NULL,
            signal_type TEXT NOT NULL CHECK (signal_type IN ('issue', 'request', 'praise')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(semantic_run_id, review_snapshot_id, core_topic_id, signal_type),
            FOREIGN KEY(semantic_run_id) REFERENCES semantic_runs(semantic_run_id),
            FOREIGN KEY(review_snapshot_id) REFERENCES review_snapshots(review_snapshot_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_review_topic_rollups_run ON semantic_review_topic_rollups(semantic_run_id, core_topic_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_review_signal_rollups_run ON semantic_review_signal_rollups(semantic_run_id, core_topic_id, signal_type)")
    conn.execute("""CREATE TRIGGER IF NOT EXISTS trg_semantic_review_topic_rollups_immutable_update
        BEFORE UPDATE ON semantic_review_topic_rollups
        BEGIN SELECT RAISE(ABORT, 'semantic_rollup_immutable'); END""")
    conn.execute("""CREATE TRIGGER IF NOT EXISTS trg_semantic_review_topic_rollups_immutable_delete
        BEFORE DELETE ON semantic_review_topic_rollups
        BEGIN SELECT RAISE(ABORT, 'semantic_rollup_immutable'); END""")
    conn.execute("""CREATE TRIGGER IF NOT EXISTS trg_semantic_review_signal_rollups_immutable_update
        BEFORE UPDATE ON semantic_review_signal_rollups
        BEGIN SELECT RAISE(ABORT, 'semantic_rollup_immutable'); END""")
    conn.execute("""CREATE TRIGGER IF NOT EXISTS trg_semantic_review_signal_rollups_immutable_delete
        BEFORE DELETE ON semantic_review_signal_rollups
        BEGIN SELECT RAISE(ABORT, 'semantic_rollup_immutable'); END""")
