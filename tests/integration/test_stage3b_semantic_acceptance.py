"""Cross-layer Stage 3B acceptance invariants.

The discovery pass is deliberately exercised with deterministic vectors.  The
test proves that discovery is a read-only consumer of the frozen Research Core,
Stage 2E diagnostics, Stage 3A vectors, and existing labels.
"""
from __future__ import annotations

import copy

import numpy as np

from apps.api.senti_next.activity_diagnostics import analyze_review_activity
from apps.api.senti_next.research_core import build_snapshot_research_report
from apps.api.senti_next.semantic_discovery import (
    SemanticDiscoveryContract,
    SemanticUnitRecord,
    build_semantic_discovery,
)


class _StaticBackend:
    identity = "stage3b-acceptance-backend"

    def discover(self, vectors, *, min_cluster_size, min_samples, metric):  # type: ignore[no-untyped-def]
        labels = np.asarray([0, 0, 0, 0, -1, -1], dtype=int)
        labels = labels[: len(vectors)]
        return labels, np.ones(len(vectors)), np.zeros(len(vectors))


def test_discovery_is_non_interfering_with_research_stage2e_and_taxonomy() -> None:
    population = [
        {
            "recommendationid": f"r{i}",
            "review": text,
            "timestamp_created": 1_700_000_000 + i,
            "voted_up": i % 2 == 0,
            "language": "english" if i % 2 == 0 else "schinese",
        }
        for i, text in enumerate(
            [
                "Game crashes after update",
                "Game crashes after update",
                "更新后游戏崩溃",
                "更新后游戏崩溃",
                "Controller support is excellent",
                "Save corruption after restart",
            ]
        )
    ]
    metadata = {
        "app_id": 123,
        "collection_complete": True,
        "coverage_status": "complete",
        "sampling_contract": {"app_id": 123, "languages": ["english", "schinese"]},
    }
    labels = {row["recommendationid"]: {"main_category": "technical/bugs"} for row in population}
    labels_before = copy.deepcopy(labels)
    units = [
        SemanticUnitRecord(
            f"{row['recommendationid']}:0",
            row["recommendationid"],
            0,
            np.asarray([1.0, 0.0] if i < 4 else [0.0, 1.0], dtype=np.float32),
            f"hash-{i // 2}",
            row["review"],
        )
        for i, row in enumerate(population)
    ]
    vectors_before = [unit.vector.copy() for unit in units]
    report_before = build_snapshot_research_report(population, metadata=metadata)
    activity_before = analyze_review_activity(population)

    discovery = build_semantic_discovery(
        units,
        semantic_index_id="semantic-index",
        research_run_id="research-run",
        population_fingerprint="population-fingerprint",
        semantic_index_fingerprint="index-fingerprint",
        contract=SemanticDiscoveryContract(min_cluster_size=4, rare_region_max_size=3, neighbor_k=2),
        review_metadata={row["recommendationid"]: row for row in population},
        taxonomy_labels=labels,
        backend=_StaticBackend(),
    )

    assert discovery["population_n"] == len(population)
    assert discovery["indexed_review_n"] == len(population)
    assert discovery["dense_region_n"] >= 1
    assert discovery["rare_region_n"] >= 1
    assert labels == labels_before
    assert all(np.array_equal(unit.vector, before) for unit, before in zip(units, vectors_before))
    assert build_snapshot_research_report(population, metadata=metadata) == report_before
    assert analyze_review_activity(population) == activity_before

