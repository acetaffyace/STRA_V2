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
    assert report["schema_version"] == "classifier-validation-report-v2"
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


def test_zero_gold_support_false_positive_counts_in_micro_but_not_macro():
    report = evaluate_classifier_fixture(
        [{"review_id": "a", "gold_labels": ["technical/bugs"]}],
        {"a": {"subcategories": ["technical/bugs", "other/general"]}},
    )
    metrics = report["topic_metrics"]
    assert metrics["micro_precision"] == 0.5
    assert metrics["micro_recall"] == 1.0
    assert metrics["micro_f1"] == pytest.approx(2 / 3)
    assert metrics["macro_topic_n"] == 1
    assert metrics["zero_gold_support_fp_n"] == 1
    assert metrics["zero_gold_support_prediction_warning"] is True


def test_wrong_legal_topic_has_zero_micro_scores_and_exact_match_is_strict():
    report = evaluate_classifier_fixture(
        [{"review_id": "a", "gold_primary_label": "technical/bugs", "gold_labels": ["technical/bugs"]}],
        {"a": {"subcategories": ["technical/performance"]}},
    )
    metrics = report["topic_metrics"]
    assert metrics["micro_precision"] == 0.0
    assert metrics["micro_recall"] == 0.0
    assert metrics["micro_f1"] == 0.0
    assert metrics["exact_match_rate"] == 0.0


def test_primary_accuracy_can_be_correct_when_exact_match_is_not():
    report = evaluate_classifier_fixture(
        [{"review_id": "a", "gold_primary_label": "technical/bugs", "gold_labels": ["technical/bugs"]}],
        {"a": {"subcategories": ["technical/bugs", "other/general"]}},
    )
    assert report["topic_metrics"]["primary_accuracy"] == 1.0
    assert report["topic_metrics"]["exact_match_rate"] == 0.0


def test_issue_and_request_zero_support_false_positives_count_in_micro():
    gold = [{
        "review_id": "a",
        "gold_labels": ["technical/bugs"],
        "gold_issue_labels": ["technical/bugs"],
        "gold_request_labels": ["technical/bugs"],
    }]
    predictions = {"a": {
        "subcategories": ["technical/bugs"],
        "issue_subcategories": ["technical/bugs", "other/general"],
        "request_subcategories": ["technical/bugs", "other/general"],
    }}
    report = evaluate_classifier_fixture(gold, predictions)
    assert report["issue_metrics"]["micro_precision"] == 0.5
    assert report["request_metrics"]["micro_precision"] == 0.5


def test_invalid_issue_and_request_fields_are_scored_as_empty_predictions():
    gold = [{
        "review_id": "a",
        "gold_labels": ["technical/bugs"],
        "gold_issue_labels": ["technical/bugs"],
        "gold_request_labels": ["technical/bugs"],
    }]
    predictions = {"a": {
        "subcategories": ["technical/bugs"],
        "issue_subcategories": ["technical/bugs", "not/a-topic"],
        "request_subcategories": ["technical/bugs", "not/a-topic"],
    }}
    report = evaluate_classifier_fixture(gold, predictions)
    assert report["issue_metrics"]["invalid_prediction_n"] == 1
    assert report["request_metrics"]["invalid_prediction_n"] == 1
    assert report["issue_metrics"]["micro_recall"] == 0.0
    assert report["request_metrics"]["micro_recall"] == 0.0
    assert report["invalid_prediction_n"] == 2


def test_duplicate_ids_fail_and_unexpected_ids_are_reported():
    with pytest.raises(ValueError, match="duplicate_gold_review_id"):
        evaluate_classifier_fixture(
            [
                {"review_id": "a", "gold_labels": ["technical/bugs"]},
                {"review_id": "a", "gold_labels": ["technical/bugs"]},
            ],
            [],
        )
    with pytest.raises(ValueError, match="duplicate_prediction_review_id"):
        evaluate_classifier_fixture(
            [{"review_id": "a", "gold_labels": ["technical/bugs"]}],
            [
                {"review_id": "a", "subcategories": ["technical/bugs"]},
                {"review_id": "a", "subcategories": ["technical/bugs"]},
            ],
        )
    report = evaluate_classifier_fixture(
        [{"review_id": "a", "gold_labels": ["technical/bugs"]}],
        {
            "a": {"subcategories": ["technical/bugs"]},
            "unexpected": {"subcategories": ["other/general"]},
        },
    )
    assert report["unexpected_prediction_n"] == 1
    assert report["unexpected_prediction_ids"] == ["unexpected"]


def test_missing_prediction_reports_coverage_and_scores_missing_as_empty():
    report = evaluate_classifier_fixture(
        [
            {"review_id": "a", "gold_labels": ["technical/bugs"]},
            {"review_id": "b", "gold_labels": ["technical/performance"]},
        ],
        {"a": {"subcategories": ["technical/bugs"]}},
    )
    assert report["matched_prediction_n"] == 1
    assert report["missing_prediction_n"] == 1
    assert report["evaluation_coverage"] == 0.5
    assert report["topic_metrics"]["micro_recall"] == 0.5


def test_empty_benchmark_is_json_safe_and_has_zero_coverage():
    report = evaluate_classifier_fixture([], {})
    assert report["matched_prediction_n"] == 0
    assert report["evaluation_coverage"] == 0.0
    assert report["topic_metrics"]["micro_f1"] == 0.0
    json.dumps(report, sort_keys=True, allow_nan=False)
