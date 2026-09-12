"""P0.2a generalized analysis_runs schema migration."""
from __future__ import annotations

from typing import Any


RUN_TYPE_VERSION_REVIEW = "version_review"
RUN_TYPE_GENERAL_ANALYSIS = "general_analysis"
RUN_TYPE_LEGACY = "legacy"


def analysis_runs_columns(conn: Any) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(analysis_runs)").fetchall()}


def migrate_analysis_runs(conn: Any) -> None:
    """Expand the legacy Version Review table into the P0.2a run entity."""
    columns = analysis_runs_columns(conn)
    if "run_type" in columns:
        return

    conn.execute(
        """CREATE TABLE analysis_runs_v3 (
            run_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            target_app_id INTEGER NOT NULL,
            event_id TEXT,
            run_type TEXT NOT NULL DEFAULT 'version_review',
            config TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'created',
            metrics TEXT,
            error TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            data_cutoff TEXT,
            window_start TEXT,
            window_end TEXT,
            requested_languages TEXT,
            requested_review_count INTEGER,
            available_matching_reviews INTEGER,
            retrieved_count INTEGER,
            deduplicated_count INTEGER,
            analysis_population_count INTEGER,
            valid_review_count INTEGER,
            classified_count INTEGER,
            fallback_count INTEGER,
            enriched_count INTEGER,
            scope_fingerprint TEXT,
            taxonomy_version TEXT,
            prompt_version TEXT,
            analysis_version TEXT,
            provider TEXT,
            model_id TEXT,
            FOREIGN KEY(event_id) REFERENCES version_events(event_id)
        )"""
    )
    conn.execute(
        """INSERT INTO analysis_runs_v3
            (run_id, user_id, target_app_id, event_id, run_type, config,
             status, metrics, error, created_at, updated_at)
        SELECT run_id, user_id, target_app_id, event_id, ?, config,
               status, metrics, error, created_at, updated_at
        FROM analysis_runs""",
        (RUN_TYPE_VERSION_REVIEW,),
    )
    conn.execute("DROP TABLE analysis_runs")
    conn.execute("ALTER TABLE analysis_runs_v3 RENAME TO analysis_runs")
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_created
           ON analysis_runs(user_id, created_at DESC)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_analysis_runs_target_app
           ON analysis_runs(target_app_id, created_at DESC)"""
    )


def recover_interrupted_general_runs(conn: Any) -> int:
    """Fail queued/running general runs left behind by a process restart."""
    sql = """UPDATE analysis_runs
           SET status='failed', error='interrupted by process restart',
               completed_at=COALESCE(completed_at, datetime('now')),
               updated_at=datetime('now')
         WHERE run_type='general_analysis' AND status IN ('queued', 'running')"""
    result = conn.exec_driver_sql(sql) if hasattr(conn, "exec_driver_sql") else conn.execute(sql)
    return int(result.rowcount or 0)


def recover_invalid_version_runs(conn: Any) -> int:
    """Close version runs that were persisted as active without a valid start."""
    sql = """UPDATE analysis_runs
           SET status='failed', error='PROCESS_INTERRUPTED_BEFORE_START',
               completed_at=COALESCE(completed_at, datetime('now')),
               updated_at=datetime('now')
         WHERE run_type='version_review'
           AND ((status='created' AND created_at < datetime('now', '-10 minutes'))
             OR (status='running' AND (started_at IS NULL OR phase IS NULL
                 OR updated_at < datetime('now', '-20 minutes'))))"""
    result = conn.exec_driver_sql(sql) if hasattr(conn, "exec_driver_sql") else conn.execute(sql)
    return int(result.rowcount or 0)


def migrate_analysis_run_population_columns(conn: Any) -> None:
    """Add explicit ingestion/population counters for Web MVP runs."""
    columns = analysis_runs_columns(conn)
    for name in ("available_matching_reviews", "deduplicated_count", "analysis_population_count"):
        if name not in columns:
            conn.execute(f"ALTER TABLE analysis_runs ADD COLUMN {name} INTEGER")
