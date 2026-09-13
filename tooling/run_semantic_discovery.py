"""Run Stage 3B open-set discovery against a completed Stage 3A index."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from sqlalchemy import text  # noqa: E402

from senti_next import db  # noqa: E402
from senti_next.semantic_discovery import SemanticDiscoveryContract  # noqa: E402
from senti_next.semantic_discovery_storage import (  # noqa: E402
    build_semantic_discovery_for_index,
    persist_semantic_discovery,
)


def _resolve_index(run_id: str) -> str:
    with db.get_connection() as conn:
        value = conn.execute(
            text(
                "SELECT index_id FROM semantic_index_runs "
                "WHERE research_run_id = :run_id AND status = 'completed' "
                "ORDER BY completed_at DESC LIMIT 1"
            ),
            {"run_id": run_id},
        ).scalar()
    if not value:
        raise ValueError(f"no completed semantic index found for research run: {run_id}")
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--index-id")
    group.add_argument("--run-id")
    parser.add_argument("--min-cluster-size", type=int, default=None)
    parser.add_argument("--min-samples", type=int, default=None)
    parser.add_argument("--neighbor-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    db.init_db()
    index_id = args.index_id or _resolve_index(args.run_id)
    contract = SemanticDiscoveryContract(
        min_cluster_size=args.min_cluster_size,
        min_samples=args.min_samples,
        neighbor_k=args.neighbor_k,
    )
    report = build_semantic_discovery_for_index(index_id, contract=contract)
    discovery_run_id = persist_semantic_discovery(report)
    payload = {
        "discovery_run_id": discovery_run_id,
        "semantic_index_id": index_id,
        "population_n": report["population_n"],
        "indexed_review_n": report["indexed_review_n"],
        "semantic_unit_n": report["semantic_unit_n"],
        "dense_region_n": report["dense_region_n"],
        "rare_region_n": report["rare_region_n"],
        "outlier_review_n": report["outlier_review_n"],
        "unclustered_review_share": report["unclustered_review_share"],
        "stability_distribution": report["stability_distribution"],
        "taxonomy_audit": report["taxonomy_audit"],
        "discovery_fingerprint": report["discovery_fingerprint"],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    print(serialized)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
