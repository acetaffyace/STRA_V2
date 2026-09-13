from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from apps.api.senti_next import db, llm
from apps.api.senti_next.semantic_region_interpretation import record_semantic_taxonomy_candidate_decision
from apps.api.senti_next.taxonomy_governance import (
    activate_snapshot,
    apply_change_set,
    current_active_snapshot,
    diff_taxonomies,
    list_eligible_candidates,
    plan_add_topic,
    publish_snapshot,
    taxonomy_status,
    trace_taxonomy_topic,
    validate_change_set,
)


@pytest.fixture()
def isolated_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def _candidate(candidate_id: str, *, recommendation: str = "candidate_new_topic", sufficiency: str = "sufficient") -> None:
    payload = {
        "candidate_name": "Camera options",
        "candidate_description": "Feedback about camera configuration.",
        "recommendation": recommendation,
        "evidence_sufficiency": sufficiency,
        "region_id": "region-camera",
        "interpretation_run_id": "interpretation-1",
    }
    with db.get_connection() as conn:
        conn.execute(
            text("""
                INSERT INTO semantic_taxonomy_candidates
                (candidate_id, interpretation_run_id, evidence_package_id, region_id,
                 interpretation_status, recommendation, candidate_name,
                 candidate_description, evidence_sufficiency, candidate_json)
                VALUES (:id, :run, :evidence, :region, 'interpreted', :recommendation,
                        :name, :description, :sufficiency, :payload)
            """),
            {
                "id": candidate_id,
                "run": f"run-{candidate_id}",
                "evidence": f"evidence-{candidate_id}",
                "region": "region-camera",
                "recommendation": recommendation,
                "name": payload["candidate_name"],
                "description": payload["candidate_description"],
                "sufficiency": sufficiency,
                "payload": json.dumps(payload, sort_keys=True),
            },
        )
    record_semantic_taxonomy_candidate_decision(candidate_id, "approve")


def _promote(candidate_id: str, *, canonical_key: str = "ui_ux_accessibility/quality_of_life/camera_options", parent_key: str | None = None):
    plan = plan_add_topic(
        candidate_id=candidate_id,
        base_version="sentinext-taxonomy-v1",
        canonical_key=canonical_key,
        display_name="Camera Options",
        description="Feedback about configurable camera behaviour and options.",
        operator="analyst",
        parent_key=parent_key,
    )
    validation = validate_change_set(plan["change_set_id"])
    assert validation["valid"] is True
    draft = apply_change_set(plan["change_set_id"])
    published = publish_snapshot(draft.snapshot_id, operator="analyst")
    return plan, draft, published


def test_approved_candidate_creates_complete_immutable_v2_and_auditable_trace(isolated_db):
    _candidate("candidate-1")
    assert [row["candidate_id"] for row in list_eligible_candidates()] == ["candidate-1"]
    plan, draft, published = _promote("candidate-1")
    assert draft.status == "draft"
    assert published.status == "published"
    assert len(published.topics) == len(current_active_snapshot().topics)
    assert current_active_snapshot().snapshot_id == published.snapshot_id
    assert published.parent_snapshot_id == plan["base_snapshot"]["snapshot_id"]
    assert diff_taxonomies("sentinext-taxonomy-v1", published.snapshot_id)["added_topics"] == ["ui_ux_accessibility/quality_of_life/camera_options"]
    topic = next(item for item in published.topics if item.canonical_key.endswith("camera_options"))
    trace = trace_taxonomy_topic(topic.topic_id, published.snapshot_id)
    assert trace["topic"]["source_candidate_id"] == "candidate-1"
    assert trace["source_candidate"]["candidate_id"] == "candidate-1"
    assert taxonomy_status()["active_taxonomy_version"] == published.taxonomy_version


def test_child_topic_parent_is_recorded_and_rollback_preserves_published_snapshot(isolated_db):
    _candidate("candidate-child")
    _, _, published = _promote("candidate-child", parent_key="ui_ux_accessibility/quality_of_life")
    topic = next(item for item in published.topics if item.canonical_key.endswith("camera_options"))
    parent = next(item for item in published.topics if item.canonical_key == "ui_ux_accessibility/quality_of_life")
    assert topic.parent_topic_id == parent.topic_id
    activate_snapshot("sentinext-taxonomy-v1", operator="reviewer", reason="rollback")
    assert current_active_snapshot().taxonomy_version == "sentinext-taxonomy-v1"
    assert db.get_connection is not None
    assert published.status == "published"
    history = __import__("apps.api.senti_next.taxonomy_governance", fromlist=["activation_history"]).activation_history()
    assert history[-1]["taxonomy_version"] == "sentinext-taxonomy-v1"


@pytest.mark.parametrize("decision", ["reject", "defer"])
def test_rejected_or_deferred_candidates_are_not_eligible(isolated_db, decision):
    _candidate(f"candidate-{decision}")
    with db.get_connection() as conn:
        conn.execute(text("DELETE FROM semantic_taxonomy_candidate_decisions WHERE candidate_id=:id"), {"id": f"candidate-{decision}"})
    record_semantic_taxonomy_candidate_decision(f"candidate-{decision}", decision)
    assert list_eligible_candidates() == []
    with pytest.raises(ValueError, match="candidate_not_approved"):
        plan_add_topic(candidate_id=f"candidate-{decision}", base_version="sentinext-taxonomy-v1", canonical_key=f"other/{decision}_topic", display_name="X", description="X", operator="analyst")


def test_latest_rejection_overrides_prior_approval_and_structural_cases_are_blocked(isolated_db):
    _candidate("candidate-latest")
    record_semantic_taxonomy_candidate_decision("candidate-latest", "reject")
    assert list_eligible_candidates() == []
    with pytest.raises(ValueError, match="candidate_not_approved"):
        plan_add_topic(candidate_id="candidate-latest", base_version="sentinext-taxonomy-v1", canonical_key="other/latest_topic", display_name="X", description="X", operator="analyst")

    _candidate("candidate-boundary", recommendation="taxonomy_boundary_review")
    with pytest.raises(ValueError, match="requires_structural_governance"):
        plan_add_topic(candidate_id="candidate-boundary", base_version="sentinext-taxonomy-v1", canonical_key="other/boundary_topic", display_name="X", description="X", operator="analyst")

    _candidate("candidate-insufficient", sufficiency="insufficient")
    with pytest.raises(ValueError, match="insufficient_evidence"):
        plan_add_topic(candidate_id="candidate-insufficient", base_version="sentinext-taxonomy-v1", canonical_key="other/insufficient_topic", display_name="X", description="X", operator="analyst")


def test_collision_parent_and_duplicate_promotion_errors(isolated_db):
    _candidate("candidate-collision")
    with pytest.raises(ValueError, match="canonical_key_conflict"):
        plan_add_topic(candidate_id="candidate-collision", base_version="sentinext-taxonomy-v1", canonical_key="technical/performance", display_name="X", description="X", operator="analyst")
    _candidate("candidate-parent")
    with pytest.raises(ValueError, match="invalid_parent"):
        plan_add_topic(candidate_id="candidate-parent", base_version="sentinext-taxonomy-v1", canonical_key="other/child_topic", display_name="X", description="X", operator="analyst", parent_key="other/missing")
    _promote("candidate-collision", canonical_key="other/new_topic")
    with pytest.raises(ValueError, match="candidate_already_promoted"):
        plan_add_topic(candidate_id="candidate-collision", base_version="sentinext-taxonomy-v2", canonical_key="other/new_topic_2", display_name="X", description="X", operator="analyst")


def test_stale_plan_is_rejected(isolated_db):
    _candidate("candidate-stale-a")
    plan = plan_add_topic(candidate_id="candidate-stale-a", base_version="sentinext-taxonomy-v1", canonical_key="other/first_topic", display_name="X", description="X", operator="analyst")
    _candidate("candidate-stale-b")
    _promote("candidate-stale-b", canonical_key="other/second_topic")
    with pytest.raises(ValueError, match="stale_taxonomy_base"):
        apply_change_set(plan["change_set_id"])


def test_published_rows_are_immutable_at_database_boundary(isolated_db):
    _candidate("candidate-immutable")
    _, _, published = _promote("candidate-immutable", canonical_key="other/immutable_topic")
    with db.get_connection() as conn:
        with pytest.raises(Exception):
            conn.execute(text("UPDATE taxonomy_snapshots SET created_by='bad' WHERE snapshot_id=:id"), {"id": published.snapshot_id})
        with pytest.raises(Exception):
            conn.execute(text("DELETE FROM taxonomy_topics WHERE snapshot_id=:id"), {"id": published.snapshot_id})


def test_json_serializable_status_and_no_classifier_mutation(isolated_db):
    assert llm.TAXONOMY_VERSION == "sentinext-taxonomy-v1"
    assert taxonomy_status()["topic_n"] == len(llm._ALLOWED_SUBCATEGORY_KEYS)
    json.dumps(taxonomy_status(), allow_nan=False, sort_keys=True)
