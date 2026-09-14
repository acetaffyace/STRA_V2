"""Persistence and explicit governance for semantic discovery candidates."""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from sqlalchemy import text

from . import db
from .research_contracts import canonical_json, sha256_json, utc_iso


def _json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return fallback


def _row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": str(row["candidate_id"]), "semantic_run_id": str(row["semantic_run_id"]), "cluster_id": str(row["cluster_id"]),
        "provisional_name": str(row["provisional_name"]), "provisional_definition": str(row["provisional_definition"]), "cluster_size": int(row["cluster_size"]),
        "nearest_known_topics": _json(row["nearest_known_topics_json"], []), "representative_unit_ids": _json(row["representative_unit_ids_json"], []),
        "segment_distribution": _json(row["segment_distribution_json"], {}), "time_distribution": _json(row["time_distribution_json"], {}),
        "recommendation_distribution": _json(row["recommendation_distribution_json"], {}), "llm_recommendation": _json(row["llm_recommendation_json"], None),
        "promotion_target": str(row["promotion_target"]), "status": str(row["status"]), "reviewed_at": utc_iso(row["reviewed_at"]) if row["reviewed_at"] else None,
        "accepted_topic_id": row["accepted_topic_id"], "created_at": utc_iso(row["created_at"]), "emerging_topic_schema_version": str(row["emerging_topic_schema_version"]),
    }


def create_emerging_topic_candidate(*, semantic_run_id: str, cluster_id: str, provisional_name: str, provisional_definition: str, cluster_size: int, nearest_known_topics: Sequence[str] = (), representative_unit_ids: Sequence[str] = (), segment_distribution: Mapping[str, Any] | None = None, time_distribution: Mapping[str, Any] | None = None, recommendation_distribution: Mapping[str, Any] | None = None, promotion_target: str = "none", llm_recommendation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not str(provisional_name).strip() or not str(provisional_definition).strip():
        raise ValueError("emerging_topic_definition_incomplete")
    if int(cluster_size) < 0:
        raise ValueError("emerging_topic_cluster_size_invalid")
    target = str(promotion_target)
    if target not in {"game", "archetype", "refine_existing", "none"}:
        raise ValueError("emerging_topic_promotion_target_invalid")
    identity = {"semantic_run_id": str(semantic_run_id), "cluster_id": str(cluster_id), "provisional_name": str(provisional_name).strip(), "provisional_definition": str(provisional_definition).strip(), "cluster_size": int(cluster_size), "nearest_known_topics": sorted(str(item) for item in nearest_known_topics), "representative_unit_ids": sorted(str(item) for item in representative_unit_ids), "segment_distribution": dict(segment_distribution or {}), "time_distribution": dict(time_distribution or {}), "recommendation_distribution": dict(recommendation_distribution or {}), "promotion_target": target}
    candidate_id = "candidate_" + sha256_json(identity)[:40]
    with db.get_connection() as conn:
        if not conn.execute(text("SELECT semantic_run_id FROM semantic_runs WHERE semantic_run_id=:id"), {"id": semantic_run_id}).scalar():
            raise KeyError(f"semantic_run_not_found:{semantic_run_id}")
        existing = conn.execute(text("SELECT * FROM emerging_topic_candidates WHERE candidate_id=:id"), {"id": candidate_id}).mappings().first()
        if existing:
            return _row(existing)
        conn.execute(text("""INSERT INTO emerging_topic_candidates
            (candidate_id, semantic_run_id, cluster_id, provisional_name, provisional_definition, cluster_size,
             nearest_known_topics_json, representative_unit_ids_json, segment_distribution_json, time_distribution_json,
             recommendation_distribution_json, llm_recommendation_json, promotion_target)
            VALUES (:candidate_id, :semantic_run_id, :cluster_id, :provisional_name, :provisional_definition, :cluster_size,
                    :nearest_known_topics, :representative_unit_ids, :segment_distribution, :time_distribution,
                    :recommendation_distribution, :llm_recommendation, :promotion_target)"""), {"candidate_id": candidate_id, "semantic_run_id": semantic_run_id, "cluster_id": cluster_id, "provisional_name": identity["provisional_name"], "provisional_definition": identity["provisional_definition"], "cluster_size": identity["cluster_size"], "nearest_known_topics": canonical_json(identity["nearest_known_topics"]), "representative_unit_ids": canonical_json(identity["representative_unit_ids"]), "segment_distribution": canonical_json(identity["segment_distribution"]), "time_distribution": canonical_json(identity["time_distribution"]), "recommendation_distribution": canonical_json(identity["recommendation_distribution"]), "llm_recommendation": canonical_json(dict(llm_recommendation)) if llm_recommendation is not None else None, "promotion_target": target})
        return _row(conn.execute(text("SELECT * FROM emerging_topic_candidates WHERE candidate_id=:id"), {"id": candidate_id}).mappings().one())


def get_emerging_topic_candidate(candidate_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM emerging_topic_candidates WHERE candidate_id=:id"), {"id": str(candidate_id)}).mappings().first()
    return _row(row) if row else None


def transition_emerging_topic_candidate(candidate_id: str, status: str, *, accepted_topic_id: str | None = None, llm_recommendation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    target = str(status).upper()
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT status FROM emerging_topic_candidates WHERE candidate_id=:id"), {"id": str(candidate_id)}).mappings().first()
        if not row:
            raise KeyError(f"emerging_topic_not_found:{candidate_id}")
        current = str(row["status"])
        allowed = {"DETECTED": {"DETECTED", "REVIEWED", "PENDING", "REJECTED", "DEFERRED"}, "REVIEWED": {"REVIEWED", "PENDING", "ACCEPTED", "MERGED", "REJECTED", "DEFERRED"}, "PENDING": {"PENDING", "ACCEPTED", "MERGED", "REJECTED", "DEFERRED"}, "ACCEPTED": {"ACCEPTED"}, "MERGED": {"MERGED"}, "REJECTED": {"REJECTED"}, "DEFERRED": {"DEFERRED"}}
        if target not in allowed[current]:
            raise ValueError(f"invalid_emerging_topic_transition:{current}->{target}")
        if target == "ACCEPTED" and not str(accepted_topic_id or "").strip():
            raise ValueError("accepted_topic_id_required")
        conn.execute(text("UPDATE emerging_topic_candidates SET status=:status, reviewed_at=CASE WHEN :status IN ('REVIEWED','PENDING','ACCEPTED','MERGED','REJECTED','DEFERRED') THEN COALESCE(reviewed_at,:now) ELSE reviewed_at END, accepted_topic_id=COALESCE(:accepted_topic_id, accepted_topic_id), llm_recommendation_json=COALESCE(:llm_recommendation, llm_recommendation_json) WHERE candidate_id=:id"), {"status": target, "accepted_topic_id": accepted_topic_id, "llm_recommendation": canonical_json(dict(llm_recommendation)) if llm_recommendation is not None else None, "now": utc_iso(None), "id": str(candidate_id)})
        return _row(conn.execute(text("SELECT * FROM emerging_topic_candidates WHERE candidate_id=:id"), {"id": str(candidate_id)}).mappings().one())


__all__ = ["create_emerging_topic_candidate", "get_emerging_topic_candidate", "transition_emerging_topic_candidate"]
