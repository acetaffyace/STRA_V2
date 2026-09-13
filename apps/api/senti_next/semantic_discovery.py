"""Deterministic open-set discovery over the frozen Stage 3A index.

This module consumes vectors; it does not re-embed text, call an LLM, mutate
taxonomy labels, or write Research Core/Stage 2E data.  Discovery structures
are diagnostic objects, not prevalence, severity, sentiment, or causal claims.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence

import numpy as np


SEMANTIC_DISCOVERY_SCHEMA_VERSION = "semantic-discovery-contract-v1"
SEMANTIC_DISCOVERY_REPORT_VERSION = "semantic-discovery-report-v1"
TAXONOMY_AUDIT_VERSION = "taxonomy-audit-v1"
DISCOVERY_ALGORITHM_VERSION = "hdbscan-open-set-v1"
RARE_REGION_MIN_SIMILARITY = 0.78
OUTLIER_MAX_NEAREST_SIMILARITY = 0.40
STABILITY_STABLE_THRESHOLD = 0.80
STABILITY_MODERATE_THRESHOLD = 0.50


def _normalise(vector: np.ndarray) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(values))
    if norm == 0 or not np.isfinite(norm):
        raise ValueError("discovery vectors must be finite and non-zero")
    return (values / norm).astype(np.float32)


@dataclass(frozen=True)
class SemanticDiscoveryContract:
    schema_version: str = SEMANTIC_DISCOVERY_SCHEMA_VERSION
    algorithm: str = "hdbscan"
    min_cluster_size: int | None = None
    min_samples: int | None = None
    metric: str = "cosine"
    rare_region_max_size: int = 10
    neighbor_k: int = 5
    review_representation: str = "normalized_mean_unit"
    include_unit_level_audit: bool = True
    taxonomy_audit_version: str = TAXONOMY_AUDIT_VERSION

    def validate(self) -> None:
        if self.schema_version != SEMANTIC_DISCOVERY_SCHEMA_VERSION:
            raise ValueError(f"unsupported discovery schema: {self.schema_version}")
        if self.algorithm != "hdbscan":
            raise ValueError("Stage 3B baseline algorithm must be hdbscan")
        if self.min_cluster_size is not None and self.min_cluster_size <= 0:
            raise ValueError("min_cluster_size must be positive")
        if self.min_samples is not None and self.min_samples <= 0:
            raise ValueError("min_samples must be positive")
        if self.metric != "cosine":
            raise ValueError("only cosine discovery is supported")
        if self.rare_region_max_size < 2:
            raise ValueError("rare_region_max_size must be at least 2")
        if self.neighbor_k <= 0:
            raise ValueError("neighbor_k must be positive")
        if self.review_representation != "normalized_mean_unit":
            raise ValueError("unsupported review representation")

    def effective_min_cluster_size(self, population_n: int) -> int:
        self.validate()
        if self.min_cluster_size is not None:
            return min(max(2, self.min_cluster_size), max(2, population_n))
        if population_n < 200:
            value = max(5, math.ceil(population_n * 0.03))
        elif population_n <= 2000:
            value = max(8, math.ceil(population_n * 0.015))
        else:
            value = max(15, math.ceil(population_n * 0.005))
        return min(value, max(2, population_n))

    def sensitivity_min_cluster_sizes(self, population_n: int) -> tuple[int, ...]:
        effective = self.effective_min_cluster_size(population_n)
        values = {max(2, round(effective * factor)) for factor in (0.75, 1.0, 1.25)}
        return tuple(sorted(min(value, max(2, population_n)) for value in values))

    def to_dict(self, *, population_n: int | None = None) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "algorithm": self.algorithm,
            "requested_min_cluster_size": self.min_cluster_size,
            "min_samples": self.min_samples,
            "metric": self.metric,
            "rare_region_max_size": self.rare_region_max_size,
            "neighbor_k": self.neighbor_k,
            "review_representation": self.review_representation,
            "include_unit_level_audit": self.include_unit_level_audit,
            "taxonomy_audit_version": self.taxonomy_audit_version,
        }
        if population_n is not None:
            payload["population_n"] = population_n
            payload["effective_min_cluster_size"] = self.effective_min_cluster_size(population_n)
        return payload

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class SemanticUnitRecord:
    unit_id: str
    review_id: str
    unit_index: int
    vector: np.ndarray = field(repr=False, compare=False)
    semantic_text_hash: str
    semantic_text: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "vector", _normalise(self.vector))


class SemanticDiscoveryBackend(Protocol):
    identity: str

    def discover(
        self,
        vectors: np.ndarray,
        *,
        min_cluster_size: int,
        min_samples: int | None,
        metric: str,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return labels, membership probabilities, and outlier scores."""
        ...


class HDBSCANDiscoveryBackend:
    """Thin adapter so discovery logic is not coupled to hdbscan internals."""

    identity = DISCOVERY_ALGORITHM_VERSION

    def discover(self, vectors: np.ndarray, *, min_cluster_size: int, min_samples: int | None, metric: str):
        if len(vectors) < max(2, min_cluster_size):
            count = len(vectors)
            return np.full(count, -1, dtype=int), np.zeros(count), np.ones(count)
        try:
            import hdbscan
        except ImportError as exc:  # pragma: no cover - dependency is installed in production/CI
            raise RuntimeError("hdbscan is required for semantic discovery") from exc
        model = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric=metric,
            algorithm="generic" if metric == "cosine" else "best",
            prediction_data=False,
            core_dist_n_jobs=1,
        )
        model.fit(np.asarray(vectors, dtype=np.float64))
        return (
            np.asarray(model.labels_, dtype=int),
            np.asarray(getattr(model, "probabilities_", np.zeros(len(vectors))), dtype=float),
            np.asarray(getattr(model, "outlier_scores_", np.zeros(len(vectors))), dtype=float),
        )


def _review_vectors(units: Sequence[SemanticUnitRecord]) -> tuple[list[str], np.ndarray, dict[str, list[SemanticUnitRecord]]]:
    grouped: dict[str, list[SemanticUnitRecord]] = {}
    for unit in units:
        grouped.setdefault(unit.review_id, []).append(unit)
    review_ids = sorted(grouped)
    vectors = []
    for review_id in review_ids:
        vectors.append(_normalise(np.mean(np.stack([u.vector for u in grouped[review_id]]), axis=0)))
    return review_ids, np.stack(vectors) if vectors else np.empty((0, 0), dtype=np.float32), grouped


def _neighbour_metrics(vectors: np.ndarray, neighbor_k: int) -> dict[int, dict[str, float | None]]:
    metrics: dict[int, dict[str, float | None]] = {}
    if len(vectors) <= 1:
        return {0: {"nearest_neighbor_similarity": None, "mean_k_neighbor_similarity": None, "local_density": 0.0}} if len(vectors) else {}
    similarity = np.clip(vectors @ vectors.T, -1.0, 1.0)
    np.fill_diagonal(similarity, -1.0)
    for index in range(len(vectors)):
        values = np.sort(similarity[index])[::-1][: min(neighbor_k, len(vectors) - 1)]
        metrics[index] = {
            "nearest_neighbor_similarity": float(values[0]),
            "mean_k_neighbor_similarity": float(np.mean(values)),
            "local_density": float(np.mean(np.maximum(values, 0.0))),
        }
    return metrics


def _unit_audit(units: Sequence[SemanticUnitRecord], neighbor_k: int) -> dict[str, Any]:
    """Retain unit-level neighborhood evidence alongside review discovery.

    Review-level means are useful for clustering but can blur a long review's
    distinct topics.  This audit keeps every unit's local geometry available
    for later tail-topic and rare-region inspection without changing review
    membership or the Research denominator.
    """
    ordered = sorted(units, key=lambda unit: (unit.review_id, unit.unit_index, unit.unit_id))
    vectors = np.stack([unit.vector for unit in ordered]) if ordered else np.empty((0, 0), dtype=np.float32)
    metrics = _neighbour_metrics(vectors, neighbor_k)
    entries = []
    for index, unit in enumerate(ordered):
        neighborhood = metrics.get(index, {})
        nearest = neighborhood.get("nearest_neighbor_similarity")
        entries.append(
            {
                "semantic_unit_id": unit.unit_id,
                "review_id": unit.review_id,
                "unit_index": unit.unit_index,
                "semantic_text_hash": unit.semantic_text_hash,
                "neighborhood": neighborhood,
                "rare_neighborhood_candidate": nearest is not None and nearest >= RARE_REGION_MIN_SIMILARITY,
            }
        )
    return {
        "unit_n": len(ordered),
        "rare_neighborhood_candidate_n": sum(1 for entry in entries if entry["rare_neighborhood_candidate"]),
        "units": entries,
    }


def _components(ids: Sequence[str], vectors: np.ndarray, candidate_indices: set[int]) -> list[list[int]]:
    remaining = set(candidate_indices)
    similarity = vectors @ vectors.T if len(vectors) else np.empty((0, 0))
    result: list[list[int]] = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        component = [start]
        queue = [start]
        while queue:
            current = queue.pop()
            neighbours = sorted(index for index in remaining if similarity[current, index] >= RARE_REGION_MIN_SIMILARITY)
            for index in neighbours:
                remaining.remove(index)
                component.append(index)
                queue.append(index)
        result.append(sorted(component))
    return result


def _stable_region_id(discovery_type: str, review_ids: Sequence[str], contract: SemanticDiscoveryContract) -> str:
    value = json.dumps({"type": discovery_type, "review_ids": sorted(review_ids), "contract": contract.fingerprint}, sort_keys=True)
    return f"{discovery_type.replace('_', '-')}-{hashlib.sha256(value.encode()).hexdigest()[:12]}"


def _region_cohesion(indices: Sequence[int], vectors: np.ndarray) -> float | None:
    if not indices:
        return None
    centroid = _normalise(np.mean(vectors[list(indices)], axis=0))
    return float(np.mean(vectors[list(indices)] @ centroid))


def _distribution(values: Iterable[Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = "unknown" if value is None or value == "" else str(value)
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def _review_summary(review_ids: Sequence[str], metadata: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    rows = [metadata[review_id] for review_id in review_ids if review_id in metadata]
    recommendations = {"recommended_n": 0, "not_recommended_n": 0, "missing_n": 0}
    for row in rows:
        value = row.get("voted_up")
        if value is True:
            recommendations["recommended_n"] += 1
        elif value is False:
            recommendations["not_recommended_n"] += 1
        else:
            recommendations["missing_n"] += 1
    timestamps = [row.get("timestamp_created") for row in rows if row.get("timestamp_created") is not None]
    text_hashes = [str(row.get("semantic_text_hash") or "") for row in rows]
    unique_text_n = len(set(value for value in text_hashes if value))
    return {
        "languages": _distribution(row.get("language") for row in rows),
        "recommendation_distribution": recommendations,
        "time_distribution": {"first_timestamp": min(timestamps) if timestamps else None, "last_timestamp": max(timestamps) if timestamps else None},
        "raw_review_n": len(review_ids),
        "unique_text_n": unique_text_n,
        "duplicate_share": (1 - unique_text_n / len(review_ids)) if review_ids and unique_text_n else None,
    }


def _stability_label(score: float | None) -> str:
    if score is None:
        return "unstable"
    if score >= STABILITY_STABLE_THRESHOLD:
        return "stable"
    if score >= STABILITY_MODERATE_THRESHOLD:
        return "moderate"
    return "unstable"


def build_semantic_discovery(
    units: Sequence[SemanticUnitRecord],
    *,
    semantic_index_id: str,
    research_run_id: str,
    population_fingerprint: str,
    semantic_index_fingerprint: str,
    contract: SemanticDiscoveryContract | None = None,
    review_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    taxonomy_labels: Mapping[str, Any] | None = None,
    stage2e: Mapping[str, Any] | None = None,
    backend: SemanticDiscoveryBackend | None = None,
    population_n_override: int | None = None,
) -> dict[str, Any]:
    """Build a deterministic open-set report from existing Stage 3A vectors."""
    active_contract = contract or SemanticDiscoveryContract()
    active_contract.validate()
    ordered_units = sorted(units, key=lambda unit: (unit.review_id, unit.unit_index, unit.unit_id))
    review_ids, review_vectors, grouped = _review_vectors(ordered_units)
    population_n = population_n_override if population_n_override is not None else (len(review_metadata) if review_metadata is not None else len(review_ids))
    if population_n < len(review_ids):
        raise ValueError("population_n cannot be smaller than indexed review count")
    active_backend = backend or HDBSCANDiscoveryBackend()
    effective_min_cluster_size = active_contract.effective_min_cluster_size(max(1, len(review_ids)))
    labels, probabilities, outlier_scores = active_backend.discover(
        review_vectors,
        min_cluster_size=effective_min_cluster_size,
        min_samples=active_contract.min_samples,
        metric=active_contract.metric,
    )
    metrics = _neighbour_metrics(review_vectors, active_contract.neighbor_k)
    review_index = {review_id: index for index, review_id in enumerate(review_ids)}
    region_specs: list[tuple[str, list[int]]] = []
    for label in sorted(set(int(value) for value in labels if int(value) >= 0)):
        indices = [index for index, value in enumerate(labels) if int(value) == label]
        region_specs.append(("rare_region" if len(indices) <= active_contract.rare_region_max_size else "dense_region", indices))
    noise_indices = {index for index, value in enumerate(labels) if int(value) < 0}
    for component in _components(review_ids, review_vectors, noise_indices):
        if len(component) >= 2 and len(component) <= active_contract.rare_region_max_size:
            region_specs.append(("rare_region", component))
        else:
            region_specs.extend(("outlier", [index]) for index in component)

    metadata: dict[str, Mapping[str, Any]] = dict(review_metadata or {})
    # Raw review metadata remains authoritative; this only supplies the
    # derived semantic-text hash needed for duplicate-support diagnostics.
    for review_id, review_units in grouped.items():
        if review_id not in metadata:
            metadata[review_id] = {"semantic_text_hash": review_units[0].semantic_text_hash}
        elif not metadata[review_id].get("semantic_text_hash"):
            metadata[review_id] = {**metadata[review_id], "semantic_text_hash": review_units[0].semantic_text_hash}
    regions: list[dict[str, Any]] = []
    for discovery_type, indices in region_specs:
        member_reviews = [review_ids[index] for index in indices]
        member_units = [unit for review_id in member_reviews for unit in grouped[review_id]]
        centroid = _normalise(np.mean(review_vectors[indices], axis=0))
        distances = [(review_id, float(np.dot(review_vectors[review_index[review_id]], centroid))) for review_id in member_reviews]
        representatives = [item[0] for item in sorted(distances, key=lambda item: (-item[1], item[0]))[:5]]
        summary = _review_summary(member_reviews, metadata)
        overlap = {}
        if stage2e:
            for key, values in stage2e.items():
                if isinstance(values, Mapping):
                    overlap_key = key.replace("_cluster", "_overlap_n")
                    overlap[overlap_key] = sum(1 for review_id in member_reviews if review_id in values)
        score_values = [float(outlier_scores[index]) for index in indices] if len(outlier_scores) else []
        regions.append(
            {
                "region_id": _stable_region_id(discovery_type, member_reviews, active_contract),
                "discovery_type": discovery_type,
                "review_ids": sorted(member_reviews),
                "semantic_unit_ids": sorted(unit.unit_id for unit in member_units),
                "support_reviews": len(member_reviews),
                "support_units": len(member_units),
                "unique_text_n": summary["unique_text_n"],
                "duplicate_share": summary["duplicate_share"],
                "cohesion": _region_cohesion(indices, review_vectors),
                "nearest_region_distance": None,
                "languages": summary["languages"],
                "recommendation_distribution": summary["recommendation_distribution"],
                "time_distribution": summary["time_distribution"],
                "representative_review_ids": representatives,
                "representative_reason": "centroid_proximity",
                "membership_strength": {review_id: float(probabilities[review_index[review_id]]) for review_id in member_reviews},
                "outlier_score": max(score_values) if score_values else None,
                "neighborhood": {review_id: metrics.get(review_index[review_id], {}) for review_id in member_reviews},
                "taxonomy_audit": {},
                "taxonomy_coverage_status": "unavailable",
                "stage2e_overlap": overlap,
                "stability_score": None,
                "stability": "unstable",
            }
        )

    # Sensitivity runs are deliberately small and never optimized against taxonomy.
    stability_runs: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for size in active_contract.sensitivity_min_cluster_sizes(max(1, len(review_ids))):
        stability_runs[size] = active_backend.discover(
            review_vectors,
            min_cluster_size=size,
            min_samples=active_contract.min_samples,
            metric=active_contract.metric,
        )
    for region in regions:
        baseline_members = set(region["review_ids"])
        scores = []
        for labels_alt, _, _ in stability_runs.values():
            if region["discovery_type"] == "outlier":
                scores.append(1.0 if all(labels_alt[review_index[item]] < 0 for item in baseline_members) else 0.0)
                continue
            candidate_labels = {int(labels_alt[review_index[item]]) for item in baseline_members if labels_alt[review_index[item]] >= 0}
            best = 0.0
            for label in candidate_labels:
                alt_members = {review_ids[index] for index, value in enumerate(labels_alt) if int(value) == label}
                union = baseline_members | alt_members
                best = max(best, len(baseline_members & alt_members) / len(union) if union else 0.0)
            scores.append(best)
        region["stability_score"] = float(np.mean(scores)) if scores else None
        region["stability"] = _stability_label(region["stability_score"])

    if taxonomy_labels:
        from .taxonomy_audit import audit_region_taxonomy

        for region in regions:
            audit = audit_region_taxonomy(region["review_ids"], taxonomy_labels)
            region["taxonomy_audit"] = audit
            region["taxonomy_coverage_status"] = audit["coverage_status"]

    regions.sort(key=lambda region: region["region_id"])
    unit_audit = _unit_audit(ordered_units, active_contract.neighbor_k)
    clustered_reviews = sum(region["support_reviews"] for region in regions if region["discovery_type"] != "outlier")
    unclustered_reviews = sum(region["support_reviews"] for region in regions if region["discovery_type"] == "outlier")
    report = {
        "schema_version": SEMANTIC_DISCOVERY_REPORT_VERSION,
        "contract": active_contract.to_dict(population_n=len(review_ids)),
        "semantic_index_id": semantic_index_id,
        "research_run_id": research_run_id,
        "population_fingerprint": population_fingerprint,
        "semantic_index_fingerprint": semantic_index_fingerprint,
        "population_n": population_n,
        "indexed_review_n": len(review_ids),
        "semantic_unit_n": len(ordered_units),
        "review_representation": "normalized_mean_unit",
        "dense_region_n": sum(1 for region in regions if region["discovery_type"] == "dense_region"),
        "rare_region_n": sum(1 for region in regions if region["discovery_type"] == "rare_region"),
        "outlier_review_n": unclustered_reviews,
        "clustered_review_share": clustered_reviews / len(review_ids) if review_ids else 0.0,
        "unclustered_review_share": unclustered_reviews / len(review_ids) if review_ids else 0.0,
        "regions": regions,
        "unit_level_audit": unit_audit,
        "stability_distribution": _distribution(region["stability"] for region in regions),
        "taxonomy_audit": {
            "well_covered_region_n": sum(1 for region in regions if region["taxonomy_coverage_status"] == "well_covered"),
            "mixed_region_n": sum(1 for region in regions if region["taxonomy_coverage_status"] == "mixed_existing_labels"),
            "potential_gap_candidate_n": sum(1 for region in regions if region["taxonomy_coverage_status"] == "potential_gap"),
            "insufficient_label_coverage_n": sum(1 for region in regions if region["taxonomy_coverage_status"] == "insufficient_taxonomy_coverage"),
        },
        "limitations": {
            "review_level_mean_may_blur_multitopic_reviews": True,
            "discovery_is_not_topic_naming": True,
            "outlier_is_not_invalidity_or_severity": True,
            "region_support_is_not_population_prevalence": True,
            "taxonomy_is_audit_target_not_training_truth": True,
        },
    }
    fingerprint_payload = {
        "semantic_index_fingerprint": semantic_index_fingerprint,
        "contract": active_contract.fingerprint,
        "regions": [
            {"region_id": region["region_id"], "review_ids": region["review_ids"], "semantic_unit_ids": region["semantic_unit_ids"]}
            for region in regions
        ],
    }
    report["discovery_fingerprint"] = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return report
