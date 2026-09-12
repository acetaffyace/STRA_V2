from datetime import date

from apps.api.senti_next import presentation_projections as projections


def run(run_id="run-a", population=3):
    return {"run_id": run_id, "target_app_id": 10, "run_type": "general_analysis", "status": "completed", "analysis_population_count": population, "config": {}}


def rows():
    return [
        {"review_id": "a", "timestamp_created": 1785627000, "voted_up": True},
        {"review_id": "b", "timestamp_created": 1785717000, "voted_up": False},
        {"review_id": "c", "timestamp_created": 1785760200, "voted_up": True},
    ]


def provenance(items):
    return {"schema_version": "general-population-temporal-v1", "population_count": len(items), "complete": True, "rows": items}


def patch_general(monkeypatch, current_run, result):
    monkeypatch.setattr(projections.storage, "get_analysis_run", lambda run_id: current_run if run_id == current_run["run_id"] else None)
    monkeypatch.setattr(projections.storage, "get_analysis_run_result", lambda run_id: result)


def test_future_run_temporal_projections_reconcile(monkeypatch):
    current_run = run()
    patch_general(monkeypatch, current_run, {"reviews": [{"review_id": "sample-only"}], "metadata": {"population_provenance": provenance(rows())}})
    volume = projections.daily_review_volume("run-a")
    rate = projections.daily_recommendation_rate("run-a")
    assert volume["available"] is True
    assert sum(point["review_count"] for point in volume["points"]) == 3
    assert sum(point["review_count"] for point in rate["points"]) == 3
    assert sum(point["recommended_count"] for point in rate["points"]) == 2


def test_historical_run_without_provenance_is_unavailable(monkeypatch):
    current_run = run(population=100)
    patch_general(monkeypatch, current_run, {"reviews": [{"review_id": "sample"}], "metadata": {"analysis_population_count": 100}})
    output = projections.daily_review_volume("run-a")
    assert output["available"] is False
    assert output["unavailable_reason"] == "historical_run_population_provenance_unavailable"


def test_count_without_membership_is_unavailable(monkeypatch):
    current_run = run()
    patch_general(monkeypatch, current_run, {"reviews": [], "metadata": {"analysis_population_count": 3}})
    output = projections.daily_review_volume("run-a")
    assert output["available"] is False
    assert output["unavailable_reason"] == "historical_run_population_provenance_unavailable"


def test_zero_review_explicit_bucket_is_null(monkeypatch):
    current_run = run(population=0)
    patch_general(monkeypatch, current_run, {"reviews": [], "metadata": {"population_provenance": provenance([])}})
    output = projections.daily_recommendation_rate("run-a", start=date(2026, 8, 1), end=date(2026, 8, 1))
    assert output["points"] == [{"period": "2026-08-01", "review_count": 0, "recommended_count": 0, "recommendation_rate": None}]


def test_run_isolation_and_immutable_growth(monkeypatch):
    run_a, run_b = run("run-a", 3), run("run-b", 1)
    result_a = {"reviews": [], "metadata": {"population_provenance": provenance(rows())}}
    result_b = {"reviews": [], "metadata": {"population_provenance": provenance([rows()[0]])}}
    monkeypatch.setattr(projections.storage, "get_analysis_run", lambda run_id: {"run-a": run_a, "run-b": run_b}.get(run_id))
    monkeypatch.setattr(projections.storage, "get_analysis_run_result", lambda run_id: {"run-a": result_a, "run-b": result_b}.get(run_id))
    before = projections.daily_review_volume("run-a")
    result_b["metadata"]["population_provenance"]["rows"].append({"review_id": "new", "timestamp_created": 1785900000, "voted_up": True})
    after = projections.daily_review_volume("run-a")
    assert before["points"] == after["points"]
    assert sum(point["review_count"] for point in before["points"]) == 3


def test_version_strip_preserves_unknown_classified_count(monkeypatch):
    current_run = {"run_id": "v2", "target_app_id": 553850, "run_type": "version_review", "status": "completed", "config": {}, "metrics": {"version_review_v2": {"event_a_id": "a", "event_b_id": "b", "window_days": 7, "raw_metrics_a": {"reviews": 20, "reviews_per_day": 2.8, "recommendation_rate": 0.5}, "raw_metrics_b": {"reviews": 30, "reviews_per_day": 4.2, "recommendation_rate": 0.6}, "raw_metric_deltas": {"recommendation_rate_pp": 10.0}, "a_semantic_sample_count": 20, "b_semantic_sample_count": 30, "a_classified_count": 0, "b_classified_count": None, "a_coverage_status": "COMPLETE", "b_coverage_status": "INSUFFICIENT", "coverage_gate": {"status": "BLOCKED"}, "comparison_status": "INSUFFICIENT"}}}
    monkeypatch.setattr(projections.storage, "get_analysis_run", lambda run_id: current_run)
    monkeypatch.setattr(projections.storage, "get_version_event", lambda event_id: {"event_id": event_id})
    output = projections.version_comparison_population_strip("v2")
    assert output["available"] is True
    assert output["classified_count_a"] is None and output["classified_count_b"] is None


def test_recent_summary_keeps_exact_reopen_identity(monkeypatch):
    history = [{"run_id": "run-a", "app_id": 10, "run_type": "general_analysis", "status": "completed"}]
    monkeypatch.setattr(projections.storage, "load_starred_games", lambda: [{"app_id": 10, "name": "Example", "metadata": {}}])
    monkeypatch.setattr(projections.storage, "list_analysis_history", lambda limit: history)
    monkeypatch.setattr(projections.storage, "get_analysis_run", lambda run_id: run())
    monkeypatch.setattr(projections.storage, "get_analysis_run_result", lambda run_id: {"metadata": {}, "insights": {"recommendation": 0.75}})
    item = projections.recent_analysis_summary()["items"][0]
    assert item["reopen_url"] == "/dashboard?game=10&run=run-a"
    assert item["recommendation_rate"] == 0.75
