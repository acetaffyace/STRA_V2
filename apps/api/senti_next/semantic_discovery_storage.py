"""Read-only semantic-index loading and independent Stage 3B persistence."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional, Sequence

import numpy as np
from sqlalchemy import text

from . import db
from .semantic_discovery import (
    DISCOVERY_ALGORITHM_VERSION,
    SemanticDiscoveryContract,
    SemanticUnitRecord,
    build_semantic_discovery,
)
from .semantic_index_storage import load_semantic_index


def load_semantic_index_unit_records(index_id: str) -> tuple[list[SemanticUnitRecord], dict[str, Any]]:
    """Load vectors without changing any Stage 3A row."""
    with db.get_connection() as conn:
        run = conn.execute(text("SELECT * FROM semantic_index_runs WHERE index_id = :index_id"), {"index_id": index_id}).mappings().first()
        if not run:
            raise ValueError(f"semantic index not found: {index_id}")
        if run["status"] != "completed":
            raise ValueError("semantic index is not complete")
        rows = conn.execute(
            text(
                "SELECT u.review_id, u.unit_index, u.semantic_text_hash, u.semantic_text, "
                "u.embedding_key, c.vector_blob, c.dimensions "
                "FROM semantic_index_units u "
                "JOIN semantic_embedding_cache c ON c.embedding_key = u.embedding_key "
                "WHERE u.index_id = :index_id ORDER BY u.review_id, u.unit_index"
            ),
            {"index_id": index_id},
        ).mappings().all()
    units = []
    for row in rows:
        vector = np.frombuffer(row["vector_blob"], dtype=np.float32).copy()
        if vector.shape != (int(row["dimensions"]),):
            raise ValueError("semantic index vector dimensions are invalid")
        units.append(
            SemanticUnitRecord(
                unit_id=f"{row['review_id']}:{row['unit_index']}",
                review_id=str(row["review_id"]),
                unit_index=int(row["unit_index"]),
                vector=vector,
                semantic_text_hash=str(row["semantic_text_hash"]),
                semantic_text=str(row["semantic_text"]),
            )
        )
    return units, dict(run)


def _discovery_run_id(semantic_index_id: str, contract: SemanticDiscoveryContract) -> str:
    return hashlib.sha256(f"{semantic_index_id}:{contract.fingerprint}".encode()).hexdigest()


def persist_semantic_discovery(report: Mapping[str, Any], *, discovery_run_id: str | None = None) -> str:
    """Persist a completed discovery report under its exact index identity."""
    index_id = str(report["semantic_index_id"])
    index = load_semantic_index(index_id)
    if not index or index["run"]["status"] != "completed":
        raise ValueError("discovery requires a completed semantic index")
    if str(index["run"]["population_fingerprint"]) != str(report["population_fingerprint"]):
        raise ValueError("semantic index population fingerprint mismatch")
    if str(index["run"]["index_fingerprint"]) != str(report["semantic_index_fingerprint"]):
        raise ValueError("semantic index fingerprint mismatch")
    persisted_contract = report["contract"]
    contract_values = {
        key: persisted_contract[key]
        for key in SemanticDiscoveryContract.__dataclass_fields__
        if key in persisted_contract
    }
    if "requested_min_cluster_size" in persisted_contract:
        contract_values["min_cluster_size"] = persisted_contract["requested_min_cluster_size"]
    contract = SemanticDiscoveryContract(**contract_values)
    # The persisted report includes effective values; use its contract identity
    # while keeping requested/effective parameters in the JSON report itself.
    contract.validate()
    run_id = discovery_run_id or _discovery_run_id(index_id, contract)
    report_json = json.dumps(dict(report), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    with db.get_connection() as conn:
        existing = conn.execute(text("SELECT status, discovery_fingerprint FROM semantic_discovery_runs WHERE discovery_run_id = :run_id"), {"run_id": run_id}).mappings().first()
        if existing and existing["status"] == "completed" and existing["discovery_fingerprint"] == report.get("discovery_fingerprint"):
            return run_id
        if existing:
            conn.execute(text("DELETE FROM semantic_discovery_runs WHERE discovery_run_id = :run_id"), {"run_id": run_id})
        conn.execute(
            text(
                "INSERT INTO semantic_discovery_runs "
                "(discovery_run_id, semantic_index_id, research_run_id, population_fingerprint, semantic_index_fingerprint, "
                "discovery_contract_json, algorithm_version, population_n, indexed_review_n, semantic_unit_n, dense_region_n, "
                "rare_region_n, outlier_review_n, unclustered_review_share, status, discovery_fingerprint, report_json, completed_at) "
                "VALUES (:run_id, :index_id, :research_run_id, :population_fingerprint, :index_fingerprint, :contract_json, :algorithm, "
                ":population_n, :indexed_review_n, :semantic_unit_n, :dense_region_n, :rare_region_n, :outlier_review_n, :unclustered_share, "
                "'completed', :discovery_fingerprint, :report_json, datetime('now'))"
            ),
            {
                "run_id": run_id,
                "index_id": index_id,
                "research_run_id": report["research_run_id"],
                "population_fingerprint": report["population_fingerprint"],
                "index_fingerprint": report["semantic_index_fingerprint"],
                "contract_json": json.dumps(report["contract"], sort_keys=True, separators=(",", ":")),
                "algorithm": DISCOVERY_ALGORITHM_VERSION,
                "population_n": report["population_n"],
                "indexed_review_n": report["indexed_review_n"],
                "semantic_unit_n": report["semantic_unit_n"],
                "dense_region_n": report["dense_region_n"],
                "rare_region_n": report["rare_region_n"],
                "outlier_review_n": report["outlier_review_n"],
                "unclustered_share": report["unclustered_review_share"],
                "discovery_fingerprint": report.get("discovery_fingerprint"),
                "report_json": report_json,
            },
        )
        for region in report["regions"]:
            conn.execute(
                text(
                    "INSERT INTO semantic_discovery_regions "
                    "(discovery_run_id, region_id, discovery_type, support_review_n, support_unit_n, unique_text_n, cohesion, "
                    "stability_score, stability, taxonomy_coverage_status, region_json) "
                    "VALUES (:run_id, :region_id, :discovery_type, :support_review_n, :support_unit_n, :unique_text_n, :cohesion, "
                    ":stability_score, :stability, :taxonomy_status, :region_json)"
                ),
                {
                    "run_id": run_id,
                    "region_id": region["region_id"],
                    "discovery_type": region["discovery_type"],
                    "support_review_n": region["support_reviews"],
                    "support_unit_n": region["support_units"],
                    "unique_text_n": region.get("unique_text_n") or 0,
                    "cohesion": region.get("cohesion"),
                    "stability_score": region.get("stability_score"),
                    "stability": region.get("stability", "unstable"),
                    "taxonomy_status": region.get("taxonomy_coverage_status", "unavailable"),
                    "region_json": json.dumps(region, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False),
                },
            )
            representatives = set(region.get("representative_review_ids") or [])
            strengths = region.get("membership_strength") or {}
            for review_id in region.get("review_ids") or []:
                role = "representative" if review_id in representatives else ("outlier" if region["discovery_type"] == "outlier" else "core")
                unit_ids = [
                    unit_id
                    for unit_id in (region.get("semantic_unit_ids") or [])
                    if unit_id == f"{review_id}:0" or unit_id.startswith(f"{review_id}:")
                ] or [None]
                for unit_id in unit_ids:
                    conn.execute(
                        text(
                            "INSERT INTO semantic_discovery_members "
                            "(discovery_run_id, region_id, review_id, semantic_unit_id, membership_strength, distance_similarity, role) "
                            "VALUES (:run_id, :region_id, :review_id, :unit_id, :strength, NULL, :role)"
                        ),
                        {"run_id": run_id, "region_id": region["region_id"], "review_id": review_id, "unit_id": unit_id, "strength": strengths.get(review_id), "role": role},
                    )
            audit = region.get("taxonomy_audit") or {}
            if audit:
                conn.execute(
                    text(
                        "INSERT INTO taxonomy_audit_regions "
                        "(discovery_run_id, region_id, coverage_status, support_review_n, labeled_review_n, unlabeled_review_n, taxonomy_coverage_rate, audit_json) "
                        "VALUES (:run_id, :region_id, :status, :support, :labeled, :unlabeled, :coverage, :audit_json)"
                    ),
                    {
                        "run_id": run_id,
                        "region_id": region["region_id"],
                        "status": audit.get("coverage_status", "unavailable"),
                        "support": audit.get("support_reviews", region["support_reviews"]),
                        "labeled": audit.get("labeled_review_n", 0),
                        "unlabeled": audit.get("unlabeled_review_n", region["support_reviews"]),
                        "coverage": audit.get("taxonomy_coverage_rate"),
                        "audit_json": json.dumps(audit, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False),
                    },
                )
    return run_id


def _persist_failed_discovery(
    *,
    index_run: Mapping[str, Any],
    contract: SemanticDiscoveryContract,
    error: str,
    discovery_run_id: str,
) -> None:
    """Record a failed discovery attempt without creating a completed report."""
    with db.get_connection() as conn:
        conn.execute(
            text("DELETE FROM semantic_discovery_runs WHERE discovery_run_id = :run_id"),
            {"run_id": discovery_run_id},
        )
        conn.execute(
            text(
                "INSERT INTO semantic_discovery_runs "
                "(discovery_run_id, semantic_index_id, research_run_id, population_fingerprint, semantic_index_fingerprint, "
                "discovery_contract_json, algorithm_version, population_n, indexed_review_n, semantic_unit_n, status, error) "
                "VALUES (:run_id, :index_id, :research_run_id, :population_fingerprint, :index_fingerprint, :contract_json, "
                ":algorithm, :population_n, :indexed_review_n, :semantic_unit_n, 'failed', :error)"
            ),
            {
                "run_id": discovery_run_id,
                "index_id": index_run["index_id"],
                "research_run_id": index_run["research_run_id"],
                "population_fingerprint": index_run["population_fingerprint"],
                "index_fingerprint": index_run["index_fingerprint"],
                "contract_json": json.dumps(contract.to_dict(population_n=int(index_run["indexed_review_n"])), sort_keys=True, separators=(",", ":")),
                "algorithm": DISCOVERY_ALGORITHM_VERSION,
                "population_n": int(index_run["population_n"]),
                "indexed_review_n": int(index_run["indexed_review_n"]),
                "semantic_unit_n": int(index_run["semantic_unit_n"]),
                "error": error[:2000],
            },
        )


def load_semantic_discovery(discovery_run_id: str) -> Optional[dict[str, Any]]:
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT report_json FROM semantic_discovery_runs WHERE discovery_run_id = :run_id"), {"run_id": discovery_run_id}).scalar()
    return json.loads(row) if row else None


def build_semantic_discovery_for_index(
    semantic_index_id: str,
    *,
    contract: SemanticDiscoveryContract | None = None,
    expected_population_fingerprint: str | None = None,
    expected_semantic_index_fingerprint: str | None = None,
    review_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    taxonomy_labels: Mapping[str, Any] | None = None,
    stage2e: Mapping[str, Any] | None = None,
    backend=None,
) -> dict[str, Any]:
    active_contract = contract or SemanticDiscoveryContract()
    active_contract.validate()
    run_id = _discovery_run_id(semantic_index_id, active_contract)
    units, index_run = load_semantic_index_unit_records(semantic_index_id)
    if expected_population_fingerprint and expected_population_fingerprint != index_run["population_fingerprint"]:
        raise ValueError("requested population fingerprint does not match semantic index")
    if expected_semantic_index_fingerprint and expected_semantic_index_fingerprint != index_run["index_fingerprint"]:
        raise ValueError("requested semantic index fingerprint does not match semantic index")
    with db.get_connection() as conn:
        existing = conn.execute(
            text("SELECT status, report_json FROM semantic_discovery_runs WHERE discovery_run_id = :run_id"),
            {"run_id": run_id},
        ).mappings().first()
    if existing and existing["status"] == "completed" and existing["report_json"]:
        return json.loads(existing["report_json"])
    index = load_semantic_index(semantic_index_id)
    metadata = dict(review_metadata or {})
    if index:
        for member in index["members"]:
            metadata.setdefault(member["review_id"], {"semantic_text_hash": member.get("review_text_hash")})
    try:
        return build_semantic_discovery(
            units,
            semantic_index_id=semantic_index_id,
            research_run_id=str(index_run["research_run_id"]),
            population_fingerprint=str(index_run["population_fingerprint"]),
            semantic_index_fingerprint=str(index_run["index_fingerprint"]),
            contract=active_contract,
            review_metadata=metadata,
            taxonomy_labels=taxonomy_labels,
            stage2e=stage2e,
            backend=backend,
            population_n_override=int(index_run["population_n"]),
        )
    except Exception as exc:
        _persist_failed_discovery(
            index_run=index_run,
            contract=active_contract,
            error=str(exc),
            discovery_run_id=run_id,
        )
        raise
