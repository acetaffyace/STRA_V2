"""Stage 3A full-population semantic index infrastructure.

This module represents text; it does not interpret text.  It deliberately has
no taxonomy, LLM, route, Research Core, or Stage 2E dependencies.  A semantic
index is a derived view of one frozen Research Population and never changes
that population's denominator or report.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

import numpy as np

from .embedding_backend import (
    DEFAULT_DIMENSIONS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_REVISION,
    DEFAULT_NORMALIZATION,
    DEFAULT_POOLING,
    DEFAULT_PREFIX_POLICY,
    EmbeddingBackend,
    EmbeddingModelIdentity,
)


SEMANTIC_INDEX_SCHEMA_VERSION = "semantic-index-contract-v1"
SEMANTIC_TEXT_PREPROCESSING_VERSION = "semantic-text-v1"
SEMANTIC_CHUNKING_VERSION = "semantic-chunk-v1"
SEMANTIC_PREFIX_POLICY = DEFAULT_PREFIX_POLICY
SEMANTIC_POOLING = DEFAULT_POOLING
SEMANTIC_NORMALIZATION = DEFAULT_NORMALIZATION
SEMANTIC_CHUNK_SIZE_TOKENS = 448
SEMANTIC_CHUNK_OVERLAP_TOKENS = 64

_WHITESPACE_RE = re.compile(r"\s+")


def preprocess_semantic_text(text: Any) -> str:
    """Conservatively normalize text while preserving language and punctuation."""
    if text is None:
        return ""
    value = unicodedata.normalize("NFKC", str(text)).replace("\r\n", "\n").replace("\r", "\n")
    return _WHITESPACE_RE.sub(" ", value).strip()


def semantic_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SemanticIndexContract:
    schema_version: str = SEMANTIC_INDEX_SCHEMA_VERSION
    model_id: str = DEFAULT_MODEL_ID
    model_revision: str = DEFAULT_MODEL_REVISION
    artifact_sha256: str = "unresolved"
    preprocessing_version: str = SEMANTIC_TEXT_PREPROCESSING_VERSION
    chunking_version: str = SEMANTIC_CHUNKING_VERSION
    prefix_policy: str = SEMANTIC_PREFIX_POLICY
    pooling: str = SEMANTIC_POOLING
    normalization: str = SEMANTIC_NORMALIZATION
    dimensions: int = DEFAULT_DIMENSIONS
    max_tokens: int = DEFAULT_MAX_TOKENS
    chunk_size_tokens: int = SEMANTIC_CHUNK_SIZE_TOKENS
    chunk_overlap_tokens: int = SEMANTIC_CHUNK_OVERLAP_TOKENS

    def validate(self) -> None:
        if self.schema_version != SEMANTIC_INDEX_SCHEMA_VERSION:
            raise ValueError(f"unsupported semantic index schema: {self.schema_version}")
        if not self.model_id:
            raise ValueError("model_id is required")
        if not self.model_revision or self.model_revision.lower() == "main":
            raise ValueError("immutable model_revision is required")
        if not self.artifact_sha256 or self.artifact_sha256 == "unresolved":
            raise ValueError("artifact_sha256 is required")
        if self.prefix_policy != SEMANTIC_PREFIX_POLICY:
            raise ValueError(f"unsupported prefix policy: {self.prefix_policy}")
        if self.pooling != SEMANTIC_POOLING:
            raise ValueError(f"unsupported pooling: {self.pooling}")
        if self.normalization != SEMANTIC_NORMALIZATION:
            raise ValueError(f"unsupported normalization: {self.normalization}")
        if self.dimensions <= 0 or self.max_tokens <= 0:
            raise ValueError("dimensions and max_tokens must be positive")
        if self.chunk_size_tokens <= 0:
            raise ValueError("chunk_size_tokens must be positive")
        if self.chunk_overlap_tokens < 0 or self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("chunk_overlap_tokens must be >= 0 and less than chunk_size_tokens")

    @classmethod
    def from_backend(cls, backend: EmbeddingBackend, **overrides: Any) -> "SemanticIndexContract":
        identity = backend.identity
        contract = cls(
            model_id=identity.model_id,
            model_revision=identity.model_revision,
            artifact_sha256=identity.artifact_sha256,
            dimensions=identity.dimensions,
            max_tokens=identity.max_tokens,
            pooling=identity.pooling,
            normalization=identity.normalization,
            prefix_policy=identity.prefix_policy,
            **overrides,
        )
        contract.validate()
        return contract

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "artifact_sha256": self.artifact_sha256,
            "preprocessing_version": self.preprocessing_version,
            "chunking_version": self.chunking_version,
            "prefix_policy": self.prefix_policy,
            "pooling": self.pooling,
            "normalization": self.normalization,
            "dimensions": self.dimensions,
            "max_tokens": self.max_tokens,
            "chunk_size_tokens": self.chunk_size_tokens,
            "chunk_overlap_tokens": self.chunk_overlap_tokens,
        }

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SemanticUnit:
    review_id: str
    unit_index: int
    semantic_text_hash: str
    semantic_text: str
    token_start: int
    token_end: int
    token_count: int
    embedding_key: str


@dataclass(frozen=True)
class SemanticIndexMember:
    review_id: str
    review_text_hash: Optional[str]
    eligible: bool
    exclusion_reason: Optional[str]
    semantic_unit_count: int


@dataclass
class SemanticIndexBuildResult:
    schema_version: str
    research_run_id: str
    population_fingerprint: str
    contract: SemanticIndexContract
    model_identity: EmbeddingModelIdentity
    population_n: int
    eligible_review_n: int
    indexed_review_n: int
    semantic_unit_n: int
    unique_embedding_n: int
    cache_hit_n: int
    cache_miss_n: int
    members: list[SemanticIndexMember]
    units: list[SemanticUnit]
    embeddings: dict[str, np.ndarray] = field(default_factory=dict, repr=False)
    index_fingerprint: str = ""

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "research_run_id": self.research_run_id,
            "population_fingerprint": self.population_fingerprint,
            "population_n": self.population_n,
            "eligible_review_n": self.eligible_review_n,
            "indexed_review_n": self.indexed_review_n,
            "semantic_unit_n": self.semantic_unit_n,
            "unique_embedding_n": self.unique_embedding_n,
            "cache_hit_n": self.cache_hit_n,
            "cache_miss_n": self.cache_miss_n,
            "model_identity": self.model_identity.to_dict(),
            "contract": self.contract.to_dict(),
            "index_fingerprint": self.index_fingerprint,
        }


class SemanticIndexBuildError(RuntimeError):
    """Embedding failure with the deterministic index counts built so far."""

    def __init__(self, message: str, partial_result: SemanticIndexBuildResult) -> None:
        super().__init__(message)
        self.partial_result = partial_result


def embedding_cache_key(*, text_hash: str, contract: SemanticIndexContract) -> str:
    contract.validate()
    payload = {
        "semantic_text_hash": text_hash,
        "model_id": contract.model_id,
        "model_revision": contract.model_revision,
        "artifact_sha256": contract.artifact_sha256,
        "preprocessing_version": contract.preprocessing_version,
        "chunking_version": contract.chunking_version,
        "prefix_policy": contract.prefix_policy,
        "pooling": contract.pooling,
        "normalization": contract.normalization,
        "dimensions": contract.dimensions,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _tokenize(backend: EmbeddingBackend, text: str) -> list[Any]:
    method = getattr(backend, "tokenize", None)
    if callable(method):
        return list(method(text))
    # Compatibility fallback for very small custom test backends.  The real
    # ONNX backend always provides tokenizer-derived boundaries.
    return text.split()


def _decode(backend: EmbeddingBackend, tokens: Sequence[Any]) -> str:
    method = getattr(backend, "decode", None)
    if callable(method):
        return preprocess_semantic_text(method(tokens))
    return preprocess_semantic_text(" ".join(str(item) for item in tokens))


def _chunks(backend: EmbeddingBackend, text: str, contract: SemanticIndexContract) -> list[tuple[str, int, int, int]]:
    tokens = _tokenize(backend, text)
    if not tokens:
        return []
    size = contract.chunk_size_tokens
    step = size - contract.chunk_overlap_tokens
    output: list[tuple[str, int, int, int]] = []
    start = 0
    while start < len(tokens):
        end = min(start + size, len(tokens))
        chunk_text = _decode(backend, tokens[start:end])
        if chunk_text:
            output.append((chunk_text, start, end, end - start))
        if end >= len(tokens):
            break
        start += step
    return output


def _identity_matches(contract: SemanticIndexContract, identity: EmbeddingModelIdentity) -> None:
    if contract.model_id != identity.model_id or contract.model_revision != identity.model_revision:
        raise ValueError("semantic contract model identity does not match embedding backend")
    if contract.artifact_sha256 != identity.artifact_sha256:
        raise ValueError("semantic contract artifact checksum does not match embedding backend")
    if contract.dimensions != identity.dimensions:
        raise ValueError("semantic contract dimensions do not match embedding backend")


def _index_fingerprint(
    population_fingerprint: str,
    contract: SemanticIndexContract,
    members: Sequence[SemanticIndexMember],
    units: Sequence[SemanticUnit],
) -> str:
    payload = {
        "population_fingerprint": population_fingerprint,
        "contract_fingerprint": contract.fingerprint,
        "members": [member.__dict__ for member in sorted(members, key=lambda item: item.review_id)],
        "units": [
            {
                "review_id": unit.review_id,
                "unit_index": unit.unit_index,
                "semantic_text_hash": unit.semantic_text_hash,
                "token_start": unit.token_start,
                "token_end": unit.token_end,
                "token_count": unit.token_count,
                "embedding_key": unit.embedding_key,
            }
            for unit in sorted(units, key=lambda item: (item.review_id, item.unit_index))
        ],
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_semantic_index(
    reviews: Iterable[Mapping[str, Any]],
    *,
    research_run_id: str,
    population_fingerprint: str,
    contract: SemanticIndexContract,
    backend: EmbeddingBackend,
    embedding_cache: Optional[Mapping[str, np.ndarray]] = None,
) -> SemanticIndexBuildResult:
    """Build a deterministic index view without mutating reviews or Research Core.

    ``embedding_cache`` is keyed by the full contract-aware key.  Vectors are
    encoded once per unique key, while every eligible review/unit remains a
    member of the population index.
    """
    if not research_run_id:
        raise ValueError("research_run_id is required")
    if not population_fingerprint:
        raise ValueError("population_fingerprint is required")
    contract.validate()
    _identity_matches(contract, backend.identity)
    source = [dict(item) for item in reviews]
    review_ids = [str(item.get("recommendationid") or item.get("review_id") or "") for item in source]
    if any(not item for item in review_ids):
        raise ValueError("every review must have a recommendationid/review_id")
    if len(set(review_ids)) != len(review_ids):
        raise ValueError("Research Population review IDs must be unique")
    ordered = sorted(zip(review_ids, source), key=lambda pair: pair[0])
    cache = dict(embedding_cache or {})
    members: list[SemanticIndexMember] = []
    units: list[SemanticUnit] = []
    embeddings: dict[str, np.ndarray] = {}
    pending_texts: dict[str, str] = {}
    pending_order: list[str] = []

    for review_id, review in ordered:
        normalized = preprocess_semantic_text(review.get("review"))
        if not normalized:
            members.append(SemanticIndexMember(review_id, None, False, "empty_text", 0))
            continue
        text_hash = semantic_text_hash(normalized)
        chunks = _chunks(backend, normalized, contract)
        if not chunks:
            members.append(SemanticIndexMember(review_id, text_hash, False, "tokenization_empty", 0))
            continue
        members.append(SemanticIndexMember(review_id, text_hash, True, None, len(chunks)))
        for unit_index, (chunk_text, token_start, token_end, token_count) in enumerate(chunks):
            chunk_hash = semantic_text_hash(chunk_text)
            key = embedding_cache_key(text_hash=chunk_hash, contract=contract)
            units.append(SemanticUnit(review_id, unit_index, chunk_hash, chunk_text, token_start, token_end, token_count, key))
            if key in cache:
                embeddings[key] = np.asarray(cache[key], dtype=np.float32)
            elif key not in pending_texts:
                pending_texts[key] = f"query: {chunk_text}"
                pending_order.append(key)

    if pending_order:
        try:
            encoded = np.asarray(backend.encode([pending_texts[key] for key in pending_order]), dtype=np.float32)
        except Exception as exc:
            partial = SemanticIndexBuildResult(
                schema_version=SEMANTIC_INDEX_SCHEMA_VERSION,
                research_run_id=research_run_id,
                population_fingerprint=population_fingerprint,
                contract=contract,
                model_identity=backend.identity,
                population_n=len(source),
                eligible_review_n=sum(1 for member in members if member.eligible),
                indexed_review_n=sum(1 for member in members if member.eligible),
                semantic_unit_n=len(units),
                unique_embedding_n=len(embeddings),
                cache_hit_n=sum(1 for unit in units if unit.embedding_key in cache),
                cache_miss_n=len(pending_order),
                members=members,
                units=units,
                embeddings=embeddings,
            )
            partial.index_fingerprint = _index_fingerprint(population_fingerprint, contract, members, units)
            raise SemanticIndexBuildError(str(exc), partial) from exc
        if encoded.shape != (len(pending_order), contract.dimensions):
            raise ValueError(f"embedding backend returned shape {encoded.shape}, expected {(len(pending_order), contract.dimensions)}")
        if not np.isfinite(encoded).all():
            raise ValueError("embedding backend returned non-finite values")
        norms = np.linalg.norm(encoded, axis=1)
        if np.any(norms == 0):
            raise ValueError("embedding backend returned a zero vector")
        for index, key in enumerate(pending_order):
            embeddings[key] = encoded[index].astype(np.float32, copy=True)

    cache_hits = sum(1 for unit in units if unit.embedding_key in cache)
    cache_miss = len(pending_order)
    result = SemanticIndexBuildResult(
        schema_version=SEMANTIC_INDEX_SCHEMA_VERSION,
        research_run_id=research_run_id,
        population_fingerprint=population_fingerprint,
        contract=contract,
        model_identity=backend.identity,
        population_n=len(source),
        eligible_review_n=sum(1 for member in members if member.eligible),
        indexed_review_n=sum(1 for member in members if member.eligible),
        semantic_unit_n=len(units),
        unique_embedding_n=len(embeddings),
        cache_hit_n=cache_hits,
        cache_miss_n=cache_miss,
        members=members,
        units=units,
        embeddings=embeddings,
    )
    result.index_fingerprint = _index_fingerprint(population_fingerprint, contract, members, units)
    return result


def build_semantic_index_for_run(
    research_run_id: str,
    *,
    contract: SemanticIndexContract | None = None,
    backend: EmbeddingBackend | None = None,
    reviews: Iterable[Mapping[str, Any]] | None = None,
) -> SemanticIndexBuildResult:
    """Build and persist an index for one immutable Research run.

    This helper is deliberately not wired into ``/analyze``. It always uses
    the run's independent immutable Research Population snapshot; mutable app
    reviews and presentation/sample payloads are never an exact-run fallback.
    """
    from . import semantic_index_storage as storage

    from . import storage as result_storage
    from .research_population_snapshot import get_analysis_run_population

    stored = result_storage.get_analysis_run_result(research_run_id)
    if not stored:
        raise ValueError(f"Research run not found: {research_run_id}")
    snapshot = get_analysis_run_population(research_run_id)
    if snapshot is None:
        raise ValueError("research_population_snapshot_unavailable")
    population_fingerprint = str(snapshot["population_fingerprint"])
    source = list(snapshot["reviews"])
    if reviews is not None:
        supplied = list(reviews)
        from .research_population_snapshot import compute_population_fingerprint
        if compute_population_fingerprint(supplied) != population_fingerprint or len(supplied) != int(snapshot["population_n"]):
            raise ValueError("research_population_snapshot_mismatch")
    if int(snapshot["population_n"]) != len(source):
        raise ValueError("research_population_snapshot_incomplete")
    active_backend = backend
    if active_backend is None:
        from .embedding_backend import LocalONNXEmbeddingBackend, default_model_cache_dir

        active_backend = LocalONNXEmbeddingBackend(model_dir=default_model_cache_dir())
    active_contract = contract or SemanticIndexContract.from_backend(active_backend)
    active_contract.validate()
    cache = storage.load_embedding_cache(contract=active_contract)
    index_id = storage._index_id(research_run_id, population_fingerprint, active_contract)
    try:
        result = build_semantic_index(
            source,
            research_run_id=research_run_id,
            population_fingerprint=str(population_fingerprint),
            contract=active_contract,
            backend=active_backend,
            embedding_cache=cache,
        )
    except SemanticIndexBuildError as exc:
        storage.persist_failed_index(app_id=int(snapshot["app_id"]), index_id=index_id, result=exc.partial_result, error=str(exc))
        raise
    storage.persist_semantic_index(app_id=int(snapshot["app_id"]), index_id=index_id, result=result)
    return result
