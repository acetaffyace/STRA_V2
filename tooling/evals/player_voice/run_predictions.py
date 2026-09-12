from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from .common import read_jsonl, write_jsonl
    from .taxonomy import PROMPT_VERSION, TAXONOMY_VERSION
except ImportError:  # pragma: no cover
    from common import read_jsonl, write_jsonl
    from taxonomy import PROMPT_VERSION, TAXONOMY_VERSION


def run_predictions(records: list[dict], batch_size: int = 50) -> list[dict]:
    """Call the production batch classifier without touching review_labels."""
    api_dir = Path(__file__).resolve().parents[3] / "apps" / "api"
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))
    from senti_next import llm
    from senti_next.providers import get_provider
    from senti_next.providers.config import get_active_provider

    active_provider, active_model = get_active_provider()
    output: list[dict] = []
    for batch_index, start in enumerate(range(0, len(records), max(1, batch_size))):
        batch_records = records[start:start + max(1, batch_size)]
        batch = []
        identities = {}
        for record in batch_records:
            review_id = str(record.get("review_id") or record["sample_id"])
            raw = {
                "recommendationid": review_id,
                "review": record["source_review_text"],
                "language": record.get("language") or "english",
                **(record.get("raw_metadata") or {}),
            }
            identity = llm.classification_identity(raw, None, provider=active_provider, model_id=active_model)
            identities[review_id] = identity
            batch.append({
                "review_id": review_id,
                "review_text": record["source_review_text"],
                "review_hash": identity["review_hash"],
                "classification_input_hash": identity["classification_input_hash"],
                "was_truncated": identity["was_truncated"],
                "original_char_count": identity["original_char_count"],
                "processed_char_count": identity["processed_char_count"],
                "reviewer_playtime": (record.get("raw_metadata") or {}).get("author", {}).get("playtime_forever", 0),
                "reviewer_voted_up": (record.get("raw_metadata") or {}).get("voted_up", True),
                "review_language": record.get("language") or "english",
                "votes_up": (record.get("raw_metadata") or {}).get("votes_up", 0),
                "timestamp_created": (record.get("raw_metadata") or {}).get("timestamp_created", 0),
            })
        started = time.perf_counter()
        provider = get_provider(active_provider, active_model)
        usage_before = len(getattr(provider, "usage_history", []))
        payloads, model_used = llm.classify_reviews_batch(batch, game_context=None)
        elapsed_ms = (time.perf_counter() - started) * 1000
        per_record_ms = elapsed_ms / len(batch) if batch else 0.0
        usage_rows = getattr(provider, "usage_history", [])[usage_before:]
        usage = {
            "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in usage_rows),
            "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in usage_rows),
            "total_tokens": sum(int(row.get("total_tokens") or 0) for row in usage_rows),
            "cached_tokens": sum(int(row.get("cached_tokens") or 0) for row in usage_rows),
            "api_requests": len(usage_rows),
        }
        for record in batch_records:
            review_id = str(record.get("review_id") or record["sample_id"])
            prediction = payloads.get(review_id)
            schema_invalid = not isinstance(prediction, dict) or bool(prediction.get("_batch_missing"))
            if schema_invalid:
                prediction = {}
            normalized = llm.normalize_taxonomy_payload(prediction)
            identity = identities[review_id]
            output.append({
                "sample_id": record["sample_id"],
                "prediction": normalized,
                "taxonomy_version": TAXONOMY_VERSION,
                "prompt_version": PROMPT_VERSION,
                "provider": active_provider,
                "model_id": model_used,
                "classification_input_hash": identity["classification_input_hash"],
                "prediction_timestamp": datetime.now(timezone.utc).isoformat(),
                "schema_invalid": schema_invalid,
                "fallback": False,
                "retry_count": 0,
                "latency_ms": per_record_ms,
            "usage": usage,
                "batch_index": batch_index,
            })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Run production player-voice classifier for an isolated evaluation JSONL")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=None, help="Optional bounded prefix for budget preflight")
    parser.add_argument("--existing", default=None, help="Existing prediction JSONL whose sample IDs must not be called again")
    args = parser.parse_args()
    records = read_jsonl(args.input)
    existing = read_jsonl(args.existing) if args.existing else []
    existing_ids = {str(item.get("sample_id")) for item in existing}
    records = [record for record in records if str(record.get("sample_id")) not in existing_ids]
    if args.limit is not None:
        records = records[:max(0, args.limit)]
    predictions = existing + run_predictions(records, args.batch_size)
    write_jsonl(args.output, predictions)
    print(json.dumps({"predictions": len(predictions), "output": args.output}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
