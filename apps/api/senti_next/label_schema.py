"""P0.3a review-label provenance migration."""
from __future__ import annotations

from typing import Any


_ADDITIVE_COLUMNS = {
    "label_origin": "TEXT",
    "validated": "INTEGER",
    "taxonomy_version": "TEXT",
    "provider": "TEXT",
    "model_id": "TEXT",
    "classification_input_hash": "TEXT",
    "was_truncated": "INTEGER",
    "original_char_count": "INTEGER",
    "processed_char_count": "INTEGER",
    "generated_at": "TEXT",
}


def migrate_review_label_provenance(conn: Any) -> None:
    """Add provenance columns without fabricating unknown legacy identity."""
    existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(review_labels)").fetchall()}
    for name, column_type in _ADDITIVE_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE review_labels ADD COLUMN {name} {column_type}")
    conn.execute(
        "UPDATE review_labels SET label_origin='legacy' WHERE label_origin IS NULL"
    )
