from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.senti_next.acquisition import AcquisitionResult
from apps.api.senti_next.routes import version_comparison as route
from apps.api.senti_next.version_comparison import COHORTS, cohort_windows


def _event(event_id: str, day: str) -> dict:
    return {
        "event_id": event_id,
        "app_id": 570,
        "event_name": event_id,
        "event_date": day,
        "effective_at": None,
        "anchor_precision": "day",
        "manual_verified": True,
        "event_status": "verified",
    }


def _complete_result(reviews=None) -> AcquisitionResult:
    reviews = list(reviews or [])
    return AcquisitionResult(
        reviews=reviews,
        source="steam",
        fetched_count=len(reviews),
        stored_count=len(reviews),
        cache_hit=False,
        collection_complete=True,
        truncated_by_max_reviews=False,
        stop_reason="end_of_results",
        stats={
            "collection_complete": True,
            "scope_complete": True,
            "retrieved_count": len(reviews),
        },
    )


def test_version_comparison_acquires_only_four_max_window_populations(monkeypatch):
    event_a = _event("a" * 8, "2026-01-10")
    event_b = _event("b" * 8, "2026-03-10")
    request = route.VersionComparisonRequest(
        app_id=570,
        event_a_id=event_a["event_id"],
        event_b_id=event_b["event_id"],
        window_days=3,
        analysis_mode="raw_only",
        semantic_budget=0,
    )
    contracts = []

    def fake_ensure(contract):
        contracts.append(contract)
        return _complete_result()

    monkeypatch.setattr(route.acquisition, "ensure_reviews", fake_ensure)
    acquired, reports = route._acquire_population(request, event_a, event_b)

    assert len(contracts) == 4
    assert set(acquired) == set(COHORTS)
    assert set(reports) == set(COHORTS)
    expected = cohort_windows(event_a, event_b, 14)
    actual_bounds = {(contract.start_time, contract.end_time) for contract in contracts}
    expected_bounds = {
        (window["start_time"], window["end_time_exclusive"] - 1)
        for window in expected.values()
    }
    assert actual_bounds == expected_bounds


def test_raw_only_execute_completes_without_semantic_classifier(monkeypatch):
    event_a = _event("a" * 8, "2026-01-10")
    event_b = _event("b" * 8, "2026-03-10")
    saved = []

    monkeypatch.setattr(route, "_events", lambda request: (event_a, event_b))
    monkeypatch.setattr(route, "cohort_overlap_report", lambda *args, **kwargs: {"status": "disjoint", "overlaps": []})
    monkeypatch.setattr(route, "_acquire_population", lambda *args, **kwargs: ({cohort: [] for cohort in COHORTS}, {cohort: _complete_result().to_dict() for cohort in COHORTS}))
    monkeypatch.setattr(route, "comparability_matrix", lambda cohorts: {})
    monkeypatch.setattr(route, "standardization_sensitivity", lambda cohorts: {})
    monkeypatch.setattr(route.storage, "list_version_events", lambda app_id: [event_a, event_b])
    monkeypatch.setattr(route, "confounder_events", lambda *args, **kwargs: [])
    monkeypatch.setattr(route.storage, "save_analysis_run_metrics", lambda run_id, metrics, **kwargs: saved.append((metrics, kwargs)))

    route._execute(
        "raw-run",
        {
            "app_id": 570,
            "event_a_id": event_a["event_id"],
            "event_b_id": event_b["event_id"],
            "window_days": 7,
            "languages": ["all"],
            "max_reviews_per_cohort": 500,
            "analysis_mode": "raw_only",
            "semantic_budget": 0,
        },
    )

    assert saved[-1][1]["status"] == "completed"
    assert saved[-1][0]["analysis_mode"] == "raw_only"
    assert saved[-1][0]["semantic"] is None
    assert saved[-1][0]["acquisition_window_days"] == 14


def test_start_created_run_is_followed_by_completed_get(monkeypatch):
    event_a = _event("a" * 8, "2026-01-10")
    event_b = _event("b" * 8, "2026-03-10")
    runs = {}
    plan = {
        "schema_version": "version-comparison-plan-v3",
        "app_id": 570,
        "event_a": event_a,
        "event_b": event_b,
        "cohort_overlap": {"status": "disjoint", "overlaps": []},
    }

    monkeypatch.setattr(route, "_plan", lambda request: plan)

    def fake_create(payload):
        run = {
            **payload,
            "config": payload["config"],
            "metrics": None,
            "phase": None,
            "error": None,
        }
        runs[payload["run_id"]] = run
        return dict(run)

    def fake_execute(run_id, request_payload):
        runs[run_id] = {
            **runs[run_id],
            "status": "completed",
            "phase": "completed",
            "metrics": {"schema_version": "version-comparison-v3"},
        }

    monkeypatch.setattr(route.storage, "create_analysis_run", fake_create)
    monkeypatch.setattr(route.storage, "get_analysis_run", lambda run_id: runs.get(run_id))
    monkeypatch.setattr(route, "_execute", fake_execute)

    app = FastAPI()
    app.include_router(route.router)
    client = TestClient(app)
    response = client.post(
        "/version-comparison/start",
        json={
            "app_id": 570,
            "event_a_id": event_a["event_id"],
            "event_b_id": event_b["event_id"],
            "window_days": 7,
            "languages": ["all"],
            "max_reviews_per_cohort": 500,
            "analysis_mode": "raw_only",
            "semantic_budget": 0,
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["run"]["status"] == "created"

    follow_up = client.get(f"/version-comparison/runs/{body['run']['run_id']}")
    assert follow_up.status_code == 200
    assert follow_up.json()["status"] == "completed"


def test_semantic_manifest_labels_then_completed(monkeypatch):
    event_a = _event("a" * 8, "2026-01-10")
    event_b = _event("b" * 8, "2026-03-10")
    cohorts = {
        cohort: [{
            "recommendationid": f"{cohort}-1",
            "timestamp_created": cohort_windows(event_a, event_b, 7)[cohort]["start_time"] + 3600,
            "language": "english",
            "voted_up": True,
        }]
        for cohort in COHORTS
    }
    reports = {cohort: _complete_result(cohorts[cohort]).to_dict() for cohort in COHORTS}
    saved = []
    label_calls = []

    monkeypatch.setattr(route, "_events", lambda request: (event_a, event_b))
    monkeypatch.setattr(route, "cohort_overlap_report", lambda *args, **kwargs: {"status": "disjoint", "overlaps": []})
    monkeypatch.setattr(route, "_acquire_population", lambda *args, **kwargs: (cohorts, reports))
    monkeypatch.setattr(route, "comparability_matrix", lambda values: {})
    monkeypatch.setattr(route, "standardization_sensitivity", lambda values: {})
    monkeypatch.setattr(route.storage, "list_version_events", lambda app_id: [event_a, event_b])
    monkeypatch.setattr(route, "confounder_events", lambda *args, **kwargs: [])
    monkeypatch.setattr(route, "_build_semantic_sample_manifest", lambda *args, **kwargs: {
        "schema_version": "semantic-sample-v1",
        "status": "ready",
        "target_distribution": {"english|0": 1.0},
        "quotas": {"english|0": 1},
        "selected_review_ids": {cohort: [f"{cohort}-1"] for cohort in COHORTS},
    })
    monkeypatch.setattr(route, "semantic_reviews_from_manifest", lambda values, manifest: [row for cohort in COHORTS for row in values[cohort]])
    monkeypatch.setattr(route.storage, "load_review_labels", lambda app_id: {
        f"{cohort}-1": {
            "label_origin": "llm",
            "validated": True,
            "payload": {"subcategories": ["gameplay/combat"], "issue_subcategories": [], "request_subcategories": []},
        }
        for cohort in COHORTS
    })
    monkeypatch.setattr(route.storage, "save_analysis_run_metrics", lambda run_id, metrics, **kwargs: saved.append((metrics, kwargs)))

    from apps.api.senti_next import llm
    from apps.api.senti_next import steam_api
    monkeypatch.setattr(llm, "ensure_review_labels", lambda app_id, reviews, **kwargs: label_calls.append((app_id, list(reviews))))
    monkeypatch.setattr(steam_api, "fetch_app_details", lambda app_id: {})

    route._execute(
        "semantic-run",
        {
            "app_id": 570,
            "event_a_id": event_a["event_id"],
            "event_b_id": event_b["event_id"],
            "window_days": 7,
            "languages": ["all"],
            "max_reviews_per_cohort": 500,
            "analysis_mode": "semantic",
            "semantic_budget": 4,
        },
    )

    assert len(label_calls) == 1
    assert len(label_calls[0][1]) == 4
    assert saved[-1][1]["status"] == "completed"
    assert saved[-1][0]["semantic"]["status"] == "ready"
