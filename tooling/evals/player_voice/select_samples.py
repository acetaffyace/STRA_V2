from __future__ import annotations

import argparse
import random
import re
from typing import Any

try:
    from .common import read_jsonl, source_hash, write_jsonl
except ImportError:  # pragma: no cover
    from common import read_jsonl, source_hash, write_jsonl

GUIDELINE_VERSION = "p0.5a-guidelines-v1"
TAXONOMY_VERSION = "sentinext-taxonomy-v1"


def _text(record: dict[str, Any]) -> str:
    return str(record.get("review") or record.get("review_text") or record.get("source_review_text") or "").strip()


def challenge_reasons(record: dict[str, Any]) -> list[str]:
    text = _text(record)
    lowered = text.lower()
    reasons: list[str] = []
    if len(text.split()) <= 6:
        reasons.append("very_short_review")
    if len(text.split()) >= 120 or len(text) >= 900:
        reasons.append("long_review")
    if re.search(r"\b(lol|yeah right|sure|bravo|great job)\b|[!?]{2,}", lowered):
        reasons.append("possible_sarcasm")
    issue_terms = re.findall(r"\b(crash|bug|broken|lag|stutter|ui|controller|server|boring|empty|refund)\w*\b", lowered)
    if len(set(issue_terms)) >= 2:
        reasons.append("multiple_issue_signals")
    if re.search(r"\b(please|wish|should|add|need|would love|希望|请|应该|añadir|por favor)\b", lowered):
        reasons.append("request_signal")
    if re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0400-\u04ff\u0e00-\u0e7f]", text) and re.search(r"[A-Za-z]", text):
        reasons.append("multilingual_code_switching")
    if re.search(r"\b(gameplay|mechanic|controls?)\b", lowered) and re.search(r"\b(level|quest|content|mode|ui|interface)\b", lowered):
        reasons.append("taxonomy_boundary_candidate")
    if re.search(r"\b(good|great|love|fun)\b", lowered) and re.search(r"\b(bad|issue|bug|but|however|crash)\b", lowered):
        reasons.append("mixed_sentiment_or_issue_plus_praise")
    return reasons


def make_record(raw: dict[str, Any], index: int, stratum: str, reason: str, signal_source: str = "raw_text") -> dict[str, Any]:
    text = _text(raw)
    review_id = raw.get("review_id") or raw.get("recommendationid")
    app_id = raw.get("app_id") or raw.get("appid")
    if app_id is None:
        raise ValueError(f"source record {index} has no app_id/appid")
    raw_metadata = {
        key: raw[key] for key in ("language", "voted_up", "votes_up", "timestamp_created", "author", "steam_purchase", "received_for_free")
        if key in raw and key != "review"
    }
    return {
        "sample_id": f"pv-{int(app_id)}-{str(review_id or index)}",
        "app_id": int(app_id),
        "review_id": str(review_id) if review_id is not None else None,
        "source_review_text": text,
        "source_review_hash": source_hash(text),
        "language": raw.get("language"),
        "raw_metadata": raw_metadata,
        "sampling_stratum": stratum,
        "sampling_reason": reason,
        "sampling_signal_source": signal_source,
        "annotation_status": "pending",
        "guideline_version": GUIDELINE_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "annotator_id": None,
        "adjudication_status": "not_started",
        "annotation_notes": "",
        "gold": None,
        "annotations": [],
    }


def select_records(records: list[dict[str, Any]], core_limit: int, challenge_limit: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    candidates = [record for record in records if _text(record) and (record.get("app_id") is not None or record.get("appid") is not None)]
    rng.shuffle(candidates)
    challenge: list[tuple[dict[str, Any], str]] = []
    core: list[dict[str, Any]] = []
    for record in candidates:
        reasons = challenge_reasons(record)
        if reasons and len(challenge) < challenge_limit:
            challenge.append((record, ";".join(reasons)))
        elif len(core) < core_limit:
            core.append(record)
        if len(challenge) >= challenge_limit and len(core) >= core_limit:
            break
    selected = [make_record(record, index, "core", "natural traffic sample") for index, record in enumerate(core)]
    selected.extend(make_record(record, index, "challenge", reason) for index, (record, reason) in enumerate(challenge, len(selected)))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Select real Steam reviews for P0.5a annotation")
    parser.add_argument("--input", required=True, help="Existing JSONL/JSON source review export")
    parser.add_argument("--output", required=True)
    parser.add_argument("--core", type=int, default=100)
    parser.add_argument("--challenge", type=int, default=50)
    parser.add_argument("--seed", type=int, default=505)
    args = parser.parse_args()
    records = read_jsonl(args.input)
    selected = select_records(records, args.core, args.challenge, args.seed)
    write_jsonl(args.output, selected)
    print({"source_records": len(records), "selected": len(selected), "core": sum(r["sampling_stratum"] == "core" for r in selected), "challenge": sum(r["sampling_stratum"] == "challenge" for r in selected), "seed": args.seed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
