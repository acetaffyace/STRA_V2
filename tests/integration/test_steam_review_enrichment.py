from __future__ import annotations

import json
import sqlite3

import pandas as pd

from apps.api.senti_next import db, storage
from apps.api.senti_next.analysis import build_reviews_dataframe
from apps.api.senti_next.evidence import gate_response_quotes
from apps.api.senti_next.routes._shared import _database_row_to_item
from apps.api.senti_next.steam_enrichment import (
    acquisition,
    canonical_fields,
    device_context,
    purchase_source,
)
from apps.api.senti_next.steam_enrichment_migration import migrate


def payload(**overrides):
    value = {
        "recommendationid": "r1",
        "review": "Player text only",
        "language": "english",
        "timestamp_created": 1700000000,
        "developer_response": "DeveloperOnly response phrase",
        "timestamp_dev_responded": 1700000100,
        "steam_purchase": True,
        "received_for_free": False,
        "primarily_steam_deck": False,
    }
    value.update(overrides)
    return value


def test_canonical_parsing_and_round_trip():
    fields = canonical_fields(payload())
    assert fields == {
        "developer_response": "DeveloperOnly response phrase",
        "timestamp_dev_responded": 1700000100,
        "steam_purchase": True,
        "received_for_free": False,
        "primarily_steam_deck": False,
    }


def test_null_semantics_and_deterministic_labels():
    fields = canonical_fields({})
    assert all(value is None for value in fields.values())
    assert purchase_source(None) == "unknown"
    assert purchase_source(True) == "steam_purchase"
    assert purchase_source(False) == "non_steam_purchase"
    assert acquisition(None) == "unknown"
    assert acquisition(True) == "received_for_free"
    assert acquisition(False) == "paid_or_not_marked_free"
    assert device_context(None) == "unknown"
    assert device_context(True) == "primarily_deck"
    assert device_context(False) == "other_or_not_primarily_deck"


def test_storage_round_trip_and_partial_upsert_preserves_known_values(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine(); db._engine = None; db.init_db()
    storage.upsert_reviews(1, [payload()])
    storage.upsert_reviews(1, [{"recommendationid": "r1", "review": "Updated player text"}])
    loaded = storage.load_reviews(1)[0]
    assert loaded["review"] == "Updated player text"
    assert loaded["developer_response"] == "DeveloperOnly response phrase"
    assert loaded["steam_purchase"] is True
    assert loaded["received_for_free"] is False
    assert loaded["primarily_steam_deck"] is False
    db.close_engine(); db._engine = None


def test_no_player_fts_contamination_and_evidence_isolation(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine(); db._engine = None; db.init_db()
    storage.upsert_reviews(1, [payload()])
    assert storage.search_review_ids(1, "DeveloperOnly") == []
    result = gate_response_quotes(
        '"DeveloperOnly response phrase"',
        [{"review_id": "r1", "app_id": 1, "text": "Player text only", "developer_response": "DeveloperOnly response phrase"}],
    )
    assert result["evidence"] == []
    assert "unverified direct quote removed" in result["response"]
    db.close_engine(); db._engine = None


def test_analysis_invariance():
    base = [payload()]
    enriched = [payload(developer_response="changed", steam_purchase=False, received_for_free=True, primarily_steam_deck=True)]
    pd.testing.assert_frame_equal(
        build_reviews_dataframe(base), build_reviews_dataframe(enriched), check_like=True
    )


def test_legacy_backfill_and_migration_idempotency():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE reviews (id INTEGER PRIMARY KEY, review_id TEXT UNIQUE, data TEXT NOT NULL)")
    conn.execute("INSERT INTO reviews(review_id, data) VALUES (?, ?)", ("r1", json.dumps(payload())))
    migrate(conn)
    first = conn.execute("SELECT developer_response, timestamp_dev_responded, steam_purchase, received_for_free, primarily_steam_deck FROM reviews").fetchone()
    migrate(conn)
    second = conn.execute("SELECT developer_response, timestamp_dev_responded, steam_purchase, received_for_free, primarily_steam_deck FROM reviews").fetchone()
    assert first == second == ("DeveloperOnly response phrase", 1700000100, 1, 0, 0)
    conn.close()


def test_api_serialization_is_null_safe():
    item = _database_row_to_item(
        {"review_id": "legacy", "app_id": 1, "data": json.dumps({"recommendationid": "legacy", "review": "old"}), "label_payload": None},
        {},
    )
    assert item.steam_context["purchase_source"] == "unknown"
    assert item.developer_response["text"] is None
    assert item.provenance["enrichment_schema_version"] == "steam-review-enrichment-v1"
