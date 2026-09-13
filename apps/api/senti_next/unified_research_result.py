"""Canonical product-domain result for one Research Run.

``quantitative`` is the exact Research Core report already produced by the
run.  This module only composes persisted facts; it never recomputes Research
Core or semantic measurements.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

UNIFIED_RESEARCH_RESULT_SCHEMA_VERSION = "unified-research-result-v1"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def build_unified_research_result(
    *,
    run_id: str,
    app_id: int,
    research_report: Mapping[str, Any],
    semantic_measurement_result: Mapping[str, Any] | None,
    semantic_status: Mapping[str, Any] | None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose a unified result for both semantic and quantitative-only runs."""
    semantic = dict(semantic_measurement_result) if semantic_measurement_result is not None else None
    status = dict(semantic_status or {})
    semantic_provenance = (semantic or {}).get("provenance") or {}
    population_provenance = dict((metadata or {}).get("population_provenance") or {})
    provenance = {
        "run_id": str(run_id),
        "app_id": int(app_id),
        "research_population": population_provenance,
        "measurement_bundle_id": semantic_provenance.get("measurement_bundle_id") or status.get("measurement_bundle_id"),
        "classification_materialization_id": semantic_provenance.get("classification_materialization_id") or status.get("classification_materialization_id"),
        "taxonomy_snapshot_id": semantic_provenance.get("taxonomy_snapshot_id") or status.get("taxonomy_snapshot_id"),
        "taxonomy_version": semantic_provenance.get("taxonomy_version") or status.get("taxonomy_version"),
        "taxonomy_fingerprint": semantic_provenance.get("taxonomy_fingerprint") or status.get("taxonomy_fingerprint"),
        "classifier_provider": semantic_provenance.get("classifier_provider") or status.get("provider"),
        "classifier_model_id": semantic_provenance.get("classifier_model_id") or status.get("model_id"),
        "classifier_prompt_version": semantic_provenance.get("classifier_prompt_version") or status.get("prompt_version"),
        "classifier_schema_version": semantic_provenance.get("classifier_schema_version") or status.get("schema_version"),
        "measurement_status": semantic_provenance.get("measurement_status") or status.get("measurement_status"),
        "validation_status": semantic_provenance.get("validation_status") or status.get("validation_status"),
        "semantic_measurement_result_fingerprint": (semantic or {}).get("semantic_measurement_result_fingerprint"),
    }
    limitations = list((semantic or {}).get("limitations") or [])
    if semantic is None and status.get("reason"):
        limitations.append(f"semantic_unavailable:{status['reason']}")
    result = {
        "schema_version": UNIFIED_RESEARCH_RESULT_SCHEMA_VERSION,
        "run_id": str(run_id),
        "app_id": int(app_id),
        "quantitative": dict(research_report),
        "semantic": semantic,
        "semantic_status": status,
        "provenance": provenance,
        "limitations": sorted(set(limitations)),
    }
    result["result_fingerprint"] = _sha(result)
    return result


__all__ = ["UNIFIED_RESEARCH_RESULT_SCHEMA_VERSION", "build_unified_research_result"]
