"""SQLite schema for independent Stage 3B discovery/audit results."""
from __future__ import annotations

SEMANTIC_DISCOVERY_MIGRATION_VERSION = 15
DESCRIPTION = "open-set semantic discovery and taxonomy audit results"


def migrate_semantic_discovery(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_discovery_runs (
            discovery_run_id TEXT PRIMARY KEY,
            semantic_index_id TEXT NOT NULL,
            research_run_id TEXT NOT NULL,
            population_fingerprint TEXT NOT NULL,
            semantic_index_fingerprint TEXT NOT NULL,
            discovery_contract_json TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            population_n INTEGER NOT NULL,
            indexed_review_n INTEGER NOT NULL,
            semantic_unit_n INTEGER NOT NULL,
            dense_region_n INTEGER NOT NULL DEFAULT 0,
            rare_region_n INTEGER NOT NULL DEFAULT 0,
            outlier_review_n INTEGER NOT NULL DEFAULT 0,
            unclustered_review_share REAL,
            status TEXT NOT NULL,
            discovery_fingerprint TEXT,
            report_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT,
            error TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_semantic_discovery_runs_index "
        "ON semantic_discovery_runs(semantic_index_id, semantic_index_fingerprint)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_discovery_regions (
            discovery_run_id TEXT NOT NULL,
            region_id TEXT NOT NULL,
            discovery_type TEXT NOT NULL,
            support_review_n INTEGER NOT NULL,
            support_unit_n INTEGER NOT NULL,
            unique_text_n INTEGER NOT NULL,
            cohesion REAL,
            stability_score REAL,
            stability TEXT NOT NULL,
            taxonomy_coverage_status TEXT NOT NULL,
            region_json TEXT NOT NULL,
            PRIMARY KEY(discovery_run_id, region_id),
            FOREIGN KEY(discovery_run_id) REFERENCES semantic_discovery_runs(discovery_run_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_discovery_members (
            discovery_run_id TEXT NOT NULL,
            region_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            semantic_unit_id TEXT,
            membership_strength REAL,
            distance_similarity REAL,
            role TEXT NOT NULL,
            PRIMARY KEY(discovery_run_id, region_id, review_id, semantic_unit_id),
            FOREIGN KEY(discovery_run_id, region_id) REFERENCES semantic_discovery_regions(discovery_run_id, region_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS taxonomy_audit_regions (
            discovery_run_id TEXT NOT NULL,
            region_id TEXT NOT NULL,
            coverage_status TEXT NOT NULL,
            support_review_n INTEGER NOT NULL,
            labeled_review_n INTEGER NOT NULL,
            unlabeled_review_n INTEGER NOT NULL,
            taxonomy_coverage_rate REAL,
            audit_json TEXT NOT NULL,
            PRIMARY KEY(discovery_run_id, region_id),
            FOREIGN KEY(discovery_run_id, region_id) REFERENCES semantic_discovery_regions(discovery_run_id, region_id) ON DELETE CASCADE
        )
        """
    )
