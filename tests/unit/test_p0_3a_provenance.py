"""P0.3a label provenance and semantic cache identity tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import db, llm, storage


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def review(text: str = "The controls feel responsive and precise.") -> dict:
    return {
        "recommendationid": "p03-review",
        "review": text,
        "language": "english",
        "voted_up": True,
        "author": {"playtime_forever": 120},
    }


def test_identity_covers_processed_input_taxonomy_prompt_provider_and_model():
    item = review("x" * 9000)
    first = llm.classification_identity(
        item, {"name": "Game", "genres": ["RPG"]}, provider="openai",
        model_id="openai:gpt-a", taxonomy_version="tax-v1", prompt_version="prompt-v1",
    )
    changed_text = llm.classification_identity(
        review("x" * 8999 + "y"), {"name": "Game", "genres": ["RPG"]}, provider="openai",
        model_id="openai:gpt-a", taxonomy_version="tax-v1", prompt_version="prompt-v1",
    )
    changed_context = llm.classification_identity(
        item, {"name": "Other Game", "genres": ["RPG"]}, provider="openai",
        model_id="openai:gpt-a", taxonomy_version="tax-v1", prompt_version="prompt-v1",
    )
    assert first["review_hash"] != changed_text["review_hash"]
    assert first["classification_input_hash"] != changed_context["classification_input_hash"]
    assert first["was_truncated"] is True
    assert first["processed_char_count"] == len(llm._sanitize_review_text("x" * 9000))
    assert llm.label_cache_eligible(
        {**first, "label_origin": "llm", "validated": True}, first
    )
    assert not llm.label_cache_eligible(
        {**first, "label_origin": "rule_fallback", "validated": False}, first
    )


def test_taxonomy_prompt_provider_and_model_changes_miss_cache():
    item = review()
    base = llm.classification_identity(item, None, provider="openai", model_id="openai:a")
    label = {**base, "label_origin": "llm", "validated": True}
    for changed in (
        {**base, "taxonomy_version": "v2"},
        {**base, "prompt_version": "v2"},
        {**base, "provider": "deepseek", "model_id": "deepseek:a"},
        {**base, "model_id": "openai:b"},
    ):
        assert not llm.label_cache_eligible(label, changed)


def test_new_label_persists_provenance_and_legacy_is_not_cache_eligible():
    item = review()
    identity = llm.classification_identity(item, None, provider="openai", model_id="openai:a")
    storage.upsert_review_label(
        7, "p03-review", identity["review_hash"], {"subcategories": ["other/general"]},
        "openai:a", llm.ACTIVE_PROMPT_VERSION,
        label_origin="llm", validated=True, taxonomy_version=llm.TAXONOMY_VERSION,
        provider="openai", model_id="openai:a",
        classification_input_hash=identity["classification_input_hash"],
        was_truncated=identity["was_truncated"],
        original_char_count=identity["original_char_count"],
        processed_char_count=identity["processed_char_count"],
    )
    saved = storage.load_review_labels(7)["p03-review"]
    assert saved["label_origin"] == "llm"
    assert saved["validated"] is True
    assert llm.label_cache_eligible(saved, identity)

    with db.get_connection() as conn:
        conn.exec_driver_sql(
            "UPDATE review_labels SET label_origin=NULL, validated=NULL WHERE app_id=7 AND review_id='p03-review'"
        )
    from senti_next.label_schema import migrate_review_label_provenance
    with db.get_connection() as conn:
        raw = conn.connection.driver_connection
        migrate_review_label_provenance(raw)
        raw.commit()
    legacy = storage.load_review_labels(7)["p03-review"]
    assert legacy["label_origin"] == "legacy"
    assert not llm.label_cache_eligible(legacy, identity)


def test_ensure_reuses_only_validated_matching_cache(monkeypatch):
    item = review()
    identity = llm.classification_identity(item, None, provider="openai", model_id="openai:test")
    storage.upsert_review_label(
        8, "p03-review", identity["review_hash"], {"subcategories": ["other/general"]},
        "openai:test", llm.ACTIVE_PROMPT_VERSION,
        label_origin="llm", validated=True, taxonomy_version=llm.TAXONOMY_VERSION,
        provider="openai", model_id="openai:test",
        classification_input_hash=identity["classification_input_hash"],
    )
    monkeypatch.setattr(llm, "_active_model_id", lambda: "openai:test")
    monkeypatch.setattr("senti_next.providers.config.get_active_provider", lambda: ("openai", "test"))
    monkeypatch.setattr(llm, "classify_reviews_batch", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cache miss")))
    result = llm.ensure_review_labels(8, [item], game_context=None)
    assert result["p03-review"]["_resolution_source"] == "cache_hit"


def test_fallback_is_persisted_but_not_cache_eligible():
    item = review()
    identity = llm.classification_identity(item, None, provider="openai", model_id="openai:test")
    storage.upsert_review_label(
        9, "p03-review", identity["review_hash"], {"subcategories": ["other/general"]},
        "fallback:default", llm.ACTIVE_PROMPT_VERSION,
        label_origin="rule_fallback", validated=False, taxonomy_version=llm.TAXONOMY_VERSION,
        classification_input_hash=identity["classification_input_hash"],
    )
    saved = storage.load_review_labels(9)["p03-review"]
    assert saved["label_origin"] == "rule_fallback"
    assert saved["validated"] is False
    assert not llm.label_cache_eligible(saved, identity)
