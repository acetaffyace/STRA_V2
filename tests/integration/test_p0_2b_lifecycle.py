"""P0.2b general-analysis lifecycle tests."""
from __future__ import annotations

import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import db, storage
from senti_next.research_core import build_snapshot_research_report
from senti_next.run_schema import recover_interrupted_general_runs
from senti_next.routes import analysis as analysis_route


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def create_run(app_id: int = 42) -> str:
    run_id = uuid4().hex
    storage.create_general_analysis_run(run_id, app_id, config={"review_count": 10}, requested_review_count=10)
    return run_id


def test_start_sets_started_once_and_terminal_transitions_are_protected():
    run_id = create_run()
    first = storage.transition_general_analysis_run(run_id, "running", phase="classifying")
    started_at = first["started_at"]
    second = storage.transition_general_analysis_run(run_id, "running", phase="classifying")
    assert second["started_at"] == started_at
    done = storage.transition_general_analysis_run(run_id, "completed", counts={"retrieved_count": 2})
    assert done["completed_at"]
    assert done["retrieved_count"] == 2
    for target in ("running", "queued"):
        with pytest.raises(ValueError):
            storage.transition_general_analysis_run(run_id, target)


def test_failure_and_cancellation_semantics():
    failed = create_run()
    storage.transition_general_analysis_run(failed, "running")
    result = storage.transition_general_analysis_run(failed, "failed", error="boom")
    assert result["status"] == "failed"
    assert result["error"] == "boom"

    queued = create_run(43)
    cancelled = storage.request_general_analysis_cancel(43)
    assert cancelled["status"] == "cancelled"
    assert cancelled["completed_at"]

    running = create_run(44)
    storage.transition_general_analysis_run(running, "running")
    requested = storage.request_general_analysis_cancel(44)
    assert requested["status"] == "running"
    assert requested["cancel_requested"] == 1


def test_success_failure_and_cancellation_of_background_job(monkeypatch):
    metadata = analysis_route.AnalyzeMetadata(app_id=42, requested=10, retrieved=0, language="all", fetched_at="2026-01-01T00:00:00Z")
    completed = create_run()
    storage.transition_general_analysis_run(completed, "running", phase="classifying")
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *args, **kwargs: {})
    analysis_route._run_analysis_job(completed, 42, [], metadata, {})
    assert storage.get_analysis_run(completed)["status"] == "completed"
    assert storage.load_analysis_result(42)["status"] == "completed"

    failed = create_run(43)
    storage.transition_general_analysis_run(failed, "running", phase="classifying")
    def fail(*args, **kwargs):
        raise RuntimeError("classifier failed")
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", fail)
    analysis_route._run_analysis_job(
        failed,
        43,
        [{"recommendationid": "r1", "review": "hello"}],
        metadata.copy(update={"app_id": 43}),
        {},
        semantic_runtime={"status": "available", "reason": None, "provider": "test", "model_id": "test-model"},
    )
    assert storage.get_analysis_run(failed)["status"] == "completed"
    failed_result = storage.get_analysis_run_result(failed)
    assert failed_result["semantic_status"]["status"] == "failed"

    cancelled = create_run(44)
    storage.transition_general_analysis_run(cancelled, "running")
    storage.request_general_analysis_cancel(44)
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *args, **kwargs: (_ for _ in ()).throw(InterruptedError("cancel")))
    analysis_route._run_analysis_job(
        cancelled,
        44,
        [{"recommendationid": "r2", "review": "hello"}],
        metadata.copy(update={"app_id": 44}),
        {},
        semantic_runtime={"status": "available", "reason": None, "provider": "test", "model_id": "test-model"},
    )
    assert storage.get_analysis_run(cancelled)["status"] == "cancelled"


def test_startup_recovery_marks_interrupted_general_runs_failed():
    queued = create_run()
    running = create_run(43)
    storage.transition_general_analysis_run(running, "running")
    with db.get_connection() as conn:
        recovered = recover_interrupted_general_runs(conn)
    assert recovered == 2
    assert storage.get_analysis_run(queued)["error"] == "interrupted by process restart"
    assert storage.get_analysis_run(running)["status"] == "failed"


class _CaptureBackground:
    def __init__(self, fail: bool = False):
        self.calls = []
        self.fail = fail

    def add_task(self, fn, *args, **kwargs):
        if self.fail:
            raise RuntimeError("scheduler unavailable")
        self.calls.append((fn, args, kwargs))


def _patch_analyze_dependencies(monkeypatch):
    monkeypatch.setattr(analysis_route, "fetch_reviews", lambda *args, **kwargs: [])
    monkeypatch.setattr(analysis_route, "fetch_reviews_multi_language", lambda *args, **kwargs: [])
    monkeypatch.setattr(analysis_route, "fetch_app_details", lambda *args, **kwargs: {})
    monkeypatch.setattr(analysis_route.llm, "estimate_review_labeling", lambda *args, **kwargs: {
        "total_reviews": 0, "cached_reviews": 0, "llm_reviews": 0,
        "needs_refresh_reviews": 0, "empty_reviews": 0, "short_reviews": 0, "reasons": {},
    })
    monkeypatch.setattr("senti_next.providers.get_active_provider", lambda: ("xai", "test-model"))
    monkeypatch.setattr("senti_next.providers.config._provider_has_key", lambda name: True)
    monkeypatch.setattr("senti_next.providers.config.validate_live_runtime", lambda provider, model: (True, None))


def test_analyze_creates_queued_run_before_scheduling(monkeypatch):
    _patch_analyze_dependencies(monkeypatch)
    background = _CaptureBackground()
    response = analysis_route.analyze(analysis_route.AnalyzeRequest(app_id=55, review_count=10), background)
    assert response.run_id
    assert len(background.calls) == 1
    run = storage.get_analysis_run(response.run_id)
    assert run["run_type"] == "general_analysis"
    assert run["status"] == "running"
    assert run["phase"] == "research_core"
    assert run["started_at"]
    started_at = run["started_at"]
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *args, **kwargs: {})
    fn, args, kwargs = background.calls[0]
    fn(*args, **kwargs)
    assert storage.get_analysis_run(response.run_id)["started_at"] == started_at


def test_schedule_failure_marks_queued_run_failed(monkeypatch):
    _patch_analyze_dependencies(monkeypatch)
    background = _CaptureBackground(fail=True)
    with pytest.raises(Exception):
        analysis_route.analyze(analysis_route.AnalyzeRequest(app_id=56, review_count=10), background)
    runs = storage.list_analysis_runs(56)
    assert runs[0]["status"] == "failed"
    assert "schedule failed" in runs[0]["error"]


def test_analyze_rejects_same_app_overlap_after_durable_start(monkeypatch):
    _patch_analyze_dependencies(monkeypatch)
    first_background = _CaptureBackground()
    first = analysis_route.analyze(analysis_route.AnalyzeRequest(app_id=57, review_count=10), first_background)
    with pytest.raises(Exception):
        analysis_route.analyze(analysis_route.AnalyzeRequest(app_id=57, review_count=10), _CaptureBackground())
    assert storage.get_analysis_run(first.run_id)["status"] == "running"


def test_ingestion_failure_is_terminal(monkeypatch):
    _patch_analyze_dependencies(monkeypatch)
    monkeypatch.setattr(analysis_route, "fetch_reviews", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("steam unavailable")))
    with pytest.raises(Exception):
        analysis_route.analyze(analysis_route.AnalyzeRequest(app_id=58, review_count=10), _CaptureBackground())
    assert storage.list_analysis_runs(58)[0]["status"] == "failed"


def test_ingestion_cancellation_stops_before_background_handoff(monkeypatch):
    _patch_analyze_dependencies(monkeypatch)

    def fetch_and_cancel(*args, **kwargs):
        run = storage.get_active_general_analysis(59)
        storage.request_general_analysis_cancel(59)
        kwargs["progress_callback"](1)
        return []

    monkeypatch.setattr(analysis_route, "fetch_reviews", fetch_and_cancel)
    with pytest.raises(Exception):
        analysis_route.analyze(analysis_route.AnalyzeRequest(app_id=59, review_count=10), _CaptureBackground())
    assert storage.list_analysis_runs(59)[0]["status"] == "cancelled"


def _raw_reviews() -> list[dict]:
    return [
        {
            "recommendationid": "r1",
            "review": "A clear review with enough text.",
            "timestamp_created": 1_700_000_000,
            "timestamp_updated": 1_700_000_000,
            "voted_up": True,
            "language": "english",
            "author": {"playtime_at_review": 120},
        },
        {
            "recommendationid": "r2",
            "review": "A second review with a different opinion.",
            "timestamp_created": 1_700_001_000,
            "timestamp_updated": 1_700_001_000,
            "voted_up": False,
            "language": "english",
            "author": {"playtime_at_review": 300},
        },
    ]


def test_analyze_without_provider_completes_quantitative_only_and_persists_exact_report(monkeypatch):
    _patch_analyze_dependencies(monkeypatch)
    monkeypatch.setattr("senti_next.providers.get_active_provider", lambda: ("", ""))
    reviews = _raw_reviews()
    monkeypatch.setattr(analysis_route, "fetch_reviews", lambda *args, **kwargs: reviews)
    called = {"ensure": 0, "dataframe": 0, "insights": 0}
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *args, **kwargs: called.__setitem__("ensure", called["ensure"] + 1))
    monkeypatch.setattr(analysis_route, "build_reviews_dataframe", lambda *args, **kwargs: called.__setitem__("dataframe", called["dataframe"] + 1))
    monkeypatch.setattr(analysis_route, "prepare_insights", lambda *args, **kwargs: called.__setitem__("insights", called["insights"] + 1))
    background = _CaptureBackground()

    response = analysis_route.analyze(analysis_route.AnalyzeRequest(app_id=60, review_count=10), background)
    assert response.label_estimate is None
    run = storage.get_analysis_run(response.run_id)
    assert run["config"]["semantic_runtime"]["status"] == "unavailable"
    assert run["config"]["semantic_runtime"]["reason"] == "no_provider"
    fn, args, kwargs = background.calls[0]
    fn(*args, **kwargs)

    result = storage.load_analysis_result(60)
    immutable = storage.get_analysis_run_result(response.run_id)
    assert result["status"] == "completed"
    assert immutable["semantic_status"]["status"] == "unavailable"
    assert immutable["semantic_status"]["reason"] == "no_provider"
    assert immutable["research_report"] == build_snapshot_research_report(
        args[2], metadata=immutable["metadata"]
    )
    assert immutable["research_report"]["population"]["review_count"] == len(reviews)
    assert run["provider"] is None
    assert run["model_id"] is None
    assert run["prompt_version"] is None
    assert called == {"ensure": 0, "dataframe": 0, "insights": 0}
    assert storage.get_analysis_run(response.run_id)["classified_count"] == 0


def test_analyze_missing_api_key_is_quantitative_only_not_http_400(monkeypatch):
    _patch_analyze_dependencies(monkeypatch)
    monkeypatch.setattr("senti_next.providers.get_active_provider", lambda: ("xai", "test-model"))
    monkeypatch.setattr("senti_next.providers.config._provider_has_key", lambda name: False)
    monkeypatch.setattr(analysis_route, "fetch_reviews", lambda *args, **kwargs: _raw_reviews())
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("semantic classifier must not run")))
    background = _CaptureBackground()

    response = analysis_route.analyze(analysis_route.AnalyzeRequest(app_id=61, review_count=10), background)
    fn, args, kwargs = background.calls[0]
    fn(*args, **kwargs)
    result = storage.get_analysis_run_result(response.run_id)
    assert result["semantic_status"]["reason"] == "no_api_key"
    assert storage.get_analysis_run(response.run_id)["status"] == "completed"


def test_invalid_semantic_configuration_does_not_block_research_core(monkeypatch):
    _patch_analyze_dependencies(monkeypatch)
    monkeypatch.setattr("senti_next.providers.get_active_provider", lambda: ("xai", "invalid-model"))
    monkeypatch.setattr("senti_next.providers.config._provider_has_key", lambda name: True)
    monkeypatch.setattr("senti_next.providers.config.validate_live_runtime", lambda provider, model: (False, "bad config"))
    monkeypatch.setattr(analysis_route, "fetch_reviews", lambda *args, **kwargs: _raw_reviews())
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("semantic classifier must not run")))
    background = _CaptureBackground()

    response = analysis_route.analyze(analysis_route.AnalyzeRequest(app_id=62, review_count=10), background)
    fn, args, kwargs = background.calls[0]
    fn(*args, **kwargs)
    result = storage.get_analysis_run_result(response.run_id)
    assert result["semantic_status"]["reason"] == "invalid_configuration"
    assert storage.get_analysis_run(response.run_id)["status"] == "completed"


def test_semantic_success_preserves_legacy_insights_and_adds_reserved_fields(monkeypatch):
    import pandas as pd

    run_id = create_run(63)
    storage.transition_general_analysis_run(run_id, "running", phase="research_core")
    metadata = analysis_route.AnalyzeMetadata(app_id=63, requested=10, retrieved=1, language="english", fetched_at="2026-01-01T00:00:00Z")
    reviews = _raw_reviews()[:1]
    frame = pd.DataFrame([{"review_id": "r1", "review": reviews[0]["review"], "llm_label_origin": "llm", "llm_validated": True}])
    calls = {"ensure": 0}
    monkeypatch.setattr(analysis_route, "build_reviews_dataframe", lambda rows: frame.copy())
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *args, **kwargs: calls.__setitem__("ensure", calls["ensure"] + 1))
    monkeypatch.setattr(analysis_route.storage, "load_review_labels", lambda app_id: {})
    monkeypatch.setattr(analysis_route.llm, "apply_review_labels", lambda df, labels: df)
    monkeypatch.setattr(analysis_route, "prepare_insights", lambda *args, **kwargs: {"legacy_metric": 7})
    monkeypatch.setattr(analysis_route.llm, "llm_usage_context", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(analysis_route.llm, "generate_health_overview", lambda **kwargs: None)

    analysis_route._run_analysis_job(
        run_id,
        63,
        reviews,
        metadata,
        {},
        semantic_runtime={"status": "available", "reason": None, "provider": "test", "model_id": "test-model"},
    )
    result = storage.get_analysis_run_result(run_id)
    assert storage.get_analysis_run(run_id)["status"] == "completed"
    assert result["insights"]["legacy_metric"] == 7
    assert result["research_report"]["mode"] == "snapshot"
    assert result["semantic_status"]["status"] == "available"
    assert calls["ensure"] == 1


def test_semantic_failure_preserves_research_core_and_completes_quantitatively(monkeypatch):
    run_id = create_run(64)
    storage.transition_general_analysis_run(run_id, "running", phase="research_core")
    metadata = analysis_route.AnalyzeMetadata(app_id=64, requested=10, retrieved=1, language="english", fetched_at="2026-01-01T00:00:00Z")
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider down")))
    monkeypatch.setattr(analysis_route, "build_reviews_dataframe", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dataframe must not run after classifier failure")))

    analysis_route._run_analysis_job(
        run_id,
        64,
        _raw_reviews(),
        metadata,
        {},
        semantic_runtime={"status": "available", "reason": None, "provider": "test", "model_id": "test-model"},
    )
    result = storage.get_analysis_run_result(run_id)
    assert storage.get_analysis_run(run_id)["status"] == "completed"
    assert result["research_report"]["schema_version"] == "research-report-v1"
    assert result["semantic_status"]["status"] == "failed"
    assert result["semantic_status"]["reason"] == "runtime_error"
    assert storage.get_analysis_run(run_id)["classified_count"] == 0


def test_research_core_failure_is_terminal_and_never_starts_semantics(monkeypatch):
    run_id = create_run(65)
    storage.transition_general_analysis_run(run_id, "running", phase="research_core")
    metadata = analysis_route.AnalyzeMetadata(app_id=65, requested=10, retrieved=1, language="english", fetched_at="2026-01-01T00:00:00Z")
    monkeypatch.setattr(analysis_route, "build_snapshot_research_report", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("research core failed")))
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("semantic layer must not run")))

    analysis_route._run_analysis_job(
        run_id,
        65,
        _raw_reviews(),
        metadata,
        {},
        semantic_runtime={"status": "available", "reason": None, "provider": "test", "model_id": "test-model"},
    )
    assert storage.get_analysis_run(run_id)["status"] == "failed"
    assert storage.get_analysis_run_result(run_id) is None
    assert storage.load_analysis_result(65)["status"] == "failed"


def test_empty_population_completes_without_semantic_calls(monkeypatch):
    run_id = create_run(66)
    storage.transition_general_analysis_run(run_id, "running", phase="research_core")
    metadata = analysis_route.AnalyzeMetadata(app_id=66, requested=10, retrieved=0, language="english", fetched_at="2026-01-01T00:00:00Z")
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("empty population must not classify")))

    analysis_route._run_analysis_job(
        run_id,
        66,
        [],
        metadata,
        {},
        semantic_runtime={"status": "available", "reason": None, "provider": "test", "model_id": "test-model"},
    )
    result = storage.get_analysis_run_result(run_id)
    assert storage.get_analysis_run(run_id)["status"] == "completed"
    assert result["research_report"]["recommendation"]["population"]["recommendation_rate"] is None
    assert result["semantic_status"]["reason"] == "no_reviews"
