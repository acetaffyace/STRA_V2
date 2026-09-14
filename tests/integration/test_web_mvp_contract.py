from senti_next import web_contract
from senti_next import llm
import pandas as pd


def test_dashboard_contract_distinguishes_reviews_from_incompatible_analysis(monkeypatch):
    monkeypatch.setattr(web_contract.storage, "count_reviews", lambda app_id: 500)
    monkeypatch.setattr(web_contract.storage, "get_analysis_run", lambda run_id: {"status": "completed", "classified_count": 0})
    monkeypatch.setattr(web_contract.storage, "get_analysis_run_result", lambda run_id: None)
    monkeypatch.setattr(web_contract.storage, "get_active_general_analysis", lambda app_id: None)
    monkeypatch.setattr(web_contract.storage, "get_analysis_design", lambda run_id: None)
    monkeypatch.setattr(
        web_contract.storage,
        "load_analysis_result",
        lambda app_id: {
            "status": "completed",
            "run_id": "run-4012810",
            "metadata": {"app_id": app_id, "retrieved": 500},
            "insights": {"five_questions": {"current_snapshot": None}},
            "reviews": [{"review_id": "r1"}],
            "error": None,
        },
    )

    payload = web_contract.build_dashboard_payload(4012810)

    assert payload["readiness"]["state"] == "ANALYSIS_INCOMPATIBLE"
    assert payload["readiness"]["review_count"] == 500
    assert payload["readiness"]["classified_count"] == 0
    assert payload["readiness"]["classification_coverage"] == 0
    assert payload["readiness"]["result_available"] is False
    assert payload["readiness"]["evidence_available"] is False


def test_dashboard_contract_marks_validated_run_ready(monkeypatch):
    monkeypatch.setattr(web_contract.storage, "count_reviews", lambda app_id: 10)
    monkeypatch.setattr(web_contract.storage, "get_analysis_run", lambda run_id: {"status": "completed", "classified_count": 8})
    monkeypatch.setattr(web_contract.storage, "get_analysis_run_result", lambda run_id: {"run_id": run_id})
    monkeypatch.setattr(web_contract.storage, "get_active_general_analysis", lambda app_id: None)
    monkeypatch.setattr(web_contract.storage, "get_analysis_design", lambda run_id: {"run_id": run_id})
    monkeypatch.setattr(
        web_contract.storage,
        "load_analysis_result",
        lambda app_id: {
            "status": "completed",
            "run_id": "run-ready",
            "metadata": {"app_id": app_id, "retrieved": 10},
            "insights": {
                "metric_provenance": {"classification_coverage": {"numerator": 8}},
                "five_questions": {"current_snapshot": {"why": "x"}},
            },
            "reviews": [],
            "error": None,
        },
    )

    payload = web_contract.build_dashboard_payload(4012810)

    assert payload["readiness"]["state"] == "ANALYSIS_READY"
    assert payload["readiness"]["classification_coverage"] == 0.8
    assert payload["readiness"]["analysis_design_available"] is True


def test_runtime_result_uses_canonical_label_envelope_for_coverage():
    frame = pd.DataFrame([{"review_id": "r1", "review": "A useful review"}])
    labeled = llm.apply_review_labels(
        frame,
        {
            "r1": {
                "model": "deepseek:deepseek-v4-flash",
                "payload": {"main_category": "technical", "subcategories": ["technical/stability_crashes"]},
                "label_origin": "llm",
                "validated": True,
            }
        },
    )
    assert labeled.loc[0, "llm_label_origin"] == "llm"
    assert bool(labeled.loc[0, "llm_validated"]) is True


def test_dashboard_exposes_independent_research_and_semantic_readiness(monkeypatch):
    report = {"schema_version": "research-report-v1", "mode": "snapshot"}
    semantic_status = {"status": "unavailable", "reason": "no_provider"}
    monkeypatch.setattr(web_contract.storage, "count_reviews", lambda app_id: 2)
    monkeypatch.setattr(web_contract.storage, "get_active_general_analysis", lambda app_id: None)
    monkeypatch.setattr(web_contract.storage, "get_analysis_design", lambda run_id: None)
    monkeypatch.setattr(web_contract.storage, "get_analysis_run", lambda run_id: {"status": "completed", "classified_count": 0})
    monkeypatch.setattr(web_contract.storage, "get_analysis_run_result", lambda run_id: {
        "run_id": run_id,
        "research_report": report,
        "semantic_status": semantic_status,
    })
    monkeypatch.setattr(web_contract.storage, "load_analysis_result", lambda app_id: {
        "status": "completed",
        "run_id": "run-quant",
        "metadata": {"app_id": app_id, "retrieved": 2},
        "insights": None,
        "research_report": report,
        "semantic_status": semantic_status,
        "reviews": [],
        "error": None,
    })

    payload = web_contract.build_dashboard_payload(4012810)

    assert payload["research_report"] == report
    assert payload["semantic_status"] == semantic_status
    assert payload["readiness"]["research_ready"] is True
    assert payload["readiness"]["semantic_ready"] is False
    assert payload["readiness"]["research_result_available"] is True
    assert payload["readiness"]["semantic_result_available"] is False
    assert payload["readiness"]["result_available"] is True
    assert payload["readiness"]["state"] == "ANALYSIS_READY"


def test_quantitative_only_500_review_fixture_is_reopenable(monkeypatch):
    report = {
        "schema_version": "research-report-v1",
        "population": {
            "review_count": 500,
            "sampling_contract": {"languages": ["all"], "max_reviews": 500},
            "collection_complete": False,
            "truncated_by_max_reviews": True,
            "stop_reason": "max_reviews_reached",
        },
        "recommendation": {
            "population": {
                "valid_n": 500,
                "recommended_n": 460,
                "not_recommended_n": 40,
                "recommendation_rate": 0.92,
            }
        },
    }
    semantic_status = {"status": "unavailable", "reason": "no_provider"}
    run_id = "a04d20626bd3471da2098b83eb474d53"
    monkeypatch.setattr(web_contract.storage, "count_reviews", lambda app_id: 500)
    monkeypatch.setattr(web_contract.storage, "get_active_general_analysis", lambda app_id: None)
    monkeypatch.setattr(web_contract.storage, "get_analysis_design", lambda run_id: {"run_id": run_id})
    monkeypatch.setattr(web_contract.storage, "get_analysis_run", lambda run_id: {
        "status": "completed",
        "target_app_id": 2638890,
        "classified_count": 0,
    })
    monkeypatch.setattr(web_contract.storage, "get_analysis_run_result", lambda run_id: {
        "run_id": run_id,
        "metadata": {"app_id": 2638890, "retrieved": 500},
        "research_report": report,
        "semantic_status": semantic_status,
        "insights": None,
        "reviews": [],
    })
    monkeypatch.setattr(web_contract.storage, "load_analysis_result", lambda app_id: {
        "status": "completed",
        "run_id": run_id,
        "metadata": {"app_id": app_id, "retrieved": 500},
        "research_report": report,
        "semantic_status": semantic_status,
        "insights": None,
        "reviews": [],
        "error": None,
    })

    payload = web_contract.build_dashboard_payload(2638890, requested_run_id=run_id)

    assert payload["readiness"]["state"] == "ANALYSIS_READY"
    assert payload["readiness"]["research_ready"] is True
    assert payload["readiness"]["research_result_available"] is True
    assert payload["readiness"]["semantic_ready"] is False
    assert payload["readiness"]["semantic_result_available"] is False
    assert payload["readiness"]["result_available"] is True
    presentation = payload["presentation"]
    assert presentation is not None
    assert presentation["research_snapshot"]["population_n"] == 500
    assert presentation["research_snapshot"]["valid_n"] == 500
    assert presentation["research_snapshot"]["recommended_n"] == 460
    assert presentation["research_snapshot"]["not_recommended_n"] == 40
    assert presentation["research_snapshot"]["recommendation_rate"] == 0.92
    assert presentation["semantic"]["available"] is False
