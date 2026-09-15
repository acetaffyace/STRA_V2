from __future__ import annotations

import senti_next
from senti_next import analysis_acquisition
from senti_next.acquisition import AcquisitionResult
from senti_next.sampling import SamplingContract


def test_empty_local_game_forces_fresh_collection(monkeypatch):
    contract = SamplingContract(app_id=42, languages=["all"], max_reviews=500)
    expected = AcquisitionResult(
        reviews=[],
        source="steam",
        fetched_count=0,
        stored_count=0,
        cache_hit=False,
        collection_complete=True,
        truncated_by_max_reviews=False,
        stop_reason="end_of_results",
        stats={},
    )
    monkeypatch.setattr(analysis_acquisition.storage, "count_reviews", lambda app_id: 0)
    called = {"collect": 0}

    def fake_collect(value, *, force, progress_callback=None):
        called["collect"] += 1
        assert value is contract
        assert force is True
        return expected

    monkeypatch.setattr(analysis_acquisition, "collect_reviews", fake_collect)
    monkeypatch.setattr(
        analysis_acquisition,
        "_ensure_reviews",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stale cache path must not run")),
    )

    result = analysis_acquisition.ensure_reviews(contract)
    assert result is expected
    assert called["collect"] == 1


def test_nonempty_local_game_can_use_coverage_cache(monkeypatch):
    contract = SamplingContract(app_id=42, languages=["all"], max_reviews=500)
    expected = AcquisitionResult(
        reviews=[{"recommendationid": "1"}],
        source="cache",
        fetched_count=0,
        stored_count=0,
        cache_hit=True,
        collection_complete=True,
        truncated_by_max_reviews=False,
        stop_reason="cache_hit",
        stats={"cache_hit": True},
    )
    monkeypatch.setattr(analysis_acquisition.storage, "count_reviews", lambda app_id: 1)
    monkeypatch.setattr(analysis_acquisition, "_ensure_reviews", lambda value, progress_callback=None: expected)

    result = analysis_acquisition.ensure_reviews(contract)
    assert result is expected


def test_analysis_fetch_compatibility_entrypoint_uses_acquisition_cache(monkeypatch):
    """The function imported by routes.analysis must reuse Acquisition Service."""
    contract = SamplingContract(app_id=42, languages=["all"], max_reviews=500)
    expected = AcquisitionResult(
        reviews=[{"recommendationid": "cached-1", "timestamp_created": 1}],
        source="cache",
        fetched_count=0,
        stored_count=0,
        cache_hit=True,
        collection_complete=True,
        truncated_by_max_reviews=False,
        stop_reason="cache_hit",
        stats={
            "cache_hit": True,
            "collection_complete": True,
            "scope_complete": True,
            "retrieved_count": 1,
        },
    )
    seen = {"progress": [], "stats": None}

    monkeypatch.setattr(analysis_acquisition, "ensure_reviews", lambda value, progress_callback=None: expected)
    monkeypatch.setattr(
        senti_next,
        "_steam_fetch_reviews",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Steam must not be called on cache hit")),
    )

    rows = senti_next.fetch_reviews(
        42,
        count=500,
        language="all",
        sampling_contract=contract,
        progress_callback=lambda value: seen["progress"].append(value),
        stats_callback=lambda value: seen.__setitem__("stats", value),
    )

    assert rows == expected.reviews
    assert seen["stats"]["cache_hit"] is True
