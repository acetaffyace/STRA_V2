from __future__ import annotations

import pytest
from sqlalchemy import text

from apps.api.senti_next import db
from apps.api.senti_next.emerging_topic_store import create_emerging_topic_candidate, get_emerging_topic_candidate, transition_emerging_topic_candidate
from apps.api.senti_next.research_run_store import create_research_run
from apps.api.senti_next.semantic_run_store import create_semantic_run


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def _semantic_run() -> dict:
    research = create_research_run(
        run_id="run_m2_candidate",
        app_id=10,
        sampling_contract={"app_id": 10, "languages": ["english"]},
        reviews=[{"recommendationid": "candidate-review", "review": "Players want a ranked mode", "language": "english"}],
        anchor_time="2026-09-14T00:00:00Z",
    )
    return create_semantic_run(research_run_id=research["run_id"], semantic_config={"segmentation_version": "segmentation-v1"})


def test_emerging_candidate_is_idempotent_and_requires_explicit_acceptance_target():
    semantic = _semantic_run()
    first = create_emerging_topic_candidate(
        semantic_run_id=semantic["semantic_run_id"],
        cluster_id="cluster-1",
        provisional_name="Ranked mode",
        provisional_definition="A player-created candidate for a ranked mode.",
        cluster_size=4,
        nearest_known_topics=["gameplay/balance"],
        representative_unit_ids=["unit-1"],
        promotion_target="game",
    )
    second = create_emerging_topic_candidate(
        semantic_run_id=semantic["semantic_run_id"],
        cluster_id="cluster-1",
        provisional_name="Ranked mode",
        provisional_definition="A player-created candidate for a ranked mode.",
        cluster_size=4,
        nearest_known_topics=["gameplay/balance"],
        representative_unit_ids=["unit-1"],
        promotion_target="game",
    )
    assert first["candidate_id"] == second["candidate_id"]
    reviewed = transition_emerging_topic_candidate(first["candidate_id"], "REVIEWED")
    assert reviewed["status"] == "REVIEWED"
    with pytest.raises(ValueError, match="accepted_topic_id_required"):
        transition_emerging_topic_candidate(first["candidate_id"], "ACCEPTED")
    accepted = transition_emerging_topic_candidate(first["candidate_id"], "ACCEPTED", accepted_topic_id="catalog_topic_1")
    assert accepted["status"] == "ACCEPTED"
    assert accepted["accepted_topic_id"] == "catalog_topic_1"
    assert get_emerging_topic_candidate(first["candidate_id"])["status"] == "ACCEPTED"
    with db.get_connection() as conn:
        with pytest.raises(Exception, match="emerging_topic_identity_immutable"):
            conn.execute(text("UPDATE emerging_topic_candidates SET provisional_name='tampered' WHERE candidate_id=:id"), {"id": first["candidate_id"]})
