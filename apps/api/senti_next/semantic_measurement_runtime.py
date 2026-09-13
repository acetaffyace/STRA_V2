"""Single production entry point for resolving the active measurement contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .classifier_taxonomy import ClassifierTaxonomyContract, baseline_classifier_taxonomy, load_classifier_taxonomy
from .classifier_validation_runtime import classifier_identity
from .semantic_measurement_bundle import (
    VALIDATED,
    activate_measurement_bundle,
    bootstrap_baseline_measurement_bundle,
    get_active_measurement_bundle,
    get_validation_run,
    list_measurement_bundles,
)


@dataclass(frozen=True)
class ResolvedMeasurementContext:
    bundle: dict[str, Any] | None
    bundle_id: str | None
    measurement_status: str | None
    validation_run_id: str | None
    validation_status: str | None
    taxonomy_contract: ClassifierTaxonomyContract | None
    taxonomy_snapshot_id: str | None
    taxonomy_version: str | None
    taxonomy_fingerprint: str | None
    classifier_provider: str | None
    classifier_model_id: str | None
    classifier_prompt_version: str | None
    classifier_schema_version: str | None
    limitations: tuple[str, ...]
    ready: bool
    reason: str | None = None


def _unavailable(reason: str, *, bundle: dict[str, Any] | None = None, limitations: list[str] | None = None) -> ResolvedMeasurementContext:
    return ResolvedMeasurementContext(
        bundle=bundle,
        bundle_id=bundle.get("bundle_id") if bundle else None,
        measurement_status=bundle.get("measurement_status") if bundle else None,
        validation_run_id=bundle.get("validation_run_id") if bundle else None,
        validation_status=bundle.get("validation_status") if bundle else None,
        taxonomy_contract=None,
        taxonomy_snapshot_id=bundle.get("taxonomy_snapshot_id") if bundle else None,
        taxonomy_version=bundle.get("taxonomy_version") if bundle else None,
        taxonomy_fingerprint=bundle.get("taxonomy_fingerprint") if bundle else None,
        classifier_provider=bundle.get("classifier_provider") if bundle else None,
        classifier_model_id=bundle.get("classifier_model_id") if bundle else None,
        classifier_prompt_version=bundle.get("classifier_prompt_version") if bundle else None,
        classifier_schema_version=bundle.get("classifier_schema_version") if bundle else None,
        limitations=tuple(limitations or (bundle or {}).get("limitations") or ()),
        ready=False,
        reason=reason,
    )


def _ready(bundle: dict[str, Any], contract: ClassifierTaxonomyContract) -> ResolvedMeasurementContext:
    return ResolvedMeasurementContext(
        bundle=bundle,
        bundle_id=str(bundle["bundle_id"]),
        measurement_status=str(bundle["measurement_status"]),
        validation_run_id=bundle.get("validation_run_id"),
        validation_status=bundle.get("validation_status"),
        taxonomy_contract=contract,
        taxonomy_snapshot_id=contract.snapshot_id,
        taxonomy_version=contract.taxonomy_version,
        taxonomy_fingerprint=contract.taxonomy_fingerprint,
        classifier_provider=str(bundle["classifier_provider"]),
        classifier_model_id=str(bundle["classifier_model_id"]),
        classifier_prompt_version=str(bundle["classifier_prompt_version"]),
        classifier_schema_version=str(bundle["classifier_schema_version"]),
        limitations=tuple(bundle.get("limitations") or ()),
        ready=True,
        reason=None,
    )


def _load_exact_contract(bundle: dict[str, Any]) -> ClassifierTaxonomyContract:
    if str(bundle.get("taxonomy_version")) == baseline_classifier_taxonomy().taxonomy_version:
        contract = baseline_classifier_taxonomy()
    else:
        contract = load_classifier_taxonomy(snapshot_id=str(bundle.get("taxonomy_snapshot_id") or ""))
    contract.validate()
    if (
        contract.snapshot_id != str(bundle.get("taxonomy_snapshot_id"))
        or contract.taxonomy_version != str(bundle.get("taxonomy_version"))
        or contract.taxonomy_fingerprint != str(bundle.get("taxonomy_fingerprint"))
    ):
        raise ValueError("taxonomy_contract_mismatch")
    return contract


def _runtime_identity(contract: ClassifierTaxonomyContract) -> dict[str, Any]:
    return classifier_identity(contract)


def resolve_measurement_context() -> ResolvedMeasurementContext:
    """Resolve and validate the exact active bundle for Production Analyze."""
    bundles = list_measurement_bundles()
    bundle = get_active_measurement_bundle()
    if not bundles:
        bundle = bootstrap_baseline_measurement_bundle()
        bundle = activate_measurement_bundle(
            bundle["bundle_id"], operator="system", reason="initial_product_bootstrap"
        )
    elif bundle is None:
        return _unavailable("no_active_measurement_bundle")

    try:
        contract = _load_exact_contract(bundle)
    except Exception:
        return _unavailable("taxonomy_contract_mismatch", bundle=bundle)

    runtime = _runtime_identity(contract)
    for field in (
        "classifier_provider",
        "classifier_model_id",
        "classifier_prompt_version",
        "classifier_schema_version",
    ):
        if str(bundle.get(field) or "") != str(runtime.get(field) or ""):
            return _unavailable("measurement_runtime_identity_mismatch", bundle=bundle)

    if bundle.get("measurement_status") == VALIDATED:
        validation_run = get_validation_run(str(bundle.get("validation_run_id") or ""))
        if not validation_run:
            return _unavailable("validated_bundle_integrity_failure", bundle=bundle)
        if (
            validation_run.get("gate_status") != "PASS"
            or validation_run.get("execution_mode") != "production_classifier"
            or not validation_run.get("actual_model_id")
            or not validation_run.get("execution_identity_fingerprint")
            or str(validation_run.get("taxonomy_snapshot_id")) != contract.snapshot_id
            or str(validation_run.get("taxonomy_version")) != contract.taxonomy_version
            or str(validation_run.get("taxonomy_fingerprint")) != contract.taxonomy_fingerprint
            or str(validation_run.get("actual_provider") or validation_run.get("classifier_provider")) != str(bundle.get("classifier_provider"))
            or str(validation_run.get("actual_model_id")) != str(bundle.get("classifier_model_id"))
            or str(validation_run.get("classifier_prompt_version")) != str(bundle.get("classifier_prompt_version"))
            or str(validation_run.get("classifier_schema_version")) != str(bundle.get("classifier_schema_version"))
        ):
            return _unavailable("validated_bundle_integrity_failure", bundle=bundle)

    return _ready(bundle, contract)


__all__ = ["ResolvedMeasurementContext", "resolve_measurement_context"]
