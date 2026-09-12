"""Utilities for interacting with Steam's public store API for reviews."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import re
import threading
import time
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from .circuit_breaker import steam_api_breaker, CircuitOpenError
from .sampling import SamplingContract

logger = logging.getLogger(__name__)

# In-memory cache for game context with TTL
_CONTEXT_CACHE: Dict[int, Tuple[Dict, float]] = {}
_CONTEXT_CACHE_LOCK = threading.Lock()
_CONTEXT_CACHE_TTL_SECONDS = 3600  # 1 hour

STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch"
APP_REVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"
APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"


@dataclass
class AppSearchResult:
    appid: int
    name: str
    price: Optional[str]
    url: str
    image_url: Optional[str] = None


class SteamAPIError(RuntimeError):
    """Raised when the Steam API returns an unexpected response."""


_GAME_URL_RE = re.compile(r"/app/(\d+)")
_DEFAULT_HEADERS = {
    "User-Agent": "SentiNext/0.1 (+https://sentinext.local)",
}
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def _get_with_retries(
    url: str,
    *,
    params: Optional[Dict] = None,
    timeout: int = 15,
    retries: int = 3,
    backoff: float = 0.6,
) -> requests.Response:
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=timeout,
                headers=_DEFAULT_HEADERS,
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt == retries:
                raise SteamAPIError(f"Request to {url} failed: {exc}") from exc
        else:
            if response.status_code == 200:
                return response
            if response.status_code not in _RETRY_STATUS_CODES or attempt == retries:
                truncated = response.text[:200] if response.text else ""
                raise SteamAPIError(
                    f"Request to {url} failed with status code {response.status_code}: {truncated}"
                )
        time.sleep(backoff * attempt)

    raise SteamAPIError(f"Request to {url} failed after {retries} attempts: {last_error}")


def _protected_get(
    url: str,
    *,
    params: Optional[Dict] = None,
    timeout: int = 15,
    retries: int = 3,
    backoff: float = 0.6,
) -> requests.Response:
    """Execute GET request with circuit breaker protection.

    Wraps _get_with_retries with the Steam API circuit breaker to prevent
    cascading failures when the Steam API is unavailable.
    """
    try:
        return steam_api_breaker.call(
            _get_with_retries,
            url,
            params=params,
            timeout=timeout,
            retries=retries,
            backoff=backoff,
        )
    except CircuitOpenError as exc:
        logger.warning("Steam API circuit open: %s", exc)
        raise SteamAPIError(
            f"Steam API temporarily unavailable (circuit open). Retry after {exc.retry_after:.1f}s"
        ) from exc


def extract_app_id_from_input(value: str) -> Optional[int]:
    """Try to pull an app id from raw user input (numeric id or store URL)."""
    value = value.strip()
    if value.isdigit():
        return int(value)

    match = _GAME_URL_RE.search(value)
    if match:
        return int(match.group(1))

    return None


def search_applications(query: str, limit: int = 5) -> List[AppSearchResult]:
    """Search the Steam store for applications that match the query."""
    params = {
        "term": query,
        "l": "english",
        "cc": "US",
    }
    resp = _protected_get(STORE_SEARCH_URL, params=params, timeout=15)

    payload = resp.json()
    items = payload.get("items", []) if isinstance(payload, dict) else []

    results: List[AppSearchResult] = []
    for row in items[:limit]:
        try:
            appid = int(row["id"])
        except (KeyError, ValueError, TypeError):
            continue
        image_url = None
        if isinstance(row, dict):
            image_url = row.get("tiny_image") or row.get("header_image") or row.get("capsule_image")
        results.append(
            AppSearchResult(
                appid=appid,
                name=row.get("name", "Unknown title"),
                price=row.get("final_formatted"),
                url=f"https://store.steampowered.com/app/{appid}",
                image_url=image_url,
            )
        )

    return results


REVIEW_METADATA_FIELDS: Dict[str, str] = {
    "recommendationid": "Unique review identifier",
    "language": "Language the review was written in",
    "review": "Full review text",
    "timestamp_created": "Unix timestamp when the review was created",
    "timestamp_updated": "Unix timestamp when the review was last updated",
    "voted_up": "Whether the reviewer marked the game as recommended",
    "votes_up": "Number of users who found this review helpful",
    "votes_funny": "Number of users who found this review funny",
    "weighted_vote_score": "Wilson score representation of helpful votes",
    "comment_count": "Number of comments on the review",
    "steam_purchase": "If the copy was purchased via Steam",
    "received_for_free": "If the reviewer received the game for free",
    "written_during_early_access": "Whether the review was written during early access",
    "developer_response": "Text of developer response, if any",
    "timestamp_dev_responded": "Unix timestamp of developer response, if any",
    "primarily_steam_deck": "Whether reviewer primarily played on Steam Deck",
}

AUTHOR_METADATA_FIELDS: Dict[str, str] = {
    "steamid": "Reviewer's SteamID",
    "num_games_owned": "Total number of games the reviewer owns",
    "num_reviews": "How many reviews the user has written",
    "playtime_forever": "Lifetime playtime in minutes",
    "playtime_last_two_weeks": "Last 2 weeks playtime in minutes",
    "playtime_at_review": "Playtime in minutes when the review was written",
    "deck_playtime_at_review": "Steam Deck playtime when review was written",
    "last_played": "Unix timestamp of last play session",
}


def _legacy_collection_order(filter_type: str) -> str:
    normalized = (filter_type or "recent").strip().lower()
    if normalized in {"all", "best", "helpful"}:
        return "helpful"
    if normalized == "updated":
        return "updated"
    return "recent"


def _steam_filter(collection_order: str) -> str:
    # Steam calls the helpfulness mode ``all``.  STRA keeps the research name
    # ``helpful`` so provenance never claims that it collected all reviews.
    return "all" if collection_order == "helpful" else collection_order


def _build_review_params(
    contract: SamplingContract,
    *,
    language: str,
    cursor: str,
    num_per_page: int,
    day_range: Optional[int] = None,
) -> Dict[str, object]:
    params: Dict[str, object] = {
        "json": 1,
        "language": language,
        "purchase_type": contract.purchase_type,
        "review_type": contract.review_type,
        "num_per_page": min(100, max(1, num_per_page)),
        "cursor": cursor,
        "filter": _steam_filter(contract.collection_order),
        # Steam's documented default is to exclude off-topic activity.  Pass
        # the value explicitly so the population contract is auditable.
        "filter_offtopic_activity": 0 if contract.include_offtopic_activity else 1,
    }
    # day_range is only meaningful for Steam's helpfulness/sliding-window
    # mode.  It is retained for legacy callers but is never used to represent
    # an arbitrary start/end research window.
    if day_range is not None and contract.collection_order == "helpful":
        params["day_range"] = max(1, min(int(day_range), 365))
    return params


def _emit_fetch_stats(stats_callback: Optional[callable], stats: dict) -> None:
    if stats_callback is None:
        return
    try:
        stats_callback(stats)
    except Exception:
        logger.debug("Fetch stats callback failed", exc_info=True)


def _fetch_reviews_contract(
    contract: SamplingContract,
    *,
    day_range: Optional[int] = None,
    legacy_stop_before_timestamp: Optional[int] = None,
    progress_callback: Optional[callable] = None,
    stats_callback: Optional[callable] = None,
) -> List[dict]:
    """Acquire one population using the supplied contract.

    Steam's ``recent`` mode is used for arbitrary creation-time windows.  The
    lower-bound stop rule is page-level: every review on the page must have a
    creation timestamp at or before the lower boundary.  A single old review
    therefore never terminates the crawl while another review on that page is
    still newer.
    """
    lower_boundary = contract.start_time if contract.start_time is not None else legacy_stop_before_timestamp
    raw_reviews: List[dict] = []
    population: List[dict] = []
    cursor = "*"
    seen_review_ids: set[str] = set()
    seen_cursors: set[str] = set()
    first_summary = True
    steam_num_reviews: Optional[int] = None
    steam_total_reviews: Optional[int] = None
    # A missing lower boundary means there is no boundary stop condition; it
    # must not short-circuit pagination.  The emitted ``lower_boundary_reached``
    # flag below treats that unconstrained case as trivially satisfied.
    boundary_reached = False
    collection_complete = False
    truncated_by_max_reviews = False
    stop_reason: Optional[str] = None
    stop_error: Optional[str] = None

    def _stats() -> dict:
        return {
            "steam_num_reviews": steam_num_reviews,
            "steam_total_reviews": steam_total_reviews,
            "available_matching_reviews": (
                steam_total_reviews
                if contract.collection_order != "helpful" and contract.start_time is None and contract.end_time is None
                else None
            ),
            "retrieved_reviews": len(raw_reviews),
            "retrieved_count": len(raw_reviews),
            "deduplicated_count": len(raw_reviews),
            "population_reviews_after_scope": len(population),
            "collection_complete": collection_complete,
            # Backward-compatible alias; callers should use collection_complete.
            "scope_complete": collection_complete,
            "truncated_by_max_reviews": truncated_by_max_reviews,
            "stop_reason": stop_reason,
            "lower_boundary_reached": lower_boundary is None or boundary_reached,
            "error": stop_error,
        }

    while True:
        if contract.max_reviews > 0 and len(population) >= contract.max_reviews:
            stop_reason = "max_reviews_reached"
            truncated_by_max_reviews = True
            break
        if cursor in seen_cursors:
            stop_reason = "cursor_repeated"
            break
        seen_cursors.add(cursor)

        remaining = 100 if contract.unlimited else max(1, contract.max_reviews - len(population))
        params = _build_review_params(
            contract,
            language=contract.languages[0],
            cursor=cursor,
            num_per_page=remaining,
            day_range=day_range,
        )
        try:
            resp = _protected_get(APP_REVIEWS_URL.format(app_id=contract.app_id), params=params, timeout=20)
        except Exception as exc:
            stop_reason = "api_failure"
            stop_error = str(exc)
            _emit_fetch_stats(stats_callback, _stats())
            raise
        try:
            data = resp.json()
        except Exception as exc:
            stop_reason = "invalid_response"
            stop_error = str(exc)
            break
        if not isinstance(data, dict):
            stop_reason = "invalid_response"
            break

        if first_summary:
            first_summary = False
            query_summary = data.get("query_summary")
            if isinstance(query_summary, dict):
                try:
                    steam_num_reviews = int(query_summary["num_reviews"]) if query_summary.get("num_reviews") is not None else None
                except (TypeError, ValueError):
                    steam_num_reviews = None
                try:
                    steam_total_reviews = int(query_summary["total_reviews"]) if query_summary.get("total_reviews") is not None else None
                except (TypeError, ValueError):
                    steam_total_reviews = None

        if data.get("success") is False:
            stop_reason = "api_failure"
            stop_error = str(data.get("error") or "Steam returned success=false")
            break
        if "reviews" not in data or not isinstance(data.get("reviews"), list):
            stop_reason = "invalid_response"
            break
        batch = data["reviews"]
        if not batch:
            stop_reason = "end_of_results"
            collection_complete = True
            break

        new_batch: List[dict] = []
        for review in batch:
            if not isinstance(review, dict):
                continue
            review_id = str(review.get("recommendationid") or "")
            # Repeated IDs are pagination transport duplicates.  Distinct
            # reviews with identical text are intentionally retained.
            if review_id and review_id in seen_review_ids:
                continue
            if review_id:
                seen_review_ids.add(review_id)
            new_batch.append(review)
        if not new_batch:
            next_cursor = data.get("cursor")
            stop_reason = "cursor_repeated" if not next_cursor or next_cursor == cursor else "invalid_response"
            break

        raw_reviews.extend(new_batch)
        for review in new_batch:
            timestamp = review.get("timestamp_created")
            try:
                timestamp_value = int(timestamp) if timestamp is not None else None
            except (TypeError, ValueError):
                timestamp_value = None
            if contract.start_time is not None or contract.end_time is not None:
                if timestamp_value is None:
                    continue
                if contract.start_time is not None and timestamp_value < contract.start_time:
                    continue
                if contract.end_time is not None and timestamp_value > contract.end_time:
                    continue
            population.append(review)

        timestamps: List[int] = []
        for review in new_batch:
            try:
                timestamps.append(int(review["timestamp_created"]))
            except (KeyError, TypeError, ValueError):
                pass
        if lower_boundary is not None and len(timestamps) == len(new_batch) and max(timestamps) <= int(lower_boundary):
            boundary_reached = True

        _emit_fetch_stats(stats_callback, {
            # ``num_reviews`` is the number returned in this response, not a
            # population total.  ``total_reviews`` is retained separately.
            "steam_num_reviews": steam_num_reviews,
            "steam_total_reviews": steam_total_reviews,
            "available_matching_reviews": (
                steam_total_reviews
                if contract.collection_order != "helpful" and contract.start_time is None and contract.end_time is None
                else None
            ),
            "retrieved_reviews": len(raw_reviews),
            "retrieved_count": len(raw_reviews),
            "deduplicated_count": len(raw_reviews),
            "population_reviews_after_scope": len(population),
            "collection_complete": collection_complete,
            "scope_complete": collection_complete,
            "truncated_by_max_reviews": truncated_by_max_reviews,
            "stop_reason": stop_reason,
            "lower_boundary_reached": lower_boundary is None or boundary_reached,
            "error": stop_error,
        })
        if progress_callback is not None:
            try:
                progress_callback(len(raw_reviews))
            except Exception:
                logger.debug("Fetch progress callback failed", exc_info=True)

        if lower_boundary is not None and boundary_reached:
            stop_reason = "lower_boundary_reached"
            collection_complete = True
            break
        next_cursor = data.get("cursor")
        if next_cursor == cursor or (next_cursor and str(next_cursor) in seen_cursors):
            stop_reason = "cursor_repeated"
            break
        if not next_cursor:
            if contract.max_reviews > 0 and len(population) >= contract.max_reviews:
                stop_reason = "end_of_results"
                collection_complete = True
            else:
                stop_reason = "end_of_results"
                collection_complete = True
            break
        if contract.max_reviews > 0 and len(population) >= contract.max_reviews:
            stop_reason = "max_reviews_reached"
            truncated_by_max_reviews = True
            break
        cursor = str(next_cursor)

    # A helpfulness query is a sliding window, so its total is not a reliable
    # population denominator.  Time-window results are post-fetch subsets and
    # likewise cannot inherit Steam's unscoped total.
    if stop_reason is None:
        stop_reason = "invalid_response"
    _emit_fetch_stats(stats_callback, _stats())
    if contract.max_reviews > 0:
        return population[: contract.max_reviews]
    return population


def fetch_reviews(
    app_id: int,
    count: int = 100,
    language: str = "english",
    filter_type: str = "recent",
    day_range: Optional[int] = None,
    include_review_bombs: bool = False,
    stop_before_timestamp: Optional[int] = None,
    progress_callback: Optional[callable] = None,
    stats_callback: Optional[callable] = None,
    sampling_contract: Optional[SamplingContract] = None,
) -> List[dict]:
    """Compatibility wrapper routed through :class:`SamplingContract`."""
    contract = sampling_contract or SamplingContract(
        app_id=app_id,
        languages=[language or "all"],
        collection_order=_legacy_collection_order(filter_type),
        include_offtopic_activity=include_review_bombs,
        max_reviews=count,
    )
    if contract.app_id != app_id:
        raise ValueError("sampling_contract.app_id must match app_id")
    return _fetch_reviews_contract(
        contract,
        day_range=day_range,
        legacy_stop_before_timestamp=stop_before_timestamp,
        progress_callback=progress_callback,
        stats_callback=stats_callback,
    )


def resolve_app_id(user_input: str) -> Optional[int]:
    """Resolve the best app id for the given user input."""
    direct_app_id = extract_app_id_from_input(user_input)
    if direct_app_id is not None:
        return direct_app_id

    results = search_applications(user_input, limit=1)
    if not results:
        return None

    return results[0].appid


def _fetch_app_details_uncached(app_id: int) -> Optional[Dict]:
    """Fetch game details from Steam's appdetails API (no caching)."""
    params = {"appids": app_id}
    try:
        resp = _protected_get(APP_DETAILS_URL, params=params, timeout=15)

        data = resp.json()
        if not data or str(app_id) not in data:
            return None

        app_data = data[str(app_id)]
        if not app_data.get("success"):
            return None

        details = app_data.get("data", {})
        if not details:
            return None

        # Extract relevant fields
        result = {
            "name": details.get("name", ""),
            "short_description": details.get("short_description", ""),
            "type": details.get("type", "game"),
            "header_image": details.get("header_image", ""),
        }

        # Extract genres
        genres = details.get("genres", [])
        result["genres"] = [g.get("description", "") for g in genres if isinstance(g, dict)]

        # Extract categories (single-player, multiplayer, etc.)
        categories = details.get("categories", [])
        result["categories"] = [c.get("description", "") for c in categories if isinstance(c, dict)]

        # Extract price info
        is_free = details.get("is_free", False)
        price_overview = details.get("price_overview", {})
        if is_free:
            result["price_final"] = "Free"
            result["price_initial"] = None
            result["is_free"] = True
            result["price_discount"] = 0
            result["price_currency"] = None
        elif price_overview:
            # Convert cents to major currency units (e.g., $29.99)
            initial_cents = price_overview.get("initial", 0)
            final_cents = price_overview.get("final", 0)
            result["price_initial"] = float(initial_cents) / 100.0 if initial_cents else None
            result["price_final"] = float(final_cents) / 100.0 if final_cents else None
            result["price_initial_formatted"] = price_overview.get("initial_formatted", "")
            result["price_final_formatted"] = price_overview.get("final_formatted", "")
            result["price_discount"] = int(price_overview.get("discount_percent", 0))
            result["price_currency"] = price_overview.get("currency", "USD")
            result["is_free"] = False
        else:
            result["price_final"] = None
            result["price_initial"] = None
            result["is_free"] = False
            result["price_discount"] = 0
            result["price_currency"] = None

        # Extract release date
        release_date = details.get("release_date", {})
        result["release_date"] = release_date.get("date", None)
        result["coming_soon"] = release_date.get("coming_soon", False)

        # Extract developers and publishers
        result["developers"] = details.get("developers", [])
        result["publishers"] = details.get("publishers", [])

        return result

    except Exception:
        return None


def fetch_app_details(app_id: int, use_cache: bool = True) -> Optional[Dict]:
    """Fetch game details from Steam's appdetails API.

    Returns a dict with: name, short_description, genres, categories, tags (if available).
    Returns None if the request fails or app is not found.

    Results are cached in-memory for 1 hour to reduce API calls.
    """
    if use_cache:
        with _CONTEXT_CACHE_LOCK:
            if app_id in _CONTEXT_CACHE:
                cached_result, cached_time = _CONTEXT_CACHE[app_id]
                if time.time() - cached_time < _CONTEXT_CACHE_TTL_SECONDS:
                    return cached_result
                # Cache expired, remove it
                del _CONTEXT_CACHE[app_id]

    result = _fetch_app_details_uncached(app_id)

    if result is not None and use_cache:
        with _CONTEXT_CACHE_LOCK:
            _CONTEXT_CACHE[app_id] = (result, time.time())

    return result


def clear_app_details_cache(app_id: Optional[int] = None) -> None:
    """Clear the app details cache. If app_id is provided, only clear that entry."""
    with _CONTEXT_CACHE_LOCK:
        if app_id is not None:
            _CONTEXT_CACHE.pop(app_id, None)
        else:
            _CONTEXT_CACHE.clear()


def fetch_reviews_multi_language(
    app_id: int,
    count: int = 100,
    languages: Optional[List[str]] = None,
    filter_type: str = "recent",
    day_range: Optional[int] = None,
    include_review_bombs: bool = False,
    progress_callback: Optional[callable] = None,
    stats_callback: Optional[callable] = None,
    sampling_contract: Optional[SamplingContract] = None,
) -> List[dict]:
    """Fetch a multi-language population through one contract implementation.

    Languages are fetched independently because Steam accepts one language per
    request.  We do not divide ``count`` across languages (which would silently
    rebalance the population); each language uses the same contract cap and the
    combined population is capped only after scope filtering.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    contract = sampling_contract or SamplingContract(
        app_id=app_id,
        languages=languages or ["all"],
        collection_order=_legacy_collection_order(filter_type),
        include_offtopic_activity=include_review_bombs,
        max_reviews=count,
    )
    if contract.app_id != app_id:
        raise ValueError("sampling_contract.app_id must match app_id")
    if contract.languages == ["all"]:
        return _fetch_reviews_contract(contract, day_range=day_range, progress_callback=progress_callback, stats_callback=stats_callback)

    total_fetched = [0]
    aggregate_stats: dict[str, object] = {}
    available_values: List[int] = []
    scope_complete_values: List[bool] = []
    language_stats: dict[str, dict] = {}
    progress_lock = threading.Lock()

    def report_progress(fetched: int) -> None:
        if progress_callback is None:
            return
        with progress_lock:
            total_fetched[0] += fetched
            try:
                progress_callback(total_fetched[0])
            except Exception:
                logger.debug("Multi-language progress callback failed", exc_info=True)

    def fetch_single_language(lang: str) -> Tuple[str, List[dict], dict]:
        language_contract = contract.model_copy(update={"languages": [lang]})
        local_stats: dict = {}
        last_reported = [0]

        def lang_progress(fetched: int) -> None:
            increment = fetched - last_reported[0]
            if increment > 0:
                last_reported[0] = fetched
                report_progress(increment)

        def lang_stats(stats: dict) -> None:
            local_stats.update(stats)

        try:
            reviews = _fetch_reviews_contract(language_contract, day_range=day_range, progress_callback=lang_progress, stats_callback=lang_stats)
            return (lang, reviews, local_stats)
        except Exception as e:
            logger.warning(f"Failed to fetch {lang} reviews for app {app_id}: {e}")
            local_stats.setdefault("collection_complete", False)
            local_stats.setdefault("scope_complete", False)
            local_stats.setdefault("truncated_by_max_reviews", False)
            local_stats.setdefault("stop_reason", "api_failure")
            local_stats.setdefault("error", str(e))
            return (lang, [], local_stats)

    all_reviews: List[dict] = []
    seen_ids: set = set()

    max_workers = min(4, len(contract.languages))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_single_language, lang) for lang in contract.languages]

        for future in as_completed(futures):
            lang, reviews, local_stats = future.result()
            for key in ("retrieved_reviews", "retrieved_count", "population_reviews_after_scope"):
                aggregate_stats[key] = int(aggregate_stats.get(key) or 0) + int(local_stats.get(key) or 0)
            available = local_stats.get("available_matching_reviews")
            if available is not None:
                available_values.append(int(available))
            complete = bool(local_stats.get("collection_complete", local_stats.get("scope_complete", False)))
            scope_complete_values.append(complete)
            stop_reason = local_stats.get("stop_reason")
            error = local_stats.get("error")
            if complete:
                status = "complete"
            elif stop_reason in {"api_failure", "invalid_response"} or error:
                status = "failed"
            else:
                status = "incomplete"
            language_stats[lang] = {
                "status": status,
                "retrieved": int(local_stats.get("retrieved_reviews") or local_stats.get("retrieved_count") or 0),
                "population_after_scope": int(local_stats.get("population_reviews_after_scope") or 0),
                "collection_complete": complete,
                "truncated_by_max_reviews": bool(local_stats.get("truncated_by_max_reviews", False)),
                "stop_reason": stop_reason,
            }
            if error:
                language_stats[lang]["error"] = error
            for review in reviews:
                review_id = review.get("recommendationid")
                if review_id and review_id not in seen_ids:
                    seen_ids.add(review_id)
                    all_reviews.append(review)

    if contract.collection_order == "updated":
        all_reviews.sort(key=lambda r: r.get("timestamp_updated", 0), reverse=True)
    elif contract.collection_order == "helpful":
        all_reviews.sort(key=lambda r: r.get("weighted_vote_score", 0), reverse=True)
    else:
        all_reviews.sort(key=lambda r: r.get("timestamp_created", 0), reverse=True)
    population = all_reviews if contract.unlimited else all_reviews[: contract.max_reviews]
    retrieved_total = int(aggregate_stats.get("retrieved_reviews") or 0)
    aggregate_complete = bool(
        len(language_stats) == len(contract.languages)
        and all(item.get("collection_complete") is True for item in language_stats.values())
    )
    if aggregate_complete:
        aggregate_stop_reason = "end_of_results"
    elif any(item.get("status") == "failed" for item in language_stats.values()):
        aggregate_stop_reason = "api_failure"
    elif any(item.get("truncated_by_max_reviews") for item in language_stats.values()):
        aggregate_stop_reason = "max_reviews_reached"
    else:
        aggregate_stop_reason = next(
            (item.get("stop_reason") for item in language_stats.values() if item.get("stop_reason")),
            "invalid_response",
        )
    aggregate_stats.update({
        # Keep retrieval counts as the number of raw review records received
        # from Steam.  ``deduplicated_count`` is the post-ID-dedup population.
        "retrieved_reviews": retrieved_total,
        "retrieved_count": retrieved_total,
        "deduplicated_count": len(all_reviews),
        "population_reviews_after_scope": len(population),
        "collection_complete": aggregate_complete,
        "scope_complete": aggregate_complete,
        "truncated_by_max_reviews": any(bool(item.get("truncated_by_max_reviews")) for item in language_stats.values()),
        "stop_reason": aggregate_stop_reason,
        "language_stats": language_stats,
        "available_matching_reviews": sum(available_values) if len(available_values) == len(contract.languages) else None,
        "deduplication_policy": "transport review-id duplicates only; duplicate text is retained",
    })
    if contract.start_time is not None or contract.end_time is not None:
        aggregate_stats["available_matching_reviews"] = None
    _emit_fetch_stats(stats_callback, aggregate_stats)
    return population


# Steam language codes mapping (display name -> API code)
STEAM_LANGUAGES = {
    "english": "english",
    "german": "german",
    "french": "french",
    "spanish": "spanish",
    "italian": "italian",
    "polish": "polish",
    "portuguese": "portuguese",
    "brazilian": "brazilian",
    "russian": "russian",
    "turkish": "turkish",
    "japanese": "japanese",
    "koreana": "koreana",
    "schinese": "schinese",
    "tchinese": "tchinese",
    "thai": "thai",
    "czech": "czech",
    "danish": "danish",
    "dutch": "dutch",
    "finnish": "finnish",
    "greek": "greek",
    "hungarian": "hungarian",
    "norwegian": "norwegian",
    "romanian": "romanian",
    "swedish": "swedish",
    "ukrainian": "ukrainian",
    "vietnamese": "vietnamese",
    "arabic": "arabic",
    "indonesian": "indonesian",
}


def iter_review_fields() -> Iterable[str]:
    """Return all review-level fields available from the API."""
    return REVIEW_METADATA_FIELDS.keys()


def iter_author_fields() -> Iterable[str]:
    """Return all author-level fields available from the API."""
    return AUTHOR_METADATA_FIELDS.keys()


# ============================================================================
# Steam Web API Endpoints (News, Players, Achievements)
# ============================================================================

STEAM_NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2"
STEAM_PLAYER_COUNT_URL = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1"
STEAM_ACHIEVEMENTS_URL = "https://api.steampowered.com/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2"
STEAM_ACHIEVEMENT_SCHEMA_URL = "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2"


@dataclass
class NewsItem:
    """Represents a Steam news/announcement item."""
    gid: str  # Unique news item ID
    title: str
    url: str
    author: str
    contents: str  # Can be HTML or BBCode
    feed_label: str  # e.g., "Community Announcements", "Patch Notes"
    date: int  # Unix timestamp
    feed_name: str
    feed_type: int  # 0 = unknown, 1 = Steam announcements, 2 = Steam news


def fetch_news_for_app(
    app_id: int,
    count: int = 20,
    max_length: int = 500,
) -> List[NewsItem]:
    """Fetch news/announcements for a Steam application.

    Uses ISteamNews/GetNewsForApp endpoint to retrieve patch notes,
    announcements, and updates.

    Args:
        app_id: Steam application ID
        count: Maximum number of news items to return (default 20)
        max_length: Maximum length of contents field (0 for full content)

    Returns:
        List of NewsItem objects sorted by date (newest first)
    """
    params = {
        "appid": app_id,
        "count": count,
        "maxlength": max_length,
        "format": "json",
    }

    try:
        resp = _protected_get(STEAM_NEWS_URL, params=params, timeout=15)
        data = resp.json()

        app_news = data.get("appnews", {})
        news_items = app_news.get("newsitems", [])

        results: List[NewsItem] = []
        for item in news_items:
            try:
                results.append(
                    NewsItem(
                        gid=str(item.get("gid", "")),
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        author=item.get("author", ""),
                        contents=item.get("contents", ""),
                        feed_label=item.get("feedlabel", ""),
                        date=item.get("date", 0),
                        feed_name=item.get("feedname", ""),
                        feed_type=item.get("feed_type", 0),
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to parse news item: {e}")
                continue

        return results

    except SteamAPIError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch news for app {app_id}: {e}")
        return []


def fetch_current_players(app_id: int) -> Optional[int]:
    """Fetch the current number of players for a Steam application.

    Uses ISteamUserStats/GetNumberOfCurrentPlayers endpoint.

    Args:
        app_id: Steam application ID

    Returns:
        Current player count, or None if unavailable
    """
    params = {
        "appid": app_id,
        "format": "json",
    }

    try:
        resp = _protected_get(STEAM_PLAYER_COUNT_URL, params=params, timeout=10)
        data = resp.json()

        response = data.get("response", {})
        if response.get("result") == 1:
            return response.get("player_count")
        return None

    except SteamAPIError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch player count for app {app_id}: {e}")
        return None


@dataclass
class AchievementStat:
    """Global achievement percentage data."""
    name: str  # Internal achievement name/API name
    percent: float  # Percentage of players who earned this (0-100)


@dataclass
class AchievementInfo:
    """Full achievement info including display name and icon."""
    name: str  # Internal API name
    display_name: str  # Localized display name
    description: str  # Achievement description
    icon: str  # URL to unlocked icon
    icon_gray: str  # URL to locked icon
    hidden: bool  # Whether achievement is hidden until unlocked


def fetch_global_achievements(app_id: int) -> List[AchievementStat]:
    """Fetch global achievement percentages for a Steam application.

    Uses ISteamUserStats/GetGlobalAchievementPercentagesForApp endpoint.

    Args:
        app_id: Steam application ID

    Returns:
        List of AchievementStat objects sorted by percentage (highest first)
    """
    params = {
        "gameid": app_id,
        "format": "json",
    }

    try:
        resp = _protected_get(STEAM_ACHIEVEMENTS_URL, params=params, timeout=15)
        data = resp.json()

        achievement_percentages = data.get("achievementpercentages", {})
        achievements = achievement_percentages.get("achievements", [])

        results: List[AchievementStat] = []
        for ach in achievements:
            try:
                results.append(
                    AchievementStat(
                        name=ach.get("name", ""),
                        percent=float(ach.get("percent", 0)),
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse achievement stat: {e}")
                continue

        # Sort by percentage descending (most common achievements first)
        results.sort(key=lambda x: x.percent, reverse=True)
        return results

    except SteamAPIError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch achievements for app {app_id}: {e}")
        return []


def fetch_achievement_schema(app_id: int) -> List[AchievementInfo]:
    """Fetch achievement schema (names, descriptions, icons) for a Steam application.

    Uses ISteamUserStats/GetSchemaForGame endpoint.
    Note: Some games may not expose their schema publicly.

    Args:
        app_id: Steam application ID

    Returns:
        List of AchievementInfo objects
    """
    params = {
        "appid": app_id,
        "format": "json",
    }

    try:
        resp = _protected_get(STEAM_ACHIEVEMENT_SCHEMA_URL, params=params, timeout=15)
        data = resp.json()

        game = data.get("game", {})
        available_stats = game.get("availableGameStats", {})
        achievements = available_stats.get("achievements", [])

        results: List[AchievementInfo] = []
        for ach in achievements:
            try:
                results.append(
                    AchievementInfo(
                        name=ach.get("name", ""),
                        display_name=ach.get("displayName", ach.get("name", "")),
                        description=ach.get("description", ""),
                        icon=ach.get("icon", ""),
                        icon_gray=ach.get("icongray", ""),
                        hidden=bool(ach.get("hidden", 0)),
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to parse achievement schema: {e}")
                continue

        return results

    except SteamAPIError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch achievement schema for app {app_id}: {e}")
        return []


def fetch_achievements_with_stats(app_id: int) -> List[Dict]:
    """Fetch achievements with both percentages and display info combined.

    Merges data from GetGlobalAchievementPercentagesForApp and GetSchemaForGame.

    Args:
        app_id: Steam application ID

    Returns:
        List of dicts with combined achievement data:
        {name, display_name, description, percent, icon, icon_gray, hidden}
    """
    # Fetch both in parallel for efficiency
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as executor:
        stats_future = executor.submit(fetch_global_achievements, app_id)
        schema_future = executor.submit(fetch_achievement_schema, app_id)

        stats = stats_future.result()
        schema = schema_future.result()

    # Create lookup by name
    schema_map = {ach.name: ach for ach in schema}

    # Merge data
    results: List[Dict] = []
    for stat in stats:
        info = schema_map.get(stat.name)
        result = {
            "name": stat.name,
            "percent": stat.percent,
            "display_name": info.display_name if info else stat.name,
            "description": info.description if info else "",
            "icon": info.icon if info else "",
            "icon_gray": info.icon_gray if info else "",
            "hidden": info.hidden if info else False,
        }
        results.append(result)

    return results
