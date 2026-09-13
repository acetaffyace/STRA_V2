"""Runtime orchestration for real classifier validation.

The provider-free scorer remains in :mod:`classifier_validation`. This module
binds a gold dataset and taxonomy contract to the production classifier,
captures actual execution identity, and applies the versioned gate.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from .classifier_taxonomy import ClassifierTaxonomyContract, baseline_classifier_taxonomy
from .classifier_validation import evaluate_classifier_fixture
from .classifier_validation_policy import ClassifierValidationPolicy, evaluate_validation_gate

VALIDATION_DATASET_SCHEMA_VERSION = "classifier-validation-dataset-v1"
CLASSIFIER_VALIDATION_RUN_SCHEMA_VERSION = "classifier-validation-run-v2"
_SCORER_ONLY_LIMITATIONS = {"synthetic_or_offline_validation_only", "not_real_model_validation"}


@dataclass(frozen=True)
class ClassifierExecutionResult:
    """Internal result of one classifier execution, including actual identity."""

    predictions: Any
    execution_mode: str
    actual_model_id: str
    actual_provider: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None

    def validate(self) -> None:
        if self.execution_mode not in {"production_classifier", "injected_classifier"}:
            raise ValueError("classifier_execution_mode_invalid")
        if not str(self.actual_model_id).strip():
            raise ValueError("classifier_execution_actual_model_id_missing")


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
    """Return the stable benchmark identity projection."""
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


def _execute_production_classifier(
    items: Sequence[Mapping[str, Any]],
    *,
    taxonomy_contract: ClassifierTaxonomyContract,
) -> ClassifierExecutionResult:
    """Run the real production path and preserve its returned model identity."""
    from .llm import CLASSIFICATION_SCHEMA_VERSION, active_classifier_prompt_version, classify_reviews
    from .providers import get_active_config

    predictions, model_used = classify_reviews(list(items), taxonomy_contract=taxonomy_contract)
    result = ClassifierExecutionResult(
        predictions=predictions,
        execution_mode="production_classifier",
        actual_model_id=str(model_used or ""),
        actual_provider=str(get_active_config().get("provider") or "") or None,
        prompt_version=active_classifier_prompt_version(),
        schema_version=CLASSIFICATION_SCHEMA_VERSION,
    )
    result.validate()
    return result


def production_classifier(items: Sequence[Mapping[str, Any]], *, taxonomy_contract: ClassifierTaxonomyContract) -> ClassifierExecutionResult:
    """Compatibility wrapper returning the explicit production execution result."""
    return _execute_production_classifier(items, taxonomy_contract=taxonomy_contract)


def classifier_identity(
    contract: ClassifierTaxonomyContract,
    *,
    provider: str | None = None,
    model_id: str | None = None,
    prompt_version: str | None = None,
    schema_version: str | None = None,
) -> dict[str, Any]:
    """Resolve current requested identity for provisional bundle bootstrap."""
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


def _execution_identity(contract: ClassifierTaxonomyContract, execution: ClassifierExecutionResult) -> dict[str, Any]:
    from .llm import CLASSIFICATION_SCHEMA_VERSION, active_classifier_prompt_version

    execution.validate()
    prompt_version = execution.prompt_version or active_classifier_prompt_version()
    schema_version = execution.schema_version or CLASSIFICATION_SCHEMA_VERSION
    payload = {
        "execution_mode": execution.execution_mode,
        "actual_provider": execution.actual_provider,
        "actual_model_id": execution.actual_model_id,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "taxonomy_snapshot_id": contract.snapshot_id,
        "taxonomy_version": contract.taxonomy_version,
        "taxonomy_fingerprint": contract.taxonomy_fingerprint,
        "classifier_taxonomy_contract_fingerprint": contract.fingerprint,
    }
    return {
        "classifier_provider": execution.actual_provider or ("injected" if execution.execution_mode == "injected_classifier" else "unconfigured"),
        "classifier_model_id": execution.actual_model_id,
        "classifier_prompt_version": prompt_version,
        "classifier_schema_version": schema_version,
        "taxonomy_snapshot_id": contract.snapshot_id,
        "taxonomy_version": contract.taxonomy_version,
        "taxonomy_fingerprint": contract.taxonomy_fingerprint,
        "classifier_taxonomy_contract_fingerprint": contract.fingerprint,
        "execution_mode": execution.execution_mode,
        "actual_model_id": execution.actual_model_id,
        "actual_provider": execution.actual_provider,
        "execution_identity_fingerprint": _sha(payload),
    }


def run_classifier_validation(
    gold_items: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    taxonomy_contract: ClassifierTaxonomyContract | None = None,
    classifier: Callable[..., Any] | None = None,
    validation_dataset_id: str | None = None,
    language_scope: str | None = None,
    provider: str | None = None,
    model_id: str | None = None,
    prompt_version: str | None = None,
    schema_version: str | None = None,
    injected_classifier_identity: Mapping[str, Any] | None = None,
    policy: ClassifierValidationPolicy | None = None,
) -> dict[str, Any]:
    """Run validation; only the no-callback path can yield production provenance."""
    contract = taxonomy_contract or baseline_classifier_taxonomy()
    contract.validate()
    items = [dict(gold_items)] if isinstance(gold_items, Mapping) else [dict(item) for item in gold_items]
    dataset = validation_dataset_identity(items, validation_dataset_id=validation_dataset_id, language_scope=language_scope)
    policy = policy or ClassifierValidationPolicy()

    if classifier is None:
        if any(value is not None for value in (provider, model_id, prompt_version, schema_version, injected_classifier_identity)):
            raise ValueError("production_identity_override_not_allowed")
        execution = _execute_production_classifier(items, taxonomy_contract=contract)
    else:
        declared = dict(injected_classifier_identity or {})
        actual_model_id = declared.get("actual_model_id") or model_id
        if not actual_model_id:
            raise ValueError("injected_classifier_identity_required")
        execution_value = classifier(items, taxonomy_contract=contract)
        predictions = execution_value.predictions if isinstance(execution_value, ClassifierExecutionResult) else execution_value
        execution = ClassifierExecutionResult(
            predictions=predictions,
            execution_mode="injected_classifier",
            actual_model_id=str(actual_model_id),
            actual_provider=str(declared.get("actual_provider") or provider or "injected"),
            prompt_version=str(declared.get("prompt_version") or prompt_version or "injected-test-prompt"),
            schema_version=str(declared.get("schema_version") or schema_version or "injected-test-schema"),
        )
        execution.validate()

    identity = _execution_identity(contract, execution)
    scorer_report = evaluate_classifier_fixture(
        items,
        execution.predictions,
        taxonomy_contract=contract,
        topic_support_sufficient=policy.sufficient_topic_support,
        topic_support_limited=policy.limited_topic_support,
    )
    gate = evaluate_validation_gate(scorer_report, policy=policy)
    limitations = [value for value in scorer_report.get("limitations", []) if value not in _SCORER_ONLY_LIMITATIONS]
    limitations.extend(gate.get("limitations", []))
    if execution.execution_mode != "production_classifier":
        limitations.append("injected_classifier_execution_for_test_or_simulation")
    limitations = sorted(set(limitations))
    completed_at = _now()
    run_identity = {
        "schema_version": CLASSIFIER_VALIDATION_RUN_SCHEMA_VERSION,
        "dataset": dataset,
        "identity": identity,
        "scorer_report": scorer_report,
        "gate": gate,
        "gate_policy": gate["policy"],
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
        "taxonomy_topic_n": scorer_report["taxonomy_topic_n"],
        "gold_covered_topic_n": scorer_report["gold_covered_topic_n"],
        "gold_topic_coverage_rate": scorer_report["gold_topic_coverage_rate"],
        "zero_gold_support_topic_n": scorer_report["zero_gold_support_topic_n"],
        "zero_gold_support_topics": scorer_report["zero_gold_support_topics"],
        "topic_support_status": scorer_report["topic_support_status"],
        "topic_metrics": copy.deepcopy(scorer_report["topic_metrics"]),
        "issue_metrics": copy.deepcopy(scorer_report.get("issue_metrics")),
        "request_metrics": copy.deepcopy(scorer_report.get("request_metrics")),
        "gate_policy_version": gate["policy_version"],
        "gate_policy": copy.deepcopy(gate["policy"]),
        "gate_status": gate["status"],
        "gate_reasons": sorted(set(gate["failures"])),
        "gate_limitations": sorted(set(gate["limitations"])),
        "limitations": limitations,
        "scorer_report": scorer_report,
        "created_at": completed_at,
        "completed_at": completed_at,
    }


__all__ = [
    "CLASSIFIER_VALIDATION_RUN_SCHEMA_VERSION",
    "ClassifierExecutionResult",
    "VALIDATION_DATASET_SCHEMA_VERSION",
    "classifier_identity",
    "normalized_validation_items",
    "production_classifier",
    "run_classifier_validation",
    "validation_dataset_identity",
]
