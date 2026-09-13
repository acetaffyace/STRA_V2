"""Stage 4A.2 immutable classification materialization persistence."""
from __future__ import annotations

from typing import Any


CLASSIFICATION_MATERIALIZATION_MIGRATION_VERSION = 22
DESCRIPTION = "frozen classification materializations"


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def migrate_classification_materialization(conn: Any) -> None:
    """Create the immutable run-level classification ledger additively."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS classification_materializations (
            materialization_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL UNIQUE,
            app_id INTEGER NOT NULL,
            measurement_bundle_id TEXT NOT NULL,
            measurement_status TEXT NOT NULL,
            validation_run_id TEXT,
            validation_status TEXT,
            taxonomy_snapshot_id TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            taxonomy_fingerprint TEXT NOT NULL,
            classifier_provider TEXT NOT NULL,
            classifier_model_id TEXT NOT NULL,
            classifier_prompt_version TEXT NOT NULL,
            classifier_schema_version TEXT NOT NULL,
            population_fingerprint TEXT NOT NULL,
            population_n INTEGER NOT NULL,
            materialized_n INTEGER NOT NULL,
            validated_llm_n INTEGER NOT NULL,
            fallback_n INTEGER NOT NULL,
            missing_n INTEGER NOT NULL,
            materialization_fingerprint TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(measurement_bundle_id) REFERENCES semantic_measurement_bundles(bundle_id),
            FOREIGN KEY(validation_run_id) REFERENCES classifier_validation_runs(validation_run_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS classification_materialization_items (
            materialization_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            item_status TEXT NOT NULL,
            review_hash TEXT NOT NULL,
            classification_input_hash TEXT NOT NULL,
            label_origin TEXT,
            validated INTEGER NOT NULL DEFAULT 0,
            provider TEXT,
            model_id TEXT,
            prompt_version TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            taxonomy_snapshot_id TEXT NOT NULL,
            taxonomy_fingerprint TEXT NOT NULL,
            payload_json TEXT,
            generated_at TEXT,
            PRIMARY KEY(materialization_id, review_id),
            FOREIGN KEY(materialization_id) REFERENCES classification_materializations(materialization_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_classification_materializations_app_created
        ON classification_materializations(app_id, created_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_classification_materialization_items_review
        ON classification_materialization_items(review_id)
        """
    )

    # These are direct references on the existing run entity.  They are
    # intentionally nullable so every pre-4A.2 run remains readable.
    if "analysis_runs" in {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}:
        existing = _columns(conn, "analysis_runs")
        for name, column_type in {
            "measurement_bundle_id": "TEXT",
            "classification_materialization_id": "TEXT",
            "taxonomy_snapshot_id": "TEXT",
            "taxonomy_fingerprint": "TEXT",
            "measurement_status": "TEXT",
            "validation_run_id": "TEXT",
            "validation_status": "TEXT",
        }.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE analysis_runs ADD COLUMN {name} {column_type}")

