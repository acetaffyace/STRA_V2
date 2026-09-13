"""Deterministic, provider-free validation for classifier payloads."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .classifier_taxonomy import ClassifierTaxonomyContract, baseline_classifier_taxonomy

VALIDATION_REPORT_SCHEMA_VERSION = "classifier-validation-report-v2"
FIXED_LIMITATIONS = [
    "synthetic_or_offline_validation_only",
    "not_real_model_validation",
    "not_population_inference",
    "not_selection_bias_correction",
    "gold_benchmark_coverage_limits_per_topic_validation",
]


def _as_records(value: Any, *, prediction: bool = False) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        if prediction and all(isinstance(v, Mapping) for v in value.values()):
            return [{"review_id": str(key), **dict(payload)} for key, payload in value.items()]
        return [dict(value)]
    return [dict(item) for item in (value or []) if isinstance(item, Mapping)]


def _labels(item: Mapping[str, Any], key: str, *, fallback: str | None = None) -> list[str]:
    value = item.get(key)
    if value is None and fallback is not None:
        value = item.get(fallback)
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(entry) for entry in value if str(entry).strip()]
    return []


def _score_multilabel(
    gold: Sequence[set[str]],
    predicted: Sequence[set[str]],
    topics: Sequence[str],
    *,
    sufficient_support: int = 5,
    limited_support: int = 1,
) -> dict[str, Any]:
    per_topic: dict[str, dict[str, Any]] = {}
    total_tp = total_fp = total_fn = 0
    zero_gold_support_fp_n = 0
    macro_rows = []
    topic_support_status: dict[str, str] = {}
    for topic in topics:
        tp = sum(topic in g and topic in p for g, p in zip(gold, predicted))
        fp = sum(topic not in g and topic in p for g, p in zip(gold, predicted))
        fn = sum(topic in g and topic not in p for g, p in zip(gold, predicted))
        support = sum(topic in g for g in gold)
        topic_support_status[topic] = (
            "sufficient" if support >= sufficient_support
            else "limited" if support >= limited_support
            else "insufficient"
        )
        # Micro aggregation covers every active topic, including topics with
        # no positive gold examples.  Their false positives still matter for
        # precision even though they cannot contribute to macro recall/F1.
        total_tp += tp
        total_fp += fp
        total_fn += fn
        if support <= 0:
            zero_gold_support_fp_n += fp
            continue
        predicted_n = sum(topic in p for p in predicted)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_topic[topic] = {
            "gold_support": support,
            "predicted_n": predicted_n,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
        macro_rows.append((precision, recall, f1))

    micro_precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0
    micro_recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if micro_precision + micro_recall else 0.0
    )
    exact_match = sum(g == p for g, p in zip(gold, predicted)) / len(gold) if gold else 0.0
    return {
        "micro_precision": micro_precision,
        "micro_recall": micro_recall,
        "micro_f1": micro_f1,
        "macro_precision": sum(row[0] for row in macro_rows) / len(macro_rows) if macro_rows else 0.0,
        "macro_recall": sum(row[1] for row in macro_rows) / len(macro_rows) if macro_rows else 0.0,
        "macro_f1": sum(row[2] for row in macro_rows) / len(macro_rows) if macro_rows else 0.0,
        "macro_topic_n": len(macro_rows),
        "exact_match_rate": exact_match,
        "per_topic": per_topic,
        "taxonomy_topic_n": len(topics),
        "gold_covered_topic_n": sum(status != "insufficient" for status in topic_support_status.values()),
        "gold_topic_coverage_rate": (
            sum(status != "insufficient" for status in topic_support_status.values()) / len(topics)
            if topics else 0.0
        ),
        "zero_gold_support_topic_n": sum(status == "insufficient" for status in topic_support_status.values()),
        "zero_gold_support_topics": sorted(topic for topic, status in topic_support_status.items() if status == "insufficient"),
        "topic_support_status": topic_support_status,
        "small_gold_support_warning": any(row["gold_support"] < 5 for row in per_topic.values()),
        "zero_gold_support_fp_n": zero_gold_support_fp_n,
        "zero_gold_support_prediction_warning": zero_gold_support_fp_n > 0,
    }


def _primary_accuracy(gold: Sequence[str | None], predicted: Sequence[Sequence[str]]) -> float:
    if not gold:
        return 0.0
    return sum(bool(g) and bool(p) and g == p[0] for g, p in zip(gold, predicted)) / len(gold)


def evaluate_classifier_fixture(
    gold_items: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    predictions: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    taxonomy_contract: ClassifierTaxonomyContract | None = None,
    topic_support_sufficient: int = 5,
    topic_support_limited: int = 1,
) -> dict[str, Any]:
    """Evaluate topic/issue/request agreement without calling a provider."""
    contract = taxonomy_contract or baseline_classifier_taxonomy()
    contract.validate()
    allowed = set(contract.active_topic_keys)
    gold = _as_records(gold_items)
    prediction_records = _as_records(predictions, prediction=True)

    gold_ids = [str(item.get("review_id")) for item in gold if item.get("review_id") is not None]
    if len(gold_ids) != len(set(gold_ids)):
        raise ValueError("duplicate_gold_review_id")
    if not isinstance(predictions, Mapping):
        prediction_ids = [str(item.get("review_id")) for item in prediction_records if item.get("review_id") is not None]
        if len(prediction_ids) != len(set(prediction_ids)):
            raise ValueError("duplicate_prediction_review_id")
    prediction_by_id = {str(item.get("review_id")): item for item in prediction_records}
    gold_id_set = set(gold_ids)
    unexpected_prediction_ids = sorted(
        {review_id for review_id in prediction_by_id if review_id not in gold_id_set}
    )

    gold_labels: list[set[str]] = []
    gold_primary: list[str | None] = []
    for item in gold:
        labels = _labels(item, "gold_labels", fallback="gold_primary_label")
        issue_labels = _labels(item, "gold_issue_labels")
        request_labels = _labels(item, "gold_request_labels")
        primary = item.get("gold_primary_label")
        all_gold_labels = set(labels) | set(issue_labels) | set(request_labels)
        if primary:
            all_gold_labels.add(str(primary))
        invalid = sorted(all_gold_labels - allowed)
        if invalid:
            raise ValueError("invalid_gold_label")
        gold_labels.append(set(labels))
        gold_primary.append(str(primary) if primary else (labels[0] if labels else None))

    predicted_labels: list[set[str]] = []
    predicted_ordered: list[list[str]] = []
    invalid_prediction_n = 0
    valid_prediction_n = 0
    missing_prediction_n = 0
    for item, gold_item in zip(gold_labels, gold):
        prediction = prediction_by_id.get(str(gold_item.get("review_id")))
        if prediction is None:
            missing_prediction_n += 1
            predicted_ordered.append([])
            predicted_labels.append(set())
            continue
        raw = _labels(prediction, "subcategories")
        invalid_labels = [label for label in raw if label not in allowed]
        invalid_prediction_n += len(invalid_labels)
        valid = [label for label in raw if label in allowed]
        if invalid_labels:
            # An invalid output is not allowed to become a successful partial
            # prediction merely because some labels were valid.
            predicted_ordered.append([])
            predicted_labels.append(set())
        else:
            valid_prediction_n += 1
            predicted_ordered.append(valid)
            predicted_labels.append(set(valid))

    topic_metrics = _score_multilabel(
        gold_labels,
        predicted_labels,
        contract.active_topic_keys,
        sufficient_support=topic_support_sufficient,
        limited_support=topic_support_limited,
    )
    issue_available = any("gold_issue_labels" in item for item in gold)
    request_available = any("gold_request_labels" in item for item in gold)

    def _optional_metrics(gold_key: str, pred_key: str) -> dict[str, Any] | None:
        nonlocal invalid_prediction_n
        if not any(gold_key in item for item in gold):
            return None
        g = [_labels(item, gold_key) for item in gold]
        p = [_labels(prediction_by_id.get(str(item.get("review_id"))) or {}, pred_key) for item in gold]
        invalid = sum(label not in allowed for labels in p for label in labels)
        invalid_prediction_n += invalid
        # An invalid field is scored as an empty prediction.  Keeping valid
        # labels from the same malformed field would make the benchmark
        # silently optimistic.
        p_clean = [
            [] if any(label not in allowed for label in labels) else labels
            for labels in p
        ]
        result = _score_multilabel(
            [set(row) for row in g],
            [set(row) for row in p_clean],
            contract.active_topic_keys,
            sufficient_support=topic_support_sufficient,
            limited_support=topic_support_limited,
        )
        result["invalid_prediction_n"] = invalid
        return result

    matched_prediction_n = len(gold) - missing_prediction_n
    evaluation_coverage = matched_prediction_n / len(gold) if gold else 0.0
    issue_metrics = _optional_metrics("gold_issue_labels", "issue_subcategories") if issue_available else None
    request_metrics = _optional_metrics("gold_request_labels", "request_subcategories") if request_available else None

    report = {
        "schema_version": VALIDATION_REPORT_SCHEMA_VERSION,
        "taxonomy_snapshot_id": contract.snapshot_id,
        "taxonomy_version": contract.taxonomy_version,
        "taxonomy_fingerprint": contract.taxonomy_fingerprint,
        "gold_item_n": len(gold),
        "prediction_item_n": len(prediction_records),
        "matched_prediction_n": matched_prediction_n,
        "valid_prediction_n": valid_prediction_n,
        "missing_prediction_n": missing_prediction_n,
        "unexpected_prediction_n": len(unexpected_prediction_ids),
        "unexpected_prediction_ids": unexpected_prediction_ids[:50],
        "invalid_prediction_n": invalid_prediction_n,
        "evaluation_coverage": evaluation_coverage,
        "taxonomy_topic_n": topic_metrics["taxonomy_topic_n"],
        "gold_covered_topic_n": topic_metrics["gold_covered_topic_n"],
        "gold_topic_coverage_rate": topic_metrics["gold_topic_coverage_rate"],
        "zero_gold_support_topic_n": topic_metrics["zero_gold_support_topic_n"],
        "zero_gold_support_topics": topic_metrics["zero_gold_support_topics"],
        "topic_support_status": topic_metrics["topic_support_status"],
        "topic_metrics": {
            **topic_metrics,
            "primary_accuracy": _primary_accuracy(gold_primary, predicted_ordered),
        },
        "issue_metrics": issue_metrics,
        "request_metrics": request_metrics,
        "limitations": list(FIXED_LIMITATIONS),
    }
    return report


def validate_classifier_fixture(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Compatibility alias for callers that prefer a validate verb."""
    return evaluate_classifier_fixture(*args, **kwargs)


__all__ = [
    "FIXED_LIMITATIONS",
    "VALIDATION_REPORT_SCHEMA_VERSION",
    "evaluate_classifier_fixture",
    "validate_classifier_fixture",
]
