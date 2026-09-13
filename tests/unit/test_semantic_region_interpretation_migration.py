from __future__ import annotations

from sqlalchemy import text

from apps.api.senti_next import db
from apps.api.senti_next.semantic_region_interpretation_schema import migrate_semantic_region_interpretation


def test_stage3c_migration_17_is_idempotent_and_complete(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine(); db.init_db()
    try:
        with db.get_connection() as conn:
            raw = conn.connection.driver_connection
            migrate_semantic_region_interpretation(raw)
            migrate_semantic_region_interpretation(raw)
            for table in ("semantic_region_evidence_packages", "semantic_region_interpretation_runs", "semantic_taxonomy_candidates", "semantic_taxonomy_candidate_decisions"):
                assert conn.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"), {"name": table}).scalar() == 1
            assert conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar() == 17
    finally:
        db.close_engine()
