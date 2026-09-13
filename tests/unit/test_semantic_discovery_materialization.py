from __future__ import annotations

from sqlalchemy import text

from apps.api.senti_next import db
from apps.api.senti_next.semantic_discovery_materialization_schema import migrate_semantic_discovery_materializations


def test_migration_16_is_additive_and_idempotent(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db.init_db()
    try:
        with db.get_connection() as conn:
            raw = conn.connection.driver_connection
            migrate_semantic_discovery_materializations(raw)
            migrate_semantic_discovery_materializations(raw)
            columns = {row[1] for row in conn.execute(text("PRAGMA table_info(semantic_discovery_runs)"))}
            assert {"structure_run_id", "structure_fingerprint", "structure_json"}.issubset(columns)
            assert conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='semantic_discovery_materializations'")
            ).scalar() == 1
    finally:
        db.close_engine()


def test_migration_16_preserves_v15_history(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db.init_db()
    try:
        with db.get_connection() as conn:
            conn.execute(
                text(
                    "INSERT INTO semantic_discovery_runs "
                    "(discovery_run_id, semantic_index_id, research_run_id, population_fingerprint, semantic_index_fingerprint, "
                    "discovery_contract_json, algorithm_version, population_n, indexed_review_n, semantic_unit_n, status, report_json) "
                    "VALUES ('old', 'idx', 'run', 'p', 'i', '{}', 'hdbscan-open-set-v1', 1, 1, 1, 'completed', '{\"schema_version\":\"semantic-discovery-report-v1\"}')"
                )
            )
            raw = conn.connection.driver_connection
            migrate_semantic_discovery_materializations(raw)
            row = conn.execute(text("SELECT status, report_json FROM semantic_discovery_runs WHERE discovery_run_id='old'")).mappings().one()
            assert row["status"] == "completed"
            assert row["report_json"] == '{"schema_version":"semantic-discovery-report-v1"}'
    finally:
        db.close_engine()
