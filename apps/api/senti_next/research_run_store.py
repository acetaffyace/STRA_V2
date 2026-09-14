"""Persistence services for the canonical M0 ResearchRun identity graph."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any, Mapping, Sequence
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from . import db
from .research_contracts import (
    JOB_SCHEMA_VERSION,
    POPULATION_SNAPSHOT_SCHEMA_VERSION,
    RESEARCH_RUN_SCHEMA_VERSION,
    REVIEW_SNAPSHOT_SCHEMA_VERSION,
    SAMPLING_CONTRACT_VERSION,
    TIME_SEMANTICS_VERSION,
    canonical_json,
    canonical_sampling_contract,
    epoch_to_utc_iso,
    population_hash,
    review_content_hash,
    review_id,
    review_snapshot_id,
    resolve_formal_window,
    sha256_json,
    utc_iso,
    utc_now,
)


def _parse(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return fallback


def _snapshot_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "review_snapshot_id": str(row["review_snapshot_id"]),
        "steam_review_id": str(row["steam_review_id"]),
        "app_id": int(row["app_id"]),
        "content_text": str(row["content_text"]),
        "content_hash": str(row["content_hash"]),
        "voted_up": None if row["voted_up"] is None else bool(row["voted_up"]),
        "language": row["language"],
        "timestamp_created": row["timestamp_created"],
        "timestamp_updated": row["timestamp_updated"],
        "payload": _parse(row["payload_json"], {}),
        "provider_metadata": _parse(row["provider_metadata_json"], {}),
        "fetched_at": utc_iso(row["fetched_at"]),
        "snapshot_schema_version": str(row["snapshot_schema_version"]),
    }


def save_review_snapshot(*, app_id: int, review: Mapping[str, Any], fetched_at: datetime | str | None = None, provider_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Persist one immutable review revision, idempotently."""
    rid = review_id(review)
    content_hash = review_content_hash(review)
    snapshot_id = review_snapshot_id(app_id, review)
    payload = dict(review)
    fetched = utc_iso(fetched_at)
    with db.get_connection() as conn:
        conn.execute(
            text("""INSERT OR IGNORE INTO review_snapshots
                (review_snapshot_id, steam_review_id, app_id, content_text, content_hash,
                 voted_up, language, timestamp_created, timestamp_updated, payload_json,
                 provider_metadata_json, fetched_at, snapshot_schema_version)
                VALUES (:snapshot_id, :review_id, :app_id, :content_text, :content_hash,
                        :voted_up, :language, :timestamp_created, :timestamp_updated,
                        :payload_json, :provider_metadata_json, :fetched_at, :schema_version)"""),
            {
                "snapshot_id": snapshot_id,
                "review_id": rid,
                "app_id": int(app_id),
                "content_text": str(review.get("review") or ""),
                "content_hash": content_hash,
                "voted_up": None if review.get("voted_up") is None else int(bool(review.get("voted_up"))),
                "language": review.get("language"),
                "timestamp_created": review.get("timestamp_created"),
                "timestamp_updated": review.get("timestamp_updated"),
                "payload_json": canonical_json(payload),
                "provider_metadata_json": canonical_json(dict(provider_metadata or {})),
                "fetched_at": fetched,
                "schema_version": REVIEW_SNAPSHOT_SCHEMA_VERSION,
            },
        )
        row = conn.execute(text("SELECT * FROM review_snapshots WHERE review_snapshot_id=:snapshot_id"), {"snapshot_id": snapshot_id}).mappings().one()
        if str(row["payload_json"]) != canonical_json(payload):
            raise ValueError("review_snapshot_conflict")
    return _snapshot_row(row)


def get_review_snapshot(review_snapshot_id_value: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM review_snapshots WHERE review_snapshot_id=:id"), {"id": str(review_snapshot_id_value)}).mappings().first()
    return _snapshot_row(row) if row else None


def _population_row(row: Mapping[str, Any], reviews: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "population_snapshot_id": str(row["population_snapshot_id"]),
        "app_id": int(row["app_id"]),
        "sampling_contract": _parse(row["sampling_contract_json"], {}),
        "sampling_contract_hash": str(row["sampling_contract_hash"]),
        "acquisition_provenance": _parse(row["acquisition_provenance_json"], {}) if "acquisition_provenance_json" in row else {},
        "ordered_review_snapshot_ids": [str(review["review_snapshot_id"]) for review in reviews],
        "membership_count": int(row["membership_count"]),
        "population_hash": str(row["population_hash"]),
        "anchor_time": utc_iso(row["anchor_time"]),
        "start_at_utc": row["start_at_utc"],
        "end_at_utc": row["end_at_utc"],
        "created_at": utc_iso(row["created_at"]),
        "snapshot_schema_version": str(row["snapshot_schema_version"]),
        "reviews": [dict(review) for review in reviews],
    }


def _load_population(conn, population_snapshot_id: str) -> dict[str, Any] | None:
    row = conn.execute(text("SELECT * FROM population_snapshots WHERE population_snapshot_id=:id"), {"id": population_snapshot_id}).mappings().first()
    if not row:
        return None
    members = conn.execute(
        text("""SELECT rs.* FROM population_snapshot_members pm
                JOIN review_snapshots rs ON rs.review_snapshot_id=pm.review_snapshot_id
                WHERE pm.population_snapshot_id=:id ORDER BY pm.ordinal"""),
        {"id": population_snapshot_id},
    ).mappings().all()
    reviews = [_snapshot_row(member) for member in members]
    ids = [review["review_snapshot_id"] for review in reviews]
    hashes = [review["content_hash"] for review in reviews]
    if len(reviews) != int(row["membership_count"]) or population_hash(ids, hashes) != str(row["population_hash"]):
        raise ValueError("population_snapshot_corrupt")
    return _population_row(row, reviews)


def create_population_snapshot(*, app_id: int, sampling_contract: Mapping[str, Any], reviews: Sequence[Mapping[str, Any]], anchor_time: datetime | str | None = None, acquisition_provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Freeze ordered ReviewSnapshot membership and its time/contract identity."""
    canonical_contract = canonical_sampling_contract(sampling_contract)
    anchor = utc_iso(anchor_time)
    start = canonical_contract.get("start_time")
    end = canonical_contract.get("end_time")
    relative_days = canonical_contract.get("relative_days")
    window = resolve_formal_window(
        anchor_time=anchor,
        start_at_utc=epoch_to_utc_iso(start) if start is not None else None,
        end_at_utc=epoch_to_utc_iso(end) if end is not None else None,
        relative_days=int(relative_days) if relative_days is not None else None,
    )
    canonical_contract["resolved_window"] = {
        "start_at_utc": window["start_at_utc"],
        "end_at_utc": window["end_at_utc"],
        "anchor_time": window["anchor_time"],
    }
    snapshots = [save_review_snapshot(app_id=app_id, review=review, fetched_at=anchor, provider_metadata=acquisition_provenance) for review in reviews]
    ids = [snapshot["review_snapshot_id"] for snapshot in snapshots]
    hashes = [snapshot["content_hash"] for snapshot in snapshots]
    if len(set(ids)) != len(ids):
        raise ValueError("population_snapshot_duplicate_review")
    contract_hash = sha256_json(canonical_contract)
    pop_hash = population_hash(ids, hashes)
    population_id = "pop_" + sha256_json({"app_id": int(app_id), "contract_hash": contract_hash, "population_hash": pop_hash, "anchor_time": anchor})[:40]
    with db.get_connection() as conn:
        existing = conn.execute(text("SELECT * FROM population_snapshots WHERE population_snapshot_id=:id"), {"id": population_id}).mappings().first()
        if existing:
            loaded = _load_population(conn, population_id)
            if str(existing["population_hash"]) != pop_hash or str(existing["sampling_contract_hash"]) != contract_hash:
                raise ValueError("population_snapshot_conflict")
            return loaded or {}
        conn.execute(
            text("""INSERT INTO population_snapshots
                (population_snapshot_id, app_id, sampling_contract_json, sampling_contract_hash, acquisition_provenance_json,
                 membership_count, population_hash, anchor_time, start_at_utc, end_at_utc,
                 snapshot_schema_version)
                VALUES (:id, :app_id, :contract_json, :contract_hash, :provenance_json, :count, :population_hash,
                        :anchor, :start_at_utc, :end_at_utc, :schema_version)"""),
            {"id": population_id, "app_id": int(app_id), "contract_json": canonical_json(canonical_contract), "contract_hash": contract_hash, "provenance_json": canonical_json(dict(acquisition_provenance or {})), "count": len(snapshots), "population_hash": pop_hash, "anchor": anchor, "start_at_utc": window["start_at_utc"], "end_at_utc": window["end_at_utc"], "schema_version": POPULATION_SNAPSHOT_SCHEMA_VERSION},
        )
        for ordinal, snapshot in enumerate(snapshots):
            conn.execute(
                text("""INSERT INTO population_snapshot_members
                    (population_snapshot_id, ordinal, review_snapshot_id, content_hash)
                    VALUES (:population_id, :ordinal, :review_snapshot_id, :content_hash)"""),
                {"population_id": population_id, "ordinal": ordinal, "review_snapshot_id": snapshot["review_snapshot_id"], "content_hash": snapshot["content_hash"]},
            )
        loaded = _load_population(conn, population_id)
    return loaded or {}


def get_population_snapshot(population_snapshot_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        return _load_population(conn, str(population_snapshot_id))


def create_research_run(*, run_id: str, app_id: int, sampling_contract: Mapping[str, Any], reviews: Sequence[Mapping[str, Any]], anchor_time: datetime | str | None = None, acquisition_provenance: Mapping[str, Any] | None = None, config: Mapping[str, Any] | None = None, created_by_job_id: str | None = None, status: str = "QUEUED", research_core_version: str = "research-core-v1") -> dict[str, Any]:
    """Create or resolve one exact immutable ResearchRun."""
    population = create_population_snapshot(app_id=app_id, sampling_contract=sampling_contract, reviews=reviews, anchor_time=anchor_time, acquisition_provenance=acquisition_provenance)
    created_at = utc_iso(anchor_time)
    contract = dict(population["sampling_contract"])
    with db.get_connection() as conn:
        existing = conn.execute(text("SELECT * FROM research_runs WHERE run_id=:run_id"), {"run_id": str(run_id)}).mappings().first()
        if existing:
            if str(existing["population_snapshot_id"]) != population["population_snapshot_id"] or str(existing["population_hash"]) != population["population_hash"]:
                raise ValueError("research_run_conflict")
            return _research_run_row(existing)
        conn.execute(
            text("""INSERT INTO research_runs
                (run_id, run_type, app_id, sampling_contract_json, sampling_contract_version,
                 acquisition_provenance_json, population_snapshot_id, population_hash, anchor_time,
                 research_core_version, metric_schema_version, time_semantics_version, config_json,
                 status, created_by_job_id, created_at, validity_status, immutable_result_ref)
                VALUES (:run_id, 'snapshot', :app_id, :contract_json, :contract_version,
                        :provenance_json, :population_id, :population_hash, :anchor_time,
                        :research_core_version, 'metric-observation-v1', :time_version, :config_json,
                        :status, :job_id, :created_at, 'VALID', :result_ref)"""),
            {"run_id": str(run_id), "app_id": int(app_id), "contract_json": canonical_json(contract), "contract_version": SAMPLING_CONTRACT_VERSION, "provenance_json": canonical_json(dict(acquisition_provenance or {})), "population_id": population["population_snapshot_id"], "population_hash": population["population_hash"], "anchor_time": population["anchor_time"], "research_core_version": research_core_version, "time_version": TIME_SEMANTICS_VERSION, "config_json": canonical_json(dict(config or {})), "status": str(status).upper(), "job_id": created_by_job_id, "created_at": created_at, "result_ref": f"research-run:{run_id}"},
        )
        row = conn.execute(text("SELECT * FROM research_runs WHERE run_id=:run_id"), {"run_id": str(run_id)}).mappings().one()
    return _research_run_row(row)


def _research_run_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"run_id": str(row["run_id"]), "run_type": str(row["run_type"]), "app_id": int(row["app_id"]), "sampling_contract": _parse(row["sampling_contract_json"], {}), "sampling_contract_version": str(row["sampling_contract_version"]), "acquisition_provenance": _parse(row["acquisition_provenance_json"], {}), "population_snapshot_id": str(row["population_snapshot_id"]), "population_hash": str(row["population_hash"]), "anchor_time": utc_iso(row["anchor_time"]), "research_core_version": str(row["research_core_version"]), "metric_schema_version": str(row["metric_schema_version"]), "time_semantics_version": str(row["time_semantics_version"]), "config": _parse(row["config_json"], {}), "status": str(row["status"]), "created_by_job_id": row["created_by_job_id"], "created_at": utc_iso(row["created_at"]), "completed_at": utc_iso(row["completed_at"]) if row["completed_at"] else None, "validity_status": str(row["validity_status"]), "immutable_result_ref": row["immutable_result_ref"]}


def get_research_run(run_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM research_runs WHERE run_id=:run_id"), {"run_id": str(run_id)}).mappings().first()
    return _research_run_row(row) if row else None


def transition_research_run(run_id: str, status: str) -> dict[str, Any] | None:
    """Bridge legacy general-run lifecycle into canonical run status."""
    target = {"queued": "QUEUED", "running": "RUNNING", "completed": "READY", "failed": "FAILED", "cancelled": "CANCELLED"}.get(str(status).lower(), str(status).upper())
    if target not in {"QUEUED", "RUNNING", "READY", "FAILED", "CANCELLED", "PARTIAL"}:
        raise ValueError("invalid_research_run_status")
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT status FROM research_runs WHERE run_id=:run_id"), {"run_id": str(run_id)}).mappings().first()
        if not row:
            return None
        current = str(row["status"])
        if current in {"READY", "FAILED", "CANCELLED", "PARTIAL"} and current != target:
            raise ValueError("research_run_terminal_status_immutable")
        if target in {"READY", "FAILED", "CANCELLED", "PARTIAL"}:
            conn.execute(text("UPDATE research_runs SET status=:status, completed_at=COALESCE(completed_at, :completed_at) WHERE run_id=:run_id"), {"run_id": str(run_id), "status": target, "completed_at": utc_iso(None)})
        else:
            conn.execute(text("UPDATE research_runs SET status=:status WHERE run_id=:run_id"), {"run_id": str(run_id), "status": target})
    return get_research_run(run_id)


def finalize_research_run(run_id: str, *, immutable_result_ref: str) -> dict[str, Any] | None:
    """Attach the insert-once result row and close a canonical run.

    The legacy result writer owns the atomic result insert.  This narrow
    bridge makes the canonical identity graph point at that exact immutable
    row without replacing or rewriting any analytical payload.
    """
    result_ref = str(immutable_result_ref).strip()
    if not result_ref:
        raise ValueError("immutable_result_ref_required")
    with db.get_connection() as conn:
        row = conn.execute(
            text("SELECT status, immutable_result_ref FROM research_runs WHERE run_id=:run_id"),
            {"run_id": str(run_id)},
        ).mappings().first()
        if not row:
            return None
        current = str(row["status"])
        existing_ref = row["immutable_result_ref"]
        if current in {"FAILED", "CANCELLED", "PARTIAL"}:
            raise ValueError("research_run_terminal_status_immutable")
        if existing_ref and str(existing_ref) not in {result_ref, f"research-run:{run_id}"}:
            raise ValueError("immutable_result_ref_conflict")
        conn.execute(
            text("""UPDATE research_runs
                    SET status='READY', completed_at=COALESCE(completed_at, :completed_at),
                        immutable_result_ref=:result_ref
                    WHERE run_id=:run_id"""),
            {"run_id": str(run_id), "completed_at": utc_iso(None), "result_ref": result_ref},
        )
    return get_research_run(run_id)


_JOB_TRANSITIONS = {"QUEUED": {"QUEUED", "RUNNING", "CANCELLED", "FAILED"}, "RUNNING": {"RUNNING", "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"}, "SUCCEEDED": {"SUCCEEDED"}, "PARTIAL": {"PARTIAL"}, "FAILED": {"FAILED", "QUEUED"}, "CANCELLED": {"CANCELLED"}}


def _job_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["retryable"] = bool(result["retryable"])
    return result


def create_job(*, job_type: str, target_resource_type: str, idempotency_key: str, target_resource_id: str | None = None, progress_total: int = 0, progress_unit: str = "items", retryable: bool = False, job_id: str | None = None) -> dict[str, Any]:
    if not str(idempotency_key).strip():
        raise ValueError("job_idempotency_key_required")
    now = utc_iso(None)
    with db.get_connection() as conn:
        existing = conn.execute(text("SELECT * FROM jobs WHERE job_type=:job_type AND idempotency_key=:key"), {"job_type": job_type, "key": idempotency_key}).mappings().first()
        if existing:
            return _job_row(existing)
        job_id_value = job_id or "job_" + uuid4().hex
        try:
            conn.execute(text("""INSERT INTO jobs
                (job_id, job_type, target_resource_type, target_resource_id, idempotency_key,
                 status, stage, progress_total, progress_unit, retryable, created_at)
                VALUES (:job_id, :job_type, :target_type, :target_id, :key, 'QUEUED', 'queued',
                        :total, :unit, :retryable, :created_at)"""), {"job_id": job_id_value, "job_type": job_type, "target_type": target_resource_type, "target_id": target_resource_id, "key": idempotency_key, "total": max(0, int(progress_total)), "unit": progress_unit, "retryable": int(bool(retryable)), "created_at": now})
        except IntegrityError:
            existing = conn.execute(text("SELECT * FROM jobs WHERE job_type=:job_type AND idempotency_key=:key"), {"job_type": job_type, "key": idempotency_key}).mappings().one()
            return _job_row(existing)
        row = conn.execute(text("SELECT * FROM jobs WHERE job_id=:job_id"), {"job_id": job_id_value}).mappings().one()
    return _job_row(row)


def get_job(job_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM jobs WHERE job_id=:job_id"), {"job_id": str(job_id)}).mappings().first()
    return _job_row(row) if row else None


def transition_job(job_id: str, status: str, *, stage: str | None = None, progress_current: int | None = None, progress_total: int | None = None, error_code: str | None = None, error_detail: str | None = None) -> dict[str, Any]:
    target = str(status).upper()
    if target not in _JOB_TRANSITIONS:
        raise ValueError("invalid_job_status")
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM jobs WHERE job_id=:job_id"), {"job_id": str(job_id)}).mappings().first()
        if not row:
            raise KeyError(f"job_not_found:{job_id}")
        current = str(row["status"])
        if target not in _JOB_TRANSITIONS[current]:
            raise ValueError(f"invalid_job_transition:{current}->{target}")
        sets = ["status=:status"]
        params: dict[str, Any] = {"job_id": str(job_id), "status": target}
        if stage is not None:
            sets.append("stage=:stage"); params["stage"] = stage
        if progress_current is not None:
            sets.append("progress_current=:progress_current"); params["progress_current"] = max(0, int(progress_current))
        if progress_total is not None:
            sets.append("progress_total=:progress_total"); params["progress_total"] = max(0, int(progress_total))
        if target == "RUNNING":
            sets.extend(["started_at=COALESCE(started_at, :now)", "heartbeat_at=:now", "attempt_count=attempt_count+1"])
        else:
            params["now"] = utc_iso(None)
        if target in {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"}:
            sets.append("finished_at=COALESCE(finished_at, :now)")
        if target == "RUNNING":
            params["now"] = utc_iso(None)
        if error_code is not None:
            sets.append("error_code=:error_code"); params["error_code"] = error_code
        if error_detail is not None:
            sets.append("error_detail=:error_detail"); params["error_detail"] = error_detail
        conn.execute(text(f"UPDATE jobs SET {', '.join(sets)} WHERE job_id=:job_id"), params)
        updated = conn.execute(text("SELECT * FROM jobs WHERE job_id=:job_id"), {"job_id": str(job_id)}).mappings().one()
    return _job_row(updated)


def request_job_cancel(job_id: str) -> dict[str, Any]:
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT status FROM jobs WHERE job_id=:job_id"), {"job_id": str(job_id)}).mappings().first()
        if not row:
            raise KeyError(f"job_not_found:{job_id}")
        now = utc_iso(None)
        if str(row["status"]) == "QUEUED":
            conn.execute(text("UPDATE jobs SET status='CANCELLED', stage='cancelled', cancel_requested_at=:now, finished_at=:now WHERE job_id=:job_id"), {"job_id": str(job_id), "now": now})
        elif str(row["status"]) == "RUNNING":
            conn.execute(text("UPDATE jobs SET cancel_requested_at=:now WHERE job_id=:job_id"), {"job_id": str(job_id), "now": now})
    return get_job(job_id) or {}


def recover_interrupted_jobs(*, stale_after_seconds: int = 300) -> int:
    cutoff = (utc_now() - timedelta(seconds=max(1, int(stale_after_seconds)))).isoformat().replace("+00:00", "Z")
    with db.get_connection() as conn:
        result = conn.execute(text("""UPDATE jobs SET status=CASE WHEN retryable=1 THEN 'QUEUED' ELSE 'FAILED' END,
                stage=CASE WHEN retryable=1 THEN 'requeued_after_restart' ELSE 'failed_after_restart' END,
                error_code=CASE WHEN retryable=1 THEN NULL ELSE 'PROCESS_INTERRUPTED' END,
                error_detail=CASE WHEN retryable=1 THEN NULL ELSE 'Job heartbeat expired before process restart.' END,
                finished_at=CASE WHEN retryable=1 THEN NULL ELSE COALESCE(finished_at, :now) END
                WHERE status='RUNNING' AND heartbeat_at IS NOT NULL AND heartbeat_at < :cutoff"""), {"cutoff": cutoff, "now": utc_iso(None)})
    return int(result.rowcount or 0)


__all__ = ["create_job", "create_population_snapshot", "create_research_run", "finalize_research_run", "get_job", "get_population_snapshot", "get_research_run", "get_review_snapshot", "recover_interrupted_jobs", "request_job_cancel", "save_review_snapshot", "transition_job", "transition_research_run"]
