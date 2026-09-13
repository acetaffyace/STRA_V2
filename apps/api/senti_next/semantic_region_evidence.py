"""Deterministic evidence packages for Stage 3C region interpretation.

Evidence is built from a *completed* Stage 3B materialization.  It is a
bounded, immutable view of original review evidence and existing discovery
metadata; it never changes vectors, labels, Research Core, or Stage 2E rows.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .semantic_discovery import SemanticUnitRecord

EVIDENCE_SCHEMA_VERSION = "semantic-region-evidence-v1"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SemanticRegionEvidenceContract:
    """Versioned limits for the material supplied to an interpreter."""

    schema_version: str = EVIDENCE_SCHEMA_VERSION
    centroid_review_limit: int = 5
    centroid_unit_limit: int = 8
    max_units_per_review: int = 2
    boundary_review_limit: int = 2
    max_review_chars: int = 1600
    max_unit_chars: int = 800
    minimum_stability: str = "moderate"
    well_covered_action: str = "no_change"

    def validate(self) -> None:
        if self.schema_version != EVIDENCE_SCHEMA_VERSION:
            raise ValueError(f"unsupported evidence schema: {self.schema_version}")
        for name in ("centroid_review_limit", "centroid_unit_limit", "max_units_per_review", "boundary_review_limit", "max_review_chars", "max_unit_chars"):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.minimum_stability not in {"moderate", "stable"}:
            raise ValueError("minimum_stability must be moderate or stable")
        if self.well_covered_action != "no_change":
            raise ValueError("well_covered_action must be no_change")

    @property
    def fingerprint(self) -> str:
        self.validate()
        return _sha(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text_for_review(review_id: str, review_metadata: Mapping[str, Mapping[str, Any]] | None, fallback: str = "") -> str:
    row = (review_metadata or {}).get(str(review_id), {})
    for key in ("review", "review_text", "text", "content"):
        if row.get(key) is not None:
            return str(row[key])
    return fallback


def _truncate(value: str, limit: int) -> str:
    value = str(value or "")
    return value if len(value) <= limit else value[: max(0, limit - 1)] + "…"


def _ordered_units(region: Mapping[str, Any], units: Sequence[SemanticUnitRecord]) -> list[SemanticUnitRecord]:
    wanted = set(str(item) for item in region.get("semantic_unit_ids") or [])
    return [unit for unit in units if unit.unit_id in wanted]


def _centroid(units: Sequence[SemanticUnitRecord]) -> np.ndarray | None:
    if not units:
        return None
    value = np.mean(np.stack([np.asarray(unit.vector, dtype=np.float32) for unit in units]), axis=0)
    norm = float(np.linalg.norm(value))
    return None if norm == 0 else (value / norm).astype(np.float32)


def _review_ids_by_region(region: Mapping[str, Any]) -> list[str]:
    return sorted({str(value) for value in region.get("review_ids") or []})


def _is_stable(region: Mapping[str, Any], contract: SemanticRegionEvidenceContract) -> bool:
    value = str(region.get("stability") or "unstable")
    if contract.minimum_stability == "stable":
        return value == "stable"
    return value in {"stable", "moderate"}


def build_semantic_region_evidence(
    materialization: Mapping[str, Any],
    region: Mapping[str, Any],
    *,
    units: Sequence[SemanticUnitRecord] = (),
    review_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    contract: SemanticRegionEvidenceContract | None = None,
) -> dict[str, Any]:
    """Build one deterministic, bounded evidence package.

    The function accepts plain mappings so tests and offline tooling can build
    evidence without a database connection.  Original review text is used
    when supplied; semantic unit text is explicitly marked as derived fallback.
    """
    active = contract or SemanticRegionEvidenceContract()
    active.validate()
    materialization_id = str(materialization.get("materialization_id") or "")
    if not materialization_id:
        raise ValueError("completed materialization_id is required")
    region_id = str(region.get("region_id") or "")
    if not region_id:
        raise ValueError("region_id is required")
    if str(materialization.get("status") or "completed") not in {"completed", ""}:
        raise ValueError("materialization must be completed")
    member_reviews = _review_ids_by_region(region)
    member_units = _ordered_units(region, units)
    centroid = _centroid(member_units)
    scored_units: list[tuple[float, SemanticUnitRecord]] = []
    if centroid is not None:
        scored_units = sorted(((float(np.dot(unit.vector, centroid)), unit) for unit in member_units), key=lambda item: (-item[0], item[1].unit_id))
    selected_units: list[dict[str, Any]] = []
    review_unit_counts: dict[str, int] = {}
    for score, unit in scored_units:
        if len(selected_units) >= active.centroid_unit_limit:
            break
        count = review_unit_counts.get(unit.review_id, 0)
        if count >= active.max_units_per_review:
            continue
        review_unit_counts[unit.review_id] = count + 1
        selected_units.append({
            "evidence_id": f"unit:{unit.unit_id}",
            "semantic_unit_id": unit.unit_id,
            "review_id": unit.review_id,
            "unit_index": unit.unit_index,
            "similarity_to_centroid": score,
            "text": _truncate(unit.semantic_text, active.max_unit_chars),
            "text_source": "derived_semantic_unit",
            "semantic_text_hash": unit.semantic_text_hash,
        })
    representative_ids = [str(value) for value in (region.get("representative_review_ids") or []) if str(value) in member_reviews]
    representative_ids = representative_ids[: active.centroid_review_limit]
    representatives = []
    unit_fallback = {unit.review_id: unit.semantic_text for unit in member_units}
    for review_id in representative_ids:
        text = _text_for_review(review_id, review_metadata, unit_fallback.get(review_id, ""))
        representatives.append({"evidence_id": f"review:{review_id}", "review_id": review_id, "text": _truncate(text, active.max_review_chars), "text_source": "original_review" if review_metadata and review_id in review_metadata else "derived_semantic_unit_fallback", "reason": "centroid_proximity"})
    boundary = []
    if str(region.get("discovery_type")) == "dense_region":
        strengths = region.get("membership_strength") or {}
        boundary_ids = sorted(member_reviews, key=lambda rid: (float(strengths.get(rid, 0.0)), rid))[: active.boundary_review_limit]
        for review_id in boundary_ids:
            text = _text_for_review(review_id, review_metadata, unit_fallback.get(review_id, ""))
            boundary.append({"evidence_id": f"boundary:{review_id}", "review_id": review_id, "membership_strength": strengths.get(review_id), "text": _truncate(text, active.max_review_chars), "text_source": "original_review" if review_metadata and review_id in review_metadata else "derived_semantic_unit_fallback"})
    evidence = {
        "representative_reviews": representatives,
        "semantic_units": selected_units,
        "boundary_reviews": boundary,
    }
    taxonomy_audit = dict(region.get("taxonomy_audit") or {})
    package = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "materialization_id": materialization_id,
        "region_id": region_id,
        "discovery_type": region.get("discovery_type"),
        "discovery_support_n": int(region.get("support_reviews") or 0),
        "discovery_support_unit_n": int(region.get("support_units") or 0),
        "population_n": int(materialization.get("population_n") or 0),
        "discovery_support_share": (float(region.get("support_reviews")) / int(materialization.get("population_n"))) if materialization.get("population_n") else None,
        "cohesion": region.get("cohesion"),
        "stability": region.get("stability"),
        "stability_score": region.get("stability_score"),
        "taxonomy_coverage_status": region.get("taxonomy_coverage_status", "unavailable"),
        "taxonomy_audit": taxonomy_audit,
        "languages": region.get("languages") or {},
        "time_distribution": region.get("time_distribution") or {},
        "stage2e_overlap": region.get("stage2e_overlap") or {},
        "evidence": evidence,
        "limitations": {
            "support_is_not_prevalence": True,
            "region_is_not_validated_topic": True,
            "semantic_similarity_is_not_coordinated_expression": True,
            "review_text_is_untrusted": True,
        },
        "contract": active.to_dict(),
    }
    package["small_support_warning"] = bool(str(region.get("discovery_type")) == "rare_region" and int(region.get("support_reviews") or 0) < 5)
    package["evidence_contract_fingerprint"] = active.fingerprint
    package["evidence_package_id"] = _sha({"materialization_id": materialization_id, "region_id": region_id, "evidence_contract_fingerprint": active.fingerprint})
    package["evidence_fingerprint"] = _sha(package)
    package["eligible_for_interpretation"] = bool(_is_stable(region, active) and str(region.get("discovery_type")) in {"dense_region", "rare_region"})
    return package


def build_evidence_packages(materialization: Mapping[str, Any], *, units: Sequence[SemanticUnitRecord] = (), review_metadata: Mapping[str, Mapping[str, Any]] | None = None, contract: SemanticRegionEvidenceContract | None = None, region_ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
    wanted = set(str(value) for value in region_ids) if region_ids is not None else None
    regions = [region for region in materialization.get("regions", []) if wanted is None or str(region.get("region_id")) in wanted]
    return [build_semantic_region_evidence(materialization, region, units=units, review_metadata=review_metadata, contract=contract) for region in sorted(regions, key=lambda item: str(item.get("region_id")))]


# Concise aliases used by CLI/tests.
build_region_evidence = build_semantic_region_evidence
build_semantic_region_evidence_packages = build_evidence_packages
EvidenceContract = SemanticRegionEvidenceContract
