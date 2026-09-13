"""Migration 21 for actual classifier execution provenance."""
from __future__ import annotations

CLASSIFIER_VALIDATION_EXECUTION_MIGRATION_VERSION = 21
DESCRIPTION = "classifier validation execution provenance hardening"


def migrate_classifier_validation_execution(conn) -> None:
    """Add nullable provenance fields without rewriting Migration 20 history."""
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(classifier_validation_runs)").fetchall()}
    if "execution_mode" not in columns:
        conn.execute("ALTER TABLE classifier_validation_runs ADD COLUMN execution_mode TEXT")
    if "actual_model_id" not in columns:
        conn.execute("ALTER TABLE classifier_validation_runs ADD COLUMN actual_model_id TEXT")
    if "execution_identity_fingerprint" not in columns:
        conn.execute("ALTER TABLE classifier_validation_runs ADD COLUMN execution_identity_fingerprint TEXT")
    if "actual_provider" not in columns:
        conn.execute("ALTER TABLE classifier_validation_runs ADD COLUMN actual_provider TEXT")
    if "gate_policy_json" not in columns:
        conn.execute("ALTER TABLE classifier_validation_runs ADD COLUMN gate_policy_json TEXT")
