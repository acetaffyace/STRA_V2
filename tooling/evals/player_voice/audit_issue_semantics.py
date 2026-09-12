"""Audit positive Gold issue labels against the production issue contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import read_jsonl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default="tooling/evals/gold/P0_5B_gold_verified.jsonl")
    parser.add_argument("--output", default="tooling/evals/reports/P0_5CV_ISSUE_SEMANTIC_AUDIT.json")
    args = parser.parse_args()
    records = read_jsonl(args.gold)
    candidates = []
    for record in records:
        gold = record.get("gold") or {}
        if gold.get("issue_present") is not True or gold.get("sentiment") != "positive":
            continue
        candidates.append({
            "sample_id": record["sample_id"],
            "source_review": record.get("source_review_text", ""),
            "sentiment": gold.get("sentiment"),
            "current_issue_present": gold.get("issue_present"),
            "current_issue_labels": gold.get("issue_labels", []),
            "evidence_spans": gold.get("evidence_spans", []),
            "reason_flagged": "positive Gold sentiment with issue_present=true; requires checking whether the text states a problem or only mentions/praises an aspect",
            "recommended_interpretation": "likely aspect mention with issue_present=false unless the human-confirmed reading identifies an explicit problem or complaint",
            "requires_human_review": True,
        })
    result = {
        "audit_version": "p0.5cv-issue-semantics-v1",
        "gold_file": args.gold,
        "gold_record_count": len(records),
        "issue_present_true_count": sum((r.get("gold") or {}).get("issue_present") is True for r in records),
        "positive_issue_candidate_count": len(candidates),
        "production_contract_summary": {
            "subcategories": "all taxonomy-relevant topics/aspects",
            "issue_subcategories": "only problems/complaints and a subset of subcategories",
            "request_subcategories": "only explicit requests and a subset of subcategories",
            "issue_rate": "count of classified records with non-empty issue_subcategories divided by validated classified records",
        },
        "candidates": candidates,
        "requires_human_gold_revision": True,
        "gold_mutated": False,
        "prediction_artifacts_mutated": False,
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"issue_true": result["issue_present_true_count"], "positive_candidates": len(candidates), "gold_mutated": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
