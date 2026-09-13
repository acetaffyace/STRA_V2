"""Versioned admission policy for classifier validation runs.

The thresholds are deliberately provisional engineering gates.  They are
centralized here so later research governance can replace one policy version
without changing the scorer or route/UI code.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

CLASSIFIER_VALIDATION_POLICY_VERSION = "classifier-validation-policy-v1"


@dataclass(frozen=True)
class ClassifierValidationPolicy:
    version: str = CLASSIFIER_VALIDATION_POLICY_VERSION
    min_evaluation_coverage: float = 0.95
    hard_fail_coverage: float = 0.80
    min_micro_f1: float = 0.80
    min_macro_f1: float = 0.70
    min_primary_accuracy: float = 0.80
    min_issue_request_f1: float = 0.65
    sufficient_topic_support: int = 5
    limited_topic_support: int = 1
    max_invalid_predictions: int = 0
    max_zero_gold_support_false_positives: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _metric_failures(metrics: Mapping[str, Any], policy: ClassifierValidationPolicy, prefix: str) -> list[str]:
    failures = []
    if float(metrics.get("micro_f1", 0.0)) < policy.min_micro_f1:
        failures.append(f"{prefix}_micro_f1_below_threshold")
    if float(metrics.get("macro_f1", 0.0)) < policy.min_macro_f1:
        failures.append(f"{prefix}_macro_f1_below_threshold")
    return failures


def evaluate_validation_gate(
    report: Mapping[str, Any],
    *,
    policy: ClassifierValidationPolicy | None = None,
) -> dict[str, Any]:
    """Return PASS, PASS_WITH_LIMITATIONS, or FAIL for a scorer report."""
    policy = policy or ClassifierValidationPolicy()
    failures: list[str] = []
    limitations: list[str] = []
    coverage = float(report.get("evaluation_coverage", 0.0))
    if int(report.get("gold_item_n", 0)) <= 0:
        failures.append("empty_gold_dataset")
    if coverage < policy.hard_fail_coverage:
        failures.append("evaluation_coverage_below_hard_floor")
    elif coverage < policy.min_evaluation_coverage:
        limitations.append("evaluation_coverage_below_full_threshold")
    if int(report.get("invalid_prediction_n", 0)) > policy.max_invalid_predictions:
        failures.append("invalid_predictions_present")
    topic = report.get("topic_metrics") or {}
    failures.extend(_metric_failures(topic, policy, "topic"))
    if float(topic.get("primary_accuracy", 0.0)) < policy.min_primary_accuracy:
        failures.append("topic_primary_accuracy_below_threshold")
    if int(topic.get("zero_gold_support_fp_n", 0)) > policy.max_zero_gold_support_false_positives:
        failures.append("zero_gold_support_false_positive")

    taxonomy_topic_n = int(report.get("taxonomy_topic_n", topic.get("taxonomy_topic_n", 0)) or 0)
    gold_covered_topic_n = int(report.get("gold_covered_topic_n", topic.get("gold_covered_topic_n", 0)) or 0)
    zero_gold_support_topic_n = int(report.get("zero_gold_support_topic_n", topic.get("zero_gold_support_topic_n", 0)) or 0)
    audited_support_status = report.get("topic_support_status") or topic.get("topic_support_status") or {}
    support_status: dict[str, str] = {str(key): str(value) for key, value in audited_support_status.items()}
    if taxonomy_topic_n:
        if len(support_status) != taxonomy_topic_n:
            failures.append("taxonomy_support_audit_incomplete")
        if gold_covered_topic_n < taxonomy_topic_n:
            limitations.append("gold_topic_coverage_incomplete")
        if zero_gold_support_topic_n:
            limitations.append("zero_gold_support_topics_present")

    for key, value in (topic.get("per_topic") or {}).items():
        if key in support_status:
            continue
        support = int(value.get("gold_support", 0))
        if support >= policy.sufficient_topic_support:
            support_status[str(key)] = "sufficient"
        elif support >= policy.limited_topic_support:
            support_status[str(key)] = "limited"
            limitations.append(f"rare_topic_support:{key}")
        else:
            support_status[str(key)] = "insufficient"
            limitations.append(f"insufficient_topic_support:{key}")

    insufficient_topics = sorted(key for key, status in support_status.items() if status == "insufficient")
    limited_topics = sorted(key for key, status in support_status.items() if status == "limited")
    if insufficient_topics:
        limitations.append("insufficient_topic_support_present")
    if limited_topics:
        limitations.append("limited_topic_support_present")

    for field_name, label in (("issue_metrics", "issue"), ("request_metrics", "request")):
        metrics = report.get(field_name)
        if metrics is None:
            limitations.append(f"{label}_gold_labels_unavailable")
            continue
        if float(metrics.get("micro_f1", 0.0)) < policy.min_issue_request_f1:
            failures.append(f"{label}_micro_f1_below_threshold")
        if int(metrics.get("invalid_prediction_n", 0)) > policy.max_invalid_predictions:
            failures.append(f"{label}_invalid_predictions_present")

    if failures:
        status = "FAIL"
    elif limitations:
        status = "PASS_WITH_LIMITATIONS"
    else:
        status = "PASS"
    return {
        "policy_version": policy.version,
        "status": status,
        "failures": sorted(set(failures)),
        "limitations": sorted(set(limitations)),
        "topic_support_status": support_status,
        "policy": policy.to_dict(),
    }


__all__ = [
    "CLASSIFIER_VALIDATION_POLICY_VERSION",
    "ClassifierValidationPolicy",
    "evaluate_validation_gate",
]
