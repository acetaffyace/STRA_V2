"""Review acquisition endpoints.

These endpoints intentionally never invoke LLM providers.  They provide the
manual Database-page crawler and expose sparse collection-window provenance for
future version/event analysis.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..acquisition import collect_reviews, list_collection_windows
from ..sampling import SamplingContract
from ..steam_api import SteamAPIError

router = APIRouter()


class CollectReviewsRequest(BaseModel):
    sampling: SamplingContract
    force: bool = Field(
        default=True,
        description="Manual collection defaults to a fresh Steam request; false allows a complete compatible cache hit.",
    )


class CollectReviewsResponse(BaseModel):
    app_id: int
    source: str
    fetched_count: int
    stored_count: int
    matched_count: int
    cache_hit: bool
    collection_complete: bool
    truncated_by_max_reviews: bool
    stop_reason: Optional[str] = None
    sampling: Dict[str, Any]
    stats: Dict[str, Any] = Field(default_factory=dict)


class CollectionWindowsResponse(BaseModel):
    app_id: Optional[int] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)


def _conservative_cache_cap(payload: Dict[str, Any], sampling: SamplingContract) -> Dict[str, Any]:
    """Do not claim complete coverage when a cache hit lands exactly on a new cap.

    A complete wider historical ledger row can cover the requested sub-window,
    while ``load_local_reviews`` applies the caller's smaller max_reviews before
    the cached result is constructed.  In that case the ledger cannot prove
    that the current capped population is exhaustive.  Mark it partial rather
    than exposing a false COMPLETE state to the UI.
    """
    if (
        payload.get("source") == "cache"
        and sampling.max_reviews > 0
        and int(payload.get("matched_count") or 0) >= sampling.max_reviews
        and payload.get("collection_complete")
        and not payload.get("truncated_by_max_reviews")
    ):
        payload = dict(payload)
        payload["collection_complete"] = False
        payload["truncated_by_max_reviews"] = True
        payload["stop_reason"] = "cache_cap_boundary_ambiguous"
        stats = dict(payload.get("stats") or {})
        stats["collection_complete"] = False
        stats["scope_complete"] = False
        stats["truncated_by_max_reviews"] = True
        stats["stop_reason"] = "cache_cap_boundary_ambiguous"
        stats["cache_cap_boundary_ambiguous"] = True
        payload["stats"] = stats
    return payload


@router.post("/reviews/collect", response_model=CollectReviewsResponse)
def collect_reviews_endpoint(request: CollectReviewsRequest) -> CollectReviewsResponse:
    """Fetch Steam reviews and persist them locally without any LLM work."""
    try:
        result = collect_reviews(request.sampling, force=request.force)
    except SteamAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Review collection failed.") from exc

    payload = _conservative_cache_cap(result.to_dict(), request.sampling)
    return CollectReviewsResponse(
        app_id=request.sampling.app_id,
        sampling=request.sampling.to_dict(),
        **payload,
    )


@router.get("/reviews/collection-windows", response_model=CollectionWindowsResponse)
def collection_windows(app_id: Optional[int] = None, limit: int = 200) -> CollectionWindowsResponse:
    if app_id is not None and app_id <= 0:
        raise HTTPException(status_code=422, detail="app_id must be positive")
    items = list_collection_windows(app_id=app_id, limit=limit)
    # `review_collection_windows` is provenance, not ownership of raw rows.
    # A user may delete an app from Database while older provenance remains;
    # never expose such rows as reusable coverage to later planners.
    live_app_ids = {item["app_id"] for item in items if storage.count_reviews(int(item["app_id"])) > 0}
    items = [item for item in items if item.get("app_id") in live_app_ids]
    return CollectionWindowsResponse(app_id=app_id, items=items)
