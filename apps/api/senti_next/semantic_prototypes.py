"""Deterministic local embedding prototype matching for Semantic Engine V2."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .embedding_backend import EmbeddingBackend, EmbeddingModelIdentity


@dataclass(frozen=True)
class TopicPrototype:
    topic_key: str
    prototype_version: str
    texts: tuple[str, ...]

    def validate(self) -> None:
        if not self.topic_key or not self.prototype_version or not self.texts or any(not text.strip() for text in self.texts):
            raise ValueError("semantic_prototype_incomplete")


@dataclass(frozen=True)
class SemanticMatch:
    topic_key: str | None
    similarity_score: float | None
    decision_band: str
    assignment_source: str | None
    prototype_version: str
    model_identity: EmbeddingModelIdentity


def _validate_thresholds(high_threshold: float, medium_threshold: float) -> tuple[float, float]:
    high = float(high_threshold)
    medium = float(medium_threshold)
    if not 0 <= medium < high <= 1:
        raise ValueError("semantic_decision_thresholds_invalid")
    return high, medium


def build_core_prototypes(source: Mapping[str, Any], *, prototype_version: str = "core-prototypes-v1") -> tuple[TopicPrototype, ...]:
    topics = source.get("topics")
    if not isinstance(topics, list):
        raise ValueError("semantic_prototype_source_invalid")
    prototypes = []
    for topic in topics:
        if not isinstance(topic, Mapping):
            raise ValueError("semantic_prototype_source_invalid")
        key = str(topic.get("id") or "").strip()
        texts = tuple(dict.fromkeys(str(value).strip() for value in (topic.get("typical_examples") or []) + [topic.get("definition") or ""] if str(value).strip()))
        prototype = TopicPrototype(key, prototype_version, texts)
        prototype.validate()
        prototypes.append(prototype)
    return tuple(sorted(prototypes, key=lambda item: item.topic_key))


def match_texts(
    texts: Sequence[str],
    *,
    prototypes: Sequence[TopicPrototype],
    backend: EmbeddingBackend,
    high_threshold: float = 0.82,
    medium_threshold: float = 0.68,
) -> list[SemanticMatch]:
    """Match each text to its best prototype with deterministic tie-breaking."""
    high, medium = _validate_thresholds(high_threshold, medium_threshold)
    if not prototypes:
        raise ValueError("semantic_prototypes_required")
    for prototype in prototypes:
        prototype.validate()
    source = [str(text or "") for text in texts]
    if not source:
        return []
    prototype_keys = sorted({text for prototype in prototypes for text in prototype.texts})
    vectors = np.asarray(backend.encode(source + prototype_keys), dtype=np.float32)
    expected_shape = (len(source) + len(prototype_keys), backend.identity.dimensions)
    if vectors.shape != expected_shape or not np.isfinite(vectors).all():
        raise ValueError("semantic_embedding_output_invalid")
    source_vectors = vectors[: len(source)]
    prototype_vectors = vectors[len(source):]
    vector_by_text = {text: prototype_vectors[index] for index, text in enumerate(prototype_keys)}
    matches: list[SemanticMatch] = []
    for vector, original in zip(source_vectors, source):
        if not original.strip():
            matches.append(SemanticMatch(None, None, "LOW", None, "none", backend.identity))
            continue
        candidates: list[tuple[float, str, str]] = []
        for prototype in prototypes:
            score = max(float(np.dot(vector, vector_by_text[text])) for text in prototype.texts)
            candidates.append((score, prototype.topic_key, prototype.prototype_version))
        score, topic_key, version = max(candidates, key=lambda item: (item[0], item[1]))
        if score >= high:
            band = "HIGH"
        elif score >= medium:
            band = "MEDIUM"
        else:
            band = "LOW"
        matches.append(SemanticMatch(topic_key if band != "LOW" else None, score, band, "prototype" if band != "LOW" else None, version, backend.identity))
    return matches


__all__ = ["SemanticMatch", "TopicPrototype", "build_core_prototypes", "match_texts"]
