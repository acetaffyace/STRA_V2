from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import read_jsonl, source_hash
    from .taxonomy import SUBCATEGORY_KEYS, TAXONOMY_VERSION, normalize_label
except ImportError:  # pragma: no cover - direct script execution
    from common import read_jsonl, source_hash
    from taxonomy import SUBCATEGORY_KEYS, TAXONOMY_VERSION, normalize_label

VALID_STATUSES = {"pending", "labeled", "ambiguous", "needs_adjudication", "exclude"}
VALID_SENTIMENTS = {"positive", "negative", "mixed", "neutral", "uncertain"}


def _error(errors: list[str], sample_id: Any, message: str) -> None:
    errors.append(f"{sample_id}: {message}")


def validate_record(record: dict[str, Any], seen_ids: set[str]) -> list[str]:
    errors: list[str] = []
    sample_id = str(record.get("sample_id") or "")
    if not sample_id:
        _error(errors, sample_id or "<missing>", "missing sample_id")
    elif sample_id in seen_ids:
        _error(errors, sample_id, "duplicate sample_id")
    seen_ids.add(sample_id)
    if not isinstance(record.get("app_id"), int) or record["app_id"] <= 0:
        _error(errors, sample_id, "app_id must be a positive integer")
    text = record.get("source_review_text")
    if not isinstance(text, str) or not text.strip():
        _error(errors, sample_id, "missing source_review_text")
    if record.get("source_review_hash") != source_hash(text or ""):
        _error(errors, sample_id, "source_review_hash does not match source_review_text")
    if record.get("taxonomy_version") != TAXONOMY_VERSION:
        _error(errors, sample_id, "taxonomy_version mismatch")
    if not isinstance(record.get("guideline_version"), str) or not record["guideline_version"]:
        _error(errors, sample_id, "missing guideline_version")
    if record.get("sampling_stratum") not in {"core", "challenge"}:
        _error(errors, sample_id, "sampling_stratum must be core or challenge")
    if record.get("annotation_status") not in VALID_STATUSES:
        _error(errors, sample_id, "invalid annotation_status")

    for label_block_name in ("gold", "annotations"):
        blocks = record.get(label_block_name)
        if blocks is None:
            continue
        if isinstance(blocks, dict):
            blocks = [blocks]
        if not isinstance(blocks, list):
            _error(errors, sample_id, f"{label_block_name} must be an object or list")
            continue
        for block_index, labels in enumerate(blocks):
            if not isinstance(labels, dict):
                _error(errors, sample_id, f"{label_block_name}[{block_index}] must be an object")
                continue
            sentiment = labels.get("sentiment")
            if sentiment is not None and sentiment not in VALID_SENTIMENTS:
                _error(errors, sample_id, f"invalid sentiment: {sentiment}")
            for field in ("subcategories", "issue_labels", "request_labels"):
                values = labels.get(field, [])
                if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                    _error(errors, sample_id, f"{field} must be a string list")
                    continue
                normalized = [normalize_label(item) for item in values]
                if any(item is None or item not in SUBCATEGORY_KEYS for item in normalized):
                    _error(errors, sample_id, f"{field} contains invalid production taxonomy label")
            for presence, field in (("issue_present", "issue_labels"), ("request_present", "request_labels")):
                if labels.get(presence) is False and labels.get(field):
                    _error(errors, sample_id, f"{presence}=false conflicts with non-empty {field}")
                # A user-confirmed taxonomy gap may preserve presence without
                # inventing a production subcategory. The top-level provenance
                # marker is added only by the explicit Gold promotion step.
                if labels.get(presence) is True and field in labels and not labels.get(field) and not record.get("gold_source_taxonomy_gap"):
                    _error(errors, sample_id, f"{presence}=true requires at least one {field}")
            spans = labels.get("evidence_spans", [])
            if not isinstance(spans, list) or any(not isinstance(span, str) for span in spans):
                _error(errors, sample_id, "evidence_spans must be a string list")
            elif any(span not in (text or "") for span in spans):
                _error(errors, sample_id, "evidence span is not an exact source substring")
    if record.get("annotation_status") == "labeled" and not record.get("gold"):
        _error(errors, sample_id, "labeled record must contain gold labels")
    return errors


def validate_records(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for record in records:
        errors.extend(validate_record(record, seen_ids))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate player-voice annotation JSONL")
    parser.add_argument("input")
    args = parser.parse_args()
    errors = validate_records(read_jsonl(args.input))
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"valid": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
