"""Resource-oriented M0 ResearchRun and durable Job endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..research_run_store import (
    create_job,
    create_research_run,
    get_job,
    get_population_snapshot,
    get_research_run,
    request_job_cancel,
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
