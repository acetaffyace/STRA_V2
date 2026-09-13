from __future__ import annotations

import json

import pytest

from apps.api.senti_next.classifier_validation import evaluate_classifier_fixture


def test_perfect_fixture_reports_exact_topic_and_primary_metrics():
    gold = [
        {"review_id": "a", "gold_primary_label": "technical/performance", "gold_labels": ["technical/performance"]},
        {"review_id": "b", "gold_primary_label": "technical/bugs", "gold_labels": ["technical/bugs", "technical/performance"]},
    ]
    predictions = {
        "a": {"subcategories": ["technical/performance"]},
        "b": {"subcategories": ["technical/bugs", "technical/performance"]},
    }
    report = evaluate_classifier_fixture(gold, predictions)
    assert report["schema_version"] == "classifier-validation-report-v1"
    assert report["topic_metrics"]["micro_f1"] == 1.0
    assert report["topic_metrics"]["exact_match_rate"] == 1.0
    assert report["topic_metrics"]["primary_accuracy"] == 1.0
    assert report["topic_metrics"]["macro_topic_n"] == 2
    assert "not_population_inference" in report["limitations"]
    json.dumps(report, sort_keys=True, allow_nan=False)


def test_partial_recall_and_issue_request_metrics_are_separate():
    gold = [{
        "review_id": "a",
        "gold_primary_label": "technical/bugs",
        "gold_labels": ["technical/bugs", "technical/performance"],
        "gold_issue_labels": ["technical/bugs"],
        "gold_request_labels": ["technical/performance"],
    }]
    predictions = [{
        "review_id": "a",
        "subcategories": ["technical/bugs"],
        "issue_subcategories": ["technical/bugs"],
        "request_subcategories": [],
    }]
    report = evaluate_classifier_fixture(gold, predictions)
    assert report["topic_metrics"]["micro_recall"] == 0.5
    assert report["issue_metrics"]["micro_f1"] == 1.0
    assert report["request_metrics"]["micro_recall"] == 0.0


def test_invalid_gold_fails_and_invalid_prediction_is_recorded():
    with pytest.raises(ValueError, match="invalid_gold_label"):
        evaluate_classifier_fixture(
            [{"review_id": "a", "gold_labels": ["not/a-topic"]}],
            {"a": {"subcategories": []}},
        )
    report = evaluate_classifier_fixture(
        [{"review_id": "a", "gold_labels": ["other/general"]}],
        {"a": {"subcategories": ["other/general", "not/a-topic"]}},
    )
    assert report["invalid_prediction_n"] == 1
    assert report["valid_prediction_n"] == 0


def test_missing_prediction_is_not_a_fake_empty_prediction():
    report = evaluate_classifier_fixture(
        [{"review_id": "a", "gold_labels": ["other/general"]}],
        {},
    )
    assert report["missing_prediction_n"] == 1
    assert report["valid_prediction_n"] == 0
