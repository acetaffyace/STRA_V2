"""Run the frozen Dev-112 Legacy vs V3 classifier A/B experiment.

This runner calls only the first-pass review classifier. It never invokes
ensure_review_labels(), so production review-label cache is not touched.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
API_DIR = ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import batch_planner, llm, review_preprocessor  # noqa: E402
from senti_next import db  # noqa: E402
from senti_next.db import get_connection  # noqa: E402
from senti_next.providers.config import validate_live_runtime  # noqa: E402
from tooling.evals.player_voice.common import canonical_json_hash, file_hash, read_jsonl, write_jsonl  # noqa: E402
from tooling.evals.player_voice.evaluate import evaluate  # noqa: E402


DEV = ROOT / "tooling" / "evals" / "dev" / "P0_5CW_dev.jsonl"
GOLD = ROOT / "tooling" / "evals" / "gold" / "P0_5B_gold_verified_v2.jsonl"
OUT = ROOT / "tooling" / "evals" / "player_voice" / "experiments" / "v3_prompt_ab"
EXPECTED_DEV_HASH = "25CDDFDF3190AB78AC24FFE935082D3A3425D53F4F1059D0E53EF2C6002DF9FF"
PROVIDER = "deepseek"
MODEL = "deepseek-v4-flash"
VARIANTS = {
    "legacy": llm.PROMPT_VERSION,
    "v3": llm.PROMPT_VERSION_V3,
}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_frozen_inputs() -> tuple[list[dict], list[dict], dict]:
    if file_hash(DEV).upper() != EXPECTED_DEV_HASH:
        raise SystemExit("STOP: P0_5CW_dev.jsonl SHA-256 does not match the frozen hash.")
    dev = read_jsonl(DEV)
    if len(dev) != 112:
        raise SystemExit(f"STOP: expected 112 Dev records, found {len(dev)}.")
    gold = read_jsonl(GOLD)
    gold_ids = {str(row["sample_id"]) for row in gold}
    if any(str(row["sample_id"]) not in gold_ids for row in dev):
        raise SystemExit("STOP: Dev contains a sample absent from Gold v2.")

    prep_by_id: dict[str, Any] = {}
    members_by_rep: dict[str, list[str]] = {}
    skip_ids: set[str] = set()
    representatives: list[dict] = []
    for app_id in sorted({int(row.get("app_id") or 0) for row in dev}):
        rows = [row for row in dev if int(row.get("app_id") or 0) == app_id]
        run = review_preprocessor.ReviewPreprocessor(mode="active").process_reviews(
            app_id, [{"review_id": str(row["review_id"]), "review": row.get("source_review_text") or ""} for row in rows]
        )
        for review_id, result in run.results.items():
            prep_by_id[str(review_id)] = result
        for rep, members in run.members_by_representative.items():
            members_by_rep[str(rep)] = [str(member) for member in members]
        skip_ids.update(str(result.review_id) for result in run.results.values() if result.skip_llm)
        for rep in run.representatives:
            result = run.results[rep]
            representatives.append({
                "review_id": str(rep),
                "review_text_for_model": result.processed_text,
            })

    planner = batch_planner.DynamicBatchPlanner()
    plans = planner.plan(representatives, batch_id_prefix="dev")
    batch_manifest = [{
        "batch_id": plan.batch_id,
        "lane": plan.lane.value,
        "review_ids": list(plan.review_ids),
        "review_count": plan.review_count,
        "total_processed_chars": plan.total_processed_chars,
    } for plan in plans]
    frozen = {
        "experiment_id": "v3_prompt_ab_dev112",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(DEV.relative_to(ROOT)).replace("\\", "/"),
        "dataset_sha256": file_hash(DEV),
        "record_count": len(dev),
        "gold_version": "P0_5B_gold_verified_v2",
        "taxonomy_version": llm.TAXONOMY_VERSION,
        "provider": PROVIDER,
        "model": MODEL,
        "preprocessor_version": review_preprocessor.PREPROCESSOR_VERSION,
        "preprocess_mode": "active",
        "preprocessor_metrics": {
            "empty_reviews": sum(not str(row.get("source_review_text") or "").strip() for row in dev),
            "pure_nonlexical_skips": len(skip_ids),
            "representatives": len(representatives),
            "duplicate_members_saved": len(dev) - len(representatives) - len(skip_ids),
            "short_lexical_reviews": sum("short_text" in prep_by_id[str(row["review_id"])].flags and str(row.get("source_review_text") or "").strip() and str(row["review_id"]) not in skip_ids for row in dev),
        },
        "batch_planner_config": asdict(planner.config),
        "batch_manifest_hash": canonical_json_hash(batch_manifest),
        "batch_count": len(batch_manifest),
        "batch_manifest": batch_manifest,
        "legacy_prompt_version": VARIANTS["legacy"],
        "v3_prompt_version": VARIANTS["v3"],
        "enrichment_limit": 0,
        "cache_enabled": False,
        "thinking_mode": "disabled",
        "representative_inputs": {
            str(item["review_id"]): {
                "review_text_for_model": item["review_text_for_model"],
                "members": members_by_rep.get(str(item["review_id"]), [str(item["review_id"])]),
                "skip_llm": str(item["review_id"]) in skip_ids,
            } for item in representatives
        },
        "records": [{
            "sample_id": row["sample_id"],
            "review_id": str(row["review_id"]),
            "source_review_text": row.get("source_review_text") or "",
            "representative_id": next((rep for rep, members in members_by_rep.items() if str(row["review_id"]) in members), str(row["review_id"])),
            "skip_llm": str(row["review_id"]) in skip_ids,
        } for row in dev],
    }
    gold_by_sample = {str(row["sample_id"]): row for row in gold}
    return dev, [gold_by_sample[str(row["sample_id"])] for row in dev], frozen


def _ledger_rows(prompt_version: str, since: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(__import__("sqlalchemy").text("SELECT call_id, attempt_number, status, input_tokens, output_tokens, total_tokens, cached_input_tokens, estimated_cost, latency_ms, error_type FROM llm_calls WHERE purpose='classifier_ab' AND workload_type='evaluation' AND prompt_version=:prompt_version AND created_at>=:since ORDER BY created_at"), {"prompt_version": prompt_version, "since": since.replace("T", " ", 1)}).mappings().all()
    return [dict(row) for row in rows]


def _make_item(record: dict, prep: dict, prompt_version: str) -> tuple[dict, dict]:
    raw = {"review_id": record["review_id"], "review": record.get("source_review_text") or ""}
    identity = llm.classification_identity(raw, None, provider=PROVIDER, model_id=MODEL, prompt_version=prompt_version, processed_text=prep["review_text_for_model"])
    item = {
        "review_id": str(record["review_id"]),
        "review_text": prep["review_text_for_model"],
        "review_hash": identity["review_hash"],
        "classification_input_hash": identity["classification_input_hash"],
        "was_truncated": identity["was_truncated"],
        "original_char_count": identity["original_char_count"],
        "processed_char_count": identity["processed_char_count"],
    }
    return item, identity


def _call_batch(items: list[dict], *, variant: str, experiment_id: str, batch_id: str, attempt_number: int) -> tuple[dict, dict]:
    os.environ["SENTINEXT_CLASSIFIER_PROMPT_VARIANT"] = variant
    version = VARIANTS[variant]
    operation_id = f"{experiment_id}:{variant}"
    started = time.perf_counter()
    before = len(getattr(_call_batch.provider, "usage_history", []))
    error = None
    payloads: dict = {}
    try:
        with llm.llm_usage_context(
            operation="classifier_ab", workload_type="evaluation", prompt_version=version,
            taxonomy_version=llm.TAXONOMY_VERSION, requested_review_count=len(items),
            operation_id=operation_id, attempt_number=attempt_number + 1,
        ):
            payloads, _ = llm.classify_reviews_batch(items, game_context=None)
    except Exception as exc:  # provider failures remain visible in ledger
        error = exc
    usage_rows = getattr(_call_batch.provider, "usage_history", [])[before:]
    telemetry = {
        "batch_id": batch_id,
        "variant": variant,
        "prompt_version": version,
        "attempt_number": attempt_number,
        "is_retry": attempt_number > 0,
        "review_count": len(items),
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "provider_usage_rows": usage_rows,
        "error": str(error) if error else None,
    }
    return payloads, telemetry


def run_variant(variant: str, dev: list[dict], frozen: dict, *, preflight: bool = False) -> tuple[list[dict], dict]:
    from senti_next.providers import get_provider
    _call_batch.provider = get_provider(PROVIDER, MODEL)
    limit_ids = {str(row["review_id"]) for row in dev[:10]} if preflight else None
    records = {str(row["review_id"]): row for row in frozen["records"]}
    prep = frozen["representative_inputs"]
    member_to_rep = {member: rep for rep, data in prep.items() for member in data["members"]}
    batch_plans = frozen["batch_manifest"]
    ledger_since = datetime.now(timezone.utc).isoformat()
    outputs: dict[str, dict] = {}
    telemetry: list[dict] = []
    for plan in batch_plans:
        ids = [rid for rid in plan["review_ids"] if limit_ids is None or rid in limit_ids or any(member_to_rep.get(rid) in limit_ids for member in limit_ids)]
        if not ids:
            continue
        items = []
        for rid in ids:
            item, _ = _make_item(records[rid], prep[rid], VARIANTS[variant])
            items.append(item)
        pending = items
        attempt = 0
        while pending and attempt <= 2:
            payloads, call_meta = _call_batch(pending, variant=variant, experiment_id=frozen["experiment_id"] + ("_preflight" if preflight else ""), batch_id=plan["batch_id"], attempt_number=attempt)
            telemetry.append(call_meta)
            validation_input = {rid: (None if isinstance(value, dict) and value.get("_batch_invalid") else value) for rid, value in payloads.items() if not (isinstance(value, dict) and value.get("_batch_missing"))}
            validation = batch_planner.validate_batch_results([item["review_id"] for item in pending], validation_input, parse_result=llm._parse_payload_mapping)
            for rid, payload in validation.valid_results.items():
                outputs[rid] = {"prediction": payload, "schema_valid": True, "retry_count": attempt, "batch_id": plan["batch_id"]}
            pending = [item for item in pending if str(item["review_id"]) in validation.retry_ids]
            if not pending or attempt >= 2:
                for item in pending:
                    outputs[item["review_id"]] = {"prediction": llm._DEFAULT_LABEL.copy(), "schema_valid": False, "fallback": True, "retry_count": attempt, "batch_id": plan["batch_id"]}
                break
            attempt += 1

    predictions = []
    for row in dev[:10] if preflight else dev:
        rid = str(row["review_id"])
        rep = member_to_rep.get(rid, rid)
        data = outputs.get(rep)
        if data is None:
            data = {"prediction": llm._DEFAULT_LABEL.copy(), "schema_valid": False, "fallback": True, "retry_count": 0, "batch_id": None}
        is_skip = bool(frozen["records"][next(index for index, item in enumerate(frozen["records"]) if item["sample_id"] == row["sample_id"])] ["skip_llm"])
        predictions.append({
            "sample_id": row["sample_id"], "review_id": rid, "variant": variant,
            "prompt_version": VARIANTS[variant], "provider": PROVIDER, "model": MODEL,
            "prediction": data["prediction"], "schema_valid": data.get("schema_valid", False),
            "fallback": bool(data.get("fallback", False)), "fallback_reason": "nonlexical_skip" if is_skip else None, "retry_count": data.get("retry_count", 0),
            "classification_input_hash": _make_item(row, prep[rep], VARIANTS[variant])[1]["classification_input_hash"] if rep in prep else None,
            "batch_id": data.get("batch_id"),
        })
    operation_id = f"{frozen['experiment_id']}{'_preflight' if preflight else ''}:{variant}"
    return predictions, {"telemetry": telemetry, "ledger": _ledger_rows(VARIANTS[variant], ledger_since), "operation_id": operation_id}


def _metrics(gold: list[dict], predictions: list[dict], engineering: dict) -> dict:
    report = evaluate(gold, predictions)
    all_predictions = [item.get("prediction") or {} for item in predictions]
    counts = Counter(len(item.get("subcategories") or []) for item in all_predictions)
    labeled = [row for row in gold if row.get("annotation_status") == "labeled" and isinstance(row.get("gold"), dict)]
    ledger = engineering["ledger"]
    report["topic_count"] = {
        "avg_predicted_subcategory_count": statistics.mean([len(item.get("subcategories") or []) for item in all_predictions]) if all_predictions else None,
        "median_predicted_subcategory_count": statistics.median([len(item.get("subcategories") or []) for item in all_predictions]) if all_predictions else None,
        "predicted_count_distribution": {str(i): counts.get(i, 0) for i in range(1, 7)},
        "avg_gold_subcategory_count": statistics.mean([len((row.get("gold") or {}).get("subcategories") or []) for row in labeled]) if labeled else None,
    }
    report["primary_topic_exact_accuracy"] = None
    report["primary_topic_unavailable_reason"] = "Gold v2 has no explicit primary_subcategory field; no primary truth was manufactured."
    latencies = [row["latency_ms"] for row in ledger if row["latency_ms"] is not None]
    def percentile(values: list[float], fraction: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
        return ordered[index]
    report["engineering"] = {
        "physical_api_calls": len(ledger),
        "input_tokens": sum(row["input_tokens"] or 0 for row in ledger),
        "cached_input_tokens": sum(row["cached_input_tokens"] or 0 for row in ledger),
        "output_tokens": sum(row["output_tokens"] or 0 for row in ledger),
        "total_tokens": sum(row["total_tokens"] or 0 for row in ledger),
        "estimated_cost": sum(row["estimated_cost"] or 0 for row in ledger) if any(row["estimated_cost"] is not None for row in ledger) else None,
        "wall_clock_duration_ms": sum(row["latency_ms"] or 0 for row in ledger) if ledger else None,
        "provider_latency_ms": {"average": statistics.mean(latencies) if latencies else None, "p50": percentile(latencies, 0.50), "p95": percentile(latencies, 0.95)},
        "successful_batches": sum(not item.get("error") for item in engineering.get("telemetry", [])),
        "failed_batches": sum(bool(item.get("error")) for item in engineering.get("telemetry", [])),
        "successful_calls": sum(row["status"] == "completed" for row in ledger),
        "failed_calls": sum(row["status"] == "failed" for row in ledger),
        "schema_invalid_count": sum(not item.get("schema_valid", False) and item.get("fallback_reason") != "nonlexical_skip" for item in predictions),
        "pure_nonlexical_skip_count": sum(item.get("fallback_reason") == "nonlexical_skip" for item in predictions),
        "fallback_count": sum(bool(item.get("fallback")) for item in predictions),
        "retry_physical_calls": sum(max(0, int(row["attempt_number"] or 1) - 1) for row in ledger),
        "split_calls": 0,
        "missing_result_count": sum(item.get("prediction") == {} for item in predictions),
    }
    return report


def _write_report(gold: list[dict], legacy: list[dict], v3: list[dict], legacy_metrics: dict, v3_metrics: dict, frozen: dict) -> None:
    changed = []
    for left, right, row in zip(legacy, v3, gold):
        lp, rp = left.get("prediction") or {}, right.get("prediction") or {}
        if lp == rp:
            continue
        changed.append({"sample_id": row["sample_id"], "review_text": row.get("source_review_text") or "", "gold": row.get("gold"), "legacy_prediction": lp, "v3_prediction": rp, "difference": {"labels_added": sorted(set(rp.get("subcategories", [])) - set(lp.get("subcategories", []))), "labels_removed": sorted(set(lp.get("subcategories", [])) - set(rp.get("subcategories", []))), "primary_changed": (lp.get("subcategories") or [None])[0] != (rp.get("subcategories") or [None])[0], "issue_changed": lp.get("issue_subcategories", []) != rp.get("issue_subcategories", []), "request_changed": lp.get("request_subcategories", []) != rp.get("request_subcategories", [])}})
    OUT.joinpath("errors").mkdir(parents=True, exist_ok=True)
    _write_json(OUT / "errors" / "dev_ab_changed_cases.json", changed)
    for variant, rows in (("legacy", legacy), ("v3", v3)):
        _write_json(
            OUT / "errors" / f"dev_{variant}_errors.json",
            [row for row in rows if not row.get("schema_valid", False) or row.get("fallback")],
        )
    delta = {"legacy": legacy_metrics, "v3": v3_metrics, "absolute_delta": {}, "relative_delta": {}}
    for key in ("subcategories", "issues", "requests"):
        for metric in ("precision", "recall", "f1"):
            lv = legacy_metrics["groups"]["all"][key]["micro"][metric]
            vv = v3_metrics["groups"]["all"][key]["micro"][metric]
            delta["absolute_delta"][f"{key}.{metric}"] = vv - lv
    for key in ("avg_predicted_subcategory_count",):
        delta["absolute_delta"][key] = v3_metrics["topic_count"][key] - legacy_metrics["topic_count"][key]
    for key, value in delta["absolute_delta"].items():
        if "." in key:
            group, metric = key.split(".", 1)
            base = legacy_metrics["groups"]["all"][group]["micro"].get(metric)
        else:
            base = legacy_metrics["topic_count"].get(key)
        delta["relative_delta"][key] = value / base if base not in (None, 0) else None
    delta["engineering"] = {"legacy": legacy_metrics["engineering"], "v3": v3_metrics["engineering"]}
    _write_json(OUT / "metrics" / "dev_ab_delta.json", delta)
    report = f"""# DEV V3 A/B Report\n\n## Experiment Integrity\n\n- Dev: 112 records; SHA-256 `{frozen['dataset_sha256']}`\n- Same provider/model: `{PROVIDER}` / `{MODEL}`\n- Same taxonomy, active V1 preprocessing, frozen V2 batch manifest `{frozen['batch_manifest_hash']}`\n- Enrichment: 0; cache: false; Holdout was not read or run\n\n## Legacy\n\n```json\n{json.dumps(legacy_metrics, ensure_ascii=False, indent=2)}\n```\n\n## V3\n\n```json\n{json.dumps(v3_metrics, ensure_ascii=False, indent=2)}\n```\n\n## Delta\n\n```json\n{json.dumps(delta, ensure_ascii=False, indent=2)}\n```\n\n## Changed Cases\n\nChanged sample count: `{len(changed)}`. Differences are deterministic only; no automatic correctness attribution was made.\n\n## Decision\n\n`DEV_REVIEW_REQUIRED`\n\n## Next Step\n\nReview paired Dev deltas and changed cases manually. Holdout 38 remains untouched and is not automatically executed.\n"""
    (OUT / "DEV_V3_AB_REPORT.md").write_text(report, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("preflight", "full", "report"), required=True)
    args = parser.parse_args()
    if args.phase == "report":
        dev, gold, frozen = _load_frozen_inputs()
        rebuilt = {}
        for variant in VARIANTS:
            prediction_path = OUT / "predictions" / f"dev_{variant}.jsonl"
            rows = [json.loads(line) for line in prediction_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            skip_ids = {str(item["sample_id"]) for item in frozen["records"] if item.get("skip_llm")}
            for row in rows:
                if str(row.get("sample_id")) in skip_ids:
                    row["fallback_reason"] = "nonlexical_skip"
            old_metrics = json.loads((OUT / "metrics" / f"dev_{variant}_metrics.json").read_text(encoding="utf-8"))
            rebuilt[variant] = _metrics(gold, rows, {"ledger": [], "telemetry": []})
            old_engineering = old_metrics.get("engineering", {})
            merged_engineering = dict(old_engineering)
            for key in ("schema_invalid_count", "pure_nonlexical_skip_count", "fallback_count", "missing_result_count"):
                merged_engineering[key] = rebuilt[variant]["engineering"].get(key)
            rebuilt[variant]["engineering"] = merged_engineering
            _write_json(OUT / "metrics" / f"dev_{variant}_metrics.json", rebuilt[variant])
            write_jsonl(prediction_path, rows)
        _write_report(gold, rebuilt["legacy"] and [json.loads(line) for line in (OUT / "predictions" / "dev_legacy.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()], rebuilt["v3"] and [json.loads(line) for line in (OUT / "predictions" / "dev_v3.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()], rebuilt["legacy"], rebuilt["v3"], frozen)
        print(json.dumps({"status": "REPORT_REBUILT", "report": str(OUT / "DEV_V3_AB_REPORT.md")}, ensure_ascii=False))
        return 0
    ok, error = validate_live_runtime(PROVIDER, MODEL)
    if not ok:
        raise SystemExit(f"STOP: provider unavailable: {error}")
    dev, gold, frozen = _load_frozen_inputs()
    OUT.mkdir(parents=True, exist_ok=True)
    # The experiment ledger is deliberately isolated from the app's
    # production database and review-label cache.
    db.init_db()
    _write_json(OUT / "DEV_AB_MANIFEST.json", frozen)
    if args.phase == "preflight":
        for variant in VARIANTS:
            predictions, engineering = run_variant(variant, dev, frozen, preflight=True)
            _write_json(OUT / "preflight" / f"{variant}.json", {"predictions": predictions, "engineering": engineering})
        print(json.dumps({"status": "PREFLIGHT_PASS", "records": 10, "manifest": str(OUT / "DEV_AB_MANIFEST.json")}, ensure_ascii=False))
        return 0
    predictions = {}
    metrics = {}
    for variant in VARIANTS:
        rows, engineering = run_variant(variant, dev, frozen)
        predictions[variant] = rows
        OUT.joinpath("predictions").mkdir(parents=True, exist_ok=True)
        write_jsonl(OUT / "predictions" / f"dev_{variant}.jsonl", rows)
        metrics[variant] = _metrics(gold, rows, engineering)
        _write_json(OUT / "metrics" / f"dev_{variant}_metrics.json", metrics[variant])
    _write_report(gold, predictions["legacy"], predictions["v3"], metrics["legacy"], metrics["v3"], frozen)
    print(json.dumps({"status": "DEV_COMPLETE", "records": len(dev), "report": str(OUT / "DEV_V3_AB_REPORT.md")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
