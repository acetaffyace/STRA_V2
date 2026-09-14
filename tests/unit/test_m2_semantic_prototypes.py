from __future__ import annotations

import numpy as np
import pytest

from apps.api.senti_next.embedding_backend import FakeEmbeddingBackend
from apps.api.senti_next.semantic_prototypes import TopicPrototype, build_core_prototypes, match_texts
from apps.api.senti_next.taxonomy_v2 import load_core_taxonomy_v2


def test_core_prototypes_cover_the_versioned_taxonomy_and_matching_is_deterministic():
    prototypes = build_core_prototypes(load_core_taxonomy_v2())
    assert len(prototypes) == 50
    backend = FakeEmbeddingBackend(dimensions=8)
    text = prototypes[0].texts[0]
    first = match_texts([text, ""], prototypes=prototypes, backend=backend, high_threshold=0.99, medium_threshold=0.5)
    second = match_texts([text, ""], prototypes=prototypes, backend=backend, high_threshold=0.99, medium_threshold=0.5)
    assert first == second
    assert first[0].decision_band == "HIGH"
    assert first[0].topic_key == prototypes[0].topic_key
    assert first[1].topic_key is None and first[1].decision_band == "LOW"


class _FixedBackend:
    class _Identity:
        dimensions = 2

    identity = _Identity()

    def encode(self, texts):
        values = {"source": [1.0, 0.0], "topic-a": [1.0, 0.0], "topic-b": [0.0, 1.0], "unknown": [-1.0, 0.0]}
        return np.asarray([values[text] for text in texts], dtype=np.float32)


def test_decision_bands_keep_low_matches_unassigned_and_ties_are_lexically_stable():
    prototypes = [TopicPrototype("topic-b", "p1", ("topic-b",)), TopicPrototype("topic-a", "p1", ("topic-a",))]
    matches = match_texts(["source", "unknown"], prototypes=prototypes, backend=_FixedBackend(), high_threshold=0.9, medium_threshold=0.5)
    assert matches[0].topic_key == "topic-a"
    assert matches[0].decision_band == "HIGH"
    assert matches[1].topic_key is None and matches[1].decision_band == "LOW"
    assert matches[1].similarity_score == 0.0
    with pytest.raises(ValueError, match="semantic_decision_thresholds_invalid"):
        match_texts(["source"], prototypes=prototypes, backend=_FixedBackend(), high_threshold=0.5, medium_threshold=0.5)
