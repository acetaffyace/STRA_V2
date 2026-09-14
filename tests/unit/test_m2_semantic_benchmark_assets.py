from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tooling.evals.semantic_v2.validate_assets import source_content_hash, validate_manifest, validate_manifests


def _labels(*, status: str = "resolved", topic: str = "gameplay/controls", evidence: str = "controls feel great") -> dict:
    if status != "resolved":
        return {"semantic_status": status, "core_topic_ids": [], "secondary_game_topic_ids": [], "secondary_archetype_topic_ids": [], "semantic_mentions": [], "signals": [], "unresolved_reason": "insufficient semantic evidence"}
    mention = {"core_topic_id": topic, "secondary_game_topic_id": "gameplay-specific-controls", "secondary_archetype_topic_id": None, "signal_type": "praise", "evidence_spans": [evidence]}
    return {"semantic_status": "resolved", "core_topic_ids": [topic], "secondary_game_topic_ids": ["gameplay-specific-controls"], "secondary_archetype_topic_ids": [], "semantic_mentions": [mention], "signals": [{"core_topic_id": topic, "signal_type": "praise", "evidence_spans": [evidence]}], "evidence_spans": [evidence]}


def _record(sample_id: str, language: str, *, role: str, text: str = "The controls feel great.", status: str = "resolved") -> dict:
    evidence = "controls feel great"
    labels = _labels(status=status, evidence=evidence)
    record = {
        "record_schema_version": f"semantic-v2-{('boundary' if role == 'boundary_regression' else 'holdout')}-record-v1",
        "dataset_role": role, "sample_id": sample_id, "taxonomy_version": "stra-core-taxonomy-v2", "language": language,
        "source": {"source_system": "test-fixture", "app_id": 1, "source_review_id": sample_id, "source_snapshot_id": "review-snapshot-test", "source_content_hash": source_content_hash(text), "source_review_text": text},
        "annotation_provenance": {"annotator_id": "human-test-1", "annotation_method": "human_double_annotation", "first_pass": labels, "final": labels, "disagreement_state": "no_disagreement", "reviewer_id": None},
        "gold": labels,
    }
    if role == "boundary_regression":
        record["boundary_metadata"] = {"boundary_category": "mechanics_vs_controls", "confusion_topic_ids": ["gameplay/mechanics", "gameplay/controls"], "policy_edge_cases": ["short_review"]}
    else:
        record["holdout_metadata"] = {"sampling_stratum": "language_stratified", "evaluation_only": True, "calibration_training_use": "prohibited"}
    return record


def _manifest(root: Path, *, role: str, records: list[dict], evaluation_only: bool | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    asset_name = "boundary.jsonl" if role == "boundary_regression" else "holdout.jsonl"
    asset = root / asset_name
    asset.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records), encoding="utf-8")
    if evaluation_only is None:
        evaluation_only = role == "evaluation_holdout"
    manifest = {"schema_version": "semantic-v2-benchmark-manifest-v2", "asset_type": role, "dataset_identity": {"dataset_id": f"test-{role}", "dataset_version": "test-v2", "taxonomy_version": "stra-core-taxonomy-v2", "guideline_version": "stra-semantic-v2-guidelines-v1", "source_collection": "test-source", "source_collection_hash": "test-source-hash", "annotation_protocol_version": "stra-semantic-v2-human-annotation-v1", "evaluation_code_commit": "test-commit"}, "minimum_primary_language_support": 1, "calibration_training_policy": {"evaluation_only": evaluation_only, "allowed_for_calibration_training": not evaluation_only}, "asset": {"path": asset_name, "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(), "min_examples": len(records), "max_examples": len(records)}}
    path = root / f"{role}.manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_separate_v2_manifests_accept_complete_human_contract(tmp_path: Path) -> None:
    boundary = _manifest(tmp_path / "boundary", role="boundary_regression", records=[_record("b-1", "en", role="boundary_regression")])
    holdout = _manifest(tmp_path / "holdout", role="evaluation_holdout", records=[_record("h-en", "en", role="evaluation_holdout", text="The controls feel great in English."), _record("h-zh", "zh", role="evaluation_holdout", text="操作很顺手。 controls feel great"), _record("h-ja", "ja", role="evaluation_holdout", text="操作が快適です。 controls feel great")])
    assert validate_manifest(boundary)["valid"] is True
    assert validate_manifest(holdout)["valid"] is True
    assert validate_manifests([boundary, holdout])["valid"] is True


def test_cross_manifest_source_hash_overlap_is_rejected(tmp_path: Path) -> None:
    text = "The controls feel great."
    boundary = _manifest(tmp_path / "boundary", role="boundary_regression", records=[_record("b-1", "en", role="boundary_regression", text=text)])
    holdout = _manifest(tmp_path / "holdout", role="evaluation_holdout", records=[_record("h-1", "en", role="evaluation_holdout", text=text), _record("h-zh", "zh", role="evaluation_holdout"), _record("h-ja", "ja", role="evaluation_holdout")])
    report = validate_manifests([boundary, holdout])
    assert report["valid"] is False
    assert any("source_content_hash overlaps" in error for error in report["errors"])


def test_unresolved_record_is_explicit_and_holdout_policy_is_fail_closed(tmp_path: Path) -> None:
    records = [_record("h-en", "en", role="evaluation_holdout", status="unresolved", text="No clear semantic assertion."), _record("h-zh", "zh", role="evaluation_holdout", text="操作很顺手。 controls feel great"), _record("h-ja", "ja", role="evaluation_holdout", text="操作が快適です。 controls feel great")]
    report = validate_manifest(_manifest(tmp_path, role="evaluation_holdout", records=records, evaluation_only=False))
    assert report["valid"] is False
    assert any("prohibited from calibration/training" in error for error in report["errors"])
    assert not any("unresolved_reason" in error for error in report["errors"])


def test_model_generated_annotation_method_is_not_accepted(tmp_path: Path) -> None:
    record = _record("b-1", "en", role="boundary_regression")
    record["annotation_provenance"]["annotation_method"] = "model_generated_label"
    report = validate_manifest(_manifest(tmp_path, role="boundary_regression", records=[record]))
    assert report["valid"] is False
    assert any("must identify a human method" in error for error in report["errors"])
