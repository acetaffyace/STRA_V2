"""Stage 4A.3 additive persistence for canonical semantic results."""
from __future__ import annotations

from typing import Any


SEMANTIC_MEASUREMENT_RESULT_MIGRATION_VERSION = 23
DESCRIPTION = "canonical semantic measurement and unified research result"


def migrate_semantic_measurement_result(conn: Any) -> None:
    """Add canonical semantic and unified result JSON columns without backfill."""
    for table in ("analysis_results", "analysis_run_results"):
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if not columns:
            continue
        for name in ("semantic_measurement_result", "unified_research_result"):
            if name not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} TEXT")

