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

    payload = result.to_dict()
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
