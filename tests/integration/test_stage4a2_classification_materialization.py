from __future__ import annotations

import os
from contextlib import nullcontext

os.environ["DATABASE_URL"] = "sqlite://"

import pytest

from apps.api.senti_next import db, llm, storage
from apps.api.senti_next.classifier_taxonomy import baseline_classifier_taxonomy
from apps.api.senti_next.classification_materialization import (
    create_classification_materialization,
    get_materialization_for_run,
    load_materialized_review_labels,
)
from apps.api.senti_next.semantic_measurement_bundle import (
    activate_measurement_bundle,
    bootstrap_baseline_measurement_bundle,
)
from apps.api.senti_next.semantic_measurement_runtime import resolve_measurement_context


@pytest.fixture(autouse=True)
def isolated_db():
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def _bundle():
    bundle = bootstrap_baseline_measurement_bundle()
    return activate_measurement_bundle(bundle["bundle_id"], operator="test", reason="test")


def _reviews(*ids):
    return [{"recommendationid": review_id, "review": f"Review {review_id}", "voted_up": True} for review_id in ids]


def _labels(bundle, reviews):
    contract = baseline_classifier_taxonomy()
    result = {}
    for review in reviews:
        identity = llm.classification_identity(
            review,
            None,
            provider=bundle["classifier_provider"],
            model_id=bundle["classifier_model_id"],
            prompt_version=bundle["classifier_prompt_version"],
            taxonomy_contract=contract,
        )
        result[str(review["recommendationid"])] = {
            **identity,
            "payload": {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []},
            "label_origin": "llm",
            "validated": True,
            "provider": bundle["classifier_provider"],
            "model_id": bundle["classifier_model_id"],
            "generated_at": "2026-09-13T00:00:00+00:00",
        }
    return result


def test_materialization_is_idempotent_and_population_isolated():
    bundle = _bundle()
    contract = baseline_classifier_taxonomy()
    reviews = _reviews("a", "b")
    labels = _labels(bundle, reviews)
    first = create_classification_materialization(
        run_id="run-a", app_id=1, all_reviews=reviews, bundle=bundle,
        taxonomy_contract=contract, labels=labels,
    )
    second = create_classification_materialization(
        run_id="run-a", app_id=1, all_reviews=reviews, bundle=bundle,
        taxonomy_contract=contract, labels=labels,
    )
    assert first["materialization_id"] == second["materialization_id"]
    assert first["materialization_fingerprint"] == second["materialization_fingerprint"]
    assert {item["review_id"] for item in first["items"]} == {"a", "b"}

    other = create_classification_materialization(
        run_id="run-b", app_id=1, all_reviews=reviews, bundle=bundle,
        taxonomy_contract=contract, labels=labels,
    )
    assert other["materialization_id"] != first["materialization_id"]

    labels["a"]["payload"] = {"subcategories": ["technical/bugs"], "issue_subcategories": [], "request_subcategories": []}
    with pytest.raises(ValueError, match="classification_materialization_conflict"):
        create_classification_materialization(
            run_id="run-a", app_id=1, all_reviews=reviews, bundle=bundle,
            taxonomy_contract=contract, labels=labels,
        )


def test_materialized_payload_survives_mutable_cache_overwrite():
    bundle = _bundle()
    contract = baseline_classifier_taxonomy()
    reviews = _reviews("a")
    labels = _labels(bundle, reviews)
    frozen = create_classification_materialization(
        run_id="run-a", app_id=1, all_reviews=reviews, bundle=bundle,
        taxonomy_contract=contract, labels=labels,
    )
    storage.upsert_review_label(
        1, "a", "changed", {"subcategories": ["technical/bugs"]}, "changed", "changed",
        label_origin="llm", validated=True, taxonomy_version=contract.taxonomy_version,
        taxonomy_snapshot_id=contract.snapshot_id, taxonomy_fingerprint=contract.taxonomy_fingerprint,
        provider=bundle["classifier_provider"], model_id=bundle["classifier_model_id"],
    )
    loaded = load_materialized_review_labels(frozen["materialization_id"])
    assert loaded["a"]["payload"]["subcategories"] == ["other/general"]


def test_fresh_resolver_bootstraps_and_retired_state_is_not_resurrected():
    context = resolve_measurement_context()
    assert context.ready is True
    assert context.measurement_status == "PROVISIONAL"
    assert context.bundle["is_active"] is True

    from apps.api.senti_next.semantic_measurement_bundle import retire_measurement_bundle
    retire_measurement_bundle(context.bundle_id, operator="test", reason="test-retire")
    unavailable = resolve_measurement_context()
    assert unavailable.ready is False
    assert unavailable.reason == "no_active_measurement_bundle"


def test_strict_mode_rejects_legacy_null_taxonomy_identity():
    contract = baseline_classifier_taxonomy()
    identity = llm.classification_identity(
        {"review_id": "r", "review": "A review"}, None,
        provider="openai", model_id="openai:test", taxonomy_contract=contract,
    )
    legacy = {**identity, "taxonomy_snapshot_id": None, "taxonomy_fingerprint": None, "label_origin": "llm", "validated": True}
    assert llm.label_cache_eligible(legacy, identity)
    assert not llm.label_cache_eligible(legacy, identity, strict_taxonomy_identity=True)


def test_file_backed_materialization_survives_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'restart.db'}")
    db.close_engine()
    db._engine = None
    db.init_db()
    bundle = _bundle()
    contract = baseline_classifier_taxonomy()
    reviews = _reviews("restart-review")
    frozen = create_classification_materialization(
        run_id="restart-run", app_id=9, all_reviews=reviews, bundle=bundle,
        taxonomy_contract=contract, labels=_labels(bundle, reviews),
    )
    db.close_engine()
    db._engine = None
    loaded = get_materialization_for_run("restart-run")
    assert loaded["materialization_id"] == frozen["materialization_id"]
    assert loaded["materialization_fingerprint"] == frozen["materialization_fingerprint"]
    assert loaded["items"] == frozen["items"]


def test_analysis_job_binds_bundle_and_aggregates_from_frozen_materialization(monkeypatch):
    from apps.api.senti_next.routes import analysis as analysis_route
    from apps.api.senti_next.routes._shared import AnalyzeMetadata

    bundle = _bundle()
    run_id = "analysis-run-4a2"
    storage.create_general_analysis_run(run_id, 77, config={}, requested_languages=["english"], requested_review_count=1)
    storage.transition_general_analysis_run(run_id, "running", phase="research_core")
    reviews = [{
        "recommendationid": "review-1", "review": "The game is good", "voted_up": True,
        "language": "english", "timestamp_created": 1, "timestamp_updated": 1,
    }]
    metadata = AnalyzeMetadata(
        app_id=77, requested=1, retrieved=1, requested_limit=1,
        retrieved_count=1, deduplicated_count=1, analysis_population_count=1,
        language="english", languages=["english"], run_id=run_id,
    )

    def fake_ensure(app_id, rows, *, game_context, taxonomy_contract, strict_taxonomy_identity, **kwargs):
        for review in rows:
            identity = llm.classification_identity(
                review, game_context, provider=bundle["classifier_provider"],
                model_id=bundle["classifier_model_id"],
                prompt_version=bundle["classifier_prompt_version"], taxonomy_contract=taxonomy_contract,
            )
            storage.upsert_review_label(
                app_id, str(review["recommendationid"]), identity["review_hash"],
                {"subcategories": ["other/general"], "issue_subcategories": [], "request_subcategories": []},
                bundle["classifier_model_id"], bundle["classifier_prompt_version"],
                label_origin="llm", validated=True, taxonomy_version=taxonomy_contract.taxonomy_version,
                taxonomy_snapshot_id=taxonomy_contract.snapshot_id, taxonomy_fingerprint=taxonomy_contract.taxonomy_fingerprint,
                provider=bundle["classifier_provider"], model_id=bundle["classifier_model_id"],
                classification_input_hash=identity["classification_input_hash"],
            )

    monkeypatch.setattr(analysis_route.llm, "ensure_review_labels", fake_ensure)
    monkeypatch.setattr(analysis_route.llm, "llm_usage_context", lambda **kwargs: nullcontext())
    monkeypatch.setattr(analysis_route.llm, "generate_health_overview", lambda **kwargs: {})
    monkeypatch.setattr(analysis_route, "prepare_insights", lambda *args, **kwargs: {"ok": True})

    analysis_route._run_analysis_job(
        run_id, 77, reviews, metadata, {}, "en",
        {"status": "available", "provider": bundle["classifier_provider"], "model_id": bundle["classifier_model_id"]},
    )
    result = storage.get_analysis_run_result(run_id)
    run = storage.get_analysis_run(run_id)
    materialization = get_materialization_for_run(run_id)
    assert result["semantic_status"]["measurement_status"] == "PROVISIONAL"
    assert result["semantic_status"]["classification_materialization_id"] == materialization["materialization_id"]
    assert run["measurement_status"] == "PROVISIONAL"
    assert run["measurement_bundle_id"] == bundle["bundle_id"]
    assert run["classification_materialization_id"] == materialization["materialization_id"]
    assert materialization["validated_llm_n"] == 1
