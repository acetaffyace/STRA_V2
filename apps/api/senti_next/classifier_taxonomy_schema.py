"""Migration for taxonomy-aware classifier cache identity (Stage 3E)."""
from __future__ import annotations

CLASSIFIER_TAXONOMY_MIGRATION_VERSION = 19
DESCRIPTION = "taxonomy snapshot and fingerprint in review label cache identity"


def migrate_classifier_taxonomy(conn) -> None:
    """Add classifier taxonomy provenance columns idempotently."""
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(review_labels)").fetchall()}
    if "taxonomy_snapshot_id" not in columns:
        conn.execute("ALTER TABLE review_labels ADD COLUMN taxonomy_snapshot_id TEXT")
    if "taxonomy_fingerprint" not in columns:
        conn.execute("ALTER TABLE review_labels ADD COLUMN taxonomy_fingerprint TEXT")

