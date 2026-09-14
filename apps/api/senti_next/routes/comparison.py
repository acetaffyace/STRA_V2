"""Read-only endpoints for the shared research comparison contract."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..research_comparison import build_research_comparison_for_runs


router = APIRouter(tags=["research-comparison"])


@router.get("/comparison")
def get_research_comparison(left_run: str, right_run: str) -> dict:
    """Compare two exact completed general-analysis runs without side effects."""
    if not left_run or not right_run or left_run == right_run:
        raise HTTPException(status_code=400, detail="left_run and right_run must be distinct.")
    try:
        return build_research_comparison_for_runs(left_run, right_run)
    except ValueError as exc:
        detail = str(exc)
        status = 404 if detail in {"comparison_run_not_found", "comparison_run_result_unavailable"} else 409
        raise HTTPException(status_code=status, detail=detail) from exc


__all__ = ["router"]
