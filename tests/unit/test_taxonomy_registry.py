from __future__ import annotations

from apps.api.senti_next import llm
from apps.api.senti_next.taxonomy_registry import (
    BASELINE_TAXONOMY_V1,
    BASELINE_TAXONOMY_VERSION,
    baseline_topics,
    build_baseline_snapshot,
    build_snapshot,
    snapshot_id_for,
    taxonomy_fingerprint,
    topic_id_for_key,
)


def test_baseline_registry_matches_frozen_classifier_taxonomy() -> None:
    assert set(BASELINE_TAXONOMY_V1) == set(llm._ALLOWED_SUBCATEGORY_KEYS)
    assert len(BASELINE_TAXONOMY_V1) == len(llm._ALLOWED_SUBCATEGORY_KEYS)
    snapshot = build_baseline_snapshot()
    assert snapshot.taxonomy_version == BASELINE_TAXONOMY_VERSION
    assert snapshot.status == "published"
    assert len(snapshot.topics) == len(BASELINE_TAXONOMY_V1)
    assert {topic.canonical_key for topic in snapshot.topics} == set(llm._ALLOWED_SUBCATEGORY_KEYS)


def test_topic_identity_and_fingerprint_are_content_addressed() -> None:
    topics = baseline_topics()
    snapshot = build_baseline_snapshot()
    assert topic_id_for_key("technical/performance") == next(topic.topic_id for topic in topics if topic.canonical_key == "technical/performance")
    assert taxonomy_fingerprint(list(reversed(topics))) == snapshot.taxonomy_fingerprint
    assert snapshot_id_for(snapshot.taxonomy_version, snapshot.parent_snapshot_id, list(reversed(topics))) == snapshot.snapshot_id


def test_child_topic_validation_rejects_cycles() -> None:
    topics = list(baseline_topics())
    topics[0] = type(topics[0])(**{**topics[0].to_dict(), "parent_topic_id": topics[1].topic_id})
    topics[1] = type(topics[1])(**{**topics[1].to_dict(), "parent_topic_id": topics[0].topic_id})
    try:
        build_snapshot(topics, taxonomy_version="sentinext-taxonomy-v-test")
    except ValueError as exc:
        assert str(exc) == "taxonomy_cycle"
    else:  # pragma: no cover - assertion guard
        raise AssertionError("taxonomy cycle was accepted")
