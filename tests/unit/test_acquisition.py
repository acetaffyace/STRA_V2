from __future__ import annotations

from senti_next import acquisition
from senti_next.sampling import SamplingContract


def _review(review_id: str, created: int, *, language: str = "english") -> dict:
    return {
        "recommendationid": review_id,
        "timestamp_created": created,
        "timestamp_updated": created,
        "language": language,
        "voted_up": True,
        "steam_purchase": True,
        "review": f"review {review_id}",
    }


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def json(self) -> dict:
        return self.payload


def test_targeted_date_path_accepts_only_verified_window(monkeypatch):
    contract = SamplingContract(
        app_id=10,
        start_time=100,
        end_time=200,
        languages=["english"],
        collection_order="recent",
        max_reviews=10,
    )
    calls = []

    def fake_get(url, *, params, timeout):
        calls.append(params)
        return _Response({
            "success": 1,
            "reviews": [_review("a", 180), _review("b", 150)],
            "cursor": None,
        })

    monkeypatch.setattr(acquisition.steam_api, "_protected_get", fake_get)
    result = acquisition._fetch_targeted_language(contract, "english", max_reviews=10)

    assert result is not None
    reviews, stats = result
    assert [row["recommendationid"] for row in reviews] == ["a", "b"]
    assert stats["targeted_date_applied"] is True
    assert stats["collection_complete"] is True
    assert calls[0]["start_date"] == 100
    assert calls[0]["end_date"] == 200
    assert calls[0]["date_range_type"] == "include"


def test_targeted_date_path_rejects_ignored_range(monkeypatch):
    contract = SamplingContract(
        app_id=10,
        start_time=100,
        end_time=200,
        languages=["english"],
        collection_order="recent",
        max_reviews=10,
    )

    monkeypatch.setattr(
        acquisition.steam_api,
        "_protected_get",
        lambda *args, **kwargs: _Response({
            "success": 1,
            "reviews": [_review("new", 999)],
            "cursor": None,
        }),
    )

    assert acquisition._fetch_targeted_language(contract, "english", max_reviews=10) is None


def test_targeted_failure_falls_back_to_canonical_cursor_fetch(monkeypatch):
    contract = SamplingContract(
        app_id=10,
        start_time=100,
        end_time=200,
        languages=["english"],
        collection_order="recent",
        max_reviews=10,
    )
    expected = [_review("fallback", 160)]

    monkeypatch.setattr(acquisition, "_fetch_targeted_language", lambda *args, **kwargs: None)

    def fake_fetch(*args, stats_callback=None, **kwargs):
        if stats_callback:
            stats_callback({
                "retrieved_reviews": 1,
                "collection_complete": True,
                "truncated_by_max_reviews": False,
                "stop_reason": "lower_boundary_reached",
            })
        return expected

    monkeypatch.setattr(acquisition.steam_api, "fetch_reviews", fake_fetch)
    reviews, stats = acquisition._fetch_from_steam(contract)

    assert reviews == expected
    assert stats["targeted_date_attempted"] is True
    assert stats["targeted_date_applied"] is False


def test_ensure_reviews_uses_compatible_cache_without_collection(monkeypatch):
    contract = SamplingContract(app_id=10, languages=["all"], max_reviews=500)
    cached = acquisition.AcquisitionResult(
        reviews=[_review("cached", 150)],
        source="cache",
        fetched_count=0,
        stored_count=0,
        cache_hit=True,
        collection_complete=True,
        truncated_by_max_reviews=False,
        stop_reason="cache_hit",
        stats={"cache_hit": True},
    )
    monkeypatch.setattr(acquisition, "cached_result", lambda value: cached)

    def fail_collect(*args, **kwargs):
        raise AssertionError("Steam collection must not run on a cache hit")

    monkeypatch.setattr(acquisition, "collect_reviews", fail_collect)
    result = acquisition.ensure_reviews(contract)

    assert result.cache_hit is True
    assert result.reviews[0]["recommendationid"] == "cached"


def test_multi_language_targeted_path_uses_total_cap(monkeypatch):
    contract = SamplingContract(
        app_id=10,
        start_time=100,
        end_time=200,
        languages=["english", "japanese"],
        collection_order="recent",
        max_reviews=5,
    )
    requested_caps = []

    def fake_targeted(_contract, language, *, max_reviews, progress_callback=None):
        requested_caps.append((language, max_reviews))
        rows = [_review(f"{language}-{i}", 190 - i, language=language) for i in range(max_reviews)]
        return rows, {
            "collection_complete": False,
            "truncated_by_max_reviews": True,
            "stop_reason": "max_reviews_reached",
            "targeted_date_attempted": True,
            "targeted_date_applied": True,
        }

    monkeypatch.setattr(acquisition, "_fetch_targeted_language", fake_targeted)
    rows, stats = acquisition._fetch_from_steam(contract)

    assert requested_caps == [("english", 3), ("japanese", 3)]
    assert len(rows) == 5
    assert stats["truncated_by_max_reviews"] is True


def test_multi_language_fallback_bounds_actual_per_language_requests(monkeypatch):
    contract = SamplingContract(
        app_id=10,
        start_time=100,
        end_time=200,
        languages=["english", "japanese", "schinese"],
        collection_order="recent",
        max_reviews=10,
    )
    requested_caps = []

    monkeypatch.setattr(acquisition, "_fetch_targeted_language", lambda *args, **kwargs: None)

    def fake_fetch(app_id, *, count, language, sampling_contract, stats_callback=None, **kwargs):
        requested_caps.append((language, count, sampling_contract.max_reviews))
        rows = [_review(f"{language}-{i}", 180 - i, language=language) for i in range(count)]
        if stats_callback:
            stats_callback({
                "retrieved_reviews": len(rows),
                "retrieved_count": len(rows),
                "population_reviews_after_scope": len(rows),
                "collection_complete": False,
                "scope_complete": False,
                "truncated_by_max_reviews": True,
                "stop_reason": "max_reviews_reached",
            })
        return rows

    monkeypatch.setattr(acquisition.steam_api, "fetch_reviews", fake_fetch)
    rows, stats = acquisition._fetch_from_steam(contract)

    # ceil(10/3) = 4, so the fallback asks for 4 per language instead of 10 per language.
    assert requested_caps == [
        ("english", 4, 4),
        ("japanese", 4, 4),
        ("schinese", 4, 4),
    ]
    assert len(rows) == 10
    assert stats["retrieved_reviews"] == 12
    assert stats["targeted_date_attempted"] is True
    assert stats["targeted_date_applied"] is False
