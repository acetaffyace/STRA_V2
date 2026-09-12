"""Import an externally supplied model-review file as a visible, non-gold draft."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import read_jsonl, write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--batch", default="tooling/evals/drafts/P0_5B_annotation_batch.jsonl")
    parser.add_argument("--output", default="tooling/evals/drafts/P0_5B_external_model_draft.jsonl")
    args = parser.parse_args()
    batch = {item["sample_id"]: item for item in read_jsonl(args.batch)}
    output = []
    for item in read_jsonl(args.source):
        base = batch.get(item["sample_id"])
        if not base or base["source_review_text"] != item["source_review_text"] or base["app_id"] != item["app_id"]:
            raise ValueError(f"source mismatch for {item['sample_id']}")
        gold = item.get("gold") or {}
        reasons = []
        if item.get("confidence") != "high":
            reasons.append(f"外部模型置信度：{item.get('confidence')}")
        if item.get("taxonomy_gap"):
            reasons.append("外部模型标记 taxonomy_gap")
        output.append({
            "sample_id": item["sample_id"],
            "codex_draft": gold,
            "uncertain": bool(reasons),
            "uncertain_reasons": reasons,
            "draft_note": f"外部文件 reviewer_type={item.get('reviewer_type')}, reviewer_model={item.get('reviewer_model')}; 仅供人工核验，不是 Gold。",
            "external_annotation_notes": item.get("annotation_notes", ""),
        })
    write_jsonl(args.output, output)
    print(json.dumps({"records": len(output), "uncertain": sum(x["uncertain"] for x in output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
