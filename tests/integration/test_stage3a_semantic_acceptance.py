"""Cross-layer Stage 3A acceptance invariants.

These tests use the deterministic fake backend; the optional real-model smoke
is deliberately separate so CI never downloads model artifacts.
"""
from __future__ import annotations

import copy
import json

from apps.api.senti_next.activity_diagnostics import analyze_review_activity
from apps.api.senti_next.embedding_backend import FakeEmbeddingBackend
from apps.api.senti_next.research_core import build_snapshot_research_report
from apps.api.senti_next.semantic_index import SemanticIndexContract, build_semantic_index


def _population() -> list[dict]:
    return [
        {
            "recommendationid": "a",
            "review": "Game crashes after the update",
            "timestamp_created": 1_700_000_000,
            "voted_up": False,
            "language": "english",
        },
        {
            "recommendationid": "b",
            "review": "更新后游戏崩溃",
            "timestamp_created": 1_700_100_000,
            "voted_up": True,
            "language": "schinese",
        },
        {
            "recommendationid": "c",
            "review": "アップデート後にゲームがクラッシュする",
            "timestamp_created": 1_700_200_000,
            "voted_up": True,
            "language": "japanese",
        },
        {"recommendationid": "d", "review": "", "timestamp_created": 1_700_300_000, "voted_up": None},
    ]


def _metadata() -> dict:
    return {
        "app_id": 123,
        "collection_complete": True,
        "truncated_by_max_reviews": False,
        "stop_reason": "end_of_results",
        "coverage_status": "complete",
        "sampling_contract": {
            "app_id": 123,
            "languages": ["english", "schinese", "japanese"],
            "review_type": "all",
            "purchase_type": "all",
            "collection_order": "recent",
            "include_offtopic_activity": True,
            "max_reviews": 100,
        },
    }


def test_stage3a_does_not_change_research_report_or_stage2e() -> None:
    population = _population()
    metadata = _metadata()
    before = build_snapshot_research_report(population, metadata=metadata)
    before_activity = analyze_review_activity(population)
    backend = FakeEmbeddingBackend(dimensions=16)
    contract = SemanticIndexContract.from_backend(backend)
    index = build_semantic_index(
        population,
        research_run_id="run-stage3a",
        population_fingerprint="population-stage3a",
        contract=contract,
        backend=backend,
    )
    after = build_snapshot_research_report(population, metadata=metadata)
    after_activity = analyze_review_activity(population)
    assert before == after
    assert before_activity == after_activity
    assert index.population_n == before["population"]["review_count"] == 4
    assert index.indexed_review_n == 3
    assert index.semantic_unit_n == 3
    assert all("taxonomy" not in unit.semantic_text.lower() for unit in index.units)
    assert json.dumps(before, sort_keys=True, allow_nan=False)


def test_stage3a_preserves_raw_input_and_duplicate_denominator() -> None:
    population = [
        {"recommendationid": str(i), "review": "same exact text", "voted_up": i % 2 == 0}
        for i in range(10)
    ]
    original = copy.deepcopy(population)
    backend = FakeEmbeddingBackend(dimensions=16)
    result = build_semantic_index(
        population,
        research_run_id="run-duplicate",
        population_fingerprint="population-duplicate",
        contract=SemanticIndexContract.from_backend(backend),
        backend=backend,
    )
    assert population == original
    assert result.population_n == 10
    assert result.indexed_review_n == 10
    assert result.unique_embedding_n == 1
    assert len(result.members) == 10


def test_semantic_index_module_has_no_taxonomy_or_llm_dependency() -> None:
    import ast
    import inspect
    import apps.api.senti_next.semantic_index as module

    imported = {
        alias.name
        for node in ast.walk(ast.parse(inspect.getsource(module)))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        alias.module
        for node in ast.walk(ast.parse(inspect.getsource(module)))
        if isinstance(node, ast.ImportFrom)
        for alias in [node]
    )
    assert not any(name and ("taxonomy" in name or name.endswith(".llm") or ".routes" in name) for name in imported)
