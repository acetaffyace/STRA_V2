"""Create P0.5c reproducibility metadata when or before predictions exist."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .common import file_hash, read_jsonl
from .taxonomy import PROMPT_VERSION, TAXONOMY_VERSION


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default="tooling/evals/gold/P0_5B_gold_verified.jsonl")
    parser.add_argument("--dev", default="tooling/evals/dev/P0_5C_dev.jsonl")
    parser.add_argument("--holdout", default="tooling/evals/holdout/P0_5C_holdout.jsonl")
    parser.add_argument("--output", default="tooling/evals/reports/P0_5C_BASELINE.json")
    parser.add_argument("--manifest", default="tooling/evals/reports/P0_5C_SPLIT_MANIFEST.json")
    parser.add_argument("--salt", default="p0.5c-gold-v1")
    args = parser.parse_args()
    gold = read_jsonl(args.gold)
    dev = read_jsonl(args.dev)
    holdout = read_jsonl(args.holdout)
    split_manifest = {
        "dataset_hash": file_hash(args.gold),
        "dev_hash": file_hash(args.dev),
        "holdout_hash": file_hash(args.holdout),
        "salt": args.salt,
        "holdout_fraction_requested": 0.25,
        "counts": {"gold": len(gold), "development": len(dev), "holdout": len(holdout)},
        "core_challenge": {
            "gold": {k: sum(r.get("sampling_stratum") == k for r in gold) for k in ("core", "challenge")},
            "development": {k: sum(r.get("sampling_stratum") == k for r in dev) for k in ("core", "challenge")},
            "holdout": {k: sum(r.get("sampling_stratum") == k for r in holdout) for k in ("core", "challenge")},
        },
        "taxonomy_gap_count": sum(bool(r.get("gold_source_taxonomy_gap")) for r in gold),
    }
    Path(args.manifest).write_text(json.dumps(split_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    baseline = {
        "status": "NO-GO_NO_PROVIDER",
        "dataset_hash": split_manifest["dataset_hash"],
        "prediction_hash": "not-generated:no-provider",
        "dataset_version": "p0.5c-gold-verified-v1",
        "core_challenge_split": split_manifest["core_challenge"],
        "development_holdout_split": split_manifest["counts"],
        "taxonomy_version": TAXONOMY_VERSION,
        "guideline_version": gold[0].get("guideline_version") if gold else None,
        "prompt_version": PROMPT_VERSION,
        "provider": None,
        "model_id": None,
        "annotation_provenance": {
            "verification_method": "human_review_of_model_assisted_labels",
            "verified_by": "project_owner",
            "verified_record_count": len(gold),
            "taxonomy_gap_count": split_manifest["taxonomy_gap_count"],
            "independent_double_human_annotation": False,
        },
        "preprocessing": {"status": "not-run; provider unavailable"},
        "evaluation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "metrics": {"status": "pending_provider_execution", "development": None, "holdout": None},
        "operational": None,
    }
    Path(args.output).write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"dataset_hash": split_manifest["dataset_hash"], "dev": len(dev), "holdout": len(holdout), "status": baseline["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
