"""Stage 4A.1 additive persistence for validation runs and measurement bundles."""
from __future__ import annotations

SEMANTIC_MEASUREMENT_MIGRATION_VERSION = 20
DESCRIPTION = "classifier validation runs and semantic measurement bundles"


def migrate_semantic_measurement(conn) -> None:
    """Create the immutable validation/bundle ledger and its activation events."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS classifier_validation_runs (
            validation_run_id TEXT PRIMARY KEY,
            validation_dataset_id TEXT NOT NULL,
            validation_dataset_fingerprint TEXT NOT NULL,
            language_scope TEXT,
            taxonomy_snapshot_id TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            taxonomy_fingerprint TEXT NOT NULL,
            classifier_provider TEXT NOT NULL,
            classifier_model_id TEXT NOT NULL,
            classifier_prompt_version TEXT NOT NULL,
            classifier_schema_version TEXT NOT NULL,
            classifier_taxonomy_contract_fingerprint TEXT NOT NULL,
            gold_item_n INTEGER NOT NULL,
            prediction_item_n INTEGER NOT NULL,
            matched_prediction_n INTEGER NOT NULL,
            evaluation_coverage REAL NOT NULL,
            topic_metrics_json TEXT NOT NULL,
            issue_metrics_json TEXT,
            request_metrics_json TEXT,
            gate_policy_version TEXT NOT NULL,
            gate_status TEXT NOT NULL,
            gate_reasons_json TEXT NOT NULL,
            limitations_json TEXT NOT NULL,
            scorer_report_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_measurement_bundles (
            bundle_id TEXT PRIMARY KEY,
            taxonomy_snapshot_id TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            taxonomy_fingerprint TEXT NOT NULL,
            classifier_provider TEXT NOT NULL,
            classifier_model_id TEXT NOT NULL,
            classifier_prompt_version TEXT NOT NULL,
            classifier_schema_version TEXT NOT NULL,
            validation_run_id TEXT,
            validation_status TEXT NOT NULL,
            measurement_status TEXT NOT NULL,
            limitations_json TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            activated_at TEXT,
            retired_at TEXT,
            FOREIGN KEY(validation_run_id) REFERENCES classifier_validation_runs(validation_run_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_measurement_activation_events (
            activation_event_id TEXT PRIMARY KEY,
            bundle_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            operator TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(bundle_id) REFERENCES semantic_measurement_bundles(bundle_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_classifier_validation_dataset
        ON classifier_validation_runs(validation_dataset_id, created_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_measurement_bundles_status
        ON semantic_measurement_bundles(measurement_status, created_at DESC)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_measurement_bundles_one_active
        ON semantic_measurement_bundles(is_active)
        WHERE is_active = 1
        """
    )
