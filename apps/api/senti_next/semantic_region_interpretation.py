"""Stage 3C bounded semantic-region interpretation.

This layer is intentionally downstream of a completed Stage 3B
materialization.  It produces reviewable candidate interpretations only; it
does not mutate taxonomy, labels, Research Core, Stage 2E, or the Stage 3A/B
index.  Existing :class:`LLMProvider` instances are the only provider API
used here.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Mapping, Sequence

from sqlalchemy import text

from . import db
from .providers.base import LLMProvider
from .semantic_discovery_storage import load_semantic_discovery_materialization, load_semantic_index_unit_records
from .semantic_region_evidence import SemanticRegionEvidenceContract, build_evidence_packages, build_semantic_region_evidence
from .semantic_region_interpretation_schema import (
    INTERPRETER_PROMPT_VERSION,
    INTERPRETATION_SCHEMA_VERSION,
    SemanticRegionInterpretationContract,
    build_interpretation_prompt,
    output_schema,
    taxonomy_labels_from_evidence,
    validate_interpretation_output,
)

INTERPRETATION_REPORT_VERSION = "semantic-region-interpretation-report-v1"
_ERRORS = {"materialization_not_found", "materialization_not_completed", "region_not_found", "evidence_build_failed", "llm_budget_exceeded", "provider_not_configured", "interpretation_failed", "invalid_structured_output", "invalid_evidence_reference", "invalid_parent_label", "persistence_failed"}


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sanitize_error(value: Any) -> str:
    import re
    text_value = str(value)
    for pattern in (r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+", r"(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+", r"(?i)(https?://)([^/@\s]+):([^/@\s]+)@"):
        text_value = re.sub(pattern, r"\1[REDACTED]", text_value)
    return text_value[:500]


def _provider_identity(provider: LLMProvider | None) -> tuple[str | None, str | None]:
    if provider is None:
        return None, None
    name = str(getattr(provider, "name", "") or "") or None
    try:
        model_id = str(provider.model_id())
    except Exception:
        model_id = str(getattr(provider, "model", "") or "") or None
    return name, model_id


def _review_metadata_from_db(review_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    wanted = [str(value) for value in review_ids]
    if not wanted:
        return {}
    placeholders = ",".join(f":review_{index}" for index in range(len(wanted)))
    with db.get_connection() as conn:
        rows = conn.execute(text(f"SELECT review_id, data FROM reviews WHERE review_id IN ({placeholders})"), {f"review_{index}": value for index, value in enumerate(wanted)}).mappings().all()
    metadata: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            payload = json.loads(row["data"] or "{}")
        except Exception:
            payload = {}
        if isinstance(payload, Mapping):
            metadata[str(row["review_id"])] = dict(payload)
    return metadata


def _persist_evidence(package: Mapping[str, Any]) -> None:
    payload = json.dumps(dict(package), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    contract = json.dumps(package.get("contract") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    with db.get_connection() as conn:
        conn.execute(text("""
            INSERT INTO semantic_region_evidence_packages
            (evidence_package_id, materialization_id, region_id, evidence_schema_version,
             evidence_contract_json, evidence_contract_fingerprint, evidence_fingerprint, evidence_json)
            VALUES (:id, :materialization_id, :region_id, :schema, :contract, :contract_fp, :evidence_fp, :payload)
            ON CONFLICT(materialization_id, region_id, evidence_contract_fingerprint) DO UPDATE SET
              evidence_package_id=excluded.evidence_package_id,
              evidence_fingerprint=excluded.evidence_fingerprint,
              evidence_json=excluded.evidence_json
        """), {"id": package["evidence_package_id"], "materialization_id": package["materialization_id"], "region_id": package["region_id"], "schema": package["schema_version"], "contract": contract, "contract_fp": package["evidence_contract_fingerprint"], "evidence_fp": package["evidence_fingerprint"], "payload": payload})


def load_semantic_region_evidence(evidence_package_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        value = conn.execute(text("SELECT evidence_json FROM semantic_region_evidence_packages WHERE evidence_package_id=:id"), {"id": evidence_package_id}).scalar()
    return json.loads(value) if value else None


def load_semantic_region_interpretation(interpretation_run_id: str) -> dict[str, Any] | None:
    """Load an immutable interpretation report without re-running a provider."""
    with db.get_connection() as conn:
        value = conn.execute(text("SELECT report_json FROM semantic_region_interpretation_runs WHERE interpretation_run_id=:id"), {"id": interpretation_run_id}).scalar()
    return json.loads(value) if value else None


def load_semantic_taxonomy_candidate(candidate_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        value = conn.execute(text("SELECT candidate_json FROM semantic_taxonomy_candidates WHERE candidate_id=:id"), {"id": candidate_id}).scalar()
    return json.loads(value) if value else None


def _load_cached_run(run_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        value = conn.execute(text("SELECT status, report_json FROM semantic_region_interpretation_runs WHERE interpretation_run_id=:id"), {"id": run_id}).first()
    if not value or value[0] != "completed" or not value[1]:
        return None
    return json.loads(value[1])


def _persist_run(report: Mapping[str, Any], *, interpreter: SemanticRegionInterpretationContract, provider_name: str | None, model_id: str | None, evidence_contract_fingerprint: str, status: str, error: str | None = None) -> None:
    report_json = json.dumps(dict(report), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    with db.get_connection() as conn:
        conn.execute(text("""
            INSERT INTO semantic_region_interpretation_runs
            (interpretation_run_id, materialization_id, evidence_contract_fingerprint,
             interpreter_contract_json, interpreter_contract_fingerprint, provider_name,
             model_id, prompt_version, schema_version, region_n, eligible_llm_region_n,
             actual_llm_call_n, candidate_n, deferred_n, status, report_json, completed_at, error)
            VALUES (:id, :materialization_id, :evidence_fp, :contract_json, :contract_fp,
                    :provider_name, :model_id, :prompt_version, :schema, :region_n,
                    :eligible, :calls, :candidate_n, :deferred_n, :status, :report_json,
                    CASE WHEN :status IN ('completed','partial','failed') THEN datetime('now') END, :error)
            ON CONFLICT(interpretation_run_id) DO UPDATE SET
              status=excluded.status, report_json=excluded.report_json,
              actual_llm_call_n=excluded.actual_llm_call_n,
              candidate_n=excluded.candidate_n, deferred_n=excluded.deferred_n,
              completed_at=excluded.completed_at, error=excluded.error
        """), {"id": report["interpretation_run_id"], "materialization_id": report["materialization_id"], "evidence_fp": evidence_contract_fingerprint, "contract_json": json.dumps(interpreter.to_dict(), sort_keys=True, separators=(",", ":")), "contract_fp": interpreter.fingerprint, "provider_name": provider_name, "model_id": model_id, "prompt_version": interpreter.prompt_version, "schema": interpreter.schema_version, "region_n": report["region_n"], "eligible": report["eligible_llm_region_n"], "calls": report["actual_llm_call_n"], "candidate_n": report["candidate_n"], "deferred_n": report["deferred_n"], "status": status, "report_json": report_json, "error": error})
        conn.execute(text("DELETE FROM semantic_taxonomy_candidates WHERE interpretation_run_id=:id"), {"id": report["interpretation_run_id"]})
        for candidate in report.get("regions", []):
            conn.execute(text("""
                INSERT INTO semantic_taxonomy_candidates
                (candidate_id, interpretation_run_id, evidence_package_id, region_id,
                 interpretation_status, recommendation, candidate_name,
                 candidate_description, evidence_sufficiency, candidate_json)
                VALUES (:candidate_id, :run_id, :evidence_id, :region_id, :status,
                        :recommendation, :name, :description, :sufficiency, :payload)
            """), {"candidate_id": candidate["candidate_id"], "run_id": report["interpretation_run_id"], "evidence_id": candidate["evidence_package_id"], "region_id": candidate["region_id"], "status": candidate["interpretation_status"], "recommendation": candidate["recommendation"], "name": candidate.get("candidate_name"), "description": candidate.get("candidate_description"), "sufficiency": candidate.get("evidence_sufficiency", "insufficient"), "payload": json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)})


def _candidate_id(run_id: str, region_id: str) -> str:
    return _sha({"interpretation_run_id": run_id, "region_id": region_id})


def _taxonomy_parent(evidence: Mapping[str, Any]) -> str | None:
    distribution = (evidence.get("taxonomy_audit") or {}).get("primary_label_distribution") or {}
    return sorted(((int(value), str(key)) for key, value in distribution.items()), key=lambda item: (-item[0], item[1]))[0][1] if distribution else None


def _deterministic_candidate(evidence: Mapping[str, Any], run_id: str) -> dict[str, Any] | None:
    region_id = str(evidence["region_id"])
    dtype = str(evidence.get("discovery_type") or "")
    stability = str(evidence.get("stability") or "unstable")
    status = str(evidence.get("taxonomy_coverage_status") or "unavailable")
    parent = _taxonomy_parent(evidence)
    if dtype == "outlier":
        recommendation, reason = "defer_insufficient_evidence", "deferred_outlier"
        sufficiency = "insufficient"
    elif stability == "unstable":
        recommendation, reason = "defer_insufficient_evidence", "deferred_unstable"
        sufficiency = "insufficient"
    elif status == "well_covered" and parent:
        recommendation, reason = "no_change", "covered_no_change"
        sufficiency = "sufficient"
    else:
        return None
    return {"candidate_id": _candidate_id(run_id, region_id), "region_id": region_id, "evidence_package_id": evidence["evidence_package_id"], "interpretation_status": reason, "recommendation": recommendation, "candidate_name": None, "candidate_description": None, "evidence_sufficiency": sufficiency, "proposed_parent_labels": [parent] if parent else [], "supporting_evidence_ids": [], "conflicting_evidence_ids": [], "evidence_summary": reason}


def _report_identity(materialization: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]], contract: SemanticRegionInterpretationContract, provider_name: str | None, model_id: str | None) -> str:
    return _sha({"materialization_id": materialization["materialization_id"], "evidence_package_ids": [item["evidence_package_id"] for item in evidence], "contract": contract.fingerprint, "provider_name": provider_name, "model_id": model_id, "prompt_version": contract.prompt_version})


def build_semantic_region_interpretation(
    materialization_id: str | Mapping[str, Any],
    *,
    provider: LLMProvider | None = None,
    contract: SemanticRegionInterpretationContract | None = None,
    evidence_contract: SemanticRegionEvidenceContract | None = None,
    region_ids: Sequence[str] | None = None,
    review_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    taxonomy_labels: Mapping[str, Any] | None = None,
    units=None,
    dry_run_evidence: bool = False,
    max_llm_calls: int | None = None,
) -> dict[str, Any]:
    """Interpret completed Stage 3B regions with a bounded provider budget."""
    interpreter = contract or SemanticRegionInterpretationContract()
    if max_llm_calls is not None:
        interpreter = SemanticRegionInterpretationContract(**{**interpreter.to_dict(), "max_llm_calls": int(max_llm_calls)})
    interpreter.validate()
    materialization = dict(materialization_id) if isinstance(materialization_id, Mapping) else load_semantic_discovery_materialization(materialization_id)
    if not materialization:
        raise ValueError("materialization_not_found")
    if materialization.get("status") not in (None, "", "completed"):
        raise ValueError("materialization_not_completed")
    if not materialization.get("materialization_id") or materialization.get("context_fingerprint") is None:
        raise ValueError("materialization_not_completed")
    resolved_materialization_id = str(materialization.get("materialization_id") or materialization_id)
    region_filter = set(str(value) for value in region_ids) if region_ids is not None else None
    if units is None:
        units, _index = load_semantic_index_unit_records(str(materialization["semantic_index_id"]))
    if review_metadata is None:
        review_metadata = _review_metadata_from_db([review_id for region in materialization.get("regions", []) for review_id in region.get("review_ids", [])])
    try:
        packages = build_evidence_packages(materialization, units=units, review_metadata=review_metadata, contract=evidence_contract, region_ids=region_ids)
        if region_ids and not packages:
            raise ValueError("region_not_found")
        for package in packages:
            _persist_evidence(package)
    except Exception as exc:
        raise ValueError("evidence_build_failed") from exc
    provider_name, model_id = _provider_identity(provider)
    run_id = _report_identity(materialization, packages, interpreter, provider_name, model_id)
    cached = _load_cached_run(run_id)
    if cached is not None:
        return cached
    eligible = [package for package in packages if package.get("eligible_for_interpretation")]
    limit = interpreter.max_llm_calls
    if len(eligible) > limit and not dry_run_evidence:
        report = {"schema_version": INTERPRETATION_REPORT_VERSION, "interpretation_run_id": run_id, "materialization_id": resolved_materialization_id, "status": "failed", "error": "llm_budget_exceeded", "region_n": len(packages), "eligible_llm_region_n": len(eligible), "actual_llm_call_n": 0, "candidate_n": 0, "deferred_n": 0, "regions": []}
        _persist_run(report, interpreter=interpreter, provider_name=provider_name, model_id=model_id, evidence_contract_fingerprint=packages[0]["evidence_contract_fingerprint"] if packages else (evidence_contract or SemanticRegionEvidenceContract()).fingerprint, status="failed", error="llm_budget_exceeded")
        raise ValueError("llm_budget_exceeded")
    if eligible and provider is None and not dry_run_evidence:
        report = {"schema_version": INTERPRETATION_REPORT_VERSION, "interpretation_run_id": run_id, "materialization_id": resolved_materialization_id, "status": "failed", "error": "provider_not_configured", "region_n": len(packages), "eligible_llm_region_n": len(eligible), "actual_llm_call_n": 0, "candidate_n": 0, "deferred_n": len(packages) - len(eligible), "regions": []}
        _persist_run(report, interpreter=interpreter, provider_name=None, model_id=None, evidence_contract_fingerprint=packages[0]["evidence_contract_fingerprint"] if packages else (evidence_contract or SemanticRegionEvidenceContract()).fingerprint, status="failed", error="provider_not_configured")
        raise ValueError("provider_not_configured")
    regions: list[dict[str, Any]] = []
    actual_calls = 0
    for package in packages:
        candidate = _deterministic_candidate(package, run_id)
        if candidate is None and package.get("eligible_for_interpretation") and not dry_run_evidence:
            actual_calls += 1
            try:
                raw = provider.generate_structured(build_interpretation_prompt(package, contract=interpreter), output_schema(), system="Interpret bounded evidence only; do not expose chain-of-thought.", temperature=0.0)  # type: ignore[union-attr]
                provided_labels: set[str] = set()
                for value in (taxonomy_labels or {}).values():
                    if isinstance(value, str):
                        provided_labels.add(value)
                    elif isinstance(value, Mapping):
                        payload = value.get("labels") or value.get("taxonomy_labels") or value.get("all_labels")
                        if isinstance(payload, str):
                            provided_labels.add(payload)
                        elif isinstance(payload, (list, tuple, set)):
                            provided_labels.update(str(item) for item in payload if item)
                    elif isinstance(value, (list, tuple, set)):
                        provided_labels.update(str(item) for item in value if item)
                labels = sorted(provided_labels) or taxonomy_labels_from_evidence(package)
                validated = validate_interpretation_output(raw, evidence_ids=[entry["evidence_id"] for group in (package["evidence"]["representative_reviews"], package["evidence"]["semantic_units"], package["evidence"]["boundary_reviews"]) for entry in group], taxonomy_labels=labels, contract=interpreter)
                candidate = {"candidate_id": _candidate_id(run_id, package["region_id"]), "region_id": package["region_id"], "evidence_package_id": package["evidence_package_id"], "interpretation_status": "interpreted", **validated}
            except ValueError as exc:
                reason = str(exc) if str(exc) in {"invalid_evidence_reference", "invalid_parent_label"} else "invalid_structured_output"
                candidate = {"candidate_id": _candidate_id(run_id, package["region_id"]), "region_id": package["region_id"], "evidence_package_id": package["evidence_package_id"], "interpretation_status": reason, "recommendation": "defer_insufficient_evidence", "candidate_name": None, "candidate_description": None, "evidence_sufficiency": "insufficient", "proposed_parent_labels": [], "supporting_evidence_ids": [], "conflicting_evidence_ids": [], "evidence_summary": _sanitize_error(exc)}
            except Exception as exc:
                candidate = {"candidate_id": _candidate_id(run_id, package["region_id"]), "region_id": package["region_id"], "evidence_package_id": package["evidence_package_id"], "interpretation_status": "interpretation_failed", "recommendation": "defer_insufficient_evidence", "candidate_name": None, "candidate_description": None, "evidence_sufficiency": "insufficient", "proposed_parent_labels": [], "supporting_evidence_ids": [], "conflicting_evidence_ids": [], "evidence_summary": _sanitize_error(exc)}
        if candidate is None:
            candidate = {"candidate_id": _candidate_id(run_id, package["region_id"]), "region_id": package["region_id"], "evidence_package_id": package["evidence_package_id"], "interpretation_status": "deferred", "recommendation": "defer_insufficient_evidence", "candidate_name": None, "candidate_description": None, "evidence_sufficiency": "insufficient", "proposed_parent_labels": [], "supporting_evidence_ids": [], "conflicting_evidence_ids": [], "evidence_summary": "not eligible for interpretation"}
        regions.append(candidate)
    candidate_n = sum(1 for item in regions if str(item.get("recommendation")) in {"candidate_child_topic", "candidate_new_topic", "taxonomy_boundary_review"})
    deferred_n = len(regions) - candidate_n
    status = "completed" if not any(item.get("interpretation_status") in {"interpretation_failed", "invalid_structured_output", "invalid_evidence_reference", "invalid_parent_label"} for item in regions) else "partial"
    report = {"schema_version": INTERPRETATION_REPORT_VERSION, "interpretation_run_id": run_id, "materialization_id": resolved_materialization_id, "research_run_id": materialization.get("research_run_id"), "population_fingerprint": materialization.get("population_fingerprint"), "semantic_index_fingerprint": materialization.get("semantic_index_fingerprint"), "evidence_contract": (evidence_contract or SemanticRegionEvidenceContract()).to_dict(), "interpreter_contract": interpreter.to_dict(), "provider_name": provider_name, "model_id": model_id, "prompt_version": INTERPRETER_PROMPT_VERSION, "region_n": len(packages), "eligible_llm_region_n": len(eligible), "actual_llm_call_n": actual_calls, "candidate_n": candidate_n, "deferred_n": deferred_n, "status": status, "regions": regions, "candidates": regions, "errors": sorted({str(item.get("interpretation_status")) for item in regions if str(item.get("interpretation_status")) in {"interpretation_failed", "invalid_structured_output", "invalid_evidence_reference", "invalid_parent_label"}}), "limitations": {"regions_are_candidates_not_validated_topics": True, "support_is_not_prevalence": True, "recommendation_is_not_sentiment": True, "taxonomy_is_not_mutated": True}}
    _persist_run(report, interpreter=interpreter, provider_name=provider_name, model_id=model_id, evidence_contract_fingerprint=packages[0]["evidence_contract_fingerprint"] if packages else (evidence_contract or SemanticRegionEvidenceContract()).fingerprint, status=status)
    return report


def record_semantic_taxonomy_candidate_decision(candidate_id: str, decision: str, *, target_existing_labels: Sequence[str] | None = None, review_note: str | None = None, reviewer: str | None = None) -> str:
    if decision not in {"approve", "reject", "defer", "request_revision"}:
        raise ValueError("invalid candidate decision")
    decision_id = _sha({"candidate_id": candidate_id, "decision": decision, "target_existing_labels": list(target_existing_labels or []), "review_note": review_note or "", "reviewer": reviewer or "", "nonce": uuid.uuid4().hex})
    with db.get_connection() as conn:
        exists = conn.execute(text("SELECT 1 FROM semantic_taxonomy_candidates WHERE candidate_id=:id"), {"id": candidate_id}).scalar()
        if not exists:
            raise ValueError("candidate_not_found")
        conn.execute(text("""
            INSERT INTO semantic_taxonomy_candidate_decisions
            (decision_id, candidate_id, decision, target_existing_labels_json, review_note, reviewer)
            VALUES (:decision_id, :candidate_id, :decision, :labels, :note, :reviewer)
        """), {"decision_id": decision_id, "candidate_id": candidate_id, "decision": decision, "labels": json.dumps(list(target_existing_labels or []), ensure_ascii=False, sort_keys=True), "note": (review_note or "")[:2000], "reviewer": (reviewer or "")[:200]})
    return decision_id


def load_latest_semantic_taxonomy_candidate_decision(candidate_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT decision_id, candidate_id, decision, target_existing_labels_json, review_note, reviewer, created_at FROM semantic_taxonomy_candidate_decisions WHERE candidate_id=:id ORDER BY created_at DESC, decision_id DESC LIMIT 1"), {"id": candidate_id}).mappings().first()
    if not row:
        return None
    result = dict(row)
    result["target_existing_labels"] = json.loads(result.pop("target_existing_labels_json") or "[]")
    return result


# Public aliases kept deliberately explicit for callers/tooling.
interpret_semantic_regions = build_semantic_region_interpretation
run_semantic_region_interpretation = build_semantic_region_interpretation
