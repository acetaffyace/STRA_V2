"""P0 contract harness.

Regression tests are required to pass now. Future-P0 tests are explicit xfails
until their owning phase is implemented; an xfail is not a regression.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))
os.environ["DATABASE_URL"] = "sqlite://"

from senti_next import db as db_module  # noqa: E402
from senti_next import storage  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    db_module.close_engine()
    db_module._engine = None
    db_module.init_db()
    yield
    db_module.close_engine()
    db_module._engine = None


def test_existing_database_initializes_and_single_upsert_is_searchable():
    review = {"recommendationid": "p0-r1", "review": "smooth performance", "timestamp_created": 1}
    assert storage.upsert_reviews(7, [review]) == 1
    assert storage.search_review_ids(7, "performance") == ["p0-r1"]


def test_non_empty_multi_app_review_fixture_preserves_global_ids():
    reviews_a = [
        {"recommendationid": "p0-a-1001", "review": "gameplay is clear", "timestamp_created": 1},
        {"recommendationid": "p0-a-1002", "review": "the tutorial is helpful", "timestamp_created": 2},
    ]
    reviews_b = [
        {"recommendationid": "p0-b-2001", "review": "soundtrack is strong", "timestamp_created": 3},
        {"recommendationid": "p0-b-2002", "review": "performance is stable", "timestamp_created": 4},
    ]
    storage.upsert_reviews(101, reviews_a)
    storage.upsert_reviews(202, reviews_b)

    with db_module.get_connection() as conn:
        rows = conn.execute(
            text("SELECT review_id, COUNT(DISTINCT app_id) FROM reviews GROUP BY review_id")
        ).fetchall()
    assert len(rows) == 4
    assert all(int(count) == 1 for _, count in rows)


def test_fts_invariant_survives_repeated_upsert_and_update():
    first = {"recommendationid": "p0-r2", "review": "old phrase", "timestamp_created": 1}
    changed = {"recommendationid": "p0-r2", "review": "new phrase", "timestamp_created": 1, "timestamp_updated": 2}
    storage.upsert_reviews(7, [first] * 100)
    storage.upsert_reviews(7, [changed])
    assert storage.search_review_ids(7, "old phrase") == []
    assert storage.search_review_ids(7, "new phrase") == ["p0-r2"]


def test_label_cache_identity_includes_taxonomy_prompt_and_model():
    from senti_next import llm

    assert llm.label_cache_identity("review", "tax-v1", "prompt-v1", "model-a") != llm.label_cache_identity("review", "tax-v2", "prompt-v1", "model-a")


def test_metric_provenance_contract_has_required_fields():
    from senti_next.insights import build_metric_contract

    metric = build_metric_contract(1, numerator=1, denominator=2, population_count=3, classified_count=2, source_type="llm_label", run_id="run-1")
    assert {"numerator", "denominator", "population_count", "classified_count", "source_type", "run_id", "coverage"} <= set(metric)


def test_invalid_fallback_labels_are_excluded_from_formal_denominator():
    from senti_next.insights import formal_metric_denominator

    assert formal_metric_denominator([{"label_source": "rule_fallback", "validated": True}]) == 0


def test_fabricated_evidence_quote_is_rejected():
    from senti_next.evidence import verify_quote

    assert verify_quote("fabricated", "real review text") is False


def test_provider_attempt_has_one_future_ledger_record():
    from senti_next import cost_ledger
    from datetime import datetime, timezone
    from sqlalchemy import text

    call_id, _ = cost_ledger.start_call("fixture", "fixture-model", purpose="classification")
    cost_ledger.finish_call(call_id, started_at=datetime.now(timezone.utc), status="completed", usage={"input_tokens": 100, "output_tokens": 20})
    with db_module.get_connection() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM llm_calls WHERE call_id=:call_id"), {"call_id": call_id}).scalar_one() == 1
