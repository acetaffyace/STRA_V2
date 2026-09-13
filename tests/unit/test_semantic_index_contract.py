from __future__ import annotations

import json

import numpy as np
import pytest

from apps.api.senti_next.embedding_backend import (
    DEFAULT_MODEL_REVISION,
    EmbeddingModelIdentity,
    FakeEmbeddingBackend,
)
from apps.api.senti_next.semantic_index import (
    SEMANTIC_CHUNK_SIZE_TOKENS,
    SemanticIndexContract,
    embedding_cache_key,
    preprocess_semantic_text,
)


def test_fake_backend_identity_is_immutable_and_normalized() -> None:
    backend = FakeEmbeddingBackend(dimensions=8)
    values = backend.encode(["query: crash after update"])
    assert values.shape == (1, 8)
    assert values.dtype == np.float32
    assert np.isclose(np.linalg.norm(values[0]), 1.0)
    assert backend.identity.model_revision == "fake-test-revision"


def test_default_revision_is_immutable_huggingface_commit() -> None:
    assert len(DEFAULT_MODEL_REVISION) == 40
    assert DEFAULT_MODEL_REVISION != "main"


def test_contract_is_backend_derived_and_json_serializable() -> None:
    contract = SemanticIndexContract.from_backend(FakeEmbeddingBackend(dimensions=8))
    contract.validate()
    payload = contract.to_dict()
    assert payload["prefix_policy"] == "query"
    assert payload["chunk_size_tokens"] == SEMANTIC_CHUNK_SIZE_TOKENS
    assert json.dumps(payload, sort_keys=True)
    assert contract.fingerprint == SemanticIndexContract.from_backend(FakeEmbeddingBackend(dimensions=8)).fingerprint


@pytest.mark.parametrize(
    "changes",
    [
        {"chunk_size_tokens": 0},
        {"chunk_overlap_tokens": -1},
        {"chunk_overlap_tokens": SEMANTIC_CHUNK_SIZE_TOKENS},
        {"prefix_policy": "passage"},
        {"pooling": "cls"},
        {"normalization": "none"},
        {"model_revision": "main"},
        {"artifact_sha256": ""},
    ],
)
def test_contract_rejects_invalid_semantic_configuration(changes: dict[str, object]) -> None:
    base = SemanticIndexContract.from_backend(FakeEmbeddingBackend(dimensions=8))
    values = base.to_dict()
    values.update(changes)
    with pytest.raises(ValueError):
        SemanticIndexContract(**values).validate()


def test_preprocessing_is_conservative_and_versioned() -> None:
    text = "  更新后\r\n\r\n游戏\t崩溃  😊  "
    assert preprocess_semantic_text(text) == "更新后 游戏 崩溃 😊"


def test_cache_key_changes_when_semantic_contract_changes() -> None:
    backend = FakeEmbeddingBackend(dimensions=8)
    contract = SemanticIndexContract.from_backend(backend)
    original = embedding_cache_key(text_hash="abc", contract=contract)
    changed = SemanticIndexContract.from_backend(backend, preprocessing_version="semantic-text-v2")
    assert original != embedding_cache_key(text_hash="abc", contract=changed)
