"""Migration 16: context materializations for immutable discovery structures."""
from __future__ import annotations

SEMANTIC_DISCOVERY_MATERIALIZATION_MIGRATION_VERSION = 16
DESCRIPTION = "semantic discovery structure/context identity and materializations"


def _columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column_if_missing(conn, table: str, column: str, declaration: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def migrate_semantic_discovery_materializations(conn) -> None:
    """Additive/idempotent migration; v15 tables and rows remain untouched."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_discovery_materializations (
            materialization_id TEXT PRIMARY KEY,
            structure_run_id TEXT NOT NULL,
            structure_fingerprint TEXT NOT NULL,
            context_schema_version TEXT NOT NULL,
            context_fingerprint TEXT NOT NULL,
            semantic_index_id TEXT NOT NULL,
            research_run_id TEXT NOT NULL,
            population_fingerprint TEXT NOT NULL,
            semantic_index_fingerprint TEXT NOT NULL,
            report_json TEXT,
            status TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_semantic_discovery_materializations_structure "
        "ON semantic_discovery_materializations(structure_fingerprint, context_fingerprint)"
    )
    # These columns make the v15 row a reusable, context-free structure cache.
    # Existing reports remain readable; NULL means the row predates v2 identity.
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='semantic_discovery_runs'").fetchone():
        _add_column_if_missing(conn, "semantic_discovery_runs", "structure_run_id", "TEXT")
        _add_column_if_missing(conn, "semantic_discovery_runs", "structure_fingerprint", "TEXT")
        _add_column_if_missing(conn, "semantic_discovery_runs", "structure_schema_version", "TEXT")
        _add_column_if_missing(conn, "semantic_discovery_runs", "structure_json", "TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_semantic_discovery_runs_structure "
            "ON semantic_discovery_runs(structure_run_id, status)"
        )
