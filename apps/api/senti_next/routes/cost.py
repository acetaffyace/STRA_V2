"""Read-only LLM cost observability endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from .. import cost_ledger

router = APIRouter(tags=["llm-cost"])


@router.get("/runs/{run_id}/llm-cost")
def run_llm_cost(run_id: str) -> dict:
    return {"run_id": run_id, "summary": cost_ledger.summarize(run_id=run_id), "calls": cost_ledger.list_calls(run_id=run_id)}


@router.get("/llm-cost/summary")
def llm_cost_summary(
    operation_type: Optional[str] = Query(default=None),
    provider: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None),
    workload_type: Optional[str] = Query(default="production"),
) -> dict:
    return cost_ledger.summarize(operation_type=operation_type, provider=provider, since=since, workload_type=workload_type)
