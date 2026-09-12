"""Tests for the version-event Player Voice Review vertical slice."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SENTINEXT_LOG_FILE"] = "/tmp/sentinext-version-runs.log"

from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.api.main import app
from apps.api.senti_next import db as db_module
from apps.api.senti_next.llm import normalize_taxonomy_payload


client = TestClient(app, raise_server_exceptions=False)
db_module.startup_complete.set()


@pytest.fixture(autouse=True)
def fresh_database():
    db_module.close_engine()
    db_module.init_db()
    yield
    db_module.close_engine()


def _seed_review(review_id: str, timestamp: int, voted_up: bool, app_id: int = 42, review_text: str | None = None) -> None:
    payload = {
        "recommendationid": review_id,
        "timestamp_created": timestamp,
        "voted_up": voted_up,
        "language": "english",
        "review": review_text or f"Review {review_id}",
    }
    with db_module.get_connection() as conn:
        conn.execute(
            text("""
                INSERT INTO reviews (app_id, review_id, data, timestamp_created)
                VALUES (:app_id, :review_id, :data, :timestamp_created)
            """),
            {
                "review_id": review_id,
                "app_id": app_id,
                "data": json.dumps(payload),
                "timestamp_created": timestamp,
            },
        )


def _seed_label(review_id: str, subcategories: list[str], issues: list[str], evidence: dict | None = None, aspects: list[dict] | None = None, app_id: int = 42) -> None:
    with db_module.get_connection() as conn:
        conn.execute(
            text("""
                INSERT INTO review_labels (app_id, review_id, model, prompt_version, payload)
                VALUES (:app_id, :review_id, 'test-model', 'test-prompt', :payload)
            """),
            {
                "review_id": review_id,
                "app_id": app_id,
                "payload": json.dumps({
                    "subcategories": subcategories,
                    "issue_subcategories": issues,
                    "request_subcategories": [],
                    "evidence": evidence or {},
                    "aspects": aspects or [],
                }),
            },
        )


def test_create_run_validates_event_target_and_preserves_config():
    event = client.post(
        "/version-events",
        json={
            "app_id": 42,
            "event_name": "Patch 1.1",
            "event_date": "2026-08-01",
            "event_type": "patch",
        },
    )
    assert event.status_code == 201
    event_id = event.json()["event_id"]

    response = client.post(
        "/runs",
        json={
            "target_app_id": 42,
            "event_id": event_id,
            "pre_window_days": 28,
            "post_window_days": 28,
            "competitor_app_ids": [100, 101],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "created"
    assert body["config"]["event"]["event_date"] == "2026-08-01"
    assert body["config"]["competitors"] == [{"appid": 100}, {"appid": 101}]
    assert body["config"]["manifest"]["prompt_version"]


def test_build_metrics_separates_pre_and_post_windows():
    event = client.post(
        "/version-events",
        json={
            "app_id": 42,
            "event_name": "Patch 1.1",
            "event_date": "2026-08-01",
            "event_type": "patch",
        },
    ).json()
    run = client.post(
        "/runs",
        json={"target_app_id": 42, "event_id": event["event_id"]},
    ).json()

    # 2026-07-20 is pre; 2026-08-10 is post.
    _seed_review("pre-1", 1784505600, True)
    _seed_review("pre-2", 1784505600, True)
    _seed_review("post-1", 1786312800, False, review_text="The patch still crashes on launch.")
    _seed_review("post-2", 1786312800, False, review_text="Performance became much worse after the update.")
    _seed_label("pre-1", ["technical/performance"], [])
    _seed_label("pre-2", ["technical/performance"], [])
    _seed_label("post-1", ["technical/performance"], ["technical/performance"], {"technical/performance": ["The patch still crashes on launch."]})
    _seed_label("post-2", ["technical/performance"], ["technical/performance"], {"technical/performance": ["Performance became much worse after the update."]})

    response = client.post(f"/runs/{run['run_id']}/metrics")
    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics["periods"]["pre"]["reviews"] == 2
    assert metrics["periods"]["pre"]["recommendation_rate"] == 1.0
    assert metrics["periods"]["post"]["recommendation_rate"] == 0.0
    category = next(item for item in metrics["categories"] if item["subcategory"] == "technical/performance")
    assert category["pre_issue_rate"] == 0.0
    assert category["post_issue_rate"] == 1.0
    assert category["sentiment_available"] is False
    assert category["priority_score"] > 0
    assert category["priority_score_is_proxy"] is True
    assert len(metrics["issue_cards"]) == 1
    assert metrics["recommendations"][0]["action_type"] == "product"
    assert metrics["recommendations"][0]["validation_metrics"]
    assert metrics["emerging_topic_candidates"] == []
    assert len(metrics["evidence_cards"]) == 2
    assert metrics["evidence_cards"][0]["source"] == "llm_label_evidence"
    assert metrics["periods"]["pre"]["segments"]["playtime_at_review"]["0-2h"]["reviews"] == 2
    assert metrics["periods"]["post"]["segments"]["language"]["english"]["recommendation_rate"] == 0.0
    assert metrics["daily_review_volume"]["2026-07-20"] == 2

    issues = client.get(f"/runs/{run['run_id']}/issues")
    assert issues.status_code == 200
    assert issues.json()["issues"][0]["subcategory"] == "technical/performance"
    evidence = client.get(f"/runs/{run['run_id']}/evidence", params={"subcategory": "technical/performance"})
    assert evidence.status_code == 200
    assert len(evidence.json()["evidence"]) == 2
    recommendations = client.get(f"/runs/{run['run_id']}/recommendations")
    assert recommendations.status_code == 200
    assert recommendations.json()["recommendations"][0]["issue_id"]


def test_competitors_use_the_same_event_window_and_taxonomy_contract():
    event = client.post(
        "/version-events",
        json={
            "app_id": 42,
            "event_name": "Patch comparison",
            "event_date": "2026-08-01",
            "event_type": "patch",
        },
    ).json()
    run = client.post(
        "/runs",
        json={"target_app_id": 42, "event_id": event["event_id"], "competitor_app_ids": [99]},
    ).json()
    _seed_review("target-post", 1786312800, False, app_id=42)
    _seed_label("target-post", ["technical/performance"], ["technical/performance"], app_id=42)
    _seed_review("competitor-post", 1786312800, True, app_id=99)
    _seed_label("competitor-post", ["technical/performance"], [], app_id=99)

    response = client.post(f"/runs/{run['run_id']}/metrics")
    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics["comparison_contract"]["same_event_date"] == "2026-08-01"
    assert metrics["comparison_contract"]["same_taxonomy_version"] == "sentinext-taxonomy-v1"
    assert metrics["competitors"][0]["app_id"] == 99
    assert metrics["competitors"][0]["periods"]["post"]["recommendation_rate"] == 1.0
    comparison = client.get(f"/runs/{run['run_id']}/comparison")
    assert comparison.status_code == 200
    assert comparison.json()["competitors"][0]["app_id"] == 99


def test_emerging_topics_are_candidates_and_require_human_review():
    event = client.post(
        "/version-events",
        json={"app_id": 42, "event_name": "Emerging issue patch", "event_date": "2026-08-01", "event_type": "patch"},
    ).json()
    run = client.post("/runs", json={"target_app_id": 42, "event_id": event["event_id"]}).json()
    _seed_review("emerging-1", 1786312800, False, review_text="The stutterstorm effect makes every fight unbearable.")
    _seed_review("emerging-2", 1786312800, False, review_text="Stutterstorm appears again after the patch.")
    _seed_label("emerging-1", ["other/general"], [], app_id=42)
    _seed_label("emerging-2", ["other/general"], [], app_id=42)

    response = client.post(f"/runs/{run['run_id']}/metrics")
    assert response.status_code == 200
    candidates = response.json()["metrics"]["emerging_topic_candidates"]
    candidate = next(item for item in candidates if item["candidate_name"] == "stutterstorm")
    assert candidate["mention_count"] == 2
    assert candidate["review_status"] == "pending_review"
    assert candidate["discovery_method"] == "lexical_v1"
    topics = client.get(f"/runs/{run['run_id']}/emerging-topics")
    assert topics.status_code == 200
    assert topics.json()["human_review_required"] is True


def test_run_rejects_event_for_another_game():
    event = client.post(
        "/version-events",
        json={
            "app_id": 7,
            "event_name": "Other game patch",
            "event_date": "2026-08-01",
            "event_type": "patch",
        },
    ).json()
    response = client.post(
        "/runs",
        json={"target_app_id": 42, "event_id": event["event_id"]},
    )
    assert response.status_code == 400


def test_run_accepts_unverified_event_and_rejects_invalid_language():
    unverified = client.post(
        "/version-events",
        json={
            "app_id": 42,
            "event_name": "Unverified patch",
            "event_date": "2026-08-01",
            "event_type": "patch",
            "manual_verified": False,
        },
    ).json()
    response = client.post("/runs", json={"target_app_id": 42, "event_id": unverified["event_id"]})
    assert response.status_code == 201

    verified = client.post(
        "/version-events",
        json={
            "app_id": 42,
            "event_name": "Verified patch",
            "event_date": "2026-08-01",
            "event_type": "patch",
        },
    ).json()
    response = client.post(
        "/runs",
        json={"target_app_id": 42, "event_id": verified["event_id"], "languages": ["klingon"]},
    )
    assert response.status_code == 400


def test_aspect_sentiment_drives_negative_rate_and_priority():
    event = client.post(
        "/version-events",
        json={
            "app_id": 42,
            "event_name": "Patch 1.2",
            "event_date": "2026-08-01",
            "event_type": "patch",
        },
    ).json()
    run = client.post("/runs", json={"target_app_id": 42, "event_id": event["event_id"]}).json()

    _seed_review("aspect-pre", 1784505600, True, review_text="The game runs smoothly.")
    _seed_review("aspect-post", 1786312800, False, review_text="The game crashes on launch.")
    _seed_label(
        "aspect-pre",
        ["technical/performance"],
        [],
        aspects=[{"aspect": "technical/performance", "sentiment": 1, "evidence_span": "runs smoothly", "confidence": 0.9}],
    )
    _seed_label(
        "aspect-post",
        ["technical/performance"],
        ["technical/performance"],
        aspects=[{"aspect": "technical/performance", "sentiment": -2, "evidence_span": "crashes on launch", "confidence": 0.8}],
    )

    response = client.post(f"/runs/{run['run_id']}/metrics")
    assert response.status_code == 200
    category = response.json()["metrics"]["categories"][0]
    assert category["sentiment_available"] is True
    assert category["pre_negative_rate"] == 0.0
    assert category["post_negative_rate"] == 1.0
    assert category["delta_negative_rate"] == 1.0
    assert category["priority_note"].startswith("Uses aspect negative rate")
    evidence = client.get(f"/runs/{run['run_id']}/evidence")
    assert any(item["source"] == "aspect_sentiment" for item in evidence.json()["evidence"])


def test_aspect_payload_normalization_is_bounded_and_legacy_safe():
    normalized = normalize_taxonomy_payload({
        "subcategories": ["technical/performance"],
        "aspects": [
            {"aspect": "technical/performance", "sentiment": -2, "evidence_span": "stutters", "confidence": 0.92},
            {"aspect": "not/a-real-topic", "sentiment": 2, "evidence_span": "ignored", "confidence": 1},
            {"aspect": "technical/performance", "sentiment": 9, "evidence_span": "ignored", "confidence": 1},
        ],
    })
    assert normalized["aspects"] == [{
        "aspect": "technical/performance",
        "subtopic": "",
        "sentiment": -2,
        "evidence_span": "stutters",
        "confidence": 0.92,
    }]
    assert normalize_taxonomy_payload({"subcategories": ["other/general"]})["aspects"] == []
