"""Create bounded, non-mutating baseline error-analysis examples."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import read_jsonl


def _labels(item: dict, field: str) -> set[str]:
    return set((item.get("prediction") or {}).get(field) or [])


def _pred(item: dict, field: str) -> bool:
    prediction = item.get("prediction") or {}
    if field == "issue_present":
        return bool(prediction.get("issue_subcategories") or prediction.get("issue_labels"))
    return bool(prediction.get("request_subcategories") or prediction.get("request_labels"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    gold = {r["sample_id"]: r for r in read_jsonl(args.gold)}
    predictions = {r["sample_id"]: r for r in read_jsonl(args.predictions)}
    families: dict[str, list[dict]] = {name: [] for name in (
        "issue_false_positive", "issue_false_negative", "request_false_positive",
        "request_false_negative", "category_boundary_confusion", "multilabel_omission",
        "challenge_failure", "long_or_truncated", "taxonomy_gap",
    )}
    for sample_id, record in gold.items():
        item = predictions.get(sample_id, {})
        gold_block = record.get("gold") or {}
        pred_block = item.get("prediction") or {}
        def example(error_type: str, details: dict) -> dict:
            return {"sample_id": sample_id, "source_review": record.get("source_review_text", ""), "gold": gold_block, "predicted": pred_block, "sampling_stratum": record.get("sampling_stratum"), "error_type": error_type, **details}
        if bool(gold_block.get("issue_present")) != _pred(item, "issue_present"):
            key = "issue_false_positive" if _pred(item, "issue_present") else "issue_false_negative"
            if len(families[key]) < 8: families[key].append(example(key, {}))
        if bool(gold_block.get("request_present")) != _pred(item, "request_present"):
            key = "request_false_positive" if _pred(item, "request_present") else "request_false_negative"
            if len(families[key]) < 8: families[key].append(example(key, {}))
        gold_labels = set(gold_block.get("subcategories") or [])
        pred_labels = set(pred_block.get("subcategories") or [])
        if gold_labels - pred_labels and len(families["multilabel_omission"]) < 8:
            families["multilabel_omission"].append(example("multilabel_omission", {"omitted_labels": sorted(gold_labels - pred_labels)}))
        if gold_labels and pred_labels and {x.split("/", 1)[0] for x in gold_labels} != {x.split("/", 1)[0] for x in pred_labels} and len(families["category_boundary_confusion"]) < 8:
            families["category_boundary_confusion"].append(example("category_boundary_confusion", {}))
        if record.get("sampling_stratum") == "challenge" and (gold_labels != pred_labels or bool(gold_block.get("issue_present")) != _pred(item, "issue_present")) and len(families["challenge_failure"]) < 8:
            families["challenge_failure"].append(example("challenge_failure", {}))
        if len(record.get("source_review_text", "")) > 3000 and len(families["long_or_truncated"]) < 8:
            families["long_or_truncated"].append(example("long_or_truncated", {"source_chars": len(record.get("source_review_text", ""))}))
        if record.get("gold_source_taxonomy_gap") and len(families["taxonomy_gap"]) < 8:
            families["taxonomy_gap"].append(example("taxonomy_gap", {}))
    result = {"sentiment": {"status": "not_evaluable", "reason": "production classifier does not emit sentiment"}, "families": families}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"families": {key: len(value) for key, value in families.items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
