from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from sqlalchemy import text

from apps.api.senti_next import db, llm, storage
from apps.api.senti_next import classifier_validation_runtime as validation_runtime
from apps.api.senti_next.classifier_taxonomy import baseline_classifier_taxonomy
from apps.api.senti_next.classification_materialization import create_classification_materialization
from apps.api.senti_next.semantic_measurement_bundle import (
    activate_measurement_bundle,
    bootstrap_baseline_measurement_bundle,
    create_measurement_bundle,
    persist_classifier_validation_run,
    retire_measurement_bundle,
)
from apps.api.senti_next.semantic_measurement_result_schema import migrate_semantic_measurement_result
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


def _materialize(run_id, rows, labels_by_id, *, bundle=None, contract=None):
    if bundle is None or contract is None:
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


def _validated_bundle(monkeypatch):
    contract = baseline_classifier_taxonomy()
    target = "other/general"
    gold = []
    predictions = {}
    for topic in contract.active_topic_keys:
        for repetition in range(5):
            review_id = f"{topic}-{repetition}"
            request_labels = [] if topic == target else [topic]
            gold.append({
                "review_id": review_id,
                "gold_labels": [topic],
                "gold_primary_label": topic,
                "gold_issue_labels": [topic],
                "gold_request_labels": request_labels,
            })
            predictions[review_id] = {
                "subcategories": [topic],
                "issue_subcategories": [topic],
                "request_subcategories": request_labels,
            }

    def production_execution(items, *, taxonomy_contract):
        return validation_runtime.ClassifierExecutionResult(
            predictions=predictions,
            execution_mode="production_classifier",
            actual_model_id="actual:production-model",
            actual_provider="fake-production-provider",
            prompt_version="production-prompt-v1",
            schema_version="production-schema-v1",
        )

    monkeypatch.setattr(validation_runtime, "_execute_production_classifier", production_execution)
    run = validation_runtime.run_classifier_validation(gold, taxonomy_contract=contract)
    assert run["gate_status"] == "PASS"
    persisted = persist_classifier_validation_run(run)
    bundle = create_measurement_bundle(
        taxonomy_contract=contract, validation_run=persisted, measurement_status="VALIDATED",
    )
    return bundle, contract, target


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


def test_bundle_retirement_does_not_change_frozen_result():
    rows = [{"recommendationid": "r1", "review": "review"}]
    frozen = _materialize("3f-retirement", rows, {
        "r1": {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []},
    })
    before = build_semantic_measurement_result(run_id="3f-retirement", materialization_id=frozen["materialization_id"])
    retire_measurement_bundle(frozen["measurement_bundle_id"], operator="test", reason="stage4a3-r1")
    after = build_semantic_measurement_result(run_id="3f-retirement", materialization_id=frozen["materialization_id"])
    assert before == after
    assert before["semantic_measurement_result_fingerprint"] == after["semantic_measurement_result_fingerprint"]
    assert before["claim_status"] == after["claim_status"] == "PROVISIONAL"


def test_validated_topic_issue_request_qualification(monkeypatch):
    bundle, contract, target = _validated_bundle(monkeypatch)
    row = {"recommendationid": "validated-1", "review": "validated review"}
    frozen = _materialize(
        "3f-validated", [row],
        {"validated-1": {"subcategories": [target], "issue_subcategories": [target], "request_subcategories": [target]}},
        bundle=bundle, contract=contract,
    )
    result = build_semantic_measurement_result(run_id="3f-validated", materialization_id=frozen["materialization_id"])
    topic = next(item for item in result["topics"] if item["topic_key"] == target)
    assert result["claim_status"] == "VALIDATED"
    assert topic["topic_validation"]["status"] == "VALIDATED"
    assert topic["issue_validation"]["status"] == "VALIDATED"
    assert topic["request_validation"]["status"] == "INSUFFICIENT"
    assert "request_measurement_not_fully_validated" in result["limitations"]


def test_validated_missing_gold_is_explicitly_unvalidated(monkeypatch):
    bundle, contract, target = _validated_bundle(monkeypatch)
    with db.get_connection() as conn:
        conn.execute(
            text("UPDATE classifier_validation_runs SET issue_metrics_json=NULL, request_metrics_json=NULL WHERE validation_run_id=:id"),
            {"id": bundle["validation_run_id"]},
        )
    row = {"recommendationid": "validated-missing-gold", "review": "validated review"}
    frozen = _materialize(
        "3f-missing-gold", [row],
        {"validated-missing-gold": {"subcategories": [target], "issue_subcategories": [], "request_subcategories": []}},
        bundle=bundle, contract=contract,
    )
    result = build_semantic_measurement_result(run_id="3f-missing-gold", materialization_id=frozen["materialization_id"])
    topic = next(item for item in result["topics"] if item["topic_key"] == target)
    assert topic["issue_validation"] == {"status": "UNVALIDATED", "reason": "issue_gold_unavailable"}
    assert topic["request_validation"] == {"status": "UNVALIDATED", "reason": "request_gold_unavailable"}


def test_invalid_frozen_measurement_status_fails_closed():
    rows = [{"recommendationid": "r1", "review": "review"}]
    frozen = _materialize("3f-retired-materialization", rows, {
        "r1": {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []},
    })
    with db.get_connection() as conn:
        conn.execute(
            text("UPDATE classification_materializations SET measurement_status='RETIRED' WHERE materialization_id=:id"),
            {"id": frozen["materialization_id"]},
        )
    with pytest.raises(ValueError, match="semantic_measurement_invalid_frozen_measurement_status"):
        build_semantic_measurement_result(run_id="3f-retired-materialization", materialization_id=frozen["materialization_id"])


def test_estimate_uses_game_context_and_strict_reason_accounting(monkeypatch):
    from apps.api.senti_next.providers import config as provider_config

    monkeypatch.setattr(provider_config, "get_active_provider", lambda: ("openai", "test-model"))
    bundle, contract = _bundle_and_contract()
    review = {"recommendationid": "estimate-1", "review": "A review with enough text to classify", "voted_up": True, "language": "english"}
    context = {"name": "Game A", "genres": ["Action"], "categories": ["Single-player"]}
    identity = llm.classification_identity(
        review, context, provider="openai", model_id="openai:test-model",
        prompt_version=llm.active_classifier_prompt_version(), taxonomy_contract=contract,
    )
    storage.upsert_review_label(
        91, "estimate-1", identity["review_hash"], {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []},
        "openai:test-model", identity["prompt_version"], label_origin="llm", validated=True,
        taxonomy_version=contract.taxonomy_version, taxonomy_snapshot_id=contract.snapshot_id,
        taxonomy_fingerprint=contract.taxonomy_fingerprint, provider="openai", model_id="openai:test-model",
        classification_input_hash=identity["classification_input_hash"],
    )
    matching = llm.estimate_review_labeling(
        91, [review], game_context=context, taxonomy_contract=contract, strict_taxonomy_identity=True,
    )
    assert matching["cached_reviews"] == 1
    assert matching["llm_reviews"] == 0
    different = llm.estimate_review_labeling(
        91, [review], game_context={**context, "name": "Game B"}, taxonomy_contract=contract, strict_taxonomy_identity=True,
    )
    assert different["cached_reviews"] == 0
    assert different["needs_refresh_reviews"] == 1
    assert different["reasons"]["identity_mismatch"] == 1


def test_migration_23_is_additive_idempotent_and_retains_rows():
    import sqlite3

    raw = sqlite3.connect(":memory:")
    raw.execute("CREATE TABLE analysis_results (id INTEGER PRIMARY KEY, payload TEXT)")
    raw.execute("CREATE TABLE analysis_run_results (id INTEGER PRIMARY KEY, payload TEXT)")
    raw.execute("INSERT INTO analysis_results(id, payload) VALUES (1, 'old')")
    raw.execute("INSERT INTO analysis_run_results(id, payload) VALUES (1, 'old-run')")
    migrate_semantic_measurement_result(raw)
    migrate_semantic_measurement_result(raw)
    for table in ("analysis_results", "analysis_run_results"):
        columns = {row[1] for row in raw.execute(f"PRAGMA table_info({table})").fetchall()}
        assert {"semantic_measurement_result", "unified_research_result"} <= columns
    assert raw.execute("SELECT payload FROM analysis_results WHERE id=1").fetchone()[0] == "old"
    assert raw.execute("SELECT payload FROM analysis_run_results WHERE id=1").fetchone()[0] == "old-run"
    raw.close()


def test_restart_persistence_and_immutable_semantic_conflict(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'stage4a3-r1.db'}")
    db.close_engine()
    db._engine = None
    db.init_db()
    rows = [{"recommendationid": "restart-1", "review": "restart review"}]
    frozen = _materialize("restart-r1", rows, {
        "restart-1": {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []},
    })
    semantic = build_semantic_measurement_result(run_id="restart-r1", materialization_id=frozen["materialization_id"])
    quantitative = {"schema_version": "research-report-v1", "recommendation": {"population": {"valid_n": 1}}}
    unified = build_unified_research_result(
        run_id="restart-r1", app_id=1, research_report=quantitative,
        semantic_measurement_result=semantic,
        semantic_status={"status": "available"},
        metadata={"population_provenance": {"population_n": 1}},
    )
    storage.create_general_analysis_run("restart-r1", 1, config={}, requested_languages=["english"], requested_review_count=1)
    storage.transition_general_analysis_run("restart-r1", "running", phase="research_core")
    storage.finalize_general_analysis_run(
        "restart-r1", 1, {}, {}, [], research_report=quantitative,
        semantic_status={"status": "available"}, semantic_measurement_result=semantic,
        unified_research_result=unified,
    )
    db.close_engine()
    db._engine = None
    loaded = storage.get_analysis_run_result("restart-r1")
    assert loaded["semantic_measurement_result"] == semantic
    assert loaded["unified_research_result"] == unified
    assert loaded["unified_research_result"]["quantitative"] == quantitative

    altered = {**semantic, "semantic_measurement_result_fingerprint": "different-fingerprint"}
    with pytest.raises(ValueError, match="semantic_measurement_result_conflict"):
        storage.finalize_general_analysis_run(
            "restart-r1", 1, {}, {}, [], research_report=quantitative,
            semantic_status={"status": "available"}, semantic_measurement_result=altered,
            unified_research_result=unified,
        )
    assert storage.get_analysis_run_result("restart-r1")["semantic_measurement_result"] == semantic


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
