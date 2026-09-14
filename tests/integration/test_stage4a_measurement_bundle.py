from __future__ import annotations

import os
import sqlite3

os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from sqlalchemy import text

from apps.api.senti_next import classifier_validation_runtime as runtime
from apps.api.senti_next import db, migrations
from apps.api.senti_next.classifier_taxonomy import baseline_classifier_taxonomy
from apps.api.senti_next.classifier_validation_execution_schema import migrate_classifier_validation_execution
from apps.api.senti_next.semantic_measurement_schema import migrate_semantic_measurement
from apps.api.senti_next.semantic_measurement_bundle import (
    PROVISIONAL,
    VALIDATED,
    activate_measurement_bundle,
    bootstrap_baseline_measurement_bundle,
    create_measurement_bundle,
    get_active_measurement_bundle,
    get_measurement_bundle,
    list_measurement_bundles,
    persist_classifier_validation_run,
    retire_measurement_bundle,
)


@pytest.fixture(autouse=True)
def isolated_db():
    db.close_engine()
    db.init_db()
    yield
    db.close_engine()


def _injected_run():
    gold = [
        {"review_id": str(index), "gold_labels": ["technical/bugs"], "gold_primary_label": "technical/bugs", "gold_issue_labels": ["technical/bugs"], "gold_request_labels": ["technical/bugs"]}
        for index in range(5)
    ]

    def fake(items, *, taxonomy_contract):
        return {item["review_id"]: {"subcategories": ["technical/bugs"], "issue_subcategories": ["technical/bugs"], "request_subcategories": ["technical/bugs"]} for item in items}

    return runtime.run_classifier_validation(
        gold,
        classifier=fake,
        injected_classifier_identity={"actual_provider": "fake", "actual_model_id": "fake:model", "prompt_version": "p", "schema_version": "s"},
    )


def _production_run(monkeypatch):
    contract = baseline_classifier_taxonomy()
    gold = []
    predictions = {}
    for index, topic in enumerate(contract.active_topic_keys):
        for repetition in range(5):
            review_id = f"{index}-{repetition}"
            gold.append({
                "review_id": review_id,
                "gold_labels": [topic],
                "gold_primary_label": topic,
                "gold_issue_labels": [topic],
                "gold_request_labels": [topic],
            })
            predictions[review_id] = {"subcategories": [topic], "issue_subcategories": [topic], "request_subcategories": [topic]}

    def test_production_execution(items, *, taxonomy_contract):
        return runtime.ClassifierExecutionResult(
            predictions=predictions,
            execution_mode="production_classifier",
            actual_model_id="actual:production-model",
            actual_provider="fake-production-provider",
            prompt_version="production-prompt-v1",
            schema_version="production-schema-v1",
        )

    monkeypatch.setattr(runtime, "_execute_production_classifier", test_production_execution)
    return runtime.run_classifier_validation(gold, taxonomy_contract=contract)


def test_migration_21_is_idempotent_and_preserves_validation_history():
    with db.get_connection() as conn:
        assert conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar() == migrations.latest_known_schema_version()
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(classifier_validation_runs)")).fetchall()}
        assert {"execution_mode", "actual_model_id", "execution_identity_fingerprint"} <= columns
    db.init_db()
    assert migrations.latest_known_schema_version() == 29


def test_migration_20_to_21_preserves_existing_validation_rows():
    raw = sqlite3.connect(":memory:")
    migrate_semantic_measurement(raw)
    raw.execute("""
        INSERT INTO classifier_validation_runs(
            validation_run_id, validation_dataset_id, validation_dataset_fingerprint,
            taxonomy_snapshot_id, taxonomy_version, taxonomy_fingerprint,
            classifier_provider, classifier_model_id, classifier_prompt_version, classifier_schema_version,
            classifier_taxonomy_contract_fingerprint, gold_item_n, prediction_item_n, matched_prediction_n,
            evaluation_coverage, topic_metrics_json, gate_policy_version, gate_status,
            gate_reasons_json, limitations_json, scorer_report_json, completed_at
        ) VALUES ('legacy-run', 'dataset', 'dataset-fp', 'snapshot', 'taxonomy', 'taxonomy-fp',
            'provider', 'model', 'prompt', 'schema', 'contract-fp', 1, 1, 1, 1.0, '{}',
            'policy', 'PASS', '[]', '[]', '{}', 'now')
    """)
    raw.commit()
    migrate_classifier_validation_execution(raw)
    migrate_classifier_validation_execution(raw)
    row = raw.execute("SELECT validation_run_id, classifier_model_id, execution_mode, actual_model_id FROM classifier_validation_runs").fetchone()
    assert row == ("legacy-run", "model", None, None)
    raw.close()


def test_injected_perfect_metrics_cannot_create_validated_bundle():
    run = _injected_run()
    assert run["execution_mode"] == "injected_classifier"
    assert run["topic_metrics"]["micro_f1"] == 1.0
    assert run["gate_status"] == "PASS_WITH_LIMITATIONS"
    persisted = persist_classifier_validation_run(run)
    assert persisted["execution_mode"] == "injected_classifier"
    with pytest.raises(ValueError, match="validated_bundle"):
        create_measurement_bundle(taxonomy_contract=baseline_classifier_taxonomy(), validation_run=persisted, measurement_status=VALIDATED)
    provisional = create_measurement_bundle(taxonomy_contract=baseline_classifier_taxonomy(), validation_run=persisted)
    assert provisional["measurement_status"] == PROVISIONAL


def test_one_topic_perfect_benchmark_exposes_zero_gold_taxonomy_topics():
    run = _injected_run()
    assert run["taxonomy_topic_n"] == 60
    assert run["gold_covered_topic_n"] == 1
    assert run["zero_gold_support_topic_n"] == 59
    assert run["zero_gold_support_topics"]
    assert run["topic_support_status"]["technical/bugs"] == "sufficient"
    assert run["gate_status"] != "PASS"


def test_authoritative_persisted_production_run_can_admit_validated_bundle(monkeypatch):
    run = _production_run(monkeypatch)
    assert run["gate_status"] == "PASS"
    assert run["execution_mode"] == "production_classifier"
    assert run["actual_model_id"] == "actual:production-model"
    persisted = persist_classifier_validation_run(run)
    tampered = {**persisted, "gate_status": "PASS", "execution_mode": "production_classifier", "actual_model_id": "caller-forged"}
    bundle = create_measurement_bundle(taxonomy_contract=baseline_classifier_taxonomy(), validation_run=tampered, measurement_status=VALIDATED)
    assert bundle["measurement_status"] == VALIDATED
    assert bundle["classifier_model_id"] == "actual:production-model"
    assert get_measurement_bundle(bundle["bundle_id"])["bundle_id"] == bundle["bundle_id"]


def test_activation_rechecks_authoritative_production_run(monkeypatch):
    run = _production_run(monkeypatch)
    persisted = persist_classifier_validation_run(run)
    bundle = create_measurement_bundle(taxonomy_contract=baseline_classifier_taxonomy(), validation_run=persisted, measurement_status=VALIDATED)
    with db.get_connection() as conn:
        conn.execute(text("UPDATE classifier_validation_runs SET execution_mode='injected_classifier' WHERE validation_run_id=:id"), {"id": persisted["validation_run_id"]})
    with pytest.raises(ValueError, match="referential_validation"):
        activate_measurement_bundle(bundle["bundle_id"], operator="test")


def test_retirement_and_active_bundle_lifecycle_remains_durable(monkeypatch):
    run = _production_run(monkeypatch)
    persisted = persist_classifier_validation_run(run)
    validated = create_measurement_bundle(taxonomy_contract=baseline_classifier_taxonomy(), validation_run=persisted, measurement_status=VALIDATED)
    activate_measurement_bundle(validated["bundle_id"], operator="test")
    assert get_active_measurement_bundle()["bundle_id"] == validated["bundle_id"]
    retired = retire_measurement_bundle(validated["bundle_id"], operator="test")
    assert retired["measurement_status"] == "RETIRED"
    assert get_active_measurement_bundle() is None


def test_baseline_provisional_bundle_changes_when_classifier_identity_changes(monkeypatch):
    import apps.api.senti_next.semantic_measurement_bundle as bundles

    current = {"classifier_provider": "provider-a", "classifier_model_id": "model-a", "classifier_prompt_version": "prompt-a", "classifier_schema_version": "schema-a"}
    monkeypatch.setattr(bundles, "classifier_identity", lambda contract: {**current, "taxonomy_snapshot_id": contract.snapshot_id, "taxonomy_version": contract.taxonomy_version, "taxonomy_fingerprint": contract.taxonomy_fingerprint, "classifier_taxonomy_contract_fingerprint": contract.fingerprint})
    first = bootstrap_baseline_measurement_bundle()
    current.update({"classifier_provider": "provider-b", "classifier_model_id": "model-b"})
    second = bootstrap_baseline_measurement_bundle()
    assert first["bundle_id"] != second["bundle_id"]
    assert first["classifier_model_id"] == "model-a"
    assert second["classifier_model_id"] == "model-b"
    assert len(list_measurement_bundles()) == 2
