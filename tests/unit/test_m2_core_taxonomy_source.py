from __future__ import annotations

import json

import pytest

from apps.api.senti_next.taxonomy_v2 import CORE_TOPIC_IDS, core_taxonomy_fingerprint, load_core_taxonomy_v2, validate_core_taxonomy_v2


def test_core_taxonomy_v2_has_the_frozen_50_topics_and_complete_definition_contract():
    source = load_core_taxonomy_v2()
    assert source["taxonomy_version"] == "stra-core-taxonomy-v2"
    assert [topic["id"] for topic in source["topics"]] == list(CORE_TOPIC_IDS)
    assert len({topic["id"] for topic in source["topics"]}) == 50
    assert all(len(topic["typical_examples"]) >= 1 and len(topic["counterexamples"]) >= 1 for topic in source["topics"])
    assert core_taxonomy_fingerprint(source) == core_taxonomy_fingerprint(json.loads(json.dumps(source, ensure_ascii=False)))


@pytest.mark.parametrize("field", ["definition", "include", "exclude", "boundary", "typical_examples", "counterexamples"])
def test_core_taxonomy_validator_rejects_missing_required_fields(field: str):
    source = load_core_taxonomy_v2()
    del source["topics"][0][field]
    with pytest.raises(ValueError, match="core_taxonomy_topic_required_field_missing|core_taxonomy_topic_definition_incomplete|core_taxonomy_topic_examples_incomplete"):
        validate_core_taxonomy_v2(source)


def test_core_taxonomy_validator_rejects_renamed_or_duplicate_topics():
    source = load_core_taxonomy_v2()
    source["topics"][0]["id"] = source["topics"][1]["id"]
    with pytest.raises(ValueError, match="core_taxonomy_topic_id_invalid_or_duplicate|core_taxonomy_topic_ids_mismatch"):
        validate_core_taxonomy_v2(source)
