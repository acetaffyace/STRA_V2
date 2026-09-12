"""Assemble reproducibility metadata for the Gold-v2 deterministic rescore."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .common import file_hash, read_jsonl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True)
    parser.add_argument("--gold-v1", required=True)
    parser.add_argument("--diff", required=True)
    parser.add_argument("--dev-metrics", required=True)
    parser.add_argument("--holdout-metrics", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    gold = read_jsonl(args.gold)
    diff = json.loads(Path(args.diff).read_text(encoding="utf-8"))
    result = {
        "status": "completed_deterministic_rescore",
        "dataset_version": "p0.5c-gold-verified-v2",
        "predecessor_dataset_version": "p0.5c-gold-verified-v1",
        "gold_v2_hash": file_hash(args.gold),
        "gold_v1_hash": file_hash(args.gold_v1),
        "correction_provenance": {
            "source": "human_adjudication_p0.5cv",
            "reviewed_candidate_count": diff["human_reviewed_candidate_count"],
            "changed_record_count": diff["changed_record_count"],
            "diff_file": args.diff,
        },
        "prediction_hashes_unchanged": {
            "dev": "356d25e02201c183076615923a57dbd626b02753bfc28f29dd38be3fa82445f0",
            "holdout": "3ea1cc3a608b3e99484e2371672194ca2648bac8dc4ca3656dc1ab9bcf5085f5",
        },
        "provider": "deepseek",
        "model_id": "deepseek-v4-flash",
        "predictions_rerun": False,
        "annotation_provenance": {
            "verified_record_count": len(gold),
            "gold_source": "user_verified_external_annotation",
            "taxonomy_gap_count": sum(bool(row.get("gold_source_taxonomy_gap")) for row in gold),
        },
        "metrics": {
            "development": json.loads(Path(args.dev_metrics).read_text(encoding="utf-8")),
            "holdout": json.loads(Path(args.holdout_metrics).read_text(encoding="utf-8")),
        },
        "evaluation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gold_v2_hash": result["gold_v2_hash"], "changed": diff["changed_record_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
