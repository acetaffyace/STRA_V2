from __future__ import annotations

import json
import os
import sqlite3

import pytest
from sqlalchemy import text

from apps.api.senti_next import db, storage
from apps.api.senti_next.classifier_taxonomy import baseline_classifier_taxonomy
from apps.api.senti_next.classification_materialization import (
    create_classification_materialization,
    population_fingerprint as materialization_population_fingerprint,
)
from apps.api.senti_next.embedding_backend import FakeEmbeddingBackend
from apps.api.senti_next.research_population_snapshot import (
    compute_population_fingerprint,
    freeze_analysis_run_population,
    get_analysis_run_population,
    get_analysis_run_population_metadata,
)
from apps.api.senti_next.semantic_index import SemanticIndexContract, build_semantic_index_for_run
from apps.api.senti_next.semantic_measurement_bundle import (
    activate_measurement_bundle,
    bootstrap_baseline_measurement_bundle,
)
from apps.api.senti_next.routes import analysis as analysis_routes


os.environ["DATABASE_URL"] = "sqlite://"


@pytest.fixture(autouse=True)
def isolated_db():
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def _reviews(*texts: str) -> list[dict]:
    return [
        {
            "recommendationid": f"r-{index}",
            "review": value,
            "language": "english",
            "voted_up": True,
            "timestamp_created": index,
            "playtime_forever": index * 10,
        }
        for index, value in enumerate(texts, start=1)
    ]


def _run(run_id: str, app_id: int = 553850) -> None:
    storage.create_general_analysis_run(run_id, app_id, config={}, requested_languages=["english"], requested_review_count=2)
    storage.transition_general_analysis_run(run_id, "running", phase="research_core")


def test_migration_24_fresh_repeat_and_foreign_keys():
    with db.get_connection() as conn:
        raw = conn.connection.driver_connection
        assert conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar() == 24
        assert conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_run_populations'")).scalar() == "analysis_run_populations"
        assert conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_run_population_items'")).scalar() == "analysis_run_population_items"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        raw.commit()
    db.init_db()
    with db.get_connection() as conn:
        with pytest.raises(Exception):
            conn.execute(text("INSERT INTO analysis_run_population_items(run_id, ordinal, review_id, review_hash, payload_json) VALUES ('missing', 0, 'r', 'h', '{}')"))


def test_migration_23_to_24_is_additive_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'upgrade.db'}")
    db.close_engine()
    db._engine = None
    db.init_db()
    _run("pre-upgrade-run")
    with db.get_connection() as conn:
        conn.execute(text("DROP TABLE analysis_run_population_items"))
        conn.execute(text("DROP TABLE analysis_run_populations"))
        conn.execute(text("DELETE FROM schema_migrations WHERE version=24"))
        conn.commit()
        assert conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar() == 23
    db.close_engine()
    db._engine = None
    db.init_db()
    db.init_db()
    with db.get_connection() as conn:
        assert conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar() == 24
        assert conn.execute(text("SELECT COUNT(*) FROM analysis_runs WHERE run_id='pre-upgrade-run'")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM analysis_run_populations")).scalar() == 0


def test_snapshot_idempotence_conflict_and_mutable_store_isolation():
    _run("snapshot-run")
    rows = _reviews("first", "second")
    first = freeze_analysis_run_population(run_id="snapshot-run", app_id=553850, reviews=rows)
    second = freeze_analysis_run_population(run_id="snapshot-run", app_id=553850, reviews=rows)
    assert first == second
    with pytest.raises(ValueError, match="research_population_snapshot_conflict"):
        freeze_analysis_run_population(run_id="snapshot-run", app_id=553850, reviews=_reviews("changed", "second"))

    storage.upsert_reviews(553850, [{**rows[0], "review": "mutable replacement"}])
    storage.delete_all_game_data(553850)
    loaded = get_analysis_run_population("snapshot-run")
    assert loaded["reviews"] == rows
    assert loaded["population_fingerprint"] == first["population_fingerprint"]


def test_snapshot_fingerprint_is_shared_with_materialization_contract():
    rows = _reviews("same text", "another text")
    assert compute_population_fingerprint(rows) == materialization_population_fingerprint(rows)
    assert compute_population_fingerprint(rows) != compute_population_fingerprint(_reviews("changed", "another text"))
    assert compute_population_fingerprint(rows) != compute_population_fingerprint([{"review_id": "different", "review": "same text"}, rows[1]])


def test_quantitative_only_run_reviews_are_exact_and_paginated(monkeypatch):
    reviews = _reviews(*[f"review {index}" for index in range(235)])
    monkeypatch.setattr(analysis_routes.storage, "get_analysis_run", lambda run_id: {"target_app_id": 553850})
    monkeypatch.setattr(analysis_routes, "get_analysis_run_population", lambda run_id: {
        "run_id": run_id,
        "population_n": len(reviews),
        "reviews": reviews,
    })
    monkeypatch.setattr(analysis_routes, "get_materialization_for_run", lambda run_id: None)

    first = analysis_routes.get_run_reviews(553850, "quant-only", limit=100, offset=0)
    second = analysis_routes.get_run_reviews(553850, "quant-only", limit=100, offset=100)
    third = analysis_routes.get_run_reviews(553850, "quant-only", limit=100, offset=200)

    assert first["semantic_available"] is False
    assert first["matched_review_count"] == 235
    assert len(first["items"]) == 100
    assert len(second["items"]) == 100
    assert len(third["items"]) == 35
    assert first["items"][0]["review_id"] == "r-1"
    assert third["items"][-1]["review_id"] == "r-235"
    assert all(item["labels"] == {"topics": [], "issues": [], "requests": []} for item in third["items"])


def test_snapshot_restart_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'population.db'}")
    db.close_engine()
    db._engine = None
    db.init_db()
    _run("restart-population")
    rows = _reviews("restart me")
    frozen = freeze_analysis_run_population(run_id="restart-population", app_id=553850, reviews=rows)
    db.close_engine()
    db._engine = None
    assert get_analysis_run_population_metadata("restart-population")["population_fingerprint"] == frozen["population_fingerprint"]
    assert get_analysis_run_population("restart-population")["reviews"] == rows


def test_quantitative_only_result_can_build_stage3a_from_snapshot():
    _run("quantitative-stage3a")
    rows = _reviews("semantic index source")
    snapshot = freeze_analysis_run_population(run_id="quantitative-stage3a", app_id=553850, reviews=rows)
    report = {"schema_version": "research-report-v1", "recommendation": {"population": {"valid_n": 1}}}
    metadata = {"population_provenance": {"population_fingerprint": snapshot["population_fingerprint"], "population_count": 1, "population_snapshot_status": "frozen"}}
    storage.finalize_general_analysis_run(
        "quantitative-stage3a", 553850, metadata, None, [], research_report=report,
        semantic_status={"status": "unavailable", "reason": "no_provider"},
    )
    result = build_semantic_index_for_run(
        "quantitative-stage3a",
        backend=FakeEmbeddingBackend(dimensions=8),
    )
    assert result.population_fingerprint == snapshot["population_fingerprint"]
    assert result.population_n == 1
    assert result.indexed_review_n == 1


def test_materialization_requires_matching_snapshot_for_real_analysis_run():
    _run("materialization-snapshot")
    rows = _reviews("matching")
    freeze_analysis_run_population(run_id="materialization-snapshot", app_id=553850, reviews=rows)
    bundle = activate_measurement_bundle(bootstrap_baseline_measurement_bundle()["bundle_id"], operator="test", reason="r1")
    contract = baseline_classifier_taxonomy()
    identity = {
        "review_hash": "", "classification_input_hash": "", "provider": bundle["classifier_provider"],
        "model_id": bundle["classifier_model_id"], "prompt_version": bundle["classifier_prompt_version"],
        "taxonomy_version": contract.taxonomy_version, "taxonomy_snapshot_id": contract.snapshot_id,
        "taxonomy_fingerprint": contract.taxonomy_fingerprint,
    }
    identity["review_hash"] = __import__("hashlib").sha256(b"matching").hexdigest()
    labels = {"r-1": {**identity, "payload": {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []}, "label_origin": "llm", "validated": True}}
    materialized = create_classification_materialization(
        run_id="materialization-snapshot", app_id=553850, all_reviews=rows, bundle=bundle,
        taxonomy_contract=contract, labels=labels,
    )
    assert materialized["population_fingerprint"] == get_analysis_run_population_metadata("materialization-snapshot")["population_fingerprint"]


def test_migration_24_retains_existing_result_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'retained.db'}")
    db.close_engine()
    db._engine = None
    db.init_db()
    _run("retained-row")
    report = {"schema_version": "research-report-v1", "recommendation": {"population": {"valid_n": 0}}}
    storage.finalize_general_analysis_run("retained-row", 553850, {}, None, [], research_report=report, semantic_status={"status": "unavailable"})
    db.close_engine()
    db._engine = None
    db.init_db()
    assert storage.get_analysis_run_result("retained-row")["research_report"] == report
