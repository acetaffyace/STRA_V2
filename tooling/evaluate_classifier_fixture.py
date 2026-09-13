"""Evaluate an offline classifier fixture without contacting an LLM provider."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.api.senti_next.classifier_taxonomy import load_classifier_taxonomy
from apps.api.senti_next.classifier_validation import evaluate_classifier_fixture


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-json", required=True, type=Path)
    parser.add_argument("--predictions-json", required=True, type=Path)
    parser.add_argument("--taxonomy-version", default=None)
    args = parser.parse_args()
    gold = json.loads(args.gold_json.read_text(encoding="utf-8"))
    predictions = json.loads(args.predictions_json.read_text(encoding="utf-8"))
    report = evaluate_classifier_fixture(
        gold,
        predictions,
        taxonomy_contract=load_classifier_taxonomy(args.taxonomy_version),
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
