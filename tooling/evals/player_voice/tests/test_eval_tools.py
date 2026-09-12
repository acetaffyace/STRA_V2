from pathlib import Path
import json

import pytest

from tooling.evals.player_voice.common import source_hash
from tooling.evals.player_voice.evaluate import evaluate
from tooling.evals.player_voice.select_samples import select_records
from tooling.evals.player_voice.split_dataset import split_records
from tooling.evals.player_voice.validate_annotations import validate_records


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures" / "scorer_fixture.jsonl"
PREDICTIONS = ROOT / "fixtures" / "predictions_fixture.jsonl"


def read_jsonl(path):
    return [__import__("json").loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_fixture_validation_and_hashes():
    records = read_jsonl(FIXTURE)
    assert validate_records(records) == []
    assert records[0]["source_review_hash"] == source_hash(records[0]["source_review_text"])


def test_validation_rejects_bad_taxonomy_and_duplicate_ids():
    records = read_jsonl(FIXTURE)
    bad = dict(records[0])
    bad["sample_id"] = records[1]["sample_id"]
    bad["gold"] = dict(bad["gold"], subcategories=["not/a/production-label"])
    errors = validate_records(records + [bad])
    assert any("duplicate sample_id" in error for error in errors)
    assert any("subcategories contains invalid" in error for error in errors)


def test_selection_is_deterministic_and_pending_only():
    source = [
        {"app_id": 1, "review_id": "a", "review_text": "Combat is great."},
        {"app_id": 2, "review_id": "b", "review_text": "Performance drops. Please add settings."},
    ]
    first = select_records(source, core_limit=1, challenge_limit=1, seed=7)
    second = select_records(source, core_limit=1, challenge_limit=1, seed=7)
    assert first == second
    assert {record["annotation_status"] for record in first} == {"pending"}
    assert all(record["source_review_hash"] == source_hash(record["source_review_text"]) for record in first)


def test_evaluator_reports_slices_and_support():
    result = evaluate(read_jsonl(FIXTURE), read_jsonl(PREDICTIONS))
    assert result["groups"]["all"]["support"] == 2
    assert result["groups"]["core"]["support"] == 1
    assert result["groups"]["challenge"]["support"] == 1
    assert "confusion_matrix" in result["groups"]["all"]["sentiment"]


def test_slice_metrics_filter_predictions_and_report_actionable_taxonomy():
    gold = [
        {"sample_id": "core", "annotation_status": "labeled", "sampling_stratum": "core", "language": "english", "gold": {"subcategories": ["gameplay/mechanics"], "issue_present": False, "issue_labels": [], "request_present": False, "request_labels": []}},
        {"sample_id": "challenge", "annotation_status": "labeled", "sampling_stratum": "challenge", "language": "english", "gold": {"subcategories": [], "issue_present": False, "issue_labels": [], "request_present": False, "request_labels": []}},
    ]
    predictions = [
        {"sample_id": "core", "prediction": {"subcategories": ["gameplay/mechanics"], "issue_labels": [], "request_labels": []}},
        {"sample_id": "challenge", "prediction": {"subcategories": ["other/general"], "issue_labels": [], "request_labels": []}},
        {"sample_id": "outside-slice", "prediction": {"subcategories": ["gameplay/mechanics"], "issue_labels": ["technical/bugs"], "request_labels": ["gameplay/mechanics"]}},
    ]
    result = evaluate(gold, predictions)
    assert result["groups"]["core"]["taxonomy_full_micro"] == result["groups"]["core"]["subcategories"]["micro"]
    assert result["groups"]["core"]["subcategories"]["micro"]["fp"] == 0
    assert result["groups"]["challenge"]["subcategories"]["micro"]["predicted"] == 1
    assert result["groups"]["challenge"]["taxonomy_actionable_micro"]["predicted"] == 0
    assert result["groups"]["challenge"]["no_actionable_topic_accuracy"]["accuracy"] == 1.0


def test_split_refuses_unlabeled_and_is_deterministic_after_annotation():
    pending = read_jsonl(FIXTURE)
    pending[0]["annotation_status"] = "pending"
    with pytest.raises(ValueError, match="labeled"):
        split_records(pending)
    records = read_jsonl(FIXTURE)
    left_a, right_a = split_records(records)
    left_b, right_b = split_records(records)
    assert [item["sample_id"] for item in left_a] == [item["sample_id"] for item in left_b]
    assert [item["sample_id"] for item in right_a] == [item["sample_id"] for item in right_b]
    if len(records) >= 10:
        assert 0.2 <= len(right_a) / len(records) <= 0.3


def test_prediction_runner_is_cache_isolated():
    source = (ROOT / "run_predictions.py").read_text(encoding="utf-8")
    assert "classify_reviews_batch" in source
    assert "ensure_review_labels" not in source


def test_issue_semantics_audit_preserves_gold_and_flags_positive_candidates():
    repo_root = Path(__file__).parents[4]
    audit_path = repo_root / "tooling" / "evals" / "reports" / "P0_5CV_ISSUE_SEMANTIC_AUDIT.json"
    gold_path = repo_root / "tooling" / "evals" / "gold" / "P0_5B_gold_verified.jsonl"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    gold = read_jsonl(gold_path)

    assert audit["gold_mutated"] is False
    assert audit["prediction_artifacts_mutated"] is False
    candidates = audit["candidates"]
    assert audit["positive_issue_candidate_count"] == 16
    assert len(candidates) == 16
    assert all(item["requires_human_review"] for item in candidates)
    assert all(item["sentiment"] == "positive" for item in candidates)

    gold_by_id = {item["sample_id"]: item for item in gold}
    assert all(gold_by_id[item["sample_id"]]["gold"]["issue_present"] is True for item in candidates)


def test_production_issue_contract_distinguishes_aspects_from_problems():
    prompt = (Path(__file__).parents[4] / "apps" / "api" / "senti_next" / "llm.py").read_text(encoding="utf-8")
    assert "only problems/complaints" in prompt
    assert "subset of subcategories" in prompt
    assert "only explicit requests" in prompt
