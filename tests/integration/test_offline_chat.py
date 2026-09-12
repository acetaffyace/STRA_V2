from __future__ import annotations

from apps.api.senti_next.offline_chat import answer_offline_question


def test_offline_chat_returns_verified_source_quotes_without_provider():
    result = {
        "mode": "codex_offline_fixture",
        "insights": {"five_questions": {"what_matters": {"signals": [{"topic": "technical/bugs"}]}}},
        "reviews": [{"review_id": "r1", "review": "The controller crashes after the update."}],
    }
    answer = answer_offline_question(result, "What matters?")
    assert answer["mode"] == "codex_offline_fixture"
    assert answer["causal_claim"] is False
    assert answer["citations"][0]["verification_status"] == "verified"
    assert answer["citations"][0]["quote"] in result["reviews"][0]["review"]

