"""Run the one-shot frozen Holdout-38 V3.1 confirmation."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tooling.evals.player_voice.experiments.v3_prompt_ab import run_frozen_dev_ab as ab  # noqa: E402

HOLDOUT = ROOT / "tooling" / "evals" / "holdout" / "P0_5CW_holdout.jsonl"
HOLDOUT_HASH = "08C68493076FC91D298586B0B61529222150EBC9189CA89EEE25DCC7E1886EE2"
GOLD = ROOT / "tooling" / "evals" / "gold" / "P0_5B_gold_verified_v2.jsonl"
OUT = ROOT / "tooling" / "evals" / "player_voice" / "experiments" / "v3_prompt_ab" / "holdout_v3_1"


def load_inputs() -> tuple[list[dict], list[dict], dict]:
    if ab.file_hash(HOLDOUT).upper() != HOLDOUT_HASH:
        raise SystemExit("STOP: Holdout hash mismatch.")
    holdout = ab.read_jsonl(HOLDOUT)
    if len(holdout) != 38:
        raise SystemExit(f"STOP: expected 38 Holdout records, found {len(holdout)}.")
    gold_rows = ab.read_jsonl(GOLD)
    gold_by_sample = {str(row["sample_id"]): row for row in gold_rows}
    if any(str(row["sample_id"]) not in gold_by_sample for row in holdout):
        raise SystemExit("STOP: Holdout contains a sample absent from Gold v2.")

    prep_by_id: dict[str, dict] = {}
    members_by_rep: dict[str, list[str]] = {}
    skip_ids: set[str] = set()
    representatives: list[dict] = []
    for app_id in sorted({int(row.get("app_id") or 0) for row in holdout}):
        rows = [row for row in holdout if int(row.get("app_id") or 0) == app_id]
        run = ab.review_preprocessor.ReviewPreprocessor(mode="active").process_reviews(
            app_id, [{"review_id": str(row["review_id"]), "review": row.get("source_review_text") or ""} for row in rows]
        )
        for review_id, result in run.results.items():
            prep_by_id[str(review_id)] = result
        for rep, members in run.members_by_representative.items():
            members_by_rep[str(rep)] = [str(member) for member in members]
        skip_ids.update(str(result.review_id) for result in run.results.values() if result.skip_llm)
        for rep in run.representatives:
            representatives.append({"review_id": str(rep), "review_text_for_model": run.results[rep].processed_text})

    planner = ab.batch_planner.DynamicBatchPlanner()
    plans = planner.plan(representatives, batch_id_prefix="holdout")
    batch_manifest = [{
        "batch_id": plan.batch_id, "lane": plan.lane.value, "review_ids": list(plan.review_ids),
        "review_count": plan.review_count, "total_processed_chars": plan.total_processed_chars,
    } for plan in plans]
    frozen = {
        "experiment_id": "v3_prompt_ab_holdout38",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(HOLDOUT.relative_to(ROOT)).replace("\\", "/"),
        "dataset_sha256": ab.file_hash(HOLDOUT), "record_count": len(holdout),
        "gold_version": "P0_5B_gold_verified_v2", "taxonomy_version": ab.llm.TAXONOMY_VERSION,
        "provider": ab.PROVIDER, "model": ab.MODEL,
        "preprocessor_version": ab.review_preprocessor.PREPROCESSOR_VERSION, "preprocess_mode": "active",
        "preprocessor_metrics": {"empty_reviews": sum(not str(row.get("source_review_text") or "").strip() for row in holdout),
            "pure_nonlexical_skips": len(skip_ids), "representatives": len(representatives),
            "duplicate_members_saved": len(holdout) - len(representatives) - len(skip_ids),
            "short_lexical_reviews": sum("short_text" in prep_by_id[str(row["review_id"])].flags and str(row.get("source_review_text") or "").strip() and str(row["review_id"]) not in skip_ids for row in holdout)},
        "batch_planner_config": asdict(planner.config), "batch_manifest_hash": ab.canonical_json_hash(batch_manifest),
        "batch_count": len(batch_manifest), "batch_manifest": batch_manifest,
        "prompt_version": ab.llm.PROMPT_VERSION_V3_1, "enrichment_limit": 0, "cache_enabled": False, "thinking_mode": "disabled",
        "representative_inputs": {str(item["review_id"]): {"review_text_for_model": item["review_text_for_model"],
            "members": members_by_rep.get(str(item["review_id"]), [str(item["review_id"])]),
            "skip_llm": str(item["review_id"]) in skip_ids} for item in representatives},
        "records": [{"sample_id": row["sample_id"], "review_id": str(row["review_id"]),
            "source_review_text": row.get("source_review_text") or "",
            "representative_id": next((rep for rep, members in members_by_rep.items() if str(row["review_id"]) in members), str(row["review_id"])),
            "skip_llm": str(row["review_id"]) in skip_ids} for row in holdout],
    }
    return holdout, [gold_by_sample[str(row["sample_id"])] for row in holdout], frozen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("preflight", "full"), required=True)
    args = parser.parse_args()
    holdout, gold, frozen = load_inputs()
    ab.VARIANTS = {"v3_1": ab.llm.PROMPT_VERSION_V3_1}
    ab.OUT = OUT
    OUT.mkdir(parents=True, exist_ok=True)
    ab.db.init_db()
    ab._write_json(OUT / "HOLDOUT_V3_1_MANIFEST.json", frozen)
    if args.phase == "preflight":
        rows, engineering = ab.run_variant("v3_1", holdout, frozen, preflight=True)
        ab._write_json(OUT / "preflight" / "v3_1.json", {"predictions": rows, "engineering": engineering})
        print(json.dumps({"status": "PREFLIGHT_PASS", "records": 10}, ensure_ascii=False))
        return 0
    rows, engineering = ab.run_variant("v3_1", holdout, frozen)
    ab.write_jsonl(OUT / "predictions" / "holdout_v3_1.jsonl", rows)
    metrics = ab._metrics(gold, rows, engineering)
    ab._write_json(OUT / "metrics" / "holdout_v3_1_metrics.json", metrics)
    OUT.joinpath("errors").mkdir(parents=True, exist_ok=True)
    ab._write_json(OUT / "errors" / "holdout_v3_1_errors.json", [row for row in rows if not row.get("schema_valid", False) or row.get("fallback")])
    report = {"experiment": "Frozen Holdout 38 V3.1 confirmation", "prompt_version": ab.llm.PROMPT_VERSION_V3_1,
        "dataset_sha256": frozen["dataset_sha256"], "batch_manifest_hash": frozen["batch_manifest_hash"],
        "metrics": metrics, "decision": "HOLDOUT_REVIEW_COMPLETE"}
    ab._write_json(OUT / "HOLDOUT_V3_1_REPORT.json", report)
    print(json.dumps({"status": "HOLDOUT_V3_1_COMPLETE", "records": len(holdout), "report": str(OUT / "HOLDOUT_V3_1_REPORT.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
