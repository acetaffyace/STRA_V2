from __future__ import annotations

import numpy as np

from apps.api.senti_next.semantic_discovery import (
    SemanticDiscoveryContract,
    SemanticUnitRecord,
    _blockwise_neighbor_metrics,
    _blockwise_threshold_components,
    build_semantic_discovery,
)
from apps.api.senti_next.semantic_discovery_storage import _sanitize_discovery_error


def _brute_metrics(vectors: np.ndarray, k: int):
    similarity = np.clip(vectors @ vectors.T, -1.0, 1.0)
    np.fill_diagonal(similarity, -1.0)
    result = {}
    for index in range(len(vectors)):
        values = np.sort(similarity[index])[::-1][: min(k, len(vectors) - 1)]
        result[index] = {
            "nearest_neighbor_similarity": float(values[0]),
            "mean_k_neighbor_similarity": float(np.mean(values)),
            "local_density": float(np.mean(np.maximum(values, 0.0))),
        }
    return result


def test_blockwise_neighbors_match_bruteforce_oracle() -> None:
    rng = np.random.default_rng(3)
    vectors = rng.normal(size=(31, 12)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    actual = _blockwise_neighbor_metrics(vectors, 5, block_size=7)
    expected = _brute_metrics(vectors, 5)
    for index in expected:
        for key in expected[index]:
            assert np.isclose(actual[index][key], expected[index][key], rtol=1e-6, atol=1e-6)


def test_blockwise_components_match_threshold_graph() -> None:
    rng = np.random.default_rng(4)
    vectors = rng.normal(size=(25, 8)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    candidates = set(range(2, 24))
    expected = []
    remaining = set(candidates)
    similarity = vectors @ vectors.T
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        component = [start]
        queue = [start]
        while queue:
            current = queue.pop()
            neighbours = sorted(index for index in remaining if similarity[current, index] >= 0.78)
            for index in neighbours:
                remaining.remove(index)
                component.append(index)
                queue.append(index)
        expected.append(sorted(component))
    assert _blockwise_threshold_components(vectors, candidates, block_size=5) == expected


class _RecordingBackend:
    identity = "recording"

    def __init__(self):
        self.calls: list[int] = []

    def discover(self, vectors, *, min_cluster_size, min_samples, metric):
        self.calls.append(min_cluster_size)
        labels = np.zeros(len(vectors), dtype=int) if len(vectors) else np.empty(0, dtype=int)
        return labels, np.ones(len(vectors)), np.zeros(len(vectors))


def _units(n: int = 16):
    return [
        SemanticUnitRecord(f"r{i}:0", f"r{i}", 0, np.eye(4, dtype=np.float32)[i % 4], f"hash-{i}")
        for i in range(n)
    ]


def test_stability_excludes_baseline_and_records_perturbation_parameters() -> None:
    backend = _RecordingBackend()
    report = build_semantic_discovery(
        _units(),
        semantic_index_id="idx",
        research_run_id="run",
        population_fingerprint="p",
        semantic_index_fingerprint="i",
        contract=SemanticDiscoveryContract(min_cluster_size=10, include_unit_level_audit=False),
        backend=backend,
    )
    assert backend.calls[0] == 10
    assert set(backend.calls[1:]) == {8, 12}
    assert all("10" not in region["stability_by_parameter"] for region in report["regions"])


def test_stability_is_not_estimable_when_perturbations_collapse_to_baseline() -> None:
    report = build_semantic_discovery(
        _units(2),
        semantic_index_id="idx",
        research_run_id="run",
        population_fingerprint="p",
        semantic_index_fingerprint="i",
        contract=SemanticDiscoveryContract(min_cluster_size=2, include_unit_level_audit=False),
        backend=_RecordingBackend(),
    )
    assert report["regions"]
    assert all(region["stability_score"] is None and region["stability"] == "not_estimable" for region in report["regions"])


def test_unit_level_audit_can_be_disabled_without_neighbor_work() -> None:
    report = build_semantic_discovery(
        _units(5),
        semantic_index_id="idx",
        research_run_id="run",
        population_fingerprint="p",
        semantic_index_fingerprint="i",
        contract=SemanticDiscoveryContract(min_cluster_size=3, include_unit_level_audit=False),
        backend=_RecordingBackend(),
    )
    assert report["unit_level_audit"] == {
        "status": "disabled",
        "unit_n": 5,
        "rare_neighborhood_candidate_n": None,
        "units": [],
    }


def test_discovery_errors_are_bounded_and_redacted() -> None:
    value = _sanitize_discovery_error(
        "Authorization: Bearer abc123 api_key=secret password=hunter2 https://user:pass@example.test/" + "x" * 3000
    )
    assert len(value) <= 2000
    assert "abc123" not in value
    assert "secret" not in value
    assert "hunter2" not in value
    assert "user:pass" not in value
