"""Run current-runtime Legacy against the already frozen Holdout V3.1 manifest."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tooling.evals.player_voice.experiments.v3_prompt_ab import run_frozen_dev_ab as ab  # noqa: E402

HOLDOUT = ROOT / "tooling" / "evals" / "holdout" / "P0_5CW_holdout.jsonl"
GOLD = ROOT / "tooling" / "evals" / "gold" / "P0_5B_gold_verified_v2.jsonl"
MANIFEST = ROOT / "tooling" / "evals" / "player_voice" / "experiments" / "v3_prompt_ab" / "holdout_v3_1" / "HOLDOUT_V3_1_MANIFEST.json"
OUT = ROOT / "tooling" / "evals" / "player_voice" / "experiments" / "v3_prompt_ab" / "holdout_legacy_paired"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("preflight", "full"), required=True)
    args = parser.parse_args()
    holdout = ab.read_jsonl(HOLDOUT)
    gold_all = ab.read_jsonl(GOLD)
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if len(holdout) != 38 or frozen.get("record_count") != 38 or frozen.get("dataset_sha256") != ab.file_hash(HOLDOUT):
        raise SystemExit("STOP: Holdout or frozen manifest integrity mismatch.")
    gold_by_sample = {str(row["sample_id"]): row for row in gold_all}
    gold = [gold_by_sample[str(row["sample_id"])] for row in holdout]

    ab.VARIANTS = {"legacy": ab.llm.PROMPT_VERSION}
    ab.OUT = OUT
    OUT.mkdir(parents=True, exist_ok=True)
    ab.db.init_db()
    ab._write_json(OUT / "HOLDOUT_LEGACY_PAIRED_MANIFEST.json", frozen)
    if args.phase == "preflight":
        rows, engineering = ab.run_variant("legacy", holdout, frozen, preflight=True)
        ab._write_json(OUT / "preflight" / "legacy.json", {"predictions": rows, "engineering": engineering})
        print(json.dumps({"status": "PREFLIGHT_PASS", "records": 10, "manifest": str(MANIFEST)}, ensure_ascii=False))
        return 0

    rows, engineering = ab.run_variant("legacy", holdout, frozen)
    ab.write_jsonl(OUT / "predictions" / "holdout_legacy_paired.jsonl", rows)
    metrics = ab._metrics(gold, rows, engineering)
    ab._write_json(OUT / "metrics" / "holdout_legacy_paired_metrics.json", metrics)
    OUT.joinpath("errors").mkdir(parents=True, exist_ok=True)
    ab._write_json(OUT / "errors" / "holdout_legacy_paired_errors.json", [row for row in rows if not row.get("schema_valid", False) or row.get("fallback")])
    report = {"experiment": "Current-runtime paired Holdout 38 Legacy", "prompt_version": ab.llm.PROMPT_VERSION,
        "dataset_sha256": frozen["dataset_sha256"], "batch_manifest_hash": frozen["batch_manifest_hash"],
        "metrics": metrics, "decision": "HOLDOUT_PAIRED_REVIEW_COMPLETE"}
    ab._write_json(OUT / "HOLDOUT_LEGACY_PAIRED_REPORT.json", report)
    print(json.dumps({"status": "HOLDOUT_LEGACY_PAIRED_COMPLETE", "records": len(holdout), "report": str(OUT / "HOLDOUT_LEGACY_PAIRED_REPORT.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
