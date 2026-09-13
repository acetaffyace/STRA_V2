from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import text

from apps.api.senti_next import db
from apps.api.senti_next.embedding_backend import FakeEmbeddingBackend
from apps.api.senti_next.semantic_discovery import SemanticDiscoveryContract, build_semantic_discovery
from apps.api.senti_next.semantic_discovery_schema import migrate_semantic_discovery
from apps.api.senti_next.semantic_discovery_storage import (
    build_semantic_discovery_for_index,
    load_semantic_discovery,
    persist_semantic_discovery,
)
from apps.api.senti_next.semantic_index import SemanticIndexContract, build_semantic_index
from apps.api.senti_next.semantic_index_storage import persist_semantic_index


@pytest.fixture
def isolated_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db.init_db()
    yield
    db.close_engine()


class StaticBackend:
    identity = "static"

    def discover(self, vectors, *, min_cluster_size, min_samples, metric):  # type: ignore[no-untyped-def]
        labels = np.asarray([0 if i < 3 else -1 for i in range(len(vectors))], dtype=int)
        return labels, np.ones(len(vectors)), np.zeros(len(vectors))


def _stored_index() -> str:
    backend = FakeEmbeddingBackend(dimensions=8)
    result = build_semantic_index(
        [
            {"recommendationid": "a", "review": "crash"},
            {"recommendationid": "b", "review": "update crash"},
            {"recommendationid": "c", "review": "更新后崩溃"},
            {"recommendationid": "d", "review": "controller"},
            {"recommendationid": "e", "review": ""},
        ],
        research_run_id="research-run",
        population_fingerprint="population-fingerprint",
        contract=SemanticIndexContract.from_backend(backend),
        backend=backend,
    )
    persist_semantic_index(app_id=1, index_id="semantic-index", result=result)
    return "semantic-index"


def test_migration_15_is_idempotent(isolated_db) -> None:
    with db.get_connection() as conn:
        raw = conn.connection.driver_connection
        migrate_semantic_discovery(raw)
        migrate_semantic_discovery(raw)
        for table in ("semantic_discovery_runs", "semantic_discovery_regions", "semantic_discovery_members", "taxonomy_audit_regions"):
            assert conn.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"), {"name": table}).scalar() == 1


def test_discovery_persists_exact_index_identity_and_is_idempotent(isolated_db) -> None:
    index_id = _stored_index()
    report = build_semantic_discovery_for_index(
        index_id,
        contract=SemanticDiscoveryContract(min_cluster_size=3),
        expected_population_fingerprint="population-fingerprint",
        backend=StaticBackend(),
    )
    assert report["population_n"] == 5
    assert report["indexed_review_n"] == 4
    run_id = persist_semantic_discovery(report)
    assert load_semantic_discovery(run_id) == report
    assert persist_semantic_discovery(report) == run_id
    with db.get_connection() as conn:
        member_count = conn.execute(text("SELECT COUNT(*) FROM semantic_discovery_members WHERE discovery_run_id = :run_id"), {"run_id": run_id}).scalar()
        assert member_count >= report["indexed_review_n"]
    with pytest.raises(ValueError, match="fingerprint"):
        build_semantic_discovery_for_index(index_id, expected_population_fingerprint="wrong", backend=StaticBackend())
    with pytest.raises(ValueError, match="semantic index fingerprint"):
        build_semantic_discovery_for_index(index_id, expected_semantic_index_fingerprint="wrong", backend=StaticBackend())


def test_discovery_can_be_built_without_taxonomy_or_stage2e(isolated_db) -> None:
    index_id = _stored_index()
    report = build_semantic_discovery_for_index(index_id, backend=StaticBackend())
    assert report["taxonomy_audit"]["well_covered_region_n"] == 0
    assert all(region["stage2e_overlap"] == {} for region in report["regions"])
