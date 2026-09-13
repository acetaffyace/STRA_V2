"""Persistence helpers for the Stage 3A semantic index.

This module stores only derived semantic units and vectors.  Raw review rows,
Research Report values, and the Research Population denominator remain owned by
the existing result/review storage.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Optional

import numpy as np
from sqlalchemy import text

from . import db
from .semantic_index import (
    SemanticIndexBuildResult,
    SemanticIndexContract,
    SemanticIndexMember,
    SemanticUnit,
)


def _vector_blob(vector: np.ndarray) -> bytes:
    values = np.asarray(vector, dtype=np.float32)
    if values.ndim != 1:
        raise ValueError("semantic cache vectors must be one-dimensional")
    return values.tobytes(order="C")


def _vector_from_blob(blob: bytes, dimensions: int) -> np.ndarray:
    values = np.frombuffer(blob, dtype=np.float32).copy()
    if values.shape != (dimensions,):
        raise ValueError("semantic cache vector has unexpected dimensions")
    return values


def load_embedding_cache(
    embedding_keys: Optional[Iterable[str]] = None,
    *,
    contract: SemanticIndexContract,
) -> dict[str, np.ndarray]:
    contract.validate()
    keys = sorted(set(str(key) for key in embedding_keys)) if embedding_keys is not None else []
    key_clause = ""
    params: dict[str, Any] = {}
    if keys:
        placeholders = ",".join(f":key_{index}" for index in range(len(keys)))
        key_clause = f" AND embedding_key IN ({placeholders})"
        params.update({f"key_{index}": key for index, key in enumerate(keys)})
    query = text(
        f"SELECT embedding_key, dimensions, vector_blob FROM semantic_embedding_cache "
        f"WHERE model_id = :model_id "
        "AND model_revision = :model_revision AND artifact_sha256 = :artifact_sha256 "
        "AND preprocessing_version = :preprocessing_version AND chunking_version = :chunking_version "
        "AND prefix_policy = :prefix_policy AND pooling = :pooling "
        "AND normalization = :normalization AND dimensions = :dimensions" + key_clause
    )
    params.update(
        {
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
    )
    with db.get_connection() as conn:
        rows = conn.execute(query, params).mappings().all()
    return {
        str(row["embedding_key"]): _vector_from_blob(row["vector_blob"], int(row["dimensions"]))
        for row in rows
    }


def _index_id(research_run_id: str, population_fingerprint: str, contract: SemanticIndexContract) -> str:
    import hashlib

    value = f"{research_run_id}:{population_fingerprint}:{contract.fingerprint}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def find_complete_index(
    *,
    research_run_id: str,
    population_fingerprint: str,
    contract: SemanticIndexContract,
) -> Optional[str]:
    contract.validate()
    with db.get_connection() as conn:
        row = conn.execute(
            text(
                "SELECT index_id FROM semantic_index_runs "
                "WHERE research_run_id = :run_id AND population_fingerprint = :population "
                "AND contract_json = :contract AND status = 'completed' "
                "ORDER BY completed_at DESC LIMIT 1"
            ),
            {
                "run_id": research_run_id,
                "population": population_fingerprint,
                "contract": json.dumps(contract.to_dict(), sort_keys=True, separators=(",", ":")),
            },
        ).scalar()
    return str(row) if row else None


def persist_semantic_index(
    *,
    app_id: int,
    index_id: str,
    result: SemanticIndexBuildResult,
) -> str:
    """Persist a completed result atomically, reusing the same identity on rerun."""
    result.contract.validate()
    contract_json = json.dumps(result.contract.to_dict(), sort_keys=True, separators=(",", ":"))
    identity = result.model_identity
    with db.get_connection() as conn:
        existing = conn.execute(
            text("SELECT status, index_fingerprint FROM semantic_index_runs WHERE index_id = :index_id"),
            {"index_id": index_id},
        ).mappings().first()
        if existing and existing["status"] == "completed" and existing["index_fingerprint"] == result.index_fingerprint:
            return index_id
        if existing:
            conn.execute(text("DELETE FROM semantic_index_runs WHERE index_id = :index_id"), {"index_id": index_id})
        conn.execute(
            text(
                "INSERT INTO semantic_index_runs "
                "(index_id, research_run_id, app_id, population_fingerprint, contract_json, model_id, model_revision, "
                "artifact_sha256, population_n, eligible_review_n, indexed_review_n, semantic_unit_n, "
                "unique_embedding_n, cache_hit_n, cache_miss_n, status, index_fingerprint, completed_at) "
                "VALUES (:index_id, :research_run_id, :app_id, :population_fingerprint, :contract_json, :model_id, "
                ":model_revision, :artifact_sha256, :population_n, :eligible_review_n, :indexed_review_n, "
                ":semantic_unit_n, :unique_embedding_n, :cache_hit_n, :cache_miss_n, 'completed', :index_fingerprint, datetime('now'))"
            ),
            {
                "index_id": index_id,
                "research_run_id": result.research_run_id,
                "app_id": int(app_id),
                "population_fingerprint": result.population_fingerprint,
                "contract_json": contract_json,
                "model_id": identity.model_id,
                "model_revision": identity.model_revision,
                "artifact_sha256": identity.artifact_sha256,
                "population_n": result.population_n,
                "eligible_review_n": result.eligible_review_n,
                "indexed_review_n": result.indexed_review_n,
                "semantic_unit_n": result.semantic_unit_n,
                "unique_embedding_n": result.unique_embedding_n,
                "cache_hit_n": result.cache_hit_n,
                "cache_miss_n": result.cache_miss_n,
                "index_fingerprint": result.index_fingerprint,
            },
        )
        for member in result.members:
            conn.execute(
                text(
                    "INSERT INTO semantic_index_members "
                    "(index_id, review_id, review_text_hash, eligible, exclusion_reason, semantic_unit_count) "
                    "VALUES (:index_id, :review_id, :review_text_hash, :eligible, :exclusion_reason, :semantic_unit_count)"
                ),
                {
                    "index_id": index_id,
                    "review_id": member.review_id,
                    "review_text_hash": member.review_text_hash,
                    "eligible": int(member.eligible),
                    "exclusion_reason": member.exclusion_reason,
                    "semantic_unit_count": member.semantic_unit_count,
                },
            )
        for unit in result.units:
            conn.execute(
                text(
                    "INSERT INTO semantic_index_units "
                    "(index_id, review_id, unit_index, semantic_text_hash, semantic_text, token_start, token_end, token_count, embedding_key) "
                    "VALUES (:index_id, :review_id, :unit_index, :semantic_text_hash, :semantic_text, :token_start, :token_end, :token_count, :embedding_key)"
                ),
                {
                    "index_id": index_id,
                    "review_id": unit.review_id,
                    "unit_index": unit.unit_index,
                    "semantic_text_hash": unit.semantic_text_hash,
                    "semantic_text": unit.semantic_text,
                    "token_start": unit.token_start,
                    "token_end": unit.token_end,
                    "token_count": unit.token_count,
                    "embedding_key": unit.embedding_key,
                },
            )
            vector = result.embeddings[unit.embedding_key]
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO semantic_embedding_cache "
                    "(embedding_key, semantic_text_hash, model_id, model_revision, artifact_sha256, preprocessing_version, "
                    "chunking_version, prefix_policy, pooling, normalization, dimensions, dtype, vector_blob) "
                    "VALUES (:embedding_key, :semantic_text_hash, :model_id, :model_revision, :artifact_sha256, "
                    ":preprocessing_version, :chunking_version, :prefix_policy, :pooling, :normalization, :dimensions, :dtype, :vector_blob)"
                ),
                {
                    "embedding_key": unit.embedding_key,
                    "semantic_text_hash": unit.semantic_text_hash,
                    "model_id": result.contract.model_id,
                    "model_revision": result.contract.model_revision,
                    "artifact_sha256": result.contract.artifact_sha256,
                    "preprocessing_version": result.contract.preprocessing_version,
                    "chunking_version": result.contract.chunking_version,
                    "prefix_policy": result.contract.prefix_policy,
                    "pooling": result.contract.pooling,
                    "normalization": result.contract.normalization,
                    "dimensions": result.contract.dimensions,
                    "dtype": "float32",
                    "vector_blob": _vector_blob(vector),
                },
            )
    return index_id


def load_semantic_index(index_id: str) -> Optional[dict[str, Any]]:
    with db.get_connection() as conn:
        run = conn.execute(text("SELECT * FROM semantic_index_runs WHERE index_id = :index_id"), {"index_id": index_id}).mappings().first()
        if not run:
            return None
        members = conn.execute(
            text("SELECT * FROM semantic_index_members WHERE index_id = :index_id ORDER BY review_id"),
            {"index_id": index_id},
        ).mappings().all()
        units = conn.execute(
            text("SELECT * FROM semantic_index_units WHERE index_id = :index_id ORDER BY review_id, unit_index"),
            {"index_id": index_id},
        ).mappings().all()
    return {"run": dict(run), "members": [dict(row) for row in members], "units": [dict(row) for row in units]}


def persist_failed_index(*, app_id: int, index_id: str, result: SemanticIndexBuildResult, error: str) -> str:
    """Persist an explicit failed index attempt without fabricating vectors."""
    identity = result.model_identity
    contract_json = json.dumps(result.contract.to_dict(), sort_keys=True, separators=(",", ":"))
    with db.get_connection() as conn:
        conn.execute(text("DELETE FROM semantic_index_runs WHERE index_id = :index_id"), {"index_id": index_id})
        conn.execute(
            text(
                "INSERT INTO semantic_index_runs "
                "(index_id, research_run_id, app_id, population_fingerprint, contract_json, model_id, model_revision, artifact_sha256, "
                "population_n, eligible_review_n, indexed_review_n, semantic_unit_n, unique_embedding_n, cache_hit_n, cache_miss_n, status, error) "
                "VALUES (:index_id, :research_run_id, :app_id, :population_fingerprint, :contract_json, :model_id, :model_revision, :artifact_sha256, "
                ":population_n, :eligible_review_n, :indexed_review_n, :semantic_unit_n, :unique_embedding_n, :cache_hit_n, :cache_miss_n, 'failed', :error)"
            ),
            {
                "index_id": index_id,
                "research_run_id": result.research_run_id,
                "app_id": int(app_id),
                "population_fingerprint": result.population_fingerprint,
                "contract_json": contract_json,
                "model_id": identity.model_id,
                "model_revision": identity.model_revision,
                "artifact_sha256": identity.artifact_sha256,
                "population_n": result.population_n,
                "eligible_review_n": result.eligible_review_n,
                "indexed_review_n": result.indexed_review_n,
                "semantic_unit_n": result.semantic_unit_n,
                "unique_embedding_n": result.unique_embedding_n,
                "cache_hit_n": result.cache_hit_n,
                "cache_miss_n": result.cache_miss_n,
                "error": str(error)[:2000],
            },
        )
    return index_id
