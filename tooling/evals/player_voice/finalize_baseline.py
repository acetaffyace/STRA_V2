"""Finalize P0.5c baseline metadata after both paid artifacts are frozen."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .common import file_hash, read_jsonl


def usage(path: str) -> dict:
    total = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "api_requests": 0, "retries": 0}
    seen = set()
    for record in read_jsonl(path):
        key = record.get("batch_index", record.get("sample_id"))
        if key in seen:
            continue
        seen.add(key)
        row = record.get("usage") or {}
        for field in total:
            total[field] += int(row.get(field) or 0)
    return total


def cost(tokens: dict) -> dict:
    # DeepSeek V4 Flash published rates used for this evaluation run.
    hit_usd = tokens["cached_tokens"] / 1_000_000 * 0.0028
    miss_usd = max(0, tokens["prompt_tokens"] - tokens["cached_tokens"]) / 1_000_000 * 0.14
    output_usd = tokens["completion_tokens"] / 1_000_000 * 0.28
    usd = hit_usd + miss_usd + output_usd
    return {"input_cache_hit_usd": hit_usd, "input_cache_miss_usd": miss_usd, "output_usd": output_usd, "total_usd": usd, "total_rmb_at_8_usd_rmb": usd * 8.0, "usd_rmb_assumption": 8.0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default="tooling/evals/gold/P0_5B_gold_verified.jsonl")
    parser.add_argument("--dev", default="tooling/evals/dev/P0_5C_dev.jsonl")
    parser.add_argument("--holdout", default="tooling/evals/holdout/P0_5C_holdout.jsonl")
    parser.add_argument("--dev-predictions", required=True)
    parser.add_argument("--holdout-predictions", required=True)
    parser.add_argument("--dev-metrics", required=True)
    parser.add_argument("--holdout-metrics", required=True)
    parser.add_argument("--dev-errors", required=True)
    parser.add_argument("--holdout-errors", required=True)
    parser.add_argument("--output", default="tooling/evals/reports/P0_5C_BASELINE.json")
    args = parser.parse_args()
    dev_usage = usage(args.dev_predictions)
    holdout_usage = usage(args.holdout_predictions)
    combined = {key: dev_usage[key] + holdout_usage[key] for key in dev_usage}
    report = {
        "status": "completed",
        "dataset_hash": file_hash(args.gold),
        "prediction_hash": {"development": file_hash(args.dev_predictions), "holdout": file_hash(args.holdout_predictions)},
        "dataset_version": "p0.5c-gold-verified-v1",
        "split_hash": {"development": file_hash(args.dev), "holdout": file_hash(args.holdout)},
        "taxonomy_version": "sentinext-taxonomy-v1",
        "guideline_version": read_jsonl(args.gold)[0].get("guideline_version"),
        "prompt_version": "steam_review_insights_v16_basic_labels",
        "schema_version": "review-classification-schema-v1",
        "provider": "deepseek",
        "model_id": "deepseek:deepseek-v4-flash",
        "thinking_mode": "disabled",
        "response_format": "json_object",
        "preprocessing": {"max_review_chars": 3000, "min_review_words": 2, "classification_identity": "production classification_identity"},
        "annotation_provenance": {"verification_method": "human_review_of_model_assisted_labels", "verified_by": "project_owner", "verified_record_count": 150, "independent_double_human_annotation": False, "taxonomy_gap_count": 4},
        "evaluation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "metrics": {"development": json.loads(Path(args.dev_metrics).read_text(encoding="utf-8")), "holdout": json.loads(Path(args.holdout_metrics).read_text(encoding="utf-8"))},
        "error_analysis": {"development": json.loads(Path(args.dev_errors).read_text(encoding="utf-8")), "holdout": json.loads(Path(args.holdout_errors).read_text(encoding="utf-8"))},
        "operational_usage": {"development": dev_usage, "holdout": holdout_usage, "combined": combined, "cost": {"development": cost(dev_usage), "holdout": cost(holdout_usage), "combined": cost(combined)}},
        "future_regression_gates": {"status": "propose_after_observed_baseline_review", "thresholds": []},
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "dataset_hash": report["dataset_hash"], "cost_rmb": report["operational_usage"]["cost"]["combined"]["total_rmb_at_8_usd_rmb"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
