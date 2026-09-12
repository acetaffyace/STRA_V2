from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from .common import canonical_json_hash, file_hash, read_jsonl
except ImportError:  # pragma: no cover
    from common import canonical_json_hash, file_hash, read_jsonl


def _set(value: Any) -> set[str]:
    return {str(item) for item in (value or []) if str(item).strip()}


def prf(gold: set[str], predicted: set[str]) -> dict[str, float | int]:
    tp = len(gold & predicted)
    fp = len(predicted - gold)
    fn = len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"support": len(gold), "predicted": len(predicted), "tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def multilabel_metrics(gold_records: list[dict], predictions: dict[str, dict], gold_field: str, pred_field: str, *, label_filter=None) -> dict[str, Any]:
    record_ids = {str(record["sample_id"]) for record in gold_records}
    scoped_predictions = {sample_id: item for sample_id, item in predictions.items() if sample_id in record_ids}
    keep = label_filter or (lambda label: True)
    gold_labels = lambda record: {label for label in _set((record.get("gold") or {}).get(gold_field)) if keep(label)}
    pred_labels = lambda sample_id: {label for label in _set(scoped_predictions.get(sample_id, {}).get(pred_field)) if keep(label)}
    labels = sorted({label for record in gold_records for label in gold_labels(record)} | {label for item in scoped_predictions.values() for label in _set(item.get(pred_field)) if keep(label)})
    per_label = {label: prf(
        {record["sample_id"] for record in gold_records if label in _set((record.get("gold") or {}).get(gold_field))},
        {sample_id for sample_id in record_ids if label in pred_labels(sample_id)},
    ) for label in labels}
    rows = [prf(gold_labels(record), pred_labels(str(record["sample_id"]))) for record in gold_records]
    macro = sum(float(item["f1"]) for item in per_label.values()) / len(per_label) if per_label else 0.0
    micro = prf({f"{record['sample_id']}::{label}" for record in gold_records for label in gold_labels(record)}, {f"{record['sample_id']}::{label}" for record in gold_records for label in pred_labels(str(record["sample_id"]))})
    return {"macro_f1": macro, "micro": micro, "per_label": per_label, "record_support": len(rows)}


def presence_metrics(gold_records: list[dict], predictions: dict[str, dict], field: str) -> dict[str, Any]:
    record_ids = {str(record["sample_id"]) for record in gold_records}
    gold_positive = {record["sample_id"] for record in gold_records if (record.get("gold") or {}).get(field) is True}
    predicted_positive = {sample_id for sample_id in record_ids if predictions.get(sample_id, {}).get(field) is True}
    score = prf(gold_positive, predicted_positive)
    score["record_support"] = len(gold_records)
    score["positive_support"] = len(gold_positive)
    return score


def no_actionable_topic_metrics(gold_records: list[dict], predictions: dict[str, dict]) -> dict[str, Any]:
    """Score the explicit no-substantive-topic contract separately."""
    eligible = 0
    correct = 0
    for record in gold_records:
        gold_labels = _set((record.get("gold") or {}).get("subcategories"))
        if any(not label.startswith("other/") for label in gold_labels):
            continue
        eligible += 1
        predicted = _set(predictions.get(str(record["sample_id"]), {}).get("subcategories"))
        correct += int(bool(predicted) and all(label.startswith("other/") for label in predicted))
    return {"eligible_support": eligible, "correct": correct, "accuracy": correct / eligible if eligible else None}


def sentiment_metrics(gold_records: list[dict], predictions: dict[str, dict]) -> dict[str, Any]:
    labels = ["positive", "negative", "mixed", "neutral", "uncertain"]
    confusion = {gold: {pred: 0 for pred in labels} for gold in labels}
    correct = 0
    total = 0
    for record in gold_records:
        gold = (record.get("gold") or {}).get("sentiment")
        pred = predictions.get(record["sample_id"], {}).get("sentiment")
        if gold not in confusion or pred not in labels:
            continue
        confusion[gold][pred] += 1
        correct += int(gold == pred)
        total += 1
    per_class = {}
    for label in labels:
        gold_ids = {record["sample_id"] for record in gold_records if (record.get("gold") or {}).get("sentiment") == label}
        pred_ids = {record["sample_id"] for record in gold_records if predictions.get(record["sample_id"], {}).get("sentiment") == label}
        per_class[label] = prf(gold_ids, pred_ids)
    if not total:
        return {
            "available": False,
            "unavailable_reason": "current production classifier contract does not emit sentiment",
            "accuracy": None,
            "support": 0,
            "macro_f1": None,
            "confusion_matrix": None,
            "per_class": None,
            "gold_class_support": {label: sum((record.get("gold") or {}).get("sentiment") == label for record in gold_records) for label in labels},
        }
    return {"available": True, "unavailable_reason": None, "accuracy": correct / total, "support": total, "macro_f1": sum(item["f1"] for item in per_class.values()) / len(per_class), "confusion_matrix": confusion, "per_class": per_class}


def evidence_metrics(gold_records: list[dict], predictions: dict[str, dict]) -> dict[str, Any]:
    exact_total = exact_pass = support_total = support_pass = 0
    for record in gold_records:
        source = record.get("source_review_text") or ""
        gold = record.get("gold") or {}
        gold_support = gold.get("evidence_support") or {}
        for span in predictions.get(record["sample_id"], {}).get("evidence_spans", []) or []:
            exact_total += 1
            exact_pass += int(str(span) in source)
            if span in gold_support:
                support_total += 1
                support_pass += int(bool(gold_support[span]))
    return {"quote_exactness": {"verified": exact_pass, "attempted": exact_total, "rate": exact_pass / exact_total if exact_total else None}, "evidence_support": {"supported": support_pass, "annotated": support_total, "rate": support_pass / support_total if support_total else None}}


def evaluate(gold_records: list[dict], prediction_records: list[dict]) -> dict[str, Any]:
    predictions = {}
    for item in prediction_records:
        if not item.get("sample_id"):
            continue
        prediction = dict(item.get("prediction", item))
        prediction.setdefault("issue_labels", prediction.get("issue_subcategories", []))
        prediction.setdefault("request_labels", prediction.get("request_subcategories", []))
        prediction.setdefault("issue_present", bool(prediction.get("issue_labels")))
        prediction.setdefault("request_present", bool(prediction.get("request_labels")))
        predictions[str(item["sample_id"])] = prediction
    labeled = [record for record in gold_records if record.get("annotation_status") == "labeled" and isinstance(record.get("gold"), dict)]
    groups: dict[str, list[dict]] = {"all": labeled, "core": [r for r in labeled if r.get("sampling_stratum") == "core"], "challenge": [r for r in labeled if r.get("sampling_stratum") == "challenge"]}
    languages = sorted({str(r.get("language") or "unknown") for r in labeled})
    for language in languages:
        groups[f"language:{language}"] = [r for r in labeled if str(r.get("language") or "unknown") == language]
    results: dict[str, Any] = {}
    for name, records in groups.items():
        # Taxonomy-gap records retain valid higher-level presence truth, but
        # are excluded from subcategory scoring because no production label
        # exists to predict.
        category_records = [record for record in records if not record.get("gold_source_taxonomy_gap")]
        results[name] = {
            "support": len(records),
            "sentiment": sentiment_metrics(records, predictions),
            "subcategories": multilabel_metrics(category_records, predictions, "subcategories", "subcategories"),
            "taxonomy_full_micro": multilabel_metrics(category_records, predictions, "subcategories", "subcategories")["micro"],
            "taxonomy_actionable_micro": multilabel_metrics(category_records, predictions, "subcategories", "subcategories", label_filter=lambda label: not label.startswith("other/"))["micro"],
            "no_actionable_topic_accuracy": no_actionable_topic_metrics(category_records, predictions),
            "issues": multilabel_metrics(category_records, predictions, "issue_labels", "issue_labels"),
            "requests": multilabel_metrics(category_records, predictions, "request_labels", "request_labels"),
            "issue_detection": presence_metrics(records, predictions, "issue_present"),
            "request_detection": presence_metrics(records, predictions, "request_present"),
            "evidence": evidence_metrics(records, predictions),
        }
    operational = [item for item in prediction_records if isinstance(item, dict)]
    usage_by_batch = {}
    for item in operational:
        usage = item.get("usage") or {}
        batch_key = item.get("batch_index", item.get("sample_id"))
        usage_by_batch.setdefault(batch_key, usage)
    results["operational"] = {
        "prediction_records": len(operational),
        "schema_invalid_rate": sum(bool(item.get("schema_invalid")) for item in operational) / len(operational) if operational else 0.0,
        "fallback_rate": sum(bool(item.get("fallback")) for item in operational) / len(operational) if operational else 0.0,
        "retry_rate": sum(int((usage or {}).get("retries") or 0) for usage in usage_by_batch.values()) / max(1, sum(int((usage or {}).get("api_requests") or 0) for usage in usage_by_batch.values())) if operational else 0.0,
        "latency_ms": sum(float(item.get("latency_ms") or 0) for item in operational) / len(operational) if operational else None,
        "input_tokens": sum(int((usage or {}).get("prompt_tokens") or 0) for usage in usage_by_batch.values()),
        "output_tokens": sum(int((usage or {}).get("completion_tokens") or 0) for usage in usage_by_batch.values()),
        "cached_input_tokens": sum(int((usage or {}).get("cached_tokens") or 0) for usage in usage_by_batch.values()),
        "api_requests": sum(int((usage or {}).get("api_requests") or 0) for usage in usage_by_batch.values()),
    }
    return {"labeled_support": len(labeled), "taxonomy_gap_count": sum(bool(record.get("gold_source_taxonomy_gap")) for record in labeled), "groups": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Score player-voice predictions against human annotations")
    parser.add_argument("--gold", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    gold = read_jsonl(args.gold)
    predictions = read_jsonl(args.predictions)
    report = evaluate(gold, predictions)
    report["dataset_hash"] = file_hash(args.gold)
    report["prediction_hash"] = file_hash(args.predictions)
    report["taxonomy_version"] = "sentinext-taxonomy-v1"
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"labeled_support": report["labeled_support"], "groups": list(report["groups"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
