"""Runtime orchestration for real classifier validation.

The provider-free scorer remains in :mod:`classifier_validation`.  This
module binds a gold dataset and an explicit taxonomy contract to the same
production classifier entry point used by analysis, then records execution
provenance and applies the versioned admission gate.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from .classifier_taxonomy import ClassifierTaxonomyContract, baseline_classifier_taxonomy
from .classifier_validation import evaluate_classifier_fixture
from .classifier_validation_policy import ClassifierValidationPolicy, evaluate_validation_gate

VALIDATION_DATASET_SCHEMA_VERSION = "classifier-validation-dataset-v1"
CLASSIFIER_VALIDATION_RUN_SCHEMA_VERSION = "classifier-validation-run-v1"
_SCORER_ONLY_LIMITATIONS = {"synthetic_or_offline_validation_only", "not_real_model_validation"}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(item: Mapping[str, Any]) -> str:
    return str(item.get("review_text") or item.get("review") or "")


def _labels(item: Mapping[str, Any], key: str) -> list[str]:
    value = item.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(entry) for entry in value]


def normalized_validation_items(gold_items: Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the stable benchmark identity projection, without file/time/object identity."""
    rows = [dict(gold_items)] if isinstance(gold_items, Mapping) else [dict(row) for row in gold_items]
    normalized = []
    for row in rows:
        review_id = row.get("review_id")
        if review_id is None:
            raise ValueError("validation_dataset_review_id_required")
        text = _text(row)
        normalized.append({
            "review_id": str(review_id),
            "review_text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
            "gold_labels": sorted(set(_labels(row, "gold_labels"))),
            "gold_issue_labels": sorted(set(_labels(row, "gold_issue_labels"))),
            "gold_request_labels": sorted(set(_labels(row, "gold_request_labels"))),
            "gold_primary_label": str(row["gold_primary_label"]) if row.get("gold_primary_label") is not None else None,
            "language": str(row.get("language") or row.get("review_language") or "") or None,
        })
    return sorted(normalized, key=lambda row: row["review_id"])


def validation_dataset_identity(
    gold_items: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    validation_dataset_id: str | None = None,
    language_scope: str | None = None,
) -> dict[str, Any]:
    items = normalized_validation_items(gold_items)
    fingerprint = _sha({"schema_version": VALIDATION_DATASET_SCHEMA_VERSION, "items": items})
    languages = sorted({row["language"] for row in items if row.get("language")})
    scope = language_scope or (languages[0] if len(languages) == 1 else "mixed" if languages else "unspecified")
    return {
        "validation_dataset_id": validation_dataset_id or f"validation-dataset-{fingerprint[:16]}",
        "validation_dataset_fingerprint": fingerprint,
        "gold_item_n": len(items),
        "language_scope": scope,
    }


def production_classifier(items: Sequence[Mapping[str, Any]], *, taxonomy_contract: ClassifierTaxonomyContract) -> Mapping[str, Any]:
    """Invoke the production batch classifier with the exact supplied contract."""
    from .llm import classify_reviews

    predictions, _model_used = classify_reviews(list(items), taxonomy_contract=taxonomy_contract)
    return predictions


def classifier_identity(
    contract: ClassifierTaxonomyContract,
    *,
    provider: str | None = None,
    model_id: str | None = None,
    prompt_version: str | None = None,
    schema_version: str | None = None,
) -> dict[str, Any]:
    """Resolve identity from existing classifier/provider sources."""
    from .llm import CLASSIFICATION_SCHEMA_VERSION, active_classifier_prompt_version
    from .providers import get_active_config

    config = get_active_config()
    resolved_provider = provider or config.get("provider") or "unconfigured"
    resolved_model_id = model_id or config.get("model_id") or "unconfigured"
    return {
        "classifier_provider": str(resolved_provider),
        "classifier_model_id": str(resolved_model_id),
        "classifier_prompt_version": prompt_version or active_classifier_prompt_version(),
        "classifier_schema_version": schema_version or CLASSIFICATION_SCHEMA_VERSION,
        "taxonomy_snapshot_id": contract.snapshot_id,
        "taxonomy_version": contract.taxonomy_version,
        "taxonomy_fingerprint": contract.taxonomy_fingerprint,
        "classifier_taxonomy_contract_fingerprint": contract.fingerprint,
    }


def run_classifier_validation(
    gold_items: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    taxonomy_contract: ClassifierTaxonomyContract | None = None,
    classifier: Callable[..., Mapping[str, Any]] | None = None,
    validation_dataset_id: str | None = None,
    language_scope: str | None = None,
    provider: str | None = None,
    model_id: str | None = None,
    prompt_version: str | None = None,
    schema_version: str | None = None,
    policy: ClassifierValidationPolicy | None = None,
) -> dict[str, Any]:
    """Run the production-compatible classifier and return an immutable run record."""
    contract = taxonomy_contract or baseline_classifier_taxonomy()
    contract.validate()
    dataset = validation_dataset_identity(
        gold_items, validation_dataset_id=validation_dataset_id, language_scope=language_scope,
    )
    identity = classifier_identity(
        contract, provider=provider, model_id=model_id, prompt_version=prompt_version, schema_version=schema_version,
    )
    execution_mode = "production_classifier" if classifier is None else "injected_classifier"
    classifier_fn = classifier or production_classifier
    predictions = classifier_fn(list(gold_items) if not isinstance(gold_items, Mapping) else [dict(gold_items)], taxonomy_contract=contract)
    scorer_report = evaluate_classifier_fixture(gold_items, predictions, taxonomy_contract=contract)
    gate = evaluate_validation_gate(scorer_report, policy=policy)
    limitations = [value for value in scorer_report.get("limitations", []) if value not in _SCORER_ONLY_LIMITATIONS]
    limitations.extend(gate.get("limitations", []))
    if execution_mode != "production_classifier":
        limitations.append("injected_classifier_execution_for_test_or_simulation")
    limitations = sorted(set(limitations))
    completed_at = _now()
    run_identity = {
        "schema_version": CLASSIFIER_VALIDATION_RUN_SCHEMA_VERSION,
        "dataset": dataset,
        "identity": identity,
        "scorer_report": scorer_report,
        "gate": gate,
        "execution_mode": execution_mode,
    }
    validation_run_id = "validation_run_" + _sha(run_identity)[:32]
    return {
        "schema_version": CLASSIFIER_VALIDATION_RUN_SCHEMA_VERSION,
        "validation_run_id": validation_run_id,
        **dataset,
        **identity,
        "gold_item_n": scorer_report["gold_item_n"],
        "prediction_item_n": scorer_report["prediction_item_n"],
        "matched_prediction_n": scorer_report["matched_prediction_n"],
        "evaluation_coverage": scorer_report["evaluation_coverage"],
        "topic_metrics": copy.deepcopy(scorer_report["topic_metrics"]),
        "issue_metrics": copy.deepcopy(scorer_report.get("issue_metrics")),
        "request_metrics": copy.deepcopy(scorer_report.get("request_metrics")),
        "gate_policy_version": gate["policy_version"],
        "gate_status": gate["status"],
        "gate_reasons": sorted(set(gate["failures"])),
        "gate_limitations": sorted(set(gate["limitations"])),
        "limitations": limitations,
        "execution_mode": execution_mode,
        "scorer_report": scorer_report,
        "created_at": completed_at,
        "completed_at": completed_at,
    }


__all__ = [
    "CLASSIFIER_VALIDATION_RUN_SCHEMA_VERSION",
    "VALIDATION_DATASET_SCHEMA_VERSION",
    "classifier_identity",
    "normalized_validation_items",
    "production_classifier",
    "run_classifier_validation",
    "validation_dataset_identity",
]
