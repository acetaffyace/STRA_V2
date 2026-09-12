"""Recompute frozen evaluation metrics without invoking a classifier."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tooling.evals.player_voice.common import file_hash, read_jsonl
from tooling.evals.player_voice.evaluate import evaluate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    gold_all = read_jsonl(args.gold)
    predictions = read_jsonl(args.predictions)
    prediction_ids = {str(row.get("sample_id")) for row in predictions}
    gold = [row for row in gold_all if str(row.get("sample_id")) in prediction_ids]
    report = evaluate(gold, predictions)
    report["dataset_hash"] = file_hash(args.gold)
    report["prediction_hash"] = file_hash(args.predictions)
    report["scoring_scope"] = {"gold_records": len(gold), "prediction_records": len(predictions), "filtered_to_prediction_ids": True}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
