from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))
os.environ["DATABASE_URL"] = "sqlite://"


def test_exact_partial_and_normalized_quotes_use_source_slice():
    from senti_next.evidence import verify_evidence

    source = "The combat feels excellent but the UI is confusing."
    exact = verify_evidence(source, "The combat feels excellent")
    assert exact["verification_status"] == "verified"
    assert exact["quote"] == "The combat feels excellent"
    assert source[exact["quote_start"]:exact["quote_end"]] == exact["quote"]

    partial = verify_evidence(source, "the UI is confusing")
    assert partial["verification_status"] == "verified"
    assert partial["quote"] == "the UI is confusing"

    normalized = verify_evidence("The game  crashes\nconstantly.", "The game crashes constantly.")
    assert normalized["verification_status"] == "verified"
    assert normalized["quote"] == "The game  crashes\nconstantly."
    assert normalized["verification_method"] == "normalized_source_slice"


def test_fabricated_altered_wrong_review_app_and_scope_are_rejected():
    from senti_next.evidence import verify_evidence

    assert verify_evidence("The combat feels excellent.", "The combat is terrible.")["verification_status"] == "rejected"
    assert verify_evidence(
        "The combat feels excellent.", "The combat feels excellent.",
        review_id="B", source_review_id="A",
    )["unavailable_reason"] == "review_id_mismatch"
    assert verify_evidence(
        "The combat feels excellent.", "The combat feels excellent.",
        review_id="A", source_review_id="A", app_id=2, source_app_id=1,
    )["unavailable_reason"] == "app_id_mismatch"
    assert verify_evidence(
        "The combat feels excellent.", "The combat feels excellent.",
        review_id="A", allowed_review_ids={"B"},
    )["unavailable_reason"] == "review_outside_run_scope"
    assert verify_evidence(None, "anything")["verification_status"] == "rejected"


def test_invalid_chat_quote_is_removed_and_valid_quote_uses_source():
    from senti_next.evidence import gate_response_quotes

    result = gate_response_quotes(
        'Players said "The combat feels excellent." but also "The combat is terrible."',
        [{"review_id": "r1", "app_id": 7, "text": "The combat feels excellent."}],
    )
    assert '"The combat feels excellent."' in result["response"]
    assert "[unverified direct quote removed]" in result["response"]
    assert len(result["evidence"]) == 1
    assert result["rejected_quotes"] == ["The combat is terrible."]


def test_historical_evidence_keeps_immutable_source_snapshot():
    from senti_next.evidence import build_evidence, source_review_hash

    old = "Performance is terrible after patch."
    item = build_evidence(old, old, review_id="123", app_id=7, run_id="run-a")
    current = "Performance is fixed now. Great update."
    assert item["verification_status"] == "verified"
    assert item["source_review_text"] == old
    assert item["source_review_hash"] == source_review_hash(old)
    assert old in item["source_review_text"]
    assert current != item["source_review_text"]


def test_chat_evidence_snapshot_is_persisted_with_message():
    from senti_next import db as db_module, storage

    db_module.close_engine()
    db_module._engine = None
    db_module.init_db()
    snapshot = {
        "review_id": "r1",
        "run_id": None,
        "quote": "The combat feels excellent.",
        "source_review_text": "The combat feels excellent.",
        "source_review_hash": source_hash("The combat feels excellent."),
        "verification_status": "verified",
    }
    storage.save_chat_message("assistant", '"The combat feels excellent."', session_id="s1", evidence=[snapshot])
    loaded = storage.load_chat_history(session_id="s1")
    assert loaded[-1]["evidence"][0]["source_review_text"] == "The combat feels excellent."
    db_module.close_engine()
    db_module._engine = None


def source_hash(value: str) -> str:
    from senti_next.evidence import source_review_hash
    return source_review_hash(value)


def test_insight_evidence_only_serializes_verified_source_slices():
    from senti_next.insights import aggregate_subcategory_insights

    frame = pd.DataFrame([
        {
            "review_id": "r1",
            "review": "Performance drops during boss fights.",
            "language": "english",
            "votes_up": 10,
            "voted_up": False,
            "llm_subcategories": ["technical/performance"],
            "llm_issue_subcategories": ["technical/performance"],
            "llm_request_subcategories": [],
            "llm_subcategory_evidence": {
                "technical/performance": ["Performance drops during boss fights.", "Performance tanks during boss fights."],
            },
        }
    ])
    result = aggregate_subcategory_insights(frame, run_id="run-a", app_id=7)
    assert len(result) == 1
    assert result[0]["issue_snippets"] == ["Performance drops during boss fights."]
    assert result[0]["issue_evidence"][0]["verification_status"] == "verified"
