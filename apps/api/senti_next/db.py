"""Database engine configuration (SQLite)."""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool, StaticPool

from . import label_schema, result_schema

logger = logging.getLogger(__name__)

# Signals when init_db() and logging setup have completed.
# Checked by the health endpoint and startup gate middleware.
startup_complete = threading.Event()

_engine: Optional[Engine] = None


def _default_sqlite_path() -> str:
    """Return the default SQLite database path using platformdirs."""
    try:
        from platformdirs import user_data_dir
        data_dir = Path(user_data_dir("SentiNext", "SentiNext"))
    except ImportError:
        # Fallback if platformdirs is not installed
        data_dir = Path.home() / ".sentinext" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "sentinext.db")


def get_database_url() -> str:
    """Get SQLite database URL.

    Environment variables:
        DATABASE_URL: Full sqlite:/// URL (optional, defaults to platformdirs location)
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("sqlite"):
            return database_url
        raise RuntimeError(
            "DATABASE_URL must be a SQLite URL (sqlite:///...). "
            "PostgreSQL is no longer supported — SentiNext uses SQLite for all deployments."
        )

    db_path = _default_sqlite_path()
    logger.info("No DATABASE_URL set, defaulting to SQLite: %s", db_path)
    return f"sqlite:///{db_path}"


def get_engine() -> Engine:
    """Get or create the SQLAlchemy engine."""
    global _engine
    if _engine is not None:
        return _engine

    url = get_database_url()

    # In-memory SQLite needs StaticPool so all connections share the same DB.
    # File-based SQLite uses NullPool for safe multi-thread concurrency.
    is_memory = url in ("sqlite://", "sqlite:///:memory:")
    pool_class = StaticPool if is_memory else NullPool

    _engine = create_engine(
        url,
        poolclass=pool_class,
        connect_args={"check_same_thread": False},
        echo=os.getenv("SENTINEXT_DB_ECHO", "").lower() in ("1", "true"),
    )

    # Enable WAL mode and foreign keys for better concurrency
    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    logger.info("Using SQLite database")
    return _engine


def is_sqlite() -> bool:
    """Check if using SQLite backend. Always True."""
    return True


@contextmanager
def get_connection() -> Generator:
    """Get a database connection from the pool.

    Usage:
        with get_connection() as conn:
            result = conn.execute(text("SELECT 1"))
    """
    engine = get_engine()
    connection = engine.connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Initialize the SQLite database schema."""
    with get_connection() as conn:
        # P0.0A migration foundation. The existing DDL remains the bootstrap
        # schema for compatibility; future destructive changes must be added
        # as ordered migrations after this version marker.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now')),
                description TEXT NOT NULL
            )
        """))

        # Reviews table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                review_id TEXT NOT NULL UNIQUE,
                data TEXT NOT NULL,
                timestamp_created INTEGER,
                timestamp_updated INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_reviews_app_id ON reviews(app_id)
        """))

        # FTS5 virtual table for full-text search
        conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS reviews_fts USING fts5(
                review_id,
                review_text,
                tokenize='unicode61'
            )
        """))

        # Review labels table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS review_labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                review_id TEXT NOT NULL,
                model TEXT,
                prompt_version TEXT,
                review_hash TEXT,
                payload TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(app_id, review_id)
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_review_labels_app_id ON review_labels(app_id)
        """))

        # Analysis results table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                app_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                run_id TEXT,
                snapshot_hash TEXT,
                context_hash TEXT,
                stale INTEGER DEFAULT 0,
                stale_reason TEXT,
                metadata TEXT,
                insights TEXT,
                reviews TEXT,
                research_report TEXT,
                semantic_status TEXT,
                error TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, app_id)
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_analysis_results_user_app
            ON analysis_results(user_id, app_id)
        """))

        # Progress table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                app_id INTEGER NOT NULL,
                processed INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                phase TEXT DEFAULT 'fetching',
                fetched_count INTEGER DEFAULT 0,
                samples_json TEXT DEFAULT '[]',
                eta_seconds REAL,
                cancelled INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, app_id)
            )
        """))

        # Starred games table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS starred_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                app_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                metadata TEXT,
                insights TEXT,
                sample TEXT,
                genres TEXT,
                categories TEXT,
                is_favorite INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, app_id)
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_starred_games_user_id ON starred_games(user_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_starred_games_favorite
            ON starred_games(is_favorite) WHERE is_favorite = 1
        """))

        # Chat messages table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id
            ON chat_messages(user_id, created_at DESC)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session
            ON chat_messages(user_id, session_id, created_at DESC)
        """))

        # LLM usage table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                model TEXT,
                prompt_tokens INTEGER,
                response_tokens INTEGER,
                total_tokens INTEGER,
                cached_tokens INTEGER,
                tool_use_prompt_tokens INTEGER,
                thoughts_tokens INTEGER,
                traffic_type TEXT,
                app_id INTEGER,
                session_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_llm_usage_user ON llm_usage(user_id, created_at DESC)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_llm_usage_operation ON llm_usage(operation, created_at DESC)
        """))

        # Chat context table (arrays stored as JSON text)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_context (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                app_ids TEXT DEFAULT '[]',
                last_intent TEXT,
                last_subcategories TEXT DEFAULT '[]',
                accumulated_facts TEXT DEFAULT '{}',
                game_names TEXT DEFAULT '{}',
                turn_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chat_context_user ON chat_context(user_id, updated_at DESC)
        """))

        # Citation feedback table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS citation_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                review_id TEXT NOT NULL,
                helpful INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_citation_feedback_user
            ON citation_feedback(user_id, session_id, created_at DESC)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_citation_feedback_review ON citation_feedback(review_id)
        """))

        # Chat sessions table (app_ids stored as JSON text)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT,
                app_ids TEXT DEFAULT '[]',
                first_user_message TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id, updated_at DESC)
        """))

        # Comparison summaries table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS comparison_summaries (
                cache_key TEXT PRIMARY KEY,
                app_ids TEXT NOT NULL,
                comparison_type TEXT NOT NULL,
                category TEXT,
                subcategory TEXT,
                summary_data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL,
                user_id TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_comparison_expires ON comparison_summaries(expires_at)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_comparison_user ON comparison_summaries(user_id)
        """))

        # Version-review intelligence tables. These are deliberately separate
        # from analysis_results: the latter stores the latest app-level
        # snapshot for the existing dashboard, while these tables preserve the
        # configuration and outputs of each version/event comparison run.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS version_events (
                event_id TEXT PRIMARY KEY,
                app_id INTEGER NOT NULL,
                event_name TEXT NOT NULL,
                event_date TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_description TEXT,
                source TEXT,
                source_url TEXT,
                manual_verified INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_version_events_app_date
            ON version_events(app_id, event_date DESC)
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS analysis_runs (
                run_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                target_app_id INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                config TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'created',
                metrics TEXT,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(event_id) REFERENCES version_events(event_id)
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_created
            ON analysis_runs(user_id, created_at DESC)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_target_app
            ON analysis_runs(target_app_id, created_at DESC)
        """))

        conn.execute(text("""
            INSERT OR IGNORE INTO schema_migrations(version, description)
            VALUES (1, 'legacy schema bootstrap')
        """))
        logger.info("SQLite schema initialized at migration version 1")

    from . import adaptive_schema, cost_ledger, fts, migrations, run_schema, steam_enrichment_migration
    from pathlib import Path
    database = make_url(get_database_url()).database

    # P0.1 FTS migration runs before the run-schema migrations.
    if database in (None, ":memory:"):
        with get_connection() as conn:
            raw = conn.connection.driver_connection
            if migrations.current_version(raw) < fts.FTS_MIGRATION_VERSION:
                fts.migrate_legacy_fts(raw)
                result = fts.verify_fts_integrity(raw)
                if not result["ok"]:
                    logger.warning("FTS integrity drift detected during migration; rebuilding index: %s", result)
                    fts.rebuild_fts(raw)
                    result = fts.verify_fts_integrity(raw)
                if not result["ok"]:
                    raise RuntimeError(f"FTS integrity verification failed after rebuild: {result}")
                migrations.record_version(raw, fts.FTS_MIGRATION_VERSION, "canonical external-content review FTS")
                raw.commit()
    else:
        database_path = Path(database).expanduser().resolve()
        backup_path = database_path.with_name(database_path.name + ".p0_1.bak")

        def migrate_and_verify(raw_conn):
            fts.migrate_legacy_fts(raw_conn)
            result = fts.verify_fts_integrity(raw_conn)
            if not result["ok"]:
                logger.warning("FTS integrity drift detected during migration; rebuilding index: %s", result)
                fts.rebuild_fts(raw_conn)
                result = fts.verify_fts_integrity(raw_conn)
            if not result["ok"]:
                raise RuntimeError(f"FTS integrity verification failed after rebuild: {result}")

        migrations.apply_ordered_migrations(
            database_path,
            [(fts.FTS_MIGRATION_VERSION, "canonical external-content review FTS", migrate_and_verify)],
            backup_path=backup_path,
            restore_on_error=True,
        )
        with get_connection() as conn:
            result = fts.verify_fts_integrity(conn)
            if not result["ok"]:
                logger.warning("FTS integrity drift detected after migrations; rebuilding index: %s", result)
                raw = conn.connection.driver_connection
                fts.rebuild_fts(raw)
                result = fts.verify_fts_integrity(raw)
            if not result["ok"]:
                raise RuntimeError(f"FTS integrity verification failed after rebuild: {result}")

    # P0.2a generalizes the existing Version Review run table.
    if database in (None, ":memory:"):
        with get_connection() as conn:
            raw = conn.connection.driver_connection
            if migrations.current_version(raw) < 3:
                run_schema.migrate_analysis_runs(raw)
                migrations.record_version(raw, 3, "generalized analysis_runs schema")
                raw.commit()
    else:
        run_database_path = Path(database).expanduser().resolve()
        run_backup_path = run_database_path.with_name(run_database_path.name + ".p0_2a.bak")
        migrations.apply_ordered_migrations(
            run_database_path,
            [(3, "generalized analysis_runs schema", run_schema.migrate_analysis_runs)],
            backup_path=run_backup_path,
            restore_on_error=True,
        )

    # P0.2b lifecycle columns are additive and do not alter Version Review
    # status semantics. Interrupted general runs are recovered below.
    if database in (None, ":memory:"):
        with get_connection() as conn:
            raw = conn.connection.driver_connection
            if migrations.current_version(raw) < 4:
                raw.execute("ALTER TABLE analysis_runs ADD COLUMN phase TEXT")
                raw.execute("ALTER TABLE analysis_runs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
                migrations.record_version(raw, 4, "general analysis lifecycle columns")
                raw.commit()
    else:
        lifecycle_path = Path(database).expanduser().resolve()
        lifecycle_backup = lifecycle_path.with_name(lifecycle_path.name + ".p0_2b.bak")

        def add_lifecycle_columns(raw_conn):
            raw_conn.execute("ALTER TABLE analysis_runs ADD COLUMN phase TEXT")
            raw_conn.execute("ALTER TABLE analysis_runs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")

        migrations.apply_ordered_migrations(
            lifecycle_path,
            [(4, "general analysis lifecycle columns", add_lifecycle_columns)],
            backup_path=lifecycle_backup,
            restore_on_error=True,
        )

    # P0.2c stores one immutable completed result per general-analysis run.
    if database in (None, ":memory:"):
        with get_connection() as conn:
            raw = conn.connection.driver_connection
            if migrations.current_version(raw) < 5:
                result_schema.migrate_analysis_run_results(raw)
                migrations.record_version(raw, 5, "immutable general analysis run results")
                raw.commit()
    else:
        result_path = Path(database).expanduser().resolve()
        result_backup = result_path.with_name(result_path.name + ".p0_2c.bak")
        migrations.apply_ordered_migrations(
            result_path,
            [(5, "immutable general analysis run results", result_schema.migrate_analysis_run_results)],
            backup_path=result_backup,
            restore_on_error=True,
        )

    # P0.3a records label origin and the complete semantic cache identity.
    if database in (None, ":memory:"):
        with get_connection() as conn:
            raw = conn.connection.driver_connection
            if migrations.current_version(raw) < 6:
                label_schema.migrate_review_label_provenance(raw)
                migrations.record_version(raw, 6, "review label provenance and cache identity")
                raw.commit()
    else:
        label_path = Path(database).expanduser().resolve()
        label_backup = label_path.with_name(label_path.name + ".p0_3a.bak")
        migrations.apply_ordered_migrations(
            label_path,
            [(6, "review label provenance and cache identity", label_schema.migrate_review_label_provenance)],
            backup_path=label_backup,
            restore_on_error=True,
        )

    # P0.4 persists verified chat evidence alongside the immutable assistant
    # message so later canonical review edits cannot invalidate the citation.
    from . import evidence_schema
    if database in (None, ":memory:"):
        with get_connection() as conn:
            raw = conn.connection.driver_connection
            if migrations.current_version(raw) < 7:
                evidence_schema.migrate_chat_evidence(raw)
                migrations.record_version(raw, 7, "immutable chat evidence metadata")
                raw.commit()
    else:
        evidence_path = Path(database).expanduser().resolve()
        evidence_backup = evidence_path.with_name(evidence_path.name + ".p0_4.bak")
        migrations.apply_ordered_migrations(
            evidence_path,
            [(7, "immutable chat evidence metadata", evidence_schema.migrate_chat_evidence)],
            backup_path=evidence_backup,
            restore_on_error=True,
        )

    # P0.6 persists one immutable row per physical provider call.
    if database in (None, ":memory:"):
        with get_connection() as conn:
            raw = conn.connection.driver_connection
            if migrations.current_version(raw) < 8:
                cost_ledger.migrate_llm_calls(raw)
                migrations.record_version(raw, 8, "durable LLM physical-call cost ledger")
                raw.commit()
    else:
        cost_path = Path(database).expanduser().resolve()
        cost_backup = cost_path.with_name(cost_path.name + ".p0_6.bak")
        migrations.apply_ordered_migrations(
            cost_path,
            [(8, "durable LLM physical-call cost ledger", cost_ledger.migrate_llm_calls)],
            backup_path=cost_backup,
            restore_on_error=True,
        )

    # Server-owned rolling ETA samples for classification progress.
    def migrate_progress_eta(raw_conn):
        columns = {str(row[1]) for row in raw_conn.execute("PRAGMA table_info(progress)").fetchall()}
        if "samples_json" not in columns:
            raw_conn.execute("ALTER TABLE progress ADD COLUMN samples_json TEXT DEFAULT '[]'")
        if "eta_seconds" not in columns:
            raw_conn.execute("ALTER TABLE progress ADD COLUMN eta_seconds REAL")

    # V1 adaptive analysis stores one immutable methodology snapshot per run.
    if database in (None, ":memory:"):
        with get_connection() as conn:
            raw = conn.connection.driver_connection
            if migrations.current_version(raw) < adaptive_schema.ADAPTIVE_SCHEMA_VERSION:
                adaptive_schema.migrate_adaptive_analysis(raw)
                migrations.record_version(raw, adaptive_schema.ADAPTIVE_SCHEMA_VERSION, "adaptive analysis design snapshots")
                raw.commit()
    else:
        adaptive_path = Path(database).expanduser().resolve()
        adaptive_backup = adaptive_path.with_name(adaptive_path.name + ".adaptive_v1.bak")
        migrations.apply_ordered_migrations(
            adaptive_path,
            [(adaptive_schema.ADAPTIVE_SCHEMA_VERSION, "adaptive analysis design snapshots and event provenance", adaptive_schema.migrate_adaptive_analysis)],
            backup_path=adaptive_backup,
            restore_on_error=True,
        )

    # Steam enrichment is additive, raw-payload backed, and analysis-inert.
    if database in (None, ":memory:"):
        with get_connection() as conn:
            raw = conn.connection.driver_connection
            if migrations.current_version(raw) < steam_enrichment_migration.ENRICHMENT_MIGRATION_VERSION:
                steam_enrichment_migration.migrate(raw)
                migrations.record_version(raw, steam_enrichment_migration.ENRICHMENT_MIGRATION_VERSION, steam_enrichment_migration.DESCRIPTION)
                raw.commit()
    else:
        enrichment_path = Path(database).expanduser().resolve()
        enrichment_backup = enrichment_path.with_name(enrichment_path.name + ".steam_enrichment_v1.bak")
        migrations.apply_ordered_migrations(
            enrichment_path,
            [(steam_enrichment_migration.ENRICHMENT_MIGRATION_VERSION, steam_enrichment_migration.DESCRIPTION, steam_enrichment_migration.migrate)],
            backup_path=enrichment_backup,
            restore_on_error=True,
        )

    # Web MVP UX population counters and rolling ETA columns are additive.
    def migrate_web_mvp_ux(raw_conn):
        run_schema.migrate_analysis_run_population_columns(raw_conn)
        migrate_progress_eta(raw_conn)

    if database in (None, ":memory:"):
        with get_connection() as conn:
            raw = conn.connection.driver_connection
            if migrations.current_version(raw) < 12:
                migrate_web_mvp_ux(raw)
                migrations.record_version(raw, 12, "Web MVP UX population counters and authoritative ETA")
                raw.commit()
    else:
        ux_path = Path(database).expanduser().resolve()
        ux_backup = ux_path.with_name(ux_path.name + ".web_mvp_ux.bak")
        migrations.apply_ordered_migrations(
            ux_path,
            [(12, "Web MVP UX population counters and authoritative ETA", migrate_web_mvp_ux)],
            backup_path=ux_backup,
            restore_on_error=True,
        )

    # Stage 2P.4 formalizes the deterministic Research Core result separately
    # from legacy semantic insights.  Migration 12 is already owned by the
    # Web MVP UX schema in this repository, so this additive migration uses 13.
    if database in (None, ":memory:"):
        with get_connection() as conn:
            raw = conn.connection.driver_connection
            if migrations.current_version(raw) < result_schema.RESEARCH_RESULT_MIGRATION_VERSION:
                result_schema.migrate_research_result_fields(raw)
                migrations.record_version(
                    raw,
                    result_schema.RESEARCH_RESULT_MIGRATION_VERSION,
                    "first-class Research Core result persistence",
                )
                raw.commit()
    else:
        research_result_path = Path(database).expanduser().resolve()
        research_result_backup = research_result_path.with_name(research_result_path.name + ".research_result_v1.bak")
        migrations.apply_ordered_migrations(
            research_result_path,
            [(
                result_schema.RESEARCH_RESULT_MIGRATION_VERSION,
                "first-class Research Core result persistence",
                result_schema.migrate_research_result_fields,
            )],
            backup_path=research_result_backup,
            restore_on_error=True,
        )

    with get_connection() as conn:
        run_schema.recover_interrupted_general_runs(conn)
        recovered = run_schema.recover_invalid_version_runs(conn)
        if recovered:
            logger.warning("Recovered %s invalid version-review run(s) after startup", recovered)


def check_db_health() -> bool:
    """Check if the database is reachable by executing SELECT 1."""
    try:
        with get_connection() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def close_engine() -> None:
    """Close the database engine and dispose of connection pool."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
        logger.info("Database engine closed")
