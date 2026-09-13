from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from apps.api.senti_next.embedding_backend import FakeEmbeddingBackend
from apps.api.senti_next.semantic_index import (
    SemanticIndexContract,
    build_semantic_index,
    embedding_cache_key,
    semantic_text_hash,
)


def _review(review_id: str, text: str | None) -> dict:
    return {
        "recommendationid": review_id,
        "review": text,
        "voted_up": review_id.endswith("p"),
        "language": "schinese" if review_id.endswith("c") else "english",
        "timestamp_created": 1_700_000_000,
    }


class CountingBackend(FakeEmbeddingBackend):
    def __init__(self, *, model_revision: str = "fake-test-revision") -> None:
        super().__init__(dimensions=16, model_revision=model_revision)
        self.calls: list[list[str]] = []

    def encode(self, texts):  # type: ignore[no-untyped-def]
        self.calls.append(list(texts))
        return super().encode(texts)


def _contract(backend: CountingBackend, **overrides):
    return SemanticIndexContract.from_backend(backend, **overrides)


def test_short_review_creates_one_unit_and_preserves_population_count() -> None:
    backend = CountingBackend()
    result = build_semantic_index(
        [_review("1", "crash after update"), _review("2", "")],
        research_run_id="run-1",
        population_fingerprint="population-a",
        contract=_contract(backend),
        backend=backend,
    )
    assert result.population_n == 2
    assert result.eligible_review_n == 1
    assert result.indexed_review_n == 1
    assert result.semantic_unit_n == 1
    assert result.members[1].exclusion_reason == "empty_text"
    assert len(backend.calls) == 1
    assert backend.calls[0][0].startswith("query: ")


def test_long_review_is_chunked_and_retains_tail() -> None:
    backend = CountingBackend()
    text = " ".join(f"token-{i}" for i in range(700))
    result = build_semantic_index(
        [_review("long", text)],
        research_run_id="run-1",
        population_fingerprint="population-a",
        contract=_contract(backend, chunk_size_tokens=32, chunk_overlap_tokens=8),
        backend=backend,
    )
    assert result.semantic_unit_n > 1
    assert result.units[-1].token_end == 700
    assert "token-699" in result.units[-1].semantic_text


def test_empty_text_variants_are_ineligible_without_denominator_mutation() -> None:
    backend = CountingBackend()
    reviews = [_review("1", "ok"), _review("2", "   "), _review("3", None)]
    result = build_semantic_index(
        reviews,
        research_run_id="run-1",
        population_fingerprint="population-a",
        contract=_contract(backend),
        backend=backend,
    )
    assert result.population_n == 3
    assert result.eligible_review_n == result.indexed_review_n == 1
    assert [m.exclusion_reason for m in result.members] == [None, "empty_text", "empty_text"]


def test_duplicate_texts_keep_all_members_but_compute_one_embedding() -> None:
    backend = CountingBackend()
    reviews = [_review(str(i), "same text") for i in range(10)]
    result = build_semantic_index(
        reviews,
        research_run_id="run-1",
        population_fingerprint="population-a",
        contract=_contract(backend),
        backend=backend,
    )
    assert result.population_n == 10
    assert result.indexed_review_n == 10
    assert result.unique_embedding_n == 1
    assert len(backend.calls) == 1
    assert len(backend.calls[0]) == 1


def test_cache_reuse_and_contract_invalidation() -> None:
    first_backend = CountingBackend(model_revision="revision-a")
    first_contract = _contract(first_backend)
    first = build_semantic_index(
        [_review("1", "same text")],
        research_run_id="run-1",
        population_fingerprint="population-a",
        contract=first_contract,
        backend=first_backend,
    )
    cache = first.embeddings
    second_backend = CountingBackend(model_revision="revision-a")
    second = build_semantic_index(
        [_review("1", "same text")],
        research_run_id="run-2",
        population_fingerprint="population-a",
        contract=_contract(second_backend),
        backend=second_backend,
        embedding_cache=cache,
    )
    assert second.cache_hit_n == 1
    assert not second_backend.calls

    changed_backend = CountingBackend(model_revision="revision-b")
    changed = build_semantic_index(
        [_review("1", "same text")],
        research_run_id="run-3",
        population_fingerprint="population-a",
        contract=_contract(changed_backend),
        backend=changed_backend,
        embedding_cache=cache,
    )
    assert changed.cache_hit_n == 0
    assert changed.cache_miss_n == 1
    assert changed_backend.calls


def test_input_order_does_not_change_fingerprint_or_units() -> None:
    backend = CountingBackend()
    contract = _contract(backend)
    reviews = [_review("b", "two"), _review("a", "one")]
    first = build_semantic_index(reviews, research_run_id="run", population_fingerprint="p", contract=contract, backend=backend)
    second = build_semantic_index(list(reversed(reviews)), research_run_id="run", population_fingerprint="p", contract=contract, backend=backend)
    assert first.index_fingerprint == second.index_fingerprint
    assert [(u.review_id, u.unit_index) for u in first.units] == [(u.review_id, u.unit_index) for u in second.units]


def test_report_and_input_are_not_mutated_by_indexing() -> None:
    backend = CountingBackend()
    reviews = [_review("1", "hello")]
    before = copy.deepcopy(reviews)
    build_semantic_index(reviews, research_run_id="run", population_fingerprint="p", contract=_contract(backend), backend=backend)
    assert reviews == before


def test_index_summary_is_json_safe_and_does_not_include_vectors() -> None:
    backend = CountingBackend()
    result = build_semantic_index([_review("1", "hello")], research_run_id="run", population_fingerprint="p", contract=_contract(backend), backend=backend)
    payload = json.loads(json.dumps(result.summary, sort_keys=True, allow_nan=False))
    assert payload["unique_embedding_n"] == 1
    assert "embeddings" not in payload


def test_review_ids_are_required_and_unique() -> None:
    backend = CountingBackend()
    with pytest.raises(ValueError, match="recommendationid"):
        build_semantic_index([{"review": "missing id"}], research_run_id="run", population_fingerprint="p", contract=_contract(backend), backend=backend)
    with pytest.raises(ValueError, match="unique"):
        build_semantic_index([_review("1", "one"), _review("1", "two")], research_run_id="run", population_fingerprint="p", contract=_contract(backend), backend=backend)
