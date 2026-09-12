"""Shared models, helpers, and constants used by multiple route modules."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ..llm import normalize_taxonomy_payload
from ..steam_enrichment import public_context

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Review limits - configurable via environment
SAMPLE_LIMIT = int(os.getenv("SENTINEXT_SAMPLE_LIMIT", "1000"))
FETCH_LIMIT = int(os.getenv("SENTINEXT_FETCH_LIMIT", "0"))  # 0 = unlimited
EXPORT_MAX_ROWS = max(1, int(os.getenv("SENTINEXT_EXPORT_MAX_ROWS", "50000")))

REVIEW_EXPORT_COLUMNS = [
    "app_id",
    "app_name",
    "review_id",
    "review",
    "language",
    "created_at",
    "timestamp_created",
    "timestamp_updated",
    "voted_up",
    "votes_up",
    "votes_funny",
    "weighted_vote_score",
    "comment_count",
    "author_num_games_owned",
    "author_num_reviews",
    "author_playtime_forever",
    "author_playtime_last_two_weeks",
    "author_playtime_at_review",
    "author_deck_playtime_at_review",
    "author_last_played",
    "author_playtime_hours",
    "author_recent_playtime_hours",
    "steam_purchase",
    "received_for_free",
    "written_during_early_access",
    "primarily_steam_deck",
    "developer_response",
    "timestamp_dev_responded",
    "llm_main_category",
    "llm_subcategory",
    "llm_subcategories",
    "llm_issue_subcategories",
    "llm_request_subcategories",
    "llm_subcategory_evidence",
    "llm_has_issue",
    "llm_has_request",
]


# ---------------------------------------------------------------------------
# Pydantic Models (shared across routes)
# ---------------------------------------------------------------------------

class AnalyzeMetadata(BaseModel):
    app_id: int
    requested: int
    retrieved: int
    requested_limit: Optional[int] = None
    available_matching_reviews: Optional[int] = None
    retrieved_reviews: Optional[int] = None
    population_reviews_after_scope: Optional[int] = None
    retrieved_count: Optional[int] = None
    deduplicated_count: Optional[int] = None
    analysis_population_count: Optional[int] = None
    language: str
    languages: Optional[List[str]] = None
    # Legacy results may not have trustworthy ingestion time.  Do not invent
    # a current timestamp just to satisfy the outward schema.
    fetched_at: Optional[str] = None
    mode: Optional[str] = None
    source: Optional[str] = None
    run_id: Optional[str] = None
    # ``window_start``/``window_end`` are legacy observed-review date fields.
    # These explicit fields describe acquisition scope instead.
    coverage_start_time: Optional[float] = None
    coverage_end_time: Optional[float] = None
    coverage_status: Optional[str] = None
    coverage_end_inclusive: Optional[bool] = None
    observed_review_start_time: Optional[float] = None
    observed_review_end_time: Optional[float] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    data_cutoff: Optional[str] = None
    active_filters: Optional[Dict[str, Any]] = None
    collection_complete: Optional[bool] = None
    truncated_by_max_reviews: Optional[bool] = None
    stop_reason: Optional[str] = None
    language_stats: Optional[Dict[str, Any]] = None
    sampling_contract: Optional[Dict[str, Any]] = None
    population_provenance: Optional[Dict[str, Any]] = None
    classification_population: Optional[int] = None
    evidence_population: Optional[int] = None
    header_image: Optional[str] = None
    review_fingerprint: Optional[str] = None
    price_initial: Optional[float] = None
    price_final: Optional[Union[float, str]] = None
    price_initial_formatted: Optional[str] = None
    price_final_formatted: Optional[str] = None
    price_discount: Optional[int] = None
    price_currency: Optional[str] = None
    is_free: Optional[bool] = None


class StarredGamePayload(BaseModel):
    app_id: int
    name: str
    metadata: AnalyzeMetadata
    insights: Optional[dict] = None
    sample: List[dict] = Field(default_factory=list)


class StarredGameResponse(BaseModel):
    app_id: int
    name: str
    metadata: AnalyzeMetadata
    insights: Optional[dict]
    sample: List[dict]
    genres: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    updated_at: str
    is_favorite: bool = False


class DatabaseReviewItem(BaseModel):
    review_id: str
    app_id: int
    app_name: Optional[str] = None
    review: str
    language: Optional[str] = None
    voted_up: bool
    votes_up: int = 0
    votes_funny: int = 0
    weighted_vote_score: Optional[float] = None
    comment_count: int = 0
    timestamp_created: Optional[int] = None
    timestamp_updated: Optional[int] = None
    steam_purchase: Optional[bool] = None
    received_for_free: Optional[bool] = None
    written_during_early_access: Optional[bool] = None
    primarily_steam_deck: Optional[bool] = None
    author_num_games_owned: int = 0
    author_num_reviews: int = 0
    author_playtime_forever: int = 0
    author_playtime_last_two_weeks: int = 0
    author_playtime_at_review: int = 0
    author_deck_playtime_at_review: int = 0
    author_last_played: Optional[int] = None
    author_playtime_hours: Optional[float] = None
    author_recent_playtime_hours: Optional[float] = None
    created_at: Optional[str] = None
    llm_main_category: Optional[str] = None
    llm_subcategory: Optional[str] = None
    llm_subcategories: List[str] = Field(default_factory=list)
    llm_issue_subcategories: List[str] = Field(default_factory=list)
    llm_request_subcategories: List[str] = Field(default_factory=list)
    llm_subcategory_evidence: Dict[str, List[str]] = Field(default_factory=dict)
    llm_has_issue: bool = False
    llm_has_request: bool = False
    steam_context: Dict[str, Any] = Field(default_factory=dict)
    developer_response: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)


class DatabaseReviewsResponse(BaseModel):
    items: List[DatabaseReviewItem]
    total: int
    offset: int
    limit: int


class DatabaseGameOption(BaseModel):
    app_id: int
    name: Optional[str] = None


class NewsItemResponse(BaseModel):
    gid: str
    title: str
    url: str
    author: str
    contents: str
    feed_label: str
    date: int
    feed_name: str
    feed_type: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_payload(value: Any, fallback: dict) -> dict:
    if value is None:
        return fallback
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def _database_row_to_item(row: Dict[str, Any], games_map: Dict[int, Optional[str]]) -> DatabaseReviewItem:
    payload = _parse_json_payload(row.get("data"), {})
    label_payload = _parse_json_payload(row.get("label_payload"), {})
    if label_payload and (
        label_payload.get("subcategories")
        or label_payload.get("main_category")
        or label_payload.get("subcategory")
    ):
        label_payload = normalize_taxonomy_payload(label_payload)

    author = payload.get("author", {}) or {}
    playtime_forever = int(author.get("playtime_forever") or 0)
    playtime_recent = int(author.get("playtime_last_two_weeks") or 0)
    created_ts = payload.get("timestamp_created")
    created_at = (
        datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        if isinstance(created_ts, (int, float))
        else None
    )

    issue_subcats = label_payload.get("issue_subcategories") or []
    request_subcats = label_payload.get("request_subcategories") or []
    evidence = label_payload.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}

    app_id_value = int(row.get("app_id") or payload.get("app_id") or 0)
    enrichment = {
        key: row.get(key) if row.get(key) is not None else payload.get(key)
        for key in ("developer_response", "timestamp_dev_responded", "steam_purchase", "received_for_free", "primarily_steam_deck")
    }
    for key in ("steam_purchase", "received_for_free", "primarily_steam_deck"):
        if enrichment[key] is not None:
            enrichment[key] = bool(enrichment[key])
    context = public_context(enrichment)

    return DatabaseReviewItem(
        review_id=str(payload.get("recommendationid") or row.get("review_id") or ""),
        app_id=app_id_value,
        app_name=games_map.get(app_id_value),
        review=payload.get("review") or "",
        language=payload.get("language"),
        voted_up=bool(payload.get("voted_up")),
        votes_up=int(payload.get("votes_up") or 0),
        votes_funny=int(payload.get("votes_funny") or 0),
        weighted_vote_score=float(payload.get("weighted_vote_score")) if payload.get("weighted_vote_score") is not None else None,
        comment_count=int(payload.get("comment_count") or 0),
        timestamp_created=int(payload.get("timestamp_created")) if payload.get("timestamp_created") is not None else None,
        timestamp_updated=int(payload.get("timestamp_updated")) if payload.get("timestamp_updated") is not None else None,
        steam_purchase=bool(payload.get("steam_purchase")) if payload.get("steam_purchase") is not None else None,
        received_for_free=bool(payload.get("received_for_free")) if payload.get("received_for_free") is not None else None,
        written_during_early_access=bool(payload.get("written_during_early_access")) if payload.get("written_during_early_access") is not None else None,
        primarily_steam_deck=bool(payload.get("primarily_steam_deck")) if payload.get("primarily_steam_deck") is not None else None,
        author_num_games_owned=int(author.get("num_games_owned") or 0),
        author_num_reviews=int(author.get("num_reviews") or 0),
        author_playtime_forever=playtime_forever,
        author_playtime_last_two_weeks=playtime_recent,
        author_playtime_at_review=int(author.get("playtime_at_review") or 0),
        author_deck_playtime_at_review=int(author.get("deck_playtime_at_review") or 0),
        author_last_played=int(author.get("last_played")) if author.get("last_played") is not None else None,
        author_playtime_hours=playtime_forever / 60.0 if playtime_forever else 0.0,
        author_recent_playtime_hours=playtime_recent / 60.0 if playtime_recent else 0.0,
        created_at=created_at,
        llm_main_category=label_payload.get("main_category"),
        llm_subcategory=label_payload.get("subcategory"),
        llm_subcategories=list(label_payload.get("subcategories") or []),
        llm_issue_subcategories=list(issue_subcats) if isinstance(issue_subcats, list) else [],
        llm_request_subcategories=list(request_subcats) if isinstance(request_subcats, list) else [],
        llm_subcategory_evidence=evidence,
        llm_has_issue=bool(issue_subcats),
        llm_has_request=bool(request_subcats),
        steam_context=context["steam_context"],
        developer_response=context["developer_response"],
        provenance=context["provenance"],
    )


def _serialize_export_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


