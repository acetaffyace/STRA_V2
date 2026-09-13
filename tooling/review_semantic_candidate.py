"""Append a human review decision for a Stage 3C candidate."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from apps.api.senti_next.semantic_region_interpretation import record_semantic_taxonomy_candidate_decision


def main() -> int:
    parser = argparse.ArgumentParser(description="Record an append-only Stage 3C candidate decision")
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--decision", required=True, choices=("approve", "reject", "defer", "request_revision"))
    parser.add_argument("--target-existing-label", action="append", default=[])
    parser.add_argument("--note", default="")
    parser.add_argument("--reviewer", default="")
    args = parser.parse_args()
    decision_id = record_semantic_taxonomy_candidate_decision(args.candidate_id, args.decision, target_existing_labels=args.target_existing_label, review_note=args.note, reviewer=args.reviewer)
    print(decision_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
