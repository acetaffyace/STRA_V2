"""Promote a user-verified external annotation file into the full Gold schema."""
from __future__ import annotations

import argparse
import json

from .common import read_jsonl, write_jsonl
from .taxonomy import TAXONOMY_VERSION


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--batch", default="tooling/evals/drafts/P0_5B_annotation_batch.jsonl")
    parser.add_argument("--output", default="tooling/evals/gold/P0_5B_gold_verified.jsonl")
    parser.add_argument("--annotator-id", default="user-verified")
    args = parser.parse_args()
    base = {item["sample_id"]: item for item in read_jsonl(args.batch)}
    output = []
    for item in read_jsonl(args.source):
        record = dict(base[item["sample_id"]])
        if record["source_review_text"] != item["source_review_text"] or record["app_id"] != item["app_id"]:
            raise ValueError(f"source mismatch for {item['sample_id']}")
        gold = dict(item["gold"])
        gold.setdefault("subcategories", list(dict.fromkeys(gold.get("issue_labels", []) + gold.get("request_labels", []))))
        record["gold"] = gold
        record["annotations"] = []
        record["annotation_status"] = "labeled"
        record["annotator_id"] = args.annotator_id
        record["adjudication_status"] = "adjudicated"
        record["annotation_notes"] = (
            f"User-verified from supplied P0_5B_gold_only.jsonl. Original reviewer_type="
            f"{item.get('reviewer_type')}; reviewer_model={item.get('reviewer_model')}; "
            f"confidence={item.get('confidence')}; taxonomy_gap={item.get('taxonomy_gap')}. "
            f"{item.get('annotation_notes', '')}"
        ).strip()
        record["gold_provenance"] = "user_verified_external_annotation"
        record["gold_source_reviewer_type"] = item.get("reviewer_type")
        record["gold_source_reviewer_model"] = item.get("reviewer_model")
        record["gold_source_confidence"] = item.get("confidence")
        record["gold_source_taxonomy_gap"] = item.get("taxonomy_gap")
        output.append(record)
    if len(output) != len(base):
        raise ValueError(f"source has {len(output)} records but batch has {len(base)}")
    write_jsonl(args.output, output)
    print(json.dumps({"records": len(output), "taxonomy_version": TAXONOMY_VERSION, "status": "labeled", "annotator_id": args.annotator_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
