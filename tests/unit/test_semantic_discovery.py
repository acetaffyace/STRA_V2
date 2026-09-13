from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from apps.api.senti_next.semantic_discovery import (
    SemanticDiscoveryContract,
    SemanticUnitRecord,
    build_semantic_discovery,
)


class StaticBackend:
    identity = "static-test-backend"

    def __init__(self, labels: list[int], fragile: bool = False) -> None:
        self.labels = labels
        self.fragile = fragile
        self.calls = []

    def discover(self, vectors, *, min_cluster_size, min_samples, metric):  # type: ignore[no-untyped-def]
        self.calls.append(min_cluster_size)
        labels = list(self.labels)
        if self.fragile and min_cluster_size != min(self.calls):
            labels = [-1] * len(labels)
        return np.asarray(labels, dtype=int), np.ones(len(labels)), np.zeros(len(labels))


def _fixture():
    vectors = [
        [1.0, 0.0], [0.99, 0.1], [0.98, -0.1], [0.97, 0.12],
        [0.0, 1.0], [0.05, 0.99],
        [-1.0, 0.0],
    ]
    labels = [0, 0, 0, 0, -1, -1, -1]
    units = [SemanticUnitRecord(f"r{i}:0", f"r{i}", 0, np.asarray(vector, dtype=np.float32), f"text-{i}") for i, vector in enumerate(vectors)]
    metadata = {
        f"r{i}": {
            "voted_up": i % 2 == 0,
            "language": "english" if i % 2 == 0 else "schinese",
            "timestamp_created": 1_700_000_000 + i,
            "semantic_text_hash": f"text-{i}",
        }
        for i in range(len(vectors))
    }
    return units, metadata, labels


def test_dense_rare_and_outlier_regions_preserve_units_and_representatives() -> None:
    units, metadata, labels = _fixture()
    report = build_semantic_discovery(
        units,
        semantic_index_id="index",
        research_run_id="run",
        population_fingerprint="population",
        semantic_index_fingerprint="index-fingerprint",
        contract=SemanticDiscoveryContract(min_cluster_size=4, rare_region_max_size=3, neighbor_k=2),
        review_metadata=metadata,
        backend=StaticBackend(labels),
    )
    assert report["population_n"] == 7
    assert report["dense_region_n"] == 1
    assert report["rare_region_n"] == 1
    assert report["outlier_review_n"] == 1
    assert sum(region["support_reviews"] for region in report["regions"]) == 7
    dense = next(region for region in report["regions"] if region["discovery_type"] == "dense_region")
    assert len(dense["representative_review_ids"]) == 4
    assert dense["representative_reason"] == "centroid_proximity"
    rare = next(region for region in report["regions"] if region["discovery_type"] == "rare_region")
    assert rare["support_units"] == 2
    assert json.dumps(report, sort_keys=True, allow_nan=False)


def test_review_level_mean_and_unit_level_audit_are_both_retained() -> None:
    units, metadata, labels = _fixture()
    units = units + [SemanticUnitRecord("r0:1", "r0", 1, np.asarray([0.0, 1.0], dtype=np.float32), "tail")]
    report = build_semantic_discovery(
        units,
        semantic_index_id="index",
        research_run_id="run",
        population_fingerprint="population",
        semantic_index_fingerprint="index-fingerprint",
        review_metadata=metadata,
        backend=StaticBackend(labels),
    )
    assert report["semantic_unit_n"] == 8
    assert any("r0:1" in region["semantic_unit_ids"] for region in report["regions"])
    assert report["review_representation"] == "normalized_mean_unit"
    assert report["unit_level_audit"]["unit_n"] == 8
    assert any(item["semantic_unit_id"] == "r0:1" for item in report["unit_level_audit"]["units"])


def test_region_ids_and_results_are_input_order_invariant() -> None:
    units, metadata, labels = _fixture()
    contract = SemanticDiscoveryContract(min_cluster_size=4, rare_region_max_size=3)
    first = build_semantic_discovery(units, semantic_index_id="index", research_run_id="run", population_fingerprint="population", semantic_index_fingerprint="fingerprint", contract=contract, review_metadata=metadata, backend=StaticBackend(labels))
    second = build_semantic_discovery(list(reversed(units)), semantic_index_id="index", research_run_id="run", population_fingerprint="population", semantic_index_fingerprint="fingerprint", contract=contract, review_metadata=metadata, backend=StaticBackend(labels))
    assert [region["region_id"] for region in first["regions"]] == [region["region_id"] for region in second["regions"]]
    assert [(region["discovery_type"], region["review_ids"]) for region in first["regions"]] == [(region["discovery_type"], region["review_ids"]) for region in second["regions"]]


def test_contract_parameter_rule_and_validation() -> None:
    contract = SemanticDiscoveryContract()
    assert contract.effective_min_cluster_size(100) == 5
    assert contract.effective_min_cluster_size(1000) == 15
    assert contract.effective_min_cluster_size(10000) == 50
    with pytest.raises(ValueError):
        SemanticDiscoveryContract(metric="euclidean").validate()


def test_taxonomy_absent_discovery_still_works() -> None:
    units, _, labels = _fixture()
    report = build_semantic_discovery(units, semantic_index_id="index", research_run_id="run", population_fingerprint="population", semantic_index_fingerprint="fingerprint", contract=SemanticDiscoveryContract(min_cluster_size=4, rare_region_max_size=3), backend=StaticBackend(labels))
    assert report["dense_region_n"] == 1
    assert report["taxonomy_audit"]["well_covered_region_n"] == 0
