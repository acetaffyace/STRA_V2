from __future__ import annotations

from typing import Any

import pytest

from apps.api.senti_next import steam_api
from apps.api.senti_next.steam_api import SteamAPIError
from apps.api.senti_next.ingest import normalize_steam_reviews
from apps.api.senti_next.sampling import SamplingContract


class _Response:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def json(self) -> dict[str, Any]:
        return self.payload


def _review(review_id: str, timestamp: int, *, text: str | None = None, language: str = "english") -> dict[str, Any]:
    return {
        "recommendationid": review_id,
        "review": text or review_id,
        "timestamp_created": timestamp,
        "timestamp_updated": timestamp,
        "voted_up": True,
        "language": language,
        "steam_purchase": True,
        "received_for_free": False,
        "written_during_early_access": False,
        "primarily_steam_deck": True,
        "votes_up": 4,
        "votes_funny": 2,
        "weighted_vote_score": "0.75",
        "comment_count": 3,
        "author": {
            "steamid": "author-1",
            "num_games_owned": 12,
            "num_reviews": 7,
            "playtime_forever": 600,
            "playtime_last_two_weeks": 60,
            "playtime_at_review": 300,
            "deck_playtime_at_review": 120,
            "last_played": 500,
        },
    }


def _mock_pages(monkeypatch: pytest.MonkeyPatch, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> _Response:
        calls.append(kwargs["params"])
        return _Response(pages.pop(0))

    monkeypatch.setattr(steam_api, "_protected_get", fake_get)
    return calls


@pytest.mark.parametrize(
    ("review_type", "purchase_type"),
    [("positive", "steam"), ("negative", "non_steam_purchase")],
)
def test_review_and_purchase_filters_map_to_steam(monkeypatch: pytest.MonkeyPatch, review_type: str, purchase_type: str) -> None:
    calls = _mock_pages(monkeypatch, [{"success": 1, "query_summary": {"num_reviews": 1, "total_reviews": 1}, "reviews": [_review("r1", 100)], "cursor": ""}])
    contract = SamplingContract(
        app_id=10,
        languages=["schinese"],
        review_type=review_type,
        purchase_type=purchase_type,
        max_reviews=1,
    )
    assert len(steam_api.fetch_reviews(10, sampling_contract=contract)) == 1
    assert calls[0]["review_type"] == review_type
    assert calls[0]["purchase_type"] == purchase_type
    assert calls[0]["language"] == "schinese"


def test_offtopic_policy_and_helpful_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _mock_pages(monkeypatch, [{"success": 1, "reviews": [_review("r1", 100)], "cursor": ""}])
    contract = SamplingContract(app_id=10, collection_order="helpful", include_offtopic_activity=True, max_reviews=1)
    steam_api.fetch_reviews(10, sampling_contract=contract)
    assert calls[0]["filter"] == "all"
    assert calls[0]["filter_offtopic_activity"] == 0

    calls = _mock_pages(monkeypatch, [{"success": 1, "reviews": [_review("r1", 100)], "cursor": ""}])
    steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10, max_reviews=1))
    assert calls[0]["filter_offtopic_activity"] == 1


def test_cursor_pagination_and_max_reviews(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _mock_pages(
        monkeypatch,
        [
            {"success": 1, "reviews": [_review("r1", 200), _review("r2", 100)], "cursor": "next"},
            {"success": 1, "reviews": [_review("r3", 50)], "cursor": ""},
        ],
    )
    result = steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10, max_reviews=3))
    assert [item["recommendationid"] for item in result] == ["r1", "r2", "r3"]
    assert [call["cursor"] for call in calls] == ["*", "next"]


def test_arbitrary_time_window_uses_page_level_safe_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _mock_pages(
        monkeypatch,
        [
            {"success": 1, "reviews": [_review("new", 300), _review("inside-a", 200)], "cursor": "p2"},
            {"success": 1, "reviews": [_review("old-one", 100), _review("inside-b", 180)], "cursor": "p3"},
            {"success": 1, "reviews": [_review("old-two", 120), _review("old-three", 110)], "cursor": "p4"},
            {"success": 1, "reviews": [_review("should-not-fetch", 90)], "cursor": ""},
        ],
    )
    result = steam_api.fetch_reviews(
        10,
        sampling_contract=SamplingContract(app_id=10, start_time=150, end_time=250),
    )
    assert {item["recommendationid"] for item in result} == {"inside-a", "inside-b"}
    assert all(150 <= item["timestamp_created"] <= 250 for item in result)
    assert len(calls) == 3


def test_end_time_excludes_newer_reviews_and_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_pages(monkeypatch, [{"success": 1, "reviews": [_review("new", 300), _review("old", 100)], "cursor": ""}])
    result = steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10, end_time=200))
    assert [item["recommendationid"] for item in result] == ["old"]

    _mock_pages(monkeypatch, [{"success": 1, "reviews": [], "cursor": ""}])
    assert steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10, max_reviews=0)) == []


def test_sampling_contract_rejects_invalid_window_and_non_chronological_window() -> None:
    with pytest.raises(ValueError, match="start_time"):
        SamplingContract(app_id=10, start_time=20, end_time=10)
    with pytest.raises(ValueError, match="collection_order"):
        SamplingContract(app_id=10, start_time=10, end_time=20, collection_order="helpful")
    assert SamplingContract(app_id=10, max_reviews=0).unlimited is True


def test_num_reviews_is_page_count_and_total_reviews_is_api_total(monkeypatch: pytest.MonkeyPatch) -> None:
    stats: list[dict[str, Any]] = []
    _mock_pages(monkeypatch, [{"success": 1, "query_summary": {"num_reviews": 2, "total_reviews": 99}, "reviews": [_review("r1", 100), _review("r2", 90)], "cursor": ""}])
    steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10, max_reviews=0), stats_callback=stats.append)
    final = stats[-1]
    assert final["steam_num_reviews"] == 2
    assert final["steam_total_reviews"] == 99
    assert final["available_matching_reviews"] == 99
    assert final["retrieved_reviews"] == 2
    assert final["population_reviews_after_scope"] == 2


def test_time_window_does_not_claim_unscoped_total(monkeypatch: pytest.MonkeyPatch) -> None:
    stats: list[dict[str, Any]] = []
    _mock_pages(monkeypatch, [{"success": 1, "query_summary": {"num_reviews": 1, "total_reviews": 99}, "reviews": [_review("r1", 100)], "cursor": ""}])
    steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10, start_time=90, end_time=110), stats_callback=stats.append)
    assert stats[-1]["available_matching_reviews"] is None


def test_key_steam_metadata_survives_normalization() -> None:
    item = normalize_steam_reviews(10, [_review("r1", 100)])[0]
    context = item["context"]
    assert context["steam_purchase"] is True
    assert context["received_for_free"] is False
    assert context["written_during_early_access"] is False
    assert context["primarily_steam_deck"] is True
    assert context["author"]["deck_playtime_at_review"] == 120


def test_duplicate_text_does_not_change_population_count(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_pages(
        monkeypatch,
        [{
            "success": 1,
            "reviews": [_review("same-a", 100, text="same text"), _review("same-b", 90, text="same text")],
            "cursor": "",
        }],
    )
    result = steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10, max_reviews=0))
    assert len(result) == 2
    assert {item["recommendationid"] for item in result} == {"same-a", "same-b"}


def test_max_reviews_before_lower_boundary_is_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _mock_pages(monkeypatch, [{
        "success": 1,
        "reviews": [_review("inside-a", 200), _review("inside-b", 180)],
        "cursor": "next",
    }])
    stats: list[dict[str, Any]] = []
    result = steam_api.fetch_reviews(
        10,
        sampling_contract=SamplingContract(app_id=10, start_time=100, end_time=250, max_reviews=1),
        stats_callback=stats.append,
    )
    assert len(result) == 1
    assert stats[-1]["collection_complete"] is False
    assert stats[-1]["truncated_by_max_reviews"] is True
    assert stats[-1]["stop_reason"] == "max_reviews_reached"
    assert len(calls) == 1


def test_max_reviews_without_stream_exhaustion_is_not_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_pages(monkeypatch, [{
        "success": 1,
        "reviews": [_review("r1", 200)],
        "cursor": "next",
    }])
    stats: list[dict[str, Any]] = []
    steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10, max_reviews=1), stats_callback=stats.append)
    assert stats[-1]["collection_complete"] is False
    assert stats[-1]["truncated_by_max_reviews"] is True
    assert stats[-1]["stop_reason"] == "max_reviews_reached"


def test_normal_end_of_results_is_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_pages(monkeypatch, [{
        "success": 1,
        "reviews": [_review("r1", 200)],
        "cursor": "next",
    }, {"success": 1, "reviews": [], "cursor": ""}])
    stats: list[dict[str, Any]] = []
    steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10, max_reviews=0), stats_callback=stats.append)
    assert stats[-1]["collection_complete"] is True
    assert stats[-1]["truncated_by_max_reviews"] is False
    assert stats[-1]["stop_reason"] == "end_of_results"


def test_safe_lower_boundary_crossing_is_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_pages(monkeypatch, [{
        "success": 1,
        "reviews": [_review("old", 90), _review("older", 80)],
        "cursor": "next",
    }])
    stats: list[dict[str, Any]] = []
    steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10, start_time=100), stats_callback=stats.append)
    assert stats[-1]["collection_complete"] is True
    assert stats[-1]["stop_reason"] == "lower_boundary_reached"


def test_repeated_cursor_is_abnormal_and_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_pages(monkeypatch, [{
        "success": 1,
        "reviews": [_review("r1", 200)],
        "cursor": "*",
    }])
    stats: list[dict[str, Any]] = []
    steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10, max_reviews=0), stats_callback=stats.append)
    assert stats[-1]["collection_complete"] is False
    assert stats[-1]["stop_reason"] == "cursor_repeated"


def test_api_failure_is_not_reported_as_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_get(url: str, **kwargs: Any) -> _Response:
        raise SteamAPIError("temporary outage")

    monkeypatch.setattr(steam_api, "_protected_get", fail_get)
    stats: list[dict[str, Any]] = []
    with pytest.raises(SteamAPIError):
        steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10), stats_callback=stats.append)
    assert stats[-1]["collection_complete"] is False
    assert stats[-1]["stop_reason"] == "api_failure"


def test_malformed_response_is_invalid_not_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_pages(monkeypatch, [{"success": 1, "reviews": {"not": "a list"}}])
    stats: list[dict[str, Any]] = []
    steam_api.fetch_reviews(10, sampling_contract=SamplingContract(app_id=10), stats_callback=stats.append)
    assert stats[-1]["collection_complete"] is False
    assert stats[-1]["stop_reason"] == "invalid_response"


def test_multilanguage_failure_is_explicitly_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **kwargs: Any) -> _Response:
        language = kwargs["params"]["language"]
        if language == "schinese":
            raise SteamAPIError("schinese unavailable")
        return _Response({"success": 1, "reviews": [_review("en-1", 200, language=language)], "cursor": ""})

    monkeypatch.setattr(steam_api, "_protected_get", fake_get)
    stats: list[dict[str, Any]] = []
    result = steam_api.fetch_reviews_multi_language(
        10,
        sampling_contract=SamplingContract(app_id=10, languages=["english", "schinese"]),
        stats_callback=stats.append,
    )
    aggregate = stats[-1]
    assert len(result) == 1
    assert aggregate["collection_complete"] is False
    assert aggregate["language_stats"]["schinese"]["status"] == "failed"
    assert aggregate["language_stats"]["schinese"]["error"] == "schinese unavailable"


def test_multilanguage_all_complete_is_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **kwargs: Any) -> _Response:
        language = kwargs["params"]["language"]
        return _Response({"success": 1, "reviews": [_review(language, 200, language=language)], "cursor": ""})

    monkeypatch.setattr(steam_api, "_protected_get", fake_get)
    stats: list[dict[str, Any]] = []
    steam_api.fetch_reviews_multi_language(
        10,
        sampling_contract=SamplingContract(app_id=10, languages=["english", "schinese"]),
        stats_callback=stats.append,
    )
    aggregate = stats[-1]
    assert aggregate["collection_complete"] is True
    assert aggregate["stop_reason"] == "end_of_results"
    assert {item["status"] for item in aggregate["language_stats"].values()} == {"complete"}
