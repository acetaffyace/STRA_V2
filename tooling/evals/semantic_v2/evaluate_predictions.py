from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from .validate_assets import EXPECTED_TAXONOMY_VERSION, PRIMARY_LANGUAGE_ALIASES


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: record must be an object")
            records.append(value)
    return records


def _topic_ids(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _prediction_assignments(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    assignments = record.get("assignments")
    if assignments is None and record.get("core_topic_id"):
        assignments = [record]
    if not isinstance(assignments, list):
        return []
    return [item for item in assignments if isinstance(item, Mapping)]


def _primary_prediction(record: Mapping[str, Any]) -> tuple[str | None, str | None, Mapping[str, Any] | None]:
    assignments = _prediction_assignments(record)
    for assignment in assignments:
        topic = str(assignment.get("core_topic_id") or "").strip()
        if topic:
            return topic, str(assignment.get("decision_band") or "").upper() or None, assignment
    return None, None, None


def _f1(tp: int, fp: int, fn: int) -> dict[str, Any]:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def _evaluate_slice(records: list[tuple[dict[str, Any], dict[str, Any]]], minimum_topic_support: int) -> dict[str, Any]:
    supports = Counter()
    predicted = Counter()
    true_positive = Counter()
    unresolved = 0
    high_total = 0
    high_correct = 0
    llm_escalations = 0
    eligible = 0
    resolved = 0
    confusion = Counter()
    novel_total = 0
    novel_detected = 0
    for gold, prediction in records:
        if not gold.get("semantic_eligible", True):
            continue
        eligible += 1
        gold_topics = _topic_ids((gold.get("gold") or {}).get("core_topic_ids"))
        gold_primary = next(iter(sorted(gold_topics)), None)
        for topic in gold_topics:
            supports[topic] += 1
        topic, band, assignment = _primary_prediction(prediction)
        if topic:
            resolved += 1
            predicted[topic] += 1
            if topic in gold_topics:
                true_positive[topic] += 1
            if assignment and str(assignment.get("assignment_source") or "").lower().startswith("llm"):
                llm_escalations += 1
        else:
            unresolved += 1
        if band == "HIGH":
            high_total += 1
            if topic in gold_topics:
                high_correct += 1
        if gold.get("novel_topic_seed"):
            novel_total += 1
            if prediction.get("novel_topic_detected") or prediction.get("emerging_topic_candidate_id"):
                novel_detected += 1
        if gold_primary is not None and topic is not None:
            confusion[(gold_primary, topic)] += 1

    supported = sorted(topic for topic, count in supports.items() if count >= minimum_topic_support)
    aggregate = _f1(
        sum(true_positive[topic] for topic in supports),
        sum(predicted[topic] for topic in supports) - sum(true_positive[topic] for topic in supports),
        sum(supports.values()) - sum(true_positive[topic] for topic in supports),
    )
    per_topic = {
        topic: _f1(true_positive[topic], predicted[topic] - true_positive[topic], supports[topic] - true_positive[topic])
        for topic in supported
    }
    f1_values = [value["f1"] for value in per_topic.values() if value["f1"] is not None]
    matrix = [
        {"gold": gold_topic, "predicted": predicted_topic, "count": count}
        for (gold_topic, predicted_topic), count in sorted(confusion.items())
    ]
    return {
        "eligible_support": eligible,
        "resolved_support": resolved,
        "unresolved_rate": unresolved / eligible if eligible else None,
        "semantic_coverage": resolved / eligible if eligible else None,
        "llm_escalation_rate": llm_escalations / eligible if eligible else None,
        "decision_band": {
            "high_support": high_total,
            "high_precision": high_correct / high_total if high_total else None,
            "high_error_rate": (high_total - high_correct) / high_total if high_total else None,
            "coverage": {band: sum(1 for _, prediction in records if _primary_prediction(prediction)[1] == band) / eligible if eligible else None for band in ("HIGH", "MEDIUM", "LOW")},
        },
        "multilabel_micro": aggregate,
        "supported_topic_count": len(supported),
        "supported_topics": per_topic,
        "macro_f1": sum(f1_values) / len(f1_values) if f1_values else None,
        "confusion_matrix": matrix,
        "top_confusions": sorted(matrix, key=lambda item: (-item["count"], item["gold"], item["predicted"]))[:20],
        "seeded_novel_topic_discovery": {"support": novel_total, "recall": novel_detected / novel_total if novel_total else None},
    }


def evaluate_predictions(
    gold_records: Iterable[Mapping[str, Any]],
    prediction_records: Iterable[Mapping[str, Any]],
    *,
    minimum_topic_support: int = 10,
    dataset_version: str | None = None,
    semantic_config_hash: str | None = None,
    evaluation_code_commit: str | None = None,
    runtime_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    gold = [dict(record) for record in gold_records]
    predictions = [dict(record) for record in prediction_records]
    if any(record.get("taxonomy_version") != EXPECTED_TAXONOMY_VERSION for record in gold):
        raise ValueError(f"gold records must use {EXPECTED_TAXONOMY_VERSION}")
    gold_by_id = {str(record.get("sample_id")): record for record in gold}
    prediction_by_id: dict[str, dict[str, Any]] = {}
    for record in predictions:
        sample_id = str(record.get("sample_id") or "")
        if not sample_id or sample_id in prediction_by_id:
            raise ValueError("prediction sample_id must be unique and non-empty")
        prediction_by_id[sample_id] = record
    missing = sorted(set(gold_by_id) - set(prediction_by_id))
    extra = sorted(set(prediction_by_id) - set(gold_by_id))
    if missing or extra:
        raise ValueError(f"gold/prediction sample_id mismatch: missing={missing[:3]} extra={extra[:3]}")
    paired = [(record, prediction_by_id[sample_id]) for sample_id, record in sorted(gold_by_id.items())]
    all_result = _evaluate_slice(paired, minimum_topic_support)
    by_language: dict[str, Any] = {}
    for language in sorted({str(record.get("language") or "") for record in gold}):
        canonical = PRIMARY_LANGUAGE_ALIASES.get(language.lower(), language.lower())
        by_language[canonical] = _evaluate_slice(
            [(record, prediction) for record, prediction in paired if PRIMARY_LANGUAGE_ALIASES.get(str(record.get("language") or "").lower(), str(record.get("language") or "").lower()) == canonical],
            minimum_topic_support,
        )
    return {
        "schema_version": "semantic-v2-evaluation-report-v1",
        "taxonomy_version": EXPECTED_TAXONOMY_VERSION,
        "dataset_version": dataset_version,
        "semantic_config_hash": semantic_config_hash,
        "evaluation_code_commit": evaluation_code_commit,
        "minimum_topic_support": minimum_topic_support,
        "all": all_result,
        "language_slices": by_language,
        "runtime_profile": dict(runtime_profile or {}),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Semantic Engine V2 predictions")
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-version")
    parser.add_argument("--semantic-config-hash")
    parser.add_argument("--evaluation-code-commit")
    parser.add_argument("--minimum-topic-support", type=int, default=10)
    args = parser.parse_args(argv)
    report = evaluate_predictions(
        _read_jsonl(args.gold),
        _read_jsonl(args.predictions),
        minimum_topic_support=args.minimum_topic_support,
        dataset_version=args.dataset_version,
        semantic_config_hash=args.semantic_config_hash,
        evaluation_code_commit=args.evaluation_code_commit,
    )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "schema_version": report["schema_version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

