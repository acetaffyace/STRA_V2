"""Run Stage 3C region interpretation for a completed Stage 3B materialization."""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from apps.api.senti_next.semantic_region_interpretation import build_semantic_region_interpretation
from apps.api.senti_next.semantic_region_interpretation_schema import SemanticRegionInterpretationContract
from apps.api.senti_next.providers import get_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Interpret bounded semantic discovery regions")
    parser.add_argument("--materialization-id", required=True)
    parser.add_argument("--provider", help="configured provider name; omit for evidence-only dry run")
    parser.add_argument("--max-llm-calls", type=int, default=25)
    parser.add_argument("--region-id", action="append", default=[])
    parser.add_argument("--dry-run-evidence", action="store_true")
    args = parser.parse_args()
    provider = None
    if args.provider and not args.dry_run_evidence:
        provider = get_provider(name=args.provider)
    report = build_semantic_region_interpretation(
        args.materialization_id,
        provider=provider,
        contract=SemanticRegionInterpretationContract(max_llm_calls=args.max_llm_calls),
        region_ids=args.region_id or None,
        dry_run_evidence=args.dry_run_evidence,
    )
    print(json.dumps({
        "schema_version": report.get("schema_version"),
        "materialization_id": report.get("materialization_id"),
        "status": report.get("status"),
        "region_n": report.get("region_n"),
        "eligible_llm_region_n": report.get("eligible_llm_region_n"),
        "actual_llm_call_n": report.get("actual_llm_call_n"),
        "candidate_n": report.get("candidate_n"),
        "deferred_n": report.get("deferred_n"),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
