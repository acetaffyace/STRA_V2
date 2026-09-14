"""Canonical M0 research identity and reproducibility contracts.

The pre-rebuild application stored a latest-per-app result and, later, a
run-linked JSON population.  These contracts make the immutable identity graph
explicit without changing the legacy readers:

    Game -> ResearchRun -> PopulationSnapshot -> ReviewSnapshot

All hashes are based on canonical JSON so the same fixture produces the same
identity across processes and Python versions.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field


TIME_SEMANTICS_VERSION = "utc-half-open-v1"
SAMPLING_CONTRACT_VERSION = "sampling-contract-v1"
REVIEW_SNAPSHOT_SCHEMA_VERSION = "review-snapshot-v1"
POPULATION_SNAPSHOT_SCHEMA_VERSION = "population-snapshot-v1"
RESEARCH_RUN_SCHEMA_VERSION = "research-run-v1"
JOB_SCHEMA_VERSION = "job-v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | str | None) -> str:
    """Normalize a timestamp to an explicit UTC ISO-8601 instant."""
    if value is None:
        return utc_now().isoformat().replace("+00:00", "Z")
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def epoch_to_utc_iso(value: int | float) -> str:
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_formal_window(
    *,
    anchor_time: datetime | str,
    start_at_utc: datetime | str | None = None,
    end_at_utc: datetime | str | None = None,
    relative_days: int | None = None,
) -> dict[str, str | None]:
    """Resolve a formal half-open window exactly once.

    ``relative_days`` is interpreted as ``[anchor - days, anchor)``.  Explicit
    windows are preserved as supplied after UTC normalization.  Equal start
    and end are valid and represent an empty population.
    """
    anchor = datetime.fromisoformat(utc_iso(anchor_time).replace("Z", "+00:00"))
    if relative_days is not None:
        if relative_days < 0:
            raise ValueError("relative_days_must_be_non_negative")
        start = anchor - __import__("datetime").timedelta(days=relative_days)
        end = anchor
    else:
        start = datetime.fromisoformat(utc_iso(start_at_utc).replace("Z", "+00:00")) if start_at_utc is not None else None
        end = datetime.fromisoformat(utc_iso(end_at_utc).replace("Z", "+00:00")) if end_at_utc is not None else None
    if start is not None and end is not None and start > end:
        raise ValueError("formal_window_start_after_end")
    return {
        "anchor_time": utc_iso(anchor),
        "start_at_utc": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if start else None,
        "end_at_utc": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if end else None,
        "interval": "[start_at_utc,end_at_utc)",
        "time_semantics_version": TIME_SEMANTICS_VERSION,
    }


def canonical_sampling_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Return the persisted, versioned SamplingContract representation."""
    result = {str(key): value for key, value in dict(contract).items()}
    languages = result.get("languages", ["all"])
    result["languages"] = sorted({str(item).strip().lower() for item in (languages if isinstance(languages, list) else [languages]) if str(item).strip()})
    result["sampling_contract_version"] = SAMPLING_CONTRACT_VERSION
    result["time_semantics_version"] = TIME_SEMANTICS_VERSION
    result["interval_semantics"] = "[start_time,end_time)"
    return result


def review_id(review: Mapping[str, Any]) -> str:
    value = review.get("recommendationid") or review.get("review_id")
    if value is None or str(value).strip() == "":
        raise ValueError("review_snapshot_review_id_required")
    return str(value)


def review_content_hash(review: Mapping[str, Any]) -> str:
    return hashlib.sha256(str(review.get("review") or "").encode("utf-8")).hexdigest()


def review_snapshot_id(app_id: int, review: Mapping[str, Any]) -> str:
    return "rs_" + sha256_json({"app_id": int(app_id), "steam_review_id": review_id(review), "content_hash": review_content_hash(review)})[:40]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewSnapshot(ContractModel):
    review_snapshot_id: str
    steam_review_id: str
    app_id: int = Field(gt=0)
    content_text: str
    content_hash: str
    voted_up: bool | None = None
    language: str | None = None
    timestamp_created: int | None = None
    timestamp_updated: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    fetched_at: str
    snapshot_schema_version: str = REVIEW_SNAPSHOT_SCHEMA_VERSION


class PopulationSnapshot(ContractModel):
    population_snapshot_id: str
    app_id: int = Field(gt=0)
    sampling_contract: dict[str, Any]
    sampling_contract_hash: str
    ordered_review_snapshot_ids: list[str]
    membership_count: int = Field(ge=0)
    population_hash: str
    anchor_time: str
    start_at_utc: str | None = None
    end_at_utc: str | None = None
    created_at: str
    snapshot_schema_version: str = POPULATION_SNAPSHOT_SCHEMA_VERSION


class ResearchRun(ContractModel):
    run_id: str
    run_type: Literal["snapshot"] = "snapshot"
    app_id: int = Field(gt=0)
    sampling_contract: dict[str, Any]
    sampling_contract_version: str = SAMPLING_CONTRACT_VERSION
    acquisition_provenance: dict[str, Any] = Field(default_factory=dict)
    population_snapshot_id: str
    population_hash: str
    anchor_time: str
    research_core_version: str = "research-core-v1"
    metric_schema_version: str = "metric-observation-v1"
    time_semantics_version: str = TIME_SEMANTICS_VERSION
    config: dict[str, Any] = Field(default_factory=dict)
    status: str = "QUEUED"
    created_by_job_id: str | None = None
    created_at: str
    completed_at: str | None = None
    validity_status: str = "VALID"
    immutable_result_ref: str | None = None


class Job(ContractModel):
    job_id: str
    job_type: str
    target_resource_type: str
    target_resource_id: str | None = None
    idempotency_key: str
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"] = "QUEUED"
    stage: str = "queued"
    progress_current: int = Field(default=0, ge=0)
    progress_total: int = Field(default=0, ge=0)
    progress_unit: str = "items"
    attempt_count: int = Field(default=0, ge=0)
    heartbeat_at: str | None = None
    retryable: bool = False
    cancel_requested_at: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class MetricObservation(ContractModel):
    metric_id: str
    metric_version: str
    source_resource_id: str
    population_snapshot_id: str
    value: float | int | None = None
    unit: str
    numerator: int | float | None = None
    denominator: int | float | None = None
    missing_count: int | None = None
    method_note: str | None = None
    availability: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"] = "AVAILABLE"


class ResearchContext(ContractModel):
    app_id: int = Field(gt=0)
    run_id: str
    semantic_run_id: str | None = None
    analysis_mode: str = "snapshot"
    population_snapshot_id: str
    population_contract_version: str = SAMPLING_CONTRACT_VERSION
    taxonomy_version: str | None = None


def population_hash(snapshot_ids: Sequence[str], snapshot_hashes: Sequence[str]) -> str:
    if len(snapshot_ids) != len(snapshot_hashes):
        raise ValueError("population_hash_inputs_length_mismatch")
    return sha256_json([
        {"ordinal": ordinal, "review_snapshot_id": snapshot_id, "content_hash": content_hash}
        for ordinal, (snapshot_id, content_hash) in enumerate(zip(snapshot_ids, snapshot_hashes))
    ])


__all__ = [
    "JOB_SCHEMA_VERSION", "MetricObservation", "PopulationSnapshot", "POPULATION_SNAPSHOT_SCHEMA_VERSION",
    "RESEARCH_RUN_SCHEMA_VERSION", "REVIEW_SNAPSHOT_SCHEMA_VERSION", "ResearchContext", "ResearchRun",
    "Job", "ReviewSnapshot", "SAMPLING_CONTRACT_VERSION", "TIME_SEMANTICS_VERSION", "canonical_json",
    "canonical_sampling_contract", "epoch_to_utc_iso", "population_hash", "review_content_hash", "review_id",
    "review_snapshot_id", "resolve_formal_window", "sha256_json", "utc_iso", "utc_now",
]
