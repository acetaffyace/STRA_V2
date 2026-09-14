"""Additive M0 persistence for the canonical research identity graph."""
from __future__ import annotations


def migrate_foundation_contracts(conn) -> None:
    """Create immutable snapshot/run/job tables.

    This function is intentionally idempotent and is called as part of the
    existing migration-24 bridge so current databases retain their historical
    schema ledger while receiving the new additive contract.
    """
    statements = [
        """
        CREATE TABLE IF NOT EXISTS review_snapshots (
            review_snapshot_id TEXT PRIMARY KEY,
            steam_review_id TEXT NOT NULL,
            app_id INTEGER NOT NULL,
            content_text TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            voted_up INTEGER,
            language TEXT,
            timestamp_created INTEGER,
            timestamp_updated INTEGER,
            payload_json TEXT NOT NULL,
            provider_metadata_json TEXT NOT NULL DEFAULT '{}',
            fetched_at TEXT NOT NULL,
            snapshot_schema_version TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(app_id, steam_review_id, content_hash)
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_review_snapshots_review
            ON review_snapshots(app_id, steam_review_id, fetched_at DESC)
        """,

        """
        CREATE TABLE IF NOT EXISTS population_snapshots (
            population_snapshot_id TEXT PRIMARY KEY,
            app_id INTEGER NOT NULL,
            sampling_contract_json TEXT NOT NULL,
            sampling_contract_hash TEXT NOT NULL,
            acquisition_provenance_json TEXT NOT NULL DEFAULT '{}',
            membership_count INTEGER NOT NULL CHECK (membership_count >= 0),
            population_hash TEXT NOT NULL,
            anchor_time TEXT NOT NULL,
            start_at_utc TEXT,
            end_at_utc TEXT,
            snapshot_schema_version TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_population_snapshots_app
            ON population_snapshots(app_id, created_at DESC)
        """,

        """
        CREATE TABLE IF NOT EXISTS population_snapshot_members (
            population_snapshot_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            review_snapshot_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            PRIMARY KEY(population_snapshot_id, ordinal),
            UNIQUE(population_snapshot_id, review_snapshot_id),
            FOREIGN KEY(population_snapshot_id) REFERENCES population_snapshots(population_snapshot_id),
            FOREIGN KEY(review_snapshot_id) REFERENCES review_snapshots(review_snapshot_id)
        );
        """,

        """
        CREATE TABLE IF NOT EXISTS research_runs (
            run_id TEXT PRIMARY KEY,
            run_type TEXT NOT NULL DEFAULT 'snapshot',
            app_id INTEGER NOT NULL,
            sampling_contract_json TEXT NOT NULL,
            sampling_contract_version TEXT NOT NULL,
            acquisition_provenance_json TEXT NOT NULL DEFAULT '{}',
            population_snapshot_id TEXT NOT NULL,
            population_hash TEXT NOT NULL,
            anchor_time TEXT NOT NULL,
            research_core_version TEXT NOT NULL,
            metric_schema_version TEXT NOT NULL,
            time_semantics_version TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'QUEUED',
            created_by_job_id TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            validity_status TEXT NOT NULL DEFAULT 'VALID',
            immutable_result_ref TEXT,
            FOREIGN KEY(population_snapshot_id) REFERENCES population_snapshots(population_snapshot_id)
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_research_runs_app_created
            ON research_runs(app_id, created_at DESC)
        """,

        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            target_resource_type TEXT NOT NULL,
            target_resource_id TEXT,
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'QUEUED',
            stage TEXT NOT NULL DEFAULT 'queued',
            progress_current INTEGER NOT NULL DEFAULT 0 CHECK (progress_current >= 0),
            progress_total INTEGER NOT NULL DEFAULT 0 CHECK (progress_total >= 0),
            progress_unit TEXT NOT NULL DEFAULT 'items',
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            heartbeat_at TEXT,
            retryable INTEGER NOT NULL DEFAULT 0,
            cancel_requested_at TEXT,
            error_code TEXT,
            error_detail TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            UNIQUE(job_type, idempotency_key)
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_jobs_status
            ON jobs(status, created_at)
        """,

        """
        CREATE TRIGGER IF NOT EXISTS trg_population_snapshots_immutable_update
        BEFORE UPDATE ON population_snapshots
        BEGIN SELECT RAISE(ABORT, 'population_snapshot_immutable'); END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_population_snapshots_immutable_delete
        BEFORE DELETE ON population_snapshots
        BEGIN SELECT RAISE(ABORT, 'population_snapshot_immutable'); END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_population_members_immutable_update
        BEFORE UPDATE ON population_snapshot_members
        BEGIN SELECT RAISE(ABORT, 'population_snapshot_members_immutable'); END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_population_members_immutable_delete
        BEFORE DELETE ON population_snapshot_members
        BEGIN SELECT RAISE(ABORT, 'population_snapshot_members_immutable'); END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_review_snapshots_immutable_update
        BEFORE UPDATE ON review_snapshots
        BEGIN SELECT RAISE(ABORT, 'review_snapshot_immutable'); END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_review_snapshots_immutable_delete
        BEFORE DELETE ON review_snapshots
        BEGIN SELECT RAISE(ABORT, 'review_snapshot_immutable'); END;
        """,
    ]
    for statement in statements:
        conn.execute(statement)
    # Development databases may have created the first M0 table shape before
    # provenance was added.  This additive check keeps that upgrade safe.
    population_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(population_snapshots)").fetchall()}
    if "acquisition_provenance_json" not in population_columns:
        conn.execute("ALTER TABLE population_snapshots ADD COLUMN acquisition_provenance_json TEXT NOT NULL DEFAULT '{}'")
