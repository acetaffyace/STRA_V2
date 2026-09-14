from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from apps.api.senti_next import db
from apps.api.senti_next import storage
from apps.api.senti_next.web_contract import build_dashboard_payload
from apps.api.senti_next.research_contracts import resolve_formal_window
from apps.api.senti_next.population_compatibility import check_population_compatibility
from apps.api.senti_next.research_run_store import (
    create_job,
    create_research_run,
    get_population_snapshot,
    get_research_run,
    recover_interrupted_jobs,
    transition_job,
)


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def _reviews() -> list[dict]:
    return [
        {"recommendationid": "r-1", "review": "Original", "language": "english", "voted_up": True, "timestamp_created": 10},
        {"recommendationid": "r-2", "review": "Second", "language": "schinese", "voted_up": False, "timestamp_created": 20},
    ]


def test_formal_window_is_anchored_and_half_open():
    result = resolve_formal_window(anchor_time="2026-09-14T00:00:00Z", relative_days=3)
    assert result["anchor_time"] == "2026-09-14T00:00:00Z"
    assert result["start_at_utc"] == "2026-09-11T00:00:00Z"
    assert result["end_at_utc"] == "2026-09-14T00:00:00Z"
    assert result["interval"] == "[start_at_utc,end_at_utc)"


def test_research_run_pins_population_and_review_revision():
    run = create_research_run(
        run_id="run_m0_exact",
        app_id=10,
        sampling_contract={"app_id": 10, "languages": ["english", "schinese"], "relative_days": 3},
        reviews=_reviews(),
        anchor_time="2026-09-14T00:00:00Z",
        acquisition_provenance={"source": "fixture", "complete": True},
    )
    assert run["population_snapshot_id"].startswith("pop_")
    assert run["time_semantics_version"] == "utc-half-open-v1"
    assert get_research_run("run_m0_exact") == run

    population = get_population_snapshot(run["population_snapshot_id"])
    assert population is not None
    assert population["membership_count"] == 2
    assert [row["content_text"] for row in population["reviews"]] == ["Original", "Second"]
    assert population["sampling_contract"]["resolved_window"]["start_at_utc"] == "2026-09-11T00:00:00Z"

    # A current mutable review row or a newer revision cannot replace the
    # historical snapshot membership.
    with db.get_connection() as conn:
        conn.execute(text("UPDATE reviews SET data=:data WHERE review_id='r-1'"), {"data": json.dumps({"review": "Current"})})
    reopened = get_population_snapshot(run["population_snapshot_id"])
    assert reopened["reviews"][0]["content_text"] == "Original"


def test_research_run_idempotency_rejects_different_population_and_snapshots_are_immutable():
    first = create_research_run(run_id="run_m0_immutable", app_id=10, sampling_contract={"app_id": 10}, reviews=_reviews(), anchor_time=datetime(2026, 9, 14, tzinfo=timezone.utc))
    assert create_research_run(run_id="run_m0_immutable", app_id=10, sampling_contract={"app_id": 10}, reviews=_reviews(), anchor_time="2026-09-14T00:00:00Z")["population_hash"] == first["population_hash"]
    changed = [dict(row) for row in _reviews()]
    changed[0]["review"] = "Edited upstream"
    with pytest.raises(ValueError, match="research_run_conflict"):
        create_research_run(run_id="run_m0_immutable", app_id=10, sampling_contract={"app_id": 10}, reviews=changed, anchor_time="2026-09-14T00:00:00Z")
    with db.get_connection() as conn:
        with pytest.raises(Exception, match="population_snapshot_immutable"):
            conn.execute(text("UPDATE population_snapshots SET population_hash='tampered' WHERE population_snapshot_id=:id"), {"id": first["population_snapshot_id"]})


def test_canonical_result_reference_is_attached_and_exact_dashboard_payload_reopens():
    run_id = "run_m0_reopen"
    storage.create_general_analysis_run(
        run_id,
        10,
        config={"sampling_contract": {"app_id": 10, "languages": ["english"]}},
        requested_languages=["english"],
    )
    storage.transition_general_analysis_run(run_id, "running")
    canonical = create_research_run(
        run_id=run_id,
        app_id=10,
        sampling_contract={"app_id": 10, "languages": ["english"]},
        reviews=_reviews(),
        anchor_time="2026-09-14T00:00:00Z",
        acquisition_provenance={"source": "fixture", "collection_complete": True},
        status="RUNNING",
    )
    storage.finalize_general_analysis_run(
        run_id,
        10,
        {"app_id": 10, "run_id": run_id, "mode": "fixture"},
        {"five_questions": {"q1": "answer"}},
        _reviews(),
        research_report={"schema_version": "research-report-v1"},
    )
    finalized = get_research_run(run_id)
    assert finalized is not None
    assert finalized["status"] == "READY"
    assert finalized["immutable_result_ref"] == f"analysis_run_results:{run_id}"
    assert canonical["population_snapshot_id"] == finalized["population_snapshot_id"]

    payload = build_dashboard_payload(10, requested_run_id=run_id)
    assert payload["readiness"]["run_id"] == run_id
    assert payload["run"]["run_id"] == run_id
    assert payload["metadata"]["run_id"] == run_id


def test_job_idempotency_transition_and_restart_recovery():
    first = create_job(job_type="research_core", target_resource_type="ResearchRun", idempotency_key="same-request", retryable=True, progress_total=2)
    second = create_job(job_type="research_core", target_resource_type="ResearchRun", idempotency_key="same-request", retryable=True, progress_total=99)
    assert second["job_id"] == first["job_id"]
    running = transition_job(first["job_id"], "RUNNING", progress_current=1)
    assert running["attempt_count"] == 1
    with db.get_connection() as conn:
        conn.execute(text("UPDATE jobs SET heartbeat_at='2020-01-01T00:00:00Z' WHERE job_id=:id"), {"id": first["job_id"]})
    assert recover_interrupted_jobs(stale_after_seconds=1) == 1
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT status, stage FROM jobs WHERE job_id=:id"), {"id": first["job_id"]}).one()
    assert tuple(row) == ("QUEUED", "requeued_after_restart")

    non_retryable = create_job(
        job_type="one_shot_export",
        target_resource_type="ResearchRun",
        idempotency_key="one-shot",
        retryable=False,
    )
    transition_job(non_retryable["job_id"], "RUNNING")
    with db.get_connection() as conn:
        conn.execute(text("UPDATE jobs SET heartbeat_at='2020-01-01T00:00:00Z' WHERE job_id=:id"), {"id": non_retryable["job_id"]})
    assert recover_interrupted_jobs(stale_after_seconds=1) == 1
    assert transition_job(non_retryable["job_id"], "FAILED")["status"] == "FAILED"


def test_population_compatibility_is_explicit_and_never_upgrades_a_truncated_source():
    run = create_research_run(
        run_id="run_m0_compatibility",
        app_id=10,
        sampling_contract={"app_id": 10, "start_time": 100, "end_time": 300, "languages": ["english"], "max_reviews": 0},
        reviews=_reviews(),
        anchor_time="2026-09-14T00:00:00Z",
        acquisition_provenance={"collection_complete": True, "truncated_by_max_reviews": False},
    )
    population = get_population_snapshot(run["population_snapshot_id"])
    exact = check_population_compatibility(existing_population=population, requested_contract=population["sampling_contract"])
    assert exact.decision == "EXACT"
    subset = check_population_compatibility(existing_population=population, requested_contract={"app_id": 10, "start_time": 100, "end_time": 300, "languages": ["english"], "max_reviews": 1})
    assert subset.decision == "SAFE_SUBSET"
    assert len(subset.derived_review_snapshot_ids) == 1

    truncated = dict(population)
    truncated["acquisition_provenance"] = {"collection_complete": False, "truncated_by_max_reviews": True}
    blocked = check_population_compatibility(existing_population=truncated, requested_contract=population["sampling_contract"])
    assert blocked.decision == "INCOMPATIBLE"
    assert any(reason["code"] == "INCOMPLETE_SOURCE" for reason in blocked.reasons)
