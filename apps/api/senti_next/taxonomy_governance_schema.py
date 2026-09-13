"""SQLite schema for versioned taxonomy governance (Stage 3D).

The registry is deliberately independent of the current classifier.  Stage
3E may make the classifier consume a snapshot; Stage 3D only stores and
governs immutable definitions.
"""
from __future__ import annotations

TAXONOMY_GOVERNANCE_MIGRATION_VERSION = 18
DESCRIPTION = "versioned taxonomy governance and immutable snapshots"


def migrate_taxonomy_governance(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS taxonomy_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            taxonomy_version TEXT NOT NULL UNIQUE,
            parent_snapshot_id TEXT,
            taxonomy_fingerprint TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('draft','published','retired')),
            topic_n INTEGER NOT NULL,
            source_change_set_id TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            published_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_taxonomy_snapshots_status ON taxonomy_snapshots(status, created_at DESC)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS taxonomy_topics (
            snapshot_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            parent_topic_id TEXT,
            display_name TEXT NOT NULL,
            description TEXT NOT NULL,
            topic_status TEXT NOT NULL CHECK(topic_status IN ('active','deprecated')),
            source_kind TEXT NOT NULL CHECK(source_kind IN ('baseline','promoted_candidate')),
            source_candidate_id TEXT,
            PRIMARY KEY(snapshot_id, topic_id),
            UNIQUE(snapshot_id, canonical_key),
            FOREIGN KEY(snapshot_id) REFERENCES taxonomy_snapshots(snapshot_id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_taxonomy_topics_key ON taxonomy_topics(snapshot_id, canonical_key)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS taxonomy_change_sets (
            change_set_id TEXT PRIMARY KEY,
            base_snapshot_id TEXT NOT NULL,
            base_taxonomy_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('planned','validated','applied','rejected')),
            requested_version TEXT NOT NULL,
            operator TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            validation_json TEXT,
            result_snapshot_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            validated_at TEXT,
            applied_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_taxonomy_change_sets_base ON taxonomy_change_sets(base_snapshot_id, status)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS taxonomy_change_items (
            change_item_id TEXT PRIMARY KEY,
            change_set_id TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('add_topic')),
            source_candidate_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            parent_topic_id TEXT,
            display_name TEXT NOT NULL,
            description TEXT NOT NULL,
            FOREIGN KEY(change_set_id) REFERENCES taxonomy_change_sets(change_set_id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_taxonomy_change_items_set ON taxonomy_change_items(change_set_id)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS taxonomy_activation_events (
            activation_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            reason TEXT NOT NULL,
            operator TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(snapshot_id) REFERENCES taxonomy_snapshots(snapshot_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_taxonomy_activation_history ON taxonomy_activation_events(created_at DESC, activation_id DESC)")
    # Published rows are immutable at the database boundary too.  Governance
    # services create a new snapshot for every change; these triggers protect
    # against accidental direct UPDATE/DELETE calls.
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS taxonomy_published_snapshot_immutable
        BEFORE UPDATE ON taxonomy_snapshots
        WHEN OLD.status = 'published'
        BEGIN SELECT RAISE(ABORT, 'published taxonomy snapshot is immutable'); END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS taxonomy_published_snapshot_no_delete
        BEFORE DELETE ON taxonomy_snapshots
        WHEN OLD.status = 'published'
        BEGIN SELECT RAISE(ABORT, 'published taxonomy snapshot is immutable'); END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS taxonomy_published_topic_immutable
        BEFORE UPDATE ON taxonomy_topics
        WHEN (SELECT status FROM taxonomy_snapshots WHERE snapshot_id = OLD.snapshot_id) = 'published'
        BEGIN SELECT RAISE(ABORT, 'published taxonomy topic is immutable'); END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS taxonomy_published_topic_no_delete
        BEFORE DELETE ON taxonomy_topics
        WHEN (SELECT status FROM taxonomy_snapshots WHERE snapshot_id = OLD.snapshot_id) = 'published'
        BEGIN SELECT RAISE(ABORT, 'published taxonomy topic is immutable'); END
    """)
