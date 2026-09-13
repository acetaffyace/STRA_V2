from __future__ import annotations

from sqlalchemy import text

from apps.api.senti_next import db, migrations
from apps.api.senti_next.taxonomy_governance_schema import migrate_taxonomy_governance
from apps.api.senti_next.taxonomy_registry import BASELINE_TAXONOMY_VERSION


def test_stage3d_migration_18_is_idempotent_and_baseline_is_materialized(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    try:
        with db.get_connection() as conn:
            raw = conn.connection.driver_connection
            migrate_taxonomy_governance(raw)
            migrate_taxonomy_governance(raw)
            tables = {
                row[0]
                for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'taxonomy_%'")).fetchall()
            }
            assert {"taxonomy_snapshots", "taxonomy_topics", "taxonomy_change_sets", "taxonomy_change_items", "taxonomy_activation_events"} <= tables
            assert conn.execute(text("SELECT COUNT(*) FROM taxonomy_snapshots WHERE taxonomy_version=:version"), {"version": BASELINE_TAXONOMY_VERSION}).scalar() == 1
            assert conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar() == 19
            assert migrations.schema_status(raw) == {"latest_known": 19, "applied": 19, "status": "current"}
    finally:
        db.close_engine()
        db._engine = None
