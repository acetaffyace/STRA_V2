"""Read-only deterministic presentation projection endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from ..presentation_projections import (
    daily_recommendation_rate,
    daily_review_volume,
    provenance_strip,
    recent_analysis_summary,
    version_comparison_population_strip,
)

router = APIRouter(tags=["presentation-projections"])


@router.get("/presentation/daily-review-volume/{run_id}")
def get_daily_review_volume(run_id: str, from_date: date | None = Query(default=None), to_date: date | None = Query(default=None)) -> dict:
    return daily_review_volume(run_id, from_date, to_date)


@router.get("/presentation/daily-recommendation-rate/{run_id}")
def get_daily_recommendation_rate(run_id: str, from_date: date | None = Query(default=None), to_date: date | None = Query(default=None)) -> dict:
    return daily_recommendation_rate(run_id, from_date, to_date)


@router.get("/presentation/recent-analysis-summary")
def get_recent_analysis_summary(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    return recent_analysis_summary(limit)


@router.get("/presentation/version-comparison-population-strip/{run_id}")
def get_version_comparison_population_strip(run_id: str) -> dict:
    return version_comparison_population_strip(run_id)


@router.get("/presentation/provenance-strip/{run_id}")
def get_provenance_strip(run_id: str) -> dict:
    return provenance_strip(run_id)

