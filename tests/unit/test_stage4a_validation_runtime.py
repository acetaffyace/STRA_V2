from __future__ import annotations

import json

import pytest

from apps.api.senti_next.classifier_taxonomy import baseline_classifier_taxonomy
from apps.api.senti_next.classifier_validation_policy import ClassifierValidationPolicy, evaluate_validation_gate
from apps.api.senti_next.classifier_validation_runtime import run_classifier_validation, validation_dataset_identity


def _gold():
    return [
        {"review_id": "a", "review_text": "slow", "language": "english", "gold_primary_label": "technical/performance", "gold_labels": ["technical/performance"]},
        {"review_id": "b", "review_text": "crash", "language": "english", "gold_primary_label": "technical/bugs", "gold_labels": ["technical/bugs"]},
    ]


def test_runtime_passes_exact_taxonomy_contract_to_production_compatible_path():
    seen = {}
    contract = baseline_classifier_taxonomy()

    def fake_classifier(items, *, taxonomy_contract):
        seen["contract"] = taxonomy_contract
        return {item["review_id"]: {"subcategories": item["gold_labels"]} for item in items}

    run = run_classifier_validation(
        _gold(), taxonomy_contract=contract, classifier=fake_classifier,
        provider="fake", model_id="fake:test-model", prompt_version="prompt-test", schema_version="schema-test",
    )
    assert seen["contract"] is contract
    assert run["taxonomy_snapshot_id"] == contract.snapshot_id
    assert run["classifier_taxonomy_contract_fingerprint"] == contract.fingerprint
    assert run["gate_status"] == "PASS_WITH_LIMITATIONS"
    assert "not_real_model_validation" not in run["limitations"]
    assert run["execution_mode"] == "injected_classifier"
    json.dumps(run, sort_keys=True, allow_nan=False)


def test_validation_dataset_fingerprint_is_stable_and_identity_changes_with_inputs():
    first = validation_dataset_identity(_gold(), validation_dataset_id="gold-v1")
    second = validation_dataset_identity(list(reversed(_gold())), validation_dataset_id="gold-v1")
    changed = validation_dataset_identity([{**_gold()[0], "review_text": "changed"}, _gold()[1]], validation_dataset_id="gold-v1")
    assert first["validation_dataset_fingerprint"] == second["validation_dataset_fingerprint"]
    assert first["validation_dataset_fingerprint"] != changed["validation_dataset_fingerprint"]
    assert first["validation_dataset_id"] == "gold-v1"


def test_gate_boundaries_cover_pass_limited_fail_invalid_and_rare_support():
    policy = ClassifierValidationPolicy(min_evaluation_coverage=1.0, min_micro_f1=0.8, min_macro_f1=0.8, min_primary_accuracy=0.8)
    base = {
        "gold_item_n": 10, "evaluation_coverage": 1.0, "invalid_prediction_n": 0,
        "topic_metrics": {"micro_f1": 1.0, "macro_f1": 1.0, "primary_accuracy": 1.0, "zero_gold_support_fp_n": 0, "per_topic": {"technical/bugs": {"gold_support": 5}}},
        "issue_metrics": {"micro_f1": 1.0, "invalid_prediction_n": 0},
        "request_metrics": {"micro_f1": 1.0, "invalid_prediction_n": 0},
    }
    assert evaluate_validation_gate(base, policy=policy)["status"] == "PASS"
    limited = {**base, "evaluation_coverage": 0.95, "topic_metrics": {**base["topic_metrics"], "per_topic": {"technical/bugs": {"gold_support": 1}}}}
    assert evaluate_validation_gate(limited, policy=policy)["status"] == "PASS_WITH_LIMITATIONS"
    failed = {**base, "invalid_prediction_n": 1}
    assert evaluate_validation_gate(failed, policy=policy)["status"] == "FAIL"
    zero_support_fp = {**base, "topic_metrics": {**base["topic_metrics"], "zero_gold_support_fp_n": 1}}
    assert evaluate_validation_gate(zero_support_fp, policy=policy)["status"] == "FAIL"

