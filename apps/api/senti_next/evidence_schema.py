"""P0.4 immutable chat evidence metadata migration."""
from __future__ import annotations

from typing import Any


def migrate_chat_evidence(conn: Any) -> None:
    existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
    if "evidence" not in existing:
        conn.execute("ALTER TABLE chat_messages ADD COLUMN evidence TEXT")
