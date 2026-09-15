"""Reusable Steam review acquisition and sparse local-window caching.

This module deliberately owns *acquisition*, not analysis.  It can be called by
Dashboard analysis, the database crawler, or future version/event workflows
without invoking an LLM.

A bounded historical window first uses Steam storefront's de-facto
``start_date``/``end_date`` parameters as a best-effort fast path.  Because
those parameters are not part of Steam's stable public contract, every returned
page is timestamp-validated.  If the fast path appears unsupported, acquisition
falls back to STRA's canonical cursor crawl in :mod:`steam_api`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from math import ceil
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text

from . import db as db_module, storage, steam_api
from .sampling import SamplingContract

logger = logging.getLogger(__name__)


@dataclass
class AcquisitionResult:
    reviews: List[dict]
    source: str
    fetched_count: int
    stored_count: int
    cache_hit: bool
    collection_complete: bool
    truncated_by_max_reviews: bool
    stop_reason: Optional[str]
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "fetched_count": self.fetched_count,
            "stored_count": self.stored_count,
            "matched_count": len(self.reviews),
            "cache_hit": self.cache_hit,
            "collection_complete": self.collection_complete,
            "truncated_by_max_reviews": self.truncated_by_max_reviews,
            "stop_reason": self.stop_reason,
            "stats": self.stats,
        }


def _languages_key(languages: Sequence[str]) -> str:
    normalized = sorted({str(item).strip().lower() for item in languages if str(item).strip()})
    return json.dumps(normalized or ["all"], separators=(",", ":"))


def ensure_collection_schema() -> None:
    """Create the additive coverage ledger used by sparse-window caching.

    The raw reviews continue to live in the existing ``reviews`` table.  This
    ledger only records which population contract was collected and whether the
    requested window was completed, so we never infer coverage from min/max
    timestamps alone.
    """
    with db_module.get_connection() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS review_collection_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                start_time INTEGER,
                end_time INTEGER,
                languages_json TEXT NOT NULL,
                review_type TEXT NOT NULL,
                purchase_type TEXT NOT NULL,
                collection_order TEXT NOT NULL,
                include_offtopic_activity INTEGER NOT NULL DEFAULT 0,
                requested_max_reviews INTEGER NOT NULL DEFAULT 0,
                fetched_count INTEGER NOT NULL DEFAULT 0,
                matched_count INTEGER NOT NULL DEFAULT 0,
                collection_complete INTEGER NOT NULL DEFAULT 0,
                truncated_by_max_reviews INTEGER NOT NULL DEFAULT 0,
                stop_reason TEXT,
                targeted_date_attempted INTEGER NOT NULL DEFAULT 0,
                targeted_date_applied INTEGER NOT NULL DEFAULT 0,
                collected_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_review_collection_windows_lookup
            ON review_collection_windows(
                app_id, review_type, purchase_type, collection_order,
                include_offtopic_activity, start_time, end_time
            )
        """))


def _review_matches_contract(review: dict, contract: SamplingContract) -> bool:
    timestamp = review.get("timestamp_created")
    try:
        created = int(timestamp) if timestamp is not None else None
    except (TypeError, ValueError):
        created = None

    if contract.start_time is not None:
        if created is None or created < int(contract.start_time):
            return False
    if contract.end_time is not None:
        if created is None or created > int(contract.end_time):
            return False

    if contract.languages != ["all"]:
        language = str(review.get("language") or "").strip().lower()
        if language not in set(contract.languages):
            return False

    if contract.review_type == "positive" and review.get("voted_up") is not True:
        return False
    if contract.review_type == "negative" and review.get("voted_up") is not False:
        return False

    if contract.purchase_type != "all":
        steam_purchase = review.get("steam_purchase")
        if contract.purchase_type == "steam" and steam_purchase is not True:
            return False
        if contract.purchase_type == "non_steam_purchase" and steam_purchase is not False:
            return False

    # Steam's off-topic population flag is not exposed as a stable per-review
    # boolean, so cache compatibility for that dimension is enforced by the
    # coverage ledger rather than guessed here.
    return True


def _sort_reviews(reviews: List[dict], order: str) -> List[dict]:
    if order == "updated":
        key = lambda row: int(row.get("timestamp_updated") or 0)
    elif order == "helpful":
        key = lambda row: float(row.get("weighted_vote_score") or 0.0)
    else:
        key = lambda row: int(row.get("timestamp_created") or 0)
    return sorted(reviews, key=key, reverse=True)


def load_local_reviews(contract: SamplingContract) -> List[dict]:
    rows = storage.load_reviews(contract.app_id)
    matched = [row for row in rows if _review_matches_contract(row, contract)]
    matched = _sort_reviews(matched, contract.collection_order)
    if contract.max_reviews > 0:
        matched = matched[: contract.max_reviews]
    return matched


def _window_contains(row: dict, contract: SamplingContract) -> bool:
    row_start = row.get("start_time")
    row_end = row.get("end_time")

    if contract.start_time is None:
        if row_start is not None:
            return False
    elif row_start is not None and int(row_start) > int(contract.start_time):
        return False

    if contract.end_time is None:
        if row_end is not None:
            return False
    elif row_end is not None and int(row_end) < int(contract.end_time):
        return False

    return True


def _coverage_rows(contract: SamplingContract) -> List[dict]:
    ensure_collection_schema()
    with db_module.get_connection() as conn:
        result = conn.execute(
            text("""
                SELECT id, app_id, start_time, end_time, languages_json,
                       review_type, purchase_type, collection_order,
                       include_offtopic_activity, requested_max_reviews,
                       fetched_count, matched_count, collection_complete,
                       truncated_by_max_reviews, stop_reason,
                       targeted_date_attempted, targeted_date_applied, collected_at
                FROM review_collection_windows
                WHERE app_id = :app_id
                  AND languages_json = :languages_json
                  AND review_type = :review_type
                  AND purchase_type = :purchase_type
                  AND collection_order = :collection_order
                  AND include_offtopic_activity = :include_offtopic_activity
                ORDER BY collected_at DESC, id DESC
            """),
            {
                "app_id": contract.app_id,
                "languages_json": _languages_key(contract.languages),
                "review_type": contract.review_type,
                "purchase_type": contract.purchase_type,
                "collection_order": contract.collection_order,
                "include_offtopic_activity": int(contract.include_offtopic_activity),
            },
        )
        columns = list(result.keys())
        return [dict(zip(columns, row)) for row in result.fetchall()]


def _cache_coverage(contract: SamplingContract) -> Optional[dict]:
    local_reviews = load_local_reviews(contract)
    for row in _coverage_rows(contract):
        if not _window_contains(row, contract):
            continue
        complete = bool(row.get("collection_complete"))
        truncated = bool(row.get("truncated_by_max_reviews"))
        if complete and not truncated:
            return {**row, "local_reviews": local_reviews}
        if contract.max_reviews > 0 and truncated:
            recorded_limit = int(row.get("requested_max_reviews") or 0)
            if recorded_limit >= contract.max_reviews and len(local_reviews) >= contract.max_reviews:
                return {**row, "local_reviews": local_reviews}
    return None


def cached_result(contract: SamplingContract) -> Optional[AcquisitionResult]:
    coverage = _cache_coverage(contract)
    if coverage is None:
        return None
    reviews = list(coverage.pop("local_reviews"))
    stats = {
        "retrieved_reviews": len(reviews),
        "retrieved_count": len(reviews),
        "deduplicated_count": len(reviews),
        "population_reviews_after_scope": len(reviews),
        "collection_complete": bool(coverage.get("collection_complete")),
        "scope_complete": bool(coverage.get("collection_complete")),
        "truncated_by_max_reviews": bool(coverage.get("truncated_by_max_reviews")),
        "stop_reason": "cache_hit",
        "targeted_date_attempted": bool(coverage.get("targeted_date_attempted")),
        "targeted_date_applied": bool(coverage.get("targeted_date_applied")),
        "cache_hit": True,
    }
    return AcquisitionResult(
        reviews=reviews,
        source="cache",
        fetched_count=0,
        stored_count=0,
        cache_hit=True,
        collection_complete=stats["collection_complete"],
        truncated_by_max_reviews=stats["truncated_by_max_reviews"],
        stop_reason="cache_hit",
        stats=stats,
    )


def _record_collection(contract: SamplingContract, result: AcquisitionResult) -> None:
    ensure_collection_schema()
    stats = result.stats
    with db_module.get_connection() as conn:
        conn.execute(
            text("""
                INSERT INTO review_collection_windows(
                    app_id, start_time, end_time, languages_json,
                    review_type, purchase_type, collection_order,
                    include_offtopic_activity, requested_max_reviews,
                    fetched_count, matched_count, collection_complete,
                    truncated_by_max_reviews, stop_reason,
                    targeted_date_attempted, targeted_date_applied, collected_at
                ) VALUES (
                    :app_id, :start_time, :end_time, :languages_json,
                    :review_type, :purchase_type, :collection_order,
                    :include_offtopic_activity, :requested_max_reviews,
                    :fetched_count, :matched_count, :collection_complete,
                    :truncated_by_max_reviews, :stop_reason,
                    :targeted_date_attempted, :targeted_date_applied, :collected_at
                )
            """),
            {
                "app_id": contract.app_id,
                "start_time": contract.start_time,
                "end_time": contract.end_time,
                "languages_json": _languages_key(contract.languages),
                "review_type": contract.review_type,
                "purchase_type": contract.purchase_type,
                "collection_order": contract.collection_order,
                "include_offtopic_activity": int(contract.include_offtopic_activity),
                "requested_max_reviews": contract.max_reviews,
                "fetched_count": result.fetched_count,
                "matched_count": len(result.reviews),
                "collection_complete": int(result.collection_complete),
                "truncated_by_max_reviews": int(result.truncated_by_max_reviews),
                "stop_reason": result.stop_reason,
                "targeted_date_attempted": int(bool(stats.get("targeted_date_attempted"))),
                "targeted_date_applied": int(bool(stats.get("targeted_date_applied"))),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def list_collection_windows(app_id: Optional[int] = None, limit: int = 200) -> List[dict]:
    ensure_collection_schema()
    query = """
        SELECT id, app_id, start_time, end_time, languages_json,
               review_type, purchase_type, collection_order,
               include_offtopic_activity, requested_max_reviews,
               fetched_count, matched_count, collection_complete,
               truncated_by_max_reviews, stop_reason,
               targeted_date_attempted, targeted_date_applied, collected_at
        FROM review_collection_windows
    """
    params: Dict[str, Any] = {"limit": max(1, min(int(limit), 1000))}
    if app_id is not None:
        query += " WHERE app_id = :app_id"
        params["app_id"] = int(app_id)
    query += " ORDER BY collected_at DESC, id DESC LIMIT :limit"
    with db_module.get_connection() as conn:
        result = conn.execute(text(query), params)
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
    for row in rows:
        try:
            row["languages"] = json.loads(row.pop("languages_json"))
        except Exception:
            row["languages"] = ["all"]
        for key in ("collection_complete", "truncated_by_max_reviews", "targeted_date_attempted", "targeted_date_applied", "include_offtopic_activity"):
            row[key] = bool(row.get(key))
    return rows


def _targeted_params(contract: SamplingContract, language: str, cursor: str, per_page: int) -> dict:
    return {
        "json": 1,
        "language": language,
        "purchase_type": contract.purchase_type,
        "review_type": contract.review_type,
        "num_per_page": min(100, max(1, int(per_page))),
        "cursor": cursor,
        "filter": "recent",
        "filter_offtopic_activity": 0 if contract.include_offtopic_activity else 1,
        "start_date": int(contract.start_time),
        "end_date": int(contract.end_time),
        "date_range_type": "include",
    }


def _fetch_targeted_language(
    contract: SamplingContract,
    language: str,
    *,
    max_reviews: int,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> Optional[Tuple[List[dict], dict]]:
    """Try the undocumented storefront date range and validate every page.

    ``None`` means the endpoint did not prove that it honored the requested
    window; callers must fall back to the documented cursor crawl.
    """
    if contract.start_time is None or contract.end_time is None or contract.collection_order != "recent":
        return None

    cursor = "*"
    seen_cursors: set[str] = set()
    seen_ids: set[str] = set()
    reviews: List[dict] = []
    first_page = True

    while True:
        if cursor in seen_cursors:
            return None
        seen_cursors.add(cursor)
        remaining = 100 if max_reviews == 0 else max(1, max_reviews - len(reviews))
        response = steam_api._protected_get(  # internal package call; guarded by validation below
            steam_api.APP_REVIEWS_URL.format(app_id=contract.app_id),
            params=_targeted_params(contract, language, cursor, min(100, remaining)),
            timeout=20,
        )
        data = response.json()
        batch = data.get("reviews") if isinstance(data, dict) else None
        if not isinstance(batch, list):
            return None
        if first_page and not batch:
            # Empty cannot prove support; a fallback crawl is the conservative
            # choice because the requested historical interval may contain data.
            return None
        first_page = False

        for review in batch:
            if not isinstance(review, dict):
                continue
            try:
                created = int(review.get("timestamp_created"))
            except (TypeError, ValueError):
                return None
            if created < int(contract.start_time) or created > int(contract.end_time):
                logger.info(
                    "Steam targeted-date parameters appear ignored for app %s; falling back to cursor crawl",
                    contract.app_id,
                )
                return None
            review_id = str(review.get("recommendationid") or "")
            if review_id and review_id in seen_ids:
                continue
            if review_id:
                seen_ids.add(review_id)
            reviews.append(review)
            if max_reviews > 0 and len(reviews) >= max_reviews:
                return reviews[:max_reviews], {
                    "collection_complete": False,
                    "scope_complete": False,
                    "truncated_by_max_reviews": True,
                    "stop_reason": "max_reviews_reached",
                    "targeted_date_attempted": True,
                    "targeted_date_applied": True,
                }

        if progress_callback is not None:
            progress_callback(len(reviews))

        next_cursor = data.get("cursor") if isinstance(data, dict) else None
        if not next_cursor or not batch:
            return reviews, {
                "collection_complete": True,
                "scope_complete": True,
                "truncated_by_max_reviews": False,
                "stop_reason": "end_of_results",
                "targeted_date_attempted": True,
                "targeted_date_applied": True,
            }
        next_cursor = str(next_cursor)
        if next_cursor == cursor or next_cursor in seen_cursors:
            return None
        cursor = next_cursor


def _fetch_balanced_languages_fallback(
    contract: SamplingContract,
    *,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> Tuple[List[dict], dict]:
    """Fallback multi-language crawl with a bounded *total* request budget.

    The legacy multi-language helper lets each language consume the full
    ``max_reviews`` cap before trimming the merged result.  That can multiply
    network and local work by the number of selected languages.  Acquisition V1
    instead gives each language an equal first-pass quota, so the sum of the
    per-language caps is at most the requested total (apart from integer
    rounding by fewer than the language count).
    """
    languages = list(contract.languages)
    if not languages:
        return [], {
            "retrieved_reviews": 0,
            "retrieved_count": 0,
            "deduplicated_count": 0,
            "population_reviews_after_scope": 0,
            "collection_complete": False,
            "scope_complete": False,
            "truncated_by_max_reviews": False,
            "stop_reason": "invalid_response",
            "language_stats": {},
        }

    per_language_cap = 0 if contract.max_reviews == 0 else max(1, ceil(contract.max_reviews / len(languages)))
    combined: List[dict] = []
    seen_ids: set[str] = set()
    language_stats: Dict[str, dict] = {}
    retrieved_total = 0
    available_values: List[int] = []
    progress_total = 0

    for language in languages:
        language_contract = contract.model_copy(
            update={"languages": [language], "max_reviews": per_language_cap}
        )
        local_stats: Dict[str, Any] = {}
        last_reported = 0

        def language_progress(value: int) -> None:
            nonlocal last_reported, progress_total
            increment = max(0, int(value) - last_reported)
            if increment <= 0:
                return
            last_reported = int(value)
            progress_total += increment
            if progress_callback is not None:
                progress_callback(progress_total)

        rows = steam_api.fetch_reviews(
            contract.app_id,
            count=per_language_cap,
            language=language,
            filter_type=contract.collection_order,
            sampling_contract=language_contract,
            progress_callback=language_progress,
            stats_callback=lambda stats, target=local_stats: target.update(stats),
        )

        retrieved = int(local_stats.get("retrieved_reviews") or local_stats.get("retrieved_count") or len(rows))
        retrieved_total += retrieved
        available = local_stats.get("available_matching_reviews")
        if available is not None:
            available_values.append(int(available))
        complete = bool(local_stats.get("collection_complete", local_stats.get("scope_complete", False)))
        truncated = bool(local_stats.get("truncated_by_max_reviews", False))
        stop_reason = local_stats.get("stop_reason")
        language_stats[language] = {
            "status": "complete" if complete else "incomplete",
            "retrieved": retrieved,
            "population_after_scope": int(local_stats.get("population_reviews_after_scope") or len(rows)),
            "collection_complete": complete,
            "truncated_by_max_reviews": truncated,
            "stop_reason": stop_reason,
        }
        if local_stats.get("error"):
            language_stats[language]["status"] = "failed"
            language_stats[language]["error"] = local_stats.get("error")

        for review in rows:
            review_id = str(review.get("recommendationid") or "")
            if review_id and review_id in seen_ids:
                continue
            if review_id:
                seen_ids.add(review_id)
            combined.append(review)

    combined = _sort_reviews(combined, contract.collection_order)
    if contract.max_reviews > 0:
        combined = combined[: contract.max_reviews]

    aggregate_complete = bool(
        len(language_stats) == len(languages)
        and all(item.get("collection_complete") is True for item in language_stats.values())
    )
    any_failed = any(item.get("status") == "failed" for item in language_stats.values())
    any_truncated = any(bool(item.get("truncated_by_max_reviews")) for item in language_stats.values())
    if any_failed:
        aggregate_stop_reason = "api_failure"
    elif any_truncated:
        aggregate_stop_reason = "max_reviews_reached"
    elif aggregate_complete:
        aggregate_stop_reason = "end_of_results"
    else:
        aggregate_stop_reason = next(
            (item.get("stop_reason") for item in language_stats.values() if item.get("stop_reason")),
            "invalid_response",
        )

    return combined, {
        "retrieved_reviews": retrieved_total,
        "retrieved_count": retrieved_total,
        "deduplicated_count": len(combined),
        "population_reviews_after_scope": len(combined),
        "collection_complete": aggregate_complete,
        "scope_complete": aggregate_complete,
        "truncated_by_max_reviews": any_truncated,
        "stop_reason": aggregate_stop_reason,
        "language_stats": language_stats,
        "available_matching_reviews": sum(available_values) if len(available_values) == len(languages) else None,
        "deduplication_policy": "transport review-id duplicates only; duplicate text is retained",
    }


def _fetch_from_steam(
    contract: SamplingContract,
    *,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> Tuple[List[dict], dict]:
    targeted_attempted = bool(
        contract.start_time is not None
        and contract.end_time is not None
        and contract.collection_order == "recent"
    )

    # ``all`` is already a single Steam population; do not fan it out.
    languages = contract.languages
    if targeted_attempted:
        if languages == ["all"]:
            targeted = _fetch_targeted_language(
                contract,
                "all",
                max_reviews=contract.max_reviews,
                progress_callback=progress_callback,
            )
            if targeted is not None:
                reviews, stats = targeted
                stats.update({
                    "retrieved_reviews": len(reviews),
                    "retrieved_count": len(reviews),
                    "deduplicated_count": len(reviews),
                    "population_reviews_after_scope": len(reviews),
                })
                return reviews, stats
        else:
            # Keep the user-visible cap a total cap.  Equal first-pass quotas
            # avoid the old N-per-language request explosion on personal PCs.
            per_language_cap = 0 if contract.max_reviews == 0 else max(1, ceil(contract.max_reviews / len(languages)))
            combined: List[dict] = []
            seen_ids: set[str] = set()
            targeted_ok = True
            language_stats: Dict[str, dict] = {}
            for language in languages:
                targeted = _fetch_targeted_language(contract, language, max_reviews=per_language_cap)
                if targeted is None:
                    targeted_ok = False
                    break
                rows, stats = targeted
                language_stats[language] = stats
                for review in rows:
                    rid = str(review.get("recommendationid") or "")
                    if rid and rid in seen_ids:
                        continue
                    if rid:
                        seen_ids.add(rid)
                    combined.append(review)
            if targeted_ok:
                combined = _sort_reviews(combined, contract.collection_order)
                if contract.max_reviews > 0:
                    combined = combined[: contract.max_reviews]
                complete = all(bool(item.get("collection_complete")) for item in language_stats.values())
                truncated = any(bool(item.get("truncated_by_max_reviews")) for item in language_stats.values())
                return combined, {
                    "retrieved_reviews": len(combined),
                    "retrieved_count": len(combined),
                    "deduplicated_count": len(combined),
                    "population_reviews_after_scope": len(combined),
                    "collection_complete": complete,
                    "scope_complete": complete,
                    "truncated_by_max_reviews": truncated,
                    "stop_reason": "max_reviews_reached" if truncated else "end_of_results",
                    "language_stats": language_stats,
                    "targeted_date_attempted": True,
                    "targeted_date_applied": True,
                }

    fallback_stats: Dict[str, Any] = {}
    if len(contract.languages) > 1:
        reviews, fallback_stats = _fetch_balanced_languages_fallback(
            contract,
            progress_callback=progress_callback,
        )
    else:
        reviews = steam_api.fetch_reviews(
            contract.app_id,
            count=contract.max_reviews,
            language=contract.languages[0],
            filter_type=contract.collection_order,
            sampling_contract=contract,
            progress_callback=progress_callback,
            stats_callback=lambda stats: fallback_stats.update(stats),
        )
    fallback_stats["targeted_date_attempted"] = targeted_attempted
    fallback_stats["targeted_date_applied"] = False
    return reviews, fallback_stats


def collect_reviews(
    contract: SamplingContract,
    *,
    force: bool = True,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> AcquisitionResult:
    """Acquire and persist one review population without invoking any LLM."""
    if not force:
        cached = cached_result(contract)
        if cached is not None:
            return cached

    reviews, stats = _fetch_from_steam(contract, progress_callback=progress_callback)
    stored_count = storage.upsert_reviews(contract.app_id, reviews)
    complete = bool(stats.get("collection_complete", stats.get("scope_complete", False)))
    truncated = bool(stats.get("truncated_by_max_reviews", False))
    result = AcquisitionResult(
        reviews=reviews,
        source="steam",
        fetched_count=int(stats.get("retrieved_reviews") or stats.get("retrieved_count") or len(reviews)),
        stored_count=stored_count,
        cache_hit=False,
        collection_complete=complete,
        truncated_by_max_reviews=truncated,
        stop_reason=stats.get("stop_reason"),
        stats=stats,
    )
    _record_collection(contract, result)
    return result


def ensure_reviews(
    contract: SamplingContract,
    *,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> AcquisitionResult:
    """Reuse a compatible local population or fetch it once and persist it."""
    cached = cached_result(contract)
    if cached is not None:
        if progress_callback is not None:
            progress_callback(len(cached.reviews))
        return cached
    return collect_reviews(contract, force=True, progress_callback=progress_callback)


__all__ = [
    "AcquisitionResult",
    "cached_result",
    "collect_reviews",
    "ensure_collection_schema",
    "ensure_reviews",
    "list_collection_windows",
    "load_local_reviews",
]
