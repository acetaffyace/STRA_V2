"""Resource-oriented M0 ResearchRun and durable Job endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel, Field

from ..research_run_store import (
    create_job,
    create_research_run,
    get_job,
    get_population_snapshot,
    get_research_run,
    request_job_cancel,
    transition_job,
)
from ..semantic_run_store import (
    create_semantic_run,
    execute_semantic_run_job,
    get_semantic_run,
    get_semantic_rollups,
    list_semantic_evidence,
    list_semantic_runs,
    semantic_config_hash,
    semantic_run_id_for,
)
from ..population_compatibility import check_population_compatibility


router = APIRouter(tags=["research-resources"])


class ResearchRunCreateRequest(BaseModel):
    app_id: int = Field(..., gt=0)
    sampling_contract: dict[str, Any]
    reviews: list[dict[str, Any]] = Field(default_factory=list)
    anchor_time: datetime | None = None
    acquisition_provenance: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    research_core_version: str = "research-core-v1"
    run_id: str | None = Field(default=None, min_length=3, max_length=160)
    created_by_job_id: str | None = None


class JobCreateRequest(BaseModel):
    job_type: str = Field(..., min_length=1, max_length=80)
    target_resource_type: str = Field(..., min_length=1, max_length=80)
    target_resource_id: str | None = Field(default=None, max_length=160)
    idempotency_key: str = Field(..., min_length=1, max_length=500)
    progress_total: int = Field(default=0, ge=0)
    progress_unit: str = Field(default="items", min_length=1, max_length=40)
    retryable: bool = False
    job_id: str | None = Field(default=None, min_length=3, max_length=160)


class PopulationCompatibilityRequest(BaseModel):
    population_snapshot_id: str = Field(..., min_length=3, max_length=160)
    requested_contract: dict[str, Any]


class SemanticRunCreateRequest(BaseModel):
    semantic_config: dict[str, Any] = Field(..., min_length=1)
    semantic_run_id: str | None = Field(default=None, min_length=3, max_length=160)


@router.post("/research-runs", status_code=201)
def create_snapshot_research_run(request: ResearchRunCreateRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
    """Persist one exact snapshot run over supplied/frozen review fixtures.

    Acquisition and Research Core execution remain separate concerns.  This
    endpoint is deliberately deterministic and is suitable for offline setup
    and restart acceptance tests.
    """
    run_id = request.run_id or ("run_" + __import__("uuid").uuid4().hex)
    if idempotency_key:
        request.config.setdefault("idempotency_key", idempotency_key)
    try:
        return create_research_run(
            run_id=run_id,
            app_id=request.app_id,
            sampling_contract=request.sampling_contract,
            reviews=request.reviews,
            anchor_time=request.anchor_time,
            acquisition_provenance=request.acquisition_provenance,
            config=request.config,
            created_by_job_id=request.created_by_job_id,
            research_core_version=request.research_core_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/research-runs/{run_id}")
def read_snapshot_research_run(run_id: str) -> dict[str, Any]:
    result = get_research_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="research_run_not_found")
    return result


@router.post("/research-runs/{run_id}/semantic-runs", status_code=202)
def create_snapshot_semantic_run(
    run_id: str,
    request: SemanticRunCreateRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Attach one exact SemanticRun and durable generation Job to a ResearchRun."""
    research = get_research_run(run_id)
    if research is None:
        raise HTTPException(status_code=404, detail="research_run_not_found")
    try:
        config_hash = semantic_config_hash(request.semantic_config)
        semantic_id = request.semantic_run_id or semantic_run_id_for(run_id, request.semantic_config)
        population = get_population_snapshot(research["population_snapshot_id"]) or {}
        job_key = idempotency_key or f"semantic-run:{run_id}:{config_hash}"
        job_id = "job_semantic_" + config_hash[:32]
        job = create_job(
            job_type="semantic_v2_generation",
            target_resource_type="semantic_run",
            target_resource_id=semantic_id,
            idempotency_key=job_key,
            progress_total=int(population.get("membership_count") or 0),
            progress_unit="reviews",
            retryable=True,
            job_id=job_id,
        )
        semantic = create_semantic_run(
            research_run_id=run_id,
            semantic_config=request.semantic_config,
            created_by_job_id=job["job_id"],
            semantic_run_id=semantic_id,
        )
        if job["status"] == "QUEUED" and semantic["status"] == "QUEUED":
            background_tasks.add_task(execute_semantic_run_job, semantic["semantic_run_id"], job["job_id"])
        elif job["status"] == "QUEUED" and semantic["status"] in {"READY", "PARTIAL", "FAILED", "CANCELLED"}:
            # A retried request may find an already materialized immutable
            # target. Close the new job without rewriting that target.
            terminal_job_status = "PARTIAL" if semantic["status"] == "PARTIAL" else "SUCCEEDED" if semantic["status"] == "READY" else semantic["status"]
            job = transition_job(job["job_id"], terminal_job_status, stage="already_materialized")
        return {"semantic_run": semantic, "job": job}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/research-runs/{run_id}/semantic-runs")
def read_snapshot_semantic_runs(run_id: str) -> dict[str, Any]:
    if get_research_run(run_id) is None:
        raise HTTPException(status_code=404, detail="research_run_not_found")
    return {"research_run_id": run_id, "semantic_runs": list_semantic_runs(run_id)}


@router.get("/semantic-runs/{semantic_run_id}")
def read_snapshot_semantic_run(semantic_run_id: str) -> dict[str, Any]:
    result = get_semantic_run(semantic_run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="semantic_run_not_found")
    job = get_job(result["created_by_job_id"]) if result.get("created_by_job_id") else None
    return {"semantic_run": result, "job": job, "rollups": get_semantic_rollups(semantic_run_id), "evidence": list_semantic_evidence(semantic_run_id)}


@router.get("/population-snapshots/{population_snapshot_id}")
def read_population_snapshot(population_snapshot_id: str) -> dict[str, Any]:
    result = get_population_snapshot(population_snapshot_id)
    if result is None:
        raise HTTPException(status_code=404, detail="population_snapshot_not_found")
    return result


@router.post("/population-compatibility/check")
def check_population_reuse(request: PopulationCompatibilityRequest) -> dict[str, Any]:
    existing = get_population_snapshot(request.population_snapshot_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="population_snapshot_not_found")
    return check_population_compatibility(existing_population=existing, requested_contract=request.requested_contract).model_dump()


@router.post("/jobs", status_code=201)
def create_durable_job(request: JobCreateRequest) -> dict[str, Any]:
    try:
        return create_job(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
def read_durable_job(job_id: str) -> dict[str, Any]:
    result = get_job(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    return result


@router.post("/jobs/{job_id}/cancel")
def cancel_durable_job(job_id: str) -> dict[str, Any]:
    try:
        return request_job_cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job_not_found") from exc
