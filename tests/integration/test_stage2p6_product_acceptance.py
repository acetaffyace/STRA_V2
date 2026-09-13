"""Stage 2P.6 cross-layer acceptance tests for the deterministic product path.

These tests intentionally exercise the production analyze job, persistence,
immutable-run retrieval, and dashboard contract together.  External Steam and
semantic-provider boundaries are replaced with deterministic fixtures; the
Research Core itself is always the real implementation except in the explicit
failure scenario.
"""
from __future__ import annotations

import copy
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

API_DIR = Path(__file__).resolve().parents[2] / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import db, storage, web_contract
from senti_next.research_core import build_snapshot_research_report
from senti_next.routes import analysis as analysis_route
from senti_next.routes._shared import AnalyzeMetadata
from senti_next.sampling import SamplingContract


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    """Keep acceptance runs isolated from the developer's local database."""
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


class _CaptureBackground:
    def __init__(self):
        self.calls = []

    def add_task(self, fn, *args, **kwargs):
        self.calls.append((fn, args, kwargs))


def _fixture_reviews(offset: int = 0, count: int = 10) -> list[dict]:
    """Raw Steam-shaped mappings with metadata variation and one duplicate group."""
    rows: list[dict] = []
    for index in range(count):
        review_id = f"stage2p6-{offset + index}"
        row = {
            "recommendationid": review_id,
            "review": (
                "The combat loop is satisfying and the pacing is strong."
                if index in (0, 1)
                else f"Fixture review {offset + index} with enough descriptive text."
            ),
            "timestamp_created": 1_700_000_000 + (offset + index) * 3_600,
            "voted_up": None if index == count - 1 else index % 3 != 0,
            "language": "english" if index % 2 == 0 else "schinese",
            "steam_purchase": index % 3 != 0,
            "received_for_free": index == 3,
            "written_during_early_access": index == 2,
            "votes_up": index + 1,
            "votes_funny": index % 2,
            "weighted_vote_score": "0.42",
            "comment_count": index % 3,
            "author": {
                "steamid": f"author-{offset + index}",
                "num_games_owned": 10 + index,
                "num_reviews": 1 + index,
                "playtime_forever": 1000 + index * 100,
                "playtime_at_review": 120 + index * 60,
                "playtime_last_two_weeks": index * 5,
                "deck_playtime_at_review": index * 10,
                "last_played": 1_700_000_000 + index * 100,
            },
        }
        if index == count - 1:
            # Exercise missing optional Steam metadata without changing the
            # raw population denominator.
            row.pop("author")
            row.pop("weighted_vote_score")
        rows.append(row)
    return rows


def _contract(app_id: int, *, max_reviews: int = 20) -> SamplingContract:
    return SamplingContract(
        app_id=app_id,
        start_time=1_699_900_000,
        end_time=1_700_100_000,
        languages=["english", "schinese"],
        review_type="all",
        purchase_type="all",
        collection_order="recent",
        include_offtopic_activity=True,
        max_reviews=max_reviews,
    )


def _stats(rows: list[dict], *, complete: bool = True, truncated: bool = False, stop_reason: str = "end_of_results") -> dict:
    return {
        "available_matching_reviews": len(rows),
        "retrieved_count": len(rows),
        "retrieved_reviews": len(rows),
        "population_reviews_after_scope": len(rows),
        "scope_complete": complete,
        "collection_complete": complete,
        "truncated_by_max_reviews": truncated,
        "stop_reason": stop_reason,
        "language_stats": {"english": {"status": "complete", "retrieved": len(rows)}},
        "lower_boundary_reached": complete,
    }


def _install_acquisition(monkeypatch, rows: list[dict], runtime: dict, *, stats: dict | None = None):
    """Replace only external acquisition/runtime boundaries."""
    stats_payload = stats or _stats(rows)

    def fake_fetch(*_args, **kwargs):
        callback = kwargs.get("stats_callback")
        if callback:
            callback(stats_payload)
        return copy.deepcopy(rows)

    monkeypatch.setattr(analysis_route, "fetch_reviews", fake_fetch)
    monkeypatch.setattr(analysis_route, "fetch_reviews_multi_language", fake_fetch)
    monkeypatch.setattr(analysis_route, "fetch_app_details", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(analysis_route, "_resolve_semantic_runtime", lambda: dict(runtime))
    monkeypatch.setattr(
        analysis_route.llm,
        "estimate_review_labeling",
        lambda *_args, **_kwargs: {
            "total_reviews": len(rows),
            "cached_reviews": 0,
            "llm_reviews": len(rows),
            "needs_refresh_reviews": 0,
            "empty_reviews": 0,
            "short_reviews": 0,
            "reasons": {},
        },
    )


def _start_analysis(monkeypatch, app_id: int, rows: list[dict], runtime: dict, *, contract: SamplingContract | None = None, stats: dict | None = None):
    _install_acquisition(monkeypatch, rows, runtime, stats=stats)
    background = _CaptureBackground()
    request = analysis_route.AnalyzeRequest(
        app_id=app_id,
        sampling=contract or _contract(app_id),
        persist=True,
    )
    response = analysis_route.analyze(request, background)
    assert len(background.calls) == 1
    return response, background


def _run_background(background: _CaptureBackground):
    fn, args, kwargs = background.calls[0]
    fn(*args, **kwargs)
    return args


def _no_provider() -> dict:
    return {"status": "unavailable", "reason": "no_provider", "provider": None, "model_id": None}


def _available_runtime() -> dict:
    return {"status": "available", "reason": None, "provider": "fixture", "model_id": "fixture-model"}


def _assert_json_safe(value):
    json.dumps(value, sort_keys=True, allow_nan=False)


def test_no_provider_full_chain_exact_report_and_quantitative_dashboard(monkeypatch):
    app_id = 2601
    rows = _fixture_reviews()
    contract = _contract(app_id)
    _install_acquisition(monkeypatch, rows, _no_provider())
    called = {"ensure": 0, "dataframe": 0, "apply": 0, "insights": 0, "health": 0}

    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *_a, **_k: called.__setitem__("ensure", called["ensure"] + 1))
    monkeypatch.setattr(analysis_route, "build_reviews_dataframe", lambda *_a, **_k: called.__setitem__("dataframe", called["dataframe"] + 1))
    monkeypatch.setattr(analysis_route.llm, "apply_review_labels", lambda *_a, **_k: called.__setitem__("apply", called["apply"] + 1))
    monkeypatch.setattr(analysis_route, "prepare_insights", lambda *_a, **_k: called.__setitem__("insights", called["insights"] + 1))
    monkeypatch.setattr(analysis_route.llm, "generate_health_overview", lambda **_k: called.__setitem__("health", called["health"] + 1))

    response, background = _start_analysis(monkeypatch, app_id, rows, _no_provider(), contract=contract)
    task_args = _run_background(background)
    immutable = storage.get_analysis_run_result(response.run_id)
    latest = storage.load_analysis_result(app_id)
    assert immutable and latest
    expected = build_snapshot_research_report(task_args[2], metadata=immutable["metadata"])

    assert storage.get_analysis_run(response.run_id)["status"] == "completed"
    assert immutable["research_report"] == expected
    assert latest["research_report"] == expected
    assert immutable["semantic_status"] == latest["semantic_status"]
    assert immutable["semantic_status"] == {"status": "unavailable", "reason": "no_provider", "provider": None, "model_id": None}
    assert immutable["insights"] is None
    assert storage.get_analysis_run(response.run_id)["classified_count"] == 0
    assert called == {"ensure": 0, "dataframe": 0, "apply": 0, "insights": 0, "health": 0}

    population = expected["population"]
    recommendation = expected["recommendation"]["population"]
    activity = expected["activity"]
    assert population["sampling_contract"] == contract.to_dict()
    assert len(task_args[2]) == immutable["metadata"]["analysis_population_count"] == population["review_count"]
    assert activity["population"]["raw_review_count"] == len(rows)
    assert recommendation["valid_n"] + recommendation["missing_n"] == len(rows)
    assert recommendation["valid_n"] == recommendation["recommended_n"] + recommendation["not_recommended_n"]
    assert expected["mode"] == "snapshot"
    assert expected["comparability"] == {"status": "unavailable", "reason": "comparison_required"}
    assert expected["standardization"] == {"status": "unavailable", "reason": "comparison_required"}
    assert expected["window_robustness"] == {"status": "unavailable", "reason": "comparison_required"}
    _assert_json_safe(expected)

    dashboard = web_contract.build_dashboard_payload(app_id)
    assert dashboard["research_report"] == expected
    assert dashboard["readiness"]["research_ready"] is True
    assert dashboard["readiness"]["semantic_ready"] is False
    assert dashboard["readiness"]["research_result_available"] is True
    assert dashboard["readiness"]["semantic_result_available"] is False


@pytest.mark.parametrize("runtime", [
    {"status": "unavailable", "reason": "no_api_key", "provider": "fixture", "model_id": "fixture-model"},
    {"status": "unavailable", "reason": "invalid_configuration", "provider": "fixture", "model_id": "invalid"},
])
def test_semantic_unavailable_configurations_still_complete_research(monkeypatch, runtime):
    app_id = 2610 if runtime["reason"] == "no_api_key" else 2611
    rows = _fixture_reviews(count=8)
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("semantic layer must not run")))
    response, background = _start_analysis(monkeypatch, app_id, rows, runtime)
    _run_background(background)
    immutable = storage.get_analysis_run_result(response.run_id)
    run = storage.get_analysis_run(response.run_id)
    assert run["status"] == "completed"
    assert immutable["research_report"] is not None
    assert immutable["semantic_status"]["status"] == "unavailable"
    assert immutable["semantic_status"]["reason"] == runtime["reason"]
    assert run["config"]["semantic_runtime"]["reason"] == runtime["reason"]


def _install_semantic_success(monkeypatch, rows: list[dict]):
    frame = pd.DataFrame([
        {
            "review_id": row["recommendationid"],
            "review": row.get("review", ""),
            "llm_label_origin": "llm",
            "llm_validated": True,
        }
        for row in rows
    ])
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *_a, **_k: {})
    monkeypatch.setattr(analysis_route.storage, "load_review_labels", lambda *_a, **_k: {})
    monkeypatch.setattr(analysis_route, "build_reviews_dataframe", lambda *_a, **_k: frame.copy())
    monkeypatch.setattr(analysis_route.llm, "apply_review_labels", lambda data, _labels: data)
    monkeypatch.setattr(analysis_route, "prepare_insights", lambda *_a, **_k: {"legacy_metric": 7})
    monkeypatch.setattr(analysis_route.llm, "llm_usage_context", lambda *_a, **_k: nullcontext())
    monkeypatch.setattr(analysis_route.llm, "generate_health_overview", lambda **_k: None)


def test_semantic_success_keeps_exact_research_report_and_full_dashboard_readiness(monkeypatch):
    app_id = 2620
    rows = _fixture_reviews()
    runtime = _available_runtime()
    _install_semantic_success(monkeypatch, rows)
    response, background = _start_analysis(monkeypatch, app_id, rows, runtime)
    task_args = _run_background(background)
    immutable = storage.get_analysis_run_result(response.run_id)
    expected = build_snapshot_research_report(task_args[2], metadata=immutable["metadata"])

    assert storage.get_analysis_run(response.run_id)["status"] == "completed"
    assert immutable["research_report"] == expected
    assert immutable["semantic_status"]["status"] == "available"
    assert immutable["insights"] is not None
    assert "research_report" not in immutable["insights"]
    assert "semantic_status" not in immutable["insights"]
    dashboard = web_contract.build_dashboard_payload(app_id)
    assert dashboard["readiness"]["research_ready"] is True
    assert dashboard["readiness"]["semantic_ready"] is True
    assert dashboard["research_report"] == expected
    assert dashboard["insights"] == immutable["insights"]


def test_semantic_runtime_failure_preserves_completed_research_product(monkeypatch):
    app_id = 2621
    rows = _fixture_reviews()
    runtime = _available_runtime()
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("fixture provider down")))
    monkeypatch.setattr(analysis_route, "build_reviews_dataframe", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("DataFrame must not run after provider failure")))
    response, background = _start_analysis(monkeypatch, app_id, rows, runtime)
    task_args = _run_background(background)
    immutable = storage.get_analysis_run_result(response.run_id)
    expected = build_snapshot_research_report(task_args[2], metadata=immutable["metadata"])
    assert storage.get_analysis_run(response.run_id)["status"] == "completed"
    assert immutable["research_report"] == expected
    assert immutable["semantic_status"]["status"] == "failed"
    assert immutable["semantic_status"]["reason"] == "runtime_error"
    assert storage.load_analysis_result(app_id)["research_report"] == expected


def test_research_core_failure_is_terminal_and_not_research_ready(monkeypatch):
    app_id = 2630
    rows = _fixture_reviews(count=6)
    runtime = _available_runtime()
    semantic_calls = {"ensure": 0}
    monkeypatch.setattr(analysis_route, "build_snapshot_research_report", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("fixture Research Core failure")))
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *_a, **_k: semantic_calls.__setitem__("ensure", semantic_calls["ensure"] + 1))
    response, background = _start_analysis(monkeypatch, app_id, rows, runtime)
    _run_background(background)
    assert storage.get_analysis_run(response.run_id)["status"] == "failed"
    assert storage.get_analysis_run_result(response.run_id) is None
    assert semantic_calls["ensure"] == 0
    dashboard = web_contract.build_dashboard_payload(app_id)
    assert dashboard["readiness"]["research_ready"] is False


def test_empty_population_is_completed_without_fake_recommendation_or_semantics(monkeypatch):
    app_id = 2640
    runtime = _no_provider()
    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("empty population must not classify")))
    response, background = _start_analysis(monkeypatch, app_id, [], runtime, contract=_contract(app_id))
    _run_background(background)
    immutable = storage.get_analysis_run_result(response.run_id)
    assert storage.get_analysis_run(response.run_id)["status"] == "completed"
    assert immutable["research_report"]["population"]["review_count"] == 0
    assert immutable["research_report"]["recommendation"]["population"]["recommendation_rate"] is None
    assert immutable["semantic_status"]["reason"] == "no_reviews"
    assert web_contract.build_dashboard_payload(app_id)["readiness"]["research_ready"] is True


@pytest.mark.parametrize("truncated, stop_reason", [(True, "max_reviews_reached"), (False, "api_failure")])
def test_limited_acquisition_provenance_is_preserved_without_completeness_upgrade(monkeypatch, truncated, stop_reason):
    app_id = 2650 if truncated else 2651
    rows = _fixture_reviews(count=7)
    contract = _contract(app_id, max_reviews=3)
    metadata = AnalyzeMetadata(
        app_id=app_id,
        requested=contract.max_reviews,
        retrieved=len(rows),
        retrieved_count=len(rows),
        retrieved_reviews=len(rows),
        deduplicated_count=len(rows),
        analysis_population_count=len(rows),
        language="english",
        languages=contract.languages,
        collection_complete=False,
        truncated_by_max_reviews=truncated,
        stop_reason=stop_reason,
        coverage_status="incomplete",
        sampling_contract=contract.to_dict(),
        active_filters={
            "collection_complete": False,
            "scope_complete": False,
            "truncated_by_max_reviews": truncated,
            "stop_reason": stop_reason,
        },
    )
    run_id = uuid4().hex
    storage.create_general_analysis_run(run_id, app_id, config={"sampling_contract": contract.to_dict()}, requested_review_count=contract.max_reviews)
    storage.transition_general_analysis_run(run_id, "running", phase="research_core")
    analysis_route._run_analysis_job(run_id, app_id, rows, metadata, {}, semantic_runtime=_no_provider())
    immutable = storage.get_analysis_run_result(run_id)
    report = immutable["research_report"]
    expected = build_snapshot_research_report(rows, metadata=immutable["metadata"])
    assert report == expected
    assert report["population"]["collection_complete"] is False
    assert report["population"]["truncated_by_max_reviews"] is truncated
    assert report["population"]["stop_reason"] == stop_reason
    assert report["recommendation"]["inference_validity"]["inference_eligibility"] == "limited"


def test_stale_read_and_repeated_get_are_side_effect_free(monkeypatch):
    app_id = 2660
    rows = _fixture_reviews(count=6)
    response, background = _start_analysis(monkeypatch, app_id, rows, _no_provider())
    _run_background(background)
    latest = storage.load_analysis_result(app_id)
    metadata = dict(latest["metadata"])
    metadata["review_fingerprint"] = "old-fingerprint"
    storage.save_analysis_result(
        app_id=app_id,
        metadata=metadata,
        insights=latest["insights"],
        reviews=latest["reviews"],
        status="completed",
        run_id=response.run_id,
        research_report=latest["research_report"],
        semantic_status=latest["semantic_status"],
    )
    monkeypatch.setattr(analysis_route, "fetch_app_details", lambda *_a, **_k: {})
    monkeypatch.setattr(analysis_route.storage, "get_reviews_fingerprint", lambda *_a, **_k: "new-fingerprint")
    for name in ("build_snapshot_research_report", "build_reviews_dataframe", "prepare_insights"):
        monkeypatch.setattr(analysis_route, name, lambda *_a, _name=name, **_k: (_ for _ in ()).throw(AssertionError(f"GET called {_name}")))
    monkeypatch.setattr(analysis_route.llm, "apply_review_labels", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("GET called apply_review_labels")))

    first = analysis_route.get_analysis_result(app_id)
    second = analysis_route.get_analysis_result(app_id)
    assert first.stale is True
    assert first.data_refreshed is False
    assert first.stale_reason == "Review pool changed since analysis run"
    assert first.research_report == latest["research_report"]
    assert first.model_dump() == second.model_dump()
    stored_after = storage.load_analysis_result(app_id)
    assert stored_after["research_report"] == latest["research_report"]
    assert stored_after["insights"] == latest["insights"]
    assert stored_after["semantic_status"] == latest["semantic_status"]


def test_reanalysis_clears_previous_report_and_run_specific_results_remain_immutable(monkeypatch):
    app_id = 2670
    runtime = _no_provider()
    rows_a = _fixture_reviews(count=10)
    rows_b = _fixture_reviews(offset=100, count=6)

    response_a, background_a = _start_analysis(monkeypatch, app_id, rows_a, runtime)
    _run_background(background_a)
    immutable_a = storage.get_analysis_run_result(response_a.run_id)

    _install_acquisition(monkeypatch, rows_b, runtime)
    background_b = _CaptureBackground()
    response_b = analysis_route.analyze(
        analysis_route.AnalyzeRequest(app_id=app_id, sampling=_contract(app_id), persist=True),
        background_b,
    )
    in_progress = storage.load_analysis_result(app_id)
    assert in_progress["status"] == "running"
    assert in_progress["research_report"] is None
    assert in_progress["semantic_status"]["status"] == "unavailable"
    _run_background(background_b)

    immutable_b = storage.get_analysis_run_result(response_b.run_id)
    latest = storage.load_analysis_result(app_id)
    assert immutable_a["research_report"]["population"]["review_count"] == 10
    assert immutable_b["research_report"]["population"]["review_count"] == 6
    assert latest["research_report"] == immutable_b["research_report"]
    assert storage.get_analysis_run_result(response_a.run_id)["research_report"] == immutable_a["research_report"]
    dashboard_a = web_contract.build_dashboard_payload(app_id, requested_run_id=response_a.run_id)
    dashboard_b = web_contract.build_dashboard_payload(app_id, requested_run_id=response_b.run_id)
    assert dashboard_a["research_report"] == immutable_a["research_report"]
    assert dashboard_b["research_report"] == immutable_b["research_report"]
    assert dashboard_a["research_report"] != dashboard_b["research_report"]


def test_historical_semantic_only_result_remains_usable_without_fabricated_research_report():
    app_id = 2680
    run_id = uuid4().hex
    storage.create_general_analysis_run(run_id, app_id, config={"legacy": True}, requested_review_count=2)
    storage.transition_general_analysis_run(run_id, "running", phase="aggregating")
    insights = {
        "five_questions": {"current_snapshot": {"why": "legacy"}},
        "metric_provenance": {"classification_coverage": {"numerator": 2}},
    }
    storage.finalize_general_analysis_run(
        run_id,
        app_id,
        {"app_id": app_id, "retrieved": 2},
        insights,
        [],
        counts={"analysis_population_count": 2, "classified_count": 2},
        research_report=None,
        semantic_status=None,
    )
    payload = web_contract.build_dashboard_payload(app_id)
    assert payload["research_report"] is None
    assert payload["readiness"]["research_ready"] is False
    assert payload["readiness"]["semantic_ready"] is True
    assert payload["insights"] == insights
