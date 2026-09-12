from senti_next import llm
from senti_next.providers.errors import ProviderFailure


def _valid_payload():
    return {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []}


def test_active_mode_submits_one_representative_and_fans_out(monkeypatch):
    monkeypatch.setenv("SENTINEXT_REVIEW_PREPROCESS_MODE", "active")
    monkeypatch.setenv("SENTINEXT_DYNAMIC_BATCH_ENABLED", "true")
    monkeypatch.setenv("SENTINEXT_ASPECT_ENRICH_LIMIT", "0")
    monkeypatch.setattr("senti_next.providers.config.get_active_provider", lambda: ("test", "model"))
    calls = []

    def fake_batch(items, *, game_context=None):
        calls.append(items)
        return {
            str(item["review_id"]): {
                "subcategories": ["other/general"],
                "issue_subcategories": [],
                "request_subcategories": [],
            }
            for item in items
        }, "test:model"

    monkeypatch.setattr(llm, "classify_reviews_batch", fake_batch)
    reviews = [
        {"review_id": "a", "review": "hello world\nhello world", "language": "english"},
        {"review_id": "b", "review": "hello world", "language": "english"},
        {"review_id": "c", "review": "different words", "language": "english"},
    ]
    result = llm.ensure_review_labels(42, reviews, cache_enabled=False)

    assert len(calls) == 1
    submitted_ids = {str(item["review_id"]) for item in calls[0]}
    assert submitted_ids == {"a", "c"}
    assert set(result) == {"a", "b", "c"}
    assert result["a"]["subcategories"] == result["b"]["subcategories"]


def test_shadow_mode_sends_original_text_and_does_not_deduplicate(monkeypatch):
    monkeypatch.setenv("SENTINEXT_REVIEW_PREPROCESS_MODE", "shadow")
    monkeypatch.setenv("SENTINEXT_ASPECT_ENRICH_LIMIT", "0")
    monkeypatch.setattr("senti_next.providers.config.get_active_provider", lambda: ("test", "model"))
    calls = []

    def fake_batch(items, *, game_context=None):
        calls.append(items)
        return {str(item["review_id"]): {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []} for item in items}, "test:model"

    monkeypatch.setattr(llm, "classify_reviews_batch", fake_batch)
    reviews = [
        {"review_id": "a", "review": "hello world\nhello world"},
        {"review_id": "b", "review": "hello world"},
    ]
    llm.ensure_review_labels(42, reviews, cache_enabled=False)

    submitted = {str(item["review_id"]): item["review_text"] for batch in calls for item in batch}
    assert submitted == {"a": "hello world\nhello world", "b": "hello world"}


def test_dynamic_pipeline_validates_and_retries_only_failed_ids(monkeypatch):
    monkeypatch.setenv("SENTINEXT_REVIEW_PREPROCESS_MODE", "active")
    monkeypatch.setenv("SENTINEXT_DYNAMIC_BATCH_ENABLED", "true")
    monkeypatch.setenv("SENTINEXT_ASPECT_ENRICH_LIMIT", "0")
    monkeypatch.setenv("SENTINEXT_BATCH_MAX_RETRY_ATTEMPTS", "2")
    monkeypatch.setattr("senti_next.providers.config.get_active_provider", lambda: ("test", "model"))
    calls = []

    def fake_batch(items, *, game_context=None):
        ids = [str(item["review_id"]) for item in items]
        calls.append(ids)
        if set(ids) == {"a", "b", "c", "d"}:
            return {"a": _valid_payload(), "b": _valid_payload(), "c": {**llm._DEFAULT_LABEL, "_batch_invalid": True}}, "test:model"
        return {review_id: _valid_payload() for review_id in ids}, "test:model"

    monkeypatch.setattr(llm, "classify_reviews_batch", fake_batch)
    reviews = [{"review_id": rid, "review": f"review {rid}"} for rid in ("a", "b", "c", "d")]
    result = llm.ensure_review_labels(42, reviews, cache_enabled=False)

    assert calls[0] == ["a", "b", "c", "d"]
    assert calls[1] == ["c", "d"]
    assert set(result) == {"a", "b", "c", "d"}


def test_dynamic_retry_ceiling_is_initial_plus_two(monkeypatch):
    monkeypatch.setenv("SENTINEXT_REVIEW_PREPROCESS_MODE", "active")
    monkeypatch.setenv("SENTINEXT_DYNAMIC_BATCH_ENABLED", "true")
    monkeypatch.setenv("SENTINEXT_ASPECT_ENRICH_LIMIT", "0")
    monkeypatch.setenv("SENTINEXT_BATCH_MAX_RETRY_ATTEMPTS", "2")
    monkeypatch.setattr("senti_next.providers.config.get_active_provider", lambda: ("test", "model"))
    calls = []

    def always_invalid(items, *, game_context=None):
        calls.append([str(item["review_id"]) for item in items])
        return {str(item["review_id"]): {**llm._DEFAULT_LABEL, "_batch_invalid": True} for item in items}, "test:model"

    monkeypatch.setattr(llm, "classify_reviews_batch", always_invalid)
    llm.ensure_review_labels(42, [{"review_id": "a", "review": "bad fps"}], cache_enabled=False)
    assert len(calls) == 3


def test_dynamic_unexpected_id_is_seen_by_validator_and_not_persisted(monkeypatch):
    monkeypatch.setenv("SENTINEXT_REVIEW_PREPROCESS_MODE", "active")
    monkeypatch.setenv("SENTINEXT_DYNAMIC_BATCH_ENABLED", "true")
    monkeypatch.setenv("SENTINEXT_ASPECT_ENRICH_LIMIT", "0")
    monkeypatch.setattr("senti_next.providers.config.get_active_provider", lambda: ("test", "model"))
    observed = []
    original_validator = llm.batch_planner.validate_batch_results

    def spy(expected_ids, returned, **kwargs):
        result = original_validator(expected_ids, returned, **kwargs)
        observed.append(result.unexpected_ids)
        return result

    monkeypatch.setattr(llm.batch_planner, "validate_batch_results", spy)
    monkeypatch.setattr(
        llm, "classify_reviews_batch",
        lambda items, **kwargs: ({"a": _valid_payload(), "x": _valid_payload()}, "test:model"),
    )
    result = llm.ensure_review_labels(42, [{"review_id": "a", "review": "good game"}], cache_enabled=False)
    assert observed == [("x",)]
    assert set(result) == {"a"}


def test_estimate_counts_short_lexical_reviews_as_llm_candidates(monkeypatch):
    monkeypatch.setattr("senti_next.providers.config.get_active_provider", lambda: ("test", "model"))
    estimate = llm.estimate_review_labeling(
        42,
        [{"review_id": "short", "review": "lag"}, {"review_id": "long", "review": "good game with a sufficiently descriptive review about performance"}],
        cache_enabled=False,
    )
    assert estimate["short_text_reviews"] == 1
    assert estimate["llm_reviews"] == 2


def test_short_lexical_text_reaches_dynamic_llm(monkeypatch):
    monkeypatch.setenv("SENTINEXT_REVIEW_PREPROCESS_MODE", "active")
    monkeypatch.setenv("SENTINEXT_DYNAMIC_BATCH_ENABLED", "true")
    monkeypatch.setenv("SENTINEXT_ASPECT_ENRICH_LIMIT", "0")
    monkeypatch.setattr("senti_next.providers.config.get_active_provider", lambda: ("test", "model"))
    calls = []

    def fake_batch(items, *, game_context=None):
        calls.extend(str(item["review_id"]) for item in items)
        return {str(item["review_id"]): _valid_payload() for item in items}, "test:model"

    monkeypatch.setattr(llm, "classify_reviews_batch", fake_batch)
    reviews = [{"review_id": text, "review": text} for text in ("crashes", "lag", "闪退", "掉帧", "贵", "卡")]
    result = llm.ensure_review_labels(42, reviews, cache_enabled=False)
    assert set(calls) == {"crashes", "lag", "闪退", "掉帧", "贵", "卡"}
    assert all(result[text]["_label_source"] != "short_review" for text in calls)


def test_dynamic_provider_failure_does_not_split(monkeypatch):
    monkeypatch.setenv("SENTINEXT_REVIEW_PREPROCESS_MODE", "active")
    monkeypatch.setenv("SENTINEXT_DYNAMIC_BATCH_ENABLED", "true")
    monkeypatch.setenv("SENTINEXT_ASPECT_ENRICH_LIMIT", "0")
    monkeypatch.setattr("senti_next.providers.config.get_active_provider", lambda: ("test", "model"))
    calls = []

    def fail_batch(items, *, game_context=None):
        calls.append(len(items))
        raise ProviderFailure("RATE_LIMIT", "busy")

    monkeypatch.setattr(llm, "classify_reviews_batch", fail_batch)
    llm.ensure_review_labels(42, [{"review_id": str(i), "review": f"bad fps {i}"} for i in range(4)], cache_enabled=False)
    assert calls == [4]
