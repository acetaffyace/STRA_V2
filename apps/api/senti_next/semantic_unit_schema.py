"""Migration 26 for immutable semantic units, mentions and evidence identity."""
from __future__ import annotations

SEMANTIC_UNIT_MIGRATION_VERSION = 26
DESCRIPTION = "immutable SemanticUnit and SemanticMention evidence identity"


def migrate_semantic_units(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS semantic_units (
            semantic_unit_id TEXT PRIMARY KEY,
            semantic_run_id TEXT NOT NULL,
            review_snapshot_id TEXT NOT NULL,
            source_content_hash TEXT NOT NULL,
            start_byte_offset INTEGER NOT NULL CHECK (start_byte_offset >= 0),
            end_byte_offset INTEGER NOT NULL CHECK (end_byte_offset >= start_byte_offset),
            text_snapshot TEXT NOT NULL,
            segmentation_version TEXT NOT NULL,
            semantic_unit_schema_version TEXT NOT NULL DEFAULT 'semantic-unit-v1',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(semantic_run_id, review_snapshot_id, start_byte_offset, end_byte_offset),
            FOREIGN KEY(semantic_run_id) REFERENCES semantic_runs(semantic_run_id),
            FOREIGN KEY(review_snapshot_id) REFERENCES review_snapshots(review_snapshot_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS semantic_mentions (
            mention_id TEXT PRIMARY KEY,
            semantic_run_id TEXT NOT NULL,
            semantic_unit_id TEXT NOT NULL,
            core_topic_id TEXT NOT NULL,
            secondary_topic_id TEXT,
            signal_type TEXT CHECK (signal_type IS NULL OR signal_type IN ('issue', 'request', 'praise')),
            assignment_source TEXT NOT NULL,
            similarity_score REAL,
            calibrated_confidence REAL CHECK (calibrated_confidence IS NULL OR (calibrated_confidence >= 0 AND calibrated_confidence <= 1)),
            decision_band TEXT NOT NULL,
            prototype_version TEXT NOT NULL,
            adjudication_ref TEXT,
            semantic_mention_schema_version TEXT NOT NULL DEFAULT 'semantic-mention-v1',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(semantic_run_id) REFERENCES semantic_runs(semantic_run_id),
            FOREIGN KEY(semantic_unit_id) REFERENCES semantic_units(semantic_unit_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_units_run_review ON semantic_units(semantic_run_id, review_snapshot_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_mentions_run_topic ON semantic_mentions(semantic_run_id, core_topic_id)")
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_semantic_units_immutable_update
        BEFORE UPDATE ON semantic_units
        BEGIN SELECT RAISE(ABORT, 'semantic_unit_immutable'); END"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_semantic_units_immutable_delete
        BEFORE DELETE ON semantic_units
        BEGIN SELECT RAISE(ABORT, 'semantic_unit_immutable'); END"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_semantic_mentions_immutable_update
        BEFORE UPDATE ON semantic_mentions
        BEGIN SELECT RAISE(ABORT, 'semantic_mention_immutable'); END"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_semantic_mentions_immutable_delete
        BEFORE DELETE ON semantic_mentions
        BEGIN SELECT RAISE(ABORT, 'semantic_mention_immutable'); END"""
    )
