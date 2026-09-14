from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from apps.api.senti_next import db, storage
from apps.api.senti_next.research_run_store import create_research_run
from apps.api.senti_next.semantic_run_store import (
    create_semantic_run,
    semantic_config_hash,
    transition_semantic_run,
)
from apps.api.senti_next.taxonomy_v2 import CORE_TAXONOMY_VERSION, core_taxonomy_fingerprint


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def _research_run() -> dict:
    return create_research_run(
        run_id="run_m2_identity",
        app_id=10,
        sampling_contract={"app_id": 10, "languages": ["english"]},
        reviews=[{"recommendationid": "r-1", "review": "Stable source", "voted_up": True, "language": "english"}],
        anchor_time="2026-09-14T00:00:00Z",
    )


def _config() -> dict:
    return {
        "semantic_engine_version": "semantic-engine-v2",
        "core_taxonomy_version": "core-taxonomy-v2",
        "game_topic_catalog_version": "game-topics-v1",
        "archetype_topic_pack_versions": ["pack-b", "pack-a"],
        "embedding_model_version": "e5-small-v1",
        "embedding_artifact_hash": "artifact-sha",
        "prototype_versions": {"core": "prototype-v3"},
        "calibration_version": "calibration-v2",
        "segmentation_version": "segmentation-v1",
        "normalization_version": "normalization-v1",
        "assignment_policy_version": "assignment-v2",
        "llm_adjudication_policy_version": "adjudication-v1",
    }


def test_semantic_config_hash_is_order_independent_and_material_changes_rotate_identity():
    first = _config()
    reordered = dict(reversed(list(first.items())))
    assert semantic_config_hash(first) == semantic_config_hash(reordered)
    changed = dict(first, calibration_version="calibration-v3")
    assert semantic_config_hash(first) != semantic_config_hash(changed)


def test_partial_semantic_config_is_pinned_to_the_versioned_core_taxonomy_source():
    created = create_semantic_run(research_run_id=_research_run()["run_id"], semantic_config={"segmentation_version": "segmentation-v1"})
    assert created["core_taxonomy_version"] == CORE_TAXONOMY_VERSION
    assert created["semantic_config_json"]["core_taxonomy_fingerprint"] == core_taxonomy_fingerprint()


def test_semantic_run_is_idempotent_per_research_run_and_config_and_identity_is_immutable():
    research = _research_run()
    first = create_semantic_run(research_run_id=research["run_id"], semantic_config=_config())
    second = create_semantic_run(research_run_id=research["run_id"], semantic_config=_config())
    assert first["semantic_run_id"] == second["semantic_run_id"]
    assert first["population_snapshot_id"] == research["population_snapshot_id"]
    assert first["population_hash"] == research["population_hash"]

    with db.get_connection() as conn:
        with pytest.raises(Exception, match="semantic_run_identity_immutable"):
            conn.execute(text("UPDATE semantic_runs SET semantic_config_json=:value WHERE semantic_run_id=:id"), {"id": first["semantic_run_id"], "value": json.dumps({"tampered": True})})


def test_semantic_run_lifecycle_persists_partial_recovery_fields():
    _research_run()
    created = create_semantic_run(research_run_id="run_m2_identity", semantic_config=_config())
    generating = transition_semantic_run(created["semantic_run_id"], "GENERATING", eligible_review_count=1)
    assert generating["status"] == "GENERATING"
    partial = transition_semantic_run(
        created["semantic_run_id"],
        "PARTIAL",
        processed_review_count=1,
        semantic_coverage=1.0,
        unresolved_review_count=1,
        result_ref="semantic_results:sem_1",
    )
    assert partial["status"] == "PARTIAL"
    assert partial["processed_review_count"] == 1
    assert partial["semantic_coverage"] == 1.0
    assert partial["unresolved_review_count"] == 1
    assert partial["result_ref"] == "semantic_results:sem_1"
