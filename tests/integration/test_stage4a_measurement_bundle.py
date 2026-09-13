from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from sqlalchemy import text

from apps.api.senti_next import db, migrations
from apps.api.senti_next.classifier_taxonomy import baseline_classifier_taxonomy
from apps.api.senti_next.classifier_validation_runtime import run_classifier_validation
from apps.api.senti_next.semantic_measurement_bundle import (
    PROVISIONAL,
    VALIDATED,
    activate_measurement_bundle,
    create_measurement_bundle,
    get_active_measurement_bundle,
    get_measurement_bundle,
    list_measurement_bundles,
    persist_classifier_validation_run,
    retire_measurement_bundle,
)


@pytest.fixture(autouse=True)
def isolated_db():
    db.close_engine()
    db.init_db()
    yield
    db.close_engine()


def _run(status="PASS"):
    gold = [
        {"review_id": str(index), "gold_labels": ["technical/bugs"], "gold_primary_label": "technical/bugs", "gold_issue_labels": ["technical/bugs"], "gold_request_labels": ["technical/bugs"]}
        for index in range(5)
    ]

    def fake(items, *, taxonomy_contract):
        return {item["review_id"]: {"subcategories": ["technical/bugs"], "issue_subcategories": ["technical/bugs"], "request_subcategories": ["technical/bugs"]} for item in items}

    result = run_classifier_validation(gold, classifier=fake, provider="fake", model_id="fake:model", prompt_version="p", schema_version="s")
    if status == "FAIL":
        result["gate_status"] = "FAIL"
    return result


def test_migration_20_is_idempotent_and_legacy_history_is_retained():
    with db.get_connection() as conn:
        assert conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar() == 20
        tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
        assert {"classifier_validation_runs", "semantic_measurement_bundles", "semantic_measurement_activation_events"} <= tables
    db.init_db()
    assert migrations.latest_known_schema_version() == 20


def test_provisional_and_validated_activation_are_distinct_and_retirement_is_durable():
    contract = baseline_classifier_taxonomy()
    provisional = create_measurement_bundle(taxonomy_contract=contract, measurement_status=PROVISIONAL, limitations=["not_formally_validated"])
    assert provisional["measurement_status"] == PROVISIONAL
    activate_measurement_bundle(provisional["bundle_id"], operator="test")
    assert get_active_measurement_bundle()["bundle_id"] == provisional["bundle_id"]

    run = _run()
    persisted = persist_classifier_validation_run(run)
    validated = create_measurement_bundle(taxonomy_contract=contract, validation_run=persisted)
    assert validated["measurement_status"] == VALIDATED
    activate_measurement_bundle(validated["bundle_id"], operator="test", reason="replace provisional")
    assert get_active_measurement_bundle()["bundle_id"] == validated["bundle_id"]
    retired = retire_measurement_bundle(validated["bundle_id"], operator="test")
    assert retired["measurement_status"] == "RETIRED"
    assert get_active_measurement_bundle() is None
    assert len(list_measurement_bundles()) == 2


def test_failed_validation_cannot_become_validated_bundle():
    run = _run("FAIL")
    persisted = persist_classifier_validation_run(run)
    with pytest.raises(ValueError, match="failed_validation"):
        create_measurement_bundle(taxonomy_contract=baseline_classifier_taxonomy(), validation_run=persisted, measurement_status=VALIDATED)
