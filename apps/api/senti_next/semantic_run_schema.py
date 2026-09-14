"""Migration 25 for immutable SemanticRun identity and lifecycle state."""
from __future__ import annotations

SEMANTIC_RUN_MIGRATION_VERSION = 25
DESCRIPTION = "immutable SemanticRun configuration identity"


def migrate_semantic_runs(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS semantic_runs (
            semantic_run_id TEXT PRIMARY KEY,
            research_run_id TEXT NOT NULL,
            population_snapshot_id TEXT NOT NULL,
            population_hash TEXT NOT NULL,
            semantic_engine_version TEXT NOT NULL,
            core_taxonomy_version TEXT NOT NULL,
            game_topic_catalog_version TEXT,
            archetype_topic_pack_versions_json TEXT NOT NULL DEFAULT '[]',
            embedding_model_version TEXT NOT NULL,
            embedding_artifact_hash TEXT NOT NULL,
            prototype_versions_json TEXT NOT NULL DEFAULT '{}',
            calibration_version TEXT NOT NULL,
            segmentation_version TEXT NOT NULL,
            normalization_version TEXT NOT NULL,
            assignment_policy_version TEXT NOT NULL,
            llm_adjudication_policy_version TEXT NOT NULL,
            semantic_config_json TEXT NOT NULL,
            semantic_config_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'QUEUED',
            eligible_review_count INTEGER NOT NULL DEFAULT 0 CHECK (eligible_review_count >= 0),
            processed_review_count INTEGER NOT NULL DEFAULT 0 CHECK (processed_review_count >= 0),
            semantic_coverage REAL CHECK (semantic_coverage IS NULL OR (semantic_coverage >= 0 AND semantic_coverage <= 1)),
            unresolved_review_count INTEGER NOT NULL DEFAULT 0 CHECK (unresolved_review_count >= 0),
            created_by_job_id TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            cost_summary_json TEXT NOT NULL DEFAULT '{}',
            result_ref TEXT,
            semantic_run_schema_version TEXT NOT NULL DEFAULT 'semantic-run-v1',
            UNIQUE(research_run_id, semantic_config_hash),
            FOREIGN KEY(research_run_id) REFERENCES research_runs(run_id),
            FOREIGN KEY(population_snapshot_id) REFERENCES population_snapshots(population_snapshot_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_runs_research_run ON semantic_runs(research_run_id, created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_runs_status ON semantic_runs(status, created_at)")
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_semantic_runs_identity_immutable
        BEFORE UPDATE ON semantic_runs
        WHEN NEW.semantic_run_id <> OLD.semantic_run_id
          OR NEW.research_run_id <> OLD.research_run_id
          OR NEW.population_snapshot_id <> OLD.population_snapshot_id
          OR NEW.population_hash <> OLD.population_hash
          OR NEW.semantic_engine_version <> OLD.semantic_engine_version
          OR NEW.core_taxonomy_version <> OLD.core_taxonomy_version
          OR COALESCE(NEW.game_topic_catalog_version, '') <> COALESCE(OLD.game_topic_catalog_version, '')
          OR NEW.archetype_topic_pack_versions_json <> OLD.archetype_topic_pack_versions_json
          OR NEW.embedding_model_version <> OLD.embedding_model_version
          OR NEW.embedding_artifact_hash <> OLD.embedding_artifact_hash
          OR NEW.prototype_versions_json <> OLD.prototype_versions_json
          OR NEW.calibration_version <> OLD.calibration_version
          OR NEW.segmentation_version <> OLD.segmentation_version
          OR NEW.normalization_version <> OLD.normalization_version
          OR NEW.assignment_policy_version <> OLD.assignment_policy_version
          OR NEW.llm_adjudication_policy_version <> OLD.llm_adjudication_policy_version
          OR NEW.semantic_config_json <> OLD.semantic_config_json
          OR NEW.semantic_config_hash <> OLD.semantic_config_hash
        BEGIN SELECT RAISE(ABORT, 'semantic_run_identity_immutable'); END"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_semantic_runs_immutable_delete
        BEFORE DELETE ON semantic_runs
        BEGIN SELECT RAISE(ABORT, 'semantic_run_immutable'); END"""
    )
