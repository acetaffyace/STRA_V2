"""Migration 29 for governed EmergingTopicCandidate persistence."""
from __future__ import annotations

EMERGING_TOPIC_MIGRATION_VERSION = 29
DESCRIPTION = "governed EmergingTopicCandidate lifecycle"


def migrate_emerging_topics(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS emerging_topic_candidates (
            candidate_id TEXT PRIMARY KEY,
            semantic_run_id TEXT NOT NULL,
            cluster_id TEXT NOT NULL,
            provisional_name TEXT NOT NULL,
            provisional_definition TEXT NOT NULL,
            cluster_size INTEGER NOT NULL CHECK (cluster_size >= 0),
            nearest_known_topics_json TEXT NOT NULL DEFAULT '[]',
            representative_unit_ids_json TEXT NOT NULL DEFAULT '[]',
            segment_distribution_json TEXT NOT NULL DEFAULT '{}',
            time_distribution_json TEXT NOT NULL DEFAULT '{}',
            recommendation_distribution_json TEXT NOT NULL DEFAULT '{}',
            llm_recommendation_json TEXT,
            promotion_target TEXT NOT NULL DEFAULT 'none' CHECK (promotion_target IN ('game', 'archetype', 'refine_existing', 'none')),
            status TEXT NOT NULL DEFAULT 'DETECTED' CHECK (status IN ('DETECTED', 'REVIEWED', 'PENDING', 'ACCEPTED', 'MERGED', 'REJECTED', 'DEFERRED')),
            reviewed_at TEXT,
            accepted_topic_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            emerging_topic_schema_version TEXT NOT NULL DEFAULT 'emerging-topic-v1',
            UNIQUE(semantic_run_id, cluster_id),
            FOREIGN KEY(semantic_run_id) REFERENCES semantic_runs(semantic_run_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emerging_topics_run_status ON emerging_topic_candidates(semantic_run_id, status)")
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_emerging_topics_identity_immutable
        BEFORE UPDATE ON emerging_topic_candidates
        WHEN NEW.candidate_id <> OLD.candidate_id
          OR NEW.semantic_run_id <> OLD.semantic_run_id
          OR NEW.cluster_id <> OLD.cluster_id
          OR NEW.provisional_name <> OLD.provisional_name
          OR NEW.provisional_definition <> OLD.provisional_definition
          OR NEW.cluster_size <> OLD.cluster_size
          OR NEW.nearest_known_topics_json <> OLD.nearest_known_topics_json
          OR NEW.representative_unit_ids_json <> OLD.representative_unit_ids_json
          OR NEW.segment_distribution_json <> OLD.segment_distribution_json
          OR NEW.time_distribution_json <> OLD.time_distribution_json
          OR NEW.recommendation_distribution_json <> OLD.recommendation_distribution_json
          OR COALESCE(NEW.promotion_target, '') <> COALESCE(OLD.promotion_target, '')
          OR NEW.emerging_topic_schema_version <> OLD.emerging_topic_schema_version
        BEGIN SELECT RAISE(ABORT, 'emerging_topic_identity_immutable'); END"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_emerging_topics_no_delete
        BEFORE DELETE ON emerging_topic_candidates
        BEGIN SELECT RAISE(ABORT, 'emerging_topic_immutable'); END"""
    )
