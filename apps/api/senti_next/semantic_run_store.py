"""Persistence services for immutable SemanticRun configuration identity."""
from __future__ import annotations

import json
import math
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from . import db
from .research_contracts import (
    SEMANTIC_CONFIG_VERSION,
    SEMANTIC_RUN_SCHEMA_VERSION,
    canonical_json,
    sha256_json,
    utc_iso,
)
from .taxonomy_v2 import CORE_TAXONOMY_VERSION, core_taxonomy_fingerprint
from .research_run_store import (
    get_job,
    get_population_snapshot,
    get_research_run,
    get_review_snapshot,
    transition_job,
)


_STATUSES = {"QUEUED", "GENERATING", "READY", "FAILED", "PARTIAL", "CANCELLED"}
_TRANSITIONS = {
    "QUEUED": {"QUEUED", "GENERATING", "FAILED", "CANCELLED"},
    "GENERATING": {"GENERATING", "READY", "PARTIAL", "FAILED", "CANCELLED"},
    "READY": {"READY"},
    "PARTIAL": {"PARTIAL"},
    "FAILED": {"FAILED"},
    "CANCELLED": {"CANCELLED"},
}


def canonical_semantic_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable JSON object whose hash identifies semantic behavior."""
    if not isinstance(config, Mapping) or not config:
        raise ValueError("semantic_config_required")
    normalized = dict(config)
    normalized.setdefault("semantic_config_version", SEMANTIC_CONFIG_VERSION)
    normalized.setdefault("semantic_engine_version", "semantic-engine-v2")
    normalized.setdefault("core_taxonomy_version", CORE_TAXONOMY_VERSION)
    normalized.setdefault("core_taxonomy_fingerprint", core_taxonomy_fingerprint())
    normalized.setdefault("embedding_model_version", "local-multilingual-embedding-v1")
    normalized.setdefault("embedding_artifact_hash", "unresolved")
    normalized.setdefault("prototype_versions", {})
    normalized.setdefault("calibration_version", "calibration-v1")
    normalized.setdefault("segmentation_version", "segmentation-v1")
    normalized.setdefault("normalization_version", "normalization-v1")
    normalized.setdefault("assignment_policy_version", "assignment-v1")
    normalized.setdefault("llm_adjudication_policy_version", "adjudication-v1")
    # Round-trip through canonical JSON to make nested values deterministic
    # and reject values that cannot be persisted as configuration identity.
    try:
        return json.loads(canonical_json(normalized))
    except (TypeError, ValueError) as exc:
        raise ValueError("semantic_config_not_json_serializable") from exc


def semantic_config_hash(config: Mapping[str, Any]) -> str:
    return sha256_json(canonical_semantic_config(config))


def semantic_run_id_for(research_run_id: str, config: Mapping[str, Any]) -> str:
    """Return the deterministic target identity for a ResearchRun/config pair."""
    config_hash = semantic_config_hash(config)
    return "sem_" + sha256_json({
        "research_run_id": str(research_run_id),
        "semantic_config_hash": config_hash,
    })[:40]


def _config_text(config: Mapping[str, Any], key: str, default: str = "unspecified") -> str:
    value = config.get(key)
    if value is None or not str(value).strip():
        return default
    return str(value)


def _parse(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return fallback
    return parsed


def _row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "semantic_run_id": str(row["semantic_run_id"]),
        "research_run_id": str(row["research_run_id"]),
        "population_snapshot_id": str(row["population_snapshot_id"]),
        "population_hash": str(row["population_hash"]),
        "semantic_engine_version": str(row["semantic_engine_version"]),
        "core_taxonomy_version": str(row["core_taxonomy_version"]),
        "game_topic_catalog_version": row["game_topic_catalog_version"],
        "archetype_topic_pack_versions": _parse(row["archetype_topic_pack_versions_json"], []),
        "embedding_model_version": str(row["embedding_model_version"]),
        "embedding_artifact_hash": str(row["embedding_artifact_hash"]),
        "prototype_versions": _parse(row["prototype_versions_json"], {}),
        "calibration_version": str(row["calibration_version"]),
        "segmentation_version": str(row["segmentation_version"]),
        "normalization_version": str(row["normalization_version"]),
        "assignment_policy_version": str(row["assignment_policy_version"]),
        "llm_adjudication_policy_version": str(row["llm_adjudication_policy_version"]),
        "semantic_config_json": _parse(row["semantic_config_json"], {}),
        "semantic_config_hash": str(row["semantic_config_hash"]),
        "status": str(row["status"]),
        "eligible_review_count": int(row["eligible_review_count"]),
        "processed_review_count": int(row["processed_review_count"]),
        "semantic_coverage": row["semantic_coverage"],
        "unresolved_review_count": int(row["unresolved_review_count"]),
        "created_by_job_id": row["created_by_job_id"],
        "created_at": utc_iso(row["created_at"]),
        "completed_at": utc_iso(row["completed_at"]) if row["completed_at"] else None,
        "cost_summary": _parse(row["cost_summary_json"], {}),
        "result_ref": row["result_ref"],
        "semantic_run_schema_version": str(row["semantic_run_schema_version"]),
    }


def create_semantic_run(
    *,
    research_run_id: str,
    semantic_config: Mapping[str, Any],
    created_by_job_id: str | None = None,
    semantic_run_id: str | None = None,
    status: str = "QUEUED",
) -> dict[str, Any]:
    """Create or resolve one SemanticRun for an exact ResearchRun/config pair."""
    research_run = get_research_run(research_run_id)
    if not research_run:
        raise KeyError(f"research_run_not_found:{research_run_id}")
    config = canonical_semantic_config(semantic_config)
    config_hash = sha256_json(config)
    run_id = semantic_run_id or semantic_run_id_for(research_run_id, config)
    target_status = str(status).upper()
    if target_status not in _STATUSES:
        raise ValueError("invalid_semantic_run_status")
    now = utc_iso(None)
    with db.get_connection() as conn:
        existing = conn.execute(text("SELECT * FROM semantic_runs WHERE research_run_id=:research_run_id AND semantic_config_hash=:config_hash"), {"research_run_id": research_run_id, "config_hash": config_hash}).mappings().first()
        if existing:
            if str(existing["semantic_run_id"]) != run_id and semantic_run_id:
                raise ValueError("semantic_run_id_conflict")
            return _row(existing)
        values = {
            "semantic_run_id": run_id,
            "research_run_id": research_run_id,
            "population_snapshot_id": research_run["population_snapshot_id"],
            "population_hash": research_run["population_hash"],
            "semantic_engine_version": _config_text(config, "semantic_engine_version", "semantic-engine-v2"),
            "core_taxonomy_version": _config_text(config, "core_taxonomy_version"),
            "game_topic_catalog_version": config.get("game_topic_catalog_version"),
            "archetype_versions": canonical_json(sorted(str(item) for item in (config.get("archetype_topic_pack_versions") or []))),
            "embedding_model_version": _config_text(config, "embedding_model_version"),
            "embedding_artifact_hash": _config_text(config, "embedding_artifact_hash"),
            "prototype_versions": canonical_json(config.get("prototype_versions") or {}),
            "calibration_version": _config_text(config, "calibration_version"),
            "segmentation_version": _config_text(config, "segmentation_version"),
            "normalization_version": _config_text(config, "normalization_version"),
            "assignment_policy_version": _config_text(config, "assignment_policy_version"),
            "llm_adjudication_policy_version": _config_text(config, "llm_adjudication_policy_version"),
            "config_json": canonical_json(config),
            "config_hash": config_hash,
            "status": target_status,
            "job_id": created_by_job_id,
            "created_at": now,
            "schema_version": SEMANTIC_RUN_SCHEMA_VERSION,
        }
        try:
            conn.execute(text("""INSERT INTO semantic_runs
                (semantic_run_id, research_run_id, population_snapshot_id, population_hash,
                 semantic_engine_version, core_taxonomy_version, game_topic_catalog_version,
                 archetype_topic_pack_versions_json, embedding_model_version, embedding_artifact_hash,
                 prototype_versions_json, calibration_version, segmentation_version, normalization_version,
                 assignment_policy_version, llm_adjudication_policy_version, semantic_config_json,
                 semantic_config_hash, status, created_by_job_id, created_at, semantic_run_schema_version)
                VALUES (:semantic_run_id, :research_run_id, :population_snapshot_id, :population_hash,
                 :semantic_engine_version, :core_taxonomy_version, :game_topic_catalog_version,
                 :archetype_versions, :embedding_model_version, :embedding_artifact_hash,
                 :prototype_versions, :calibration_version, :segmentation_version, :normalization_version,
                 :assignment_policy_version, :llm_adjudication_policy_version, :config_json,
                 :config_hash, :status, :job_id, :created_at, :schema_version)"""), values)
        except IntegrityError:
            existing = conn.execute(text("SELECT * FROM semantic_runs WHERE research_run_id=:research_run_id AND semantic_config_hash=:config_hash"), {"research_run_id": research_run_id, "config_hash": config_hash}).mappings().one()
            return _row(existing)
        created = conn.execute(text("SELECT * FROM semantic_runs WHERE semantic_run_id=:semantic_run_id"), {"semantic_run_id": run_id}).mappings().one()
    return _row(created)


def get_semantic_run(semantic_run_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM semantic_runs WHERE semantic_run_id=:semantic_run_id"), {"semantic_run_id": str(semantic_run_id)}).mappings().first()
    return _row(row) if row else None


def list_semantic_runs(research_run_id: str) -> list[dict[str, Any]]:
    with db.get_connection() as conn:
        rows = conn.execute(
            text("SELECT * FROM semantic_runs WHERE research_run_id=:id ORDER BY created_at DESC, semantic_run_id"),
            {"id": str(research_run_id)},
        ).mappings().all()
    return [_row(row) for row in rows]


def transition_semantic_run(
    semantic_run_id: str,
    status: str,
    *,
    eligible_review_count: int | None = None,
    processed_review_count: int | None = None,
    semantic_coverage: float | None = None,
    unresolved_review_count: int | None = None,
    cost_summary: Mapping[str, Any] | None = None,
    result_ref: str | None = None,
) -> dict[str, Any]:
    target = str(status).upper()
    if target not in _STATUSES:
        raise ValueError("invalid_semantic_run_status")
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT status FROM semantic_runs WHERE semantic_run_id=:semantic_run_id"), {"semantic_run_id": str(semantic_run_id)}).mappings().first()
        if not row:
            raise KeyError(f"semantic_run_not_found:{semantic_run_id}")
        current = str(row["status"])
        if target not in _TRANSITIONS[current]:
            raise ValueError(f"invalid_semantic_run_transition:{current}->{target}")
        sets = ["status=:status"]
        params: dict[str, Any] = {"semantic_run_id": str(semantic_run_id), "status": target}
        for name, value in (("eligible_review_count", eligible_review_count), ("processed_review_count", processed_review_count), ("semantic_coverage", semantic_coverage), ("unresolved_review_count", unresolved_review_count)):
            if value is not None:
                sets.append(f"{name}=:{name}")
                params[name] = value
        if cost_summary is not None:
            sets.append("cost_summary_json=:cost_summary_json")
            params["cost_summary_json"] = canonical_json(dict(cost_summary))
        if result_ref is not None:
            sets.append("result_ref=:result_ref")
            params["result_ref"] = str(result_ref)
        if target in {"READY", "FAILED", "PARTIAL", "CANCELLED"}:
            sets.append("completed_at=COALESCE(completed_at, :completed_at)")
            params["completed_at"] = utc_iso(None)
        conn.execute(text(f"UPDATE semantic_runs SET {', '.join(sets)} WHERE semantic_run_id=:semantic_run_id"), params)
    return get_semantic_run(semantic_run_id) or {}


def _semantic_unit_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "semantic_unit_id": str(row["semantic_unit_id"]),
        "semantic_run_id": str(row["semantic_run_id"]),
        "review_snapshot_id": str(row["review_snapshot_id"]),
        "source_content_hash": str(row["source_content_hash"]),
        "start_byte_offset": int(row["start_byte_offset"]),
        "end_byte_offset": int(row["end_byte_offset"]),
        "text_snapshot": str(row["text_snapshot"]),
        "segmentation_version": str(row["segmentation_version"]),
        "semantic_unit_schema_version": str(row["semantic_unit_schema_version"]),
        "created_at": utc_iso(row["created_at"]),
    }


def _semantic_mention_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mention_id": str(row["mention_id"]),
        "semantic_run_id": str(row["semantic_run_id"]),
        "semantic_unit_id": str(row["semantic_unit_id"]),
        "core_topic_id": str(row["core_topic_id"]),
        "secondary_topic_id": row["secondary_topic_id"],
        "signal_type": row["signal_type"],
        "assignment_source": str(row["assignment_source"]),
        "similarity_score": row["similarity_score"],
        "calibrated_confidence": row["calibrated_confidence"],
        "decision_band": str(row["decision_band"]),
        "prototype_version": str(row["prototype_version"]),
        "adjudication_ref": row["adjudication_ref"],
        "semantic_mention_schema_version": str(row["semantic_mention_schema_version"]),
        "created_at": utc_iso(row["created_at"]),
    }


def create_semantic_unit(
    *,
    semantic_run_id: str,
    review_snapshot_id: str,
    start_byte_offset: int,
    end_byte_offset: int,
    segmentation_version: str,
    text_snapshot: str | None = None,
) -> dict[str, Any]:
    """Persist one UTF-8 byte-addressed, immutable semantic evidence unit."""
    semantic_run = get_semantic_run(semantic_run_id)
    if not semantic_run:
        raise KeyError(f"semantic_run_not_found:{semantic_run_id}")
    snapshot = get_review_snapshot(review_snapshot_id)
    if not snapshot:
        raise KeyError(f"review_snapshot_not_found:{review_snapshot_id}")
    try:
        start = int(start_byte_offset)
        end = int(end_byte_offset)
    except (TypeError, ValueError) as exc:
        raise ValueError("semantic_unit_byte_offset_invalid") from exc
    source_bytes = snapshot["content_text"].encode("utf-8")
    if start < 0 or end < start or end > len(source_bytes):
        raise ValueError("semantic_unit_byte_offset_invalid")
    try:
        decoded_text = source_bytes[start:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("semantic_unit_utf8_boundary") from exc
    if text_snapshot is not None and str(text_snapshot) != decoded_text:
        raise ValueError("semantic_unit_text_snapshot_conflict")
    version = str(segmentation_version).strip()
    if not version:
        raise ValueError("segmentation_version_required")
    unit_id = "unit_" + sha256_json({
        "semantic_run_id": str(semantic_run_id),
        "review_snapshot_id": str(review_snapshot_id),
        "source_content_hash": snapshot["content_hash"],
        "start_byte_offset": start,
        "end_byte_offset": end,
        "segmentation_version": version,
    })[:40]
    values = {
        "semantic_unit_id": unit_id,
        "semantic_run_id": str(semantic_run_id),
        "review_snapshot_id": str(review_snapshot_id),
        "source_content_hash": snapshot["content_hash"],
        "start_byte_offset": start,
        "end_byte_offset": end,
        "text_snapshot": decoded_text,
        "segmentation_version": version,
    }
    with db.get_connection() as conn:
        existing = conn.execute(text("SELECT * FROM semantic_units WHERE semantic_unit_id=:id"), {"id": unit_id}).mappings().first()
        if existing:
            if str(existing["text_snapshot"]) != decoded_text:
                raise ValueError("semantic_unit_conflict")
            return _semantic_unit_row(existing)
        try:
            conn.execute(text("""INSERT INTO semantic_units
                (semantic_unit_id, semantic_run_id, review_snapshot_id, source_content_hash,
                 start_byte_offset, end_byte_offset, text_snapshot, segmentation_version)
                VALUES (:semantic_unit_id, :semantic_run_id, :review_snapshot_id, :source_content_hash,
                        :start_byte_offset, :end_byte_offset, :text_snapshot, :segmentation_version)"""), values)
        except IntegrityError:
            existing = conn.execute(text("SELECT * FROM semantic_units WHERE semantic_unit_id=:id"), {"id": unit_id}).mappings().first()
            if existing:
                return _semantic_unit_row(existing)
            raise
        created = conn.execute(text("SELECT * FROM semantic_units WHERE semantic_unit_id=:id"), {"id": unit_id}).mappings().one()
    return _semantic_unit_row(created)


def get_semantic_unit(semantic_unit_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM semantic_units WHERE semantic_unit_id=:id"), {"id": str(semantic_unit_id)}).mappings().first()
    return _semantic_unit_row(row) if row else None


def create_semantic_mention(
    *,
    semantic_run_id: str,
    semantic_unit_id: str,
    core_topic_id: str,
    assignment_source: str,
    decision_band: str,
    prototype_version: str,
    secondary_topic_id: str | None = None,
    signal_type: str | None = None,
    similarity_score: float | None = None,
    calibrated_confidence: float | None = None,
    adjudication_ref: str | None = None,
    mention_id: str | None = None,
) -> dict[str, Any]:
    """Persist one cardinality-safe topic mention for a semantic unit."""
    if not get_semantic_run(semantic_run_id):
        raise KeyError(f"semantic_run_not_found:{semantic_run_id}")
    unit = get_semantic_unit(semantic_unit_id)
    if not unit:
        raise KeyError(f"semantic_unit_not_found:{semantic_unit_id}")
    if unit["semantic_run_id"] != str(semantic_run_id):
        raise ValueError("semantic_mention_run_mismatch")
    core = str(core_topic_id).strip()
    if not core:
        raise ValueError("core_topic_id_required")
    source = str(assignment_source).strip()
    band = str(decision_band).strip()
    prototype = str(prototype_version).strip()
    if not source or not band or not prototype:
        raise ValueError("semantic_mention_required_field")
    if signal_type is not None and signal_type not in {"issue", "request", "praise"}:
        raise ValueError("invalid_signal_type")
    if calibrated_confidence is not None:
        try:
            confidence = float(calibrated_confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_calibrated_confidence") from exc
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("invalid_calibrated_confidence")
    else:
        confidence = None
    if similarity_score is not None:
        try:
            similarity = float(similarity_score)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_similarity_score") from exc
        if not math.isfinite(similarity):
            raise ValueError("invalid_similarity_score")
    else:
        similarity = None
    identity = {
        "semantic_run_id": str(semantic_run_id),
        "semantic_unit_id": str(semantic_unit_id),
        "core_topic_id": core,
        "secondary_topic_id": secondary_topic_id,
        "signal_type": signal_type,
        "assignment_source": source,
        "prototype_version": prototype,
        "adjudication_ref": adjudication_ref,
    }
    resolved_id = str(mention_id) if mention_id else "men_" + sha256_json(identity)[:40]
    values = {
        "mention_id": resolved_id,
        **identity,
        "similarity_score": similarity,
        "calibrated_confidence": confidence,
        "decision_band": band,
    }
    with db.get_connection() as conn:
        existing = conn.execute(text("SELECT * FROM semantic_mentions WHERE mention_id=:id"), {"id": resolved_id}).mappings().first()
        if existing:
            return _semantic_mention_row(existing)
        try:
            conn.execute(text("""INSERT INTO semantic_mentions
                (mention_id, semantic_run_id, semantic_unit_id, core_topic_id, secondary_topic_id,
                 signal_type, assignment_source, similarity_score, calibrated_confidence,
                 decision_band, prototype_version, adjudication_ref)
                VALUES (:mention_id, :semantic_run_id, :semantic_unit_id, :core_topic_id, :secondary_topic_id,
                        :signal_type, :assignment_source, :similarity_score, :calibrated_confidence,
                        :decision_band, :prototype_version, :adjudication_ref)"""), values)
        except IntegrityError:
            existing = conn.execute(text("SELECT * FROM semantic_mentions WHERE mention_id=:id"), {"id": resolved_id}).mappings().first()
            if existing:
                return _semantic_mention_row(existing)
            raise
        created = conn.execute(text("SELECT * FROM semantic_mentions WHERE mention_id=:id"), {"id": resolved_id}).mappings().one()
    return _semantic_mention_row(created)


def get_semantic_mention(mention_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM semantic_mentions WHERE mention_id=:id"), {"id": str(mention_id)}).mappings().first()
    return _semantic_mention_row(row) if row else None


def materialize_semantic_rollups(semantic_run_id: str) -> dict[str, Any]:
    """Materialize review-level unique topic/signal keys from immutable mentions."""
    if not get_semantic_run(semantic_run_id):
        raise KeyError(f"semantic_run_not_found:{semantic_run_id}")
    with db.get_connection() as conn:
        topics = conn.execute(text("""SELECT DISTINCT m.semantic_run_id, u.review_snapshot_id, m.core_topic_id
            FROM semantic_mentions m JOIN semantic_units u ON u.semantic_unit_id=m.semantic_unit_id
            WHERE m.semantic_run_id=:id"""), {"id": str(semantic_run_id)}).mappings().all()
        for item in topics:
            rollup_id = "rt_" + sha256_json(dict(item))[:40]
            conn.execute(text("""INSERT OR IGNORE INTO semantic_review_topic_rollups
                (rollup_id, semantic_run_id, review_snapshot_id, core_topic_id)
                VALUES (:rollup_id, :semantic_run_id, :review_snapshot_id, :core_topic_id)"""), {"rollup_id": rollup_id, **dict(item)})
        signals = conn.execute(text("""SELECT DISTINCT m.semantic_run_id, u.review_snapshot_id, m.core_topic_id, m.signal_type
            FROM semantic_mentions m JOIN semantic_units u ON u.semantic_unit_id=m.semantic_unit_id
            WHERE m.semantic_run_id=:id AND m.signal_type IS NOT NULL"""), {"id": str(semantic_run_id)}).mappings().all()
        for item in signals:
            rollup_id = "rs_" + sha256_json(dict(item))[:40]
            conn.execute(text("""INSERT OR IGNORE INTO semantic_review_signal_rollups
                (rollup_id, semantic_run_id, review_snapshot_id, core_topic_id, signal_type)
                VALUES (:rollup_id, :semantic_run_id, :review_snapshot_id, :core_topic_id, :signal_type)"""), {"rollup_id": rollup_id, **dict(item)})
        return {"topic_rollup_count": len(topics), "signal_rollup_count": len(signals)}


def get_semantic_rollups(semantic_run_id: str) -> dict[str, Any]:
    with db.get_connection() as conn:
        topic_rows = conn.execute(text("""SELECT core_topic_id, COUNT(*) AS review_count
            FROM semantic_review_topic_rollups WHERE semantic_run_id=:id
            GROUP BY core_topic_id ORDER BY core_topic_id"""), {"id": str(semantic_run_id)}).mappings().all()
        signal_rows = conn.execute(text("""SELECT core_topic_id, signal_type, COUNT(*) AS review_count
            FROM semantic_review_signal_rollups WHERE semantic_run_id=:id
            GROUP BY core_topic_id, signal_type ORDER BY core_topic_id, signal_type"""), {"id": str(semantic_run_id)}).mappings().all()
    return {
        "topic_rollup_count": sum(int(row["review_count"]) for row in topic_rows),
        "signal_rollup_count": sum(int(row["review_count"]) for row in signal_rows),
        "topics": [{"core_topic_id": str(row["core_topic_id"]), "review_count": int(row["review_count"])} for row in topic_rows],
        "signals": [{"core_topic_id": str(row["core_topic_id"]), "signal_type": str(row["signal_type"]), "review_count": int(row["review_count"])} for row in signal_rows],
    }


def execute_semantic_run_job(semantic_run_id: str, job_id: str) -> dict[str, Any]:
    """Run the deterministic evidence stage behind a durable semantic Job.

    Provider/model-specific classification can enrich the frozen fixture
    payload through ``fixture_mentions``.  Reviews without an explicit
    assignment remain unresolved and therefore produce a truthful PARTIAL
    SemanticRun instead of an invented topic.
    """
    semantic_run = get_semantic_run(semantic_run_id)
    job = get_job(job_id)
    if not semantic_run:
        raise KeyError(f"semantic_run_not_found:{semantic_run_id}")
    if not job:
        raise KeyError(f"job_not_found:{job_id}")
    if job["status"] != "QUEUED":
        return semantic_run
    population = get_population_snapshot(semantic_run["population_snapshot_id"])
    if population is None:
        transition_job(job_id, "FAILED", stage="failed", error_code="population_not_found")
        return transition_semantic_run(semantic_run_id, "FAILED", result_ref=f"semantic_results:{semantic_run_id}")
    reviews = list(population.get("reviews") or [])
    eligible = [review for review in reviews if str(review.get("content_text") or "").strip()]
    transition_job(job_id, "RUNNING", stage="segmenting", progress_total=len(eligible))
    transition_semantic_run(semantic_run_id, "GENERATING", eligible_review_count=len(eligible))
    config = semantic_run.get("semantic_config_json") or {}
    fixture_mentions = config.get("fixture_mentions") or {}
    unresolved = 0
    processed = 0
    try:
        for review in eligible:
            current_job = get_job(job_id) or {}
            if current_job.get("cancel_requested_at") or current_job.get("status") == "CANCELLED":
                transition_semantic_run(semantic_run_id, "CANCELLED", processed_review_count=processed, unresolved_review_count=unresolved)
                if current_job.get("status") != "CANCELLED":
                    transition_job(job_id, "CANCELLED", stage="cancelled")
                return get_semantic_run(semantic_run_id) or {}
            content = str(review["content_text"])
            unit = create_semantic_unit(
                semantic_run_id=semantic_run_id,
                review_snapshot_id=review["review_snapshot_id"],
                start_byte_offset=0,
                end_byte_offset=len(content.encode("utf-8")),
                segmentation_version=semantic_run["segmentation_version"],
                text_snapshot=content,
            )
            assignment = fixture_mentions.get(str(review.get("steam_review_id"))) or review.get("payload", {}).get("semantic_mention") or {}
            core_topic_id = str(assignment.get("core_topic_id") or "").strip()
            if core_topic_id:
                prototype_version = str(assignment.get("prototype_version") or semantic_run["embedding_model_version"])
                create_semantic_mention(
                    semantic_run_id=semantic_run_id,
                    semantic_unit_id=unit["semantic_unit_id"],
                    core_topic_id=core_topic_id,
                    secondary_topic_id=assignment.get("secondary_topic_id"),
                    signal_type=assignment.get("signal_type"),
                    assignment_source=str(assignment.get("assignment_source") or "fixture"),
                    similarity_score=assignment.get("similarity_score"),
                    calibrated_confidence=assignment.get("calibrated_confidence"),
                    decision_band=str(assignment.get("decision_band") or "assigned"),
                    prototype_version=prototype_version,
                    adjudication_ref=assignment.get("adjudication_ref"),
                )
            else:
                unresolved += 1
            processed += 1
            transition_job(job_id, "RUNNING", stage="segmenting", progress_current=processed, progress_total=len(eligible))
            transition_semantic_run(
                semantic_run_id,
                "GENERATING",
                processed_review_count=processed,
                unresolved_review_count=unresolved,
                semantic_coverage=(processed / len(eligible)) if eligible else 1.0,
            )
        materialized_rollups = materialize_semantic_rollups(semantic_run_id)
        final_status = "PARTIAL" if unresolved or processed != len(eligible) else "READY"
        result = transition_semantic_run(
            semantic_run_id,
            final_status,
            processed_review_count=processed,
            unresolved_review_count=unresolved,
            semantic_coverage=(processed / len(eligible)) if eligible else 1.0,
            result_ref=f"semantic_results:{semantic_run_id}",
        )
        result["rollups"] = materialized_rollups
        transition_job(job_id, "PARTIAL" if final_status == "PARTIAL" else "SUCCEEDED", stage="completed", progress_current=processed, progress_total=len(eligible))
        return result
    except Exception as exc:
        try:
            transition_job(job_id, "FAILED", stage="failed", error_code="semantic_generation_failed", error_detail=str(exc))
            transition_semantic_run(semantic_run_id, "FAILED", processed_review_count=processed, unresolved_review_count=unresolved, result_ref=f"semantic_results:{semantic_run_id}")
        except Exception:
            pass
        raise


__all__ = [
    "canonical_semantic_config", "create_semantic_mention", "create_semantic_run", "create_semantic_unit",
    "execute_semantic_run_job", "get_semantic_mention", "get_semantic_rollups", "get_semantic_run", "get_semantic_unit",
    "materialize_semantic_rollups",
    "list_semantic_runs", "semantic_config_hash", "semantic_run_id_for", "transition_semantic_run",
]
