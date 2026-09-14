from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from apps.api.senti_next import db
from apps.api.senti_next.providers import config as provider_config
from apps.api.senti_next import semantic_measurement_bundle as bundle_module
from apps.api.senti_next import semantic_measurement_runtime as runtime
from apps.api.senti_next.classifier_taxonomy import baseline_classifier_taxonomy
from apps.api.senti_next.semantic_measurement_bundle import bootstrap_baseline_measurement_bundle


os.environ["DATABASE_URL"] = "sqlite://"


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    # Keep this identity-rotation contract independent of a developer's saved
    # provider selection in data/llm_config.json.
    monkeypatch.setattr(provider_config, "_CONFIG_FILE", tmp_path / "llm_config.json")
    monkeypatch.setattr(provider_config, "_API_KEYS_FILE", tmp_path / "api_keys.json")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def _runtime_identity(contract):
    return {
        "classifier_provider": "openai",
        "classifier_model_id": "gpt-5-mini",
        "classifier_prompt_version": "steam_review_insights_v16_basic_labels",
        "classifier_schema_version": "review-classification-schema-v1",
        "taxonomy_snapshot_id": contract.snapshot_id,
        "taxonomy_version": contract.taxonomy_version,
        "taxonomy_fingerprint": contract.taxonomy_fingerprint,
    }


def test_provisional_baseline_rotates_once_when_runtime_identity_changes(monkeypatch):
    first = runtime.resolve_measurement_context()
    assert first.ready is True
    assert first.bundle["classifier_provider"] == "unconfigured"
    contract = baseline_classifier_taxonomy()
    identity = _runtime_identity(contract)
    monkeypatch.setattr(runtime, "_runtime_identity", lambda _: identity)
    monkeypatch.setattr(bundle_module, "classifier_identity", lambda _: identity)

    rotated = runtime.resolve_measurement_context()
    assert rotated.ready is True
    assert rotated.bundle_id != first.bundle_id
    assert rotated.bundle["classifier_provider"] == "openai"
    assert rotated.bundle["measurement_status"] == "PROVISIONAL"
    with db.get_connection() as conn:
        old = conn.execute(
            text("SELECT is_active FROM semantic_measurement_bundles WHERE bundle_id=:id"), {"id": first.bundle_id}
        ).fetchone()
        events = conn.execute(
            text("SELECT COUNT(*) FROM semantic_measurement_activation_events WHERE bundle_id=:id AND event_type='activated'"),
            {"id": rotated.bundle_id},
        ).fetchone()[0]
    assert old[0] == 0
    assert events == 1

    again = runtime.resolve_measurement_context()
    assert again.bundle_id == rotated.bundle_id
    with db.get_connection() as conn:
        assert conn.execute(
            text("SELECT COUNT(*) FROM semantic_measurement_activation_events WHERE bundle_id=:id AND event_type='activated'"),
            {"id": rotated.bundle_id},
        ).fetchone()[0] == 1


def test_no_active_state_is_not_resurrected(monkeypatch):
    current = runtime.resolve_measurement_context()
    from apps.api.senti_next.semantic_measurement_bundle import retire_measurement_bundle
    retire_measurement_bundle(current.bundle_id, operator="test", reason="r1")
    unavailable = runtime.resolve_measurement_context()
    assert unavailable.ready is False
    assert unavailable.reason == "no_active_measurement_bundle"


def test_validated_identity_mismatch_never_rotates(monkeypatch):
    contract = baseline_classifier_taxonomy()
    bundle = {
        "bundle_id": "validated",
        "measurement_status": "VALIDATED",
        "validation_run_id": "validation-1",
        "taxonomy_snapshot_id": contract.snapshot_id,
        "taxonomy_version": contract.taxonomy_version,
        "taxonomy_fingerprint": contract.taxonomy_fingerprint,
        "limitations": [],
        "classifier_provider": "old-provider",
        "classifier_model_id": "old-model",
        "classifier_prompt_version": "old-prompt",
        "classifier_schema_version": "review-classification-schema-v1",
    }
    validation = {
        "gate_status": "PASS",
        "execution_mode": "production_classifier",
        "actual_model_id": "old-model",
        "execution_identity_fingerprint": "fp",
        "taxonomy_snapshot_id": contract.snapshot_id,
        "taxonomy_version": contract.taxonomy_version,
        "taxonomy_fingerprint": contract.taxonomy_fingerprint,
        "actual_provider": "old-provider",
        "classifier_prompt_version": "old-prompt",
        "classifier_schema_version": "review-classification-schema-v1",
    }
    monkeypatch.setattr(runtime, "list_measurement_bundles", lambda: [bundle])
    monkeypatch.setattr(runtime, "get_active_measurement_bundle", lambda: bundle)
    monkeypatch.setattr(runtime, "get_validation_run", lambda _: validation)
    monkeypatch.setattr(runtime, "_runtime_identity", lambda _: {**_runtime_identity(contract), "classifier_prompt_version": "new-prompt"})
    monkeypatch.setattr(runtime, "bootstrap_baseline_measurement_bundle", lambda: (_ for _ in ()).throw(AssertionError("validated bundle rotated")))
    unavailable = runtime.resolve_measurement_context()
    assert unavailable.ready is False
    assert unavailable.reason == "measurement_runtime_identity_mismatch"
