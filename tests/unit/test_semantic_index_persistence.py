from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import text

from apps.api.senti_next import db
from apps.api.senti_next.embedding_backend import FakeEmbeddingBackend
from apps.api.senti_next.semantic_index import SemanticIndexContract, build_semantic_index
from apps.api.senti_next.semantic_index_schema import migrate_semantic_index
from apps.api.senti_next.semantic_index_storage import (
    find_complete_index,
    load_embedding_cache,
    load_semantic_index,
    persist_failed_index,
    persist_semantic_index,
)


@pytest.fixture
def isolated_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db.init_db()
    yield
    db.close_engine()


def _reviews() -> list[dict]:
    return [
        {"recommendationid": "1", "review": "crash after update"},
        {"recommendationid": "2", "review": "更新后游戏崩溃"},
        {"recommendationid": "3", "review": ""},
    ]


def test_migration_14_is_idempotent_and_creates_all_tables(isolated_db) -> None:
    with db.get_connection() as conn:
        raw = conn.connection.driver_connection
        migrate_semantic_index(raw)
        migrate_semantic_index(raw)
        for table in ("semantic_index_runs", "semantic_index_members", "semantic_index_units", "semantic_embedding_cache"):
            assert conn.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"), {"name": table}).scalar() == 1


def test_persist_load_and_cache_reuse(isolated_db) -> None:
    backend = FakeEmbeddingBackend(dimensions=16)
    contract = SemanticIndexContract.from_backend(backend)
    result = build_semantic_index(
        _reviews(), research_run_id="run-a", population_fingerprint="population-a", contract=contract, backend=backend
    )
    index_id = "index-a"
    persist_semantic_index(app_id=123, index_id=index_id, result=result)
    loaded = load_semantic_index(index_id)
    assert loaded is not None
    assert loaded["run"]["status"] == "completed"
    assert loaded["run"]["population_n"] == 3
    assert len(loaded["members"]) == 3
    cached = load_embedding_cache(contract=contract)
    assert len(cached) == 2
    assert find_complete_index(research_run_id="run-a", population_fingerprint="population-a", contract=contract) == index_id
    persist_semantic_index(app_id=123, index_id=index_id, result=result)
    assert load_semantic_index(index_id)["run"]["status"] == "completed"


def test_failed_index_is_explicit_and_has_no_completed_children(isolated_db) -> None:
    backend = FakeEmbeddingBackend(dimensions=16)
    contract = SemanticIndexContract.from_backend(backend)
    result = build_semantic_index(
        _reviews(), research_run_id="run-f", population_fingerprint="population-f", contract=contract, backend=backend
    )
    persist_failed_index(app_id=123, index_id="index-f", result=result, error="model unavailable")
    loaded = load_semantic_index("index-f")
    assert loaded is not None
    assert loaded["run"]["status"] == "failed"
    assert loaded["run"]["error"] == "model unavailable"
    assert loaded["members"] == []


def test_migration_function_is_safe_on_raw_sqlite_connection() -> None:
    conn = sqlite3.connect(":memory:")
    migrate_semantic_index(conn)
    migrate_semantic_index(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='semantic_index_runs'").fetchone()
    conn.close()
