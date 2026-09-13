"""SQLite schema for the optional Stage 3A semantic index."""
from __future__ import annotations

SEMANTIC_INDEX_MIGRATION_VERSION = 14
DESCRIPTION = "full-population semantic index and reusable embedding cache"


def migrate_semantic_index(conn) -> None:
    """Create Stage 3A tables additively and idempotently.

    The tables are deliberately independent from Research Core result tables.
    A semantic index references a research run and its population fingerprint;
    it never changes that run's denominator or report.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_index_runs (
            index_id TEXT PRIMARY KEY,
            research_run_id TEXT NOT NULL,
            app_id INTEGER NOT NULL,
            population_fingerprint TEXT NOT NULL,
            contract_json TEXT NOT NULL,
            model_id TEXT NOT NULL,
            model_revision TEXT NOT NULL,
            artifact_sha256 TEXT NOT NULL,
            population_n INTEGER NOT NULL,
            eligible_review_n INTEGER NOT NULL,
            indexed_review_n INTEGER NOT NULL,
            semantic_unit_n INTEGER NOT NULL,
            unique_embedding_n INTEGER NOT NULL,
            cache_hit_n INTEGER NOT NULL,
            cache_miss_n INTEGER NOT NULL,
            status TEXT NOT NULL,
            index_fingerprint TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT,
            error TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_semantic_index_runs_research_run "
        "ON semantic_index_runs(research_run_id, population_fingerprint)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_index_members (
            index_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            review_text_hash TEXT,
            eligible INTEGER NOT NULL,
            exclusion_reason TEXT,
            semantic_unit_count INTEGER NOT NULL,
            PRIMARY KEY(index_id, review_id),
            FOREIGN KEY(index_id) REFERENCES semantic_index_runs(index_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_index_units (
            index_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            unit_index INTEGER NOT NULL,
            semantic_text_hash TEXT NOT NULL,
            semantic_text TEXT NOT NULL,
            token_start INTEGER NOT NULL,
            token_end INTEGER NOT NULL,
            token_count INTEGER NOT NULL,
            embedding_key TEXT NOT NULL,
            PRIMARY KEY(index_id, review_id, unit_index),
            FOREIGN KEY(index_id) REFERENCES semantic_index_runs(index_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_semantic_index_units_embedding_key "
        "ON semantic_index_units(embedding_key)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_embedding_cache (
            embedding_key TEXT PRIMARY KEY,
            semantic_text_hash TEXT NOT NULL,
            model_id TEXT NOT NULL,
            model_revision TEXT NOT NULL,
            artifact_sha256 TEXT NOT NULL,
            preprocessing_version TEXT NOT NULL,
            chunking_version TEXT NOT NULL,
            prefix_policy TEXT NOT NULL,
            pooling TEXT NOT NULL,
            normalization TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            dtype TEXT NOT NULL,
            vector_blob BLOB NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
