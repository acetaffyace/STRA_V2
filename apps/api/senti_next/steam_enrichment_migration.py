"""Additive, idempotent Steam review enrichment migration."""
from __future__ import annotations

import sqlite3

ENRICHMENT_MIGRATION_VERSION = 11
DESCRIPTION = "Steam review enrichment canonical fields and raw-payload backfill"


def migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(reviews)").fetchall()}
    definitions = {
        "developer_response": "TEXT",
        "timestamp_dev_responded": "INTEGER",
        "steam_purchase": "INTEGER",
        "received_for_free": "INTEGER",
        "primarily_steam_deck": "INTEGER",
    }
    for name, definition in definitions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE reviews ADD COLUMN {name} {definition}")

    # Deterministic backfill only when the exact source key exists in stored
    # JSON. Missing historical source data remains NULL/unknown.
    conn.execute("""
        UPDATE reviews SET
            developer_response = CASE WHEN json_type(data, '$.developer_response') IS NOT NULL
                THEN json_extract(data, '$.developer_response') ELSE developer_response END,
            timestamp_dev_responded = CASE WHEN json_type(data, '$.timestamp_dev_responded') IS NOT NULL
                THEN CAST(json_extract(data, '$.timestamp_dev_responded') AS INTEGER) ELSE timestamp_dev_responded END,
            steam_purchase = CASE WHEN json_type(data, '$.steam_purchase') IS NOT NULL
                THEN CAST(json_extract(data, '$.steam_purchase') AS INTEGER) ELSE steam_purchase END,
            received_for_free = CASE WHEN json_type(data, '$.received_for_free') IS NOT NULL
                THEN CAST(json_extract(data, '$.received_for_free') AS INTEGER) ELSE received_for_free END,
            primarily_steam_deck = CASE WHEN json_type(data, '$.primarily_steam_deck') IS NOT NULL
                THEN CAST(json_extract(data, '$.primarily_steam_deck') AS INTEGER) ELSE primarily_steam_deck END
    """)
