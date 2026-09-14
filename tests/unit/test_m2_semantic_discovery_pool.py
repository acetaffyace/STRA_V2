from __future__ import annotations

import pytest

from apps.api.senti_next.semantic_discovery_pool import build_discovery_pool, sample_cluster_evidence


def _unit(unit_id: str, band: str, topic: str = "gameplay/mechanics", review_id: str | None = None, language: str = "english", score: float = 0.5) -> dict:
    return {"semantic_unit_id": unit_id, "review_id": review_id or unit_id, "decision_band": band, "core_topic_id": topic, "language": language, "similarity_score": score}


def test_discovery_pool_is_reason_coded_and_order_independent() -> None:
    units = [_unit("high-1", "HIGH"), _unit("medium-1", "MEDIUM"), _unit("low-1", "LOW"), _unit("recent-1", "HIGH", review_id="burst"), _unit("novel-1", "HIGH")]
    first = build_discovery_pool(units, seed="run", max_low=1, max_medium=1, max_high_per_topic=0, high_volume_topic_min=100, recent_review_ids=["burst"], novelty_unit_ids=["novel-1"])
    second = build_discovery_pool(reversed(units), seed="run", max_low=1, max_medium=1, max_high_per_topic=0, high_volume_topic_min=100, recent_review_ids=["burst"], novelty_unit_ids=["novel-1"])
    assert [item["semantic_unit_id"] for item in first] == [item["semantic_unit_id"] for item in second]
    reasons = {item["semantic_unit_id"]: item["pool_reasons"] for item in first}
    assert reasons["low-1"] == ["low_confidence"]
    assert reasons["recent-1"] == ["recent_temporal_burst"]
    assert reasons["novel-1"] == ["novelty_or_outlier"]


def test_high_volume_topic_sampling_and_cluster_evidence_types() -> None:
    units = [_unit(f"high-{index}", "HIGH", score=0.4 + index / 100, language="english" if index % 2 else "japanese") for index in range(3)]
    pool = build_discovery_pool(units, seed="run", max_high_per_topic=2, high_volume_topic_min=3)
    assert len(pool) == 2
    assert all("high_volume_topic_sample" in item["pool_reasons"] for item in pool)
    evidence = sample_cluster_evidence(pool, representative_ids=[pool[0]["semantic_unit_id"]], limit_per_type=1)
    assert set(evidence) == {"central", "diverse", "boundary"}
    assert all(len(values) == 1 for values in evidence.values())


def test_discovery_pool_rejects_invalid_units() -> None:
    with pytest.raises(ValueError, match="discovery_pool_unit_identity_invalid"):
        build_discovery_pool([{"semantic_unit_id": "u", "review_id": "r", "decision_band": "UNKNOWN"}], seed="run")

