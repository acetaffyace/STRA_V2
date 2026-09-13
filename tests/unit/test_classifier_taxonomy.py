from __future__ import annotations

import pytest

from apps.api.senti_next import llm
from apps.api.senti_next.classifier_taxonomy import (
    BASELINE_TAXONOMY_VERSION,
    ClassifierTaxonomyContract,
    allowed_topic_keys,
    baseline_classifier_taxonomy,
    build_batch_classification_schema,
    build_review_classification_schema,
    load_classifier_taxonomy,
    render_classifier_taxonomy,
)


def test_default_contract_is_frozen_v1_and_matches_classifier_vocabulary():
    contract = load_classifier_taxonomy()
    assert contract.taxonomy_version == BASELINE_TAXONOMY_VERSION
    assert contract.topic_count == 60
    assert set(contract.active_topic_keys) == set(llm._ALLOWED_SUBCATEGORY_KEYS)
    items = [{"review_id": "r", "review_text": "x"}]
    assert llm._build_batch_prompt(items, taxonomy_contract=contract) == llm._build_batch_prompt(items)


def test_v1_prompt_and_schema_parity():
    contract = baseline_classifier_taxonomy()
    items = [{"review_id": "r", "review_text": "x"}]
    assert llm._build_batch_prompt(items, taxonomy_contract=contract) == llm._build_batch_prompt(items)
    assert build_review_classification_schema(contract) == llm._REVIEW_CLASSIFICATION_SCHEMA
    assert build_batch_classification_schema(["r"], contract) == llm._build_batch_json_schema(["r"])


def test_dynamic_contract_supports_three_level_paths_and_active_only_output():
    contract = ClassifierTaxonomyContract(
        "classifier-taxonomy-contract-v1",
        "snapshot-v2",
        "sentinext-taxonomy-v2",
        "fingerprint-v2",
        ("other/general", "ui_ux_accessibility/quality_of_life/camera_options", "other/retired"),
        ("other/general", "ui_ux_accessibility/quality_of_life/camera_options"),
        2,
    )
    contract.validate()
    assert allowed_topic_keys(contract) == contract.active_topic_keys
    assert "camera_options" in render_classifier_taxonomy(contract)
    assert llm._normalize_subcategory_value(
        "ui_ux_accessibility/quality_of_life/camera_options", contract.active_topic_keys
    ) == "ui_ux_accessibility/quality_of_life/camera_options"
    with pytest.raises(ValueError, match="No valid subcategories"):
        llm._parse_payload_mapping({"subcategories": ["other/retired"]}, taxonomy_contract=contract)


def test_dynamic_schema_enum_is_active_topic_set():
    contract = ClassifierTaxonomyContract(
        "classifier-taxonomy-contract-v1", "s", "v2", "f", ("other/general",), ("other/general",), 1
    )
    schema = build_review_classification_schema(contract)
    assert schema["properties"]["subcategories"]["items"]["enum"] == ["other/general"]
    assert build_batch_classification_schema(["a", "b"], contract)["required"] == ["a", "b"]


def test_v3_and_v3_1_are_distinct_identity_variants(monkeypatch):
    item = {"review_id": "r", "review": "A review"}
    v3 = llm.classification_identity(item, None, provider="p", model_id="m", prompt_version=llm.PROMPT_VERSION_V3)
    v31 = llm.classification_identity(item, None, provider="p", model_id="m", prompt_version=llm.PROMPT_VERSION_V3_1)
    assert v3["classification_input_hash"] != v31["classification_input_hash"]
    assert v3["prompt_version"] != v31["prompt_version"]
