from __future__ import annotations

import json
import os

os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from sqlalchemy import text

from apps.api.senti_next import db, llm
from apps.api.senti_next.classifier_taxonomy import baseline_classifier_taxonomy
from apps.api.senti_next.classification_materialization import create_classification_materialization
from apps.api.senti_next.semantic_measurement_bundle import activate_measurement_bundle, bootstrap_baseline_measurement_bundle
from apps.api.senti_next.topic_measurement import build_semantic_measurement_result
from apps.api.senti_next.unified_research_result import build_unified_research_result


@pytest.fixture(autouse=True)
def isolated_db():
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def _bundle_and_contract():
    bundle = bootstrap_baseline_measurement_bundle()
    bundle = activate_measurement_bundle(bundle["bundle_id"], operator="test", reason="stage4a3")
    return bundle, baseline_classifier_taxonomy()


def _materialize(run_id, rows, labels_by_id):
    bundle, contract = _bundle_and_contract()
    labels = {}
    for row in rows:
        review_id = str(row["recommendationid"])
        payload = labels_by_id.get(review_id)
        if payload is None:
            continue
        identity = llm.classification_identity(
            row, None, provider=bundle["classifier_provider"],
            model_id=bundle["classifier_model_id"],
            prompt_version=bundle["classifier_prompt_version"],
            taxonomy_contract=contract,
        )
        labels[review_id] = {
            **identity, "payload": payload, "label_origin": "llm",
            "validated": True, "provider": bundle["classifier_provider"],
            "model_id": bundle["classifier_model_id"],
        }
    frozen = create_classification_materialization(
        run_id=run_id, app_id=1, all_reviews=rows, bundle=bundle,
        taxonomy_contract=contract, labels=labels,
    )
    return frozen


def test_3f_uses_classified_denominator_and_primary_is_exclusive():
    rows = [{"recommendationid": f"r{i}", "review": f"review {i}"} for i in range(1, 5)]
    frozen = _materialize("3f-basic", rows, {
        "r1": {"subcategories": ["technical/performance", "technical/bugs"], "issue_subcategories": ["technical/performance"], "request_subcategories": []},
        "r2": {"subcategories": ["technical/performance", "ui_ux_accessibility/quality_of_life"], "issue_subcategories": ["technical/performance"], "request_subcategories": ["ui_ux_accessibility/quality_of_life"]},
        "r3": {"subcategories": ["gameplay/balance"], "issue_subcategories": ["gameplay/balance"], "request_subcategories": []},
        "r4": {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []},
    })
    result = build_semantic_measurement_result(run_id="3f-basic", materialization_id=frozen["materialization_id"])
    topics = {row["topic_key"]: row for row in result["topics"]}
    assert result["classified_n"] == 4
    assert topics["technical/performance"]["topic_n"] == 2
    assert topics["technical/performance"]["topic_share"] == 0.5
    assert topics["technical/performance"]["issue_n"] == 2
    assert topics["technical/performance"]["issue_share"] == 0.5
    assert topics["ui_ux_accessibility/quality_of_life"]["request_n"] == 1
    assert topics["ui_ux_accessibility/quality_of_life"]["request_share"] == 0.25
    assert sum(row["primary_n"] for row in result["topics"]) == 4
    assert sum(row["topic_n"] for row in result["topics"]) > 4
    assert result["claim_status"] == "PROVISIONAL"


def test_3f_coverage_and_zero_classified_have_explicit_states():
    rows = [{"recommendationid": f"r{i}", "review": f"review {i}"} for i in range(5)]
    partial = _materialize("3f-partial", rows, {
        "r0": {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []},
        "r1": {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []},
    })
    partial_result = build_semantic_measurement_result(run_id="3f-partial", materialization_id=partial["materialization_id"])
    assert partial_result["classified_n"] == 2
    assert partial_result["classification_coverage"] == 0.4
    assert partial_result["coverage_status"] == "PARTIAL"
    assert "partial_classification_coverage" in partial_result["limitations"]

    empty = _materialize("3f-empty", rows, {})
    empty_result = build_semantic_measurement_result(run_id="3f-empty", materialization_id=empty["materialization_id"])
    assert empty_result["classified_n"] == 0
    assert empty_result["classification_coverage"] == 0.0
    assert empty_result["coverage_status"] == "NONE"
    assert empty_result["measurement_state"] == "MEASURED"
    assert "no_validated_classifications" in empty_result["limitations"]
    assert all(row["topic_share"] == 0.0 for row in empty_result["topics"])


def test_3f_rejects_invalid_frozen_payload():
    rows = [{"recommendationid": "r1", "review": "review"}]
    frozen = _materialize("3f-invalid", rows, {
        "r1": {"subcategories": ["other/general"], "issue_subcategories": ["technical/bugs"], "request_subcategories": []},
    })
    with pytest.raises(ValueError, match="semantic_measurement_invalid_materialized_payload"):
        build_semantic_measurement_result(run_id="3f-invalid", materialization_id=frozen["materialization_id"])


def test_unified_result_keeps_exact_quantitative_report_for_quantitative_only_run():
    report = {"schema_version": "research-report-v1", "recommendation": {"population": {"valid_n": 3}}}
    result = build_unified_research_result(
        run_id="quant-only", app_id=10, research_report=report,
        semantic_measurement_result=None,
        semantic_status={"status": "unavailable", "reason": "no_active_measurement_bundle"},
        metadata={"population_provenance": {"population_n": 3}},
    )
    assert result["quantitative"] == report
    assert result["semantic"] is None
    assert result["semantic_status"]["reason"] == "no_active_measurement_bundle"
    assert result["provenance"]["run_id"] == "quant-only"
    assert result["result_fingerprint"]
