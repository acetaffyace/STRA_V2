from __future__ import annotations

import os

import pytest

from apps.api.senti_next import db, llm, migrations, storage
from apps.api.senti_next.classifier_taxonomy import baseline_classifier_taxonomy
from apps.api.senti_next.classifier_taxonomy_schema import migrate_classifier_taxonomy


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def _identity(**kwargs):
    item = {"review_id": "r", "review": "The game is good", "voted_up": True}
    return llm.classification_identity(item, None, provider="openai", model_id="openai:test", **kwargs)


def test_v1_legacy_cache_without_snapshot_provenance_remains_reusable():
    identity = _identity()
    legacy = {**identity, "taxonomy_snapshot_id": None, "taxonomy_fingerprint": None, "label_origin": "llm", "validated": True}
    assert llm.label_cache_eligible(legacy, identity)


def test_v2_requires_exact_snapshot_and_fingerprint_and_v1_to_v2_misses():
    v1 = _identity()
    v2 = _identity(taxonomy_version="sentinext-taxonomy-v2", taxonomy_snapshot_id="snapshot-v2", taxonomy_fingerprint="fp-v2")
    saved = {**v1, "label_origin": "llm", "validated": True}
    assert not llm.label_cache_eligible(saved, v2)
    assert llm.label_cache_eligible({**v2, "label_origin": "llm", "validated": True}, v2)
    assert not llm.label_cache_eligible({**v2, "taxonomy_fingerprint": "changed", "label_origin": "llm", "validated": True}, v2)


def test_migration_19_is_additive_and_idempotent():
    with db.get_connection() as conn:
        raw = conn.connection.driver_connection
        migrate_classifier_taxonomy(raw)
        migrate_classifier_taxonomy(raw)
        columns = {row[1] for row in raw.execute("PRAGMA table_info(review_labels)").fetchall()}
        assert {"taxonomy_snapshot_id", "taxonomy_fingerprint"} <= columns
        assert migrations.latest_known_schema_version() == 24


def test_saved_label_round_trips_taxonomy_identity():
    contract = baseline_classifier_taxonomy()
    identity = _identity(taxonomy_contract=contract)
    storage.upsert_review_label(
        4, "r", identity["review_hash"], {"subcategories": ["other/general"]}, "openai:test", llm.ACTIVE_PROMPT_VERSION,
        label_origin="llm", validated=True, taxonomy_version=contract.taxonomy_version,
        taxonomy_snapshot_id=contract.snapshot_id, taxonomy_fingerprint=contract.taxonomy_fingerprint,
        provider="openai", model_id="openai:test", classification_input_hash=identity["classification_input_hash"],
    )
    loaded = storage.load_review_labels(4)["r"]
    assert loaded["taxonomy_snapshot_id"] == contract.snapshot_id
    assert loaded["taxonomy_fingerprint"] == contract.taxonomy_fingerprint
