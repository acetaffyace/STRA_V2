"""Immutable classification snapshots for a single Research Run.

The app-level review label cache remains an operational cache.  This module is
the historical source of truth for the labels consumed by a completed run.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import text

from . import db, llm
from .classifier_taxonomy import ClassifierTaxonomyContract
from .research_population_snapshot import compute_population_fingerprint, get_analysis_run_population_metadata

_ITEM_STATUSES = {"classified", "fallback", "missing"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _review_id(review: Mapping[str, Any]) -> str:
    value = review.get("recommendationid") or review.get("review_id")
    if value is None or str(value) == "":
        raise ValueError("classification_materialization_review_id_required")
    return str(value)


def _review_hash(review: Mapping[str, Any]) -> str:
    return hashlib.sha256(str(review.get("review") or "").encode("utf-8")).hexdigest()


def _bundle_identity(bundle: Mapping[str, Any]) -> dict[str, str]:
    return {
        "provider": str(bundle.get("classifier_provider") or ""),
        "model_id": str(bundle.get("classifier_model_id") or ""),
        "prompt_version": str(bundle.get("classifier_prompt_version") or ""),
        "schema_version": str(bundle.get("classifier_schema_version") or ""),
        "taxonomy_snapshot_id": str(bundle.get("taxonomy_snapshot_id") or ""),
        "taxonomy_version": str(bundle.get("taxonomy_version") or ""),
        "taxonomy_fingerprint": str(bundle.get("taxonomy_fingerprint") or ""),
    }


def population_fingerprint(all_reviews: Sequence[Mapping[str, Any]]) -> str:
    """Compatibility wrapper for the shared immutable population contract."""
    return compute_population_fingerprint(all_reviews)


def _parse_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value:
        parsed = json.loads(value) if isinstance(value, str) else value
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["items"] = []
    result["is_immutable"] = True
    return result


def _item_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["validated"] = bool(result.get("validated"))
    result["payload"] = _parse_payload(result.pop("payload_json", None))
    return result


def _load_items(conn: Any, materialization_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """SELECT materialization_id, review_id, item_status, review_hash,
                      classification_input_hash, label_origin, validated,
                      provider, model_id, prompt_version, taxonomy_version,
                      taxonomy_snapshot_id, taxonomy_fingerprint, payload_json,
                      generated_at
               FROM classification_materialization_items
               WHERE materialization_id=:materialization_id
               ORDER BY review_id"""
        ),
        {"materialization_id": materialization_id},
    ).mappings().all()
    return [_item_row(row) for row in rows]


def get_classification_materialization(materialization_id: str) -> dict[str, Any] | None:
    db.init_db()
    with db.get_connection() as conn:
        row = conn.execute(
            text("SELECT * FROM classification_materializations WHERE materialization_id=:id"),
            {"id": materialization_id},
        ).mappings().first()
        if not row:
            return None
        result = _row(row)
        result["items"] = _load_items(conn, materialization_id)
        return result


def get_materialization_for_run(run_id: str) -> dict[str, Any] | None:
    db.init_db()
    with db.get_connection() as conn:
        row = conn.execute(
            text("SELECT * FROM classification_materializations WHERE run_id=:run_id"),
            {"run_id": run_id},
        ).mappings().first()
        if not row:
            return None
        result = _row(row)
        result["items"] = _load_items(conn, str(row["materialization_id"]))
        return result


def _validate_item_identity(item: Mapping[str, Any], identity: Mapping[str, str]) -> None:
    for key in ("prompt_version", "taxonomy_version", "taxonomy_snapshot_id", "taxonomy_fingerprint"):
        if str(item.get(key) or "") != identity[key if key != "prompt_version" else "prompt_version"]:
            raise ValueError("classification_materialization_identity_mismatch")
    if item.get("item_status") == "classified":
        if str(item.get("provider") or "") != identity["provider"] or str(item.get("model_id") or "") != identity["model_id"]:
            raise ValueError("classification_materialization_identity_mismatch")


def create_classification_materialization(
    *,
    run_id: str,
    app_id: int,
    all_reviews: Sequence[Mapping[str, Any]],
    bundle: Mapping[str, Any],
    taxonomy_contract: ClassifierTaxonomyContract,
    labels: Mapping[str, Mapping[str, Any]],
    game_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze labels for exactly ``all_reviews``; repeated identical writes are idempotent."""
    db.init_db()
    taxonomy_contract.validate()
    identity = _bundle_identity(bundle)
    expected_taxonomy = {
        "taxonomy_snapshot_id": taxonomy_contract.snapshot_id,
        "taxonomy_version": taxonomy_contract.taxonomy_version,
        "taxonomy_fingerprint": taxonomy_contract.taxonomy_fingerprint,
    }
    if any(identity[key] != value for key, value in expected_taxonomy.items()):
        raise ValueError("classification_materialization_identity_mismatch")

    items: list[dict[str, Any]] = []
    for review in all_reviews:
        review_id = _review_id(review)
        current_identity = llm.classification_identity(
            review,
            game_context,
            provider=identity["provider"],
            model_id=identity["model_id"],
            prompt_version=identity["prompt_version"],
            taxonomy_contract=taxonomy_contract,
        )
        label = labels.get(review_id)
        payload = _parse_payload(label.get("payload") if label else None)
        validated = bool(label and label.get("label_origin") == "llm" and label.get("validated") is True)
        if validated:
            label_identity = {
                "provider": str(label.get("provider") or ""),
                "model_id": str(label.get("model_id") or ""),
                "prompt_version": str(label.get("prompt_version") or ""),
                "taxonomy_version": str(label.get("taxonomy_version") or ""),
                "taxonomy_snapshot_id": str(label.get("taxonomy_snapshot_id") or ""),
                "taxonomy_fingerprint": str(label.get("taxonomy_fingerprint") or ""),
            }
            if any(label_identity[key] != identity[key] for key in label_identity) or str(label.get("review_hash") or "") != current_identity["review_hash"]:
                raise ValueError("classification_materialization_identity_mismatch")
        if validated:
            item_status = "classified"
        elif label is not None:
            item_status = "fallback"
        else:
            item_status = "missing"

        item = {
            "review_id": review_id,
            "item_status": item_status,
            "review_hash": _review_hash(review),
            "classification_input_hash": str((label or {}).get("classification_input_hash") or current_identity["classification_input_hash"]),
            "label_origin": (label or {}).get("label_origin"),
            "validated": validated,
            "provider": (label or {}).get("provider") if item_status == "classified" else ((label or {}).get("provider") or None),
            "model_id": (label or {}).get("model_id") if item_status == "classified" else ((label or {}).get("model_id") or None),
            "prompt_version": identity["prompt_version"],
            "taxonomy_version": identity["taxonomy_version"],
            "taxonomy_snapshot_id": identity["taxonomy_snapshot_id"],
            "taxonomy_fingerprint": identity["taxonomy_fingerprint"],
            "payload": payload,
            "generated_at": (label or {}).get("generated_at"),
        }
        _validate_item_identity(item, identity)
        items.append(item)

    items.sort(key=lambda item: item["review_id"])
    population_fp = population_fingerprint(all_reviews)
    population_snapshot = get_analysis_run_population_metadata(run_id)
    if population_snapshot is not None and (
        population_snapshot["population_fingerprint"] != population_fp
        or int(population_snapshot["population_n"]) != len(all_reviews)
    ):
        raise ValueError("classification_population_snapshot_mismatch")
    if population_snapshot is None:
        # Existing unit seams use synthetic materialization IDs without a
        # persisted analysis_runs row. Real analysis runs must always have the
        # independent immutable snapshot created by /analyze.
        with db.get_connection() as conn:
            analysis_run_exists = conn.execute(
                text("SELECT 1 FROM analysis_runs WHERE run_id=:run_id AND run_type='general_analysis'"),
                {"run_id": run_id},
            ).first() is not None
        if analysis_run_exists:
            raise ValueError("research_population_snapshot_unavailable")
    materialization_content = {
        "run_id": run_id,
        "measurement_bundle_id": bundle["bundle_id"],
        "measurement_status": bundle["measurement_status"],
        "validation_run_id": bundle.get("validation_run_id"),
        "validation_status": bundle.get("validation_status"),
        **identity,
        "population_fingerprint": population_fp,
        "items": items,
    }
    materialization_fp = _sha(materialization_content)
    materialization_id = "classification_materialization_" + _sha({"run_id": run_id, "materialization_fingerprint": materialization_fp})[:32]
    counts = {
        "materialized_n": len(items),
        "validated_llm_n": sum(item["item_status"] == "classified" for item in items),
        "fallback_n": sum(item["item_status"] == "fallback" for item in items),
        "missing_n": sum(item["item_status"] == "missing" for item in items),
    }

    with db.get_connection() as conn:
        existing = conn.execute(
            text("SELECT * FROM classification_materializations WHERE run_id=:run_id"),
            {"run_id": run_id},
        ).mappings().first()
        if existing:
            if str(existing["materialization_fingerprint"]) != materialization_fp:
                raise ValueError("classification_materialization_conflict")
            result = _row(existing)
            result["items"] = _load_items(conn, str(existing["materialization_id"]))
            return result

        conn.execute(
            text(
                """INSERT INTO classification_materializations(
                    materialization_id, run_id, app_id, measurement_bundle_id,
                    measurement_status, validation_run_id, validation_status,
                    taxonomy_snapshot_id, taxonomy_version, taxonomy_fingerprint,
                    classifier_provider, classifier_model_id,
                    classifier_prompt_version, classifier_schema_version,
                    population_fingerprint, population_n, materialized_n,
                    validated_llm_n, fallback_n, missing_n,
                    materialization_fingerprint, created_at
                ) VALUES (
                    :materialization_id, :run_id, :app_id, :measurement_bundle_id,
                    :measurement_status, :validation_run_id, :validation_status,
                    :taxonomy_snapshot_id, :taxonomy_version, :taxonomy_fingerprint,
                    :classifier_provider, :classifier_model_id,
                    :classifier_prompt_version, :classifier_schema_version,
                    :population_fingerprint, :population_n, :materialized_n,
                    :validated_llm_n, :fallback_n, :missing_n,
                    :materialization_fingerprint, :created_at
                )"""
            ),
            {
                "materialization_id": materialization_id,
                "run_id": run_id,
                "app_id": int(app_id),
                "measurement_bundle_id": bundle["bundle_id"],
                "measurement_status": bundle["measurement_status"],
                "validation_run_id": bundle.get("validation_run_id"),
                "validation_status": bundle.get("validation_status"),
                "taxonomy_snapshot_id": identity["taxonomy_snapshot_id"],
                "taxonomy_version": identity["taxonomy_version"],
                "taxonomy_fingerprint": identity["taxonomy_fingerprint"],
                "classifier_provider": identity["provider"],
                "classifier_model_id": identity["model_id"],
                "classifier_prompt_version": identity["prompt_version"],
                "classifier_schema_version": identity["schema_version"],
                "population_fingerprint": population_fp,
                "population_n": len(all_reviews),
                **counts,
                "materialization_fingerprint": materialization_fp,
                "created_at": _now(),
            },
        )
        for item in items:
            conn.execute(
                text(
                    """INSERT INTO classification_materialization_items(
                        materialization_id, review_id, item_status, review_hash,
                        classification_input_hash, label_origin, validated,
                        provider, model_id, prompt_version, taxonomy_version,
                        taxonomy_snapshot_id, taxonomy_fingerprint, payload_json,
                        generated_at
                    ) VALUES (
                        :materialization_id, :review_id, :item_status, :review_hash,
                        :classification_input_hash, :label_origin, :validated,
                        :provider, :model_id, :prompt_version, :taxonomy_version,
                        :taxonomy_snapshot_id, :taxonomy_fingerprint, :payload_json,
                        :generated_at
                    )"""
                ),
                {**item, "materialization_id": materialization_id, "validated": int(item["validated"]), "payload_json": _json(item["payload"])},
            )
        row = conn.execute(
            text("SELECT * FROM classification_materializations WHERE materialization_id=:id"),
            {"id": materialization_id},
        ).mappings().one()
        result = _row(row)
        result["items"] = _load_items(conn, materialization_id)
        return result


def load_materialized_review_labels(materialization_id: str) -> dict[str, dict[str, Any]]:
    materialization = get_classification_materialization(materialization_id)
    if materialization is None:
        raise ValueError("classification_materialization_not_found")
    labels: dict[str, dict[str, Any]] = {}
    for item in materialization["items"]:
        labels[item["review_id"]] = {
            "model": item.get("model_id"),
            "payload": item.get("payload") or {},
            "label_origin": item.get("label_origin"),
            "validated": bool(item.get("validated")),
            "taxonomy_version": item.get("taxonomy_version"),
            "taxonomy_snapshot_id": item.get("taxonomy_snapshot_id"),
            "taxonomy_fingerprint": item.get("taxonomy_fingerprint"),
            "provider": item.get("provider"),
            "model_id": item.get("model_id"),
            "prompt_version": item.get("prompt_version"),
            "classification_input_hash": item.get("classification_input_hash"),
            "review_hash": item.get("review_hash"),
            "generated_at": item.get("generated_at"),
        }
    return labels


def bind_measurement_to_analysis_run(run_id: str, bundle: Mapping[str, Any]) -> None:
    db.init_db()
    with db.get_connection() as conn:
        result = conn.execute(
            text(
                """UPDATE analysis_runs SET measurement_bundle_id=:bundle_id,
                           taxonomy_snapshot_id=:snapshot_id,
                           taxonomy_fingerprint=:taxonomy_fingerprint,
                           measurement_status=:measurement_status,
                           validation_run_id=:validation_run_id,
                           validation_status=:validation_status,
                           taxonomy_version=COALESCE(taxonomy_version, :taxonomy_version),
                           provider=COALESCE(provider, :provider),
                           model_id=COALESCE(model_id, :model_id),
                           prompt_version=COALESCE(prompt_version, :prompt_version),
                           updated_at=datetime('now')
                    WHERE run_id=:run_id AND run_type='general_analysis'"""
            ),
            {
                "run_id": run_id,
                "bundle_id": bundle["bundle_id"],
                "snapshot_id": bundle["taxonomy_snapshot_id"],
                "taxonomy_fingerprint": bundle["taxonomy_fingerprint"],
                "measurement_status": bundle["measurement_status"],
                "validation_run_id": bundle.get("validation_run_id"),
                "validation_status": bundle.get("validation_status"),
                "taxonomy_version": bundle["taxonomy_version"],
                "provider": bundle["classifier_provider"],
                "model_id": bundle["classifier_model_id"],
                "prompt_version": bundle["classifier_prompt_version"],
            },
        )
        if result.rowcount != 1:
            raise ValueError("analysis_run_not_found")


def bind_materialization_to_analysis_run(run_id: str, materialization_id: str) -> None:
    db.init_db()
    with db.get_connection() as conn:
        result = conn.execute(
            text(
                """UPDATE analysis_runs SET classification_materialization_id=:materialization_id,
                           updated_at=datetime('now')
                    WHERE run_id=:run_id AND run_type='general_analysis'"""
            ),
            {"run_id": run_id, "materialization_id": materialization_id},
        )
        if result.rowcount != 1:
            raise ValueError("analysis_run_not_found")


__all__ = [
    "bind_materialization_to_analysis_run",
    "bind_measurement_to_analysis_run",
    "create_classification_materialization",
    "get_classification_materialization",
    "get_materialization_for_run",
    "load_materialized_review_labels",
    "population_fingerprint",
]
