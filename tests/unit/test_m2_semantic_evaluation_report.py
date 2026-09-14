from __future__ import annotations

import pytest

from tooling.evals.semantic_v2.evaluate_predictions import evaluate_predictions


def _gold(sample_id: str, language: str, topic: str, *, novel: bool = False) -> dict:
    return {
        "sample_id": sample_id,
        "language": language,
        "taxonomy_version": "stra-core-taxonomy-v2",
        "semantic_eligible": True,
        "novel_topic_seed": novel,
        "gold": {"core_topic_ids": [topic], "evidence_spans": ["controls"]},
    }


def test_semantic_v2_report_contains_required_quality_slices() -> None:
    gold = [_gold("en-1", "english", "gameplay/controls"), _gold("zh-1", "schinese", "gameplay/controls", novel=True), _gold("ja-1", "japanese", "technical/bugs")]
    predictions = [
        {"sample_id": "en-1", "assignments": [{"core_topic_id": "gameplay/controls", "decision_band": "HIGH", "assignment_source": "prototype"}]},
        {"sample_id": "zh-1", "assignments": [{"core_topic_id": "gameplay/controls", "decision_band": "MEDIUM", "assignment_source": "llm_adjudication"}], "novel_topic_detected": True},
        {"sample_id": "ja-1", "assignments": []},
    ]
    report = evaluate_predictions(gold, predictions, minimum_topic_support=1, dataset_version="test-v1", semantic_config_hash="sha", evaluation_code_commit="commit")
    assert report["taxonomy_version"] == "stra-core-taxonomy-v2"
    assert report["all"]["multilabel_micro"]["f1"] == pytest.approx(0.8)
    assert report["all"]["decision_band"]["high_precision"] == 1.0
    assert report["all"]["unresolved_rate"] == pytest.approx(1 / 3)
    assert report["all"]["llm_escalation_rate"] == pytest.approx(1 / 3)
    assert report["all"]["seeded_novel_topic_discovery"]["recall"] == 1.0
    assert set(report["language_slices"]) == {"en", "zh", "ja"}


def test_semantic_v2_report_rejects_old_taxonomy() -> None:
    with pytest.raises(ValueError, match="stra-core-taxonomy-v2"):
        evaluate_predictions(
            [{**_gold("old", "english", "gameplay/controls"), "taxonomy_version": "sentinext-taxonomy-v1"}],
            [{"sample_id": "old", "assignments": []}],
        )

