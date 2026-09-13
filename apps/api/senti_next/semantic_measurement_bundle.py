"""Persistence and activation service for Stage 4A.1 measurement bundles."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import text

from . import db
from .classifier_taxonomy import ClassifierTaxonomyContract, baseline_classifier_taxonomy
from .classifier_validation_runtime import classifier_identity

PROVISIONAL = "PROVISIONAL"
VALIDATED = "VALIDATED"
RETIRED = "RETIRED"
_STATUSES = {PROVISIONAL, VALIDATED, RETIRED}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _ensure_db() -> None:
    db.init_db()


def _bundle_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["limitations"] = json.loads(result.pop("limitations_json") or "[]")
    result["is_active"] = bool(result.get("is_active"))
    return result


def _run_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ("topic_metrics_json", "issue_metrics_json", "request_metrics_json", "gate_reasons_json", "limitations_json", "scorer_report_json"):
        output_key = key[:-5]
        value = result.pop(key, None)
        result[output_key] = json.loads(value) if value else None
    return result


def persist_classifier_validation_run(validation_run: Mapping[str, Any]) -> dict[str, Any]:
    """Insert an immutable run record; repeated content-addressed writes are read-only."""
    _ensure_db()
    run = dict(validation_run)
    required = ("validation_run_id", "validation_dataset_id", "validation_dataset_fingerprint", "taxonomy_snapshot_id", "taxonomy_version", "taxonomy_fingerprint", "classifier_provider", "classifier_model_id", "classifier_prompt_version", "classifier_schema_version", "classifier_taxonomy_contract_fingerprint")
    missing = [key for key in required if not run.get(key)]
    if missing:
        raise ValueError("validation_run_identity_incomplete:" + ",".join(missing))
    with db.get_connection() as conn:
        existing = conn.execute(text("SELECT * FROM classifier_validation_runs WHERE validation_run_id=:id"), {"id": run["validation_run_id"]}).mappings().first()
        if existing:
            return _run_from_row(existing)
        conn.execute(text("""
            INSERT INTO classifier_validation_runs(
                validation_run_id, validation_dataset_id, validation_dataset_fingerprint, language_scope,
                taxonomy_snapshot_id, taxonomy_version, taxonomy_fingerprint,
                classifier_provider, classifier_model_id, classifier_prompt_version, classifier_schema_version,
                classifier_taxonomy_contract_fingerprint, gold_item_n, prediction_item_n, matched_prediction_n,
                evaluation_coverage, topic_metrics_json, issue_metrics_json, request_metrics_json,
                gate_policy_version, gate_status, gate_reasons_json, limitations_json, scorer_report_json,
                created_at, completed_at
            ) VALUES (
                :validation_run_id, :validation_dataset_id, :validation_dataset_fingerprint, :language_scope,
                :taxonomy_snapshot_id, :taxonomy_version, :taxonomy_fingerprint,
                :classifier_provider, :classifier_model_id, :classifier_prompt_version, :classifier_schema_version,
                :classifier_taxonomy_contract_fingerprint, :gold_item_n, :prediction_item_n, :matched_prediction_n,
                :evaluation_coverage, :topic_metrics_json, :issue_metrics_json, :request_metrics_json,
                :gate_policy_version, :gate_status, :gate_reasons_json, :limitations_json, :scorer_report_json,
                :created_at, :completed_at
            )
        """), {
            "validation_run_id": run["validation_run_id"], "validation_dataset_id": run["validation_dataset_id"],
            "validation_dataset_fingerprint": run["validation_dataset_fingerprint"], "language_scope": run.get("language_scope"),
            "taxonomy_snapshot_id": run["taxonomy_snapshot_id"], "taxonomy_version": run["taxonomy_version"], "taxonomy_fingerprint": run["taxonomy_fingerprint"],
            "classifier_provider": run["classifier_provider"], "classifier_model_id": run["classifier_model_id"], "classifier_prompt_version": run["classifier_prompt_version"], "classifier_schema_version": run["classifier_schema_version"], "classifier_taxonomy_contract_fingerprint": run["classifier_taxonomy_contract_fingerprint"],
            "gold_item_n": run["gold_item_n"], "prediction_item_n": run["prediction_item_n"], "matched_prediction_n": run["matched_prediction_n"], "evaluation_coverage": run["evaluation_coverage"],
            "topic_metrics_json": _json(run.get("topic_metrics") or {}), "issue_metrics_json": _json(run["issue_metrics"]) if run.get("issue_metrics") is not None else None, "request_metrics_json": _json(run["request_metrics"]) if run.get("request_metrics") is not None else None,
            "gate_policy_version": run["gate_policy_version"], "gate_status": run["gate_status"], "gate_reasons_json": _json(run.get("gate_reasons") or []), "limitations_json": _json(run.get("limitations") or []), "scorer_report_json": _json(run.get("scorer_report") or {}),
            "created_at": run.get("created_at") or _now(), "completed_at": run.get("completed_at") or _now(),
        })
        row = conn.execute(text("SELECT * FROM classifier_validation_runs WHERE validation_run_id=:id"), {"id": run["validation_run_id"]}).mappings().one()
        return _run_from_row(row)


def get_validation_run(validation_run_id: str) -> dict[str, Any] | None:
    _ensure_db()
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM classifier_validation_runs WHERE validation_run_id=:id"), {"id": validation_run_id}).mappings().first()
        return _run_from_row(row) if row else None


def list_validation_runs() -> list[dict[str, Any]]:
    _ensure_db()
    with db.get_connection() as conn:
        rows = conn.execute(text("SELECT * FROM classifier_validation_runs ORDER BY created_at DESC, rowid DESC")).mappings().all()
        return [_run_from_row(row) for row in rows]


def create_measurement_bundle(
    *,
    taxonomy_contract: ClassifierTaxonomyContract,
    validation_run: Mapping[str, Any] | None = None,
    measurement_status: str | None = None,
    limitations: list[str] | None = None,
    bundle_id: str | None = None,
) -> dict[str, Any]:
    """Create an immutable bundle; only an actual gate PASS can be VALIDATED."""
    _ensure_db()
    taxonomy_contract.validate()
    run = dict(validation_run) if validation_run else None
    validation_status = str(run.get("gate_status")) if run else "UNAVAILABLE"
    if run:
        for field, expected in (
            ("taxonomy_snapshot_id", taxonomy_contract.snapshot_id),
            ("taxonomy_version", taxonomy_contract.taxonomy_version),
            ("taxonomy_fingerprint", taxonomy_contract.taxonomy_fingerprint),
        ):
            if str(run.get(field)) != str(expected):
                raise ValueError("validation_run_taxonomy_identity_mismatch")
    if validation_status == "FAIL":
        if measurement_status == VALIDATED:
            raise ValueError("failed_validation_cannot_create_validated_bundle")
        requested_status = PROVISIONAL
    elif measurement_status is None:
        requested_status = VALIDATED if validation_status == "PASS" else PROVISIONAL
    else:
        requested_status = measurement_status
    if requested_status not in _STATUSES or requested_status == RETIRED:
        raise ValueError("invalid_measurement_status")
    if requested_status == VALIDATED and validation_status != "PASS":
        raise ValueError("validated_bundle_requires_pass_validation")
    resolved_identity = classifier_identity(taxonomy_contract)
    if run:
        resolved_identity.update({
            "classifier_provider": run["classifier_provider"],
            "classifier_model_id": run["classifier_model_id"],
            "classifier_prompt_version": run["classifier_prompt_version"],
            "classifier_schema_version": run["classifier_schema_version"],
        })
    bundle_limitations = sorted(set((limitations or []) + (run.get("limitations", []) if run else [])))
    if requested_status == PROVISIONAL and not run:
        bundle_limitations = sorted(set(bundle_limitations + ["not_formally_validated"]))
    content = {
        "taxonomy_snapshot_id": taxonomy_contract.snapshot_id, "taxonomy_version": taxonomy_contract.taxonomy_version, "taxonomy_fingerprint": taxonomy_contract.taxonomy_fingerprint,
        "classifier_provider": resolved_identity["classifier_provider"], "classifier_model_id": resolved_identity["classifier_model_id"], "classifier_prompt_version": resolved_identity["classifier_prompt_version"], "classifier_schema_version": resolved_identity["classifier_schema_version"],
        "validation_run_id": run.get("validation_run_id") if run else None, "validation_status": validation_status, "measurement_status": requested_status, "limitations": bundle_limitations,
    }
    resolved_id = bundle_id or "measurement_bundle_" + _sha(content)[:32]
    with db.get_connection() as conn:
        existing = conn.execute(text("SELECT * FROM semantic_measurement_bundles WHERE bundle_id=:id"), {"id": resolved_id}).mappings().first()
        if existing:
            raise ValueError("measurement_bundle_exists")
        conn.execute(text("""
            INSERT INTO semantic_measurement_bundles(
                bundle_id, taxonomy_snapshot_id, taxonomy_version, taxonomy_fingerprint,
                classifier_provider, classifier_model_id, classifier_prompt_version, classifier_schema_version,
                validation_run_id, validation_status, measurement_status, limitations_json
            ) VALUES (:bundle_id, :taxonomy_snapshot_id, :taxonomy_version, :taxonomy_fingerprint,
                :classifier_provider, :classifier_model_id, :classifier_prompt_version, :classifier_schema_version,
                :validation_run_id, :validation_status, :measurement_status, :limitations_json)
        """), {**content, "bundle_id": resolved_id, "limitations_json": _json(bundle_limitations)})
        row = conn.execute(text("SELECT * FROM semantic_measurement_bundles WHERE bundle_id=:id"), {"id": resolved_id}).mappings().one()
        return _bundle_from_row(row)


def get_measurement_bundle(bundle_id: str) -> dict[str, Any] | None:
    _ensure_db()
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM semantic_measurement_bundles WHERE bundle_id=:id"), {"id": bundle_id}).mappings().first()
        return _bundle_from_row(row) if row else None


def list_measurement_bundles() -> list[dict[str, Any]]:
    _ensure_db()
    with db.get_connection() as conn:
        rows = conn.execute(text("SELECT * FROM semantic_measurement_bundles ORDER BY created_at DESC, rowid DESC")).mappings().all()
        return [_bundle_from_row(row) for row in rows]


def get_active_measurement_bundle() -> dict[str, Any] | None:
    _ensure_db()
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM semantic_measurement_bundles WHERE is_active=1 LIMIT 1")).mappings().first()
        return _bundle_from_row(row) if row else None


def activate_measurement_bundle(bundle_id: str, *, operator: str, reason: str = "activate") -> dict[str, Any]:
    _ensure_db()
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM semantic_measurement_bundles WHERE bundle_id=:id"), {"id": bundle_id}).mappings().first()
        if not row:
            raise ValueError("measurement_bundle_not_found")
        if row["measurement_status"] == RETIRED:
            raise ValueError("retired_bundle_cannot_activate")
        if row["measurement_status"] == VALIDATED and row["validation_status"] != "PASS":
            raise ValueError("validated_bundle_requires_pass_validation")
        conn.execute(text("UPDATE semantic_measurement_bundles SET is_active=0 WHERE is_active=1"))
        conn.execute(text("UPDATE semantic_measurement_bundles SET is_active=1, activated_at=COALESCE(activated_at, datetime('now')) WHERE bundle_id=:id"), {"id": bundle_id})
        event_id = "measurement_activation_" + uuid.uuid4().hex
        conn.execute(text("INSERT INTO semantic_measurement_activation_events(activation_event_id,bundle_id,event_type,operator,reason) VALUES (:event,:bundle,'activated',:operator,:reason)"), {"event": event_id, "bundle": bundle_id, "operator": operator, "reason": reason})
        result = conn.execute(text("SELECT * FROM semantic_measurement_bundles WHERE bundle_id=:id"), {"id": bundle_id}).mappings().one()
        return _bundle_from_row(result)


def retire_measurement_bundle(bundle_id: str, *, operator: str, reason: str = "retire") -> dict[str, Any]:
    _ensure_db()
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM semantic_measurement_bundles WHERE bundle_id=:id"), {"id": bundle_id}).mappings().first()
        if not row:
            raise ValueError("measurement_bundle_not_found")
        conn.execute(text("UPDATE semantic_measurement_bundles SET measurement_status='RETIRED', is_active=0, retired_at=COALESCE(retired_at, datetime('now')) WHERE bundle_id=:id"), {"id": bundle_id})
        event_id = "measurement_activation_" + uuid.uuid4().hex
        conn.execute(text("INSERT INTO semantic_measurement_activation_events(activation_event_id,bundle_id,event_type,operator,reason) VALUES (:event,:bundle,'retired',:operator,:reason)"), {"event": event_id, "bundle": bundle_id, "operator": operator, "reason": reason})
        result = conn.execute(text("SELECT * FROM semantic_measurement_bundles WHERE bundle_id=:id"), {"id": bundle_id}).mappings().one()
        return _bundle_from_row(result)


def bootstrap_baseline_measurement_bundle() -> dict[str, Any]:
    """Return/create the honest legacy baseline for product integration."""
    _ensure_db()
    contract = baseline_classifier_taxonomy()
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM semantic_measurement_bundles WHERE taxonomy_snapshot_id=:snapshot AND validation_run_id IS NULL ORDER BY created_at ASC, rowid ASC LIMIT 1"), {"snapshot": contract.snapshot_id}).mappings().first()
        if row:
            return _bundle_from_row(row)
    return create_measurement_bundle(
        taxonomy_contract=contract,
        measurement_status=PROVISIONAL,
        limitations=["not_formally_validated", "legacy_baseline_for_engineering_integration"],
    )


__all__ = [
    "PROVISIONAL", "RETIRED", "VALIDATED",
    "activate_measurement_bundle", "bootstrap_baseline_measurement_bundle", "create_measurement_bundle",
    "get_active_measurement_bundle", "get_measurement_bundle", "list_measurement_bundles", "list_validation_runs",
    "persist_classifier_validation_run", "get_validation_run", "retire_measurement_bundle",
]
