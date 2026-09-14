"""Migration 27 for versioned Game/Archetype Topic catalog governance."""
from __future__ import annotations

TOPIC_CATALOG_MIGRATION_VERSION = 27
DESCRIPTION = "versioned Game and Archetype Topic catalog governance"


def migrate_topic_catalogs(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS topic_catalog_versions (
            catalog_version_id TEXT PRIMARY KEY,
            catalog_scope TEXT NOT NULL CHECK (catalog_scope IN ('game', 'archetype')),
            app_id INTEGER,
            catalog_version TEXT NOT NULL,
            parent_catalog_version_id TEXT,
            catalog_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'PUBLISHED', 'RETIRED')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            published_at TEXT,
            topic_catalog_schema_version TEXT NOT NULL DEFAULT 'topic-catalog-v1',
            UNIQUE(catalog_scope, app_id, catalog_version),
            FOREIGN KEY(parent_catalog_version_id) REFERENCES topic_catalog_versions(catalog_version_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS topic_catalog_topics (
            catalog_topic_id TEXT PRIMARY KEY,
            catalog_version_id TEXT NOT NULL,
            topic_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            definition TEXT NOT NULL,
            include_text TEXT NOT NULL,
            exclude_text TEXT NOT NULL,
            boundary_text TEXT NOT NULL,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            topic_status TEXT NOT NULL DEFAULT 'active' CHECK (topic_status IN ('active', 'deprecated')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(catalog_version_id, topic_key),
            FOREIGN KEY(catalog_version_id) REFERENCES topic_catalog_versions(catalog_version_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topic_catalog_versions_scope ON topic_catalog_versions(catalog_scope, app_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topic_catalog_topics_version ON topic_catalog_topics(catalog_version_id, topic_status)")
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_topic_catalog_versions_identity_immutable
        BEFORE UPDATE ON topic_catalog_versions
        WHEN NEW.catalog_version_id <> OLD.catalog_version_id
          OR NEW.catalog_scope <> OLD.catalog_scope
          OR COALESCE(NEW.app_id, -1) <> COALESCE(OLD.app_id, -1)
          OR NEW.catalog_version <> OLD.catalog_version
          OR COALESCE(NEW.parent_catalog_version_id, '') <> COALESCE(OLD.parent_catalog_version_id, '')
          OR NEW.catalog_hash <> OLD.catalog_hash
          OR NEW.topic_catalog_schema_version <> OLD.topic_catalog_schema_version
        BEGIN SELECT RAISE(ABORT, 'topic_catalog_identity_immutable'); END"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_topic_catalog_versions_no_delete
        BEFORE DELETE ON topic_catalog_versions
        BEGIN SELECT RAISE(ABORT, 'topic_catalog_immutable'); END"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_topic_catalog_topics_immutable_update
        BEFORE UPDATE ON topic_catalog_topics
        BEGIN SELECT RAISE(ABORT, 'topic_catalog_topic_immutable'); END"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_topic_catalog_topics_immutable_delete
        BEFORE DELETE ON topic_catalog_topics
        BEGIN SELECT RAISE(ABORT, 'topic_catalog_topic_immutable'); END"""
    )
