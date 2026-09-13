"""Canonical 3F semantic measurement from an immutable classification snapshot.

This module deliberately consumes only ``ClassificationMaterialization`` and
the persisted measurement/validation contracts.  Topic, issue, and request
shares are observed shares among validated LLM-classified reviews; they are
not estimates of all-player prevalence.  Topic/issue/request shares are
multi-label and may sum above one.  Primary-topic shares are mutually
exclusive.  Classification coverage uses the full research population as its
denominator.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .classifier_taxonomy import baseline_classifier_taxonomy, load_classifier_taxonomy
from .classification_materialization import get_classification_materialization
from .semantic_measurement_bundle import PROVISIONAL, VALIDATED, get_measurement_bundle, get_validation_run

SEMANTIC_MEASUREMENT_RESULT_SCHEMA_VERSION = "semantic-measurement-result-v1"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _labels(payload: Mapping[str, Any], field: str) -> list[str]:
    value = payload.get(field) or []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, (list, tuple)):
        return []
    # A frozen payload is validated below; de-duplication here makes the
    # counting rule explicit and prevents duplicate model output inflating n.
    return list(dict.fromkeys(str(item) for item in value if str(item).strip()))


def _validation_qualification(
    *,
    validation_run: Mapping[str, Any] | None,
    bundle_status: str,
    metrics_key: str,
    topic_key: str,
) -> dict[str, Any]:
    if bundle_status != "VALIDATED":
        return {"status": "UNVALIDATED", "reason": "provisional_measurement_bundle"}
    if validation_run is None:
        return {"status": "UNVALIDATED", "reason": "validation_run_unavailable"}
    metrics = validation_run.get(metrics_key)
    if metrics is None:
        return {"status": "UNVALIDATED", "reason": f"{metrics_key.removesuffix('_metrics')}_gold_unavailable"}
    per_topic = metrics.get("per_topic") or {}
    support_status = (metrics.get("topic_support_status") or {}).get(topic_key, "insufficient")
    row = dict(per_topic.get(topic_key) or {})
    row["gold_support"] = int(row.get("gold_support") or 0)
    row["support_status"] = support_status
    if support_status == "sufficient":
        status = "VALIDATED"
    elif support_status == "limited":
        status = "LIMITED"
    else:
        status = "INSUFFICIENT"
    row["status"] = status
    return row


def _validate_materialization(
    materialization: Mapping[str, Any],
    bundle: Mapping[str, Any],
    validation_run: Mapping[str, Any] | None,
    frozen_measurement_status: str,
) -> tuple[Any, list[Mapping[str, Any]], int, int, int]:
    if str(materialization.get("run_id")) == "":
        raise ValueError("semantic_measurement_materialization_incomplete")
    if str(materialization.get("measurement_bundle_id")) != str(bundle.get("bundle_id")):
        raise ValueError("semantic_measurement_materialization_incomplete")
    for key in (
        "taxonomy_snapshot_id", "taxonomy_version", "taxonomy_fingerprint",
        "classifier_provider", "classifier_model_id", "classifier_prompt_version",
        "classifier_schema_version",
    ):
        if str(materialization.get(key) or "") != str(bundle.get(key) or ""):
            raise ValueError("semantic_measurement_materialization_incomplete")
    if str(materialization.get("validation_run_id") or "") != str(bundle.get("validation_run_id") or ""):
        raise ValueError("semantic_measurement_materialization_incomplete")
    if frozen_measurement_status == VALIDATED and validation_run is None:
        raise ValueError("semantic_measurement_invalid_validation_provenance")
    if validation_run is not None:
        for key in ("taxonomy_snapshot_id", "taxonomy_version", "taxonomy_fingerprint", "classifier_prompt_version", "classifier_schema_version"):
            if str(validation_run.get(key) or "") != str(materialization.get(key) or ""):
                if frozen_measurement_status == VALIDATED:
                    raise ValueError("semantic_measurement_invalid_validation_provenance")
                raise ValueError("semantic_measurement_materialization_incomplete")
        if str(validation_run.get("actual_provider") or validation_run.get("classifier_provider") or "") != str(materialization.get("classifier_provider") or ""):
            if frozen_measurement_status == VALIDATED:
                raise ValueError("semantic_measurement_invalid_validation_provenance")
            raise ValueError("semantic_measurement_materialization_incomplete")
        if str(validation_run.get("actual_model_id") or "") != str(materialization.get("classifier_model_id") or ""):
            if frozen_measurement_status == VALIDATED:
                raise ValueError("semantic_measurement_invalid_validation_provenance")
            raise ValueError("semantic_measurement_materialization_incomplete")
        if frozen_measurement_status == VALIDATED and (
            validation_run.get("gate_status") != "PASS"
            or validation_run.get("execution_mode") != "production_classifier"
            or not validation_run.get("actual_model_id")
            or not validation_run.get("execution_identity_fingerprint")
        ):
            raise ValueError("semantic_measurement_invalid_validation_provenance")

    try:
        baseline = baseline_classifier_taxonomy()
        taxonomy = (
            baseline
            if str(materialization.get("taxonomy_version")) == baseline.taxonomy_version
            else load_classifier_taxonomy(snapshot_id=str(materialization["taxonomy_snapshot_id"]))
        )
        taxonomy.validate()
    except Exception as exc:
        raise ValueError("semantic_measurement_materialization_incomplete") from exc
    if str(taxonomy.taxonomy_version) != str(materialization.get("taxonomy_version")) or str(taxonomy.taxonomy_fingerprint) != str(materialization.get("taxonomy_fingerprint")):
        raise ValueError("semantic_measurement_materialization_incomplete")

    items = list(materialization.get("items") or [])
    population_n = int(materialization.get("population_n") or 0)
    materialized_n = int(materialization.get("materialized_n") or 0)
    if population_n != materialized_n or materialized_n != len(items):
        raise ValueError("semantic_measurement_materialization_incomplete")
    allowed = set(taxonomy.active_topic_keys)
    classified_n = fallback_n = missing_n = 0
    for item in items:
        status = str(item.get("item_status") or "")
        if status not in {"classified", "fallback", "missing"}:
            raise ValueError("semantic_measurement_materialization_incomplete")
        for item_key, materialization_key in (
            ("prompt_version", "classifier_prompt_version"),
            ("taxonomy_version", "taxonomy_version"),
            ("taxonomy_snapshot_id", "taxonomy_snapshot_id"),
            ("taxonomy_fingerprint", "taxonomy_fingerprint"),
        ):
            if str(item.get(item_key) or "") != str(materialization.get(materialization_key) or ""):
                raise ValueError("semantic_measurement_materialization_incomplete")
        if status == "classified" and (
            str(item.get("provider") or "") != str(materialization.get("classifier_provider") or "")
            or str(item.get("model_id") or "") != str(materialization.get("classifier_model_id") or "")
        ):
            raise ValueError("semantic_measurement_materialization_incomplete")
        if status == "fallback":
            fallback_n += 1
        elif status == "missing":
            missing_n += 1
        if status == "classified":
            if item.get("label_origin") != "llm" or item.get("validated") is not True:
                raise ValueError("semantic_measurement_materialization_incomplete")
            classified_n += 1
            payload = item.get("payload") or {}
            topics = _labels(payload, "subcategories")
            issues = _labels(payload, "issue_subcategories")
            requests = _labels(payload, "request_subcategories")
            if not set(topics).issubset(allowed) or not set(issues).issubset(allowed) or not set(requests).issubset(allowed):
                raise ValueError("semantic_measurement_invalid_materialized_payload")
            if not set(issues).issubset(topics) or not set(requests).issubset(topics):
                raise ValueError("semantic_measurement_invalid_materialized_payload")
    if (int(materialization.get("validated_llm_n") or 0), int(materialization.get("fallback_n") or 0), int(materialization.get("missing_n") or 0)) != (classified_n, fallback_n, missing_n):
        raise ValueError("semantic_measurement_materialization_incomplete")
    return taxonomy, items, population_n, materialized_n, classified_n


def build_semantic_measurement_result(*, run_id: str, materialization_id: str) -> dict[str, Any]:
    """Build a deterministic, frozen 3F measurement for one research run."""
    materialization = get_classification_materialization(materialization_id)
    if materialization is None or str(materialization.get("run_id")) != str(run_id):
        raise ValueError("semantic_measurement_materialization_incomplete")
    frozen_measurement_status = str(materialization.get("measurement_status") or "")
    if frozen_measurement_status not in {PROVISIONAL, VALIDATED}:
        raise ValueError("semantic_measurement_invalid_frozen_measurement_status")
    bundle = get_measurement_bundle(str(materialization.get("measurement_bundle_id") or ""))
    if bundle is None:
        raise ValueError("semantic_measurement_materialization_incomplete")
    if str(materialization.get("validation_run_id") or "") != str(bundle.get("validation_run_id") or ""):
        raise ValueError("semantic_measurement_materialization_incomplete")
    validation_run = get_validation_run(str(materialization["validation_run_id"])) if materialization.get("validation_run_id") else None
    taxonomy, items, population_n, materialized_n, classified_n = _validate_materialization(
        materialization, bundle, validation_run, frozen_measurement_status
    )

    topic_n = {key: 0 for key in taxonomy.active_topic_keys}
    primary_n = {key: 0 for key in taxonomy.active_topic_keys}
    issue_n = {key: 0 for key in taxonomy.active_topic_keys}
    request_n = {key: 0 for key in taxonomy.active_topic_keys}
    for item in items:
        if item.get("item_status") != "classified":
            continue
        payload = item.get("payload") or {}
        topics = _labels(payload, "subcategories")
        for key in topics:
            topic_n[key] += 1
        if topics:
            primary_n[topics[0]] += 1
        for key in _labels(payload, "issue_subcategories"):
            issue_n[key] += 1
        for key in _labels(payload, "request_subcategories"):
            request_n[key] += 1

    denominator = classified_n
    topic_rows: list[dict[str, Any]] = []
    for key in taxonomy.active_topic_keys:
        topic_rows.append({
            "topic_key": key,
            "topic_n": topic_n[key],
            "topic_share": topic_n[key] / denominator if denominator else 0.0,
            "observed_classified_topic_share": topic_n[key] / denominator if denominator else 0.0,
            "primary_n": primary_n[key],
            "primary_share": primary_n[key] / denominator if denominator else 0.0,
            "issue_n": issue_n[key],
            "issue_share": issue_n[key] / denominator if denominator else 0.0,
            "request_n": request_n[key],
            "request_share": request_n[key] / denominator if denominator else 0.0,
            "topic_validation": _validation_qualification(validation_run=validation_run, bundle_status=frozen_measurement_status, metrics_key="topic_metrics", topic_key=key),
            "issue_validation": _validation_qualification(validation_run=validation_run, bundle_status=frozen_measurement_status, metrics_key="issue_metrics", topic_key=key),
            "request_validation": _validation_qualification(validation_run=validation_run, bundle_status=frozen_measurement_status, metrics_key="request_metrics", topic_key=key),
        })

    coverage = classified_n / population_n if population_n else 0.0
    coverage_status = "NONE" if classified_n == 0 else "FULL" if classified_n == population_n else "PARTIAL"
    limitations = sorted(set(bundle.get("limitations") or []))
    if frozen_measurement_status == PROVISIONAL:
        limitations.append("provisional_measurement_bundle")
    if coverage_status == "PARTIAL":
        limitations.append("partial_classification_coverage")
    if classified_n == 0:
        limitations.append("no_validated_classifications")
    if frozen_measurement_status == VALIDATED and any(row["issue_validation"]["status"] != "VALIDATED" for row in topic_rows):
        limitations.append("issue_measurement_not_fully_validated")
    if frozen_measurement_status == VALIDATED and any(row["request_validation"]["status"] != "VALIDATED" for row in topic_rows):
        limitations.append("request_measurement_not_fully_validated")
    limitations = sorted(set(limitations))
    provenance = {
        "measurement_bundle_id": bundle["bundle_id"],
        "measurement_status": frozen_measurement_status,
        "validation_run_id": materialization.get("validation_run_id"),
        "validation_status": materialization.get("validation_status"),
        "taxonomy_snapshot_id": materialization["taxonomy_snapshot_id"],
        "taxonomy_version": materialization["taxonomy_version"],
        "taxonomy_fingerprint": materialization["taxonomy_fingerprint"],
        "classifier_provider": materialization["classifier_provider"],
        "classifier_model_id": materialization["classifier_model_id"],
        "classifier_prompt_version": materialization["classifier_prompt_version"],
        "classifier_schema_version": materialization["classifier_schema_version"],
        "classification_materialization_id": materialization["materialization_id"],
        "materialization_fingerprint": materialization["materialization_fingerprint"],
        "population_fingerprint": materialization["population_fingerprint"],
    }
    result = {
        "schema_version": SEMANTIC_MEASUREMENT_RESULT_SCHEMA_VERSION,
        "run_id": str(run_id),
        "materialization_id": materialization["materialization_id"],
        "classification_materialization_id": materialization["materialization_id"],
        "measurement_bundle_id": bundle["bundle_id"],
        "claim_status": frozen_measurement_status,
        "provenance": provenance,
        "population_n": population_n,
        "materialized_n": materialized_n,
        "classified_n": classified_n,
        "validated_llm_n": classified_n,
        "fallback_n": int(materialization.get("fallback_n") or 0),
        "missing_n": int(materialization.get("missing_n") or 0),
        "classification_coverage": coverage,
        "coverage_status": coverage_status,
        "measurement_state": "NO_POPULATION" if population_n == 0 else "MEASURED",
        "denominators": {"population_n": population_n, "materialized_n": materialized_n, "classified_n": classified_n},
        "topics": topic_rows,
        "limitations": limitations,
        "semantics": {
            "topic_share": "multi_label_observed_classified_share",
            "issue_share": "multi_label_observed_classified_share",
            "request_share": "multi_label_observed_classified_share",
            "primary_share": "mutually_exclusive_observed_classified_share",
            "classification_coverage": "classified_n_divided_by_population_n",
            "observed_population": "validated_llm_classified_Steam_reviews_not_all_players",
        },
    }
    result["semantic_measurement_result_fingerprint"] = _sha(result)
    result["result_fingerprint"] = result["semantic_measurement_result_fingerprint"]
    return result


__all__ = ["SEMANTIC_MEASUREMENT_RESULT_SCHEMA_VERSION", "build_semantic_measurement_result"]
