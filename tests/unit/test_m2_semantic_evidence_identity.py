from __future__ import annotations

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import text

from apps.api.senti_next import db, migrations
from apps.api.senti_next.research_run_store import create_job, create_research_run, get_job
from apps.api.senti_next.semantic_run_store import (
    create_semantic_mention,
    create_semantic_run,
    create_semantic_unit,
    execute_semantic_run_job,
    get_semantic_rollups,
)
from apps.api.senti_next.routes.research_runs import SemanticRunCreateRequest, create_snapshot_semantic_run


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def _context() -> tuple[dict, dict]:
    review = {
        "recommendationid": "r-unit-1",
        "review": "修复 crash 🔧",
        "voted_up": False,
        "language": "schinese",
    }
    research = create_research_run(
        run_id="run_m2_evidence",
        app_id=10,
        sampling_contract={"app_id": 10, "languages": ["schinese"]},
        reviews=[review],
        anchor_time="2026-09-14T00:00:00Z",
    )
    semantic = create_semantic_run(
        research_run_id=research["run_id"],
        semantic_config={"segmentation_version": "segmentation-v1"},
    )
    return research, semantic


def test_semantic_unit_uses_utf8_byte_offsets_and_is_idempotent():
    research, semantic = _context()
    snapshot_id = research["population_snapshot_id"]
    # Resolve the frozen member rather than reconstructing a snapshot identity.
    with db.get_connection() as conn:
        snapshot_id = conn.execute(
            text("SELECT review_snapshot_id FROM population_snapshot_members WHERE population_snapshot_id=:id"),
            {"id": snapshot_id},
        ).scalar_one()
    content = "修复 crash 🔧"
    end = len(content.encode("utf-8"))
    first = create_semantic_unit(
        semantic_run_id=semantic["semantic_run_id"],
        review_snapshot_id=snapshot_id,
        start_byte_offset=0,
        end_byte_offset=end,
        segmentation_version="segmentation-v1",
    )
    second = create_semantic_unit(
        semantic_run_id=semantic["semantic_run_id"],
        review_snapshot_id=snapshot_id,
        start_byte_offset=0,
        end_byte_offset=end,
        segmentation_version="segmentation-v1",
        text_snapshot=content,
    )
    assert first["semantic_unit_id"] == second["semantic_unit_id"]
    assert first["text_snapshot"] == content
    assert first["source_content_hash"]


def test_semantic_unit_rejects_invalid_utf8_boundaries_and_text_conflicts():
    research, semantic = _context()
    with db.get_connection() as conn:
        snapshot_id = conn.execute(
            text("SELECT review_snapshot_id FROM population_snapshot_members WHERE population_snapshot_id=:id"),
            {"id": research["population_snapshot_id"]},
        ).scalar_one()
    with pytest.raises(ValueError, match="semantic_unit_utf8_boundary"):
        create_semantic_unit(
            semantic_run_id=semantic["semantic_run_id"],
            review_snapshot_id=snapshot_id,
            start_byte_offset=1,
            end_byte_offset=4,
            segmentation_version="segmentation-v1",
        )
    with pytest.raises(ValueError, match="semantic_unit_text_snapshot_conflict"):
        create_semantic_unit(
            semantic_run_id=semantic["semantic_run_id"],
            review_snapshot_id=snapshot_id,
            start_byte_offset=0,
            end_byte_offset=len("修复".encode("utf-8")),
            segmentation_version="segmentation-v1",
            text_snapshot="tampered",
        )


def test_semantic_mention_preserves_one_core_topic_with_optional_secondary_and_is_immutable():
    _, semantic = _context()
    with db.get_connection() as conn:
        snapshot_id = conn.execute(text("SELECT review_snapshot_id FROM population_snapshot_members")).scalar_one()
    unit = create_semantic_unit(
        semantic_run_id=semantic["semantic_run_id"],
        review_snapshot_id=snapshot_id,
        start_byte_offset=0,
        end_byte_offset=len("修复".encode("utf-8")),
        segmentation_version="segmentation-v1",
    )
    first = create_semantic_mention(
        semantic_run_id=semantic["semantic_run_id"],
        semantic_unit_id=unit["semantic_unit_id"],
        core_topic_id="performance",
        secondary_topic_id="crash",
        signal_type="issue",
        assignment_source="prototype",
        similarity_score=0.82,
        calibrated_confidence=0.91,
        decision_band="high_confidence",
        prototype_version="prototype-v3",
        adjudication_ref="adj-1",
    )
    second = create_semantic_mention(
        semantic_run_id=semantic["semantic_run_id"],
        semantic_unit_id=unit["semantic_unit_id"],
        core_topic_id="performance",
        secondary_topic_id="crash",
        signal_type="issue",
        assignment_source="prototype",
        similarity_score=0.82,
        calibrated_confidence=0.91,
        decision_band="high_confidence",
        prototype_version="prototype-v3",
        adjudication_ref="adj-1",
    )
    assert first["mention_id"] == second["mention_id"]
    assert first["core_topic_id"] == "performance"
    assert first["secondary_topic_id"] == "crash"
    with db.get_connection() as conn:
        with pytest.raises(Exception, match="semantic_mention_immutable"):
            conn.execute(text("UPDATE semantic_mentions SET decision_band='low' WHERE mention_id=:id"), {"id": first["mention_id"]})
    with pytest.raises(ValueError, match="invalid_signal_type"):
        create_semantic_mention(
            semantic_run_id=semantic["semantic_run_id"],
            semantic_unit_id=unit["semantic_unit_id"],
            core_topic_id="performance",
            assignment_source="prototype",
            decision_band="high_confidence",
            prototype_version="prototype-v3",
            signal_type="neutral",
        )
    with pytest.raises(ValueError, match="invalid_calibrated_confidence"):
        create_semantic_mention(
            semantic_run_id=semantic["semantic_run_id"],
            semantic_unit_id=unit["semantic_unit_id"],
            core_topic_id="performance",
            assignment_source="prototype",
            decision_band="high_confidence",
            prototype_version="prototype-v3",
            calibrated_confidence=1.1,
        )


def test_migration_registry_and_schema_include_evidence_tables():
    assert migrations.latest_known_schema_version() == 28
    with db.get_connection() as conn:
        tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).all()}
    assert {"semantic_runs", "semantic_units", "semantic_mentions"} <= tables


def test_semantic_generation_job_is_durable_and_marks_unresolved_reviews_partial():
    research, _ = _context()
    semantic = create_semantic_run(
        research_run_id=research["run_id"],
        semantic_config={
            "segmentation_version": "segmentation-v1",
            "fixture_mentions": {"r-unit-1": {"core_topic_id": "technical/crash", "signal_type": "issue", "decision_band": "HIGH", "prototype_version": "prototype-v1"}},
        },
    )
    job = create_job(
        job_type="semantic_v2_generation",
        target_resource_type="semantic_run",
        target_resource_id=semantic["semantic_run_id"],
        idempotency_key="semantic-job-m2-evidence",
        progress_total=1,
        progress_unit="reviews",
        retryable=True,
    )
    result = execute_semantic_run_job(semantic["semantic_run_id"], job["job_id"])
    assert result["status"] == "READY"
    assert result["processed_review_count"] == 1
    assert result["unresolved_review_count"] == 0
    assert get_job(job["job_id"])["status"] == "SUCCEEDED"
    rollups = get_semantic_rollups(semantic["semantic_run_id"])
    assert rollups["topic_rollup_count"] == 1
    assert rollups["signal_rollup_count"] == 1

    unresolved_research = create_research_run(
        run_id="run_m2_unresolved",
        app_id=10,
        sampling_contract={"app_id": 10, "languages": ["english"]},
        reviews=[{"recommendationid": "r-unresolved", "review": "No assignment yet", "language": "english"}],
        anchor_time="2026-09-14T00:00:00Z",
    )
    unresolved = create_semantic_run(
        research_run_id=unresolved_research["run_id"],
        semantic_config={"segmentation_version": "segmentation-v1"},
    )
    unresolved_job = create_job(
        job_type="semantic_v2_generation",
        target_resource_type="semantic_run",
        target_resource_id=unresolved["semantic_run_id"],
        idempotency_key="semantic-job-m2-unresolved",
        retryable=True,
    )
    partial = execute_semantic_run_job(unresolved["semantic_run_id"], unresolved_job["job_id"])
    assert partial["status"] == "PARTIAL"
    assert partial["unresolved_review_count"] == 1
    assert get_job(unresolved_job["job_id"])["status"] == "PARTIAL"


def test_semantic_run_resource_endpoint_is_idempotent_and_schedules_durable_job():
    research, _ = _context()
    request = SemanticRunCreateRequest(semantic_config={"segmentation_version": "endpoint-segmentation-v1"})
    first_tasks = BackgroundTasks()
    first = create_snapshot_semantic_run(research["run_id"], request, first_tasks, "api-idempotency-m2")
    second_tasks = BackgroundTasks()
    second = create_snapshot_semantic_run(research["run_id"], request, second_tasks, "api-idempotency-m2")
    assert first["semantic_run"]["semantic_run_id"] == second["semantic_run"]["semantic_run_id"]
    assert first["job"]["job_id"] == second["job"]["job_id"]
    assert first["job"]["status"] == "QUEUED"
    assert len(first_tasks.tasks) == 1
    first_tasks.tasks[0].func(*first_tasks.tasks[0].args, **first_tasks.tasks[0].kwargs)
    fetched = get_job(first["job"]["job_id"])
    assert fetched["status"] == "PARTIAL"
