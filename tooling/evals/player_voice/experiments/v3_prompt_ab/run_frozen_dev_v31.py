"""Run the frozen Dev-112 V3.1-only follow-up experiment."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tooling.evals.player_voice.experiments.v3_prompt_ab import run_frozen_dev_ab as ab  # noqa: E402


def main() -> int:
    if ab.file_hash(ab.DEV).upper() != ab.EXPECTED_DEV_HASH:
        raise SystemExit("STOP: frozen Dev hash mismatch.")
    dev, gold, regenerated = ab._load_frozen_inputs()
    manifest_path = ab.OUT / "DEV_AB_MANIFEST.json"
    frozen = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else regenerated
    if frozen.get("dataset_sha256") != regenerated.get("dataset_sha256") or frozen.get("batch_manifest_hash") != regenerated.get("batch_manifest_hash"):
        raise SystemExit("STOP: existing frozen manifest does not match the current Dev/preprocessing inputs.")

    ab.VARIANTS = {"v3_1": ab.llm.PROMPT_VERSION_V3_1}
    ab.OUT = ROOT / "tooling" / "evals" / "player_voice" / "experiments" / "v3_prompt_ab" / "v3_1"
    ab.OUT.mkdir(parents=True, exist_ok=True)
    ab.db.init_db()
    ab._write_json(ab.OUT / "DEV_AB_MANIFEST.json", frozen)

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("preflight", "full"), required=True)
    args = parser.parse_args()
    if args.phase == "preflight":
        rows, engineering = ab.run_variant("v3_1", dev, frozen, preflight=True)
        ab._write_json(ab.OUT / "preflight" / "v3_1.json", {"predictions": rows, "engineering": engineering})
        print(json.dumps({"status": "PREFLIGHT_PASS", "records": 10}, ensure_ascii=False))
        return 0

    rows, engineering = ab.run_variant("v3_1", dev, frozen)
    ab.write_jsonl(ab.OUT / "predictions" / "dev_v3_1.jsonl", rows)
    metrics = ab._metrics(gold, rows, engineering)
    ab._write_json(ab.OUT / "metrics" / "dev_v3_1_metrics.json", metrics)
    ab.OUT.joinpath("errors").mkdir(parents=True, exist_ok=True)
    ab._write_json(ab.OUT / "errors" / "dev_v3_1_errors.json", [row for row in rows if not row.get("schema_valid", False) or row.get("fallback")])
    report = {
        "experiment": "Frozen Dev 112 V3.1-only follow-up",
        "prompt_version": ab.llm.PROMPT_VERSION_V3_1,
        "dataset_sha256": frozen["dataset_sha256"],
        "batch_manifest_hash": frozen["batch_manifest_hash"],
        "metrics": metrics,
        "decision": "DEV_REVIEW_REQUIRED",
        "holdout_status": "untouched",
    }
    ab._write_json(ab.OUT / "DEV_V3_1_REPORT.json", report)
    print(json.dumps({"status": "DEV_V3_1_COMPLETE", "records": len(dev), "report": str(ab.OUT / "DEV_V3_1_REPORT.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
